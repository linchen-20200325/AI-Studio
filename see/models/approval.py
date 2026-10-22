from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

from see.models.enums import ApprovalKind


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Approval(BaseModel):
    """人工核准紀錄。只能由人工操作（CLI / UI）建立。"""

    approval_id: str
    kind: ApprovalKind
    target: str = Field(description="核准對象：provider 名稱、job id、project id 等")
    approved_by: str = "human"
    approved_at: datetime = Field(default_factory=_now)
    max_cost: float | None = Field(default=None, ge=0)
    currency: str = "USD"
    note: str = ""
