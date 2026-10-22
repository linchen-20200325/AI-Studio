from __future__ import annotations

from pydantic import BaseModel, Field

from see.models.enums import AssetKind


class Asset(BaseModel):
    asset_id: str
    scene_id: str | None = None
    kind: AssetKind
    path: str
    fingerprint: str = Field(description="sha256 of inputs that produced this asset")
    provider: str = ""
    model: str = ""
    duration: float | None = Field(default=None, ge=0)
