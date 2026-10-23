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


def download_plan(preset: str) -> dict[str, Any]:
    cfg = MODEL_PRESETS[preset]
    return {"preset": preset, "model_id": cfg["model_id"], "estimated_gb": cfg["download_gb"],
            "allow_patterns": cfg["allow_patterns"], "variant": cfg["variant"]}


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


class DiffusersImageProvider(ImageProvider):
    def __init__(self, preset: str = "sd15", model_path: str | None = None, device: str = "auto",
                 steps: int | None = None, guidance: float | None = None) -> None:
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

    @property
    def info(self) -> ProviderInfo:
        return ProviderInfo(name=f"diffusers-{self.preset}", kind=ProviderKind.IMAGE, cost_tier=CostTier.LOCAL_FREE,
                            model=self.model_id, version=PROVIDER_VERSION)

    def is_available(self) -> bool:
        return _torch_available() and _weights_present(self.model_id, self.model_path)

    def unavailable_reason(self) -> str:
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
        kwargs: dict[str, Any] = {"torch_dtype": dtype, "local_files_only": True}
        if self.cfg["variant"] and plan.dtype == "float16":
            kwargs["variant"] = self.cfg["variant"]
        if self.preset == "sd15":
            kwargs["safety_checker"] = None  # 未下載 safety_checker；省 VRAM
            kwargs["feature_extractor"] = None  # 只有 safety_checker 需要；避免 torchvision warning
        pipe = AutoPipelineForText2Image.from_pretrained(self.model_path or self.model_id, **kwargs)
        if plan.attention_slicing and hasattr(pipe, "enable_attention_slicing"):
            pipe.enable_attention_slicing()
        if plan.vae_slicing and hasattr(pipe, "enable_vae_slicing"):
            pipe.enable_vae_slicing()
            if hasattr(pipe, "enable_vae_tiling"):
                pipe.enable_vae_tiling()
        if plan.vae_fp32 and hasattr(pipe, "vae"):
            pipe.vae.to(dtype=torch.float32)
            if hasattr(pipe.vae, "config"):
                try:
                    pipe.vae.config.force_upcast = True
                except Exception:  # noqa: BLE001
                    pass
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

        gw, gh = gen_size(request.width, request.height, plan.max_side, int(self.cfg["multiple"]))
        gen = torch.Generator(device="cpu").manual_seed(request.seed if request.seed is not None else 0)
        with torch.inference_mode():
            latents = pipe(prompt=request.prompt, negative_prompt=request.negative_prompt or None, width=gw, height=gh,
                           num_inference_steps=self.steps, guidance_scale=self.guidance, generator=gen,
                           output_type="latent").images
            if not torch.isfinite(latents).all():
                return None  # UNet 階段 NaN/Inf
            vae = pipe.vae
            scaling = float(getattr(getattr(vae, "config", None), "scaling_factor", 0.18215))
            z = (latents / scaling).to(dtype=vae.dtype)
            image = vae.decode(z, return_dict=False)[0]
            return pipe.image_processor.postprocess(image, output_type="np")[0]

    def generate_image(self, request: ImageRequest, out_path: Path) -> ImageResult:
        if not self.is_available():
            raise ProviderUnavailable(self.unavailable_reason())
        self.calls += 1
        import numpy as np
        from PIL import Image

        t0 = time.monotonic()
        dev, vram = self._resolve_device()
        plan = make_runtime_plan(dev, vram, int(self.cfg["max_side"]), getattr(self, "gpu_name", None))
        initial = plan
        self.attempts: list[str] = []
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
        if img.size != (request.width, request.height):
            img = img.resize((request.width, request.height), Image.LANCZOS)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(out_path, format="PNG")
        # D-021：存檔後重開驗證；黑圖不得留在磁碟上被後續流程（manifest / clip）當成功
        defect = image_defect(out_path)
        if defect is not None:
            out_path.unlink(missing_ok=True)
            raise ProviderError(f"diffusers saved image rejected: {defect}; attempts=" + "; ".join(self.attempts))
        meta = self.evidence(initial, plan, out_path, time.monotonic() - t0)
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
            "image_stats": image_stats(out_path).to_dict(),
        }
