"""D-021 回歸：黑圖不得被當成有效快取、不得留在磁碟被 pipeline 視為成功；fp32 降級／fallback 的最終狀態可追蹤。"""

from __future__ import annotations

import contextlib
import json
import sys
import types
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from see.core.errors import ProviderError, RenderError
from see.core.image_qa import image_defect, image_stats
from see.models.enums import CostTier, ProviderKind
from see.models.provider import ProviderInfo
from see.providers.base import ImageProvider, ImageRequest, ImageResult
from see.providers.image.diffusers_local import PROVIDER_VERSION, DiffusersImageProvider, RuntimePlan
from see.providers.image.fallback import FallbackImageProvider
from see.providers.image.placeholder import PlaceholderImageProvider
from tests.conftest import TINY_STORY, requires_ffmpeg


def _write_black(path: Path, size=(64, 36)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, (0, 0, 0)).save(path, format="PNG")


class _BlackProvider(ImageProvider):
    """模擬「回報成功但寫出全黑 PNG」的 provider（舊版 fp16 路徑的行為）。"""

    def __init__(self) -> None:
        self.calls = 0

    @property
    def info(self) -> ProviderInfo:
        return ProviderInfo(name="black-image", kind=ProviderKind.IMAGE, cost_tier=CostTier.LOCAL_FREE, model="black")

    def estimate_cost(self, request):
        return self._estimate(1, "image")

    def generate_image(self, request: ImageRequest, out_path: Path) -> ImageResult:
        self.calls += 1
        _write_black(out_path, (request.width, request.height))
        return ImageResult(path=str(out_path), width=request.width, height=request.height, provider=self.info.name, model="black")


# ---------------------------------------------------------------- image_qa
def test_image_defect_classifies_black_flat_missing_and_ok(tmp_path: Path):
    _write_black(tmp_path / "black.png")
    assert image_defect(tmp_path / "black.png").startswith("black")
    Image.new("RGB", (16, 16), (120, 120, 120)).save(tmp_path / "flat.png")
    assert image_defect(tmp_path / "flat.png").startswith("flat")
    assert image_defect(tmp_path / "nope.png") == "missing"
    (tmp_path / "bad.png").write_bytes(b"not a png")
    assert image_defect(tmp_path / "bad.png").startswith("undecodable")
    PlaceholderImageProvider().generate_image(ImageRequest(prompt="山", width=64, height=36), tmp_path / "ok.png")
    assert image_defect(tmp_path / "ok.png") is None
    st = image_stats(tmp_path / "ok.png")
    assert st.width == 64 and st.max > 5 and not st.is_black and st.to_dict()["is_black"] is False


# ---------------------------------------------------------------- cache reuse
@requires_ffmpeg
def test_black_cached_artifact_is_not_reused(orchestrator, providers):
    rep = orchestrator.run(TINY_STORY, project_id="blk1")
    assert all("image" in r.rebuilt and r.image_meta["regenerated"] is True for r in rep.scene_reports)
    sid = rep.project.scenes[0].scene_id
    img = orchestrator.store.scene_dir("blk1", sid) / "image.png"
    _write_black(img, (96, 54))  # 模擬舊版留下的黑圖；manifest fingerprint 仍相同
    assert orchestrator.store.load_manifest("blk1", sid).valid("image", orchestrator.store.load_manifest("blk1", sid).entries["image"].fingerprint)
    calls = providers.image.calls
    rep2 = orchestrator.rebuild(orchestrator.store.load("blk1"))
    first = next(r for r in rep2.scene_reports if r.scene_id == sid)
    assert "image" in first.rebuilt and first.reasons["image"].startswith("cached artifact rejected: black")
    assert "clip" in first.reused  # placeholder 確定性 → 重生圖位元相同 → clip 合法重用
    assert first.image_meta["regenerated"] is True and first.image_meta["reason"].startswith("cached artifact rejected")
    assert providers.image.calls == calls + 1  # 只重生那一景
    assert image_defect(img) is None
    others = [r for r in rep2.scene_reports if r.scene_id != sid]
    assert others and all("image" in r.reused and r.image_meta["regenerated"] is False for r in others)
    # manifest 內留有證據
    rec = orchestrator.store.load_manifest("blk1", sid).entries["image"]
    assert rec.meta["generated_by"] == "placeholder-image" and rec.meta["image_stats"]["is_black"] is False
    # clip 綁定圖檔內容：圖檔內容改變（仍是有效圖）→ image 重用但 clip 必重做
    Image.effect_noise((96, 54), 60).convert("RGB").save(img)
    rep3 = orchestrator.rebuild(orchestrator.store.load("blk1"))
    first3 = next(r for r in rep3.scene_reports if r.scene_id == sid)
    assert "image" in first3.reused and "clip" in first3.rebuilt


