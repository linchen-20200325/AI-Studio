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

import dataclasses
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CaseCharacter:
    """多角色受控案例中的一個角色（D-049）。外觀走產品同一條路徑（CharacterAppearance／CharacterTraits → anchor_text），
    測試的就是產品實際送進模型的錨點，不另寫一套 prompt。`swap_checks`＝只屬於此角色、不得出現在另一角色身上的屬性。"""

    character_id: str
    position: str  # 構圖位置描述（英文），例 "on the left"
    appearance: dict[str, Any]  # CharacterAppearance kwargs；traits 以 dict 給
    swap_checks: tuple[str, ...]

    @property
    def anchor(self) -> str:
        from see.models.project import CharacterAppearance

        return CharacterAppearance(**self.appearance).anchor_text


# D-056：構圖位置 → 左→右欄位順序。S4 identity 的 mask 由此「明確」決定，不依賴 characters tuple 的排列順序。
REGION_ORDER = {"on the left": ("left", 0), "in the center": ("center", 1), "in the middle": ("center", 1),
                "on the right": ("right", 2)}


def region_of(position: str) -> tuple[str, int]:
    """位置描述 → (region 名稱, 左→右排序鍵)；未知位置 fail-closed（不猜）。"""
    key = (position or "").strip().lower()
    if key not in REGION_ORDER:
        raise ValueError(f"unknown character position '{position}'; known: {sorted(REGION_ORDER)}")
    return REGION_ORDER[key]


def multi_character_prompt(chars: tuple[CaseCharacter, ...], composition: str) -> str:
    """確定性組裝：人數 → 每個角色「錨點 + 位置」→ 共用構圖詞。"""
    count = {2: "two people", 3: "three people"}.get(len(chars), f"{len(chars)} people")
    return ", ".join([f"{count} side by side"] + [f"{c.anchor} {c.position}" for c in chars] + [composition])


# S2（D-051）：regional 用的共用構圖（與 multi_character_prompt 的 composition 相同來源，由案例保存）
def regional_prompts(case: "StyleTestCase") -> tuple[str, list[str]]:
    """回傳 (base, [region_i])。base＝人數＋共用構圖（**不含任何角色屬性**，避免屬性經 base 洩漏）；
    region_i＝該角色錨點＋共用構圖（只含自己的屬性）。Style Profile 詞由呼叫端各自附加。"""
    if not case.characters or not case.composition_en:
        raise ValueError(f"case {case.case_id} has no characters/composition for regional prompting")
    count = {2: "two people", 3: "three people"}.get(len(case.characters), f"{len(case.characters)} people")
    return f"{count} side by side, {case.composition_en}", [f"{c.anchor}, {case.composition_en}" for c in case.characters]


@dataclass(frozen=True)
class StyleTestCase:
    case_id: str
    scene_zh: str
    expected_subjects_en: tuple[str, ...]  # 人工審圖清單＋prompt 自動檢查用
    seed: int = 1234
    notes: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)
    # D-041：構圖／鏡頭需求（例如正面胸像）是 Mock LLM 關鍵詞表無法表達的；案例可自帶英文 base prompt。
    # 屬於「案例定義」而非臨時覆寫 → 仍算 baseline_condition；風格詞仍由 Style Profile 附加，模型由 --checkpoint 決定。
    base_prompt_en: str | None = None
    review_checklist: tuple[str, ...] = field(default_factory=tuple)  # 人工審圖項目（主觀驗收清單）
    characters: tuple[CaseCharacter, ...] = field(default_factory=tuple)  # D-049：多角色受控案例
    composition_en: str = ""  # D-051：多角色案例的共用構圖詞（regional prompting 用）


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
    # D-046：人物多樣性受控案例——與 girl_portrait_closeup 只差「人物描述」一詞組（構圖／鏡頭／背景詞完全相同），
    # 避免把族群寫成固定臉型：只寫可觀察的地區外貌描述＋成人，不加刻板五官詞。產品不以任何性別／族群為預設（§16）。
    *[StyleTestCase(
        cid, zh, (subj, "upper body", "front view", "looking at viewer", "face"),
        notes=f"人物多樣性（D-046）：{label}；與 girl_portrait_closeup 同構圖，只換人物描述",
        tags=("human", "portrait", "face_quality", "diversity"),
        base_prompt_en=(f"{subj}, upper body portrait, front view, facing the camera, looking at viewer, "
                        "clear detailed face, detailed eyes, hair, city at night in the background, "
                        "blurred background, shallow depth of field"),
        review_checklist=("人物描述是否符合（性別呈現／東亞外貌，非西方臉孔）", "正面人物、半身或胸像", "眼睛（對稱、瞳孔、高光）",
                          "五官（鼻、嘴、臉型）", "頭髮", "手部（若入鏡）", "背景未搶過人物", "整體明暗"))
      for cid, zh, subj, label in (
          ("east_asian_female_portrait", "一位東亞成年女性的正面半身近景，看著鏡頭，臉部清楚，背景是模糊的城市夜景",
           "an East Asian adult woman", "東亞女性"),
          ("east_asian_male_portrait", "一位東亞成年男性的正面半身近景，看著鏡頭，臉部清楚，背景是模糊的城市夜景",
           "an East Asian adult man", "東亞男性"))],
]}

