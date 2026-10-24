"""Preference Layer（D-042／D-058 §17.5；D-062）：生成偏好的結構化資料（不是 prompt 字串），與角色身份分離。

- 偏好只描述「要什麼」：Visual Style、Mood、Lighting、Color Tone、Camera、Composition、Generation Settings。
  **不含** gender、character_id、identity reference 等身份資料（PROJECT_RULES §17；身份在 CharacterDefinition）。
- 解析順序（已有規格者）：Project default → Scene override，逐欄位：Scene 有設定（非 None）才覆寫。
  Character default（`CharacterDefinition.default_style_profile／default_mood_profile`）尚未參與解析：多角色同景時
  以哪個角色為準沒有規格 → 留待裁示（BACKLOG），不自行發明優先序。
- 預設全部 None：舊 Project／Scene 沒有這些欄位時行為完全相同、image fingerprint 不變。
- Mood 等 preset 只是標籤；preset → prompt 詞的對照尚無規格（需產品字句或 DG-10 LLM）→ 目前只有 `custom_en`
  （使用者自己寫的英文詞）會進 prompt。preset 有值但無 custom_en 時，evidence 會標 `no_prompt_effect`（missing ≠ success）。
"""
from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MoodPreset(str, Enum):
    """D-058 §17.6 E 列出的 Mood 選項（標籤；不含 prompt 詞對照）。"""

    warm = "warm"
    horror = "horror"
    sunny = "sunny"
    sad = "sad"
    romantic = "romantic"
    suspense = "suspense"
    custom = "custom"


def _terms(v: list[str]) -> list[str]:
    out = [t.strip() for t in v if t and t.strip()]
    for t in out:
        if len(t) > 80:
            raise ValueError("each term must be <= 80 chars")
    return out


class PreferenceTerms(BaseModel):
    """一個偏好維度：可選 preset 標籤＋使用者自訂英文詞（只有後者進 prompt）。"""

    model_config = ConfigDict(extra="forbid")

    preset: str | None = Field(default=None, max_length=40)
    custom_en: list[str] = Field(default_factory=list, max_length=8)

    @field_validator("custom_en")
    @classmethod
    def _clean(cls, v: list[str]) -> list[str]:
        return _terms(v)

    @property
    def prompt_terms(self) -> list[str]:
        return list(self.custom_en)


class MoodPref(PreferenceTerms):
    preset: MoodPreset | None = None  # type: ignore[assignment]


class GenerationSettings(BaseModel):
    """模型無關的生成設定。gen_policy：None＝沿用 provider 預設（production default 不變）。"""

    model_config = ConfigDict(extra="forbid")

    gen_policy: str | None = Field(default=None, pattern=r"^(fit|native)$")


DIMENSIONS = ("mood", "lighting", "color_tone", "camera", "composition")


class PreferenceSet(BaseModel):
    """Project default 或 Scene override。所有欄位 None＝未設定（不覆寫上一層）。
    extra="forbid"：身份資料（gender、character_id、reference…）不得混入偏好。"""

    model_config = ConfigDict(extra="forbid")

    visual_style_id: str | None = Field(default=None, min_length=1, max_length=64, description="StyleProfile id")
    mood: MoodPref | None = None
    lighting: PreferenceTerms | None = None
    color_tone: PreferenceTerms | None = None
    camera: PreferenceTerms | None = None
    composition: PreferenceTerms | None = None
    generation: GenerationSettings | None = None

    @property
    def is_empty(self) -> bool:
        return all(getattr(self, k) is None for k in type(self).model_fields)


def resolve(project_style_id: str, project_prefs: PreferenceSet | None, scene_prefs: PreferenceSet | None) -> dict[str, Any]:
    """Project default → Scene override（逐欄位）。回傳可序列化的 resolved snapshot（含每欄來源）。"""
    layers = [("project", project_prefs), ("scene", scene_prefs)]
    out: dict[str, Any] = {"visual_style_id": project_style_id, "sources": {"visual_style_id": "project.style_id"}}
    for name in ("visual_style_id", *DIMENSIONS, "generation"):
        for src, layer in layers:
            v = getattr(layer, name) if layer is not None else None
            if v is not None:
                out[name] = v.model_dump(mode="json") if isinstance(v, BaseModel) else v
                out["sources"][name] = src
    return out


def prompt_terms(resolved: dict[str, Any]) -> list[str]:
    """固定順序：mood → lighting → color_tone → camera → composition（只取 custom_en）。"""
    terms: list[str] = []
    for d in DIMENSIONS:
        terms += list((resolved.get(d) or {}).get("custom_en") or [])
    return terms


def no_prompt_effect(resolved: dict[str, Any]) -> list[str]:
    """有 preset 但沒有任何 custom_en 的維度 → 目前不影響生成（preset 詞對照尚無規格）。"""
    return [d for d in DIMENSIONS if (resolved.get(d) or {}).get("preset") and not (resolved.get(d) or {}).get("custom_en")]


