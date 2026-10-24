"""D-064 Environment Doctor／Bootstrap／Manifest／Export／Migration foundation（不需 GPU、不下載、不改系統）。"""
from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path

import pytest
from PIL import Image

from see.core import environment as env
from see.core.config import Settings
from see.core.environment import Status
from see.core.reference_library import ReferenceLibrary
from see.models.character_definition import CharacterDefinition, RefRole
from see.providers.image import checkpoints as ck
from see.storage.character_store import CharacterStore, CharacterStoreError
from see.storage.project_store import ProjectStore
from tests.conftest import TINY_STORY, requires_ffmpeg

NO_GPU = {"torch": None, "cuda_available": False, "cuda_build": None, "cudnn": None, "devices": [], "source": "torch not installed"}


@pytest.fixture
def s(tmp_path, monkeypatch):
    monkeypatch.setattr(env, "gpu_info", lambda: dict(NO_GPU))  # 雲端／CI 一律無 GPU；不讓結果受機器影響
    st = Settings()
    st.workspace = tmp_path / "ws"
    st.models_dir = tmp_path / "models"
    st.image_model_path = st.tts_model_path = ""
    return st


def _status(rep, key):
    return {c.key: c.status for c in rep.checks}[key]


def _tree(root: Path) -> list[tuple[str, int]]:
    return sorted((str(p.relative_to(root)), p.stat().st_size if p.is_file() else -1) for p in root.rglob("*")) if root.exists() else []


def _img(path, color):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (16, 16), color).save(path)
    return path


def _fake_models(root: Path) -> None:
    """小型假模型：SD1.5 diffusers 資料夾、Kokoro、單檔 checkpoint（僅結構與 provenance；不是真權重）。"""
    sd = root / "sd15"
    (sd / "model_index.json").parent.mkdir(parents=True)
    (sd / "model_index.json").write_text("{}")
    for c, n in (("unet", "diffusion_pytorch_model"), ("vae", "diffusion_pytorch_model"), ("text_encoder", "model")):
        (sd / c).mkdir()
        (sd / c / f"{n}.fp16.safetensors").write_bytes(b"x")
    kd = root / "kokoro-v1_1-zh"
    (kd / "voices").mkdir(parents=True)
    (kd / "kokoro-v1_1-zh.pth").write_bytes(b"w")
    (kd / "config.json").write_text("{}")
    (kd / "voices" / "zf_001.pt").write_bytes(b"v")
    (kd / "provenance.json").write_text("{}")


@pytest.fixture
def tiny_ckpt(monkeypatch, tmp_path):
    """把 checkpoint 型錄換成一個 3 bytes 的測試項目（真檔 2 GB 不適合測試）。"""
    from dataclasses import replace

    from see.core.hashing import file_sha256

    data = b"abc"
    probe = tmp_path / "probe.bin"
    probe.write_bytes(data)
    spec = replace(next(iter(ck.CHECKPOINTS.values())), checkpoint_id="tiny_ckpt", filename="tiny.safetensors",
                   bytes=len(data), sha256=file_sha256(probe))
    monkeypatch.setattr(ck, "CHECKPOINTS", {"tiny_ckpt": spec})
    return spec, data


def test_doctor_runs_without_gpu_and_without_optional_packages(s, monkeypatch):
    real = importlib.util.find_spec
    monkeypatch.setattr(importlib.util, "find_spec", lambda n, *a: None if n in ("torch", "kokoro", "diffusers") else real(n, *a))
    rep = env.run_doctor(s, env={})
    assert _status(rep, "gpu.cuda") == Status.UNAVAILABLE  # 無 GPU 不是 ERROR
    assert _status(rep, "python.torch") == Status.UNAVAILABLE and _status(rep, "python.kokoro") == Status.UNAVAILABLE
    assert not any(k.startswith(("gpu.", "models.")) or k in ("python.torch", "python.kokoro") for k in rep.failed_required)
    assert "sd15_image" in rep.readiness["not_ready"] and "tts_kokoro" in rep.readiness["not_ready"]
    assert "identity_lora" in rep.readiness["not_ready"] and "HARDWARE_UPGRADE_BLOCKED" in rep.readiness["not_ready"]["identity_lora"]
    assert rep.tiers["D_future_blocked"]["status"] == "BLOCKED" and rep.tiers["C_gpu_image"]["status"] in ("UNAVAILABLE", "PARTIAL")
    assert all(c.status in set(Status) for c in rep.checks)
    json.dumps(rep.to_dict(), ensure_ascii=False)


