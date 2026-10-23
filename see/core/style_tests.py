"""Style 真機驗收的測試案例與分層判定（D-035）。

分層（不得互相推論）：
- `technical_valid`：**自動**判定——真模型（diffusers）生成、非 placeholder、非黑圖、非單色平面。只證明「產生了一張
  技術上有效的圖」，**不代表** scene／style 通過。
- `prompt_subject_check`：**自動**、確定性——預期主體（英文）是否真的出現在送進模型的 prompt。只驗證 prompt 管線，不驗證影像。
- `scene_validated`／`style_validated`：**人工**判定（`style-review`），預設 None（尚未審）。目前沒有可靠的免費自動
  視覺評估，不以啟發式分數冒充。

案例與風格分離：新增風格只需在 `see/core/styles.py` 加 StyleProfile；新增案例只需在這裡加 StyleTestCase。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class StyleTestCase:
    case_id: str
    scene_zh: str
    expected_subjects_en: tuple[str, ...]  # 人工審圖清單＋prompt 自動檢查用
    seed: int = 1234
    notes: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)


STYLE_TEST_CASES: dict[str, StyleTestCase] = {c.case_id: c for c in [
    StyleTestCase("kitten_butterfly", "小貓咪在院子裡追蝴蝶，陽光很溫暖", ("a kitten", "butterflies", "a courtyard"),
                  notes="E2-4 公平比較基準案例（D-033）", tags=("animal", "outdoor")),
    StyleTestCase("girl_city_night", "一個女孩站在城市的街道上，夜晚", ("a girl", "a city", "night"),
                  notes="人物案例：P1 日系動畫／AI 真人／電影感需要人物（D-034）", tags=("human", "outdoor")),
]}
DEFAULT_CASE = "kitten_butterfly"


def get_case(case_id: str) -> StyleTestCase:
    if case_id not in STYLE_TEST_CASES:
        raise ValueError(f"unknown style-test case '{case_id}'; available: {sorted(STYLE_TEST_CASES)}")
    return STYLE_TEST_CASES[case_id]


def prompt_subject_check(prompt: str, expected: tuple[str, ...]) -> dict[str, Any]:
    low = prompt.lower()
    missing = [e for e in expected if e.lower() not in low]
    return {"expected": list(expected), "missing": missing, "passed": not missing}


def technical_validity(generated_by: str, stats: dict[str, Any]) -> dict[str, Any]:
    reasons = []
    if not generated_by.startswith("diffusers"):
        reasons.append(f"not a real model output (generated_by={generated_by})")
    if stats.get("is_black"):
        reasons.append("black image")
    if stats.get("is_flat"):
        reasons.append("flat image")
    return {"technical_valid": not reasons, "technical_reasons": reasons}


VERDICTS = ("pass", "fail")


def verdict_to_bool(v: str | None) -> bool | None:
    if v is None:
        return None
    if v not in VERDICTS:
        raise ValueError(f"verdict must be one of {VERDICTS}")
    return v == "pass"
