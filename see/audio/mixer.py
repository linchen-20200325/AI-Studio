"""純 numpy 混音：narration + BGM + SFX，含 ducking 與 peak limiter。確定性、可單元測試，沒有任何素材來源知識。

所有可調參數集中在 `MixParams`（不散落 magic numbers）。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np

from see.audio.pcm import SAMPLE_RATE


def db_to_gain(db: float) -> float:
    return float(10.0 ** (db / 20.0))


def gain_to_db(g: float) -> float:
    return float(20.0 * np.log10(max(g, 1e-9)))


@dataclass(frozen=True)
class DuckingParams:
    enabled: bool = True
    depth_db: float = -12.0          # narration 出現時 BGM 額外衰減量
    threshold_db: float = -40.0      # narration RMS 高於此值視為「有人聲」
    window_ms: float = 20.0          # RMS 偵測窗
    attack_ms: float = 60.0          # 壓下去的速度
    release_ms: float = 450.0        # 恢復的速度（平順）
    hold_ms: float = 200.0           # 人聲停頓短於此值不恢復（避免抽動）


@dataclass(frozen=True)
class LimiterParams:
    ceiling_db: float = -1.0         # 輸出峰值上限（dBFS）
    lookahead_ms: float = 5.0
    release_ms: float = 80.0


@dataclass(frozen=True)
class MixParams:
    narration_gain_db: float = 0.0
    bgm_gain_db: float = -18.0       # BGM 基準音量（未 duck 時）
    sfx_gain_db: float = -6.0
    bgm_fade_s: float = 1.5          # BGM 開頭／結尾淡入淡出
    ducking: DuckingParams = field(default_factory=DuckingParams)
    limiter: LimiterParams = field(default_factory=LimiterParams)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _one_pole(target: np.ndarray, attack_coef: float, release_coef: float) -> np.ndarray:
    """對 per-window 目標增益做非對稱平滑（下降用 attack、上升用 release）。窗數少（每秒 50 個），迭代成本可忽略。"""
    out = np.empty_like(target)
    g = 1.0
    for i, t in enumerate(target):
        coef = attack_coef if t < g else release_coef
        g = t + (g - t) * coef
        out[i] = g
    return out


def ducking_envelope(narration: np.ndarray, p: DuckingParams, sample_rate: int = SAMPLE_RATE) -> tuple[np.ndarray, dict[str, Any]]:
    """回傳 per-sample BGM 增益（1 = 不衰減）與統計。narration 全靜音 → 全 1。"""
    n = len(narration)
    if not p.enabled or n == 0:
        return np.ones(n, dtype=np.float32), {"active_ratio": 0.0, "min_gain_db": 0.0}
    win = max(int(sample_rate * p.window_ms / 1000.0), 1)
    n_win = int(np.ceil(n / win))
    mono = narration.mean(axis=1) if narration.ndim == 2 else narration
    padded = np.zeros(n_win * win, dtype=np.float32)
    padded[:n] = mono
    rms = np.sqrt(np.mean(padded.reshape(n_win, win) ** 2, axis=1))
    active = rms > db_to_gain(p.threshold_db)
    hold = int(np.ceil(p.hold_ms / p.window_ms))
    if hold > 0 and active.any():  # hold：最近 hold 個窗內有人聲就維持 duck（向量化的「向後延伸」）
        idx = np.where(active, np.arange(n_win), -10**9)
        last = np.maximum.accumulate(idx)
        active = (np.arange(n_win) - last) <= hold
    target = np.where(active, db_to_gain(p.depth_db), 1.0).astype(np.float32)
    tau = lambda ms: float(np.exp(-p.window_ms / max(ms, 1e-6)))  # noqa: E731
    smooth = _one_pole(target, tau(p.attack_ms), tau(p.release_ms))
    centers = (np.arange(n_win) + 0.5) * win
    env = np.interp(np.arange(n), centers, smooth).astype(np.float32)
    return env, {"active_ratio": round(float(active.mean()), 4), "min_gain_db": round(gain_to_db(float(env.min())), 2)}


def limit(x: np.ndarray, p: LimiterParams, sample_rate: int = SAMPLE_RATE) -> tuple[np.ndarray, dict[str, Any]]:
    """Look-ahead peak limiter：輸出峰值 ≤ ceiling；回傳最大增益衰減。"""
    if len(x) == 0:
        return x, {"limiter_max_reduction_db": 0.0}
    ceiling = db_to_gain(p.ceiling_db)
    blk = max(int(sample_rate * p.lookahead_ms / 1000.0), 1)
    n_blk = int(np.ceil(len(x) / blk))
    peak = np.zeros(n_blk * blk, dtype=np.float32)
    peak[: len(x)] = np.abs(x).max(axis=1) if x.ndim == 2 else np.abs(x)
    blk_peak = peak.reshape(n_blk, blk).max(axis=1)
    # 每塊取「本塊與下一塊」的峰值 → 在峰值到達前就開始降增益
    ahead = np.maximum(blk_peak, np.append(blk_peak[1:], 0.0))
    target = np.minimum(1.0, ceiling / np.maximum(ahead, 1e-9)).astype(np.float32)
    rel = float(np.exp(-p.lookahead_ms / max(p.release_ms, 1e-6)))
    smooth = _one_pole(target, 0.0, rel)  # attack 立即
    smooth = np.minimum(smooth, target)    # 保證不超過每塊所需
    g = np.repeat(smooth, blk)[: len(x)]
    y = x * (g[:, None] if x.ndim == 2 else g)
    y = np.clip(y, -ceiling, ceiling)      # 數值安全網（理論上不會觸發）
    return y.astype(np.float32), {"limiter_max_reduction_db": round(gain_to_db(float(smooth.min())), 2)}


@dataclass
class SfxEvent:
    start_s: float
    samples: np.ndarray  # (n, 2)
    label: str = ""


def mix(narration: np.ndarray, bgm: np.ndarray | None, sfx: list[SfxEvent], p: MixParams,
        sample_rate: int = SAMPLE_RATE) -> tuple[np.ndarray, dict[str, Any]]:
    """narration 長度決定總長；bgm 已由呼叫端 fit 到同長；sfx 依 start_s 疊加（超出尾端截掉）。"""
    n = len(narration)
    out = narration.astype(np.float32) * db_to_gain(p.narration_gain_db)
    stats: dict[str, Any] = {"duration_s": round(n / sample_rate, 3), "bgm": bgm is not None, "sfx_count": len(sfx)}
    if bgm is not None:
        b = bgm[:n].astype(np.float32) * db_to_gain(p.bgm_gain_db)
        fade = min(int(p.bgm_fade_s * sample_rate), n // 2)
        if fade > 0:
            ramp = np.linspace(0.0, 1.0, fade, dtype=np.float32)
            b[:fade] *= ramp[:, None]
            b[n - fade:] *= ramp[::-1][:, None]
        env, dstats = ducking_envelope(narration, p.ducking, sample_rate)
        out = out + b * env[:, None]
        stats["ducking"] = {"enabled": p.ducking.enabled, **dstats}
    else:
        stats["ducking"] = {"enabled": False, "reason": "no bgm"}
    placed = []
    sfx_gain = db_to_gain(p.sfx_gain_db)
    for ev in sfx:
        start = int(round(ev.start_s * sample_rate))
        if start >= n or start < 0:
            placed.append({"label": ev.label, "start_s": ev.start_s, "placed": False, "reason": "outside timeline"})
            continue
        seg = ev.samples[: n - start] * sfx_gain
        out[start:start + len(seg)] += seg
        placed.append({"label": ev.label, "start_s": round(ev.start_s, 3), "placed": True, "duration_s": round(len(seg) / sample_rate, 3)})
    stats["sfx"] = placed
    stats["pre_limit_peak_db"] = round(gain_to_db(float(np.abs(out).max()) if n else 0.0), 2)
    out, lstats = limit(out, p.limiter, sample_rate)
    stats.update(lstats)
    stats["peak_db"] = round(gain_to_db(float(np.abs(out).max()) if n else 0.0), 2)
    return out, stats
