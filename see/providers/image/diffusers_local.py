"""DiffusersImageProvider：本機 open-weight 模型生圖（LOCAL_FREE）。**絕不自動下載權重。**

- 模型由 preset / model_id 指定；核心 pipeline 不知道是哪個模型（Provider Agnostic）。
- `local_files_only=True`：權重必須已在本機 HF cache 或 `model_path`；缺權重 → ProviderUnavailable。
- 低 VRAM（≤ 6 GB，例如 GTX 1650 4 GB）自動啟用：fp16、attention slicing、VAE slicing/tiling、
  model CPU offload、較低生成解析度；OOM 時再降一級重試一次，仍失敗才交給 Fallback（placeholder）。
"""

from __future__ import annotations

import gc
import importlib.util
import logging
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from see.core.errors import ProviderError, ProviderUnavailable
from see.core.image_qa import image_defect, image_stats
from see.models.cost import CostEstimate
from see.models.enums import CostTier, ProviderKind
from see.models.provider import ProviderInfo
from see.providers.base import ImageProvider, ImageRequest, ImageResult

MODEL_PRESETS: dict[str, dict[str, Any]] = {
    "flux-schnell": {"model_id": "black-forest-labs/FLUX.1-schnell", "steps": 4, "guidance": 0.0, "max_side": 1024,
                     "variant": None, "multiple": 16, "download_gb": 24.0, "allow_patterns": None},
    "sd15": {"model_id": "stable-diffusion-v1-5/stable-diffusion-v1-5", "steps": 25, "guidance": 7.0, "max_side": 512,
             "variant": "fp16", "multiple": 8, "download_gb": 2.2,
             # D-022：fp32 升級不另外下載 fp32 權重，而是把同一份 fp16 權重在載入時 upcast（diffusers 依 dtype cast 浮點參數）
             "fp32_escalation": "upcast fp16 variant at load (no extra download)",
             # 只抓 fp16 權重與設定；略過 safety_checker（省 ~600MB 與 VRAM）
             "allow_patterns": ["*.json", "*.txt", "tokenizer/*", "scheduler/*", "feature_extractor/*",
                                "unet/diffusion_pytorch_model.fp16.safetensors",
                                "vae/diffusion_pytorch_model.fp16.safetensors",
                                "text_encoder/model.fp16.safetensors"]},
}
LOW_VRAM_MB = 6_500
PROVIDER_VERSION = "3"  # D-021：bump 使 Batch 7/8 舊 fp16 路徑留下的 image fingerprint 全部失效（強制重生）
log = logging.getLogger("see.image.diffusers")


@dataclass(frozen=True)
class RuntimePlan:
    """純函式可測的推理策略（不碰 torch）。"""

    device: str
    dtype: str
    low_vram: bool
    attention_slicing: bool
    vae_slicing: bool
    cpu_offload: bool
    max_side: int
    vae_fp32: bool = False  # VAE 以 fp32 跑（GTX 16xx 等卡 fp16 VAE 會出 NaN → 黑圖）

    def downgrade_memory(self) -> "RuntimePlan":
        """OOM 後的下一級：解析度減 128（下限 384），並強制全部省記憶體選項。"""
        return RuntimePlan(self.device, self.dtype, True, True, True, True, max(self.max_side - 128, 384), self.vae_fp32)

    def downgrade_numeric(self) -> "RuntimePlan | None":
        """NaN／黑圖後的下一級：先 VAE fp32，再整個 pipeline fp32；都試過回 None。"""
        if self.dtype == "float16" and not self.vae_fp32:
            return RuntimePlan(self.device, "float16", self.low_vram, self.attention_slicing, self.vae_slicing,
                               self.cpu_offload, self.max_side, vae_fp32=True)
        if self.dtype == "float16":
            return RuntimePlan(self.device, "float32", True, True, True, True, min(self.max_side, 512), vae_fp32=True)
        return None

    # 向後相容
    def downgrade(self) -> "RuntimePlan":
        return self.downgrade_memory()


_FP16_FRAGILE_GPUS = ("gtx 1650", "gtx 1660", "gtx 16")  # Turing 無 tensor core，fp16 VAE/UNet 常出 NaN


def gpu_prefers_fp32_vae(gpu_name: str | None) -> bool:
    n = (gpu_name or "").lower()
    return any(k in n for k in _FP16_FRAGILE_GPUS)


def make_runtime_plan(device: str, vram_mb: int | None, preset_max_side: int, gpu_name: str | None = None) -> RuntimePlan:
    if device == "cuda":
        low = vram_mb is None or vram_mb <= LOW_VRAM_MB
        return RuntimePlan(device="cuda", dtype="float16", low_vram=low, attention_slicing=low, vae_slicing=low,
                           cpu_offload=low, max_side=min(preset_max_side, 512) if low else preset_max_side,
                           vae_fp32=gpu_prefers_fp32_vae(gpu_name))
    if device == "mps":
        return RuntimePlan("mps", "float32", False, True, True, False, preset_max_side)
    return RuntimePlan("cpu", "float32", True, True, True, False, min(preset_max_side, 512))


def is_numeric_failure(arr: Any) -> bool:
    """判斷生成結果是否為 NaN／全黑（fp16 溢位的典型症狀）。arr：numpy float 影像陣列 [0,1]。"""
    import numpy as np

    a = np.asarray(arr, dtype=np.float32)
    if a.size == 0 or np.isnan(a).any() or np.isinf(a).any():
        return True
    return float(a.max()) < 0.02  # 幾乎全黑


