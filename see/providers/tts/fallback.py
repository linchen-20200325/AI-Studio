"""FallbackTTSProvider：依序嘗試候選；只在 LOCAL_FREE / FREE_TIER 之間 fallback。

PROJECT_RULES §4：遇到 PAID 候選不得自動執行，必須先過 ApprovalGate（由 pipeline 負責）。
"""

from __future__ import annotations

from pathlib import Path

from see.core.errors import ProviderError, ProviderUnavailable
from see.models.cost import CostEstimate
from see.models.enums import CostTier
from see.models.provider import ProviderInfo
from see.providers.base import TTSProvider, TTSRequest, TTSResult, VoiceInfo


class FallbackTTSProvider(TTSProvider):
    def __init__(self, candidates: list[TTSProvider]) -> None:
        if not candidates:
            raise ValueError("need at least one candidate")
        self.candidates = candidates
        self._active: TTSProvider | None = None

    @property
    def active(self) -> TTSProvider:
        if self._active is None:
            for c in self.candidates:
                if c.info.cost_tier == CostTier.PAID:
                    break  # 不自動跨到 PAID
                if c.is_available():
                    self._active = c
                    break
            if self._active is None:
                raise ProviderUnavailable("no free TTS provider available in this environment")
        return self._active

    @property
    def info(self) -> ProviderInfo:
        return self.active.info

    def is_available(self) -> bool:
        try:
            return self.active.is_available()
        except ProviderUnavailable:
            return False

    def estimate_cost(self, request: TTSRequest) -> CostEstimate:
        return self.active.estimate_cost(request)

    def list_voices(self) -> list[VoiceInfo]:
        return self.active.list_voices()

    def synthesize(self, request: TTSRequest, out_path: Path) -> TTSResult:
        errors: list[str] = []
        for c in self.candidates:
            if c.info.cost_tier == CostTier.PAID:
                errors.append(f"{c.info.name}: PAID candidate skipped (needs human approval)")
                break
            if not c.is_available():
                errors.append(f"{c.info.name}: unavailable")
                continue
            try:
                result = c.synthesize(request, out_path)
                # 不改 self._active：info/fingerprint 固定為「第一個可用候選」（同 image D-023），實際生成者看 meta
                # 證據：實際生成者與之前失敗的候選（BACKLOG：TTS provenance）
                result.meta = {**result.meta, "generated_by": result.provider, "fallback_from": list(errors)}
                return result
            except ProviderError as e:
                errors.append(f"{c.info.name}: {e}")
        raise ProviderError("all free TTS candidates failed: " + "; ".join(errors))