def test_check_gpu_reports_cuda_details_when_present():
    info = {**NO_GPU, "torch": "2.5.1+cu121", "cuda_available": True, "cuda_build": "12.1",
            "devices": [{"index": 0, "name": "NVIDIA GeForce GTX 1650", "vram_mb": 4096, "compute_capability": "7.5", "fp16": True, "bf16": False}]}
    c = env.check_gpu(info)[0]
    assert c.status == Status.OK and "GTX 1650" in c.detail and "VRAM 4096" in c.detail and "fp16=yes bf16=no" in c.detail
    broken = env.check_gpu({**NO_GPU, "torch": "2.5.1", "error": "OSError: dll"})[0]
    assert broken.status == Status.ERROR and not broken.required


def test_models_dir_missing_unset_and_relocated(s, tmp_path, tiny_ckpt):
    spec, data = tiny_ckpt
    rep = env.run_doctor(s, env={})
    assert _status(rep, "models.models_dir") == Status.UNAVAILABLE and "未設定" in [c for c in rep.checks if c.key == "models.models_dir"][0].detail
    rep = env.run_doctor(s, env={"SEE_MODELS_DIR": str(s.models_dir)})  # 設定了但不存在
    assert _status(rep, "models.models_dir") == Status.ERROR and "models.models_dir" not in rep.failed_required
    # 舊機 D:\ai-models → 新機 E:\AI\models：只改 SEE_MODELS_DIR
    old = tmp_path / "D_ai-models"
    _fake_models(old)
    f = ck.checkpoint_file(old, spec)
    f.parent.mkdir(parents=True)
    f.write_bytes(data)
    (f.parent / ck.PROVENANCE_FILE).write_text(json.dumps({"local_sha256": spec.sha256, "sha256": spec.sha256}))
    new = tmp_path / "E_AI" / "models"
    shutil.move(str(old), str(new))
    s.models_dir = new
    rep = env.run_doctor(s, env={"SEE_MODELS_DIR": str(new)})
    st = {m["model_id"]: m for m in rep.models}
    assert _status(rep, "models.models_dir") == Status.OK
    assert st["sd15_base"]["status"] == "OK" and st["kokoro_v1_1_zh"]["status"] == "OK" and st["tiny_ckpt"]["status"] == "OK"
    assert st["tiny_ckpt"]["rel_path"] == "checkpoints/tiny_ckpt/tiny.safetensors" and st["tiny_ckpt"]["root"] == "SEE_MODELS_DIR"
    assert env.model_inventory(s, hash_files=True)[2]["sha256_verified"] is True
    f2 = ck.checkpoint_file(new, spec)
    f2.write_bytes(b"xyz")  # 同大小但內容被換
    bad = [m for m in env.model_inventory(s, hash_files=True) if m["model_id"] == "tiny_ckpt"][0]
    assert bad["status"] == "ERROR" and bad["sha256_verified"] is False
    (f2.parent / ck.PROVENANCE_FILE).unlink()
    assert [m for m in env.model_inventory(s) if m["model_id"] == "tiny_ckpt"][0]["status"] == "PARTIAL"  # 缺 provenance ≠ OK


def test_sanitize_and_settings_split():
    home = "/home/alice"
    out = env.sanitize({"p": "/home/alice/AI-Studio/workspace", "w": "C:\\Users\\alice\\x", "n": 3}, home=home, user="alice")
    assert out == {"p": "~/AI-Studio/workspace", "w": "C:\\Users\\<user>\\x", "n": 3}
    assert env.sanitize("palice and al", home=home, user="al") == "palice and al"  # 太短的使用者名稱不替換（避免誤傷）
    snap = env.settings_snapshot({"SEE_MODELS_DIR": "E:\\AI\\models", "SEE_IMAGE_PROVIDER": "auto", "SEE_API_KEY": "sk-1", "PATH": "/x"})
    assert snap["machine_specific"]["SEE_MODELS_DIR"] == "E:\\AI\\models" and snap["portable"]["SEE_IMAGE_PROVIDER"] == "auto"
    assert snap["other_see_vars"] == {"SEE_API_KEY": "<redacted>"} and '"PATH"' not in json.dumps(snap) and "/x" not in json.dumps(snap)
    assert set(env.PORTABLE_SETTINGS).isdisjoint(env.MACHINE_SETTINGS)


def test_manifest_serialization_and_future_schema(s):
    rep = env.run_doctor(s, env={})
    p = env.write_manifest(rep, s)
    m = env.load_manifest(p)
    for k in ("schema_version", "generated_at", "os", "python", "torch", "cuda", "gpu", "ffmpeg", "repo", "models_dir",
              "detected_model_ids", "workspace_version", "models"):
        assert k in m
    assert m["schema_version"] == env.MANIFEST_SCHEMA_VERSION and m["models_dir"]["variable"] == "SEE_MODELS_DIR"
    p.write_text(json.dumps({**m, "schema_version": 99}))
    with pytest.raises(ValueError):
        env.load_manifest(p)
    example = env.load_manifest(Path(__file__).resolve().parents[1] / "docs" / "environment_manifest.example.json")
    assert example["schema_version"] == 1 and "Users" not in json.dumps(example)


