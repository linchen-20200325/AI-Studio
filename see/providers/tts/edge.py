"""EdgeTTSProvider：微軟 Edge 線上 TTS（FREE_TIER，不需 key，需要網路）。

Optional：需 `pip install edge-tts`。預設不啟用（SEE_TTS_PROVIDER=edge 才用）。
非官方服務，可用性不保證；任何失敗都 raise，不會自動切到 PAID。
"""

from __future__ import annotations

import asyncio
import importlib
import importlib.util
from pathlib import Path

from see.core.errors import ProviderError, ProviderUnavailable
from see.core.ffmpeg import FFmpeg
from see.models.cost import CostEstimate
from see.models.enums import CostTier, ProviderKind
from see.models.provider import ProviderInfo
from see.providers.base import TTSProvider, TTSRequest, TTSResult

_DEFAULT_VOICES = {"zh-TW": "zh-TW-HsiaoChenNeural", "zh-CN": "zh-CN-XiaoxiaoNeural", "en-US": "en-US-AriaNeural"}


class EdgeTTSProvider(TTSProvider):
    def __init__(self, ffmpeg: FFmpeg | None = None) -> None:
        self.ffmpeg = ffmpeg or FFmpeg()
        self.calls = 0

    @property
    def info(self) -> ProviderInfo:
        return ProviderInfo(name="edge-tts", kind=ProviderKind.TTS, cost_tier=CostTier.FREE_TIER,
                            model="edge-neural", version="1", requires_network=True)

    def is_available(self) -> bool:
        return importlib.util.find_spec("edge_tts") is not None

    def estimate_cost(self, request: TTSRequest) -> CostEstimate:
        return self._estimate(units=len(request.text), unit_name="chars")

    def synthesize(self, request: TTSRequest, out_path: Path) -> TTSResult:
        if not self.is_available():
            raise ProviderUnavailable("edge-tts package not installed")
        edge_tts = importlib.import_module("edge_tts")
        self.calls += 1
        voice = request.voice if request.voice not in ("", "default") else _DEFAULT_VOICES.get(request.language, "zh-TW-HsiaoChenNeural")
        rate = f"{int((request.speed - 1) * 100):+d}%"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        mp3 = out_path.with_suffix(".mp3")

        async def _run() -> None:
            await edge_tts.Communicate(request.text, voice=voice, rate=rate).save(str(mp3))

        try:
            asyncio.run(_run())
        except Exception as e:  # 網路 / 服務錯誤一律包成 ProviderError，不自動 fallback
            raise ProviderError(f"edge-tts failed: {e}") from e
        self.ffmpeg.run(["-i", str(mp3), "-ar", "44100", "-ac", "1", str(out_path)])
        mp3.unlink(missing_ok=True)
        info = self.ffmpeg.probe(out_path)
        return TTSResult(path=str(out_path), duration=info.duration, provider=self.info.name,
                         model=self.info.model, sample_rate=info.sample_rate)
