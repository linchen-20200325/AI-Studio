"""D-053：S4 Identity adapter 型錄守門（無下載、無載入）。"""

from __future__ import annotations

import pytest

from see.providers.image.adapters import ADAPTERS, AdapterFile, AdapterSpec, assert_usable, get_adapter


def test_ip_adapter_catalog_not_approved_and_safetensors_only():
    a = get_adapter("ip_adapter_plus_face_sd15")
    assert not a.approved and not a.commercial_cleared and a.usage == "internal_quality_validation_only"
    assert a.total_bytes == 98_183_288 + 2_528_373_448 + 560  # ≈2.63 GB
    assert all(f.path.endswith((".safetensors", ".json")) for f in a.files)
    assert all(f.sha256 and len(f.sha256) == 64 for f in a.files if f.path.endswith(".safetensors"))
    with pytest.raises(PermissionError):
        assert_usable(a)  # DG-25 前一律拒絕
    with pytest.raises(ValueError):
        get_adapter("ip_adapter_faceid_sd15")  # FaceID（pickle＋InsightFace 非商用）不列入


def test_assert_usable_rejects_pickle_even_if_approved():
    bad = AdapterSpec("x", "ip_adapter", "sd15", "r", "v", (AdapterFile("m.bin", 1, "0" * 64),), "", "", approved=True)
    with pytest.raises(ValueError):
        assert_usable(bad)
    assert set(ADAPTERS) == {"ip_adapter_plus_face_sd15"}
