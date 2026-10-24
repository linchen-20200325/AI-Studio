"""D-065 Scene 結構化設定：schema、None 不補值、中文自訂、確定性對照、no_prompt_effect、再生成範圍、與角色覆寫分離、舊資料相容。"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from see.core.scene_prompt import settings_terms
from see.models.preferences import PreferenceSet, PreferenceTerms, regeneration_scope
from see.models.scene import Scene
from see.models.scene_settings import FIELDS, LABELS_ZH, PRESETS, SceneSettings
from tests.conftest import TINY_STORY, requires_ffmpeg

LEGACY = {"scene_id": "s1", "index": 0, "duration": 3, "narration": "n", "visual_description": "v",
          "image_prompt": "插畫風格，山", "image_prompt_en": "mountains, storybook"}


def _planned(orch, pid):
    p = orch.create_project(TINY_STORY, project_id=pid)
    orch.write_script(p)
    orch.storyboard(p)
    return p


def test_schema_fields_labels_and_none_is_not_filled():
    assert set(FIELDS) == {"background", "environment", "location", "time_of_day", "weather", "composition", "framing", "shot_size",
                           "camera_angle", "focus_target", "lighting", "color_tone", "mood"}
    assert set(LABELS_ZH) == set(FIELDS) and LABELS_ZH["shot_size"] == "景別" and LABELS_ZH["camera_angle"] == "鏡頭角度"
    s = SceneSettings(weather={"preset": "rain"})
    assert s.set_fields() == ["weather"] and all(getattr(s, f) is None for f in FIELDS if f != "weather")  # 其他欄位不補值
    sc = Scene.model_validate({**LEGACY, "settings": {}})
    assert sc.settings is None  # 空設定＝未指定
    assert Scene.model_validate({**LEGACY, "settings": {"weather": {"preset": None, "custom_zh": ""}}}).settings is None


def test_chinese_custom_values_persist_and_invalid_fail_closed():
    s = Scene.model_validate({**LEGACY, "settings": {"background": {"custom_zh": "下雨的老街"}, "time_of_day": {"preset": "dusk"}}})
    again = Scene.model_validate_json(s.model_dump_json())
    assert again.settings.background.preset == "custom" and again.settings.background.custom_zh == "下雨的老街"
    assert again.settings.time_of_day.preset == "dusk"
    for bad in ({"weather": {"preset": "hail"}},  # 未知 preset
                {"weather": {"preset": "rain", "custom_zh": "大雨"}},  # preset 與自訂衝突
                {"background": {"preset": "forest"}},  # background 只收自訂中文
                {"weather": {"preset": "custom"}},  # 自訂沒填字
                {"expression": {"preset": "smile"}},  # 角色欄位不得混入 Scene 設定
                {"camera_movement": {"preset": "zoom_in"}}):  # 鏡頭運動的單一來源是 Scene.camera_motion
        with pytest.raises(ValidationError):
            SceneSettings.model_validate(bad)


def test_deterministic_mapping_and_no_prompt_effect():
    st = SceneSettings(background={"custom_zh": "森林"}, time_of_day={"preset": "night"}, weather={"preset": "rain"},
                       lighting={"preset": "neon"}, shot_size={"preset": "close_up"}, focus_target={"custom_zh": "小貓"},
                       mood={"custom_zh": "完全對不到的感覺"})
    terms, ev = settings_terms(st)
    assert terms == ["a forest", "night", "rainy", "neon lighting", "close-up shot", "focus on a kitten"]
    assert ev["applied_fields"] == ["background", "time_of_day", "weather", "lighting", "shot_size", "focus_target"]
    assert ev["no_prompt_effect"] == ["mood"] and ev["ai_translated"] is False and ev["source"] == "structured"
    assert ev["overrides_preference_dims"] == ["camera", "lighting"]
    assert settings_terms(st)[0] == terms  # 確定性
    for f, presets in PRESETS.items():  # 每個 preset 都有中文標籤與英文詞
        assert all(zh and en for zh, en in presets.values()), f


def test_old_scene_prompt_unchanged_and_marked_legacy(orchestrator):
    p = _planned(orchestrator, "ss0")
    s = p.scenes[0]
    req, ctx = orchestrator.image_request(p, s)
    assert req.prompt == s.effective_image_prompt and ctx["scene_settings"]["source"] == "legacy_none"
    assert "settings" not in s.model_dump(exclude_none=True)


def test_prompt_wiring_and_preference_override(orchestrator):
    p = _planned(orchestrator, "ss1")
    sid = p.scenes[0].scene_id
    orchestrator.set_preferences(p, PreferenceSet(lighting=PreferenceTerms(custom_en=["moonlight"]),
                                                  color_tone=PreferenceTerms(custom_en=["sepia"])))
    orchestrator.update_scene(p, sid, settings={"weather": {"preset": "snow"}, "lighting": {"preset": "candlelight"}})
    req, ctx = orchestrator.image_request(p, p.scene(sid))
    assert "snowy" in req.prompt and "candlelight" in req.prompt
    assert "moonlight" not in req.prompt and "sepia" in req.prompt  # Scene 結構化光線取代 Project 偏好光線；色調沒指定 → 沿用偏好
    other = orchestrator.image_request(p, p.scenes[1])[0]
    assert "moonlight" in other.prompt and "snowy" not in other.prompt  # 只影響本景
    with pytest.raises(ValueError):
        orchestrator.update_scene(p, sid, preferences={"visual_style_id": "vaporwave"})  # 未知風格 fail closed
    orchestrator.update_scene(p, sid, preferences={"visual_style_id": "anime"})
    assert orchestrator.image_request(p, p.scene(sid))[1]["style_id"] == "anime"


def test_regeneration_scope_for_settings_and_camera_motion(orchestrator):
    p = _planned(orchestrator, "ss2")
    sid = p.scenes[0].scene_id
    for f in FIELDS:
        r = regeneration_scope([f"settings.{f}"])
        assert r["affects_image"] and r["affects_video"] and not r["affects_narration_audio"] and "subtitle" in r["unaffected"]
    imp = orchestrator.edit_impact(p, sid, settings={"weather": {"preset": "fog"}})
    assert imp["changed_fields"] == ["settings.weather"] and imp["assets"][:2] == ["image", "clip"] and "narration" in imp["unaffected"]
    cam = orchestrator.edit_impact(p, sid, camera_motion="zoom_out" if p.scenes[0].camera_motion.value != "zoom_out" else "pan_left")
    assert cam["assets"] == ["clip", "lipsync", "render"] and not cam["affects_image"] and not cam["affects_narration_audio"]
    assert orchestrator.edit_impact(p, sid, settings={})["changed_fields"] == []  # 空＝不變
    orchestrator.update_scene(p, sid, settings={"weather": {"preset": "fog"}, "mood": {"preset": "sad"}})
    only = orchestrator.edit_impact(p, sid, settings={"weather": {"preset": "fog"}, "mood": {"preset": "romantic"}})
    assert only["changed_fields"] == ["settings.mood"]


def test_settings_and_character_overrides_do_not_overwrite_each_other(orchestrator):
    p = _planned(orchestrator, "ss3")
    sid = p.scenes[0].scene_id
    orchestrator.update_scene(p, sid, character_ids=["hero"])
    orchestrator.update_scene(p, sid, characters=[{"character_id": "hero", "expression": {"preset": "smile"}, "outfit_override": "雨衣"}])
    chars_before = {k: v.model_dump() for k, v in p.characters.items()}
    orchestrator.update_scene(p, sid, settings={"weather": {"preset": "rain"}, "shot_size": {"preset": "wide"}})
    sc = p.scene(sid)
    assert sc.characters[0].expression.preset.value == "smile" and sc.characters[0].outfit_override == "雨衣"
    assert {k: v.model_dump() for k, v in p.characters.items()} == chars_before
    orchestrator.update_scene(p, sid, characters=[{"character_id": "hero", "expression": {"preset": "sad"}}])
    assert p.scene(sid).settings.weather.preset == "rain"  # 改角色不動 Scene 設定
    req, ctx = orchestrator.image_request(p, p.scene(sid))
    assert ctx["scene_settings"]["applied_fields"] == ["weather", "shot_size"] and ctx["scene_characters"][0]["applied_fields"] == ["expression"]


def test_settings_do_not_touch_character_definition_store(orchestrator):
    from see.models.character_definition import CharacterDefinition
    from see.storage.character_store import CharacterStore

    store = CharacterStore(orchestrator.settings.workspace)
    store.create(CharacterDefinition(character_id="char_001", display_name="男主角", outfit="灰西裝"))
    before = store.get("char_001")
    p = _planned(orchestrator, "ss4")
    orchestrator.update_scene(p, p.scenes[0].scene_id, settings={"lighting": {"preset": "dim"}})
    after = store.get("char_001")
    assert after == before and after.revision == 1


@requires_ffmpeg
def test_weather_change_rebuilds_image_and_clip_only_camera_motion_only_clip(orchestrator):
    p = _planned(orchestrator, "ss5")
    orchestrator.build_scene_assets(p)
    sid = p.scenes[0].scene_id
    orchestrator.update_scene(p, sid, settings={"weather": {"preset": "rain"}})
    first = {r.scene_id: r for r in orchestrator.build_scene_assets(p)}[sid]
    assert "image" in first.rebuilt and "clip" in first.rebuilt and "narration" in first.reused and "subtitle" in first.reused
    assert first.image_meta["scene_settings"]["applied_fields"] == ["weather"]
    new_motion = "pan_up" if p.scene(sid).camera_motion.value != "pan_up" else "pan_down"
    orchestrator.update_scene(p, sid, camera_motion=new_motion)
    cam = {r.scene_id: r for r in orchestrator.build_scene_assets(p)}[sid]
    assert cam.rebuilt == ["clip"] and {"image", "narration", "subtitle"} <= set(cam.reused)


def test_non_default_style_leaves_no_empty_prompt_terms(orchestrator):
    """legacy 畫風詞在 prompt 中間（後面接場景／人物詞）時，換風格不得留下空項（", ,"）。"""
    p = _planned(orchestrator, "ss6")
    sid = p.scenes[0].scene_id
    orchestrator.update_scene(p, sid, settings={"weather": {"preset": "rain"}}, preferences={"visual_style_id": "anime"})
    prompt = orchestrator.image_request(p, p.scene(sid))[0].prompt
    assert ", ," not in prompt and ",," not in prompt and "rainy" in prompt and "watercolor" not in prompt
