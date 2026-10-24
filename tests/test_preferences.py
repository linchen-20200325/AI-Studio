"""D-062 Preference Layer（非 UI 核心）：結構化偏好、Project→Scene override、再生成範圍、快照、舊資料相容。"""
from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from see.models.preferences import (GenerationSettings, MoodPref, PreferenceSet, PreferenceTerms, prompt_terms,
                                    regeneration_scope, resolve, snapshot)
from see.models.project import Project
from see.models.scene import Scene
from tests.conftest import TINY_STORY, requires_ffmpeg


def _planned(orch, pid):
    p = orch.create_project(TINY_STORY, project_id=pid)
    orch.write_script(p)
    orch.storyboard(p)
    return p


def test_preferences_hold_no_identity_fields():
    names = set(PreferenceSet.model_fields)
    assert not names & {"gender", "gender_presentation", "character_id", "reference", "reference_assets", "identity"}
    with pytest.raises(ValidationError):
        PreferenceSet(gender_presentation="male")  # 身份資料不得塞進偏好（extra 欄位 → 驗證失敗）


def test_resolve_project_then_scene_override_per_field():
    proj = PreferenceSet(mood=MoodPref(preset="warm", custom_en=["warm atmosphere"]),
                         lighting=PreferenceTerms(custom_en=["golden hour"]))
    scene = PreferenceSet(lighting=PreferenceTerms(custom_en=["moonlight"]), visual_style_id="anime")
    r = resolve("realistic", proj, scene)
    assert r["visual_style_id"] == "anime" and r["sources"]["visual_style_id"] == "scene"
    assert r["mood"]["custom_en"] == ["warm atmosphere"] and r["sources"]["mood"] == "project"
    assert r["lighting"]["custom_en"] == ["moonlight"] and r["sources"]["lighting"] == "scene"
    assert prompt_terms(r) == ["warm atmosphere", "moonlight"]
    assert resolve("default", None, None) == {"visual_style_id": "default", "sources": {"visual_style_id": "project.style_id"}}


def test_preset_without_custom_terms_is_reported_as_no_effect():
    r = resolve("default", PreferenceSet(mood=MoodPref(preset="horror")), None)
    assert prompt_terms(r) == [] and snapshot(r)["no_prompt_effect"] == ["mood"]  # missing ≠ success
    with pytest.raises(ValidationError):
        MoodPref(preset="angry")
    with pytest.raises(ValidationError):
        GenerationSettings(gen_policy="huge")


def test_snapshot_hash_is_stable_and_content_sensitive():
    a = snapshot(resolve("default", PreferenceSet(camera=PreferenceTerms(custom_en=["low angle"])), None))
    b = snapshot(resolve("default", PreferenceSet(camera=PreferenceTerms(custom_en=["low angle"])), None))
    c = snapshot(resolve("default", PreferenceSet(camera=PreferenceTerms(custom_en=["high angle"])), None))
    assert a["preference_sha256"] == b["preference_sha256"] != c["preference_sha256"]


def test_regeneration_scope_rules():
    img = regeneration_scope(["image_prompt_en"])
    assert img["affects_image"] and img["affects_video"] and not img["affects_narration_audio"]
    assert "narration" in img["unaffected"] and "subtitle" in img["unaffected"]
    nar = regeneration_scope(["narration"])
    assert nar["affects_narration_audio"] and not nar["affects_image"]
    assert regeneration_scope(["transition"])["assets"] == ["render"]
    assert regeneration_scope([])["assets"] == []
    with pytest.raises(ValueError):
        regeneration_scope(["status"])


def test_old_project_json_without_preferences_loads_unchanged(orchestrator):
    p = _planned(orchestrator, "pf0")
    raw = json.loads(p.model_dump_json())
    raw.pop("preferences")
    for s in raw["scenes"]:
        s.pop("preferences")
    old = Project.model_validate(raw)
    assert old.preferences is None and all(s.preferences is None for s in old.scenes)
    r1, _ = orchestrator.image_request(old, old.scenes[0])
    r2, _ = orchestrator.image_request(p, p.scenes[0])
    assert r1.model_dump() == r2.model_dump()  # 舊資料：request（＝image fingerprint 輸入）完全相同


