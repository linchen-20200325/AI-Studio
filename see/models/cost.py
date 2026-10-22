from __future__ import annotations

from pydantic import BaseModel, Field

from see.models.enums import CostTier


class CostEstimate(BaseModel):
    """執行前的成本估算。PAID provider 必須如實填寫。"""

    provider: str
    model: str
    cost_tier: CostTier
    units: float = Field(ge=0, description="工作量，例如秒數、張數、tokens")
    unit_name: str = "unit"
    estimated_cost: float = Field(ge=0)
    currency: str = "USD"
    note: str = ""
