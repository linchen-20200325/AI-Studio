"""字幕切句與 SRT 產生（確定性，不依賴 AI）。"""

from __future__ import annotations

import re
from dataclasses import dataclass

_SPLIT_RE = re.compile(r"(?<=[。！？!?；;])|(?<=[，,、：:])")
_STRIP_RE = re.compile(r"[\s]+")


@dataclass(frozen=True)
class Cue:
    index: int
    start: float
    end: float
    text: str


def split_sentences(text: str) -> list[str]:
    """按中文標點切成句子；會把句尾標點保留在前一句。"""
    text = _STRIP_RE.sub("", text)
    parts = [p for p in _SPLIT_RE.split(text) if p]
    return parts or ([text] if text else [])


def chunk_for_display(text: str, max_chars: int = 18) -> list[str]:
    """把文字切成每行 ≤ max_chars 的字幕段；優先在標點處切，必要時硬切。"""
    sentences = split_sentences(text)
    chunks: list[str] = []
    buf = ""
    for s in sentences:
        if len(buf) + len(s) <= max_chars:
            buf += s
            continue
        if buf:
            chunks.append(buf)
            buf = ""
        while len(s) > max_chars:
            chunks.append(s[:max_chars])
            s = s[max_chars:]
        buf = s
    if buf:
        chunks.append(buf)
    return [c.strip("，,、：:") or c for c in chunks]


def build_cues(text: str, duration: float, max_chars: int = 18, lead_in: float = 0.0) -> list[Cue]:
    """按字數比例把 duration 分配給各段。"""
    chunks = chunk_for_display(text, max_chars)
    if not chunks or duration <= 0:
        return []
    total_chars = sum(len(c) for c in chunks) or 1
    cues: list[Cue] = []
    t = lead_in
    usable = max(duration - lead_in, 0.1)
    for i, c in enumerate(chunks):
        span = usable * len(c) / total_chars
        end = min(t + span, lead_in + usable)
        cues.append(Cue(index=i + 1, start=round(t, 3), end=round(max(end, t + 0.2), 3), text=c))
        t = end
    return cues


def _ts(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def to_srt(cues: list[Cue]) -> str:
    blocks = [f"{c.index}\n{_ts(c.start)} --> {_ts(c.end)}\n{c.text}\n" for c in cues]
    return "\n".join(blocks) + ("\n" if blocks else "")
