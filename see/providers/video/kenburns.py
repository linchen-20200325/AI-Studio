"""KenBurnsVideoProvider：靜態圖 → 有鏡頭運動的片段（FFmpeg zoompan）。LOCAL_FREE。

這是 Phase 0 的 VideoProvider。未來的 AI image-to-video provider 實作同一介面即可替換。
片段內含：旁白音軌（若提供）、燒錄字幕（若提供）。
"""

from __future__ import annotations

from pathlib import Path

from see.core.errors import ProviderError
from see.core.ffmpeg import FFmpeg, escape_filter_path
from see.models.cost import CostEstimate
from see.models.enums import CameraMotion, CostTier, ProviderKind
from see.models.provider import ProviderInfo
from see.providers.base import VideoProvider, VideoRequest, VideoResult


def zoompan_expr(motion: str, frames: int, zoom_max: float = 1.25) -> str:
    """回傳 zoompan 的 z/x/y 表達式。以輸出幀序號 `on` 線性插值，確定性且不依賴前一幀狀態。"""
    d = max(frames - 1, 1)
    p = f"(on/{d})"  # 0 → 1
    zi = f"(1+({zoom_max}-1)*{p})"
    zo = f"({zoom_max}-({zoom_max}-1)*{p})"
    center_x, center_y = "(iw/2-(iw/zoom/2))", "(ih/2-(ih/zoom/2))"
    m = CameraMotion(motion) if motion in CameraMotion.__members__.values() else CameraMotion.STATIC
    if m == CameraMotion.ZOOM_IN:
        return f"z='{zi}':x='{center_x}':y='{center_y}'"
    if m == CameraMotion.ZOOM_OUT:
        return f"z='{zo}':x='{center_x}':y='{center_y}'"
    z_fixed = f"{(1 + zoom_max) / 2:.4f}"
    if m == CameraMotion.PAN_RIGHT:
        return f"z='{z_fixed}':x='(iw-iw/zoom)*{p}':y='{center_y}'"
    if m == CameraMotion.PAN_LEFT:
        return f"z='{z_fixed}':x='(iw-iw/zoom)*(1-{p})':y='{center_y}'"
    if m == CameraMotion.PAN_DOWN:
        return f"z='{z_fixed}':x='{center_x}':y='(ih-ih/zoom)*{p}'"
    if m == CameraMotion.PAN_UP:
        return f"z='{z_fixed}':x='{center_x}':y='(ih-ih/zoom)*(1-{p})'"
    return f"z='1':x='0':y='0'"


class KenBurnsVideoProvider(VideoProvider):
    def __init__(self, ffmpeg: FFmpeg | None = None, crf: int = 23, preset: str = "veryfast") -> None:
        self.ffmpeg = ffmpeg or FFmpeg()
        self.crf = crf
        self.preset = preset
        self.calls = 0

    @property
    def info(self) -> ProviderInfo:
        return ProviderInfo(name="kenburns-ffmpeg", kind=ProviderKind.VIDEO, cost_tier=CostTier.LOCAL_FREE,
                            model=f"zoompan/libx264-crf{self.crf}", version="1")

    def is_available(self) -> bool:
        return self.ffmpeg.available()

    def estimate_cost(self, request: VideoRequest) -> CostEstimate:
        return self._estimate(units=request.duration, unit_name="seconds")

    def generate_clip(self, request: VideoRequest, out_path: Path) -> VideoResult:
        if not request.image_path or not Path(request.image_path).exists():
            raise ProviderError("kenburns needs an existing image_path")
        self.calls += 1
        frames = max(int(round(request.duration * request.fps)), 2)
        w, h = request.width, request.height
        vf = [
            # 先放大到目標的 2 倍再 zoompan，減少整數位移抖動
            f"scale={w * 2}:{h * 2}:force_original_aspect_ratio=increase",
            f"crop={w * 2}:{h * 2}",
            f"zoompan={zoompan_expr(request.camera_motion, frames)}:d={frames}:s={w}x{h}:fps={request.fps}",
            "format=yuv420p",
        ]
        has_subs = False
        if request.subtitle_path and Path(request.subtitle_path).exists():
            style = "FontSize=20,Outline=2,Shadow=1,MarginV=36,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000"
            if request.subtitle_font:
                style = f"FontName={request.subtitle_font}," + style
            vf.append(f"subtitles='{escape_filter_path(Path(request.subtitle_path))}':force_style='{style}'")
            has_subs = True
        args: list[str] = ["-i", str(request.image_path)]
        has_audio = False
        if request.audio_path and Path(request.audio_path).exists():
            args += ["-i", str(request.audio_path)]
            has_audio = True
        if not has_audio:
            args += ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]
        # 旁白（或靜音）補靜音/裁切到片段長度，統一 44.1kHz stereo，方便後續 acrossfade
        graph = f"[0:v]{','.join(vf)}[v];[1:a]aformat=sample_rates=44100:channel_layouts=stereo,apad[a]"
        args += ["-filter_complex", graph, "-map", "[v]", "-map", "[a]", "-c:a", "aac", "-b:a", "128k"]
        args += ["-t", f"{request.duration:.3f}", "-r", str(request.fps),
                 "-c:v", "libx264", "-preset", self.preset, "-crf", str(self.crf), "-pix_fmt", "yuv420p",
                 "-shortest", str(out_path)]
        out_path.parent.mkdir(parents=True, exist_ok=True)
        self.ffmpeg.run(args)
        info = self.ffmpeg.probe(out_path)
        return VideoResult(path=str(out_path), duration=info.duration, provider=self.info.name,
                           model=self.info.model, has_audio=info.has_audio, has_subtitles=has_subs)
