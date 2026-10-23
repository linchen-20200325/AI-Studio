"""Voice Selection 非 UI 部分（D-030）：角色 voice／語速、優先序、試聽、確認閘門、舊專案 fingerprint 不變。"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from see.core.errors import InvalidTransition, PaidProviderNotApproved, SchemaViolation
from see.models import CostTier, JobKind, JobStatus
from see.models.provider import ProviderInfo
from see.providers.tts.silent import SilentTTSProvider
from see.ui.server import create_app
from tests.conftest import TINY_STORY, requires_ffmpeg


def _planned(orch, pid="vs1"):
    p = orch.create_project(TINY_STORY, project_id=pid)
    orch.write_script(p)
    orch.storyboard(p)
    return p


def test_resolution_order(orchestrator):
    p = _planned(orchestrator)
    s0 = p.scenes[0]
    assert orchestrator.resolve_voice(p, s0) == ("default", 1.0, "provider-default")  # 舊專案行為不變
    orchestrator.set_character(p, "narrator", display_name="旁白", voice_id="zm_010", speed=1.1)
    orchestrator.update_scene(p, s0.scene_id, narrator_id="narrator")
    s0 = p.scenes[0]
    assert orchestrator.resolve_voice(p, s0) == ("zm_010", 1.1, "character:narrator")
    orchestrator.update_scene(p, s0.scene_id, voice="zf_002", speech_speed=0.9)
    assert orchestrator.resolve_voice(p, p.scenes[0]) == ("zf_002", 0.9, "scene")
    with pytest.raises(ValueError, match="unknown narrator_id"):
        orchestrator.update_scene(p, p.scenes[1].scene_id, narrator_id="ghost")
    p.scenes[1].narrator_id = "ghost"  # 直接寫壞資料 → build 時 fail-closed
    with pytest.raises(SchemaViolation):
        orchestrator.resolve_voice(p, p.scenes[1])


def test_character_edit_resets_confirmation_and_scene_status(orchestrator):
    p = _planned(orchestrator, "vs2")
    orchestrator.set_character(p, "hero", voice_id="zm_010")
    orchestrator.update_scene(p, p.scenes[0].scene_id, narrator_id="hero")
    assert orchestrator.unconfirmed_characters(p) == ["hero"]
    orchestrator.confirm_character(p, "hero")
    assert p.characters["hero"].confirmed and p.characters["hero"].confirmed_at is not None
    assert orchestrator.unconfirmed_characters(p) == []
    same = orchestrator.set_character(p, "hero", voice_id="zm_010")  # 無實際變更 → 保留確認
    assert same.confirmed
    orchestrator.set_character(p, "hero", speed=1.2)
    assert not p.characters["hero"].confirmed and orchestrator.unconfirmed_characters(p) == ["hero"]
    with pytest.raises(ValueError):
        orchestrator.set_character(p, "bad id!", voice_id="x")
    with pytest.raises(KeyError):
        orchestrator.confirm_character(p, "nobody")


@requires_ffmpeg
def test_final_requires_confirmed_character_and_fingerprint_stability(orchestrator, providers):
    rep = orchestrator.run(TINY_STORY, project_id="vs3")
    p = rep.project
    # 未使用角色：重建全部 reuse（新欄位不改舊 fingerprint）
    calls = providers.tts.calls
    r2 = orchestrator.rebuild(p)
    assert providers.tts.calls == calls and all("narration" in r.reused for r in r2.scene_reports)
    orchestrator.set_character(p, "narrator", voice_id="default", speed=1.3)
    orchestrator.update_scene(p, p.scenes[0].scene_id, narrator_id="narrator")
    r3 = orchestrator.rebuild(p)
    rebuilt = {r.scene_id: r.rebuilt for r in r3.scene_reports}
    assert "narration" in rebuilt[p.scenes[0].scene_id]  # 語速變了 → 只重做該景旁白
    assert all("narration" not in v for k, v in rebuilt.items() if k != p.scenes[0].scene_id)
    m = r3.scene_reports[0].narration_meta
    assert m["voice_source"] == "character:narrator" and m["narrator_id"] == "narrator"
    orchestrator.approve(p)
    with pytest.raises(InvalidTransition, match="unconfirmed"):
        orchestrator.render(p, JobKind.FINAL)
    orchestrator.confirm_character(p, "narrator")
    job, _ = orchestrator.render(p, JobKind.FINAL)
    assert job.status == JobStatus.DONE


def test_preview_voice_does_not_touch_projects(orchestrator, tmp_path: Path):
    res = orchestrator.preview_voice("你好", voice="default", speed=1.0)
    assert Path(res.path).exists() and "voice_previews" in res.path
    assert orchestrator.store.list_projects() == []


def test_preview_voice_refuses_paid(orchestrator):
    class PaidTTS(SilentTTSProvider):
        @property
        def info(self) -> ProviderInfo:
            return ProviderInfo(name="paid-tts", kind="tts", cost_tier=CostTier.PAID, model="x")

    orchestrator.p.tts = PaidTTS()
    with pytest.raises(PaidProviderNotApproved):
        orchestrator.preview_voice("你好")


@requires_ffmpeg
@pytest.mark.e2e
def test_voice_api(settings):
    c = TestClient(create_app(settings, sync_jobs=True))
    v = c.get("/api/voices").json()
    assert v["provider"] == "silent-tts" and v["voices"] == []
    r = c.post("/api/voices/preview", json={"text": "你好", "speed": 1.0}).json()
    assert r["url"].startswith("/api/voice-previews/") and r["duration"] > 0
    assert c.get(r["url"]).headers["content-type"] == "audio/wav"
    assert c.get("/api/voice-previews/..%2Fx.wav").status_code == 404
    pid = c.post("/api/projects", json={"text": TINY_STORY}).json()["project_id"]
    p = c.post(f"/api/projects/{pid}/characters/narrator", json={"voice_id": "zm_010", "speed": 1.1}).json()
    assert p["characters"]["narrator"]["voice_id"] == "zm_010" and not p["characters"]["narrator"]["confirmed"]
    sid = p["scenes"][0]["scene_id"]
    assert c.post(f"/api/projects/{pid}/scenes/{sid}", json={"narrator_id": "narrator"}).status_code == 202
    assert c.get(f"/api/projects/{pid}").json()["unconfirmed_characters"] == ["narrator"]
    assert c.post(f"/api/projects/{pid}/approve", json={}).status_code == 200
    assert c.post(f"/api/projects/{pid}/final").status_code == 409
    assert c.post(f"/api/projects/{pid}/characters/narrator/confirm").json()["unconfirmed_characters"] == []
    assert c.post(f"/api/projects/{pid}/final").status_code == 202
    assert c.post(f"/api/projects/{pid}/characters/ghost/confirm").status_code == 404
