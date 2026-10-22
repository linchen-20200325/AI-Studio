from pathlib import Path

from see.app.cli import main
from see.providers.image.diffusers_local import (
    MODEL_PRESETS,
    DiffusersImageProvider,
    download_plan,
    gen_size,
    make_runtime_plan,
)


def test_low_vram_plan_for_gtx1650():
    p = make_runtime_plan("cuda", 4096, MODEL_PRESETS["sd15"]["max_side"])
    assert p.low_vram and p.attention_slicing and p.vae_slicing and p.cpu_offload and p.dtype == "float16" and p.max_side == 512
    d = p.downgrade()
    assert d.max_side == 384 and d.downgrade().max_side == 384  # 下限


def test_high_vram_plan_keeps_full_res():
    p = make_runtime_plan("cuda", 16_000, 1024)
    assert not p.low_vram and not p.cpu_offload and p.max_side == 1024


def test_cpu_plan_is_float32_capped():
    p = make_runtime_plan("cpu", None, 1024)
    assert p.device == "cpu" and p.dtype == "float32" and p.max_side == 512


def test_gen_size_multiple_and_cap():
    assert gen_size(1920, 1080, 512, 8) == (512, 288)
    assert gen_size(1080, 1920, 512, 8) == (288, 512)
    assert gen_size(300, 300, 512, 8) == (296, 296)


def test_download_plan_sd15_is_small_and_skips_safety_checker():
    plan = download_plan("sd15")
    assert plan["estimated_gb"] < 3 and not any("safety_checker" in p for p in plan["allow_patterns"])


def test_default_preset_sd15_and_model_path_check(tmp_path: Path):
    p = DiffusersImageProvider()
    assert p.preset == "sd15" and p.info.model.endswith("stable-diffusion-v1-5")
    assert not DiffusersImageProvider(model_path=str(tmp_path)).is_available()


def test_image_download_without_yes_does_nothing(tmp_path: Path, capsys, monkeypatch):
    monkeypatch.setenv("SEE_MODELS_DIR", str(tmp_path / "models"))
    assert main(["image-download", "--preset", "sd15"]) == 0
    assert "stable-diffusion-v1-5" in capsys.readouterr().out
    assert not (tmp_path / "models").exists()


def test_image_setup_prints_steps(capsys, monkeypatch):
    monkeypatch.setenv("SEE_MODELS_DIR", "/nonexistent/models")
    assert main(["image-setup"]) == 0
    out = capsys.readouterr().out
    assert "image-download --preset sd15 --yes" in out and "pip install diffusers" in out
