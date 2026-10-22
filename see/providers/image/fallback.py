"""FallbackImageProvider：依序嘗試 LOCAL_FREE / FREE_TIER 候選；遇 PAID 候選即停（需人工核准）。"""

from __future__ import annotations

from pathlib import Path

from see.core.errors import ProviderError, ProviderUnavailable
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
                self._active = c
                return res
            except ProviderError as e:
                errors.append(f"{c.info.name}: {e}")
        raise ProviderError("all free image candidates failed: " + "; ".join(errors))
