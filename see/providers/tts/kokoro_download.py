"""Kokoro v1.1-zh 權重下載器（只在使用者明確執行 `tts-download --yes` 時跑；PROJECT_RULES §10／D-027）。

寫入 provenance.json：repo、revision（commit sha）、每個檔案的 bytes 與 sha256、下載時間、授權、核准編號。
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from see.core.hashing import file_sha256
from see.providers.tts.kokoro import (
    APPROVAL,
    CONFIG_FILE,
    LICENSE,
    MODEL_FILE,
    PREFERRED_VOICES,
    PROVENANCE_FILE,
    REPO_ID,
    download_plan,
)


def plan_text(dest: Path) -> str:
    return json.dumps({"plan": download_plan(), "dest": str(dest)}, ensure_ascii=False, indent=2)


def choose_voices(repo_files: list[str], wanted: list[str] | None) -> list[str]:
    """repo 內實際存在的 voice；wanted 缺少時以前 2 個 zf_ 與前 2 個 zm_ 補足。"""
    available = sorted(Path(f).stem for f in repo_files if f.startswith("voices/") and f.endswith(".pt"))
    if wanted:
        missing = [v for v in wanted if v not in available]
        if missing:
            raise ValueError(f"voices not in {REPO_ID}: {missing}; available sample: {available[:10]}")
        return list(wanted)
    chosen = [v for v in PREFERRED_VOICES if v in available]
    if len(chosen) < 4:
        for prefix in ("zf_", "zm_"):
            for v in available:
                if v.startswith(prefix) and v not in chosen and sum(c.startswith(prefix) for c in chosen) < 2:
                    chosen.append(v)
    return chosen


def write_provenance(dest: Path, revision: str | None, files: list[Path], extra: dict[str, Any] | None = None) -> dict[str, Any]:
    prov = {"repo_id": REPO_ID, "revision": revision, "license": LICENSE, "approval": APPROVAL,
            "downloaded_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "files": {str(f.relative_to(dest)).replace("\\", "/"): {"bytes": f.stat().st_size, "sha256": file_sha256(f)} for f in files},
            **(extra or {})}
    prov["total_mb"] = round(sum(v["bytes"] for v in prov["files"].values()) / 1e6, 1)
    (dest / PROVENANCE_FILE).write_text(json.dumps(prov, ensure_ascii=False, indent=2), encoding="utf-8")
    return prov


def download_kokoro(dest: Path, voices: list[str] | None = None) -> dict[str, Any]:
    """實際下載（需 huggingface_hub）。只抓 config、模型、指定 voices；不抓其他檔。"""
    from huggingface_hub import HfApi, hf_hub_download  # type: ignore

    dest.mkdir(parents=True, exist_ok=True)
    (dest.parent / ".gitignore").write_text("*\n", encoding="utf-8")  # 模型資料夾永不進 Git
    api = HfApi()
    info = api.model_info(REPO_ID, files_metadata=False)
    repo_files = [s.rfilename for s in (info.siblings or [])]
    chosen = choose_voices(repo_files, voices)
    targets = [CONFIG_FILE, MODEL_FILE] + [f"voices/{v}.pt" for v in chosen]
    got: list[Path] = []
    for name in targets:
        p = hf_hub_download(repo_id=REPO_ID, filename=name, revision=info.sha, local_dir=str(dest))
        got.append(Path(p))
    return write_provenance(dest, info.sha, got, {"voices": chosen})
