"""Web API 測試：同步 runner + Silent TTS，離線確定性。"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from see.core.config import Settings
from see.ui.server import create_app
from tests.conftest import TINY_STORY, requires_ffmpeg

pytestmark = [requires_ffmpeg, pytest.mark.e2e]


@pytest.fixture
def client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings, sync_jobs=True))


def test_index_and_health(client: TestClient):
    assert "建立 Preview" in client.get("/").text
    h = client.get("/api/health").json()
    assert h["ok"] and h["ffmpeg"]


def test_create_preview_play_edit_approve_final(client: TestClient):
    r = client.post("/api/projects", json={"text": TINY_STORY, "aspect": "9:16", "speech_speed": 1.2})
    assert r.status_code == 202
    pid = r.json()["project_id"]
    p = client.get(f"/api/projects/{pid}").json()
    assert p["job"]["state"] == "done", p["job"]
    assert p["status"] == "PREVIEW" and p["aspect"] == "9:16" and p["preview_url"]
    assert p["cost"]["display"] == "NT$0" and p["cost"]["actual"] == 0
    assert all(v["cost_tier"] in ("LOCAL_FREE", "FREE_TIER") for v in p["cost"]["providers"].values())
    # 影片可透過 API 取得（含 Range 支援供手機播放器）
    v = client.get(p["preview_url"])
    assert v.status_code == 200 and v.headers["content-type"] == "video/mp4" and len(v.content) > 10_000
    rv = client.get(p["preview_url"], headers={"Range": "bytes=0-99"})
    assert rv.status_code == 206 and len(rv.content) == 100
    img = client.get(p["scenes"][0]["image_url"])
    assert img.status_code == 200 and img.headers["content-type"] == "image/png"
    m = p["scenes"][0]["image_meta"]  # D-021：UI 可看見實際生成者／是否重生／黑圖統計
    assert m["generated_by"] == "placeholder-image" and m["regenerated"] is True and m["image_stats"]["is_black"] is False
    # 單景修改
    sid = p["scenes"][1]["scene_id"]
    r = client.post(f"/api/projects/{pid}/scenes/{sid}", json={"narration": "牠一跳，就跳上了最高的那顆石頭。", "camera_motion": "pan_left"})
    assert r.status_code == 202
    p = client.get(f"/api/projects/{pid}").json()
    assert p["job"]["state"] == "done" and p["status"] == "PREVIEW"
    assert p["scenes"][1]["narration"].startswith("牠一跳") and p["scenes"][1]["camera_motion"] == "pan_left"
    # 核准 → final
    assert client.post(f"/api/projects/{pid}/final").status_code == 409
    assert client.post(f"/api/projects/{pid}/approve", json={"by": "tester"}).json()["status"] == "APPROVED"
    assert client.post(f"/api/projects/{pid}/final").status_code == 202
    p = client.get(f"/api/projects/{pid}").json()
    assert p["status"] == "FINAL" and p["final_url"]
    assert client.get(p["final_url"]).status_code == 200
    assert client.get("/api/projects").json()[0]["project_id"] == pid


def test_validation_and_404(client: TestClient):
    assert client.post("/api/projects", json={"text": ""}).status_code == 422
    assert client.post("/api/projects", json={"text": "故事", "aspect": "4:3"}).status_code == 422
    assert client.get("/api/projects/nope").status_code == 404
    assert client.get("/api/projects/../preview.mp4").status_code in (404, 422)
    r = client.post("/api/projects", json={"text": TINY_STORY})
    pid = r.json()["project_id"]
    assert client.post(f"/api/projects/{pid}/scenes/scene_999", json={"narration": "x"}).status_code == 404
    assert client.post(f"/api/projects/{pid}/scenes/scene_001", json={"camera_motion": "spin"}).status_code == 422


def test_regen_single_scene_via_api(client: TestClient, settings: Settings):
    pid = client.post("/api/projects", json={"text": TINY_STORY}).json()["project_id"]
    clip2 = Path(settings.workspace) / "projects" / pid / "scenes" / "scene_002" / "clip.mp4"
    before = clip2.read_bytes()
    assert client.post(f"/api/projects/{pid}/scenes/scene_001/regen").status_code == 202
    p = client.get(f"/api/projects/{pid}").json()
    assert p["job"]["state"] == "done"
    assert clip2.read_bytes() == before
