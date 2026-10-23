"""跨平台 subprocess 封裝：永遠以 UTF-8 解碼（errors=replace），不依賴 Windows 的 cp950 等 locale 編碼。

背景：Windows 上 `subprocess.run(text=True)` 會用 locale 編碼解碼子程序輸出；ffmpeg / espeak 的輸出是 UTF-8，
含中文或二進位片段時會在 reader thread 丟 UnicodeDecodeError（D-020）。
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass

ENCODING = "utf-8"


@dataclass(frozen=True)
class ProcResult:
    returncode: int
    stdout: str
    stderr: str


def run_text(cmd: list[str], timeout: float | None = None, check: bool = False, input_text: str | None = None) -> ProcResult:
    """執行命令並回傳 UTF-8 解碼（無法解碼的 byte 以 U+FFFD 取代）的結果。例外原樣拋出給呼叫端處理。"""
    proc = subprocess.run(cmd, capture_output=True, timeout=timeout, input=input_text.encode(ENCODING) if input_text else None)
    out = proc.stdout.decode(ENCODING, errors="replace") if proc.stdout else ""
    err = proc.stderr.decode(ENCODING, errors="replace") if proc.stderr else ""
    if check and proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, cmd, output=out, stderr=err)
    return ProcResult(proc.returncode, out, err)


def ensure_utf8_stdio() -> None:
    """讓 CLI 在 Windows 主控台也能印中文／符號（cp950 下 print 會 UnicodeEncodeError）。"""
    import sys

    for stream in (sys.stdout, sys.stderr):
        try:
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError, OSError):
            pass
