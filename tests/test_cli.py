import json
from pathlib import Path

from see.app.cli import main
from tests.conftest import TINY_STORY, requires_ffmpeg


def test_check_env_runs(capsys):
    main(["check-env"])
    assert "ffmpeg" in capsys.readouterr().out


@requires_ffmpeg
def test_cli_run_and_status(tmp_path: Path, capsys, monkeypatch):
    story = tmp_path / "s.txt"
    story.write_text(TINY_STORY, encoding="utf-8")
    monkeypatch.setenv("SEE_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.setenv("SEE_TTS_PROVIDER", "silent")
    assert main(["run", str(story), "--project-id", "cli1"]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["status"] == "PREVIEW" and Path(summary["output"]).exists()
    assert summary["probe"]["has_video"] and summary["probe"]["has_audio"]
    assert main(["status", "cli1"]) == 0
    assert "scene_001" in capsys.readouterr().out
    assert main(["final", "cli1"]) == 2  # 未核准 → 拒絕
    assert main(["approve", "cli1", "--by", "tester"]) == 0
    assert main(["final", "cli1"]) == 0