def snapshot(resolved: dict[str, Any]) -> dict[str, Any]:
    """偏好快照（provenance）：resolved 內容＋穩定 hash。"""
    body = {k: v for k, v in resolved.items() if k != "sources"}
    digest = hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return {"preference_sha256": digest, "resolved": resolved, "no_prompt_effect": no_prompt_effect(resolved)}


# ---------------------------------------------------------------- 再生成範圍（依 pipeline 實際 fingerprint 相依推導）
# image fingerprint ← prompt／negative／style／偏好詞／生成設定；clip fingerprint ← image 檔 sha256＋narration＋subtitle＋video 參數；
# narration ← 旁白文字／voice／語速；subtitle ← 字幕文字＋旁白長度。lipsync ← clip。
SCENE_FIELD_IMPACT: dict[str, tuple[str, ...]] = {
    "image_prompt": ("image", "clip", "lipsync"), "image_prompt_en": ("image", "clip", "lipsync"),
    "negative_prompt": ("image", "clip", "lipsync"), "visual_description": ("image", "clip", "lipsync"),
    "character_ids": ("image", "clip", "lipsync"), "preferences": ("image", "clip", "lipsync"),
    "narration": ("narration", "subtitle", "clip", "lipsync"), "voice": ("narration", "clip", "lipsync"),
    "speech_speed": ("narration", "subtitle", "clip", "lipsync"), "narrator_id": ("narration", "clip", "lipsync"),
    "subtitle_override": ("subtitle", "clip", "lipsync"),
    "video_prompt": ("clip", "lipsync"), "camera_motion": ("clip", "lipsync"), "duration": ("clip", "lipsync"),
    "lipsync": ("lipsync",), "transition": ("render",), "audio_cues": ("render",),
    "image_prompt_zh": ("image", "clip", "lipsync"),  # D-063 中文圖片描述（prompt builder → image）
}
# D-063 Scene Character Override 子欄位（key 形如 characters.expression）：演出詞進 image prompt；
# display_name／notes／raw_character_direction_zh 目前不進任何產物 → 空範圍（改了不重做）。
_IMAGE_CHAIN = ("image", "clip", "lipsync")
SCENE_FIELD_IMPACT.update({f"characters.{f}": _IMAGE_CHAIN for f in (
    "expression", "emotion", "action", "gaze", "pose", "outfit_override", "placement", "depth")})
SCENE_FIELD_IMPACT.update({f"characters.{f}": () for f in ("display_name", "notes", "raw_character_direction_zh")})
SCENE_FIELD_IMPACT["characters"] = _IMAGE_CHAIN  # 整批覆寫（無法逐欄比對時的保守範圍）
# D-065 Scene 結構化設定：全部欄位都進 image prompt → image＋clip（＋lipsync）；鏡頭運動是既有 camera_motion（只影響 clip）
SCENE_FIELD_IMPACT.update({f"settings.{f}": _IMAGE_CHAIN for f in (
    "background", "environment", "location", "time_of_day", "weather", "composition", "framing", "shot_size", "camera_angle",
    "focus_target", "lighting", "color_tone", "mood")})
SCENE_FIELD_IMPACT["settings"] = _IMAGE_CHAIN


def settings_field_changes(before: dict[str, Any] | None, after: dict[str, Any] | None) -> list[str]:
    """Scene 結構化設定逐欄比對 → settings.<field>。"""
    b, a = before or {}, after or {}
    return sorted(f"settings.{k}" for k in set(b) | set(a) if (b.get(k) or a.get(k)) and b.get(k) != a.get(k))


def character_field_changes(before: list[dict[str, Any]], after: list[dict[str, Any]]) -> list[str]:
    """逐角色比對 Scene Character Override → 改變的子欄位 key（characters.<field>）。新增／移除角色＝該角色有值的子欄位。"""
    b = {c["character_id"]: c for c in before}
    a = {c["character_id"]: c for c in after}
    out: set[str] = set()
    for cid in set(a) | set(b):
        x, y = b.get(cid, {}), a.get(cid, {})
        for k in (set(x) | set(y)) - {"character_id"}:
            if x.get(k) or y.get(k):
                if x.get(k) != y.get(k):
                    out.add(f"characters.{k}")
    return sorted(out)
ASSET_ORDER = ("image", "narration", "subtitle", "clip", "lipsync", "render")


def regeneration_scope(changed_fields: list[str] | set[str]) -> dict[str, Any]:
    """改了哪些 Scene 欄位 → 哪些產物要重做（其餘沿用快取）。render＝重新組裝 preview（不重做任何單景產物）。"""
    unknown = sorted(set(changed_fields) - set(SCENE_FIELD_IMPACT))
    if unknown:
        raise ValueError(f"no regeneration-scope rule for fields {unknown}")
    hit = {a for f in changed_fields for a in SCENE_FIELD_IMPACT[f]}
    if hit - {"render"}:
        hit.add("render")
    assets = [a for a in ASSET_ORDER if a in hit]
    return {"assets": assets, "affects_image": "image" in hit, "affects_video": "clip" in hit,
            "affects_narration_audio": "narration" in hit, "unaffected": [a for a in ASSET_ORDER if a not in hit]}
