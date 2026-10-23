"""Kokoro TTS provider（D-027 候選）：fake backend，不需 kokoro 套件、不下載權重。"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest

from see.core.config import Settings
from see.core.errors import ProviderError, ProviderUnavailable
from see.providers.base import TTSRequest
from see.providers.registry import ProviderRegistry
from see.providers.tts.fallback import FallbackTTSProvider
from see.providers.tts.kokoro import (
    MODEL_FILE,
    CONFIG_FILE,
    KokoroTTSProvider,
    download_plan,
    local_voices,
    weights_present,
)
from see.providers.tts.kokoro_download import choose_voices, write_provenance
from see.providers.tts.silent import SilentTTSProvider
from tests.conftest import requires_ffmpeg


class FakeBackend:
    """每個字 0.25 秒的正弦波；voice 決定頻率，方便驗證 voice 真的被用到。"""

    def __init__(self, silent: bool = False, fail: bool = False) -> None:
        self.silent, self.fail, self.calls = silent, fail, []

    def synthesize(self, text: str, voice_path: Path, speed: float) -> tuple[np.ndarray, int]:
        self.calls.append((text, voice_path.stem, speed))
        if self.fail:
            raise RuntimeError("boom")
        sr = 24000
        n = int(sr * 0.25 * len(text) / speed)
        if self.silent:
            return np.zeros(n, dtype=np.float32), sr
        f = 220.0 if voice_path.stem.startswith("zf_") else 110.0
        t = np.arange(n) / sr
        return (0.5 * np.sin(2 * math.pi * f * t)).astype(np.float32), sr

    def describe(self) -> dict:
        return {"device": "fake"}


def make_model_dir(tmp_path: Path, voices=("zf_001", "zm_009")) -> Path:
    d = tmp_path / "kokoro-v1_1-zh"
    (d / "voices").mkdir(parents=True)
    (d / MODEL_FILE).write_bytes(b"\0" * 64)
    (d / CONFIG_FILE).write_text("{}", encoding="utf-8")
    for v in voices:
        (d / "voices" / f"{v}.pt").write_bytes(b"\0" * 16)
    return d


def test_download_plan_is_descriptive_and_offline():
    plan = download_plan()
    assert plan["repo_id"] == "hexgrad/Kokoro-82M-v1.1-zh" and plan["license"] == "Apache-2.0"
    assert "D-027" in plan["approval"] and plan["estimated_mb"] < 500


def test_unavailable_without_weights(tmp_path: Path):
    tts = KokoroTTSProvider(tmp_path / "nope", backend=FakeBackend())
    assert not tts.is_available() and not weights_present(tmp_path / "nope")
    with pytest.raises(ProviderUnavailable):
        tts.synthesize(TTSRequest(text="你好"), tmp_path / "o.wav")


@requires_ffmpeg
def test_synthesize_writes_wav_with_evidence(tmp_path: Path):
    d = make_model_dir(tmp_path)
    be = FakeBackend()
    tts = KokoroTTSProvider(d, backend=be)
    assert tts.is_available() and tts.info.cost_tier == "LOCAL_FREE" and not tts.info.requires_network
    r = tts.synthesize(TTSRequest(text="小貓咪在院子裡追蝴蝶", language="zh-TW"), tmp_path / "n.wav")
    assert Path(r.path).exists() and r.sample_rate == 24000
    assert abs(r.duration - 0.25 * 10) < 0.05  # duration 來自 ffprobe 實測
    assert r.meta["generated_by"] == "kokoro-tts" and r.meta["voice"] == "zf_001"  # default → 第一個女聲
    assert r.meta["device"] == "fake" and r.meta["rtf"] is not None
    assert be.calls[0][1] == "zf_001" and be.calls[0][2] == 1.0


@requires_ffmpeg
def test_voice_selection_and_speed(tmp_path: Path):
    d = make_model_dir(tmp_path)
    be = FakeBackend()
    tts = KokoroTTSProvider(d, backend=be)
    r = tts.synthesize(TTSRequest(text="你好你好", voice="zm_009", speed=2.0), tmp_path / "m.wav")
    assert r.meta["voice"] == "zm_009" and be.calls[0][2] == 2.0 and abs(r.duration - 0.5) < 0.05
    with pytest.raises(ProviderError, match="unknown kokoro voice"):
        tts.synthesize(TTSRequest(text="你好", voice="af_heart"), tmp_path / "x.wav")


def test_fail_closed_on_silence_and_backend_error(tmp_path: Path):
    d = make_model_dir(tmp_path)
    with pytest.raises(ProviderError, match="silent"):
        KokoroTTSProvider(d, backend=FakeBackend(silent=True)).synthesize(TTSRequest(text="你好你好"), tmp_path / "s.wav")
    with pytest.raises(ProviderError, match="synthesis failed"):
        KokoroTTSProvider(d, backend=FakeBackend(fail=True)).synthesize(TTSRequest(text="你好"), tmp_path / "f.wav")
    assert not (tmp_path / "s.wav").exists() and not (tmp_path / "f.wav").exists()


def test_fallback_chain_skips_kokoro_when_unavailable_and_keeps_stable_info(tmp_path: Path):
    kok = KokoroTTSProvider(tmp_path / "missing", backend=FakeBackend())
    fb = FallbackTTSProvider([kok, SilentTTSProvider()])
    assert fb.info.name == "silent-tts"
    r = fb.synthesize(TTSRequest(text="你好"), tmp_path / "a.wav")
    assert r.provider == "silent-tts" and r.meta["generated_by"] == "silent-tts"
    assert any("kokoro-tts: unavailable" in e for e in r.meta["fallback_from"])


def test_fallback_after_kokoro_failure_records_degradation(tmp_path: Path):
    d = make_model_dir(tmp_path)
    kok = KokoroTTSProvider(d, backend=FakeBackend(fail=True))
    fb = FallbackTTSProvider([kok, SilentTTSProvider()])
    assert fb.info.name == "kokoro-tts"  # 首選可用 → fingerprint key 固定為 kokoro
    r = fb.synthesize(TTSRequest(text="你好"), tmp_path / "b.wav")
    assert r.provider == "silent-tts" and fb.info.name == "kokoro-tts"  # 失敗不改 info（同 D-023）
    assert any("kokoro-tts: kokoro synthesis failed" in e for e in r.meta["fallback_from"])


def test_registry_has_kokoro_and_auto_chain(tmp_path: Path):
    s = Settings()
    s.models_dir = tmp_path
    r = ProviderRegistry(s)
    assert {"kokoro", "auto", "espeak", "silent"} <= set(r._tts)
    s.tts_provider = "kokoro"
    k = ProviderRegistry(s).build().tts
    assert isinstance(k, KokoroTTSProvider) and k.model_dir == tmp_path / "kokoro-v1_1-zh" and k.device == "cpu"
    s.tts_provider = "auto"
    auto = ProviderRegistry(s).build().tts
    assert [c.info.name for c in auto.candidates] == ["kokoro-tts", "espeak-tts", "silent-tts"]


def test_choose_voices_and_provenance(tmp_path: Path):
    files = ["config.json", "kokoro-v1_1-zh.pth"] + [f"voices/zf_{i:03d}.pt" for i in (1, 2, 3)] + [f"voices/zm_{i:03d}.pt" for i in (9, 10, 11)]
    assert choose_voices(files, None) == ["zf_001", "zf_002", "zm_009", "zm_010"]
    assert choose_voices(files, ["zm_011"]) == ["zm_011"]
    with pytest.raises(ValueError):
        choose_voices(files, ["af_heart"])
    d = make_model_dir(tmp_path)
    prov = write_provenance(d, "abc123", [d / MODEL_FILE, d / "voices" / "zf_001.pt"], {"voices": ["zf_001"]})
    saved = json.loads((d / "provenance.json").read_text(encoding="utf-8"))
    assert saved["revision"] == "abc123" and saved["files"][MODEL_FILE]["bytes"] == 64
    assert len(saved["files"][MODEL_FILE]["sha256"]) == 64 and "D-027" in prov["approval"]
    assert local_voices(d) == ["zf_001", "zm_009"]


@requires_ffmpeg
def test_pipeline_uses_kokoro_meta_and_retries_degraded_narration(tmp_path: Path, settings, providers):
    """orchestrator：narration meta 進 manifest；fallback 產物在首選恢復後自動重做（同 D-023）。"""
    from see.pipeline.orchestrator import Orchestrator
    from see.render.renderer import Renderer
    from see.storage.project_store import ProjectStore
    from see.workers.local import LocalExecutor

    d = make_model_dir(tmp_path)
    kok = KokoroTTSProvider(d, backend=FakeBackend(fail=True))
    providers.tts = FallbackTTSProvider([kok, SilentTTSProvider()])
    orch = Orchestrator(settings, providers, LocalExecutor(), ProjectStore(settings.workspace), Renderer())
    project = orch.create_project("小貓咪在院子裡追蝴蝶。牠跳上石頭，又跳下來。最後牠累了，在陽光下睡著了。", project_id="k1")
    orch.write_script(project)
    orch.storyboard(project)
    reports = orch.build_scene_assets(project)
    m = reports[0].narration_meta
    assert m["generated_by"] == "silent-tts" and m["degraded"] is True and m["regenerated"] is True
    # 首選恢復 → 降級旁白被淘汰重做
    kok._backend = FakeBackend()
    reports2 = orch.build_scene_assets(project)
    assert "narration" in reports2[0].rebuilt and reports2[0].narration_meta["generated_by"] == "kokoro-tts"
    assert reports2[0].narration_meta["degraded"] is False and "degraded narration" in reports2[0].reasons["narration"]
    rec = orch.store.load_manifest(project.project_id, project.scenes[0].scene_id).entries["narration"]
    assert rec.provider == "kokoro-tts" and rec.meta["voice"] == "zf_001"
    assert project.scenes[0].measured_narration_duration > 0
    # 第三次：全部 reuse
    reports3 = orch.build_scene_assets(project)
    assert "narration" in reports3[0].reused and reports3[0].narration_meta["regenerated"] is False
