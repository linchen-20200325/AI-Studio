"""端到端 + 增量重算測試（需要 ffmpeg；使用 SilentTTS 保證離線確定性）。"""

from pathlib import Path

import pytest

from see.core.errors import InvalidTransition
from see.core.ffmpeg import FFmpeg
from see.core.hashing import file_sha256
from see.models import JobKind, JobStatus, Status
from tests.conftest import TINY_STORY, requires_ffmpeg

pytestmark = [requires_ffmpeg, pytest.mark.e2e]


def _scene_hashes(orch, pid: str) -> dict[str, dict[str, str]]:
    out = {}
    for sid in [s.scene_id for s in orch.store.load(pid).scenes]:
        d = orch.store.scene_dir(pid, sid)
        out[sid] = {f.name: file_sha256(f) for f in d.iterdir() if f.suffix in (".png", ".wav", ".srt", ".mp4")}
    return out


def test_full_run_produces_playable_preview(orchestrator):
    rep = orchestrator.run(TINY_STORY, project_id="t1")
    out = rep.output_path
    assert out.exists() and out.name == "preview.mp4"
    info = FFmpeg().probe(out)
    assert info.has_video and info.has_audio
    assert info.width == 640 and info.height == 360
    assert abs(info.duration - rep.timeline.total_duration) < 1.0
    assert rep.project.status == Status.PREVIEW
    assert all(s.status == Status.PREVIEW for s in rep.project.scenes)
    assert rep.job.status == JobStatus.DONE and rep.job.estimated_cost == 0 and rep.job.actual_cost == 0
    assert (orchestrator.store.renders_dir("t1") / "preview.json").exists()
    assert (orchestrator.store.renders_dir("t1") / "preview.srt").read_text(encoding="utf-8").count("-->") >= 3
    # 每景 clip 時長 ≥ 旁白長度 + pad
    for s in rep.project.scenes:
        assert s.measured_narration_duration is not None
        assert s.duration >= s.measured_narration_duration + orchestrator.settings.narration_pad - 0.01


def test_second_rebuild_reuses_everything(orchestrator, providers):
    orchestrator.run(TINY_STORY, project_id="t2")
    before = _scene_hashes(orchestrator, "t2")
    calls = (providers.image.calls, providers.tts.calls, providers.video.calls)
    rep = orchestrator.rebuild(orchestrator.store.load("t2"))
    assert all(r.rebuilt == [] for r in rep.scene_reports)
    assert _scene_hashes(orchestrator, "t2") == before
    assert (providers.image.calls, providers.tts.calls, providers.video.calls) == calls


def test_editing_one_scene_does_not_touch_others(orchestrator, providers):
    rep = orchestrator.run(TINY_STORY, project_id="t3")
    assert len(rep.project.scenes) >= 3
    before = _scene_hashes(orchestrator, "t3")
    project = orchestrator.store.load("t3")
    target = project.scenes[1].scene_id
    orchestrator.update_scene(project, target, narration="牠一跳，就跳上了最高的那顆石頭。")
    assert project.status == Status.DRAFT
    v_calls = providers.video.calls
    rep2 = orchestrator.rebuild(project)
    after = _scene_hashes(orchestrator, "t3")
    for r in rep2.scene_reports:
        if r.scene_id == target:
            assert "narration" in r.rebuilt and "clip" in r.rebuilt and "image" in r.reused
        else:
            assert r.rebuilt == [], f"{r.scene_id} was rebuilt: {r.rebuilt}"
    for sid in before:
        if sid != target:
            assert after[sid] == before[sid], f"{sid} files changed"
    assert after[target]["clip.mp4"] != before[target]["clip.mp4"]
    assert providers.video.calls == v_calls + 1
    assert rep2.output_path.exists()


def test_subtitle_override_only_rebuilds_subtitle_and_clip(orchestrator):
    orchestrator.run(TINY_STORY, project_id="t4")
    project = orchestrator.store.load("t4")
    sid = project.scenes[0].scene_id
    orchestrator.update_scene(project, sid, subtitle_override="（字幕覆寫）")
    rep = orchestrator.build_scene_assets(project, [sid])
    assert rep[0].rebuilt == ["subtitle", "clip"] and set(rep[0].reused) == {"image", "narration"}
    srt = (orchestrator.store.scene_dir("t4", sid) / "subtitles.srt").read_text(encoding="utf-8")
    assert "字幕覆寫" in srt


def test_regenerate_single_scene(orchestrator):
    orchestrator.run(TINY_STORY, project_id="t5")
    before = _scene_hashes(orchestrator, "t5")
    project = orchestrator.store.load("t5")
    r = orchestrator.regenerate_scene(project, "scene_001")
    assert set(r.rebuilt) == {"image", "narration", "subtitle", "clip"}
    after = _scene_hashes(orchestrator, "t5")
    assert after["scene_002"] == before["scene_002"]


def test_human_approval_gate_and_final_render(orchestrator):
    rep = orchestrator.run(TINY_STORY, project_id="t6")
    project = rep.project
    with pytest.raises(InvalidTransition):
        orchestrator.render(project, JobKind.FINAL)  # PREVIEW ≠ FINAL
    orchestrator.approve(project, approved_by="tester")
    assert project.status == Status.APPROVED and project.approvals[-1].approved_by == "tester"
    job, _ = orchestrator.render(project, JobKind.FINAL)
    assert job.kind == JobKind.FINAL and Path(job.output_path).name == "final.mp4" and Path(job.output_path).exists()
    assert project.status == Status.FINAL
    # 修改後核准失效
    orchestrator.update_scene(project, "scene_001", narration="改了。")
    assert project.status == Status.DRAFT
    with pytest.raises(InvalidTransition):
        orchestrator.approve(project)


def test_update_scene_rejects_unknown_fields(orchestrator):
    rep = orchestrator.run(TINY_STORY, project_id="t7")
    with pytest.raises(ValueError):
        orchestrator.update_scene(rep.project, "scene_001", status=Status.FINAL)
