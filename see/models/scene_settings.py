"""Scene 結構化設定（D-065）：把場景描述從一長串文字拆成可編輯、可覆寫、可局部重做的欄位。

- 欄位（全部可為 None＝未指定；**缺值不補造**）：
  場景 background／environment／location／time_of_day／weather；構圖 composition／framing／shot_size／camera_angle／focus_target；
  視覺 lighting／color_tone／mood。
- **不重複既有單一來源（SSOT）**：鏡頭運動＝既有 `Scene.camera_motion`（只影響影片片段）；視覺風格＝既有
  `Scene.preferences.visual_style_id`（StyleProfile 的 Scene override）。
- 每個欄位：preset（固定選項）或「自訂」中文（`custom_zh`）。preset → 英文詞是逐字直譯（確定性對照，非 AI）；自訂中文經
  prompt builder 關鍵詞對照，轉不到 → evidence `no_prompt_effect`。
- 與 Scene Character Override（表情、動作、服裝、位置…）分離：本模型不含任何角色欄位（extra="forbid"），兩者互不覆寫。
- 與 D-062 偏好層：Scene 結構化欄位是最具體的一層（Scene structured > Scene.preferences > Project.preferences），
  設定了 lighting／color_tone／mood／composition 就取代同名偏好維度；shot_size／camera_angle 取代偏好的 camera 維度。
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

# 欄位 → {preset: (中文標籤, 英文 prompt 詞)}；空 dict＝只收自訂中文
PRESETS: dict[str, dict[str, tuple[str, str]]] = {
    "background": {},
    "environment": {"indoor": ("室內", "indoor scene"), "outdoor": ("戶外", "outdoor scene"), "city": ("城市", "city street"),
                    "countryside": ("鄉村", "countryside"), "forest": ("森林", "forest"), "seaside": ("海邊", "seaside"),
                    "mountain": ("山區", "mountains")},
    "location": {},
    "time_of_day": {"dawn": ("清晨", "early morning, dawn"), "morning": ("上午", "morning"), "noon": ("正午", "midday"),
                    "afternoon": ("下午", "afternoon"), "dusk": ("黃昏", "dusk, sunset"), "night": ("夜晚", "night")},
    "weather": {"sunny": ("晴天", "sunny"), "cloudy": ("陰天", "overcast sky"), "rain": ("下雨", "rainy"), "snow": ("下雪", "snowy"),
                "fog": ("起霧", "foggy"), "storm": ("暴風雨", "stormy")},
    "composition": {"centered": ("置中", "centered composition"), "rule_of_thirds": ("三分法", "rule of thirds composition"),
                    "symmetrical": ("對稱", "symmetrical composition"), "leading_lines": ("引導線", "leading lines"),
                    "negative_space": ("留白", "negative space")},
    "framing": {"tight": ("緊湊", "tight framing"), "loose": ("寬鬆", "loose framing"),
                "frame_within_frame": ("框中框", "frame within a frame"), "over_the_shoulder": ("過肩", "over-the-shoulder shot")},
    "shot_size": {"extreme_close_up": ("大特寫", "extreme close-up"), "close_up": ("特寫", "close-up shot"),
                  "medium_close_up": ("近景", "medium close-up shot"), "medium": ("中景", "medium shot"), "full": ("全景", "full shot"),
                  "wide": ("遠景", "wide shot"), "extreme_wide": ("大遠景", "extreme wide shot")},
    "camera_angle": {"eye_level": ("平視", "eye-level shot"), "high_angle": ("俯角", "high-angle shot"), "low_angle": ("仰角", "low-angle shot"),
                     "birds_eye": ("鳥瞰", "bird's-eye view"), "dutch_angle": ("傾斜", "dutch angle")},
    "focus_target": {},
    "lighting": {"soft": ("柔光", "soft lighting"), "natural": ("自然光", "natural light"), "golden_hour": ("黃金時刻", "golden hour lighting"),
                 "backlit": ("逆光", "backlit"), "dramatic": ("戲劇性光影", "dramatic lighting"), "neon": ("霓虹", "neon lighting"),
                 "candlelight": ("燭光", "candlelight"), "dim": ("昏暗", "dim lighting")},
    "color_tone": {"warm": ("暖色調", "warm color palette"), "cool": ("冷色調", "cool color palette"), "neutral": ("中性", "neutral colors"),
                   "vivid": ("鮮豔", "vivid colors"), "muted": ("低飽和", "muted colors"), "monochrome": ("黑白", "monochrome"),
                   "pastel": ("粉彩", "pastel colors")},
    "mood": {"warm": ("溫馨", "warm atmosphere"), "horror": ("恐怖", "horror atmosphere"), "sunny": ("陽光", "cheerful sunny mood"),
             "sad": ("悲傷", "melancholic mood"), "romantic": ("浪漫", "romantic atmosphere"), "suspense": ("懸疑", "suspenseful atmosphere")},
}
FIELDS = tuple(PRESETS)
# prompt 固定順序：場景 → 視覺 → 構圖
PROMPT_ORDER = ("background", "environment", "location", "time_of_day", "weather", "lighting", "color_tone", "mood",
                "composition", "framing", "shot_size", "camera_angle", "focus_target")
LABELS_ZH: dict[str, str] = {"background": "背景", "environment": "環境", "location": "地點", "time_of_day": "時間", "weather": "天氣",
                             "composition": "構圖", "framing": "取景", "shot_size": "景別", "camera_angle": "鏡頭角度",
                             "focus_target": "焦點", "lighting": "光線", "color_tone": "色調", "mood": "氣氛"}
GROUPS: dict[str, tuple[str, ...]] = {"場景": ("background", "environment", "location", "time_of_day", "weather"),
                                      "構圖": ("composition", "framing", "shot_size", "camera_angle", "focus_target"),
                                      "視覺": ("lighting", "color_tone", "mood")}
# Scene 結構化欄位 → 被取代的 D-062 偏好維度
OVERRIDES_PREFERENCE: dict[str, str] = {"lighting": "lighting", "color_tone": "color_tone", "mood": "mood",
                                        "composition": "composition", "shot_size": "camera", "camera_angle": "camera"}
FOCUS_PREFIX = "focus on"


class SceneTerm(BaseModel):
    """preset（固定選項 key）或 preset="custom"＋custom_zh（中文）。只填 custom_zh 視為自訂。"""

    model_config = ConfigDict(extra="forbid")

    preset: str | None = Field(default=None, max_length=40)
    custom_zh: str = Field(default="", max_length=120)

    @model_validator(mode="after")
    def _normalize(self) -> SceneTerm:
        self.custom_zh = self.custom_zh.strip()
        if self.preset in (None, "") and self.custom_zh:
            self.preset = "custom"
        if self.preset == "":
            self.preset = None
        if self.preset == "custom" and not self.custom_zh:
            raise ValueError("preset 'custom' requires custom_zh")
        if self.preset not in (None, "custom") and self.custom_zh:
            raise ValueError("custom_zh is only allowed with preset 'custom'")
        return self

    @property
    def is_empty(self) -> bool:
        return self.preset is None


class SceneSettings(BaseModel):
    """Scene 結構化設定；None＝未指定（不補值）。"""

    model_config = ConfigDict(extra="forbid")

    background: SceneTerm | None = None
    environment: SceneTerm | None = None
    location: SceneTerm | None = None
    time_of_day: SceneTerm | None = None
    weather: SceneTerm | None = None
    composition: SceneTerm | None = None
    framing: SceneTerm | None = None
    shot_size: SceneTerm | None = None
    camera_angle: SceneTerm | None = None
    focus_target: SceneTerm | None = None
    lighting: SceneTerm | None = None
    color_tone: SceneTerm | None = None
    mood: SceneTerm | None = None

    @model_validator(mode="after")
    def _known_presets(self) -> SceneSettings:
        for f in FIELDS:
            t = getattr(self, f)
            if t is not None and t.is_empty:
                setattr(self, f, None)  # 空項目＝未指定
                continue
            if t is not None and t.preset != "custom" and t.preset not in PRESETS[f]:
                allowed = sorted(PRESETS[f]) + ["custom"] if PRESETS[f] else ["custom（只收中文自訂）"]
                raise ValueError(f"{f}: unknown preset {t.preset!r}; allowed: {allowed}")
        return self

    @property
    def is_empty(self) -> bool:
        return all(getattr(self, f) is None for f in FIELDS)

    def set_fields(self) -> list[str]:
        return [f for f in FIELDS if getattr(self, f) is not None]