def test_scene_override_changes_only_that_scene(orchestrator):
    p = _planned(orchestrator, "pf1")
    base = [orchestrator.image_request(p, s)[0].model_dump() for s in p.scenes]
    for s in p.scenes:
        s.status = "PREVIEW"
    out = orchestrator.set_preferences(p, PreferenceSet(color_tone=PreferenceTerms(custom_en=["teal and orange"]),
                                                        generation=GenerationSettings(gen_policy="native")),
                                       scene_id=p.scenes[0].scene_id)
    assert out["changed_scenes"] == [p.scenes[0].scene_id] and not out["affects_narration_audio"]
    r0, ctx = orchestrator.image_request(p, p.scenes[0])
    assert r0.prompt.endswith("teal and orange") and r0.params["gen_policy"] == "native"
    assert ctx["preference_snapshot"]["resolved"]["sources"]["color_tone"] == "scene"
    assert p.scenes[0].status == "DRAFT" and all(s.status == "PREVIEW" for s in p.scenes[1:])
    assert [orchestrator.image_request(p, s)[0].model_dump() for s in p.scenes[1:]] == base[1:]


def test_project_default_and_validation(orchestrator):
    p = _planned(orchestrator, "pf2")
    out = orchestrator.set_preferences(p, PreferenceSet(mood=MoodPref(custom_en=["melancholic"])))
    assert sorted(out["changed_scenes"]) == sorted(s.scene_id for s in p.scenes)
    assert all(orchestrator.image_request(p, s)[0].prompt.endswith("melancholic") for s in p.scenes)
    again = orchestrator.set_preferences(p, PreferenceSet(mood=MoodPref(custom_en=["melancholic"])))
    assert again["changed_scenes"] == []  # 沒有實際改變 → 不讓任何景失效
    with pytest.raises(ValueError):
        orchestrator.set_preferences(p, PreferenceSet(visual_style_id="anime"))  # project 風格唯一來源是 style_id
    with pytest.raises(ValueError):
        orchestrator.set_preferences(p, PreferenceSet(visual_style_id="nope"), scene_id=p.scenes[0].scene_id)
    cleared = orchestrator.set_preferences(p, PreferenceSet())  # 空集合＝清除
    assert p.preferences is None and cleared["changed_scenes"]


def test_edit_impact_counts_only_real_changes(orchestrator):
    p = _planned(orchestrator, "pf3")
    s = p.scenes[0]
    same = orchestrator.edit_impact(p, s.scene_id, image_prompt_en=s.image_prompt_en, narration=None)
    assert same["changed_fields"] == [] and same["assets"] == []
    imp = orchestrator.edit_impact(p, s.scene_id, image_prompt_en="a red kite over hills")
    assert imp["changed_fields"] == ["image_prompt_en"] and imp["affects_image"] and not imp["affects_narration_audio"]


@requires_ffmpeg
def test_preference_change_rebuilds_image_and_clip_but_not_narration(orchestrator):
    p = _planned(orchestrator, "pf4")
    orchestrator.build_scene_assets(p)
    orchestrator.set_preferences(p, PreferenceSet(lighting=PreferenceTerms(custom_en=["neon lights"])), scene_id=p.scenes[0].scene_id)
    reps = {r.scene_id: r for r in orchestrator.build_scene_assets(p)}
    first = reps[p.scenes[0].scene_id]
    assert "image" in first.rebuilt and "narration" in first.reused and "subtitle" in first.reused
    assert first.image_meta["preference_snapshot"]["resolved"]["lighting"]["custom_en"] == ["neon lights"]
    assert all("image" in r.reused and "narration" in r.reused for sid, r in reps.items() if sid != p.scenes[0].scene_id)


def test_scene_model_accepts_preferences_round_trip():
    s = Scene(scene_id="s1", index=0, duration=3, narration="n", visual_description="v", image_prompt="p",
              preferences=PreferenceSet(camera=PreferenceTerms(preset="close-up", custom_en=["close-up shot"])))
    assert Scene.model_validate_json(s.model_dump_json()).preferences.camera.custom_en == ["close-up shot"]
