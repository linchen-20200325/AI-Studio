"""設定：環境變數 → Settings。不含任何 secret 的預設值。"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


def _env(name: str, default: str) -> str:
    value = os.environ.get(name)
    return value if value not in (None, "") else default


def detect_cjk_font() -> str:
    """用 fontconfig 找可顯示中文的字型；找不到回傳空字串（libass 會用預設字型）。"""
    fc_list = shutil.which("fc-list")
    if not fc_list:
        return ""
    try:
        out = subprocess.run([fc_list, ":lang=zh", "family"], capture_output=True, text=True, timeout=10).stdout
    except (subprocess.SubprocessError, OSError):
        return ""
    families: list[str] = []
    for line in out.splitlines():
        for fam in line.split(","):
            fam = fam.strip()
            if fam:
                families.append(fam)
    preferred = ("Noto Sans CJK TC", "Noto Sans CJK SC", "Noto Sans CJK", "WenQuanYi Zen Hei",
                 "WenQuanYi Micro Hei", "Microsoft JhengHei", "PingFang TC", "Droid Sans Fallback")
    for p in preferred:
        if p in families:
            return p
    for p in preferred:
        for fam in families:
            if fam.startswith(p):
                return fam
    return families[0] if families else ""


@dataclass
class Settings:
    workspace: Path = field(default_factory=lambda: Path(_env("SEE_WORKSPACE", "./workspace")).resolve())
    llm_provider: str = field(default_factory=lambda: _env("SEE_LLM_PROVIDER", "mock"))
    image_provider: str = field(default_factory=lambda: _env("SEE_IMAGE_PROVIDER", "placeholder"))
    video_provider: str = field(default_factory=lambda: _env("SEE_VIDEO_PROVIDER", "kenburns"))
    tts_provider: str = field(default_factory=lambda: _env("SEE_TTS_PROVIDER", "auto"))
    audio_provider: str = field(default_factory=lambda: _env("SEE_AUDIO_PROVIDER", "null"))
    lipsync_provider: str = field(default_factory=lambda: _env("SEE_LIPSYNC_PROVIDER", "null"))
    subtitle_font: str = field(default_factory=lambda: _env("SEE_SUBTITLE_FONT", "") or detect_cjk_font())
    width: int = 1280
    height: int = 720
    fps: int = 25
    transition_duration: float = 0.5
    min_scene_duration: float = 3.0
    max_scene_duration: float = 12.0
    target_total_min: float = 30.0
    target_total_max: float = 60.0
    narration_pad: float = 0.6
    ffmpeg: str = field(default_factory=lambda: _env("SEE_FFMPEG", "ffmpeg"))
    ffprobe: str = field(default_factory=lambda: _env("SEE_FFPROBE", "ffprobe"))

    def fingerprint_params(self) -> dict[str, object]:
        """會影響產物內容的設定；進 fingerprint。"""
        return {
            "width": self.width, "height": self.height, "fps": self.fps,
            "transition_duration": self.transition_duration, "subtitle_font": self.subtitle_font,
            "narration_pad": self.narration_pad,
        }