def test_bootstrap_check_is_read_only_and_apply_safe_never_overwrites(s):
    rep = env.run_doctor(s, env={})
    plan = env.bootstrap_plan(rep, s)
    assert not s.workspace.exists() and not s.models_dir.exists()  # 唯讀：連 workspace 都沒建立
    assert plan["auto_safe"] and any("SEE_MODELS_DIR" in i["item"] for i in plan["user_action"])
    assert any("torch" in i["item"] for i in plan["needs_approval"]) and len(plan["blocked"]) == len(env.BLOCKED)
    assert not any("pip install torch" in i["command"] for k in plan for i in plan[k])
    (s.workspace / "projects" / "p1").mkdir(parents=True)
    (s.workspace / "projects" / "p1" / "keep.txt").write_text("user data")
    (s.workspace / env.WORKSPACE_VERSION_FILE).write_text(json.dumps({"workspace_schema_version": 1, "note": "mine"}))
    before = _tree(s.workspace)
    done = env.apply_safe(s)
    assert "mkdir reference_library/people/" in done and not any("projects/" == d.split()[-1] for d in done)
    after = dict(_tree(s.workspace))
    assert all(after.get(k) == v for k, v in before)  # 既有內容（含版本檔）位元不變
    assert json.loads((s.workspace / env.WORKSPACE_VERSION_FILE).read_text())["note"] == "mine"
    assert env.apply_safe(s) == []  # 冪等


def test_old_workspace_compat_and_unknown_future_schema(s):
    s.workspace.mkdir(parents=True)
    ver, src = env.read_workspace_version(s.workspace)
    assert ver == 1 and "legacy" in src  # 舊 workspace 沒有版本檔 → v1
    # 舊角色檔（無 schema_version）仍可讀；比程式新的 → fail safe
    cs = CharacterStore(s.workspace)
    cs.create(CharacterDefinition(character_id="char_001", display_name="男主角"))
    f = cs.root / "char_001.json"
    raw = json.loads(f.read_text())
    raw.pop("schema_version")
    f.write_text(json.dumps(raw))
    assert cs.get("char_001").schema_version == 1 and cs.migration_plan()["legacy_compatible"] == ["char_001.json"]
    assert json.loads(f.read_text()).get("schema_version") is None  # 讀取不會偷偷改寫舊檔
    bk = cs.backup()
    assert (bk / "char_001.json").read_text() == f.read_text()
    f.write_text(json.dumps({**raw, "schema_version": 99}))
    with pytest.raises(CharacterStoreError):
        cs.get("char_001")
    assert cs.migration_plan()["newer_than_supported"] == ["char_001.json"]
    rep = env.run_doctor(s, env={})
    assert _status(rep, "workspace.character_store") == Status.ERROR
    (s.workspace / env.WORKSPACE_VERSION_FILE).write_text(json.dumps({"workspace_schema_version": 99}))
    rep = env.run_doctor(s, env={})
    assert _status(rep, "workspace.schema_version") == Status.ERROR and "workspace.schema_version" in rep.failed_required


def test_reference_and_character_metadata_survive_workspace_move(tmp_path):
    a = tmp_path / "D_drive" / "ws"
    _img(a / "reference_library" / "people" / "hero.jpg", (10, 20, 30))
    _img(a / "reference_library" / "people" / "old.jpg", (40, 50, 60))
    lib = ReferenceLibrary(a)
    hero = lib.register("people/hero.jpg", asset_id="hero_face", role=RefRole.identity_face, source_type="user_supplied", character_id="char_001")
    assert hero.file_path == "people/hero.jpg"  # D-064：不存本機絕對路徑
    lib.register("people/old.jpg", asset_id="old_face", role=RefRole.pose, source_type="user_supplied", character_id="char_001")
    lib.mark_primary("hero_face")
    side = a / "reference_library" / "people" / "old.jpg.ref.json"  # 模擬 D-064 前的舊 sidecar（絕對路徑、無 schema_version）
    raw = json.loads(side.read_text())
    raw["file_path"] = str(a / "reference_library" / "people" / "old.jpg")
    raw.pop("schema_version")
    side.write_text(json.dumps(raw))
    CharacterStore(a).create(CharacterDefinition(character_id="char_001", display_name="男主角"))
    CharacterStore(a).archive("char_001")
    b = tmp_path / "E_drive" / "AI" / "ws"
    shutil.copytree(a, b)
    shutil.rmtree(a)
    lib2 = ReferenceLibrary(b)
    assert all(not e.problems for e in lib2.list())
    assert {x.asset_id for x in lib2.assets_for("char_001")} == {"hero_face", "old_face"}
    assert lib2.get("hero_face")[1].is_primary and lib2.get("hero_face")[1].sha256 == hero.sha256
    rec = CharacterStore(b).get("char_001")
    assert rec.archived and rec.revision == 2  # 封存狀態與 revision 隨檔案保存
    side2 = b / "reference_library" / "people" / "old.jpg.ref.json"
    side2.write_text(json.dumps({**raw, "schema_version": 99}))
    assert any("newer than supported" in p for e in lib2.list() if e.rel_path == "people/old.jpg" for p in e.problems)


