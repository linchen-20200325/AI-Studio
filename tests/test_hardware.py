from see.core import hardware as hw
from see.core.hardware import GPUInfo, HardwareProfile, TorchInfo, recommend_image_tier


def _prof(**kw) -> HardwareProfile:
    base = dict(os="Windows", ram_total_mb=32_000, disk_free_mb=200_000, gpus=[], torch=TorchInfo())
    base.update(kw)
    return HardwareProfile(**base)


def test_detect_runs_without_gpu_tools(monkeypatch):
    monkeypatch.setattr(hw, "_run", lambda cmd, timeout=15: None)
    p = hw.detect_hardware(".")
    assert p.os and p.cpu_cores and p.gpus == [] and any("GPU" in n for n in p.notes)


def test_parse_nvidia_smi(monkeypatch):
    monkeypatch.setattr(hw, "_run", lambda cmd, timeout=15: "NVIDIA GeForce RTX 4070, 12282, 1200, 560.94\n" if cmd[0] == "nvidia-smi" else None)
    g = hw._gpus_nvidia()
    assert g[0].vendor == "nvidia" and g[0].vram_total_mb == 12282 and g[0].vram_free_mb == 11082 and g[0].driver == "560.94"


def test_recommend_rtx_16gb_gets_flux():
    p = _prof(gpus=[GPUInfo(vendor="nvidia", name="RTX 4080", vram_total_mb=16_000)])
    r = recommend_image_tier(p)
    assert r.recommended.key == "flux-schnell" and r.fallback.key == "flux-schnell-nf4" and not r.cpu_only


def test_recommend_8gb_gets_nf4_then_sd15():
    p = _prof(gpus=[GPUInfo(vendor="nvidia", name="RTX 3060 Ti", vram_total_mb=8_000)])
    r = recommend_image_tier(p)
    assert r.recommended.key == "flux-schnell-nf4" and r.fallback.key == "sd15"


def test_recommend_no_gpu_is_cpu_only_sd15():
    r = recommend_image_tier(_prof(ram_total_mb=16_000))
    assert r.cpu_only and r.recommended.key == "sd15" and r.fallback is None


def test_recommend_insufficient_hardware():
    r = recommend_image_tier(_prof(ram_total_mb=4_000, disk_free_mb=2_000))
    assert r.recommended is None and any("硬體不足" in x for x in r.reasons)


def test_paid_tier_never_recommended():
    r = recommend_image_tier(_prof(gpus=[GPUInfo(vendor="nvidia", name="H100", vram_total_mb=80_000)]))
    assert r.recommended.cost_tier == "LOCAL_FREE" and (r.fallback is None or r.fallback.cost_tier == "LOCAL_FREE")
