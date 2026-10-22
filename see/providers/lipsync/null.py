"""NullLipSyncProvider：不做 lip sync。介面預留。"""

from __future__ import annotations

from pathlib import Path

from see.models.cost import CostEstimate
from see.models.enums import CostTier, ProviderKind
from see.models.provider import ProviderInfo
from see.providers.base import LipSyncProvider, LipSyncRequest, LipSyncResult


class NullLipSyncProvider(LipSyncProvider):
    @property
    def info(self) -> ProviderInfo:
        return ProviderInfo(name="null-lipsync", kind=ProviderKind.LIPSYNC, cost_tier=CostTier.LOCAL_FREE, model="none")

    def estimate_cost(self, request: LipSyncRequest) -> CostEstimate:
        return self._estimate(units=0, unit_name="seconds")

    def lipsync(self, request: LipSyncRequest, out_path: Path) -> LipSyncResult:
        return LipSyncResult(path=None, provider=self.info.name, model=self.info.model, applied=False)
