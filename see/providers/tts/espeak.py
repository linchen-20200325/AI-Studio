"""EspeakTTSProvider：espeak-ng 本機中文 TTS。LOCAL_FREE，品質低但可離線。"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from see.core.errors import ProviderError, ProviderUnavailable
from see.core.ffmpeg import FFmpeg
from see.models.cost import CostEstimate
from see.models.enums import CostTier, ProviderKind
from see.models.provider import ProviderInfo
from see.providers.base import TTSProvider, TTSRequest, TTSResult

_LANG_TO_VOICE = {"zh-TW": "cmn", "zh": "cmn", "zh-CN": "cmn", "en": "en", "en-US": "en-us", "ja": "ja"}


class EspeakTTSProvider(TTSProvider):
    def __init__(self, binary: str = "espeak-ng", base_wpm: int = 200, ffmpeg: FFmpeg | None = None) -> None:
        self.binary = binary
        self.base_wpm = base_wpm
        self.ffmpeg = ffmpeg or FFmpeg()
        self.calls = 0

    @property
    def info(self) -> ProviderInfo:
        return ProviderInfo(name="espeak-tts", kind=ProviderKind.TTS, cost_tier=CostTier.LOCAL_FREE,
                            model=f"espeak-ng/{self.base_wpm}wpm", version="1")

    def is_available(self) -> bool:
        return shutil.which(self.binary) is not None

    def estimate_cost(self, request: TTSRequest) -> CostEstimate:
        return self._estimate(units=len(request.text), unit_name="chars")

    def synthesize(self, request: TTSRequest, out_path: Path) -> TTSResult:
        if not self.is_available():
            raise ProviderUnavailable(f"{self.binary} not found")
        self.calls += 1
        voice = request.voice if request.voice not in ("", "default") else _LANG_TO_VOICE.get(request.language, "cmn")
        wpm = max(80, min(400, int(self.base_wpm * request.speed)))
        out_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = [self.binary, "-v", voice, "-s", str(wpm), "-w", str(out_path), "--", request.text]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        except (subprocess.SubprocessError, OSError) as e:
            raise ProviderError(f"espeak-ng failed: {e}") from e
        if proc.returncode != 0 or not out_path.exists() or out_path.stat().st_size < 100:
            raise ProviderError(f"espeak-ng returned {proc.returncode}: {proc.stderr[-500:]}")
        info = self.ffmpeg.probe(out_path)
        return TTSResult(path=str(out_path), duration=info.duration, provider=self.info.name,
                         model=self.info.model, sample_rate=info.sample_rate)
