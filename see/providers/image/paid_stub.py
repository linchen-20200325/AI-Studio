"""PaidImageProviderStub：未來付費 Image API 的占位（PAID）。永不連線、永不消費。

存在目的：證明 ApprovalGate 的接線；真正實作另開 Decision Gate。
"""

from __future__ import annotations

from pathlib import Path

from see.core.errors import ProviderUnavailable
from see.models.cost import CostEstimate
from see.models.enums import CostTier, ProviderKind
from see.models.provider import ProviderInfo
from see.providers.base import ImageProvider, ImageRequest, ImageResult


class PaidImageProviderStub(ImageProvider):
    def __init__(self, name: str = "paid-image-stub", model: str = "unconfigured", usd_per_image: float = 0.04) -> None:
        self._name, self._model, self.usd_per_image = name, model, usd_per_image

    @property
    def info(self) -> ProviderInfo:
        return ProviderInfo(name=self._name, kind=ProviderKind.IMAGE, cost_tier=CostTier.PAID, model=self._model,
                            requires_network=True, requires_api_key=True)

    def is_available(self) -> bool:
        return False  # 未設定 key；且即使設定也必須先過 ApprovalGate

    def estimate_cost(self, request: ImageRequest) -> CostEstimate:
        return self._estimate(units=1, unit_name="image", cost=self.usd_per_image, currency="USD")

    def generate_image(self, request: ImageRequest, out_path: Path) -> ImageResult:
        raise ProviderUnavailable("paid image provider is a stub: no network call is implemented by design")