def gen_size(width: int, height: int, max_side: int, multiple: int) -> tuple[int, int]:
    scale = min(max_side / max(width, height), 1.0)
    gw = max(int(width * scale) // multiple * multiple, 256)
    gh = max(int(height * scale) // multiple * multiple, 256)
    return gw, gh


GEN_POLICIES = ("fit", "native")


def gen_size_native(width: int, height: int, short_side: int, multiple: int, max_ratio: float = 1.5) -> tuple[int, int]:
    """D-035 診斷策略：短邊維持模型原生解析度（SD 1.5＝512），長邊最多 short×max_ratio；之後再中心裁切回目標比例。

    `fit`（舊行為）把 16:9 的長邊壓到 512 → 512×288，短邊遠低於 SD 1.5 訓練解析度，是 scene adherence 異常的主要嫌疑。
    """
    ar = width / height
    r = min(max(ar, 1 / ar), max_ratio)
    long_ = max(int(short_side * r) // multiple * multiple, short_side)
    short = short_side // multiple * multiple
    return (long_, short) if ar >= 1 else (short, long_)


def center_crop_to_aspect(w: int, h: int, target_w: int, target_h: int) -> tuple[int, int, int, int]:
    """回傳 (left, top, right, bottom)：把 w×h 中心裁成 target 比例（純函式，可測）。"""
    t = target_w / target_h
    if w / h > t:
        nw = int(round(h * t))
        left = (w - nw) // 2
        return left, 0, left + nw, h
    nh = int(round(w / t))
    top = (h - nh) // 2
    return 0, top, w, top + nh


def download_plan(preset: str) -> dict[str, Any]:
    cfg = MODEL_PRESETS[preset]
    return {"preset": preset, "model_id": cfg["model_id"], "estimated_gb": cfg["download_gb"],
            "allow_patterns": cfg["allow_patterns"], "variant": cfg["variant"],
            "fp32_escalation": cfg.get("fp32_escalation", "n/a")}


WEIGHT_COMPONENTS = ("unet", "vae", "text_encoder")


def local_weight_variants(model_path: str | Path) -> dict[str, set[str | None]]:
    """每個元件資料夾實際存在的權重 variant（None = 無 variant 的 fp32 檔）。純檔案系統檢查，不碰 torch。"""
    out: dict[str, set[str | None]] = {}
    for comp in WEIGHT_COMPONENTS:
        d = Path(model_path) / comp
        found: set[str | None] = set()
        for f in d.glob("*.safetensors") if d.is_dir() else []:
            parts = f.name.split(".")
            found.add(parts[-2] if len(parts) >= 3 else None)  # model.fp16.safetensors → "fp16"
        for f in d.glob("*.bin") if d.is_dir() else []:
            parts = f.name.split(".")
            found.add(parts[-2] if len(parts) >= 3 else None)
        out[comp] = found
    return out


def pick_variant(model_path: str | None, preferred: str | None, plan_dtype: str) -> str | None:
    """決定 from_pretrained 的 `variant`，使 runtime 階梯與實際下載內容一致（D-022）。

    規則：優先用所有元件都齊的 variant；preferred（fp16）齊 → 用它（dtype=float32 時由 diffusers 載入即 upcast，
    不需要 fp32 檔）；否則無 variant 檔齊 → None；都不齊 → ProviderError 指向 image-download。
    model_path=None（HF cache）無法檢查 → 維持舊行為。
    """
    if not model_path:
        return preferred if plan_dtype == "float16" else None
    have = local_weight_variants(model_path)
    complete = set.intersection(*have.values()) if have else set()
    if preferred in complete:
        return preferred
    if None in complete:
        return None
    missing = {c: sorted(str(v) for v in vs) for c, vs in have.items()}
    raise ProviderError(f"model weights incomplete at {model_path}: per-component variants {missing}; "
                        f"re-run `python -m see.app.cli image-download --yes`")


def diffusers_supports_dtype_kwarg() -> bool:
    """diffusers ≥ 0.36 以 `dtype=` 取代 `torch_dtype=`（後者 FutureWarning）。以 `_resolve_dtype` 存在與否判斷。"""
    try:
        from diffusers.pipelines import pipeline_utils  # type: ignore

        return hasattr(pipeline_utils, "_resolve_dtype")
    except Exception:  # noqa: BLE001
        return False


def load_kwargs(plan: RuntimePlan, variant: str | None, preset: str, dtype_obj: Any, supports_dtype: bool) -> dict[str, Any]:
    """from_pretrained 參數（純函式可測）。variant 由 pick_variant 決定，不再綁 plan.dtype。"""
    kw: dict[str, Any] = {("dtype" if supports_dtype else "torch_dtype"): dtype_obj, "local_files_only": True}
    if variant:
        kw["variant"] = variant
    if preset == "sd15":
        kw["safety_checker"] = None  # 未下載 safety_checker；省 VRAM
        kw["feature_extractor"] = None  # 只有 safety_checker 需要；避免 torchvision warning
    return kw


def _torch_available() -> bool:
    return importlib.util.find_spec("torch") is not None and importlib.util.find_spec("diffusers") is not None


def _weights_present(model_id: str, model_path: str | None) -> bool:
    if model_path:
        return (Path(model_path) / "model_index.json").exists()
    if importlib.util.find_spec("huggingface_hub") is None:
        return False
    try:
        from huggingface_hub import scan_cache_dir  # type: ignore

        return any(r.repo_id == model_id for r in scan_cache_dir().repos)
    except Exception:  # noqa: BLE001
        return False


SCHEDULERS = ("default", "dpmpp_2m_karras", "euler_a")


def make_scheduler(name: str, config: Any) -> Any:
    """依名稱建立 diffusers scheduler（A1111 名稱對照）；default＝模型自帶（SD 1.5＝PNDM）。"""
    if name == "dpmpp_2m_karras":
        from diffusers import DPMSolverMultistepScheduler  # type: ignore

        return DPMSolverMultistepScheduler.from_config(config, use_karras_sigmas=True, algorithm_type="dpmsolver++")
    if name == "euler_a":
        from diffusers import EulerAncestralDiscreteScheduler  # type: ignore

        return EulerAncestralDiscreteScheduler.from_config(config)
    raise ValueError(f"unknown scheduler '{name}'; known: {SCHEDULERS}")


def _cuda_peak_mb(torch: Any, reset: bool = False) -> float | None:
    try:
        if not torch.cuda.is_available():
            return None
        if reset:
            torch.cuda.reset_peak_memory_stats()
            return None
        return round(torch.cuda.max_memory_allocated() / 2**20, 1)
    except Exception:  # noqa: BLE001
        return None


def final_layer_norm_of(text_encoder: Any) -> Any:
    """transformers 4.x：`CLIPTextModel.text_model.final_layer_norm`；5.x 把 CLIPTextTransformer 攤平，
    `final_layer_norm` 直接掛在 `CLIPTextModel` 上（diffusers ≤0.41 的 clip_skip 路徑只認 4.x 形狀 → AttributeError，D-040）。"""
    inner = getattr(text_encoder, "text_model", None)
    ln = getattr(inner, "final_layer_norm", None) if inner is not None else None
    if ln is None:
        ln = getattr(text_encoder, "final_layer_norm", None)
    if ln is None:
        raise ProviderError("text encoder has no final_layer_norm (neither 4.x nor 5.x CLIPTextModel layout)")
    return ln


def encode_prompt_clip_skip(pipe: Any, prompt: str, negative: str, clip_skip_a1111: int) -> tuple[Any, Any, dict[str, Any]]:
    """A1111「Clip skip = N」語意：取 `hidden_states[-N]`（N=1＝最後一層）再套 final_layer_norm（A1111 與 diffusers 皆如此）。
    不呼叫 diffusers 的 `clip_skip=` 參數（0.41 與 transformers 5.x 不相容），改自行編碼並傳 prompt_embeds。

    執行期驗證（寫進 evidence）：`len(hidden_states) == num_hidden_layers + 1`，且 `final_layer_norm(hidden_states[-1])`
    必須與 `last_hidden_state` 逐元素相等 → 證明 hidden_states 順序為「embeddings, layer1 … layerL」，
    `hidden_states[-N]` 才是倒數第 N 層；不成立則 raise，不產生語意錯誤的圖。
    """
    import torch  # type: ignore

    if clip_skip_a1111 < 1:
        raise ValueError("clip_skip_a1111 must be >= 1")
    tok, te = pipe.tokenizer, pipe.text_encoder
    device = getattr(pipe, "_execution_device", None) or next(te.parameters()).device
    ln = final_layer_norm_of(te)
    num_layers = int(te.config.num_hidden_layers)
    if clip_skip_a1111 > num_layers:
        raise ValueError(f"clip skip {clip_skip_a1111} exceeds num_hidden_layers {num_layers}")

    def _one(text: str) -> tuple[Any, dict[str, Any]]:
        ids = tok(text, padding="max_length", max_length=tok.model_max_length, truncation=True, return_tensors="pt").input_ids
        out = te(ids.to(device), output_hidden_states=True)
        hs = out.hidden_states
        last = out.last_hidden_state
        if hs is None or len(hs) != num_layers + 1:
            raise ProviderError(f"unexpected hidden_states length {None if hs is None else len(hs)} (expected {num_layers + 1})")
        if not torch.allclose(ln(hs[-1]).float(), last.float(), atol=1e-4, rtol=1e-4):
            raise ProviderError("hidden_states ordering check failed: final_layer_norm(hidden_states[-1]) != last_hidden_state")
        emb = ln(hs[-clip_skip_a1111])
        return emb, {"hidden_states_len": len(hs), "layer_index_used": len(hs) - clip_skip_a1111, "ordering_verified": True}

    pe, info = _one(prompt)
    npe, _ = _one(negative or "")
    info.update({"clip_skip_a1111": clip_skip_a1111, "num_hidden_layers": num_layers,
                 "method": "manual hidden_states[-N] + final_layer_norm (A1111 semantics); bypasses diffusers clip_skip="})
    return pe, npe, info


# ---------------------------------------------------------------- D-051：S1 長 prompt 分段、S2 regional prompting（皆 opt-in）
CHUNK_TOKENS = 75  # 每段內容 token（加 BOS/EOS＝77，SD 1.5 CLIP 上限）
REGIONAL_BASE_RATIO = 0.2  # 共用 base prompt 權重（其餘 0.8 依區域 mask 分配；A1111 Regional Prompter 常用值）


def chunk_token_ids(ids: list[int], bos: int, eos: int, pad: int, n_chunks: int | None = None) -> list[list[int]]:
    """A1111 式長 prompt：內容 token（不含 BOS/EOS）每 75 一段 → 各段 [BOS]+段+[EOS]+pad 到 77。
    單段時與標準 tokenizer 輸出（padding=max_length）逐 id 相同。`n_chunks` 指定時以空段補齊（negative 對齊用）。純函式。"""
    body = [i for i in ids if i not in (bos, eos)] if ids[:1] == [bos] else list(ids)
    chunks = [body[i:i + CHUNK_TOKENS] for i in range(0, len(body), CHUNK_TOKENS)] or [[]]
    if n_chunks is not None:
        if n_chunks < len(chunks):
            raise ValueError(f"n_chunks {n_chunks} < required {len(chunks)}")
        chunks += [[] for _ in range(n_chunks - len(chunks))]
    width = CHUNK_TOKENS + 2
    return [([bos] + c + [eos] + [pad] * width)[:width] for c in chunks]


def latent_level_shape(hw: int, h0: int, w0: int) -> tuple[int, int]:
    """cross-attention 的序列長 hw 對應哪一層 UNet 解析度（SD 1.5 每層 stride-2 → 尺寸 ceil(n/2)）。純函式。"""
    h, w = h0, w0
    for _ in range(6):
        if h * w == hw:
            return h, w
        h, w = -(-h // 2), -(-w // 2)
    raise ProviderError(f"cannot map attention length {hw} to latent {h0}x{w0}")


def column_bounds(n: int, w: int) -> list[tuple[int, int]]:
    """n 個角色由左到右等分欄位（整數邊界、無縫覆蓋 0..w）。純函式。"""
    if n < 1:
        raise ValueError("n must be >= 1")
    edges = [round(j * w / n) for j in range(n + 1)]
    return [(edges[j], edges[j + 1]) for j in range(n)]


def encode_text_chunks(pipe: Any, texts: list[str], clip_skip_a1111: int) -> tuple[list[Any], dict[str, Any]]:
    """把每段文字分段編碼（A1111 clip skip 語意，同 D-040 驗證），**所有文字補到同樣段數** → 各自 (1, 77·c, dim)。"""
    import torch  # type: ignore

    tok, te = pipe.tokenizer, pipe.text_encoder
    device = getattr(pipe, "_execution_device", None) or next(te.parameters()).device
    ln = final_layer_norm_of(te)
    num_layers = int(te.config.num_hidden_layers)
    if not 1 <= clip_skip_a1111 <= num_layers:
        raise ValueError(f"clip skip {clip_skip_a1111} out of range 1..{num_layers}")
    bos, eos = int(tok.bos_token_id), int(tok.eos_token_id)
    pad = int(tok.pad_token_id) if tok.pad_token_id is not None else eos
    raw = [tok(t or "", add_special_tokens=False).input_ids for t in texts]
    n_chunks = max(max(1, -(-len(r) // CHUNK_TOKENS)) for r in raw)
    out = []
    for r in raw:
        ids = torch.tensor(chunk_token_ids([bos] + list(r) + [eos], bos, eos, pad, n_chunks), device=device)
        res = te(ids, output_hidden_states=True)
        hs = res.hidden_states
        if hs is None or len(hs) != num_layers + 1:
            raise ProviderError(f"unexpected hidden_states length {None if hs is None else len(hs)}")
        if not torch.allclose(ln(hs[-1]).float(), res.last_hidden_state.float(), atol=1e-4, rtol=1e-4):
            raise ProviderError("hidden_states ordering check failed")
        emb = ln(hs[-clip_skip_a1111])  # (c, 77, dim)
        out.append(emb.reshape(1, -1, emb.shape[-1]))
    return out, {"chunks": n_chunks, "content_tokens": [len(r) for r in raw], "clip_skip_a1111": clip_skip_a1111,
                 "method": "A1111-style 75-token chunks, each BOS+chunk+EOS, concatenated"}


REGION_RANK = {"left": 0, "center": 1, "right": 2}
IDENTITY_SCALE = 0.6  # IP-Adapter 臉部條件權重（文字 prompt 仍有效；常用 0.5–0.7）


def identity_column_masks(n: int, width: int, height: int) -> list[Any]:
    """S4：每個角色一張 IP-Adapter mask（左→右等分欄，與 two_characters_ab 的 on the left／right 對應）。PIL L 圖。"""
    from PIL import Image

    masks = []
    for a, b in column_bounds(n, width):
        m = Image.new("L", (width, height), 0)
        m.paste(255, (a, 0, b, height))
        masks.append(m)
    return masks


class RegionalAttnProcessor:
    """S2：cross-attention 分區（Regional Prompter／Latent Couple 類，零新模型）。
    encoder_hidden_states 是 [base, region_1 … region_n] 等長串接；每段各自做 attention，輸出依空間 mask 合成：
    out = r·base + (1−r)·Σ mask_i·region_i（mask 為左→右等分欄，總和恆為 1）。CFG 的 uncond 半邊各段相同 → 合成後等於原值。
    只裝在 attn2（cross-attention）；不支援的 Attention 變體直接 raise（fail-closed）。"""

    def __init__(self, n_regions: int, latent_hw: tuple[int, int], base_ratio: float = REGIONAL_BASE_RATIO) -> None:
        self.n, self.latent_hw, self.base_ratio = n_regions, latent_hw, base_ratio
        self._masks: dict[tuple[int, Any, Any], list[Any]] = {}

    def _masks_for(self, hw: int, device: Any, dtype: Any) -> list[Any]:
        import torch  # type: ignore

        key = (hw, device, dtype)
        if key not in self._masks:
            h, w = latent_level_shape(hw, *self.latent_hw)
            ms = []
            for a, b in column_bounds(self.n, w):
                m = torch.zeros(h, w, device=device, dtype=dtype)
                m[:, a:b] = 1
                ms.append(m.reshape(1, h * w, 1))
            self._masks[key] = ms
        return self._masks[key]

    def __call__(self, attn: Any, hidden_states: Any, encoder_hidden_states: Any = None, attention_mask: Any = None,
                 temb: Any = None, *args: Any, **kwargs: Any) -> Any:
        import torch  # type: ignore

        if encoder_hidden_states is None or hidden_states.ndim != 3 or attention_mask is not None:
            raise ProviderError("RegionalAttnProcessor: unsupported call (needs cross-attention, 3-D hidden states, no mask)")
        for flag in ("spatial_norm", "group_norm", "norm_cross"):
            if getattr(attn, flag, None) is not None:
                raise ProviderError(f"RegionalAttnProcessor: unsupported attention variant ({flag})")
        if getattr(attn, "residual_connection", False):
            raise ProviderError("RegionalAttnProcessor: unsupported residual_connection")
        segs = encoder_hidden_states.chunk(self.n + 1, dim=1)
        q = attn.head_to_batch_dim(attn.to_q(hidden_states))
        outs = []
        for e in segs:
            k, v = attn.head_to_batch_dim(attn.to_k(e)), attn.head_to_batch_dim(attn.to_v(e))
            outs.append(attn.batch_to_head_dim(torch.bmm(attn.get_attention_scores(q, k, None), v)))
        masks = self._masks_for(hidden_states.shape[1], hidden_states.device, outs[0].dtype)
        mixed = sum(m * o for m, o in zip(masks, outs[1:]))
        out = self.base_ratio * outs[0] + (1 - self.base_ratio) * mixed
        out = attn.to_out[1](attn.to_out[0](out))
        return out / getattr(attn, "rescale_output_factor", 1.0)


def regional_processors(unet: Any, n_regions: int, latent_hw: tuple[int, int]) -> dict[str, Any]:
    """attn2（cross-attention）換成 RegionalAttnProcessor，其餘保留原 processor。"""
    proc = RegionalAttnProcessor(n_regions, latent_hw)
    return {name: (proc if name.endswith("attn2.processor") else p) for name, p in unet.attn_processors.items()}


def _prompt_token_info(pipe: Any, prompt: str, negative: str) -> dict[str, Any]:
    """CLIP tokenizer 實際 token 數；超過 model_max_length（SD 1.5＝77，含 BOS/EOS）的部分會被 pipeline 靜默截斷。"""
    tok = getattr(pipe, "tokenizer", None)
    if tok is None:
        return {}
    try:
        limit = int(getattr(tok, "model_max_length", 77))
        n, nn = len(tok(prompt).input_ids), len(tok(negative or "").input_ids)
        return {"prompt_tokens": n, "negative_tokens": nn, "token_limit": limit,
                "prompt_truncated": n > limit, "negative_truncated": nn > limit}
    except Exception:  # noqa: BLE001
        return {}


class DiffusersImageProvider(ImageProvider):
    def __init__(self, preset: str = "sd15", model_path: str | None = None, device: str = "auto",
                 steps: int | None = None, guidance: float | None = None, checkpoint: Any = None,
                 checkpoint_path: str | None = None, scheduler: str | None = None,
                 identity_adapter: Any = None, identity_dir: str | None = None) -> None:
        if preset not in MODEL_PRESETS:
            raise ValueError(f"unknown preset '{preset}'; known: {sorted(MODEL_PRESETS)}")
        cfg = MODEL_PRESETS[preset]
        self.preset, self.cfg = preset, cfg
        self.model_id: str = cfg["model_id"]
        self.model_path = model_path
        self.device = device
        self.steps = steps or cfg["steps"]
        self.guidance = cfg["guidance"] if guidance is None else guidance
        self._pipe: Any = None
        self._plan: RuntimePlan | None = None
        self.calls = 0
        self.last_plan: RuntimePlan | None = None
        self.weights_variant: str | None = None
        self._floor: RuntimePlan | None = None  # 本程序內已證實需要的最低精度階梯（避免每景重走 fp16→NaN→fp32）
        # D-039：單檔 checkpoint（SD 1.5 架構）；model_path 仍是 base SD 1.5 diffusers 資料夾，只借它的 config／tokenizer
        self.checkpoint = checkpoint
        self.checkpoint_path = checkpoint_path
        # D-054（S4，opt-in）：Identity adapter（IP-Adapter）；None＝不載入，行為與既有完全相同
        self.identity_adapter = identity_adapter
        self.identity_dir = identity_dir
        self._id_encoder: Any = None
        self._id_cache: dict[tuple[str, ...], Any] = {}
        if checkpoint is not None and preset != "sd15":
            raise ValueError("single-file checkpoints are SD 1.5 architecture; use preset 'sd15'")
        self.scheduler_name = scheduler or (checkpoint.scheduler if checkpoint is not None else "default")
        if self.scheduler_name not in SCHEDULERS:
            raise ValueError(f"unknown scheduler '{self.scheduler_name}'; known: {SCHEDULERS}")

    @property
    def info(self) -> ProviderInfo:
        if self.checkpoint is not None:
            return ProviderInfo(name=f"diffusers-{self.preset}-ckpt", kind=ProviderKind.IMAGE, cost_tier=CostTier.LOCAL_FREE,
                                model=f"{self.checkpoint.checkpoint_id}@{self.checkpoint.sha256[:12]}", version=PROVIDER_VERSION)
        return ProviderInfo(name=f"diffusers-{self.preset}", kind=ProviderKind.IMAGE, cost_tier=CostTier.LOCAL_FREE,
                            model=self.model_id, version=PROVIDER_VERSION)

    def is_available(self) -> bool:
        if self.checkpoint is not None and not (self.checkpoint_path and Path(self.checkpoint_path).is_file()):
            return False
        return _torch_available() and _weights_present(self.model_id, self.model_path)

    def unavailable_reason(self) -> str:
        if self.checkpoint is not None and not (self.checkpoint_path and Path(self.checkpoint_path).is_file()):
            return (f"checkpoint {self.checkpoint.checkpoint_id} 不在 {self.checkpoint_path}；"
                    f"執行 `python -m see.app.cli checkpoint-download {self.checkpoint.checkpoint_id} --yes`")
        if not _torch_available():
            return "torch / diffusers 未安裝（執行 `python -m see.app.cli image-setup` 看步驟）"
        if not _weights_present(self.model_id, self.model_path):
            return f"模型 {self.model_id} 不在本機；執行 `python -m see.app.cli image-download --preset {self.preset} --yes`（不會自動下載）"
        return ""

    def estimate_cost(self, request: ImageRequest) -> CostEstimate:
        return self._estimate(units=1, unit_name="image")

    # ------------------------------------------------------------ torch side
    def _resolve_device(self) -> tuple[str, int | None]:
        import torch  # type: ignore

        if self.device != "auto":
            dev = self.device
        elif torch.cuda.is_available():
            dev = "cuda"
        elif getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            dev = "mps"
        else:
            dev = "cpu"
        vram = int(torch.cuda.get_device_properties(0).total_memory / 2**20) if dev == "cuda" else None
        self.gpu_name = torch.cuda.get_device_name(0) if dev == "cuda" else None
        return dev, vram

    def _load(self, plan: RuntimePlan) -> Any:
        if self._pipe is not None and self._plan == plan:
            return self._pipe
        self._release()
        import torch  # type: ignore
        from diffusers import AutoPipelineForText2Image  # type: ignore

        dtype = getattr(torch, plan.dtype)
        if self.checkpoint is not None:
            return self._load_checkpoint(plan, torch, dtype)
        variant = pick_variant(self.model_path, self.cfg["variant"], plan.dtype)
        self.weights_variant = variant
        supports_dtype = diffusers_supports_dtype_kwarg()
        kwargs = load_kwargs(plan, variant, self.preset, dtype, supports_dtype)
        src = self.model_path or self.model_id
        if plan.vae_fp32 and plan.dtype != "float32":
            # D-022：VAE 直接以 fp32 載入（同一份 fp16 檔 upcast），避免 `.to()` 事後 cast 的 diffusers 警告
            try:
                from diffusers import AutoencoderKL  # type: ignore

                vkw: dict[str, Any] = {("dtype" if supports_dtype else "torch_dtype"): torch.float32, "local_files_only": True,
                                       "subfolder": "vae"}
                if variant:
                    vkw["variant"] = variant
                kwargs["vae"] = AutoencoderKL.from_pretrained(src, **vkw)
            except Exception as e:  # noqa: BLE001
                log.warning("separate fp32 VAE load failed (%s); falling back to .to(float32)", e)
        pipe = AutoPipelineForText2Image.from_pretrained(src, **kwargs)
        return self._finish_load(pipe, plan, torch)

    def _load_checkpoint(self, plan: RuntimePlan, torch: Any, dtype: Any) -> Any:
        """D-039：單檔 safetensors → `from_single_file`，config 取本機 base SD 1.5 資料夾（離線，不另下載）。
        fp16 權重在 dtype=float32 時於載入 upcast（同 D-022）；VAE 以 `.to(float32)` 處理。"""
        from diffusers import StableDiffusionPipeline  # type: ignore

        self.weights_variant = "single-file"
        # from_single_file 長期支援 torch_dtype（新版僅 FutureWarning）；feature_extractor／safety_checker 不使用
        kw: dict[str, Any] = {"torch_dtype": dtype, "local_files_only": True, "config": self.model_path,
                              "safety_checker": None, "feature_extractor": None, "requires_safety_checker": False}
        pipe = StableDiffusionPipeline.from_single_file(self.checkpoint_path, **kw)
        return self._finish_load(pipe, plan, torch)

    def _finish_load(self, pipe: Any, plan: RuntimePlan, torch: Any) -> Any:
        if self.scheduler_name != "default":
            pipe.scheduler = make_scheduler(self.scheduler_name, pipe.scheduler.config)
        if plan.attention_slicing and hasattr(pipe, "enable_attention_slicing"):
            pipe.enable_attention_slicing()
        if plan.vae_slicing and hasattr(pipe, "enable_vae_slicing"):
            pipe.enable_vae_slicing()
            if hasattr(pipe, "enable_vae_tiling"):
                pipe.enable_vae_tiling()
        if plan.vae_fp32 and hasattr(pipe, "vae") and pipe.vae.dtype != torch.float32:
            pipe.vae.to(dtype=torch.float32)
        if plan.cpu_offload and plan.device == "cuda" and hasattr(pipe, "enable_model_cpu_offload"):
            pipe.enable_model_cpu_offload()
        else:
            pipe.to(plan.device)
        pipe.set_progress_bar_config(disable=True)
        self._pipe, self._plan = pipe, plan
        return pipe

    def _release(self) -> None:
        self._pipe = None
        gc.collect()
        try:
            import torch  # type: ignore

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------ generation
    def _run_pipe(self, pipe: Any, plan: RuntimePlan, request: ImageRequest) -> Any:
        """跑一次推理，回傳 numpy float 影像 [0,1]（HxWx3）。

        D-021：不用 pipeline 內建的 decode。SD 1.5 pipeline 把 fp16 latents 直接餵 VAE（diffusers 0.41 無 dtype cast），
        `vae_fp32=True` 時會 dtype 不匹配丟例外。改取 `output_type="latent"`，自行 cast 到 VAE dtype 再 decode；
        latents 本身含 NaN 代表 UNet 階段就壞了，直接視為數值失敗（不用浪費 VAE decode）。
        """
        import torch  # type: ignore

        policy = str(request.params.get("gen_policy", "fit"))
        if policy not in GEN_POLICIES:
            raise ProviderError(f"unknown gen_policy '{policy}'; known: {GEN_POLICIES}")
        if policy == "native":
            gw, gh = gen_size_native(request.width, request.height, plan.max_side, int(self.cfg["multiple"]))
        else:
            gw, gh = gen_size(request.width, request.height, plan.max_side, int(self.cfg["multiple"]))
        clip_skip = self.checkpoint.diffusers_clip_skip if self.checkpoint is not None else None
        self._gen_info = {"gen_policy": policy, "gen_width": gw, "gen_height": gh, "steps": self.steps,
                          "guidance": self.guidance, "scheduler": type(getattr(pipe, "scheduler", None)).__name__,
                          "scheduler_name": self.scheduler_name,
                          # D-043：base 也明確記錄（1＝不跳層），跨次比較才看得出 clip skip 是否一致
                          "clip_skip_a1111": self.checkpoint.clip_skip_a1111 if self.checkpoint is not None else 1,
                          "clip_skip_diffusers": clip_skip,
                          **_prompt_token_info(pipe, request.prompt, request.negative_prompt)}
        gen = torch.Generator(device="cpu").manual_seed(request.seed if request.seed is not None else 0)
        _cuda_peak_mb(torch, reset=True)
        mode = request.params.get("prompt_mode") or {}
        long_prompt, regional = bool(mode.get("long_prompt")), mode.get("regional")
        if long_prompt or regional:
            self._gen_info["prompt_mode"] = "regional" if regional else "long_prompt"  # regional 隱含分段編碼
        restore = None
        with torch.inference_mode():
            if long_prompt or regional:
                # D-051 S1／S2（opt-in）：分段編碼（regional 時一律分段，避免各區截斷）；clip skip 沿用模型 preset（base＝1）
                cs = self.checkpoint.clip_skip_a1111 if self.checkpoint is not None else 1
                if regional:
                    texts = [str(regional["base"])] + [str(t) for t in regional["regions"]]
                    embs, info = encode_text_chunks(pipe, texts + [request.negative_prompt or ""], cs)
                    pe, neg = torch.cat(embs[:-1], dim=1), embs[-1]
                    npe = torch.cat([neg] * len(texts), dim=1)
                    restore = dict(pipe.unet.attn_processors)
                    vsf = int(getattr(pipe, "vae_scale_factor", 8))  # SD 1.5＝8
                    pipe.unet.set_attn_processor(regional_processors(pipe.unet, len(texts) - 1, (gh // vsf, gw // vsf)))
                    info.update({"regions": len(texts) - 1, "layout": "columns", "base_ratio": REGIONAL_BASE_RATIO,
                                 "region_prompts": texts[1:], "base_prompt": texts[0],
                                 "note": "conditioning uses base+region prompts; request.prompt kept only for evidence"})
                else:
                    (pe, npe), info = encode_text_chunks(pipe, [request.prompt, request.negative_prompt or ""], cs)
                self._gen_info["prompt_encoding"] = info
                self._gen_info["prompt_truncated_effective"] = False
                call_kw: dict[str, Any] = {"prompt_embeds": pe, "negative_prompt_embeds": npe}
            elif clip_skip:
                # D-040：自行編碼（A1111 語意、含執行期順序驗證），不用 diffusers `clip_skip=`（transformers 5.x 不相容）
                pe, npe, cs_info = encode_prompt_clip_skip(pipe, request.prompt, request.negative_prompt or "",
                                                           self.checkpoint.clip_skip_a1111)
                self._gen_info["clip_skip_encoding"] = cs_info
                call_kw = {"prompt_embeds": pe, "negative_prompt_embeds": npe}
            else:
                call_kw = {"prompt": request.prompt, "negative_prompt": request.negative_prompt or None}
            identity = request.params.get("identity")
            id_loaded = False
            if identity:
                if regional:
                    raise ProviderError("identity conditioning is not combined with S2 regional prompting (D-054)")
                restore = dict(pipe.unet.attn_processors)
                id_kw, id_info = self._identity_kwargs(pipe, identity, gw, gh, torch)
                id_loaded = True
                call_kw.update(id_kw)
                self._gen_info["identity"] = id_info
            try:
                latents = pipe(width=gw, height=gh, num_inference_steps=self.steps, guidance_scale=self.guidance,
                               generator=gen, output_type="latent", **call_kw).images
            finally:
                if id_loaded:  # IP-Adapter processors 必須卸載，否則後續一般生成會把文字 token 誤當 image token
                    pipe.unload_ip_adapter()
                if restore is not None:  # 快取的 pipe 必須還原，避免影響後續一般生成
                    pipe.unet.set_attn_processor(restore)
            if not torch.isfinite(latents).all():
                return None  # UNet 階段 NaN/Inf
            vae = pipe.vae
            scaling = float(getattr(getattr(vae, "config", None), "scaling_factor", 0.18215))
            z = (latents / scaling).to(dtype=vae.dtype)
            image = vae.decode(z, return_dict=False)[0]
            self._gen_info["vram_peak_mb"] = _cuda_peak_mb(torch)
            return pipe.image_processor.postprocess(image, output_type="np")[0]

    def _identity_embeds(self, refs: list[dict[str, Any]], torch: Any) -> Any:
        """參考圖 → IP-Adapter plus 用的 image embeddings（hidden_states[-2]，同 diffusers encode_image）。
        image encoder 只在 **CPU fp32** 跑（不佔 4 GB VRAM）；結果依 (encoder sha, 各參考圖 sha) 快取。"""
        key = (self.identity_adapter.encoder_file.sha256 or "",) + tuple(r["sha256"] for r in refs)
        if key in self._id_cache:
            return self._id_cache[key], True
        from PIL import Image
        from transformers import CLIPImageProcessor, CLIPVisionModelWithProjection  # type: ignore

        if self._id_encoder is None:
            enc_dir = Path(self.identity_dir) / Path(self.identity_adapter.encoder_file.path).parent
            self._id_encoder = CLIPVisionModelWithProjection.from_pretrained(str(enc_dir), local_files_only=True,
                                                                             torch_dtype=torch.float32).eval()
        size = int(self._id_encoder.config.image_size)
        fx = CLIPImageProcessor(size=size, crop_size=size)  # transformers 5.x 無 torchvision → 自動 PIL 版
        imgs = [Image.open(r["path"]).convert("RGB") for r in refs]
        px = fx(images=imgs, return_tensors="pt").pixel_values.to(dtype=torch.float32)
        with torch.inference_mode():
            pos = self._id_encoder(px, output_hidden_states=True).hidden_states[-2]
            neg = self._id_encoder(torch.zeros_like(px), output_hidden_states=True).hidden_states[-2]
        emb = torch.cat([neg[None], pos[None]], dim=0)  # (2, n_refs, tokens, dim)：CFG 的 negative 在前
        self._id_cache[key] = emb
        return emb, False

    def _identity_kwargs(self, pipe: Any, identity: dict[str, Any], gw: int, gh: int, torch: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        """S4（D-054）：載入 IP-Adapter（不註冊 image encoder → 不上 GPU）、每角色一張參考圖＋一張分欄 mask。"""
        spec = self.identity_adapter
        if spec is None or self.identity_dir is None or identity.get("adapter_id") != spec.adapter_id:
            raise ProviderError(f"identity adapter not configured for {identity.get('adapter_id')}")
        refs = list(identity.get("references") or [])
        if len(refs) < 1:
            raise ProviderError("identity conditioning needs at least one reference image")
        regions = [r.get("region") for r in refs]
        if all(regions) and [REGION_RANK[g] for g in regions] != sorted(REGION_RANK[g] for g in regions):
            raise ProviderError(f"identity references must be ordered left→right to match column masks, got {regions}")
        from diffusers.image_processor import IPAdapterMaskProcessor  # type: ignore

        emb, cache_hit = self._identity_embeds(refs, torch)
        # diffusers 0.41 `load_ip_adapter` 以「無參數」重建現有 attn1 processor 類別 → 開了 attention slicing
        # （SlicedAttnProcessor 需 slice_size）會 TypeError（tiny 整合測試實測，D-054）。先換成 SDPA processor
        # （AttnProcessor2_0；CUDA 上走 memory-efficient kernel，不展開完整注意力矩陣），呼叫端 finally 會還原原 processor。
        from diffusers.models.attention_processor import AttnProcessor2_0  # type: ignore

        pipe.unet.set_attn_processor(AttnProcessor2_0())
        w = Path(spec.weight_file.path)
        pipe.load_ip_adapter(str(self.identity_dir), subfolder=str(w.parent), weight_name=w.name,
                             image_encoder_folder=None, local_files_only=True)
        scale = float(identity.get("scale", IDENTITY_SCALE))
        pipe.set_ip_adapter_scale([[scale] * len(refs)])
        bounds = column_bounds(len(refs), gw)
        masks = IPAdapterMaskProcessor().preprocess(identity_column_masks(len(refs), gw, gh), height=gh, width=gw)
        masks = masks.reshape(1, masks.shape[0], masks.shape[2], masks.shape[3])
        # D-056 執行期自檢：第 i 張 mask 的非零欄位必須恰為 bounds[i]（防轉置／翻轉／broadcast）
        for i, (a, b) in enumerate(bounds):
            cols = (masks[0, i].amax(dim=0) > 0.5).nonzero().flatten()
            if cols.numel() == 0 or int(cols[0]) != a or int(cols[-1]) != b - 1 or masks.shape[2:] != (gh, gw):
                raise ProviderError(f"identity mask {i} geometry check failed (expected columns {a}..{b - 1})")
        dtype = next(pipe.unet.parameters()).dtype
        kw = {"ip_adapter_image_embeds": [emb.to(dtype=dtype)], "cross_attention_kwargs": {"ip_adapter_masks": [masks]}}
        info = {"adapter_id": spec.adapter_id, "adapter_sha256": spec.weight_file.sha256,
                "image_encoder_sha256": spec.encoder_file.sha256, "image_encoder_device": "cpu", "scale": scale,
                "mask": {"layout": "columns", "order": [r.get("character_id") for r in refs],
                         "binding": "refs[i] ↔ ip_adapter_image_embeds[0][:, i] ↔ ip_adapter_masks[0][:, i] (adapter 0)"},
                "references": [{**{k: r.get(k) for k in ("character_id", "sha256", "bytes", "source", "source_evidence",
                                                     "library_category", "position")},
                                "assigned_region": r.get("region") or (("left", "right")[i] if len(refs) == 2 else None),
                                "adapter_index": 0, "image_index": i, "mask_bounds_gen_px": [a, 0, b, gh]}
                               for i, (r, (a, b)) in enumerate(zip(refs, bounds))],
                "face_crop": "CLIP center crop (no face detector)", "embeds_cache_hit": cache_hit,
                "combined_with_regional": False, "attn1_processor_during_identity": "AttnProcessor2_0 (SDPA)"}
        return kw, info

    def generate_image(self, request: ImageRequest, out_path: Path) -> ImageResult:
        if not self.is_available():
            raise ProviderUnavailable(self.unavailable_reason())
        self.calls += 1
        import numpy as np
        from PIL import Image

        t0 = time.monotonic()
        dev, vram = self._resolve_device()
        plan = make_runtime_plan(dev, vram, int(self.cfg["max_side"]), getattr(self, "gpu_name", None))
        plan_origin = "fresh"
        if self._floor is not None and self._floor.device == plan.device:
            plan, plan_origin = self._floor, "carried from previous scene (numeric failure already proven)"
        initial = plan
        self.attempts: list[str] = []
        self._gen_info: dict[str, Any] = {}
        img = None
        for _attempt in range(4):  # OOM 最多降一次、數值問題最多降兩次
            try:
                pipe = self._load(plan)
                log.info("diffusers %s attempt %d: %s", self.preset, len(self.attempts) + 1, plan)
                arr = self._run_pipe(pipe, plan, request)
                if arr is None or is_numeric_failure(arr):
                    nxt = plan.downgrade_numeric()
                    self.attempts.append(f"numeric failure (NaN/black) with dtype={plan.dtype} vae_fp32={plan.vae_fp32}")
                    log.warning("diffusers %s: %s -> %s", self.preset, self.attempts[-1], "escalate" if nxt else "give up")
                    if nxt is None:
                        raise ProviderError("generation produced NaN/black image even in fp32: " + "; ".join(self.attempts))
                    plan = nxt
                    continue
                img = Image.fromarray((np.clip(arr, 0, 1) * 255).round().astype("uint8"))
                if self._gen_info.get("gen_policy") == "native":
                    box = center_crop_to_aspect(img.width, img.height, request.width, request.height)
                    img = img.crop(box)
                    self._gen_info["crop_box"] = list(box)
                self.last_plan = plan
                break
            except ProviderError:
                raise
            except Exception as e:  # noqa: BLE001
                is_oom = "out of memory" in str(e).lower() or type(e).__name__ == "OutOfMemoryError"
                if is_oom and "oom" not in self.attempts:
                    self.attempts.append("oom")
                    log.warning("diffusers %s: OOM at %s -> downgrade memory", self.preset, plan)
                    plan = plan.downgrade_memory()
                    self._release()
                    continue
                raise ProviderError(f"diffusers generation failed ({type(e).__name__}): {e}") from e
        if img is None:
            raise ProviderError("diffusers generation exhausted retries: " + "; ".join(self.attempts))
        self._gen_info["upscale_factor"] = round(request.width / img.width, 3)
        if img.size != (request.width, request.height):
            img = img.resize((request.width, request.height), Image.LANCZOS)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(out_path, format="PNG")
        # D-021：存檔後重開驗證；黑圖不得留在磁碟上被後續流程（manifest / clip）當成功
        defect = image_defect(out_path)
        if defect is not None:
            out_path.unlink(missing_ok=True)
            raise ProviderError(f"diffusers saved image rejected: {defect}; attempts=" + "; ".join(self.attempts))
        if any(a.startswith("numeric") for a in self.attempts):
            self._floor = plan
        meta = self.evidence(initial, plan, out_path, time.monotonic() - t0)
        meta["plan_origin"] = plan_origin
        self.last_evidence = meta
        log.info("diffusers %s done: %s", self.preset, meta)
        return ImageResult(path=str(out_path), width=request.width, height=request.height,
                           provider=self.info.name, model=self.info.model, meta=meta)

    def evidence(self, initial: RuntimePlan, final: RuntimePlan, out_path: Path, elapsed_s: float) -> dict[str, Any]:
        """可追蹤的最終狀態（寫入 manifest / CLI / UI）。"""
        return {
            "generated_by": self.info.name, "model": self.model_id, "gpu": getattr(self, "gpu_name", None),
            "initial_plan": asdict(initial), "final_plan": asdict(final),
            "final_dtype": final.dtype, "final_vae_fp32": final.vae_fp32, "final_max_side": final.max_side,
            "attempts": list(self.attempts), "numeric_downgrade": any(a.startswith("numeric") for a in self.attempts),
            "oom_downgrade": "oom" in self.attempts, "elapsed_s": round(elapsed_s, 2),
            "weights_variant": self.weights_variant,
            "fp32_source": self.cfg.get("fp32_escalation", "n/a") if final.dtype == "float32" or final.vae_fp32 else None,
            "image_stats": image_stats(out_path).to_dict(),
            **getattr(self, "_gen_info", {}),
            **({"checkpoint": {k: getattr(self.checkpoint, k) for k in ("checkpoint_id", "display_name", "version", "sha256",
                                                                         "official_source", "license_status", "commercial_cleared",
                                                                         "usage", "attribution")},
                "checkpoint_path": self.checkpoint_path} if self.checkpoint is not None else {}),
        }
