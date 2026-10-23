"""FallbackImageProvider：依序嘗試 LOCAL_FREE / FREE_TIER 候選；遇 PAID 候選即停（需人工核准）。

注意（D-021）：`info` 只代表「第一個可用候選」，不是「這次真的生成的 provider」。真正的生成者寫在
`ImageResult.meta["generated_by"]`、`meta["fallback_from"]`；`last_generated_by` 也保留最近一次結果。
"""

from __future__ import annotations

import logging
from pathlib import Path

from see.core.errors import ProviderError, ProviderUnavailable
from see.core.image_qa import image_defect
from see.models.cost import CostEstimate
from see.models.enums import CostTier
from see.models.provider import ProviderInfo
from see.providers.base import ImageProvider, ImageRequest, ImageResult


class FallbackImageProvider(ImageProvider):
    def __init__(self, candidates: list[ImageProvider]) -> None:
        if not candidates:
            raise ValueError("need at least one candidate")
        self.candidates = candidates
        self._active: ImageProvider | None = None
        self.skipped: list[str] = []
        self.last_generated_by: str | None = None
        self.last_fallback_from: list[str] = []

    @property
    def active(self) -> ImageProvider:
        if self._active is None:
            for c in self.candidates:
                if c.info.cost_tier == CostTier.PAID:
                    break
                if c.is_available():
                    self._active = c
                    break
                reason = getattr(c, "unavailable_reason", lambda: "unavailable")()
                self.skipped.append(f"{c.info.name}: {reason}")
            if self._active is None:
                raise ProviderUnavailable("no free image provider available: " + "; ".join(self.skipped))
        return self._active

    @property
    def info(self) -> ProviderInfo:
        return self.active.info

    def is_available(self) -> bool:
        try:
            return self.active.is_available()
        except ProviderUnavailable:
            return False

    def estimate_cost(self, request: ImageRequest) -> CostEstimate:
        return self.active.estimate_cost(request)

    def generate_image(self, request: ImageRequest, out_path: Path) -> ImageResult:
        errors: list[str] = []
        for c in self.candidates:
            if c.info.cost_tier == CostTier.PAID:
                errors.append(f"{c.info.name}: PAID candidate skipped (needs human approval)")
                break
            if not c.is_available():
                reason = getattr(c, "unavailable_reason", lambda: "unavailable")()
                if f"{c.info.name}: {reason}" not in self.skipped:
                    self.skipped.append(f"{c.info.name}: {reason}")
                continue
            try:
                res = c.generate_image(request, out_path)
                defect = image_defect(Path(res.path))
                if defect is not None:  # 候選回報成功但產物不可用（黑圖／無法解碼）→ 視同失敗，換下一個
                    Path(res.path).unlink(missing_ok=True)
                    raise ProviderError(f"output rejected: {defect}")
                # 注意：不把 _active 改成 c——info / fingerprint_key 必須穩定指向「首選可用候選」，
                # 否則一景 fallback 後其餘景的 fingerprint 會漂移（D-023）。實際生成者看 meta / last_generated_by。
                self.last_generated_by = res.provider
                self.last_fallback_from = list(errors)
                res.meta = {**res.meta, "generated_by": res.provider, "fallback_from": list(errors),
                            "fallback": bool(errors), "skipped": list(self.skipped)}
                if errors:
                    logging.getLogger("see.image.fallback").warning("image fallback → %s after: %s", res.provider, "; ".join(errors))
                return res
            except ProviderError as e:
                errors.append(f"{c.info.name}: {e}")
        raise ProviderError("all free image candidates failed: " + "; ".join(errors))