def test_export_contains_recovery_info_without_private_paths(s, tmp_path, monkeypatch):
    s.workspace = tmp_path / "home" / "alice" / "ws"
    _img(s.workspace / "reference_library" / "people" / "hero.jpg", (1, 2, 3))
    ReferenceLibrary(s.workspace).register("people/hero.jpg", asset_id="hero_face", role=RefRole.identity_face,
                                           source_type="user_supplied", character_id="char_001")
    CharacterStore(s.workspace).create(CharacterDefinition(character_id="char_001", display_name="男主角"))
    real = env.sanitize
    monkeypatch.setattr(env, "sanitize", lambda o, home=None, user=None: real(o, str(tmp_path / "home" / "alice"), "alice"))
    out = env.export_environment(s, hash_files=False)
    names = sorted(p.name for p in out.iterdir())
    assert names == ["environment_manifest.json", "models_manifest.json", "python_packages.txt", "settings.json", "workspace_inventory.json"]
    blob = "".join(p.read_text(encoding="utf-8") for p in out.iterdir())
    assert "alice" not in blob and not list(out.rglob("*.jpg")) and not list(out.rglob("*.safetensors"))
    inv = json.loads((out / "workspace_inventory.json").read_text())
    assert inv["reference_library"][0]["asset"]["file_path"] == "people/hero.jpg" and len(inv["reference_library"][0]["asset"]["sha256"]) == 64
    assert inv["character_store"][0]["definition"]["character_id"] == "char_001"
    assert "pydantic" in (out / "python_packages.txt").read_text().lower()
    (out / "x").write_text("1")
    with pytest.raises(FileExistsError):
        env.export_environment(s, out_dir=out)  # 不覆寫既有輸出


@requires_ffmpeg
def test_project_assets_reused_after_workspace_move(orchestrator, tmp_path):
    from see.pipeline.orchestrator import Orchestrator

    p = orchestrator.create_project(TINY_STORY, project_id="mv1")
    orchestrator.write_script(p)
    orchestrator.storyboard(p)
    orchestrator.build_scene_assets(p)
    old = orchestrator.settings.workspace
    new = tmp_path / "moved_ws"
    shutil.copytree(old, new)
    shutil.rmtree(old)
    orchestrator.settings.workspace = new
    o2 = Orchestrator(orchestrator.settings, orchestrator.p, orchestrator.executor, ProjectStore(new), orchestrator.renderer)
    p2 = o2.store.load("mv1")
    reps = o2.build_scene_assets(p2)
    assert all(r.rebuilt == [] for r in reps)  # 搬家後沿用全部產物，不重做
    rec = o2.store.load_manifest("mv1", p2.scenes[0].scene_id).entries["image"]
    assert Path(rec.path).is_relative_to(new)


@requires_ffmpeg
def test_smoke_test_passes_without_gpu():
    res = {n: st for n, st, _ in env.smoke_test()}
    assert res == {"web_api_import": Status.OK, "tts_interface": Status.OK, "pipeline": Status.OK}


def test_cli_doctor_bootstrap_json(s, monkeypatch, capsys):
    from see.app.cli import main

    monkeypatch.setenv("SEE_WORKSPACE", str(s.workspace))
    monkeypatch.delenv("SEE_MODELS_DIR", raising=False)
    main(["doctor", "--json"])
    d = json.loads(capsys.readouterr().out)
    assert {"checks", "readiness", "tiers", "settings", "failed_required"} <= set(d)
    assert main(["bootstrap", "--check"]) == 0 and not s.workspace.exists()
    assert "唯讀" in capsys.readouterr().out


def test_missing_models_dir_message_differs_from_unverified(s, monkeypatch):
    """BACKLOG 實例：新視窗沒設 SEE_MODELS_DIR → 應說「模型目錄未設定」，不是「未驗證」。"""
    from see.app.cli import _style_test_image_provider

    monkeypatch.delenv("SEE_MODELS_DIR", raising=False)
    _, err = _style_test_image_provider(s, "cyberrealistic_final", None)
    assert err.startswith("模型目錄未設定") and "doctor" in err
    monkeypatch.setenv("SEE_MODELS_DIR", str(s.models_dir))
    _, err = _style_test_image_provider(s, "cyberrealistic_final", None)
    assert "沒有通過驗證的 provenance" in err and "doctor --hash" in err
