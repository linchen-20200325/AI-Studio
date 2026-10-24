"""內建 Style Profile 型錄與套用邏輯（D-032）。

- `default` = Phase 1 既有行為（storybook watercolor 已寫在 image_prompt_en 內）→ 套用時**完全不改 prompt**，
  舊專案 image fingerprint 不變。
- 其他風格：移除舊的 storybook 風格尾綴、改接該風格的 positive_terms；只有 `validated=True` 的風格有真機證據。
- 風格只是 prompt 層 + 參數提示，**不是**模型選型；未來換 image provider／LoRA 不需改這裡的資料結構。
"""

from __future__ import annotations

import re
from typing import Any

from see.core.prompting import _STYLE as LEGACY_STYLE_SUFFIX
from see.models.style import StyleProfile

BUILTIN_STYLES: dict[str, StyleProfile] = {s.style_id: s for s in [
    StyleProfile(style_id="default", display_name="繪本水彩（預設）", family="illustration",
                 description="Phase 1 既有風格；SD 1.5 真機驗證", validated=True),
    StyleProfile(style_id="picture_book", display_name="兒童繪本", family="illustration",
                 positive_terms=["children's picture book illustration", "gouache", "soft pastel colors", "simple shapes", "warm light"],
                 negative_terms=["photorealistic", "3d render"]),
    StyleProfile(style_id="anime", display_name="日系動畫", family="anime",
                 positive_terms=["anime style", "cel shading", "clean line art", "vibrant colors", "detailed background"],
                 negative_terms=["photorealistic", "3d render", "watercolor"]),
    StyleProfile(style_id="realistic", display_name="寫實攝影", family="realistic",
                 positive_terms=["photorealistic", "natural lighting", "35mm photograph", "shallow depth of field", "high detail"],
                 negative_terms=["cartoon", "illustration", "anime", "painting"]),
    StyleProfile(style_id="cinematic", display_name="電影感", family="cinematic",
                 positive_terms=["cinematic still", "dramatic lighting", "anamorphic", "film grain", "color graded"],
                 negative_terms=["cartoon", "flat lighting"]),
    StyleProfile(style_id="3d", display_name="3D 動畫", family="3d",
                 positive_terms=["3d animated film still", "pixar style", "soft global illumination", "subsurface scattering"],
                 negative_terms=["2d", "flat", "sketch", "photorealistic"]),
]}


def get_style(style_id: str) -> StyleProfile:
    if style_id not in BUILTIN_STYLES:
        raise ValueError(f"unknown style '{style_id}'; available: {sorted(BUILTIN_STYLES)}")
    return BUILTIN_STYLES[style_id]


def _join(*parts: str) -> str:
    return ", ".join(p.strip(" ,") for p in parts if p and p.strip(" ,"))


def apply_style(prompt: str, negative: str, style: StyleProfile, provider_name: str = "") -> tuple[str, str, dict[str, Any]]:
    """回傳 (prompt, negative, params)。default → 原樣返回（params 空），保證舊 fingerprint 不變。"""
    if style.is_default:
        return prompt, negative, {}
    # legacy 畫風詞可能在中間（D-063／D-065 會在其後接人物／場景詞）→ 移除後收掉留下的空項（", ,"）
    base = re.sub(r"\s*,(\s*,)+", ",", prompt.replace(LEGACY_STYLE_SUFFIX, "")).strip(" ,")
    params: dict[str, Any] = {"style_id": style.style_id, **style.params, **style.provider_overrides.get(provider_name, {})}
    return _join(base, ", ".join(style.positive_terms)), _join(negative, ", ".join(style.negative_terms)), params
