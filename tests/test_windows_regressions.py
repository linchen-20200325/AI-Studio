"""Windows 真機回歸（D-020）：subprocess 不得依賴 locale 編碼；fp16 NaN／黑圖要被偵測並升級精度。"""

import subprocess
from pathlib import Path

import numpy as np
import pytest

from see.core import proc
from see.core.ffmpeg import FFmpeg
from see.core.proc import run_text
from see.providers.base import TTSRequest
from see.providers.image.diffusers_local import (
    RuntimePlan,
    gpu_prefers_fp32_vae,
    is_numeric_failure,
    make_runtime_plan,
)
from see.providers.tts.espeak import EspeakTTSProvider


class _Fake:
    def __init__(self, stdout: bytes, stderr: bytes, rc: int = 0):
        self.stdout, self.stderr, self.returncode = stdout, stderr, rc


def test_run_text_decodes_utf8_and_binary_without_raising(monkeypatch):
    seen = {}

    def fake_run(cmd, **kw):
        seen.update(kw)
        return _Fake(b"\x89PNG\r\n\x1a\n", "字幕 WenQuanYi".encode("utf-8") + b"\xff\xfe", 0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    r = run_text(["x"], timeout=5)
    assert "text" not in seen and "encoding" not in seen  # bytes 模式，不走 locale
    assert r.stdout.startswith("�PNG") and "字幕 WenQuanYi" in r.stderr and r.returncode == 0


def test_ffmpeg_wrappers_use_run_text(monkeypatch):
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        return _Fake(b'{"streams": [], "format": {"duration": "1.0"}}', "錯誤".encode("utf-8"), 0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    ff = FFmpeg("ffmpeg", "ffprobe")
    ff.run(["-i", "x"])
    info = ff.probe(Path("x.mp4"))
    assert info.duration == 1.0 and len(calls) == 2


def test_ffmpeg_error_message_survives_non_utf8_bytes(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: _Fake(b"", b"\x89 bad \xe5\xbe", 1))
    with pytest.raises(Exception) as ei:
        FFmpeg().run(["-i", "x"])
    assert "bad" in str(ei.value)


def test_espeak_uses_run_text(monkeypatch, tmp_path):
    monkeypatch.setattr(EspeakTTSProvider, "is_available", lambda self: True)
    captured = {}

    def fake_run_text(cmd, timeout=None, **kw):
        captured["cmd"] = cmd
        Path(cmd[cmd.index("-w") + 1]).write_bytes(b"RIFF" + b"\0" * 200)
        return proc.ProcResult(0, "", "")

    monkeypatch.setattr("see.providers.tts.espeak.run_text", fake_run_text)
    prov = EspeakTTSProvider()
    monkeypatch.setattr(prov.ffmpeg, "probe", lambda p: type("I", (), {"duration": 1.2, "sample_rate": 22050})())
    r = prov.synthesize(TTSRequest(text="你好"), tmp_path / "o.wav")
    assert r.duration == 1.2 and "你好" in captured["cmd"]


def test_numeric_failure_detection():
    ok = np.random.default_rng(0).random((8, 8, 3)).astype(np.float32)
    assert not is_numeric_failure(ok)
    assert is_numeric_failure(np.zeros((8, 8, 3), np.float32))
    nan = ok.copy(); nan[0, 0, 0] = np.nan
    assert is_numeric_failure(nan)


def test_gtx1650_plan_starts_with_fp32_vae_and_escalates():
    assert gpu_prefers_fp32_vae("NVIDIA GeForce GTX 1650") and not gpu_prefers_fp32_vae("NVIDIA GeForce RTX 3060")
    p = make_runtime_plan("cuda", 4096, 512, "NVIDIA GeForce GTX 1650")
    assert p.dtype == "float16" and p.vae_fp32 and p.low_vram
    p2 = p.downgrade_numeric()
    assert p2.dtype == "float32" and p2.cpu_offload and p2.max_side == 512
    assert p2.downgrade_numeric() is None
    rtx = make_runtime_plan("cuda", 12_000, 512, "RTX 3060")
    assert not rtx.vae_fp32 and rtx.downgrade_numeric().vae_fp32 and rtx.downgrade_numeric().dtype == "float16"


def test_memory_downgrade_keeps_vae_fp32():
    p = RuntimePlan("cuda", "float16", True, True, True, True, 512, vae_fp32=True)
    assert p.downgrade_memory().vae_fp32 and p.downgrade_memory().max_side == 384