# D-049：A／B 雙人同框受控案例。兩人屬性刻意「互斥」（性別呈現、髮長、髮色、服裝顏色與款式、眼鏡只在 B），
# 人工審圖才判斷得出是否互換／混合；構圖詞取 portrait 系列子集（正面、半身、看鏡頭、模糊城市夜景）以減少變因。
# 只是受控測試設定：不代表產品預設角色、性別、族群或外觀（PROJECT_RULES §16）。
_AB_CHARS = (
    CaseCharacter("char_a", "on the left",
                  {"outfit_en": "red coat", "traits": {"gender_presentation": "woman", "appearance_region": "East Asian",
                                                       "hair_style": "long straight", "hair_color": "black"}},
                  ("woman", "long straight black hair", "red coat")),
    CaseCharacter("char_b", "on the right",
                  {"outfit_en": "grey suit", "traits": {"gender_presentation": "man", "appearance_region": "East Asian",
                                                        "hair_style": "short", "hair_color": "grey",
                                                        "distinctive_marks": ["round glasses"]}},
                  ("man", "short grey hair", "grey suit", "round glasses")),
)
_AB_COMPOSITION = "upper body, front view, looking at viewer, city at night in the background, blurred background"
_AB = StyleTestCase(
    "two_characters_ab", "兩位東亞成年人並肩站立的正面半身近景：左邊黑長直髮紅大衣的女性、右邊灰短髮戴圓眼鏡穿灰西裝的男性，背景模糊城市夜景",
    ("two people", "woman", "man", "red coat", "grey suit", "round glasses"),
    notes="Multi-character 受控案例（D-049）：驗證 A／B 是否互換臉／髮／衣服／配件；構圖詞為 portrait 系列精簡子集（77 token 限制）",
    tags=("human", "multi_character", "identity_binding"),
    # CLIP 上限 77 token：兩組錨點較長 → 構圖詞取 portrait 系列的精簡子集，確保 Style Profile 詞不被截斷（真機 evidence 另記實測 token）
    base_prompt_en=multi_character_prompt(_AB_CHARS, _AB_COMPOSITION),
    review_checklist=("畫面恰為兩人（無多出人物、無融合肢體）", "左＝A 女性、右＝B 男性（位置是否對調）",
                      "A：黑色長直髮；B：灰色短髮（髮色／髮長是否互換或混合）",
                      "A：紅大衣；B：灰西裝（服裝是否互換或混合）", "圓眼鏡只在 B（是否出現在 A 或兩人都有／都沒有）",
                      "兩人臉部品質（眼睛、五官）", "兩人皆為東亞外貌（主觀）", "背景未搶過人物"),
    characters=_AB_CHARS, composition_en=_AB_COMPOSITION)
STYLE_TEST_CASES[_AB.case_id] = _AB

# D-057（DG-26 Route A）：A／B 各自「單人」生成（單色背景 → 可鍵控去背）＋無人背景，之後 compose-scene 合成。
# 角色定義沿用 _AB_CHARS（同一份結構化設定），只把位置改成 in the center；位置改由合成時的 placement 決定。
_ISO_COMPOSITION = "solo, upper body, front view, looking at viewer, plain light grey background, simple background, studio portrait"
for _c in _AB_CHARS:
    _iso = dataclasses.replace(_c, position="in the center")
    _case = StyleTestCase(
        f"ab_{_c.character_id}_isolated", f"two_characters_ab 的 {_c.character_id} 單人生成（單色背景，供去背合成）",
        tuple(_c.swap_checks) + ("solo", "plain light grey background"),
        notes="DG-26 Route A 角色層（D-057）：單人 identity fidelity 對照雙人 S4；背景必須單純才能零下載鍵控去背",
        tags=("human", "portrait", "layer", "identity_binding"),
        base_prompt_en=f"one person, {_iso.anchor}, {_ISO_COMPOSITION}",
        review_checklist=("畫面只有一人", "臉部是否像本角色 reference（identity fidelity，主觀）", "性別呈現／髮型／服裝符合本角色",
                          "背景是否為單純淺灰（影響去背）"),
        characters=(_iso,), composition_en=_ISO_COMPOSITION)
    STYLE_TEST_CASES[_case.case_id] = _case
_BG = StyleTestCase(
    "ab_background", "two_characters_ab 的背景層：無人的模糊城市夜景",
    ("city at night", "no people"),
    notes="DG-26 Route A 背景層（D-057）：不含人物，供 compose-scene 放置角色層",
    tags=("background", "layer"),
    base_prompt_en="city street at night, blurred background, bokeh lights, empty street, no people, nobody, eye level view",
    review_checklist=("畫面沒有人物", "城市夜景、背景模糊（角色貼上後不搶戲）"))
STYLE_TEST_CASES[_BG.case_id] = _BG
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


