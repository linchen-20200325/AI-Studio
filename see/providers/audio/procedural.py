"""ProceduralAudioProvider：以程式生成確定性的測試 BGM／SFX（LOCAL_FREE；D-031）。

- 不使用任何外部素材 → 無授權問題（license = generated）。同一 request 永遠產生同一段音訊（seed 來自 description）。
- 這是第一版「來源」之一；CC0／使用者素材／其他合法來源未來以新的 AudioProvider 加入，不改 Audio Layer。
- 品質定位：測試／占位用的柔和 pad 與簡單音效，**不是**產品級配樂。
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np

from see.audio.pcm import SAMPLE_RATE, write_wav
from see.core.errors import ProviderError
from see.models.cost import CostEstimate
from see.models.enums import CostTier, ProviderKind
from see.models.provider import ProviderInfo
from see.providers.base import AudioProvider, AudioRequest, AudioResult

VERSION = "1"
_ROOTS_HZ = (196.00, 220.00, 246.94, 261.63)                       # G3 A3 B3 C4
_PROGRESSION = ((0, 4, 7), (9, 12, 16), (5, 9, 12), (7, 11, 14))     # I vi IV V（半音）
_SFX_KEYWORDS = {"whoosh": ("風", "飛", "跑", "whoosh", "swish"), "chime": ("鈴", "叮", "星", "chime", "bell", "魔法"),
                 "thud": ("跳", "落", "撞", "thud", "drop")}
SFX_DEFAULT_S = 0.6


def _seed(text: str) -> int:
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:8], 16)


def sfx_variant(description: str) -> str:
    d = description.lower()
    for name, keys in _SFX_KEYWORDS.items():
        if any(k in d for k in keys):
            return name
    return "pop"


def _bgm(duration: float, seed: int) -> np.ndarray:
    n = int(round(duration * SAMPLE_RATE))
    t = np.arange(n, dtype=np.float64) / SAMPLE_RATE
    root = _ROOTS_HZ[seed % len(_ROOTS_HZ)]
    bar_s = (2.0, 2.4, 2.8)[(seed >> 4) % 3]
    out = np.zeros((n, 2), dtype=np.float64)
    bar_n = int(bar_s * SAMPLE_RATE)
    for b0 in range(0, n, bar_n):
        chord = _PROGRESSION[(b0 // bar_n) % len(_PROGRESSION)]
        seg = slice(b0, min(b0 + bar_n + int(0.5 * SAMPLE_RATE), n))  # 0.5 s 尾音與下一和弦重疊
        tt = t[seg] - t[b0]
        env = np.minimum(tt / 0.4, 1.0) * np.exp(-np.maximum(tt - bar_s, 0) / 0.25)
        for k, semi in enumerate(chord):
            f = root * 2 ** (semi / 12)
            for ch, detune in enumerate((0.997, 1.003)):  # 左右微 detune → 寬度
                tone = np.sin(2 * np.pi * f * detune * tt) + 0.3 * np.sin(4 * np.pi * f * detune * tt)
                out[seg, ch] += env * tone / (len(chord) * 1.3)
    peak = np.abs(out).max() if n else 0.0
    return (out / peak * 0.5 if peak > 0 else out).astype(np.float32)


def _sfx(variant: str, duration: float, seed: int) -> np.ndarray:
    n = max(int(round(duration * SAMPLE_RATE)), 1)
    t = np.arange(n) / SAMPLE_RATE
    if variant == "chime":
        x = sum(np.sin(2 * np.pi * f * t) * np.exp(-t * d) for f, d in ((1318.5, 5.0), (1975.5, 7.0), (2637.0, 9.0)))
    elif variant == "whoosh":
        rng = np.random.default_rng(seed)
        noise = rng.standard_normal(n)
        kernel = np.ones(32) / 32  # 簡單低通 → 「風聲」
        x = np.convolve(noise, kernel, mode="same") * np.sin(np.pi * t / t[-1]) ** 2 * 3.0 if n > 1 else noise
    elif variant == "thud":
        f = 90 * np.exp(-t * 6)
        x = np.sin(2 * np.pi * np.cumsum(f) / SAMPLE_RATE) * np.exp(-t * 12)
    else:  # pop
        x = np.sin(2 * np.pi * 880 * t) * np.exp(-t * 30)
    x = np.asarray(x, dtype=np.float64)
    peak = np.abs(x).max()
    x = x / peak * 0.8 if peak > 0 else x
    return np.stack([x, x], axis=1).astype(np.float32)


class ProceduralAudioProvider(AudioProvider):
    def __init__(self) -> None:
        self.calls = 0

    @property
    def info(self) -> ProviderInfo:
        return ProviderInfo(name="procedural-audio", kind=ProviderKind.AUDIO, cost_tier=CostTier.LOCAL_FREE,
                            model="procedural-pad-sfx", version=VERSION)

    def estimate_cost(self, request: AudioRequest) -> CostEstimate:
        return self._estimate(units=request.duration, unit_name="seconds")

    def generate_audio(self, request: AudioRequest, out_path: Path) -> AudioResult:
        self.calls += 1
        seed = _seed(f"{request.kind}:{request.description}")
        if request.kind == "bgm":
            x, variant = _bgm(request.duration, seed), "pad"
        elif request.kind == "sfx":
            variant = str(request.params.get("variant") or sfx_variant(request.description))
            x = _sfx(variant, request.duration, seed)
        else:
            raise ProviderError(f"procedural-audio does not support kind '{request.kind}' (v{VERSION}: bgm, sfx)")
        write_wav(out_path, x)
        return AudioResult(path=str(out_path), duration=len(x) / SAMPLE_RATE, provider=self.info.name, model=self.info.model,
                           meta={"source_type": "procedural", "license": "generated (no external material)",
                                 "seed": seed, "variant": variant, "version": VERSION})
