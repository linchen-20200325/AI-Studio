"""DiffusersImageProvider：本機 open-weight 模型生圖（LOCAL_FREE）。骨架 — 不會自動下載任何權重。

- 模型由 `model_id` 指定（FLUX.1-schnell / SD 1.5 / 未來 Qwen-Image、Z-Image 等皆可），核心 pipeline 不知道是哪個模型。
- `local_files_only=True`：權重必須已在本機 HF cache 或 `model_path`；缺權重 → ProviderUnavailable，絕不觸發下載。
- 下載權重是人工步驟（見 docs/AI_IMAGE_PROVIDER_PLAN.md），符合「需要下載大型模型 → 停止並詢問」。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

from see.core.errors import ProviderError, ProviderUnavailable
from see.models.cost import CostEstimate
from see.models.enums import CostTier, ProviderKind
from see.models.provider import ProviderInfo
from see.providers.base import ImageProvider, ImageRequest, ImageResult

MODEL_PRESETS: dict[str, dict[str, Any]] = {
    # key → diffusers 載入參數；steps/guidance 為該模型建議值
    "flux-schnell": {"model_id": "black-forest-labs/FLUX.1-schnell", "steps": 4, "guidance": 0.0, "max_side": 1024},
    "sd15": {"model_id": "stable-diffusion-v1-5/stable-diffusion-v1-5", "steps": 25, "guidance": 7.0, "max_side": 512},
}


def _torch_available() -> bool:
    return importlib.util.find_spec("torch") is not None and importlib.util.find_spec("diffusers") is not None


def _weights_present(model_id: str, model_path: str | None) -> bool:
    if model_path:
        return Path(model_path).exists()
    if importlib.util.find_spec("huggingface_hub") is None:
        return False
    try:
        from huggingface_hub import scan_cache_dir  # type: ignore

        return any(r.repo_id == model_id for r in scan_cache_dir().repos)
    except Exception:  # noqa: BLE001
        return False


class DiffusersImageProvider(ImageProvider):
    def __init__(self, preset: str = "flux-schnell", model_path: str | None = None, device: str = "auto",
                 steps: int | None = None, guidance: float | None = None) -> None:
        if preset not in MODEL_PRESETS:
            raise ValueError(f"unknown preset '{preset}'; known: {sorted(MODEL_PRESETS)}")
        cfg = MODEL_PRESETS[preset]
        self.preset = preset
        self.model_id: str = cfg["model_id"]
        self.model_path = model_path
        self.device = device
        self.steps = steps or cfg["steps"]
        self.guidance = cfg["guidance"] if guidance is None else guidance
        self.max_side: int = cfg["max_side"]
        self._pipe: Any = None
        self.calls = 0

    @property
    def info(self) -> ProviderInfo:
        return ProviderInfo(name=f"diffusers-{self.preset}", kind=ProviderKind.IMAGE, cost_tier=CostTier.LOCAL_FREE,
                            model=self.model_id, version="1")

    def is_available(self) -> bool:
        return _torch_available() and _weights_present(self.model_id, self.model_path)

    def unavailable_reason(self) -> str:
        if not _torch_available():
            return "torch / diffusers 未安裝（見 docs/AI_IMAGE_PROVIDER_PLAN.md 安裝步驟）"
        if not _weights_present(self.model_id, self.model_path):
            return f"模型權重 {self.model_id} 不在本機；下載需人工執行（不自動下載）"
        return ""

    def estimate_cost(self, request: ImageRequest) -> CostEstimate:
        return self._estimate(units=1, unit_name="image")

    def _load(self) -> Any:
        if self._pipe is not None:
            return self._pipe
        import torch  # type: ignore
        from diffusers import AutoPipelineForText2Image  # type: ignore

        device = self.device
        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "mps" if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available() else "cpu"
        dtype = torch.bfloat16 if device == "cuda" else torch.float32
        src = self.model_path or self.model_id
        pipe = AutoPipelineForText2Image.from_pretrained(src, torch_dtype=dtype, local_files_only=True)
        if device == "cuda" and hasattr(pipe, "enable_model_cpu_offload"):
            pipe.enable_model_cpu_offload()  # 低 VRAM 友善；足夠 VRAM 時 diffusers 仍會用 GPU 運算
        else:
            pipe.to(device)
        self._pipe = pipe
        return pipe

    def generate_image(self, request: ImageRequest, out_path: Path) -> ImageResult:
        if not self.is_available():
            raise ProviderUnavailable(self.unavailable_reason())
        self.calls += 1
        import torch  # type: ignore

        pipe = self._load()
        # 生成解析度：長邊 ≤ max_side，且為 16 的倍數；之後縮放到請求尺寸
        scale = min(self.max_side / max(request.width, request.height), 1.0)
        gw = max(int(request.width * scale) // 16 * 16, 256)
        gh = max(int(request.height * scale) // 16 * 16, 256)
        gen = torch.Generator(device="cpu").manual_seed(request.seed if request.seed is not None else 0)
        try:
            img = pipe(prompt=request.prompt, negative_prompt=request.negative_prompt or None, width=gw, height=gh,
                       num_inference_steps=self.steps, guidance_scale=self.guidance, generator=gen).images[0]
        except Exception as e:  # noqa: BLE001
            raise ProviderError(f"diffusers generation failed: {type(e).__name__}: {e}") from e
        if (gw, gh) != (request.width, request.height):
            from PIL import Image

            img = img.resize((request.width, request.height), Image.LANCZOS)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(out_path, format="PNG")
        return ImageResult(path=str(out_path), width=request.width, height=request.height,
                           provider=self.info.name, model=self.info.model)
