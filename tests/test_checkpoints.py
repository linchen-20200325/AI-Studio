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
    import see.providers.image.diffusers_local as dl

    monkeypatch.setattr(dl, "encode_prompt_clip_skip", lambda pipe, pr, ne, n: ("PE", "NPE", {"clip_skip_a1111": n, "ordering_verified": True}))
    p._run_pipe(Pipe(), plan, ImageRequest(prompt="a girl", width=1920, height=1080, params={"gen_policy": "native"}))
    # D-040：不得把 clip_skip= 交給 diffusers（0.41 + transformers 5.x → AttributeError），改傳自編 embeds
    assert "clip_skip" not in seen and "prompt" not in seen
    assert seen["prompt_embeds"] == "PE" and seen["negative_prompt_embeds"] == "NPE"
    assert p._gen_info["clip_skip_a1111"] == 2 and p._gen_info["clip_skip_encoding"]["ordering_verified"]
    seen.clear()
    base = DiffusersImageProvider("sd15")
    base._run_pipe(Pipe(), plan, ImageRequest(prompt="a girl", width=1920, height=1080))
    assert "clip_skip" not in seen and seen["prompt"] == "a girl" and "prompt_embeds" not in seen  # base SD 1.5 呼叫不變
    # D-043：base 也明確記錄 clip skip（1＝不跳層），跨次比較才能看出差異
    assert base._gen_info["clip_skip_a1111"] == 1 and base._gen_info["clip_skip_diffusers"] is None


# ---------------------------------------------------------------- D-040：clip skip 與 transformers 4.x／5.x CLIPTextModel 版面
# 容器無 torch：以 numpy 替身＋假 torch 模組（只需 allclose）驗證語意；真機整合由 E2-5 證據覆蓋。
class _Arr:
    def __init__(self, a):
        self.a = np.asarray(a, np.float32)

    def float(self):
        return self

    def __mul__(self, k):
        return _Arr(self.a * k)

    def to(self, device):
        return self


def _fake_torch_min(monkeypatch):
    import contextlib

    ft = types.ModuleType("torch")
    ft.allclose = lambda x, y, atol=0, rtol=0: bool(np.allclose(x.a, y.a, atol=atol, rtol=rtol))
    ft.inference_mode = contextlib.nullcontext
    ft.Generator = lambda device="cpu": types.SimpleNamespace(manual_seed=lambda s: s)
    ft.isfinite = lambda t: types.SimpleNamespace(all=lambda: True)
    monkeypatch.setitem(sys.modules, "torch", ft)


class _LN:
    """可辨識的 final_layer_norm 替身：x * 10。"""

    def __call__(self, x):
        return x * 10


class _TE:
    """假 CLIPTextModel：hidden_states = [emb, l1, l2, l3]（值 1..4），last_hidden_state = ln(l3)。"""

    def __init__(self, layout: str, ordering_ok: bool = True):
        self.config = types.SimpleNamespace(num_hidden_layers=3)
        self._ln = _LN()
        if layout == "v4":
            self.text_model = types.SimpleNamespace(final_layer_norm=self._ln)
        elif layout == "v5":
            self.final_layer_norm = self._ln
        self.ordering_ok = ordering_ok

    def __call__(self, ids, output_hidden_states=False):
        hs = tuple(_Arr(np.full((1, 4, 2), float(i + 1))) for i in range(4))
        last = self._ln(hs[-1]) if self.ordering_ok else hs[-1]
        return types.SimpleNamespace(hidden_states=hs, last_hidden_state=last)


class _Tok:
    model_max_length = 77

    def __call__(self, text, **kw):
        assert kw.get("max_length") == 77 and kw.get("truncation") and kw.get("padding") == "max_length"
        return types.SimpleNamespace(input_ids=_Arr(np.zeros((1, 77))))


def _pipe(te):
    return types.SimpleNamespace(tokenizer=_Tok(), text_encoder=te, _execution_device="cpu")


