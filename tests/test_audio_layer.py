"""Audio Layer（D-031）：程序化 BGM／SFX、ducking、limiter、混音整合與相容性。"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from see.audio.mixer import DuckingParams, LimiterParams, MixParams, SfxEvent, db_to_gain, ducking_envelope, limit, mix
from see.audio.pcm import SAMPLE_RATE, decode_to_wav, read_wav, write_wav
from see.core.errors import PaidProviderNotApproved, ProviderError
from see.core.ffmpeg import FFmpeg
from see.models import CostTier
from see.models.provider import ProviderInfo
from see.providers.audio.null import NullAudioProvider
from see.providers.audio.procedural import ProceduralAudioProvider, sfx_variant
from see.providers.base import AudioRequest
from tests.conftest import TINY_STORY, requires_ffmpeg

SR = SAMPLE_RATE


def tone(seconds: float, amp: float = 0.5, f: float = 440.0) -> np.ndarray:
    t = np.arange(int(seconds * SR)) / SR
    x = (amp * np.sin(2 * np.pi * f * t)).astype(np.float32)
    return np.stack([x, x], axis=1)


def silence(seconds: float) -> np.ndarray:
    return np.zeros((int(seconds * SR), 2), dtype=np.float32)


# ---------------------------------------------------------------- unit（numpy only）
def test_procedural_is_deterministic(tmp_path: Path):
    p = ProceduralAudioProvider()
    assert p.info.cost_tier == CostTier.LOCAL_FREE and not p.info.requires_network
    a = p.generate_audio(AudioRequest(kind="bgm", description="輕柔背景音樂", duration=3.0), tmp_path / "a.wav")
    b = p.generate_audio(AudioRequest(kind="bgm", description="輕柔背景音樂", duration=3.0), tmp_path / "b.wav")
    assert Path(a.path).read_bytes() == Path(b.path).read_bytes()
    assert a.meta["source_type"] == "procedural" and "generated" in a.meta["license"] and abs(a.duration - 3.0) < 1e-3
    x = read_wav(Path(a.path))
    assert 0.3 < np.abs(x).max() <= 0.51
    s1 = p.generate_audio(AudioRequest(kind="sfx", description="一陣風吹過", duration=0.6), tmp_path / "s.wav")
    assert s1.meta["variant"] == "whoosh" and sfx_variant("叮的一聲") == "chime" and sfx_variant("xyz") == "pop"
    with pytest.raises(ProviderError):
        p.generate_audio(AudioRequest(kind="ambience", description="雨", duration=1.0), tmp_path / "x.wav")


def test_ducking_engages_and_recovers():
    p = DuckingParams()
    narr = np.concatenate([silence(1.0), tone(1.0, 0.3), silence(1.5)])
    env, st = ducking_envelope(narr, p)
    at = lambda s: float(env[int(s * SR)])  # noqa: E731
    assert at(0.5) == pytest.approx(1.0, abs=1e-3)                       # 人聲前：不衰減
    assert at(1.7) == pytest.approx(db_to_gain(p.depth_db), rel=0.05)    # 人聲中：衰減到 depth
    assert at(2.05) < 0.5                                                 # hold：短停頓不立刻恢復
    assert at(3.4) > 0.9                                                  # release 後平順恢復
    assert np.all(np.abs(np.diff(env)) < 0.01)                            # 無階梯跳變
    assert st["active_ratio"] > 0 and st["min_gain_db"] <= p.depth_db + 0.5


def test_no_narration_means_no_ducking():
    env, st = ducking_envelope(silence(2.0), DuckingParams())
    assert np.all(env == 1.0) and st["active_ratio"] == 0.0
    out, stats = mix(silence(2.0), tone(2.0, 0.5), [], MixParams())
    mid = out[SR // 2: SR * 3 // 2]
    assert np.abs(mid).max() == pytest.approx(0.5 * db_to_gain(MixParams().bgm_gain_db), rel=0.02)


def test_narration_only_is_untouched():
    narr = tone(1.0, 0.4)
    out, stats = mix(narr, None, [], MixParams())
    assert np.allclose(out, narr, atol=1e-6) and stats["ducking"]["enabled"] is False
    assert stats["limiter_max_reduction_db"] == 0.0


def test_limiter_prevents_clipping():
    p = MixParams(bgm_gain_db=0.0, sfx_gain_db=0.0, ducking=DuckingParams(enabled=False))
    loud = tone(1.0, 0.99)
    out, stats = mix(loud, tone(1.0, 0.99, 445), [SfxEvent(0.2, tone(0.3, 0.99, 880), "pop")], p)
    ceiling = db_to_gain(p.limiter.ceiling_db)
    assert np.abs(out).max() <= ceiling + 1e-6 and stats["pre_limit_peak_db"] > 0 and stats["limiter_max_reduction_db"] < 0
    y, st = limit(tone(0.5, 0.2), LimiterParams())
    assert np.allclose(y, tone(0.5, 0.2)) and st["limiter_max_reduction_db"] == 0.0


def test_sfx_placement_and_outside_timeline():
    out, stats = mix(silence(1.0), None, [SfxEvent(0.5, tone(0.1, 0.5), "a"), SfxEvent(5.0, tone(0.1), "late")], MixParams())
    assert stats["sfx"][0]["placed"] and not stats["sfx"][1]["placed"]
    assert np.abs(out[: int(0.49 * SR)]).max() == 0.0 and np.abs(out[int(0.5 * SR): int(0.6 * SR)]).max() > 0


def test_narration_stays_dominant_with_bgm():
    narr = tone(2.0, 0.3, 300)
    bgm = tone(2.0, 0.5, 200)
    out, _ = mix(narr, bgm, [], MixParams())
    seg = slice(int(0.8 * SR), int(1.2 * SR))
    bgm_part = out[seg] - narr[seg]
    assert np.sqrt(np.mean(bgm_part ** 2)) < 0.1 * np.sqrt(np.mean(narr[seg] ** 2))  # BGM 比人聲低 > 20 dB


# ---------------------------------------------------------------- integration（ffmpeg + orchestrator）
def _audio_json(orch, pid, kind="preview") -> dict:
    return json.loads((orch.store.renders_dir(pid) / f"{kind}.audio.json").read_text(encoding="utf-8"))


@requires_ffmpeg
def test_null_audio_is_backward_compatible(orchestrator):
    rep = orchestrator.run(TINY_STORY, project_id="au0")
    ev = _audio_json(orchestrator, "au0")
    assert ev["status"] == "disabled" and ev["provider"] == "null-audio" and ev["cost_tier"] == "LOCAL_FREE"
    assert not (orchestrator.store.renders_dir("au0") / "preview.dry.mp4").exists()
    assert rep.output_path.exists() and not (orchestrator.store.renders_dir("au0") / "audio").exists()


@requires_ffmpeg
def test_procedural_bgm_and_sfx_mix_without_touching_scene_cache(orchestrator, providers):
    rep = orchestrator.run(TINY_STORY, project_id="au1")  # null 先跑：建立 per-scene 快取
    p = rep.project
    calls = (providers.image.calls, providers.tts.calls, providers.video.calls)
    orchestrator.p.audio = ProceduralAudioProvider()
    sid = p.scenes[1].scene_id
    cues = [c.model_dump() for c in p.scenes[1].audio_cues] + [{"kind": "sfx", "description": "叮的一聲", "start_offset": 0.5},
                                                                 {"kind": "ambience", "description": "雨聲"}]
    orchestrator.update_scene(p, sid, audio_cues=cues)
    r2 = orchestrator.rebuild(p)
    assert (providers.image.calls, providers.tts.calls, providers.video.calls) == calls  # audio_cues 不進任何 scene fingerprint
    assert all(set(r.rebuilt) == set() for r in r2.scene_reports)
    ev = _audio_json(orchestrator, "au1")
    assert ev["status"] == "mixed" and not ev["degraded"]
    assert ev["bgm"]["source_type"] == "procedural" and ev["bgm"]["status"] == "ok" and ev["bgm"]["from_scene"] == p.scenes[0].scene_id
    assert ev["sfx"][0]["variant"] == "chime" and ev["sfx"][0]["status"] == "ok"
    assert ev["mix"]["sfx"][0]["placed"] and ev["mix"]["ducking"]["enabled"] is True
    assert ev["mix"]["ducking"]["active_ratio"] == 0.0  # Silent TTS：無人聲 → 不 duck
    assert any(s["kind"] == "ambience" for s in ev["skipped"])
    assert ev["mix"]["peak_db"] <= MixParams().limiter.ceiling_db + 0.1
    assert ev["params"]["ducking"]["depth_db"] == MixParams().ducking.depth_db
    out = r2.output_path
    info = FFmpeg().probe(out)
    assert info.has_audio and info.has_video and abs(info.duration - r2.timeline.total_duration) < 0.5
    wav = read_wav(decode_to_wav(FFmpeg(), out, out.with_suffix(".check.wav")))
    assert np.abs(wav).max() > 0.01  # 有 BGM（narration 是靜音）
    assert not (orchestrator.store.renders_dir("au1") / "preview.dry.mp4").exists()


@requires_ffmpeg
def test_failing_audio_source_is_reported_not_hidden(orchestrator):
    class Broken(ProceduralAudioProvider):
        def generate_audio(self, request, out_path):
            raise ProviderError("disk on fire")

    orchestrator.p.audio = Broken()
    rep = orchestrator.run(TINY_STORY, project_id="au2")
    ev = _audio_json(orchestrator, "au2")
    assert ev["status"] == "unavailable" and ev["degraded"] and ev["bgm"]["status"] == "unavailable"
    assert "disk on fire" in ev["bgm"]["error"] and rep.output_path.exists()  # 照樣輸出 narration-only


@requires_ffmpeg
def test_paid_audio_source_is_blocked(orchestrator):
    class Paid(ProceduralAudioProvider):
        @property
        def info(self):
            return ProviderInfo(name="paid-music", kind="audio", cost_tier=CostTier.PAID, model="x")

    paid = Paid()
    orchestrator.p.audio = paid
    with pytest.raises(PaidProviderNotApproved):
        orchestrator.run(TINY_STORY, project_id="au3")
    assert paid.calls == 0


def test_registry_and_null_flag():
    from see.core.config import Settings
    from see.providers.registry import ProviderRegistry

    s = Settings()
    assert s.audio_provider == "null" and not NullAudioProvider().generates_audio  # 預設不變（產品聲音體驗 → DG-17）
    assert {"null", "procedural"} <= set(ProviderRegistry(s)._audio)
    s.audio_provider = "procedural"
    assert ProviderRegistry(s).build().audio.info.name == "procedural-audio"


def test_write_read_roundtrip(tmp_path: Path):
    x = tone(0.2, 0.5)
    y = read_wav(write_wav(tmp_path / "r.wav", x))
    assert y.shape == x.shape and np.allclose(x, y, atol=1e-4)
