from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from see.core.config import Settings
from see.core.ffmpeg import FFmpeg
from see.pipeline.orchestrator import Orchestrator
from see.providers.image.placeholder import PlaceholderImageProvider
from see.providers.lipsync.null import NullLipSyncProvider
from see.providers.audio.null import NullAudioProvider
from see.providers.llm.mock import MockLLMProvider
from see.providers.registry import Providers
from see.providers.tts.silent import SilentTTSProvider
from see.providers.video.kenburns import KenBurnsVideoProvider
from see.render.renderer import Renderer
from see.storage.project_store import ProjectStore
from see.workers.local import LocalExecutor

TINY_STORY = "小貓咪在院子裡追蝴蝶。牠跳上石頭，又跳下來。最後牠累了，在陽光下睡著了。"
FFMPEG_OK = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
requires_ffmpeg = pytest.mark.skipif(not FFMPEG_OK, reason="ffmpeg/ffprobe not installed")


@pytest.fixture(autouse=True)
def _isolate_local_config(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    """D-065：開發者機器上的 see.local.json 不得影響測試 → 預設指向不存在的檔案（個別測試可再覆寫）。"""
    monkeypatch.setenv("SEE_LOCAL_CONFIG", str(tmp_path_factory.mktemp("cfg") / "absent.local.json"))


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    s = Settings()
    s.workspace = tmp_path / "ws"
    s.tts_provider = "silent"
    s.width, s.height, s.fps = 640, 360, 15  # 測試用小尺寸，加速
    s.min_scene_duration = 2.0
    return s


@pytest.fixture
def providers() -> Providers:
    ff = FFmpeg()
    return Providers(llm=MockLLMProvider(min_scene_s=2.0), image=PlaceholderImageProvider(),
                     video=KenBurnsVideoProvider(ff), tts=SilentTTSProvider(), audio=NullAudioProvider(),
                     lipsync=NullLipSyncProvider())


@pytest.fixture
def orchestrator(settings: Settings, providers: Providers) -> Orchestrator:
    return Orchestrator(settings, providers, LocalExecutor(), ProjectStore(settings.workspace), Renderer())