# ---------------------------------------------------------------- D-043 跨次比較條件（取代舊 fair_comparison 旗標）
# 舊 `fair_comparison` 只表示「這張是否為 fit 基準條件、無診斷覆寫」，native 一律 false、且完全不看 checkpoint／clip skip，
# 不能回答「兩張圖的比較是否只差一個變數」。改由兩份 evidence 逐項比對（相容舊 JSON）。
COMPARISON_FIELDS = ("case_id", "seed", "style_id", "base_prompt", "prompt", "negative_prompt", "request_size",
                     "gen_policy", "gen_size", "crop_box", "steps", "guidance", "scheduler", "final_dtype",
                     "model", "clip_skip_a1111", "prompt_mode", "identity_mode")
# 模型預設（D-042：模型專屬參數歸模型設定）——換 checkpoint 時隨模型改變屬「模型預設差異」，不是意外變數
MODEL_PRESET_FIELDS = ("clip_skip_a1111",)
BASE_MODEL = "sd15-base"
# 這些欄位缺值（兩邊都 None）就無法確認條件一致 → not_comparable；crop_box 在 fit 本來就是 None，不列入
REQUIRED_FIELDS = ("case_id", "seed", "prompt", "negative_prompt", "gen_size", "steps", "guidance", "scheduler", "model")


def comparison_conditions(ev: dict[str, Any]) -> dict[str, Any]:
    """從 style-test evidence 取出所有會影響輸出的條件。舊 JSON 沒有 clip skip 欄位時：無 checkpoint → 1（diffusers 預設＝不跳層）。"""
    g = ev.get("generation") or {}
    ck = ev.get("checkpoint") or None
    model = f"{ck.get('checkpoint_id')}@{str(ck.get('sha256', ''))[:12]}" if isinstance(ck, dict) else BASE_MODEL
    clip = g.get("clip_skip_a1111")
    if clip is None and model == BASE_MODEL:
        clip = 1
    gw, gh = g.get("gen_width"), g.get("gen_height")
    return {"case_id": ev.get("case_id"), "seed": ev.get("seed"), "style_id": ev.get("style_id"),
            "base_prompt": ev.get("base_prompt"), "prompt": ev.get("prompt"), "negative_prompt": ev.get("negative_prompt"),
            "request_size": f"{ev.get('width')}x{ev.get('height')}", "gen_policy": g.get("gen_policy"),
            "gen_size": f"{gw}x{gh}" if gw and gh else None,
            "crop_box": list(g["crop_box"]) if g.get("crop_box") is not None else None,
            "steps": g.get("steps"), "guidance": g.get("guidance"),
            "scheduler": g.get("scheduler_name") or g.get("scheduler"), "final_dtype": ev.get("final_dtype"),
            "model": model, "clip_skip_a1111": clip,
            # D-051：舊 JSON 沒有此欄位＝標準編碼（單段 77 token）
            "prompt_mode": g.get("prompt_mode") or "standard",
            # D-054：舊 JSON 沒有 identity＝none（只有文字錨點）
            "identity_mode": (g.get("identity") or {}).get("adapter_id") or "none"}


# 受控實驗可刻意改變的變數（D-052）：每次比較只能有其中一個不同
EXPERIMENT_FIELDS = ("model", "prompt_mode", "identity_mode")


def compare_conditions(a: dict[str, Any], b: dict[str, Any], intended: tuple[str, ...] | None = None) -> dict[str, Any]:
    """比對兩份 evidence。`intended`＝刻意改變的實驗變數：
    - None（預設，D-052）：自動判定——EXPERIMENT_FIELDS 中**恰好一個**不同時，它就是 intended；兩個以上同時不同 → 全列 unexpected
      （例：換 checkpoint 又換 prompt_mode 不是受控比較）。
    - 明確指定：只有列出的欄位可不同；指定多個且同時不同 → not_comparable（受控比較一次只改一個變數）。
    verdict：`single_variable`｜`model_preset_level`（換模型＋只差模型 preset 參數，如 clip skip）｜`not_comparable`。"""
    ca, cb = comparison_conditions(a), comparison_conditions(b)
    diffs = {k: [ca[k], cb[k]] for k in COMPARISON_FIELDS if ca[k] != cb[k]}
    unknown = [k for k in REQUIRED_FIELDS if ca[k] is None and cb[k] is None]
    if intended is None:
        exp = [k for k in EXPERIMENT_FIELDS if k in diffs]
        chosen, source = (tuple(exp), "auto") if len(exp) == 1 else ((), "auto")
    else:
        chosen, source = tuple(intended), "explicit"
    changed = [k for k in diffs if k in chosen]
    if len(changed) > 1:
        chosen, changed = (), []  # 一次只改一個變數；多個同時變 → 全部視為 unexpected
    preset = [k for k in diffs if k in MODEL_PRESET_FIELDS and "model" in changed]
    other = [k for k in diffs if k not in changed and k not in preset]
    if other or unknown:
        verdict = "not_comparable"
    elif preset:
        verdict = "model_preset_level"
    else:
        verdict = "single_variable"
    return {"verdict": verdict, "differences": diffs, "intended": changed, "intended_source": source,
            "model_preset_differences": preset, "unexpected_differences": other, "unknown_fields": unknown,
            "identical": [k for k in COMPARISON_FIELDS if k not in diffs and k not in unknown]}
