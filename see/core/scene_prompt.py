"""Scene → 模型英文 prompt 的 prompt builder（D-063）。一般使用者只寫中文；英文 prompt 是內部實作細節。

流程：`image_prompt_zh` →（PromptTranslator）→ 英文 base prompt ＋ 本幕人物演出詞 → image provider。

- **目前沒有 AI 翻譯**：預設 translator 是 `KeywordFallbackTranslator`（既有 Mock 關鍵詞對照，確定性），會漏詞；
  evidence 一律標 `ai_translated=false`、命中的詞與是否落到通用描述，不假裝品質。
  未來 LLM translator 只要實作 `PromptTranslator`（name／ai_translated／translate）即可替換，呼叫端不變。
- 來源（prompt_source.source）：
  - `zh_generated`：有中文圖片描述 → 由 translator 產生（此時 image_prompt_en／image_prompt 不使用）。
  - `legacy_en`：無中文、有 image_prompt_en（舊 Scene、Mock storyboard 產生）→ 原樣使用（fingerprint 不變）。
  - `legacy_image_prompt`：兩者皆空 → image_prompt。
  - `advanced_override`：**保留名稱、尚未實作**（進階覆寫的優先序無規格；Advanced 目前只讀）。
- 舊 Scene（無 image_prompt_zh、無 characters）→ prompt 與 Phase 1 完全相同。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from see.core.prompting import build_image_prompt_en, zh_to_en_keywords
from see.models.scene import Scene
from see.models.scene_character import DIRECTION_FIELDS, PROMPT_EN, SceneCharacter

PROMPT_SOURCES = ("zh_generated", "legacy_en", "legacy_image_prompt", "advanced_override")


@dataclass(frozen=True)
class Translation:
    text_en: str  # 轉換結果；空字串＝沒有可用英文詞
    matched_terms: tuple[str, ...] = field(default_factory=tuple)


class PromptTranslator(Protocol):
    """中文 → 模型英文詞的 service contract（provider-agnostic）。"""

    name: str
    ai_translated: bool

    def translate_scene(self, text_zh: str) -> Translation: ...  # 整段畫面描述 → 完整 base prompt
    def translate_terms(self, text_zh: str) -> Translation: ...  # 短語（自訂表情、本幕服裝）→ 英文詞；可為空


class KeywordFallbackTranslator:
    """確定性關鍵詞對照（see.core.prompting）。不是翻譯：只抓字典裡有的名詞／場景詞。"""

    name = "keyword_fallback_v1"
    ai_translated = False

    def translate_scene(self, text_zh: str) -> Translation:
        kws = tuple(zh_to_en_keywords(text_zh))
        return Translation(build_image_prompt_en(text_zh), kws)

    def translate_terms(self, text_zh: str) -> Translation:
        kws = tuple(zh_to_en_keywords(text_zh, limit=4))
        return Translation(", ".join(kws), kws)


DEFAULT_TRANSLATOR = KeywordFallbackTranslator()


def base_prompt(scene: Scene, translator: PromptTranslator = DEFAULT_TRANSLATOR) -> tuple[str, dict[str, Any]]:
    """回傳 (英文 base prompt, prompt_source evidence)。"""
    zh = scene.image_prompt_zh.strip()
    if zh:
        t = translator.translate_scene(zh)
        return t.text_en, {"source": "zh_generated", "translator": translator.name, "ai_translated": translator.ai_translated,
                           "matched_terms": list(t.matched_terms), "generic_fallback": not t.matched_terms,
                           "shadowed": [k for k in ("image_prompt_en", "image_prompt") if getattr(scene, k).strip()]}
    if scene.image_prompt_en.strip():
        return scene.image_prompt_en.strip(), {"source": "legacy_en", "translator": None, "ai_translated": False}
    return scene.image_prompt, {"source": "legacy_image_prompt", "translator": None, "ai_translated": False}


def character_terms(sc: SceneCharacter, translator: PromptTranslator = DEFAULT_TRANSLATOR) -> tuple[list[str], dict[str, Any]]:
    """一位角色的本幕演出詞（固定順序：位置 → 景深 → 表情 → 情緒 → 動作 → 視線 → 姿勢 → 服裝）。
    回傳 (英文詞, evidence)。display_name／notes／raw direction 不進 prompt。"""
    terms: list[str] = []
    applied: list[str] = []
    no_effect: list[str] = []
    for f in ("placement", "depth"):
        v = getattr(sc, f)
        if v is not None:
            terms.append(PROMPT_EN[f][v.value])
            applied.append(f)
    for f in DIRECTION_FIELDS:
        c = getattr(sc, f)
        if c is None:
            continue
        if c.preset.value == "custom":
            t = translator.translate_terms(c.custom_zh)
            if t.text_en:
                terms.append(t.text_en)
                applied.append(f)
            else:
                no_effect.append(f)
        else:
            terms.append(PROMPT_EN[f][c.preset.value])
            applied.append(f)
    if sc.outfit_override.strip():
        t = translator.translate_terms(sc.outfit_override)
        if t.text_en:
            terms.append(f"wearing {t.text_en}")
            applied.append("outfit_override")
        else:
            no_effect.append("outfit_override")
    return terms, {"character_id": sc.character_id, "applied_fields": applied, "no_prompt_effect": no_effect,
                   "raw_direction_saved": bool(sc.raw_character_direction_zh.strip()), "raw_direction_applied": False}


def scene_prompt(scene: Scene, translator: PromptTranslator = DEFAULT_TRANSLATOR) -> tuple[str, dict[str, Any]]:
    """base prompt ＋ 各角色演出詞（角色間以 '; ' 分隔）。SD1.5 不保證把詞綁到正確角色（DG-24／D-061 限制）。"""
    prompt, source = base_prompt(scene, translator)
    evidence = []
    clauses = []
    for sc in scene.characters:
        terms, ev = character_terms(sc, translator)
        evidence.append(ev)
        if terms:
            clauses.append(", ".join(terms))
    if clauses:
        prompt = ", ".join([prompt, "; ".join(clauses)])
    return prompt, {"prompt_source": source, "scene_characters": evidence}
