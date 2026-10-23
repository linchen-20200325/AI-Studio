"""NullAudioProvider：不產生 BGM/SFX。LOCAL_FREE。介面預留給未來免費素材庫或程序化生成。"""

from __future__ import annotations

from pathlib import Path

from see.models.cost import CostEstimate
from see.models.enums import CostTier, ProviderKind
from see.models.provider import ProviderInfo
from see.providers.base import AudioProvider, AudioRequest, AudioResult


class NullAudioProvider(AudioProvider):
    generates_audio = False

    @property
    def info(self) -> ProviderInfo:
        return ProviderInfo(name="null-audio", kind=ProviderKind.AUDIO, cost_tier=CostTier.LOCAL_FREE, model="none")

    def estimate_cost(self, request: AudioRequest) -> CostEstimate:
        return self._estimate(units=0, unit_name="seconds")

    def generate_audio(self, request: AudioRequest, out_path: Path) -> AudioResult:
        return AudioResult(path=None, duration=0.0, provider=self.info.name, model=self.info.model)
