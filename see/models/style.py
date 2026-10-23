"""Style Profile（D-032）：影片視覺風格的結構化描述，provider-agnostic。

不是單一 prompt 字串：分成正向詞、負向詞、provider 參數提示（例如 steps／guidance）與 per-provider 覆寫，
讓 SD 1.5（prompt）與未來的 LoRA／IP-Adapter／其他 image provider 都能各取所需。provider 不認得的欄位直接忽略。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class StyleProfile(BaseModel):
    style_id: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_-]+$")
    display_name: str = Field(min_length=1)
    description: str = ""
    family: str = Field(default="illustration", description="realistic | illustration | anime | 3d | cinematic | ...（分類用）")
    positive_terms: list[str] = Field(default_factory=list, description="附加到 image prompt 的風格詞（英文）")
    negative_terms: list[str] = Field(default_factory=list, description="附加到 negative prompt")
    params: dict[str, Any] = Field(default_factory=dict, description="通用生成參數提示；provider 自行決定是否採用")
    provider_overrides: dict[str, dict[str, Any]] = Field(default_factory=dict, description="provider name → 額外參數")
    builtin: bool = True
    validated: bool = Field(default=False, description="是否已有真機視覺驗收證據（目前只有 default）")

    @property
    def is_default(self) -> bool:
        return self.style_id == "default"
