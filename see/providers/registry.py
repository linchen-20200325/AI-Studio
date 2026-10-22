"""ProviderRegistry：由設定字串建立 Provider。核心流程只透過 registry 拿介面。

新增 Provider：在對應 dict 註冊 factory 即可，不需改 pipeline。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from see.core.config import Settings
from see.core.errors import ProviderUnavailable
from see.core.ffmpeg import FFmpeg
from see.providers.audio.null import NullAudioProvider
from see.providers.base import (
    AudioProvider,
    ImageProvider,
    LipSyncProvider,
    LLMProvider,
    TTSProvider,
    VideoProvider,
)
from see.providers.image.diffusers_local import DiffusersImageProvider
from see.providers.image.fallback import FallbackImageProvider
from see.providers.image.paid_stub import PaidImageProviderStub
from see.providers.image.placeholder import PlaceholderImageProvider
from see.providers.lipsync.null import NullLipSyncProvider
from see.providers.llm.mock import MockLLMProvider
from see.providers.tts.edge import EdgeTTSProvider
from see.providers.tts.espeak import EspeakTTSProvider
from see.providers.tts.fallback import FallbackTTSProvider
from see.providers.tts.silent import SilentTTSProvider
from see.providers.video.kenburns import KenBurnsVideoProvider


@dataclass
class Providers:
    llm: LLMProvider
    image: ImageProvider
    video: VideoProvider
    tts: TTSProvider
    audio: AudioProvider
    lipsync: LipSyncProvider


class ProviderRegistry:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.ffmpeg = FFmpeg(settings.ffmpeg, settings.ffprobe)
        self._llm: dict[str, Callable[[], LLMProvider]] = {
            "mock": lambda: MockLLMProvider(settings.min_scene_duration, settings.max_scene_duration,
                                            settings.target_total_min, settings.target_total_max),
        }
        def _diffusers() -> DiffusersImageProvider:
            path = settings.image_model_path or str(settings.models_dir / settings.image_model_preset)
            return DiffusersImageProvider(preset=settings.image_model_preset, model_path=path)

        self._image: dict[str, Callable[[], ImageProvider]] = {
            "placeholder": PlaceholderImageProvider,
            "diffusers": _diffusers,
            "paid-stub": PaidImageProviderStub,
            # auto：本機 diffusers 有權重就用，否則 placeholder；永不自動跨到 PAID
            "auto": lambda: FallbackImageProvider([_diffusers(), PlaceholderImageProvider()]),
        }
        self._video: dict[str, Callable[[], VideoProvider]] = {
            "kenburns": lambda: KenBurnsVideoProvider(self.ffmpeg),
        }
        self._tts: dict[str, Callable[[], TTSProvider]] = {
            "espeak": lambda: EspeakTTSProvider(ffmpeg=self.ffmpeg),
            "silent": SilentTTSProvider,
            "edge": lambda: EdgeTTSProvider(ffmpeg=self.ffmpeg),
            "auto": lambda: FallbackTTSProvider([EspeakTTSProvider(ffmpeg=self.ffmpeg), SilentTTSProvider()]),
        }
        self._audio: dict[str, Callable[[], AudioProvider]] = {"null": NullAudioProvider}
        self._lipsync: dict[str, Callable[[], LipSyncProvider]] = {"null": NullLipSyncProvider}

    @staticmethod
    def _pick(table: dict[str, Callable[[], object]], key: str, kind: str) -> object:
        if key not in table:
            raise ProviderUnavailable(f"unknown {kind} provider '{key}'; known: {sorted(table)}")
        return table[key]()

    def build(self) -> Providers:
        s = self.settings
        return Providers(
            llm=self._pick(self._llm, s.llm_provider, "llm"),  # type: ignore[arg-type]
            image=self._pick(self._image, s.image_provider, "image"),  # type: ignore[arg-type]
            video=self._pick(self._video, s.video_provider, "video"),  # type: ignore[arg-type]
            tts=self._pick(self._tts, s.tts_provider, "tts"),  # type: ignore[arg-type]
            audio=self._pick(self._audio, s.audio_provider, "audio"),  # type: ignore[arg-type]
            lipsync=self._pick(self._lipsync, s.lipsync_provider, "lipsync"),  # type: ignore[arg-type]
        )
