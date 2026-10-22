"""SilentTTSProvider：靜音 + 以字數估算時長。LOCAL_FREE。

用途：測試、無 TTS 工具的環境。保證 pipeline 永遠可離線跑完。
"""

from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

from see.models.cost import CostEstimate
from see.models.enums import CostTier, ProviderKind
from see.models.provider import ProviderInfo
from see.providers.base import TTSProvider, TTSRequest, TTSResult

CHARS_PER_SECOND = 3.5


class SilentTTSProvider(TTSProvider):
    def __init__(self, sample_rate: int = 22050) -> None:
        self.sample_rate = sample_rate
        self.calls = 0

    @property
    def info(self) -> ProviderInfo:
        return ProviderInfo(name="silent-tts", kind=ProviderKind.TTS, cost_tier=CostTier.LOCAL_FREE,
                            model="silence", version="1")

    def estimate_cost(self, request: TTSRequest) -> CostEstimate:
        return self._estimate(units=len(request.text), unit_name="chars")

    def synthesize(self, request: TTSRequest, out_path: Path) -> TTSResult:
        self.calls += 1
        duration = max(len(request.text) / (CHARS_PER_SECOND * request.speed), 0.5)
        n = int(math.ceil(duration * self.sample_rate))
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(out_path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(self.sample_rate)
            w.writeframes(struct.pack("<h", 0) * n)
        return TTSResult(path=str(out_path), duration=n / self.sample_rate, provider=self.info.name,
                         model=self.info.model, sample_rate=self.sample_rate)
