from pathlib import Path

import pytest

from see.core.approval import ApprovalGate
from see.core.errors import BudgetExceeded, PaidProviderNotApproved, ProviderError
from see.models import Approval, ApprovalKind, CostEstimate, CostTier, Project, ProviderInfo, ProviderKind
from see.providers.base import TTSProvider, TTSRequest, TTSResult
from see.providers.tts.fallback import FallbackTTSProvider
from see.providers.tts.silent import SilentTTSProvider


class FakePaidTTS(TTSProvider):
    calls = 0

    @property
    def info(self) -> ProviderInfo:
        return ProviderInfo(name="fake-paid-tts", kind=ProviderKind.TTS, cost_tier=CostTier.PAID, model="premium",
                            requires_api_key=True, requires_network=True)

    def estimate_cost(self, request: TTSRequest) -> CostEstimate:
        return self._estimate(units=len(request.text), unit_name="chars", cost=0.30 * len(request.text) / 1000)

    def synthesize(self, request: TTSRequest, out_path: Path) -> TTSResult:
        FakePaidTTS.calls += 1
        return TTSResult(path=str(out_path), duration=1.0, provider=self.info.name, model="premium")


class BrokenFreeTTS(SilentTTSProvider):
    @property
    def info(self) -> ProviderInfo:
        return ProviderInfo(name="broken-free", kind=ProviderKind.TTS, cost_tier=CostTier.LOCAL_FREE, model="x")

    def synthesize(self, request, out_path):
        raise ProviderError("boom")


def _project(**kw) -> Project:
    return Project(project_id="p", input_text="故事", **kw)


def test_paid_without_approval_is_rejected():
    est = FakePaidTTS().estimate_cost(TTSRequest(text="一" * 100))
    with pytest.raises(PaidProviderNotApproved):
        ApprovalGate.check(est, _project())


def test_paid_with_approval_but_zero_budget_is_rejected():
    est = FakePaidTTS().estimate_cost(TTSRequest(text="一" * 100))
    p = _project(approvals=[Approval(approval_id="a1", kind=ApprovalKind.PAID_PROVIDER, target="fake-paid-tts")])
    with pytest.raises(BudgetExceeded):
        ApprovalGate.check(est, p)  # budget=0, estimated 0.03 > 0


def test_paid_with_approval_and_cap_passes():
    est = FakePaidTTS().estimate_cost(TTSRequest(text="一" * 100))
    p = _project(approvals=[Approval(approval_id="a1", kind=ApprovalKind.PAID_PROVIDER, target="fake-paid-tts", max_cost=1.0)])
    ApprovalGate.check(est, p)


def test_free_tiers_pass_without_approval():
    for tier in (CostTier.LOCAL_FREE, CostTier.FREE_TIER):
        ApprovalGate.check(CostEstimate(provider="x", model="m", cost_tier=tier, units=1, estimated_cost=0), _project())


def test_fallback_never_crosses_into_paid(tmp_path: Path):
    FakePaidTTS.calls = 0
    fb = FallbackTTSProvider([BrokenFreeTTS(), FakePaidTTS()])
    with pytest.raises(ProviderError) as ei:
        fb.synthesize(TTSRequest(text="你好"), tmp_path / "o.wav")
    assert "PAID candidate skipped" in str(ei.value)
    assert FakePaidTTS.calls == 0


def test_fallback_uses_next_free_candidate(tmp_path: Path):
    fb = FallbackTTSProvider([BrokenFreeTTS(), SilentTTSProvider()])
    r = fb.synthesize(TTSRequest(text="你好"), tmp_path / "o.wav")
    assert r.provider == "silent-tts" and fb.info.name == "silent-tts"