@requires_ffmpeg
def test_provider_black_output_fails_pipeline_and_leaves_no_artifact(orchestrator, providers):
    providers.image = _BlackProvider()
    with pytest.raises(RenderError, match="unusable image"):
        orchestrator.run(TINY_STORY, project_id="blk2")
    sid = orchestrator.store.load("blk2").scenes[0].scene_id
    assert not (orchestrator.store.scene_dir("blk2", sid) / "image.png").exists()
    assert "image" not in orchestrator.store.load_manifest("blk2", sid).entries


# ---------------------------------------------------------------- fallback evidence
def test_fallback_rejects_black_candidate_and_records_true_generator(tmp_path: Path):
    black = _BlackProvider()
    prov = FallbackImageProvider([black, PlaceholderImageProvider()])
    assert prov.info.name == "black-image"  # 生成前 info 只代表第一個可用候選（CLI providers.image.name 不可當生成證據）
    res = prov.generate_image(ImageRequest(prompt="山", width=64, height=36), tmp_path / "a.png")
    assert res.provider == "placeholder-image" and res.meta["generated_by"] == "placeholder-image"
    assert res.meta["fallback"] is True and "black-image: output rejected: black" in res.meta["fallback_from"][0]
    assert prov.last_generated_by == "placeholder-image" and image_defect(tmp_path / "a.png") is None


def test_fallback_all_black_raises_and_cleans_file(tmp_path: Path):
    prov = FallbackImageProvider([_BlackProvider()])
    with pytest.raises(ProviderError, match="output rejected: black"):
        prov.generate_image(ImageRequest(prompt="山", width=64, height=36), tmp_path / "a.png")
    assert not (tmp_path / "a.png").exists()


# ---------------------------------------------------------------- diffusers ladder (no torch needed)
def test_provider_version_bumped_invalidates_old_fingerprints():
    info = DiffusersImageProvider("sd15").info
    assert info.version == PROVIDER_VERSION and PROVIDER_VERSION not in ("1", "2")
    old = ProviderInfo(name=info.name, kind=info.kind, cost_tier=info.cost_tier, model=info.model, version="2")
    assert old.fingerprint_key != info.fingerprint_key


def _prime(monkeypatch, prov: DiffusersImageProvider, outputs: list):
    """跳過 torch：固定 GTX 1650 cuda 裝置，_run_pipe 依序回傳預設結果。"""
    monkeypatch.setattr(prov, "is_available", lambda: True)
    monkeypatch.setattr(prov, "_resolve_device", lambda: ("cuda", 4095))
    prov.gpu_name = "NVIDIA GeForce GTX 1650"
    monkeypatch.setattr(prov, "_load", lambda plan: object())
    seq = iter(outputs)
    plans: list[RuntimePlan] = []

    def fake_run(pipe, plan, request):
        plans.append(plan)
        return next(seq)

    monkeypatch.setattr(prov, "_run_pipe", fake_run)
    return plans


def test_numeric_failure_escalates_to_fp32_and_evidence_is_traceable(monkeypatch, tmp_path: Path):
    good = np.random.default_rng(1).random((36, 64, 3)).astype(np.float32)
    nan = good.copy(); nan[0, 0, 0] = np.nan
    prov = DiffusersImageProvider("sd15")
    plans = _prime(monkeypatch, prov, [nan, good])
    res = prov.generate_image(ImageRequest(prompt="cat", width=64, height=36, seed=1), tmp_path / "o.png")
    assert [(p.dtype, p.vae_fp32) for p in plans] == [("float16", True), ("float32", True)]
    m = res.meta
    assert m["numeric_downgrade"] is True and m["final_dtype"] == "float32" and m["final_vae_fp32"] is True
    assert m["initial_plan"]["dtype"] == "float16" and m["oom_downgrade"] is False and m["generated_by"] == "diffusers-sd15"
    assert m["attempts"] == ["numeric failure (NaN/black) with dtype=float16 vae_fp32=True"]
    assert m["image_stats"]["is_black"] is False and (tmp_path / "o.png").exists()
    assert json.dumps(m)  # manifest 可序列化


