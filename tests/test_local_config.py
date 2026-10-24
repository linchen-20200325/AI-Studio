"""D-065 專案本機設定檔（see.local.json）：優先序 env > local config > unset、不進 Git、只收 machine-specific、doctor 顯示來源。"""
from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from see.core import config as cfg
from see.core import environment as env
from see.core.config import LocalConfigError, Settings, read_local_config, setting_source, write_local_config


@pytest.fixture
def local(tmp_path, monkeypatch):
    p = tmp_path / "proj" / "see.local.json"
    monkeypatch.setenv("SEE_LOCAL_CONFIG", str(p))
    for k in cfg.LOCAL_CONFIG_KEYS.values():
        monkeypatch.delenv(k, raising=False)
    return p


def test_local_config_is_gitignored_and_only_example_is_tracked():
    root = cfg.repo_root()
    assert "see.local.json" in (root / ".gitignore").read_text(encoding="utf-8").splitlines()
    example = json.loads((root / "see.local.example.json").read_text(encoding="utf-8"))
    cfg.validate_local_config(example)  # 範例本身符合 schema（只有 machine-specific key）
    if shutil.which("git") and (root / ".git").exists():
        assert subprocess.run(["git", "-C", str(root), "check-ignore", "-q", "see.local.json"]).returncode == 0
        assert subprocess.run(["git", "-C", str(root), "check-ignore", "-q", "see.local.example.json"]).returncode == 1


def test_priority_env_then_local_then_unset(local, tmp_path, monkeypatch):
    assert setting_source("SEE_MODELS_DIR") == (None, "unset")
    assert Settings().models_dir.name == "models"  # 未設定 → 程式預設 ./models
    write_local_config({"models_dir": str(tmp_path / "E_AI" / "models"), "tts_device": "cuda"}, local)
    assert setting_source("SEE_MODELS_DIR") == (str(tmp_path / "E_AI" / "models"), "local_config")
    s = Settings()
    assert s.models_dir == (tmp_path / "E_AI" / "models").resolve() and s.tts_device == "cuda"
    monkeypatch.setenv("SEE_MODELS_DIR", str(tmp_path / "from_env"))
    assert setting_source("SEE_MODELS_DIR") == (str(tmp_path / "from_env"), "env")
    assert Settings().models_dir == (tmp_path / "from_env").resolve()
    assert Settings().tts_device == "cuda"  # 其他 key 仍來自 local config


def test_relative_paths_follow_config_folder_and_windows_paths_kept(local):
    write_local_config({"models_dir": "../models_here", "workspace_dir": "E:\\AI\\ws"}, local)
    data, err = read_local_config(local)
    assert err is None and data["models_dir"] == str((local.parent / "../models_here").resolve())
    assert data["workspace_dir"] == "E:\\AI\\ws"  # Windows 絕對路徑原樣保留（不寫死、不改寫磁碟代號）


def test_only_machine_specific_keys_no_secrets_no_preferences(local):
    for bad in ({"api_key": "sk-x"}, {"image_provider": "auto"}, {"style_id": "anime"}, {"hf_token": "x"}):
        with pytest.raises(LocalConfigError):
            write_local_config(bad, local)  # type: ignore[arg-type]
    assert not local.exists()
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_text(json.dumps({"schema_version": 1, "models_dir": "x", "OPENAI_API_KEY": "sk"}))
    data, err = read_local_config(local)
    assert data == {} and "not allowed" in err  # 整份不採用（fail closed）
    assert Settings().models_dir.name == "models"
    local.write_text(json.dumps({"schema_version": 99, "models_dir": "x"}))
    assert read_local_config(local)[1] and "schema_version" in read_local_config(local)[1]


def test_doctor_shows_source(local, tmp_path, monkeypatch):
    monkeypatch.setattr(env, "gpu_info", lambda: {"torch": None, "cuda_available": False, "cuda_build": None, "cudnn": None,
                                                    "devices": [], "source": "torch not installed"})
    models = tmp_path / "m"
    models.mkdir()
    write_local_config({"models_dir": str(models)}, local)
    s = Settings()
    s.workspace = tmp_path / "ws"
    rep = env.run_doctor(s, env={})
    by = {c.key: c for c in rep.checks}
    assert by["config.local_config"].status == env.Status.OK
    assert by["config.models_dir"].data["source"] == "local_config" and "來源：local_config" in by["config.models_dir"].detail
    assert by["models.models_dir"].status == env.Status.OK and by["models.models_dir"].data["source"] == "local_config"
    assert rep.settings["machine_specific_sources"]["SEE_MODELS_DIR"] == "local_config"
    rep2 = env.run_doctor(s, env={"SEE_MODELS_DIR": str(models)})
    assert {c.key: c for c in rep2.checks}["config.models_dir"].data["source"] == "env"
    local.write_text("{not json")
    rep3 = env.run_doctor(s, env={})
    c3 = {c.key: c for c in rep3.checks}
    assert c3["config.local_config"].status == env.Status.ERROR and c3["config.models_dir"].data["source"] == "unset"
    assert "config.local_config" not in rep3.failed_required


def test_config_cli_set_show_unset(local, capsys):
    from see.app.cli import main

    assert main(["config", "set", "models_dir", "E:\\AI\\models"]) == 0
    assert json.loads(local.read_text())["models_dir"] == "E:\\AI\\models"
    assert "local_config" in capsys.readouterr().out
    assert main(["config", "set", "api_key", "sk"]) == 2 and "api_key" not in local.read_text()
    assert main(["config", "unset", "models_dir"]) == 0 and "models_dir" not in json.loads(local.read_text())
