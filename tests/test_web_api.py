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
    assert "建立預覽影片" in client.get("/").text  # D-063 一般 UI 全中文
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


def test_scene_image_prompt_en_edit_rebuilds_only_visual_assets(client: TestClient, settings: Settings):
    """D-062 Batch B：Scene 卡改英文圖片描述 → 只重做 image＋clip（旁白／字幕沿用快取）；impact 端點不寫入。"""
    from see.storage.project_store import ProjectStore

    pid = client.post("/api/projects", json={"text": TINY_STORY}).json()["project_id"]
    p = client.get(f"/api/projects/{pid}").json()
    s = p["scenes"][0]
    sid = s["scene_id"]
    assert "image_prompt_en" in s and "video_prompt" in s and "visual_description" in s
    store = ProjectStore(settings.workspace)
    before = {k: v.fingerprint for k, v in store.load_manifest(pid, sid).entries.items()}
    other = p["scenes"][1]["scene_id"]
    other_before = {k: v.fingerprint for k, v in store.load_manifest(pid, other).entries.items()}
    imp = client.post(f"/api/projects/{pid}/scenes/{sid}/impact", json={"image_prompt_en": "a red kite over green hills"}).json()
    assert imp["changed_fields"] == ["image_prompt_en"] and imp["affects_image"] and not imp["affects_narration_audio"]
    assert client.get(f"/api/projects/{pid}").json()["scenes"][0]["image_prompt_en"] == s["image_prompt_en"]  # 未寫入
    r = client.post(f"/api/projects/{pid}/scenes/{sid}", json={"image_prompt_en": "a red kite over green hills"})
    assert r.status_code == 202 and r.json()["impact"]["assets"][:2] == ["image", "clip"]
    p2 = client.get(f"/api/projects/{pid}").json()
    assert p2["job"]["state"] == "done" and p2["scenes"][0]["image_prompt_en"] == "a red kite over green hills"
    after = {k: v.fingerprint for k, v in store.load_manifest(pid, sid).entries.items()}
    assert after["image"] != before["image"] and after["clip"] != before["clip"]
    assert after["narration"] == before["narration"] and after["subtitle"] == before["subtitle"]
    # 其他景完全沒動
    assert {k: v.fingerprint for k, v in store.load_manifest(pid, other).entries.items()} == other_before
    # video_prompt 只影響 clip；visual_description 不可為空
    assert client.post(f"/api/projects/{pid}/scenes/{other}/impact", json={"video_prompt": "slow push in"}).json()["assets"][:1] == ["clip"]
    assert client.post(f"/api/projects/{pid}/scenes/{sid}", json={"visual_description": ""}).status_code == 422


def test_scene_zh_description_and_character_override_via_api(client: TestClient, settings: Settings):
    """D-063：一般 UI 只送中文圖片描述＋本幕人物覆寫；英文 prompt 只在 advanced（只讀）；只重做 image＋clip。"""
    from see.storage.project_store import ProjectStore

    pid = client.post("/api/projects", json={"text": TINY_STORY}).json()["project_id"]
    s = client.get(f"/api/projects/{pid}").json()["scenes"][0]
    sid = s["scene_id"]
    assert s["image_prompt_zh"] == "" and s["characters"] == [] and s["advanced"]["prompt_source"]["source"] == "legacy_en"
    opts = client.get("/api/options").json()
    assert opts["scene_character"]["expression"]["smile"] == "微笑" and opts["camera_motion_labels"]["static"] == "固定"
    store = ProjectStore(settings.workspace)
    before = {k: v.fingerprint for k, v in store.load_manifest(pid, sid).entries.items()}
    r = client.post(f"/api/projects/{pid}/scenes/{sid}", json={"image_prompt_zh": "森林裡的小貓，夜晚"})
    assert r.status_code == 202 and r.json()["impact"]["changed_fields"] == ["image_prompt_zh"]
    s2 = client.get(f"/api/projects/{pid}").json()["scenes"][0]
    adv = s2["advanced"]
    assert s2["image_prompt_zh"] == "森林裡的小貓，夜晚" and s2["image_prompt_en"] == s["image_prompt_en"]  # legacy 欄位保留不刪
    assert adv["prompt_source"]["source"] == "zh_generated" and adv["prompt_source"]["ai_translated"] is False
    assert "a forest" in adv["model_prompt_en"] and "a kitten" in adv["model_prompt_en"]
    after = {k: v.fingerprint for k, v in store.load_manifest(pid, sid).entries.items()}
    assert after["image"] != before["image"] and after["narration"] == before["narration"] and after["subtitle"] == before["subtitle"]
    # 人物覆寫：不在本幕的角色 → 422（fail closed）；角色加入本幕後可設定，標籤不顯示內部 id
    bad = client.post(f"/api/projects/{pid}/scenes/{sid}/impact", json={"characters": [{"character_id": "ghost"}]})
    assert bad.status_code == 422
    client.post(f"/api/projects/{pid}/scenes/{sid}", json={"character_ids": ["hero"]})
    s3 = client.get(f"/api/projects/{pid}").json()["scenes"][0]
    assert s3["character_slots"] == [{"character_id": "hero", "label": "角色 1"}]
    imp = client.post(f"/api/projects/{pid}/scenes/{sid}/impact",
                      json={"characters": [{"character_id": "hero", "expression": {"preset": "sad"}, "placement": "right"}]}).json()
    assert imp["changed_fields"] == ["characters.expression", "characters.placement"] and not imp["affects_narration_audio"]


def test_scene_structured_settings_via_api(client: TestClient, settings: Settings):
    """D-065：Scene 結構化設定（中文自訂＋固定選項）存檔、只重做 image＋clip；視覺風格走 Scene preferences。"""
    from see.storage.project_store import ProjectStore

    pid = client.post("/api/projects", json={"text": TINY_STORY}).json()["project_id"]
    s = client.get(f"/api/projects/{pid}").json()["scenes"][0]
    sid = s["scene_id"]
    assert s["settings"] == {} and s["advanced"]["scene_settings"]["source"] == "legacy_none"
    o = client.get("/api/options").json()
    assert o["scene_settings"]["labels"]["weather"] == "天氣" and o["scene_settings"]["presets"]["weather"]["rain"] == "下雨"
    assert o["styles"]["anime"] == "日系動畫"
    store = ProjectStore(settings.workspace)
    before = {k: v.fingerprint for k, v in store.load_manifest(pid, sid).entries.items()}
    body = {"settings": {"background": {"custom_zh": "森林"}, "weather": {"preset": "rain"}}, "preferences": {"visual_style_id": "anime"}}
    imp = client.post(f"/api/projects/{pid}/scenes/{sid}/impact", json=body).json()
    assert imp["changed_fields"] == ["preferences", "settings.background", "settings.weather"] and not imp["affects_narration_audio"]
    assert client.post(f"/api/projects/{pid}/scenes/{sid}", json=body).status_code == 202
    s2 = client.get(f"/api/projects/{pid}").json()["scenes"][0]
    assert s2["settings"]["background"] == {"preset": "custom", "custom_zh": "森林"} and s2["preferences"]["visual_style_id"] == "anime"
    assert s2["advanced"]["scene_settings"]["applied_fields"] == ["background", "weather"]
    after = {k: v.fingerprint for k, v in store.load_manifest(pid, sid).entries.items()}
    assert after["image"] != before["image"] and after["narration"] == before["narration"] and after["subtitle"] == before["subtitle"]
    bad = client.post(f"/api/projects/{pid}/scenes/{sid}/impact", json={"settings": {"weather": {"preset": "hail"}}})
    assert bad.status_code == 422