def test_numeric_failure_in_fp32_leaves_no_black_file(monkeypatch, tmp_path: Path):
    prov = DiffusersImageProvider("sd15")
    plans = _prime(monkeypatch, prov, [None, np.zeros((36, 64, 3), np.float32), np.zeros((36, 64, 3), np.float32)])
    with pytest.raises(ProviderError, match="even in fp32"):
        prov.generate_image(ImageRequest(prompt="cat", width=64, height=36), tmp_path / "o.png")
    assert [p.dtype for p in plans] == ["float16", "float32"]  # GTX 1650 起點已是 vae_fp32 → 只剩一級可升
    assert not (tmp_path / "o.png").exists()


def test_saved_image_is_revalidated_after_write(monkeypatch, tmp_path: Path):
    """就算 ndarray 檢查被繞過（例如極低亮度 0.019 全圖），存檔後重開仍須擋下。"""
    prov = DiffusersImageProvider("sd15")
    dim = np.full((36, 64, 3), 0.015, np.float32); dim[0, 0, :] = 0.021  # max ≥ 0.02 → 通過 ndarray 檢查，但 uint8 全 ≤ 5
    _prime(monkeypatch, prov, [dim, dim, dim])
    with pytest.raises(ProviderError, match="saved image rejected: black"):
        prov.generate_image(ImageRequest(prompt="cat", width=64, height=36), tmp_path / "o.png")
    assert not (tmp_path / "o.png").exists()


def test_run_pipe_casts_latents_to_vae_dtype(monkeypatch):
    """H4：vae_fp32 時 latents 必須 cast 到 VAE dtype 再 decode（diffusers 0.41 SD1.5 pipeline 自己不會 cast）。"""

    class T:  # 極簡 tensor 替身
        def __init__(self, a, dtype="float16"):
            self.a, self.dtype = np.asarray(a, np.float32), dtype

        def __truediv__(self, k):
            return T(self.a / k, self.dtype)

        def to(self, dtype):
            return T(self.a, dtype)

    seen = {}

    class Vae:
        dtype = "float32"
        config = types.SimpleNamespace(scaling_factor=0.18215)

        def decode(self, z, return_dict=True):
            seen["dtype"] = z.dtype
            return (z,)

    class Proc:
        def postprocess(self, image, output_type="np"):
            return [np.clip(image.a, 0, 1)]

    class Pipe:
        vae, image_processor = Vae(), Proc()

        def __call__(self, **kw):
            seen["kw"] = kw
            return types.SimpleNamespace(images=T(np.full((1, 4, 8, 8), 0.5)))

    fake_torch = types.ModuleType("torch")
    fake_torch.inference_mode = contextlib.nullcontext
    fake_torch.Generator = lambda device="cpu": types.SimpleNamespace(manual_seed=lambda s: f"gen{s}")
    fake_torch.isfinite = lambda t: types.SimpleNamespace(all=lambda: bool(np.isfinite(t.a).all()))
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    prov = DiffusersImageProvider("sd15")
    plan = RuntimePlan("cuda", "float16", True, True, True, True, 512, vae_fp32=True)
    arr = prov._run_pipe(Pipe(), plan, ImageRequest(prompt="cat", width=640, height=360, seed=3))
    assert seen["dtype"] == "float32" and seen["kw"]["output_type"] == "latent" and seen["kw"]["generator"] == "gen3"
    assert seen["kw"]["width"] == 512 and seen["kw"]["height"] == 288 and arr.shape[0] == 1
    # UNet 階段 NaN → None（視為數值失敗，不浪費 VAE decode）
    Pipe.__call__ = lambda self, **kw: types.SimpleNamespace(images=T(np.full((1, 4, 8, 8), np.nan)))
    assert prov._run_pipe(Pipe(), plan, ImageRequest(prompt="cat", width=640, height=360)) is None
