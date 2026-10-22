"""Renderer：把 Timeline 的片段用 xfade / acrossfade 組裝成一支 mp4。LOCAL_FREE（FFmpeg）。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from see.core.errors import RenderError
from see.core.ffmpeg import FFmpeg
from see.models.enums import Transition
from see.models.timeline import Timeline, TimelineItem

_XFADE = {
    Transition.CUT: "fade",
    Transition.FADE: "fade",
    Transition.DISSOLVE: "dissolve",
    Transition.WIPE_LEFT: "wipeleft",
    Transition.SLIDE_LEFT: "slideleft",
    Transition.FADE_BLACK: "fadeblack",
}
CUT_DURATION = 0.08  # Phase 0 限制：cut 以極短 fade 模擬（見 DECISIONS D-005）


@dataclass(frozen=True)
class ClipInput:
    scene_id: str
    index: int
    path: Path
    duration: float
    transition_in: Transition


@dataclass(frozen=True)
class EncodeProfile:
    crf: int = 23
    preset: str = "veryfast"
    audio_bitrate: str = "128k"


PREVIEW_PROFILE = EncodeProfile()
FINAL_PROFILE = EncodeProfile(crf=20, preset="medium", audio_bitrate="192k")


def build_timeline(clips: list[ClipInput], transition_duration: float, fps: int, width: int, height: int) -> Timeline:
    if not clips:
        raise RenderError("timeline needs at least one clip")
    items: list[TimelineItem] = []
    t = 0.0
    for i, c in enumerate(clips):
        if i == 0:
            td = 0.0
        else:
            td = CUT_DURATION if c.transition_in == Transition.CUT else transition_duration
            prev = clips[i - 1]
            td = min(td, prev.duration * 0.5, c.duration * 0.5)  # xfade 要求 < 兩側片長
        start = max(t - td, 0.0)
        end = start + c.duration
        items.append(TimelineItem(scene_id=c.scene_id, index=c.index, clip_path=str(c.path), clip_duration=c.duration,
                                  start=round(start, 3), end=round(end, 3), transition_in=c.transition_in,
                                  transition_in_duration=round(td, 3)))
        t = end
    return Timeline(fps=fps, width=width, height=height, items=items)


class Renderer:
    def __init__(self, ffmpeg: FFmpeg | None = None) -> None:
        self.ffmpeg = ffmpeg or FFmpeg()

    def filter_graph(self, timeline: Timeline) -> tuple[str, str, str]:
        """回傳 (filter_complex, video_label, audio_label)。"""
        items = timeline.items
        if len(items) == 1:
            return "[0:v]copy[vout];[0:a]anull[aout]", "[vout]", "[aout]"
        parts: list[str] = []
        v_prev, a_prev = "[0:v]", "[0:a]"
        for i in range(1, len(items)):
            it = items[i]
            td = it.transition_in_duration
            offset = it.start  # 下一段開始疊入的時間點
            v_out = f"[v{i}]" if i < len(items) - 1 else "[vout]"
            a_out = f"[a{i}]" if i < len(items) - 1 else "[aout]"
            parts.append(f"{v_prev}[{i}:v]xfade=transition={_XFADE[it.transition_in]}:duration={td:.3f}:offset={offset:.3f}{v_out}")
            parts.append(f"{a_prev}[{i}:a]acrossfade=d={td:.3f}:c1=tri:c2=tri{a_out}")
            v_prev, a_prev = v_out, a_out
        return ";".join(parts), "[vout]", "[aout]"

    def assemble(self, timeline: Timeline, out_path: Path, profile: EncodeProfile = PREVIEW_PROFILE) -> Path:
        for it in timeline.items:
            if not Path(it.clip_path).exists():
                raise RenderError(f"missing clip for {it.scene_id}: {it.clip_path}")
        graph, v, a = self.filter_graph(timeline)
        args: list[str] = []
        for it in timeline.items:
            args += ["-i", it.clip_path]
        args += ["-filter_complex", graph, "-map", v, "-map", a,
                 "-c:v", "libx264", "-preset", profile.preset, "-crf", str(profile.crf), "-pix_fmt", "yuv420p",
                 "-r", str(timeline.fps), "-c:a", "aac", "-b:a", profile.audio_bitrate,
                 "-movflags", "+faststart", str(out_path)]
        out_path.parent.mkdir(parents=True, exist_ok=True)
        self.ffmpeg.run(args)
        return out_path
