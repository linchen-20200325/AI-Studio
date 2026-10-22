import pytest
from pydantic import ValidationError

from see.models import Project, Scene, SceneDraft, Script, StoryboardDraft, Beat, Status, Transition


def _draft(i: int) -> SceneDraft:
    return SceneDraft(index=i, duration=4, narration=f"旁白{i}", visual_description="v", image_prompt="p")


def test_scene_requires_positive_duration():
    with pytest.raises(ValidationError):
        SceneDraft(index=0, duration=0, narration="x", visual_description="v", image_prompt="p")


def test_scene_rejects_empty_narration():
    with pytest.raises(ValidationError):
        SceneDraft(index=0, duration=1, narration="", visual_description="v", image_prompt="p")


def test_storyboard_indices_must_be_contiguous():
    with pytest.raises(ValidationError):
        StoryboardDraft(scenes=[_draft(0), _draft(2)])
    StoryboardDraft(scenes=[_draft(0), _draft(1)])


def test_scene_from_draft_and_subtitle_override():
    s = Scene.from_draft(_draft(0), "scene_001")
    assert s.status == Status.DRAFT and s.subtitle_text == "旁白0"
    s.subtitle_override = "字幕"
    assert s.subtitle_text == "字幕"
    assert s.transition == Transition.FADE


def test_script_needs_a_beat():
    with pytest.raises(ValidationError):
        Script(title="t", beats=[])
    Script(title="t", beats=[Beat(index=0, narration="a")])


def test_project_defaults_budget_zero_and_draft():
    p = Project(project_id="p", input_text="故事")
    assert p.budget == 0 and p.status == Status.DRAFT
    with pytest.raises(ValidationError):
        Project(project_id="p", input_text="x", budget=-1)


def test_project_roundtrip_json():
    p = Project(project_id="p", input_text="故事", scenes=[Scene.from_draft(_draft(0), "scene_001")])
    q = Project.model_validate_json(p.model_dump_json())
    assert q == p
