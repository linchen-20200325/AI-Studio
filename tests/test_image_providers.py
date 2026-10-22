from pathlib import Path

import pytest

from see.core.approval import ApprovalGate
from see.core.config import Settings
from see.core.errors import PaidProviderNotApproved, ProviderUnavailable
from see.models import Project
from see.providers.base import ImageRequest
from see.providers.image.diffusers_local import DiffusersImageProvider
from see.providers.image.fallback import FallbackImageProvider
from see.providers.image.paid_stub import PaidImageProviderStub
from see.providers.image.placeholder import PlaceholderImageProvider
from see.providers.registry import ProviderRegistry


def test_diffusers_scaffold_never_downloads(tmp_path: Path):
    p = DiffusersImageProvider(preset="flux-schnell")
    assert p.info.cost_tier == "LOCAL_FREE" and p.info.model == "black-forest-labs/FLUX.1-schnell"
    assert not p.is_available()  # 本環境無 torch/權重
    with pytest.raises(ProviderUnavailable):
        p.generate_image(ImageRequest(prompt="x", width=64, height=64), tmp_path / "x.png")
    with pytest.raises(ValueError):
        DiffusersImageProvider(preset="nope")


def test_auto_image_falls_back_to_placeholder(tmp_path: Path):
    s = Settings(); s.image_provider = "auto"
    prov = ProviderRegistry(s).build().image
    assert isinstance(prov, FallbackImageProvider)
    res = prov.generate_image(ImageRequest(prompt="山", width=64, height=36), tmp_path / "a.png")
    assert res.provider == "placeholder-image" and prov.info.name == "placeholder-image"
    assert prov.skipped and "diffusers-flux-schnell" in prov.skipped[0]


def test_fallback_stops_before_paid(tmp_path: Path):
    prov = FallbackImageProvider([DiffusersImageProvider("sd15"), PaidImageProviderStub()])
    with pytest.raises(ProviderUnavailable):
        _ = prov.info


def test_paid_stub_blocked_by_gate():
    stub = PaidImageProviderStub()
    est = stub.estimate_cost(ImageRequest(prompt="x"))
    assert est.cost_tier == "PAID" and est.estimated_cost > 0
    with pytest.raises(PaidProviderNotApproved):
        ApprovalGate.check(est, Project(project_id="p", input_text="故事"))


def test_registry_keys():
    s = Settings()
    r = ProviderRegistry(s)
    assert {"placeholder", "auto", "diffusers", "paid-stub"} <= set(r._image)
    s.image_provider = "paid-stub"
    assert ProviderRegistry(s).build().image.info.cost_tier == "PAID"
    assert isinstance(PlaceholderImageProvider(), PlaceholderImageProvider)
