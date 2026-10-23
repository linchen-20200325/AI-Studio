"""PCM 讀寫：統一 44.1 kHz stereo float32（-1..1）。只用標準庫 wave + numpy；解碼其他格式交給 ffmpeg。"""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

from see.core.errors import RenderError
from see.core.ffmpeg import FFmpeg

SAMPLE_RATE = 44100
CHANNELS = 2


def write_wav(path: Path, samples: np.ndarray, sample_rate: int = SAMPLE_RATE) -> Path:
    """samples: (n, 2) 或 (n,) float32；寫 16-bit PCM。呼叫端負責先做 limiter（這裡只做最後的安全 clip）。"""
    x = np.asarray(samples, dtype=np.float32)
    if x.ndim == 1:
        x = np.stack([x, x], axis=1)
    pcm = (np.clip(x, -1.0, 1.0) * 32767.0).astype("<i2")
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(pcm.shape[1])
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm.tobytes())
    return path


def read_wav(path: Path) -> np.ndarray:
    """讀 16-bit PCM wav → (n, 2) float32。非 44.1k／非 stereo／非 16-bit 一律 fail-closed（請先用 decode_to_wav 正規化）。"""
    with wave.open(str(path), "rb") as w:
        if w.getsampwidth() != 2 or w.getframerate() != SAMPLE_RATE or w.getnchannels() not in (1, 2):
            raise RenderError(f"{path}: expected 16-bit {SAMPLE_RATE} Hz mono/stereo wav")
        ch = w.getnchannels()
        data = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32) / 32767.0
    data = data.reshape(-1, ch)
    return np.repeat(data, 2, axis=1) if ch == 1 else data


def decode_to_wav(ffmpeg: FFmpeg, src: Path, dst: Path) -> Path:
    """任意音訊／影片的音軌 → 44.1k stereo 16-bit wav。"""
    ffmpeg.run(["-i", str(src), "-vn", "-ac", str(CHANNELS), "-ar", str(SAMPLE_RATE), "-c:a", "pcm_s16le", str(dst)])
    return dst


def fit_length(x: np.ndarray, n: int, loop: bool = False) -> np.ndarray:
    """補靜音或裁切到 n 個 frame；loop=True 時以重複填滿（BGM 用）。"""
    if len(x) >= n:
        return x[:n]
    if loop and len(x) > 0:
        reps = int(np.ceil(n / len(x)))
        return np.tile(x, (reps, 1))[:n]
    return np.concatenate([x, np.zeros((n - len(x), x.shape[1]), dtype=np.float32)], axis=0)
