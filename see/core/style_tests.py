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
    # D-041：構圖／鏡頭需求（例如正面胸像）是 Mock LLM 關鍵詞表無法表達的；案例可自帶英文 base prompt。
    # 屬於「案例定義」而非臨時覆寫 → 仍算 fair_comparison；風格詞仍由 Style Profile 附加，模型由 --checkpoint 決定。
    base_prompt_en: str | None = None
    review_checklist: tuple[str, ...] = field(default_factory=tuple)  # 人工審圖項目（主觀驗收清單）


STYLE_TEST_CASES: dict[str, StyleTestCase] = {c.case_id: c for c in [
    StyleTestCase("kitten_butterfly", "小貓咪在院子裡追蝴蝶，陽光很溫暖", ("a kitten", "butterflies", "a courtyard"),
                  notes="E2-4 公平比較基準案例（D-033）", tags=("animal", "outdoor")),
    StyleTestCase("girl_city_night", "一個女孩站在城市的街道上，夜晚", ("a girl", "a city", "night"),
                  notes="人物案例：P1 日系動畫／AI 真人／電影感需要人物（D-034）", tags=("human", "outdoor")),
    StyleTestCase(
        "girl_portrait_closeup", "一個女孩的正面半身近景，看著鏡頭，臉部清楚，背景是模糊的城市夜景",
        ("girl", "upper body", "front view", "looking at viewer", "face"),
        notes="人物近景品質（D-041）：girl_city_night 實測為背面遠景、臉不可見 → 專驗臉／眼／五官／頭髮（手若入鏡一併觀察）；"
              "與模型、風格無關的中性構圖描述，可用於任何 Style Profile／checkpoint",
        tags=("human", "portrait", "face_quality"),
        base_prompt_en=("a girl, upper body portrait, front view, facing the camera, looking at viewer, "
                        "clear detailed face, detailed eyes, hair, city at night in the background, "
                        "blurred background, shallow depth of field"),
        review_checklist=("正面人物（非背面）", "半身或胸像，臉部佔畫面足夠比例", "眼睛（對稱、瞳孔、高光）",
                          "五官（鼻、嘴、臉型）", "頭髮（髮絲、輪廓）", "手部（若入鏡）", "背景未搶過人物",
                          "整體明暗（黑色比例觀察）")),
]}
DEFAULT_CASE = "kitten_butterfly"


def get_case(case_id: str) -> StyleTestCase:
    if case_id not in STYLE_TEST_CASES:
        raise ValueError(f"unknown style-test case '{case_id}'; available: {sorted(STYLE_TEST_CASES)}")
    return STYLE_TEST_CASES[case_id]


def case_base_prompt(case: StyleTestCase, scene_override: str | None, build_from_zh) -> tuple[str, str]:
    """回傳 (base_prompt, 來源)。scene 覆寫 → Mock 關鍵詞；案例自帶英文 → 用它；否則以案例中文場景走 Mock 關鍵詞。"""
    if scene_override:
        return build_from_zh(scene_override), "scene_override"
    if case.base_prompt_en:
        return case.base_prompt_en, "case_base_prompt_en"
    return build_from_zh(case.scene_zh), "case_scene_zh"


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
