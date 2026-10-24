"""D-063：中文圖片描述（image_prompt_zh）→ prompt builder、Scene Character Override、再生成範圍、舊資料相容。"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from see.core.scene_prompt import KeywordFallbackTranslator, base_prompt, character_terms, scene_prompt
from see.models.preferences import regeneration_scope
from see.models.scene import Scene
from see.models.scene_character import LABELS_ZH, PROMPT_EN, SceneCharacter
from tests.conftest import TINY_STORY, requires_ffmpeg

LEGACY = {"scene_id": "s1", "index": 0, "duration": 3, "narration": "n", "visual_description": "v",
          "image_prompt": "插畫風格，山", "image_prompt_en": "mountains, storybook"}


def _planned(orch, pid, cids=("hero", "heroine")):
    p = orch.create_project(TINY_STORY, project_id=pid)
    orch.write_script(p)
    orch.storyboard(p)
    orch.update_scene(p, p.scenes[0].scene_id, character_ids=list(cids))
    return p


def test_old_scene_loads_without_new_fields_and_prompt_is_unchanged():
    s = Scene.model_validate(LEGACY)  # 舊 JSON：沒有 image_prompt_zh／characters
    assert s.image_prompt_zh == "" and s.characters == []
    prompt, ev = scene_prompt(s)
    assert prompt == s.effective_image_prompt == "mountains, storybook"
    assert ev == {"prompt_source": {"source": "legacy_en", "translator": None, "ai_translated": False}, "scene_characters": []}
    s2 = Scene.model_validate({**LEGACY, "image_prompt_en": ""})
    assert base_prompt(s2)[1]["source"] == "legacy_image_prompt" and base_prompt(s2)[0] == "插畫風格，山"


def test_zh_description_is_generated_source_and_never_claims_ai():
    s = Scene.model_validate({**LEGACY, "image_prompt_zh": "森林裡的小狐狸抬頭看蝴蝶，黃昏，溫暖電影感。"})
    prompt, src = base_prompt(s)
    assert src["source"] == "zh_generated" and src["ai_translated"] is False and src["translator"] == "keyword_fallback_v1"
    assert "a forest" in prompt and "butterflies" in prompt and src["shadowed"] == ["image_prompt_en", "image_prompt"]
    _, none = base_prompt(Scene.model_validate({**LEGACY, "image_prompt_zh": "完全對不到的句子"}))
    assert none["generic_fallback"] is True and none["matched_terms"] == []  # 沒對到就照實標示


def test_scene_character_schema_fails_closed():
    ok = SceneCharacter(character_id="hero", expression={"preset": "custom", "custom_zh": "皺眉"})
    assert ok.expression.custom_zh == "皺眉"
    bad = [
        {"character_id": "hero", "expression": {"preset": "custom"}},  # 自訂沒填字
        {"character_id": "hero", "expression": {"preset": "smile", "custom_zh": "皺眉"}},  # preset 與自訂衝突
        {"character_id": "hero", "gaze": {"preset": "at_camera", "target_character_id": "heroine"}},
        {"character_id": "hero", "gender": "male"},  # 身份欄位不得混入本幕覆寫
        {"character_id": "hero", "placement": "top"},
    ]
    for b in bad:
        with pytest.raises(ValidationError):
            SceneCharacter.model_validate(b)
    with pytest.raises(ValidationError):  # 覆寫必須是本幕出場角色
        Scene.model_validate({**LEGACY, "character_ids": ["hero"], "characters": [{"character_id": "villain"}]})
    with pytest.raises(ValidationError):  # 重複
        Scene.model_validate({**LEGACY, "character_ids": ["hero"], "characters": [{"character_id": "hero"}, {"character_id": "hero"}]})
    with pytest.raises(ValidationError):  # 視線對象不在本幕
        Scene.model_validate({**LEGACY, "character_ids": ["hero"],
                              "characters": [{"character_id": "hero", "gaze": {"preset": "at_character", "target_character_id": "x"}}]})


def test_every_preset_has_zh_label_and_prompt_term():
    for f, labels in LABELS_ZH.items():
        assert set(labels) - {"custom"} == set(PROMPT_EN[f]), f


def test_character_terms_order_and_honest_no_effect():
    sc = SceneCharacter(character_id="hero", placement="left", depth="foreground", expression={"preset": "serious"},
                        emotion={"preset": "nervous"}, action={"preset": "clenching_fist"},
                        gaze={"preset": "at_character", "target_character_id": "heroine"}, pose={"preset": "side"},
                        outfit_override="雨中的西裝", notes="不進 prompt", raw_character_direction_zh="男主角站在左側，表情緊張")
    terms, ev = character_terms(sc, KeywordFallbackTranslator())
    assert terms[:7] == ["on the left side of the frame", "in the foreground", "serious expression", "nervous", "clenched fist",
                         "looking at the other character", "side view"]
    assert ev["raw_direction_saved"] is True and ev["raw_direction_applied"] is False
    assert "不進 prompt" not in " ".join(terms) and "hero" not in " ".join(terms)  # 不洩漏內部 id／備註
    # 「西裝」不在關鍵詞表 → 只有「雨」轉得到；完全轉不到的自訂表情 → no_prompt_effect
    sc2 = SceneCharacter(character_id="hero", expression={"preset": "custom", "custom_zh": "皺眉"})
    t2, ev2 = character_terms(sc2)
    assert t2 == [] and ev2["no_prompt_effect"] == ["expression"] and ev2["applied_fields"] == []


def test_override_reaches_prompt_and_evidence_but_not_character_defaults(orchestrator):
    p = _planned(orchestrator, "sc1")
    s = p.scenes[0]
    chars_before = {k: v.model_dump() for k, v in p.characters.items()}
    script_before = p.script.model_dump() if p.script else None
    orchestrator.update_scene(p, s.scene_id, characters=[{"character_id": "hero", "expression": {"preset": "smile"},
                                                          "outfit_override": "雨衣", "placement": "left"}])
    s = p.scene(s.scene_id)
    req, ctx = orchestrator.image_request(p, s)
    assert req.prompt.startswith(s.image_prompt_en) and "smiling" in req.prompt and "on the left side of the frame" in req.prompt
    assert ctx["scene_characters"][0]["applied_fields"] == ["placement", "expression", "outfit_override"]
    assert ctx["prompt_source"]["source"] == "legacy_en"
    # 本幕服裝不寫回角色永久設定
    assert {k: v.model_dump() for k, v in p.characters.items()} == chars_before
    assert (p.script.model_dump() if p.script else None) == script_before
    assert orchestrator.store.load(p.project_id).scene(s.scene_id).characters[0].outfit_override == "雨衣"
    with pytest.raises(ValueError):
        orchestrator.update_scene(p, s.scene_id, characters=[{"character_id": "villain"}])


def test_edit_impact_for_character_fields_and_shadowed_legacy(orchestrator):
    p = _planned(orchestrator, "sc2")
    sid = p.scenes[0].scene_id
    imp = orchestrator.edit_impact(p, sid, characters=[{"character_id": "hero", "gaze": {"preset": "at_camera"}}])
    assert imp["changed_fields"] == ["characters.gaze"] and imp["affects_image"] and imp["affects_video"]
    assert not imp["affects_narration_audio"] and "narration" in imp["unaffected"] and "subtitle" in imp["unaffected"]
    inert = orchestrator.edit_impact(p, sid, characters=[{"character_id": "hero", "notes": "備註", "raw_character_direction_zh": "緊張"}])
    assert inert["changed_fields"] == ["characters.notes", "characters.raw_character_direction_zh"] and inert["assets"] == []
    zh = orchestrator.edit_impact(p, sid, image_prompt_zh="森林")
    assert zh["changed_fields"] == ["image_prompt_zh"] and zh["affects_image"] and not zh["affects_narration_audio"]
    orchestrator.update_scene(p, sid, image_prompt_zh="森林")
    shadow = orchestrator.edit_impact(p, sid, image_prompt_en="a red kite")  # 中文描述為準 → 英文 legacy 改了不影響
    assert shadow["shadowed_fields"] == ["image_prompt_en"] and shadow["assets"] == []
    with pytest.raises(ValueError):
        orchestrator.edit_impact(p, sid, characters=[{"character_id": "villain"}])
    for f in ("expression", "action", "gaze", "pose", "outfit_override", "placement", "depth"):
        r = regeneration_scope([f"characters.{f}"])
        assert r["affects_image"] and not r["affects_narration_audio"] and "subtitle" in r["unaffected"]


@requires_ffmpeg
def test_expression_change_rebuilds_image_and_clip_only(orchestrator):
    p = _planned(orchestrator, "sc3")
    orchestrator.build_scene_assets(p)
    sid = p.scenes[0].scene_id
    orchestrator.update_scene(p, sid, characters=[{"character_id": "hero", "expression": {"preset": "afraid"}}])
    reps = {r.scene_id: r for r in orchestrator.build_scene_assets(p)}
    first = reps[sid]
    assert "image" in first.rebuilt and "clip" in first.rebuilt
    assert "narration" in first.reused and "subtitle" in first.reused
    assert first.image_meta["scene_characters"][0]["applied_fields"] == ["expression"]
    assert all("image" in r.reused and "narration" in r.reused for k, r in reps.items() if k != sid)
    # 只改備註／中文原話 → 不重做任何產物
    orchestrator.update_scene(p, sid, characters=[{"character_id": "hero", "expression": {"preset": "afraid"}, "notes": "n"}])
    again = {r.scene_id: r for r in orchestrator.build_scene_assets(p)}[sid]
    assert again.rebuilt == []
