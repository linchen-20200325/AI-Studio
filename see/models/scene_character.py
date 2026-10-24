"""Scene Character Override（D-063）：每一幕的人物演出設定（表情／情緒／動作／視線／姿勢／本幕服裝／位置／景深）。

- 與角色永久設定分離（PROJECT_RULES §17.9）：臉型、五官、髮型、基本服裝、default voice／style 在 CharacterDefinition／
  CharacterAppearance；這裡只描述「這一幕」，**不會也不得**寫回角色預設（outfit_override 只屬於本幕）。
- 結構化欄位只在使用者明確選擇／填寫時成立；`raw_character_direction_zh` 只保存使用者的中文原話，
  目前沒有可靠解析（無 LLM）→ 不自動拆成欄位、不進 prompt（evidence 標 raw_direction_applied=false）。
- 不推論性別／國籍／敏感身份；欄位都是演出指示，不是身份。
- preset 的英文詞是逐字直譯（表情「微笑」→ smiling），不是風格化文案；「自訂」中文經 prompt builder 轉換，
  轉換不到就照實標 no_prompt_effect（missing ≠ success）。
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

PROJECT_CHAR_ID = r"^[A-Za-z0-9_-]{1,64}$"  # 與 Project.characters／Scene.character_ids 相同格式


class Horizontal(str, Enum):
    left = "left"
    center = "center"
    right = "right"


class Depth(str, Enum):
    foreground = "foreground"
    midground = "midground"
    background = "background"


class Expression(str, Enum):
    smile = "smile"
    serious = "serious"
    afraid = "afraid"
    sad = "sad"
    angry = "angry"
    surprised = "surprised"
    indifferent = "indifferent"
    custom = "custom"


class Emotion(str, Enum):
    nervous = "nervous"
    relaxed = "relaxed"
    happy = "happy"
    sad = "sad"
    angry = "angry"
    afraid = "afraid"
    romantic = "romantic"
    suspense = "suspense"
    custom = "custom"


class Action(str, Enum):
    standing = "standing"
    walking = "walking"
    looking_back = "looking_back"
    raising_hand = "raising_hand"
    clenching_fist = "clenching_fist"
    hugging = "hugging"
    running = "running"
    looking_at_phone = "looking_at_phone"
    custom = "custom"


class Gaze(str, Enum):
    at_camera = "at_camera"
    at_character = "at_character"
    at_object = "at_object"
    into_distance = "into_distance"
    downward = "downward"
    custom = "custom"


class Pose(str, Enum):
    frontal = "frontal"
    side = "side"
    sitting = "sitting"
    crouching = "crouching"
    looking_back = "looking_back"
    head_down = "head_down"
    custom = "custom"


# 一般 UI 顯示用（繁體中文）；技術值只在 Advanced／evidence
LABELS_ZH: dict[str, dict[str, str]] = {
    "expression": {"smile": "微笑", "serious": "嚴肅", "afraid": "害怕", "sad": "悲傷", "angry": "憤怒", "surprised": "驚訝",
                   "indifferent": "冷漠", "custom": "自訂"},
    "emotion": {"nervous": "緊張", "relaxed": "放鬆", "happy": "開心", "sad": "悲傷", "angry": "憤怒", "afraid": "害怕",
                "romantic": "浪漫", "suspense": "懸疑感", "custom": "自訂"},
    "action": {"standing": "站立", "walking": "走路", "looking_back": "回頭", "raising_hand": "抬手", "clenching_fist": "握拳",
               "hugging": "擁抱", "running": "奔跑", "looking_at_phone": "看手機", "custom": "自訂"},
    "gaze": {"at_camera": "看鏡頭", "at_character": "看另一角色", "at_object": "看物品", "into_distance": "看遠方",
             "downward": "低頭", "custom": "自訂"},
    "pose": {"frontal": "正面", "side": "側身", "sitting": "坐姿", "crouching": "蹲下", "looking_back": "回頭",
             "head_down": "低頭", "custom": "自訂"},
    "placement": {"left": "左", "center": "中", "right": "右"},
    "depth": {"foreground": "前景", "midground": "中景", "background": "後景"},
}

# preset → 英文 prompt 詞（逐字直譯；custom 由 prompt builder 處理）
PROMPT_EN: dict[str, dict[str, str]] = {
    "expression": {"smile": "smiling", "serious": "serious expression", "afraid": "frightened expression", "sad": "sad expression",
                   "angry": "angry expression", "surprised": "surprised expression", "indifferent": "indifferent expression"},
    "emotion": {"nervous": "nervous", "relaxed": "relaxed", "happy": "happy", "sad": "sorrowful", "angry": "furious",
                "afraid": "fearful", "romantic": "romantic mood", "suspense": "suspenseful mood"},
    "action": {"standing": "standing", "walking": "walking", "looking_back": "looking back over the shoulder",
               "raising_hand": "raising one hand", "clenching_fist": "clenched fist", "hugging": "hugging", "running": "running",
               "looking_at_phone": "looking at a phone"},
    "gaze": {"at_camera": "looking at the viewer", "at_character": "looking at the other character", "at_object": "looking at an object",
             "into_distance": "gazing into the distance", "downward": "looking down"},
    "pose": {"frontal": "front view", "side": "side view", "sitting": "sitting", "crouching": "crouching",
             "looking_back": "turning back", "head_down": "head bowed"},
    "placement": {"left": "on the left side of the frame", "center": "in the center of the frame", "right": "on the right side of the frame"},
    "depth": {"foreground": "in the foreground", "midground": "in the middle ground", "background": "in the background"},
}

DIRECTION_FIELDS = ("expression", "emotion", "action", "gaze", "pose")


class _Choice(BaseModel):
    """preset 擇一；preset=custom 時必須填 custom_zh（使用者中文原話）。其他組合 fail closed。"""

    model_config = ConfigDict(extra="forbid")

    custom_zh: str = Field(default="", max_length=80)

    @model_validator(mode="after")
    def _custom_consistent(self):
        custom = self.preset.value == "custom"  # type: ignore[attr-defined]
        text = self.custom_zh.strip()
        if custom and not text:
            raise ValueError("preset 'custom' requires custom_zh")
        if not custom and text:
            raise ValueError("custom_zh is only allowed with preset 'custom'")
        self.custom_zh = text
        return self


class ExpressionChoice(_Choice):
    preset: Expression


class EmotionChoice(_Choice):
    preset: Emotion


class ActionChoice(_Choice):
    preset: Action


class GazeChoice(_Choice):
    preset: Gaze
    target_character_id: str | None = Field(default=None, pattern=PROJECT_CHAR_ID, description="preset=at_character 時看誰（選填）")

    @model_validator(mode="after")
    def _target_only_for_character(self):
        if self.target_character_id is not None and self.preset != Gaze.at_character:
            raise ValueError("target_character_id is only allowed with gaze 'at_character'")
        return self


class PoseChoice(_Choice):
    preset: Pose


class SceneCharacter(BaseModel):
    """某角色在某一幕的演出覆寫。全部欄位可選：None／空＝本幕不指定（沿用畫面描述與角色預設）。"""

    model_config = ConfigDict(extra="forbid")

    character_id: str = Field(pattern=PROJECT_CHAR_ID)
    display_name: str = Field(default="", max_length=64, description="本幕顯示名稱（只供顯示；不改角色資料、不進 prompt）")
    expression: ExpressionChoice | None = None
    emotion: EmotionChoice | None = None
    action: ActionChoice | None = None
    gaze: GazeChoice | None = None
    pose: PoseChoice | None = None
    outfit_override: str = Field(default="", max_length=120, description="本幕服裝（中文）；不寫回角色 default outfit")
    placement: Horizontal | None = None
    depth: Depth | None = None
    notes: str = Field(default="", max_length=300, description="備註（不進 prompt）")
    raw_character_direction_zh: str = Field(default="", max_length=500, description="使用者中文人物描述原文（只保存；尚無可靠解析）")


# 子欄位 → 是否影響圖片（再生成範圍；display_name／notes／raw direction 目前不影響任何產物）
SCENE_CHARACTER_IMAGE_FIELDS = (*DIRECTION_FIELDS, "outfit_override", "placement", "depth")
SCENE_CHARACTER_INERT_FIELDS = ("display_name", "notes", "raw_character_direction_zh")
