"""ffmpeg / ffprobe 封裝：所有 subprocess 呼叫集中於此，方便測試與替換。"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from see.core.errors import RenderError
from see.core.proc import run_text


@dataclass(frozen=True)
class MediaInfo:
    duration: float
    has_video: bool
    has_audio: bool
    width: int | None
    height: int | None
    sample_rate: int | None


class FFmpeg:
    def __init__(self, ffmpeg: str = "ffmpeg", ffprobe: str = "ffprobe") -> None:
        self.ffmpeg = ffmpeg
        self.ffprobe = ffprobe

    def available(self) -> bool:
        return shutil.which(self.ffmpeg) is not None and shutil.which(self.ffprobe) is not None

    def run(self, args: list[str], timeout: float = 600) -> None:
        cmd = [self.ffmpeg, "-hide_banner", "-loglevel", "error", "-y", *args]
        try:
            proc = run_text(cmd, timeout=timeout)
        except FileNotFoundError as e:
            raise RenderError(f"ffmpeg not found: {self.ffmpeg}") from e
        except subprocess.TimeoutExpired as e:
            raise RenderError(f"ffmpeg timed out after {timeout}s: {' '.join(cmd)}") from e
        if proc.returncode != 0:
            raise RenderError(f"ffmpeg failed ({proc.returncode}): {' '.join(cmd)}\n{proc.stderr[-4000:]}")

    def probe(self, path: Path) -> MediaInfo:
        cmd = [self.ffprobe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)]
        try:
            proc = run_text(cmd, timeout=60)
        except FileNotFoundError as e:
            raise RenderError(f"ffprobe not found: {self.ffprobe}") from e
        if proc.returncode != 0:
            raise RenderError(f"ffprobe failed on {path}: {proc.stderr[-2000:]}")
        data = json.loads(proc.stdout or "{}")
        streams = data.get("streams", [])
        v = next((s for s in streams if s.get("codec_type") == "video"), None)
        a = next((s for s in streams if s.get("codec_type") == "audio"), None)
        fmt = data.get("format", {})
        duration = float(fmt.get("duration") or (v or a or {}).get("duration") or 0.0)
        return MediaInfo(
            duration=duration,
            has_video=v is not None,
            has_audio=a is not None,
            width=int(v["width"]) if v and "width" in v else None,
            height=int(v["height"]) if v and "height" in v else None,
            sample_rate=int(a["sample_rate"]) if a and "sample_rate" in a else None,
        )


def escape_filter_path(path: Path) -> str:
    """ffmpeg filter 參數內的路徑跳脫（':' 與 '\\' 與 "'"）。"""
    s = str(path)
    return s.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
