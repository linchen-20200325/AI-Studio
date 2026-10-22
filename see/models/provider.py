from __future__ import annotations

from pydantic import BaseModel, Field

from see.models.enums import CostTier, ProviderKind


class ProviderInfo(BaseModel):
    """每個 Provider 必須提供的自我描述。"""

    name: str = Field(min_length=1)
    kind: ProviderKind
    cost_tier: CostTier
    model: str = Field(min_length=1)
    version: str = "0"
    requires_network: bool = False
    requires_api_key: bool = False

    @property
    def fingerprint_key(self) -> str:
        return f"{self.kind}:{self.name}:{self.model}:{self.version}"
