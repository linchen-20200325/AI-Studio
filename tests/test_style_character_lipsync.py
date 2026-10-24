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
    snap = ctx.pop("preference_snapshot")  # D-062：偏好快照只進 evidence，不改 request／fingerprint
    assert ctx == {"style_id": "default", "style_validated": True, "character_anchors": []}
    assert snap["resolved"]["visual_style_id"] == "default" and snap["no_prompt_effect"] == []


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


# ---------------------------------------------------------------- style-test CLI（DG-18 A 真機驗收工具）
def test_style_test_cli_isolated_and_fair(tmp_path, monkeypatch, capsys):
    import json as _json

    from see.app.cli import main

    monkeypatch.setenv("SEE_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.setenv("SEE_IMAGE_PROVIDER", "placeholder")
    monkeypatch.setenv("SEE_MODELS_DIR", str(tmp_path / "no-models"))
    evs = []
    for sid in ("anime", "realistic"):
        rc = main(["style-test", "--style", sid])
        assert rc == 3  # 沒有本機 SD 權重 → placeholder → 明確標為無效，不當成功
        evs.append(_json.loads((tmp_path / "ws" / "style_tests" / f"{sid}_seed1234.json").read_text(encoding="utf-8")))
    capsys.readouterr()
    a, r = evs
    assert a["seed"] == r["seed"] == 1234 and a["base_prompt"] == r["base_prompt"] and (a["width"], a["height"]) == (r["width"], r["height"])
    assert a["prompt"] != r["prompt"] and "anime style" in a["prompt"] and "photorealistic" in r["prompt"]
    assert not a["technical_valid"] and a["generated_by"] == "placeholder-image"
    assert a["scene_validated"] is None and a["style_validated"] is None  # 人工判定，不自動推論（D-035）
    assert a["baseline_condition"] and a["prompt_subject_check"]["passed"]
    assert not (tmp_path / "ws" / "projects").exists()  # 不建立任何專案／manifest
    with pytest.raises(ValueError):
        main(["style-test", "--style", "vaporwave"])


# ---------------------------------------------------------------- D-035 分層驗收／診斷參數
def test_gen_size_native_keeps_sd15_short_side():
    from see.providers.image.diffusers_local import center_crop_to_aspect, gen_size, gen_size_native

    assert gen_size(2880, 1620, 512, 8) == (512, 288)  # 現行 fit：短邊 288，遠低於 SD 1.5 訓練解析度
    assert gen_size_native(2880, 1620, 512, 8) == (768, 512)
    assert gen_size_native(1620, 2880, 512, 8) == (512, 768)
    assert gen_size_native(1024, 1024, 512, 8) == (512, 512)
    assert gen_size_native(2880, 1620, 384, 8) == (576, 384)  # OOM 降級後仍可用
    l, t, r, b = center_crop_to_aspect(768, 512, 2880, 1620)
    assert (r - l, b - t) == (768, 432) and t == 40


def test_technical_validity_does_not_imply_scene_or_style():
    from see.core.style_tests import get_case, prompt_subject_check, technical_validity, verdict_to_bool

    ok = technical_validity("diffusers-sd15", {"is_black": False, "is_flat": False})
    assert ok == {"technical_valid": True, "technical_reasons": []}
    bad = technical_validity("placeholder-image", {"is_black": False, "is_flat": True})
    assert not bad["technical_valid"] and len(bad["technical_reasons"]) == 2
    c = get_case("kitten_butterfly")
    assert prompt_subject_check("a kitten, a courtyard, butterflies", c.expected_subjects_en)["passed"]
    assert prompt_subject_check("a courtyard", c.expected_subjects_en)["missing"] == ["a kitten", "butterflies"]
    assert verdict_to_bool(None) is None and verdict_to_bool("fail") is False
    with pytest.raises(ValueError):
        get_case("nope")


def test_style_test_diagnostics_never_overwrite_baseline(tmp_path, monkeypatch, capsys):
    import json as _json

    from see.app.cli import main

    monkeypatch.setenv("SEE_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.setenv("SEE_IMAGE_PROVIDER", "placeholder")
    monkeypatch.setenv("SEE_MODELS_DIR", str(tmp_path / "no-models"))
    main(["style-test", "--style", "picture_book"])
    main(["style-test", "--style", "picture_book", "--gen-policy", "native"])
    main(["style-test", "--style", "picture_book", "--base-prompt", "a kitten chasing butterflies in a courtyard"])
    main(["style-test", "--style", "anime", "--case", "girl_city_night"])
    capsys.readouterr()
    d = tmp_path / "ws" / "style_tests"
    names = sorted(p.name for p in d.glob("*.json"))
    assert names == ["anime_seed1234_girl_city_night.json", "picture_book_seed1234.json",
                     "picture_book_seed1234_customprompt.json", "picture_book_seed1234_native.json"]
    nat = _json.loads((d / "picture_book_seed1234_native.json").read_text(encoding="utf-8"))
    assert not nat["baseline_condition"] and nat["diagnostic_overrides"]["gen_policy"] == "native"
    girl = _json.loads((d / "anime_seed1234_girl_city_night.json").read_text(encoding="utf-8"))
    assert "a girl" in girl["prompt"] and girl["baseline_condition"]


def test_style_review_only_on_technical_valid(tmp_path, monkeypatch, capsys):
    import json as _json

    from see.app.cli import main

    monkeypatch.setenv("SEE_WORKSPACE", str(tmp_path / "ws"))
    d = tmp_path / "ws" / "style_tests"
    d.mkdir(parents=True)
    (d / "x.json").write_text(_json.dumps({"style_id": "picture_book", "technical_valid": True}), encoding="utf-8")
    (d / "bad.json").write_text(_json.dumps({"style_id": "anime", "technical_valid": False}), encoding="utf-8")
    assert main(["style-review", "x", "--scene", "fail", "--style", "fail", "--note", "像藝術品"]) == 0
    ev = _json.loads((d / "x.json").read_text(encoding="utf-8"))
    assert ev["scene_validated"] is False and ev["style_validated"] is False and ev["human_review"]["subjective"]
    assert main(["style-review", "bad", "--scene", "pass", "--style", "pass"]) == 3
    assert main(["style-review", "missing", "--scene", "pass", "--style", "pass"]) == 2
    capsys.readouterr()


def test_default_pipeline_request_has_no_gen_policy():
    """fit 為預設且不進 params → 舊專案 image fingerprint 不變（gen_policy 只在診斷時出現）。"""
    from see.app.cli import _style_test_stem

    assert _style_test_stem("anime", "kitten_butterfly", 1234, "fit", False) == "anime_seed1234"


# ---------------------------------------------------------------- D-041 人物近景品質案例
def test_portrait_closeup_case_is_model_and_style_agnostic(tmp_path, monkeypatch, capsys):
    import json as _json

    from see.app.cli import main
    from see.core.style_tests import get_case

    c = get_case("girl_portrait_closeup")
    assert c.base_prompt_en and "front view" in c.base_prompt_en and "looking at viewer" in c.base_prompt_en
    assert "meinamix" not in c.base_prompt_en.lower() and "anime" not in c.base_prompt_en.lower()  # 構圖中性，不綁模型／風格
    assert any("眼睛" in x for x in c.review_checklist) and any("手部" in x for x in c.review_checklist)
    monkeypatch.setenv("SEE_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.setenv("SEE_IMAGE_PROVIDER", "placeholder")
    monkeypatch.setenv("SEE_MODELS_DIR", str(tmp_path / "no-models"))
    evs = {}
    for sid in ("anime", "realistic"):
        main(["style-test", "--style", sid, "--case", "girl_portrait_closeup", "--gen-policy", "native"])
        evs[sid] = _json.loads((tmp_path / "ws" / "style_tests" / f"{sid}_seed1234_girl_portrait_closeup_native.json").read_text(encoding="utf-8"))
    capsys.readouterr()
    a, r = evs["anime"], evs["realistic"]
    assert a["base_prompt"] == r["base_prompt"] == c.base_prompt_en and a["prompt_source"] == "case_base_prompt_en"
    assert a["prompt"].startswith(c.base_prompt_en) and "anime style" in a["prompt"] and "photorealistic" in r["prompt"]
    assert a["prompt_subject_check"]["passed"] and a["human_review"]["subjective"] == "single-user subjective"
    assert a["human_review"]["checklist"] == list(c.review_checklist)


def test_scene_flag_rejects_case_id(tmp_path, monkeypatch, capsys):
    from see.app.cli import main

    monkeypatch.setenv("SEE_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.setenv("SEE_IMAGE_PROVIDER", "placeholder")
    assert main(["style-test", "--style", "anime", "--scene", "girl_city_night"]) == 2
    assert "--case girl_city_night" in capsys.readouterr().err


# ---------------------------------------------------------------- D-043 跨次比較條件
def _ev(checkpoint=None, clip=None, **over):
    g = {"gen_policy": "native", "gen_width": 768, "gen_height": 512, "crop_box": [0, 40, 768, 472], "steps": 25,
         "guidance": 7.0, "scheduler": "DPMSolverMultistepScheduler", "scheduler_name": "dpmpp_2m_karras"}
    if clip is not None:
        g["clip_skip_a1111"] = clip
    ev = {"case_id": "girl_portrait_closeup", "seed": 1234, "style_id": "anime", "base_prompt": "a girl", "prompt": "a girl, anime",
          "negative_prompt": "lowres", "width": 1920, "height": 1080, "final_dtype": "float32", "generation": g,
          "checkpoint": checkpoint, "technical_valid": True}
    ev.update(over)
    return ev


MEINA = {"checkpoint_id": "meinamix_v12", "sha256": "a5e5a941a3217247dbceceee5b67f8d6b1ef2514260e08a5757436bec7035f93"}


def test_compare_base_vs_meinamix_is_model_preset_level_not_single_variable():
    """E2-5 實況：base（舊 JSON 無 clip skip 欄位＝1）vs MeinaMix（clip skip 2）→ 不是嚴格單一變數。"""
    from see.core.style_tests import compare_conditions

    r = compare_conditions(_ev(), _ev(checkpoint=MEINA, clip=2))
    assert r["verdict"] == "model_preset_level"
    assert r["differences"]["model"] == ["sd15-base", "meinamix_v12@a5e5a941a321"]
    assert r["differences"]["clip_skip_a1111"] == [1, 2] and r["unexpected_differences"] == []
    assert {"seed", "prompt", "negative_prompt", "gen_size", "steps", "guidance", "scheduler", "final_dtype"} <= set(r["identical"])


def test_compare_single_variable_and_not_comparable():
    from see.core.style_tests import compare_conditions

    assert compare_conditions(_ev(clip=1), _ev(checkpoint=MEINA, clip=1))["verdict"] == "single_variable"
    bad = compare_conditions(_ev(), _ev(checkpoint=MEINA, clip=2, seed=99))
    assert bad["verdict"] == "not_comparable" and bad["unexpected_differences"] == ["seed"]
    # 同模型下 clip skip 不同 → 不能算模型預設差異
    same = compare_conditions(_ev(clip=1), _ev(clip=2))
    assert same["verdict"] == "not_comparable" and same["unexpected_differences"] == ["clip_skip_a1111"]
    # 缺必要欄位 → 無法確認 → not_comparable
    assert compare_conditions(_ev(generation={}), _ev(generation={}))["verdict"] == "not_comparable"


def test_style_compare_cli(tmp_path, monkeypatch, capsys):
    import json as _json

    from see.app.cli import main

    monkeypatch.setenv("SEE_WORKSPACE", str(tmp_path / "ws"))
    d = tmp_path / "ws" / "style_tests"
    d.mkdir(parents=True)
    (d / "base.json").write_text(_json.dumps(_ev()), encoding="utf-8")
    (d / "meina.json").write_text(_json.dumps(_ev(checkpoint=MEINA, clip=2)), encoding="utf-8")
    (d / "other.json").write_text(_json.dumps(_ev(steps=30, checkpoint=MEINA, clip=2)), encoding="utf-8")
    assert main(["style-compare", "base", "meina"]) == 0
    out = _json.loads(capsys.readouterr().out)
    assert out["verdict"] == "model_preset_level"
    assert main(["style-compare", "base", "missing"]) == 2
    capsys.readouterr()
    (d / "other.json").write_text(_json.dumps(_ev(checkpoint=MEINA, clip=2, seed=1)), encoding="utf-8")
    assert main(["style-compare", "base", "other"]) == 4


def test_style_test_evidence_records_comparison_conditions(tmp_path, monkeypatch, capsys):
    import json as _json

    from see.app.cli import main

    monkeypatch.setenv("SEE_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.setenv("SEE_IMAGE_PROVIDER", "placeholder")
    monkeypatch.setenv("SEE_MODELS_DIR", str(tmp_path / "no-models"))
    main(["style-test", "--style", "anime", "--case", "girl_portrait_closeup"])
    capsys.readouterr()
    ev = _json.loads((tmp_path / "ws" / "style_tests" / "anime_seed1234_girl_portrait_closeup.json").read_text(encoding="utf-8"))
    assert "fair_comparison" not in ev and ev["baseline_condition"] is True
    assert ev["comparison_conditions"]["model"] == "sd15-base" and ev["comparison_conditions"]["seed"] == 1234


def test_diversity_portrait_cases_only_change_subject():
    """D-046：東亞女性／男性案例與 girl_portrait_closeup 構圖詞完全相同，只換人物描述（受控變因）。"""
    from see.core.style_tests import get_case

    ref = get_case("girl_portrait_closeup").base_prompt_en.split(", ", 1)[1]
    for cid, subj in (("east_asian_female_portrait", "an East Asian adult woman"), ("east_asian_male_portrait", "an East Asian adult man")):
        c = get_case(cid)
        head, tail = c.base_prompt_en.split(", ", 1)
        assert head == subj and tail == ref and c.seed == 1234 and subj in c.expected_subjects_en


# ---------------------------------------------------------------- D-047 結構化 Character 設定（角色 A／B）
def test_character_traits_anchor_and_legacy_compat():
    from see.models.project import CharacterTraits

    legacy = CharacterAppearance(description_en="a young monk boy", outfit_en="orange robe", features_en=["round face"])
    assert legacy.traits is None and legacy.anchor_text == "a young monk boy, wearing orange robe, round face"  # 舊 fingerprint 不變
    # 舊 project.json（沒有 traits 鍵）仍可載入
    assert CharacterAppearance.model_validate({"description_en": "x"}).traits is None
    t = CharacterTraits(gender_presentation="woman", age=28, appearance_region="East Asian", hair_style="short bob",
                        hair_color="black", facial_features=["almond-shaped eyes"], body_type="slim", distinctive_marks=["round glasses"])
    a = CharacterAppearance(outfit_en="navy blazer", traits=t)
    assert a.anchor_text == ("28-year-old East Asian woman, slim, short bob black hair, almond-shaped eyes, round glasses, "
                             "wearing navy blazer")
    assert CharacterTraits().is_empty and CharacterTraits().anchor_parts == []  # 無任何性別／族群／年齡預設
    assert CharacterTraits(age_range="in his 40s", gender_presentation="man").anchor_parts == ["man", "in his 40s"]
    assert CharacterTraits(hair_style="ponytail").anchor_parts == ["ponytail hair"]
    with pytest.raises(ValueError):
        CharacterTraits(age=0)


def test_reference_images_local_only():
    assert CharacterAppearance(reference_images=["D:/refs/a.png"]).reference_images == ["D:/refs/a.png"]
    with pytest.raises(ValueError):
        CharacterAppearance(reference_images=["https://example.com/face.jpg"])


def test_character_a_b_each_keep_own_anchor_in_same_scene(orchestrator):
    from see.models.enums import Status
    from see.models.project import CharacterTraits

    p = _planned(orchestrator, "ab1")
    a = CharacterAppearance(outfit_en="red coat", traits=CharacterTraits(gender_presentation="woman", appearance_region="East Asian"))
    b = CharacterAppearance(outfit_en="grey suit", traits=CharacterTraits(gender_presentation="man", appearance_region="East Asian", age=40))
    orchestrator.set_character_appearance(p, "char_a", a)
    orchestrator.set_character_appearance(p, "char_b", b)
    orchestrator.update_scene(p, p.scenes[0].scene_id, character_ids=["char_a", "char_b"])
    req, ctx = orchestrator.image_request(p, p.scenes[0])
    refs = req.params["characters"]
    assert [r["character_id"] for r in refs] == ["char_a", "char_b"] == ctx["character_anchors"]
    assert refs[0]["anchor"] == "East Asian woman, wearing red coat" and refs[1]["anchor"] == "40-year-old East Asian man, wearing grey suit"
    assert req.prompt.startswith("East Asian woman, wearing red coat, 40-year-old East Asian man, wearing grey suit, ")
    # 只改 B 的設定 → 只有 B 出現的景回 DRAFT（A 獨有的景不受影響）
    orchestrator.update_scene(p, p.scenes[1].scene_id, character_ids=["char_a"])
    for sc in p.scenes:
        sc.status = Status.APPROVED if sc.scene_id == p.scenes[1].scene_id else sc.status
    orchestrator.set_character_appearance(p, "char_b", CharacterAppearance(traits=CharacterTraits(gender_presentation="man", hair_color="grey")))
    assert p.scenes[1].status == "APPROVED" and p.scenes[0].status == "DRAFT"


def test_appearance_api_traits(settings):
    c = TestClient(create_app(settings, sync_jobs=True))
    pid = c.post("/api/projects", json={"text": TINY_STORY}).json()["project_id"]
    v = c.post(f"/api/projects/{pid}/characters/hero/appearance",
               json={"traits": {"gender_presentation": "man", "appearance_region": "East Asian", "age": 30}}).json()
    assert v["characters"]["hero"]["appearance"]["traits"]["appearance_region"] == "East Asian"
    assert c.post(f"/api/projects/{pid}/characters/hero/appearance", json={"traits": {"age": 999}}).status_code == 422


# ---------------------------------------------------------------- D-049 A／B 多角色同框受控案例
def test_two_characters_case_uses_product_anchor_path_and_disjoint_attributes():
    from see.core.style_tests import get_case

    c = get_case("two_characters_ab")
    a, b = c.characters
    # 錨點走產品同一條路徑（CharacterTraits → anchor_text）
    # D-058：A＝男、B＝女（v2）；character_id 不代表性別，性別來自 CharacterDefinition.gender_presentation
    assert a.anchor == "East Asian man, short grey hair, round glasses, wearing grey suit"
    assert b.anchor == "East Asian woman, long straight black hair, wearing red coat"
    assert a.definition.gender_presentation.value == "male" and b.definition.gender_presentation.value == "female"
    assert c.definition_version == 2
    assert c.base_prompt_en.startswith(f"two people side by side, {a.anchor} on the left, {b.anchor} on the right, ")
    assert c.base_prompt_en.endswith("upper body, front view, looking at viewer, city at night in the background, blurred background")
    assert c.seed == 1234
    # 互斥屬性：只屬於 B 的配件／顏色不得出現在 A 的錨點，反之亦然（否則人工審圖無法判斷互換）
    assert "glasses" not in b.anchor and "red" not in a.anchor and "black" not in a.anchor and "grey" not in b.anchor


def test_two_characters_style_test_evidence(tmp_path, monkeypatch, capsys):
    import json as _json

    from see.app.cli import main

    monkeypatch.setenv("SEE_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.setenv("SEE_IMAGE_PROVIDER", "placeholder")
    monkeypatch.setenv("SEE_MODELS_DIR", str(tmp_path / "no-models"))
    main(["style-test", "--style", "realistic", "--case", "two_characters_ab", "--gen-policy", "native"])
    capsys.readouterr()
    ev = _json.loads((tmp_path / "ws" / "style_tests" / "realistic_seed1234_two_characters_ab-v2_native.json").read_text(encoding="utf-8"))
    assert [x["character_id"] for x in ev["case_characters"]] == ["char_a", "char_b"]
    assert ev["case_definition_version"] == 2 and ev["historical_reversed_character_mapping"] is False
    assert [d["gender_presentation"] for d in ev["character_definitions"]] == ["male", "female"]
    assert ev["prompt_subject_check"]["passed"] and ev["prompt_source"] == "case_base_prompt_en"
    assert "圓眼鏡只在 A" in " ".join(ev["human_review"]["checklist"])

