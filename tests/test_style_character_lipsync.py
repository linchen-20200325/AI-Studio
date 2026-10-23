"""Style Profile／Character Consistency／Lip-sync foundation（D-032）：相容性、套用、fail-closed、fallback。"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from see.core.errors import PaidProviderNotApproved, ProviderError, SchemaViolation
from see.core.prompting import _STYLE as LEGACY
from see.core.styles import BUILTIN_STYLES, apply_style, get_style
from see.models import CostTier
from see.models.project import CharacterAppearance
from see.models.provider import ProviderInfo
from see.providers.base import LipSyncProvider, LipSyncResult
from see.providers.lipsync.null import NullLipSyncProvider
from see.ui.server import create_app
from tests.conftest import TINY_STORY, requires_ffmpeg


def _planned(orch, pid):
    p = orch.create_project(TINY_STORY, project_id=pid)
    orch.write_script(p)
    orch.storyboard(p)
    return p


# ---------------------------------------------------------------- style
def test_default_style_is_noop_and_others_replace_legacy_suffix():
    d = get_style("default")
    assert d.validated and apply_style(f"a kitten, {LEGACY}", "lowres", d) == (f"a kitten, {LEGACY}", "lowres", {})
    for sid, st in BUILTIN_STYLES.items():
        assert st.style_id == sid
        if sid == "default":
            continue
        assert not st.validated  # 只有 default 有真機證據
        p, n, params = apply_style(f"a kitten, {LEGACY}", "lowres", st, "diffusers-sd15")
        assert LEGACY not in p and p.startswith("a kitten") and st.positive_terms[0] in p
        assert n.startswith("lowres") and params["style_id"] == sid
    with pytest.raises(ValueError):
        get_style("vaporwave")


def test_old_projects_keep_image_request_identical(orchestrator):
    p = _planned(orchestrator, "st0")
    req, ctx = orchestrator.image_request(p, p.scenes[0])
    s = p.scenes[0]
    assert req.prompt == s.effective_image_prompt and req.negative_prompt == s.negative_prompt and req.params == {}
    assert ctx == {"style_id": "default", "style_validated": True, "character_anchors": []}


def test_style_change_changes_only_images(orchestrator):
    p = _planned(orchestrator, "st1")
    orchestrator.set_style(p, "anime")
    req, ctx = orchestrator.image_request(p, p.scenes[0])
    assert "anime style" in req.prompt and req.params["style"]["style_id"] == "anime" and ctx["style_validated"] is False
    assert all(sc.status == "DRAFT" for sc in p.scenes)
    with pytest.raises(ValueError):
        orchestrator.set_style(p, "nope")
    p.style_id = "nope"  # 壞資料 → build 時 fail-closed
    with pytest.raises(SchemaViolation):
        orchestrator.image_request(p, p.scenes[0])


# ---------------------------------------------------------------- character consistency
def test_character_anchor_applies_only_to_scenes_with_that_character(orchestrator):
    p = _planned(orchestrator, "ch1")
    cid = "hero"
    orchestrator.set_character(p, cid, voice_id="zm_010")
    orchestrator.confirm_character(p, cid)
    orchestrator.update_scene(p, p.scenes[0].scene_id, character_ids=[cid])
    app = CharacterAppearance(description_en="a young monk boy with a shaved head", outfit_en="orange robe", features_en=["round face"])
    ch = orchestrator.set_character_appearance(p, cid, app)
    assert ch.confirmed  # 外觀不影響 voice 確認
    req0, ctx0 = orchestrator.image_request(p, p.scenes[0])
    assert req0.prompt.startswith("a young monk boy with a shaved head, wearing orange robe, round face")
    assert req0.params["characters"][0]["character_id"] == cid and ctx0["character_anchors"] == [cid]
    req1, _ = orchestrator.image_request(p, p.scenes[1])
    assert req1.params == {} and "monk" not in req1.prompt  # 沒出現的景不受影響
    assert orchestrator.set_character_appearance(p, cid, None).appearance is None
    assert orchestrator.image_request(p, p.scenes[0])[0].params == {}


def test_script_character_ids_without_profile_are_ignored(orchestrator):
    p = _planned(orchestrator, "ch2")
    sc = next((s for s in p.scenes if s.character_ids), None)
    if sc is not None:  # mock 會帶 char_01 之類 id；沒有 Project.characters 設定 → 不加錨點
        assert orchestrator.image_request(p, sc)[0].params == {}


# ---------------------------------------------------------------- lip-sync
class CopyLipSync(LipSyncProvider):
    """測試用：把 clip 複製一份當作「已同步」結果。"""

    accepts_image_input = True

    def __init__(self, fail: bool = False, applied: bool = True) -> None:
        self.fail, self.applied, self.calls = fail, applied, 0

    @property
    def info(self) -> ProviderInfo:
        return ProviderInfo(name="copy-lipsync", kind="lipsync", cost_tier=CostTier.LOCAL_FREE, model="copy")

    def estimate_cost(self, request):
        return self._estimate(units=0, unit_name="seconds")

    def lipsync(self, request, out_path: Path) -> LipSyncResult:
        self.calls += 1
        if self.fail:
            raise ProviderError("no face found")
        if not self.applied:
            return LipSyncResult(path=None, provider=self.info.name, model="copy", applied=False, meta={"reason": "no face"})
        shutil.copy(request.video_path, out_path)
        return LipSyncResult(path=str(out_path), provider=self.info.name, model="copy", applied=True, meta={"face_detected": True})


def test_null_lipsync_flags():
    n = NullLipSyncProvider()
    assert not n.applies and n.info.cost_tier == CostTier.LOCAL_FREE
    assert n.lipsync.__self__ is n


@requires_ffmpeg
def test_lipsync_stage_disabled_by_default(orchestrator):
    rep = orchestrator.run(TINY_STORY, project_id="ls0")
    for r in rep.scene_reports:
        assert r.lipsync_meta["status"] == "disabled" and r.lipsync_meta["reason"] == "null provider"
    orchestrator.p.lipsync = CopyLipSync()
    r2 = orchestrator.rebuild(rep.project)  # provider 可用但 scene.lipsync=False → 仍停用、不重做任何東西
    assert all(r.lipsync_meta["reason"] == "scene.lipsync=False" and not r.rebuilt for r in r2.scene_reports)
    assert orchestrator.p.lipsync.calls == 0


@requires_ffmpeg
def test_lipsync_applied_reused_and_used_in_timeline(orchestrator):
    rep = orchestrator.run(TINY_STORY, project_id="ls1")
    p = rep.project
    lp = CopyLipSync()
    orchestrator.p.lipsync = lp
    sid = p.scenes[0].scene_id
    orchestrator.update_scene(p, sid, lipsync=True)
    r2 = orchestrator.rebuild(p)
    m = r2.scene_reports[0].lipsync_meta
    assert m["status"] == "applied" and m["face_detected"] and lp.calls == 1
    assert r2.scene_reports[0].rebuilt == ["lipsync"]  # 只多一個 lipsync 產物；image/tts/clip 皆 reuse
    assert r2.timeline.items[0].clip_path.endswith("clip_lipsync.mp4")
    r3 = orchestrator.rebuild(p)
    assert "lipsync" in r3.scene_reports[0].reused and lp.calls == 1
    orchestrator.p.lipsync = NullLipSyncProvider()  # 換回 null → 回到原 clip
    r4 = orchestrator.rebuild(p)
    assert r4.timeline.items[0].clip_path.endswith("clip.mp4")


@requires_ffmpeg
def test_lipsync_failure_keeps_original_clip(orchestrator):
    rep = orchestrator.run(TINY_STORY, project_id="ls2")
    p = rep.project
    orchestrator.p.lipsync = CopyLipSync(fail=True)
    orchestrator.update_scene(p, p.scenes[0].scene_id, lipsync=True)
    r2 = orchestrator.rebuild(p)
    m = r2.scene_reports[0].lipsync_meta
    assert m["status"] == "degraded" and "no face" in m["error"] and r2.timeline.items[0].clip_path.endswith("clip.mp4")
    orchestrator.p.lipsync = CopyLipSync(applied=False)
    r3 = orchestrator.rebuild(p)
    assert r3.scene_reports[0].lipsync_meta["status"] == "not_applied"


@requires_ffmpeg
def test_paid_lipsync_blocked(orchestrator):
    class Paid(CopyLipSync):
        @property
        def info(self):
            return ProviderInfo(name="paid-lipsync", kind="lipsync", cost_tier=CostTier.PAID, model="x")

    rep = orchestrator.run(TINY_STORY, project_id="ls3")
    paid = Paid()
    orchestrator.p.lipsync = paid
    orchestrator.update_scene(rep.project, rep.project.scenes[0].scene_id, lipsync=True)
    with pytest.raises(PaidProviderNotApproved):
        orchestrator.rebuild(rep.project)
    assert paid.calls == 0


@requires_ffmpeg
@pytest.mark.e2e
def test_style_and_appearance_api(settings):
    c = TestClient(create_app(settings, sync_jobs=True))
    assert {s["style_id"] for s in c.get("/api/styles").json()} >= {"default", "anime", "realistic", "cinematic", "3d", "picture_book"}
    pid = c.post("/api/projects", json={"text": TINY_STORY}).json()["project_id"]
    assert c.get(f"/api/projects/{pid}").json()["style_id"] == "default"
    assert c.post(f"/api/projects/{pid}/style", json={"style_id": "bad"}).status_code == 422
    assert c.post(f"/api/projects/{pid}/style", json={"style_id": "anime"}).json()["style_id"] == "anime"
    v = c.post(f"/api/projects/{pid}/characters/hero/appearance", json={"description_en": "a girl", "outfit_en": "red coat"}).json()
    assert v["characters"]["hero"]["appearance"]["outfit_en"] == "red coat"
