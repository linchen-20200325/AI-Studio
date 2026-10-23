"""D-039：已核准 SD 1.5 checkpoint 的型錄、下載驗證、provenance、style-test 接線（不碰真模型／網路）。"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import sys
import types
from pathlib import Path

import numpy as np
import pytest

from see.providers.base import ImageRequest
from see.providers.image import checkpoints as ck
from see.providers.image.diffusers_local import DiffusersImageProvider, RuntimePlan


def test_catalog_is_internal_only_safetensors():
    assert set(ck.CHECKPOINTS) == {"meinamix_v12", "cyberrealistic_final"}
    for c in ck.CHECKPOINTS.values():
        assert c.filename.endswith(".safetensors") and len(c.sha256) == 64 and c.sha256 == c.sha256.lower()
        assert c.commercial_cleared is False and c.usage == ck.USAGE and c.attribution
        assert len(c.download_revision) == 40
    assert ck.get_checkpoint("meinamix_v12").diffusers_clip_skip == 1  # A1111 clip skip 2 → diffusers 1
    assert ck.get_checkpoint("cyberrealistic_final").diffusers_clip_skip is None
    with pytest.raises(ValueError):
        ck.get_checkpoint("anything-v3")


def test_validate_remote_rejects_any_mismatch():
    c = ck.get_checkpoint("cyberrealistic_final")
    ok = {"filename": c.filename, "bytes": c.bytes, "sha256": c.sha256.upper(), "revision": c.download_revision}
    assert ck.validate_remote(c, ok) == []
    assert any("size" in e for e in ck.validate_remote(c, {**ok, "bytes": 1}))
    assert any("sha256" in e for e in ck.validate_remote(c, {**ok, "sha256": "0" * 64}))
    assert any("filename" in e for e in ck.validate_remote(c, {**ok, "filename": "x.ckpt"}))
    assert any("revision" in e for e in ck.validate_remote(c, {**ok, "revision": "f" * 40}))
    pickle = dataclasses.replace(c, filename="model.ckpt")
    assert any("safetensors" in e for e in ck.validate_remote(pickle, {**ok, "filename": "model.ckpt"}))


def _fake_hub(monkeypatch, payload: bytes, remote: dict):
    hub = types.ModuleType("huggingface_hub")

    class Api:
        def model_info(self, repo, revision=None, files_metadata=False):
            sib = types.SimpleNamespace(rfilename=remote["filename"], size=remote["bytes"],
                                        lfs=types.SimpleNamespace(sha256=remote["sha256"]))
            return types.SimpleNamespace(sha=remote["revision"], siblings=[sib])

    def dl(repo_id, filename, revision, local_dir):
        p = Path(local_dir) / filename
        p.write_bytes(payload)
        return str(p)

    hub.HfApi, hub.hf_hub_download = Api, dl
    monkeypatch.setitem(sys.modules, "huggingface_hub", hub)


def _small_spec(payload: bytes) -> ck.CheckpointSpec:
    return dataclasses.replace(ck.get_checkpoint("meinamix_v12"), bytes=len(payload),
                               sha256=hashlib.sha256(payload).hexdigest())


def test_download_verifies_and_writes_provenance(monkeypatch, tmp_path):
    payload = b"safetensors-bytes" * 100
    spec = _small_spec(payload)
    _fake_hub(monkeypatch, payload, {"filename": spec.filename, "bytes": spec.bytes, "sha256": spec.sha256,
                                     "revision": spec.download_revision})
    prov = ck.download_checkpoint(tmp_path, spec)
    assert prov["verified"] and prov["local_sha256"] == spec.sha256 and prov["commercial_cleared"] is False
    assert prov["official_source"] and prov["license_status"] and prov["version"]
    assert json.loads((tmp_path / "checkpoints" / spec.checkpoint_id / "provenance.json").read_text(encoding="utf-8"))["verified"]
    assert (tmp_path / "checkpoints" / ".gitignore").read_text() == "*\n"


def test_download_tampered_file_is_deleted(monkeypatch, tmp_path):
    payload = b"good" * 50
    spec = _small_spec(payload)
    _fake_hub(monkeypatch, b"evil" * 50, {"filename": spec.filename, "bytes": spec.bytes, "sha256": spec.sha256,
                                          "revision": spec.download_revision})
    with pytest.raises(ValueError, match="rejected"):
        ck.download_checkpoint(tmp_path, spec)
    assert not ck.checkpoint_file(tmp_path, spec).exists()
    assert ck.read_provenance(tmp_path, spec) is None


def test_download_refuses_before_transfer_when_remote_differs(monkeypatch, tmp_path):
    payload = b"x" * 10
    spec = _small_spec(payload)
    _fake_hub(monkeypatch, payload, {"filename": spec.filename, "bytes": 999, "sha256": spec.sha256,
                                     "revision": spec.download_revision})
    with pytest.raises(ValueError, match="nothing downloaded"):
        ck.download_checkpoint(tmp_path, spec)
    assert not ck.checkpoint_dir(tmp_path, spec).exists()


def test_cli_check_and_plan_never_download(monkeypatch, tmp_path, capsys):
    from see.app.cli import main

    monkeypatch.setenv("SEE_MODELS_DIR", str(tmp_path))
    c = ck.get_checkpoint("meinamix_v12")
    monkeypatch.setattr(ck, "fetch_remote_metadata", lambda spec: {"filename": c.filename, "bytes": c.bytes,
                                                                   "sha256": c.sha256, "revision": c.download_revision})
    monkeypatch.setattr(ck, "download_checkpoint", lambda *a: pytest.fail("must not download"))
    assert main(["checkpoint-download", "meinamix_v12", "--check"]) == 0
    assert main(["checkpoint-download", "meinamix_v12"]) == 0
    out = capsys.readouterr().out
    assert '"match": true' in out and '"commercial_cleared": false' in out


def test_style_test_checkpoint_missing_is_fail_closed(monkeypatch, tmp_path, capsys):
    from see.app.cli import main

    monkeypatch.setenv("SEE_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.setenv("SEE_MODELS_DIR", str(tmp_path / "models"))
    assert main(["style-test", "--style", "anime", "--checkpoint", "meinamix_v12", "--gen-policy", "native"]) == 2
    assert not (tmp_path / "ws" / "style_tests").exists() or not list((tmp_path / "ws" / "style_tests").glob("*.png"))
    assert "provenance" in capsys.readouterr().err  # 不會偷偷 fallback 到 placeholder


def test_stem_includes_checkpoint_and_scheduler():
    from see.app.cli import _style_test_stem

    assert _style_test_stem("anime", "girl_city_night", 1234, "native", False, "meinamix_v12", "dpmpp_2m_karras") == \
        "anime_seed1234_girl_city_night_native_ckpt-meinamix_v12_sched-dpmpp_2m_karras"
    assert _style_test_stem("anime", "kitten_butterfly", 1234, "fit", False) == "anime_seed1234"


def test_provider_checkpoint_identity_and_availability(tmp_path):
    spec = ck.get_checkpoint("meinamix_v12")
    base = DiffusersImageProvider("sd15")
    p = DiffusersImageProvider("sd15", model_path=str(tmp_path), checkpoint=spec, checkpoint_path=str(tmp_path / "none.safetensors"))
    assert p.info.name == "diffusers-sd15-ckpt" and p.info.model.startswith("meinamix_v12@")
    assert p.info.fingerprint_key != base.info.fingerprint_key  # 不與 base SD 1.5 快取混用
    assert not p.is_available() and "checkpoint-download" in p.unavailable_reason()
    assert p.scheduler_name == "dpmpp_2m_karras" and base.scheduler_name == "default"
    with pytest.raises(ValueError):
        DiffusersImageProvider("sd15", scheduler="lms")


def test_load_checkpoint_uses_single_file_with_local_config(monkeypatch, tmp_path):
    seen: dict = {}

    class Sched:
        config = {"k": 1}

    class Pipe:
        scheduler = Sched()
        vae = types.SimpleNamespace(dtype="float32")

        def enable_attention_slicing(self): seen["slicing"] = True
        def enable_vae_slicing(self): pass
        def enable_vae_tiling(self): pass
        def enable_model_cpu_offload(self): seen["offload"] = True
        def set_progress_bar_config(self, **kw): pass

    class SDP:
        @staticmethod
        def from_single_file(path, **kw):
            seen["path"], seen["kw"] = path, kw
            return Pipe()

    diff = types.ModuleType("diffusers")
    diff.StableDiffusionPipeline = SDP
    diff.AutoPipelineForText2Image = None  # _load 在分派前 import；checkpoint 路徑不得使用它
    diff.DPMSolverMultistepScheduler = types.SimpleNamespace(from_config=lambda cfg, **kw: ("dpm", kw))
    monkeypatch.setitem(sys.modules, "diffusers", diff)
    fake_torch = types.ModuleType("torch")
    fake_torch.float32, fake_torch.float16 = "float32", "float16"
    fake_torch.cuda = types.SimpleNamespace(is_available=lambda: False, empty_cache=lambda: None)
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    spec = ck.get_checkpoint("meinamix_v12")
    p = DiffusersImageProvider("sd15", model_path=str(tmp_path / "sd15"), checkpoint=spec, checkpoint_path=str(tmp_path / "m.safetensors"))
    pipe = p._load(RuntimePlan("cuda", "float32", True, True, True, True, 512, vae_fp32=True))
    assert seen["path"].endswith("m.safetensors") and seen["kw"]["config"].endswith("sd15")
    assert seen["kw"]["local_files_only"] is True and seen["kw"]["safety_checker"] is None and seen["kw"]["torch_dtype"] == "float32"
    assert pipe.scheduler == ("dpm", {"use_karras_sigmas": True, "algorithm_type": "dpmsolver++"})
    assert seen["offload"] and p.weights_variant == "single-file"


def test_run_pipe_passes_clip_skip_for_checkpoint(monkeypatch):
    import contextlib

    class T:
        def __init__(self, a, dtype="float32"):
            self.a, self.dtype = np.asarray(a, np.float32), dtype

        def __truediv__(self, k):
            return T(self.a / k, self.dtype)

        def to(self, dtype):
            return T(self.a, dtype)

    seen: dict = {}

    class Pipe:
        vae = types.SimpleNamespace(dtype="float32", config=types.SimpleNamespace(scaling_factor=0.18215),
                                    decode=lambda z, return_dict=True: (z,))
        image_processor = types.SimpleNamespace(postprocess=lambda image, output_type="np": [image.a])
        scheduler = types.SimpleNamespace()

        def __call__(self, **kw):
            seen.update(kw)
            return types.SimpleNamespace(images=T(np.full((1, 4, 8, 8), 0.5)))

    fake_torch = types.ModuleType("torch")
    fake_torch.inference_mode = contextlib.nullcontext
    fake_torch.Generator = lambda device="cpu": types.SimpleNamespace(manual_seed=lambda s: s)
    fake_torch.isfinite = lambda t: types.SimpleNamespace(all=lambda: True)
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    plan = RuntimePlan("cuda", "float32", True, True, True, True, 512, vae_fp32=True)
    p = DiffusersImageProvider("sd15", checkpoint=ck.get_checkpoint("meinamix_v12"), checkpoint_path="x")
    p._run_pipe(Pipe(), plan, ImageRequest(prompt="a girl", width=1920, height=1080, params={"gen_policy": "native"}))
    assert seen["clip_skip"] == 1 and p._gen_info["clip_skip_a1111"] == 2 and p._gen_info["vram_peak_mb"] is None
    seen.clear()
    DiffusersImageProvider("sd15")._run_pipe(Pipe(), plan, ImageRequest(prompt="a girl", width=1920, height=1080))
    assert "clip_skip" not in seen  # base SD 1.5 呼叫參數不變