@pytest.mark.parametrize("layout", ["v4", "v5"])
def test_clip_skip_a1111_semantics_on_both_transformers_layouts(monkeypatch, layout):
    """A1111 clip skip 2 = hidden_states[-2]（倒數第二層）再套 final_layer_norm；4.x 與 5.x 版面都必須成立。"""
    _fake_torch_min(monkeypatch)
    from see.providers.image.diffusers_local import encode_prompt_clip_skip

    pe, npe, info = encode_prompt_clip_skip(_pipe(_TE(layout)), "a girl", "", 2)
    assert np.array_equal(pe.a, np.full((1, 4, 2), 30.0))  # l2=3 → ×10
    assert np.array_equal(npe.a, pe.a)
    assert info["layer_index_used"] == 2 and info["hidden_states_len"] == 4 and info["ordering_verified"]
    pe1, _, _ = encode_prompt_clip_skip(_pipe(_TE(layout)), "a girl", "", 1)
    assert np.array_equal(pe1.a, np.full((1, 4, 2), 40.0))  # clip skip 1 = 最後一層 = 等同不 skip


def test_clip_skip_refuses_unverifiable_ordering_or_missing_layer_norm(monkeypatch):
    _fake_torch_min(monkeypatch)
    from see.core.errors import ProviderError
    from see.providers.image.diffusers_local import encode_prompt_clip_skip, final_layer_norm_of

    with pytest.raises(ProviderError, match="ordering"):
        encode_prompt_clip_skip(_pipe(_TE("v5", ordering_ok=False)), "x", "", 2)
    with pytest.raises(ProviderError, match="final_layer_norm"):
        final_layer_norm_of(types.SimpleNamespace())
    with pytest.raises(ValueError):
        encode_prompt_clip_skip(_pipe(_TE("v5")), "x", "", 4)  # 超過層數


def test_regression_diffusers_clip_skip_kwarg_never_used_with_transformers5_layout(monkeypatch):
    """回歸：真機錯誤 `'CLIPTextModel' object has no attribute 'text_model'`（diffusers 0.41 clip_skip 路徑）。
    模擬 diffusers 0.41：收到 clip_skip= 就存取 text_encoder.text_model → 5.x 版面必炸；我們的路徑不得觸發。"""
    _fake_torch_min(monkeypatch)

    class _T:
        def __init__(self, a, dtype="float32"):
            self.a, self.dtype = np.asarray(a, np.float32), dtype

        def __truediv__(self, k):
            return _T(self.a / k, self.dtype)

        def to(self, dtype):
            return _T(self.a, dtype)

    class Pipe041:
        tokenizer, text_encoder = _Tok(), _TE("v5")
        _execution_device = "cpu"
        vae = types.SimpleNamespace(dtype="float32", config=types.SimpleNamespace(scaling_factor=0.18215),
                                    decode=lambda z, return_dict=True: (z,))
        image_processor = types.SimpleNamespace(postprocess=lambda image, output_type="np": [image.a])
        scheduler = types.SimpleNamespace()

        def __call__(self, **kw):
            if kw.get("clip_skip"):
                self.text_encoder.text_model.final_layer_norm  # noqa: B018  AttributeError（真機症狀）
            assert "prompt_embeds" in kw and "negative_prompt_embeds" in kw and "prompt" not in kw
            return types.SimpleNamespace(images=_T(np.full((1, 4, 8, 8), 0.5)))

    p = DiffusersImageProvider("sd15", checkpoint=ck.get_checkpoint("meinamix_v12"), checkpoint_path="x")
    plan = RuntimePlan("cuda", "float32", True, True, True, True, 512, vae_fp32=True)
    arr = p._run_pipe(Pipe041(), plan, ImageRequest(prompt="a girl", width=1920, height=1080, params={"gen_policy": "native"}))
    assert arr is not None and p._gen_info["clip_skip_encoding"]["ordering_verified"]
    assert p._gen_info["clip_skip_encoding"]["layer_index_used"] == 2
