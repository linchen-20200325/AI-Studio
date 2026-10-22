"""Fingerprint：決定「是否需要重做」的唯一依據。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def fingerprint(*parts: Any) -> str:
    """把任意可 JSON 序列化的輸入做穩定 sha256。"""
    payload = json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def file_sha256(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def short_id(text: str, n: int = 10) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:n]
