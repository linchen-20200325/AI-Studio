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
    assert prov.info.name == "black-image"  # info 只代表第一個可用候選（CLI providers.image.name 不可當生成證據）
    res = prov.generate_image(ImageRequest(prompt="山", width=64, height=36), tmp_path / "a.png")
    assert prov.info.name == "black-image"  # fallback 後 info 仍穩定（fingerprint key 不漂移，D-023）
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


# ---------------------------------------------------------------- D-022: fp32 escalation with fp16-only local weights
from see.providers.image.diffusers_local import load_kwargs, local_weight_variants, pick_variant  # noqa: E402


def _fake_model_dir(tmp_path: Path, variants: dict[str, list[str | None]]) -> Path:
    root = tmp_path / "sd15"
    (root / "model_index.json").parent.mkdir(parents=True, exist_ok=True)
    (root / "model_index.json").write_text("{}")
    for comp, vs in variants.items():
        (root / comp).mkdir(parents=True, exist_ok=True)
        for v in vs:
            name = ("model" if comp == "text_encoder" else "diffusion_pytorch_model") + (f".{v}" if v else "") + ".safetensors"
            (root / comp / name).write_bytes(b"\0")
    return root


def test_fp16_only_weights_are_reused_for_fp32_plan(tmp_path: Path):
    """真機事實：image-download 只抓 fp16 檔；fp32 升級必須仍用 variant=fp16（載入時 upcast），不得去找不存在的 fp32 檔。"""
    root = _fake_model_dir(tmp_path, {"unet": ["fp16"], "vae": ["fp16"], "text_encoder": ["fp16"]})
    assert local_weight_variants(root) == {"unet": {"fp16"}, "vae": {"fp16"}, "text_encoder": {"fp16"}}
    assert pick_variant(str(root), "fp16", "float16") == "fp16"
    assert pick_variant(str(root), "fp16", "float32") == "fp16"
    kw = load_kwargs(RuntimePlan("cuda", "float32", True, True, True, True, 512, True), "fp16", "sd15", "F32", supports_dtype=True)
    assert kw["variant"] == "fp16" and kw["dtype"] == "F32" and "torch_dtype" not in kw and kw["safety_checker"] is None
    kw_old = load_kwargs(RuntimePlan("cuda", "float16", True, True, True, True, 512), None, "sd15", "F16", supports_dtype=False)
    assert kw_old["torch_dtype"] == "F16" and "variant" not in kw_old


def test_pick_variant_prefers_complete_set_and_reports_incomplete(tmp_path: Path):
    fp32_only = _fake_model_dir(tmp_path / "a", {"unet": [None], "vae": [None], "text_encoder": [None]})
    assert pick_variant(str(fp32_only), "fp16", "float16") is None  # 只有 fp32 檔 → 不要求 fp16 variant
    both = _fake_model_dir(tmp_path / "b", {"unet": ["fp16", None], "vae": ["fp16", None], "text_encoder": ["fp16", None]})
    assert pick_variant(str(both), "fp16", "float32") == "fp16"
    broken = _fake_model_dir(tmp_path / "c", {"unet": ["fp16"], "vae": ["fp16"], "text_encoder": []})
    with pytest.raises(ProviderError, match="image-download"):
        pick_variant(str(broken), "fp16", "float16")
    assert pick_variant(None, "fp16", "float16") == "fp16" and pick_variant(None, "fp16", "float32") is None  # HF cache：舊行為


def test_numeric_floor_is_carried_to_next_scene(monkeypatch, tmp_path: Path):
    """第一景 fp16 → NaN → fp32 成功後，第二景直接從 fp32 開始（不重走階梯），evidence 標 plan_origin。"""
    good = np.random.default_rng(2).random((36, 64, 3)).astype(np.float32)
    nan = good.copy(); nan[0, 0, 0] = np.nan
    prov = DiffusersImageProvider("sd15")
    plans = _prime(monkeypatch, prov, [nan, good, good])
    r1 = prov.generate_image(ImageRequest(prompt="a", width=64, height=36), tmp_path / "1.png")
    r2 = prov.generate_image(ImageRequest(prompt="b", width=64, height=36), tmp_path / "2.png")
    assert [p.dtype for p in plans] == ["float16", "float32", "float32"]
    assert r1.meta["plan_origin"] == "fresh" and r1.meta["numeric_downgrade"] is True
    assert r2.meta["plan_origin"].startswith("carried") and r2.meta["numeric_downgrade"] is False
    assert r2.meta["final_dtype"] == "float32" and r2.meta["initial_plan"]["dtype"] == "float32"
    assert r2.meta["fp32_source"] == "upcast fp16 variant at load (no extra download)"


# ---------------------------------------------------------------- D-023: fallback (degraded) artifacts are not valid cache; regen semantics
class _FlakyProvider(ImageProvider):
    """模擬 diffusers：對 fail_seeds 內的 seed 失敗（→ Fallback 退 placeholder），其餘產生雜訊圖。"""

    def __init__(self, fail_seeds: set[int], available: bool = True) -> None:
        self.fail_seeds, self.available, self.calls = fail_seeds, available, 0

    @property
    def info(self) -> ProviderInfo:
        return ProviderInfo(name="diffusers-fake", kind=ProviderKind.IMAGE, cost_tier=CostTier.LOCAL_FREE, model="fake", version="1")

    def is_available(self) -> bool:
        return self.available

    def unavailable_reason(self) -> str:
        return "weights missing"

    def estimate_cost(self, request):
        return self._estimate(1, "image")

    def generate_image(self, request: ImageRequest, out_path: Path) -> ImageResult:
        self.calls += 1
        if request.seed in self.fail_seeds:
            raise ProviderError("simulated NaN even in fp32")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        Image.effect_noise((request.width, request.height), 64).convert("RGB").save(out_path)
        return ImageResult(path=str(out_path), width=request.width, height=request.height, provider=self.info.name, model="fake",
                           meta={"final_dtype": "float32"})


def _image_entries(orch, pid):
    return {s.scene_id: orch.store.load_manifest(pid, s.scene_id).entries["image"] for s in orch.store.load(pid).scenes}


@requires_ffmpeg
def test_fallback_artifact_is_retried_once_preferred_provider_works(orchestrator, providers):
    """真機情境：scene_001 在 provider 壞掉時退回 placeholder 並被快取；修好後下一次 run 必須重試，其他景繼續 reuse。"""
    flaky = _FlakyProvider(fail_seeds={0})
    providers.image = FallbackImageProvider([flaky, PlaceholderImageProvider()])
    rep = orchestrator.run(TINY_STORY, project_id="dg1")
    ents = _image_entries(orchestrator, "dg1")
    first = rep.project.scenes[0].scene_id
    assert ents[first].provider == "placeholder-image" and ents[first].meta["degraded"] is True and ents[first].meta["fallback"] is True
    assert all(e.provider == "diffusers-fake" and e.meta["degraded"] is False for sid, e in ents.items() if sid != first)
    # provider 修好（不改任何 prompt / fingerprint）
    flaky.fail_seeds = set()
    calls = flaky.calls
    rep2 = orchestrator.rebuild(orchestrator.store.load("dg1"))
    r1 = next(r for r in rep2.scene_reports if r.scene_id == first)
    assert r1.rebuilt == ["image", "clip"] and "degraded artifact from fallback provider placeholder-image" in r1.reasons["image"]
    assert r1.image_meta["generated_by"] == "diffusers-fake" and r1.image_meta["degraded"] is False
    assert all(r.rebuilt == [] for r in rep2.scene_reports if r.scene_id != first)
    assert flaky.calls == calls + 1
    # 再跑一次：全部 reuse（不 churn）
    rep3 = orchestrator.rebuild(orchestrator.store.load("dg1"))
    assert all(r.rebuilt == [] for r in rep3.scene_reports)


@requires_ffmpeg
def test_placeholder_cache_is_kept_while_preferred_provider_unavailable(orchestrator, providers):
    """首選 provider 不可用（無權重）時，placeholder 快取是合法的，不得每次 run 都重做。"""
    providers.image = FallbackImageProvider([_FlakyProvider(set(), available=False), PlaceholderImageProvider()])
    orchestrator.run(TINY_STORY, project_id="dg2")
    rep = orchestrator.rebuild(orchestrator.store.load("dg2"))
    assert all(r.rebuilt == [] for r in rep.scene_reports)
    assert all(e.meta["degraded"] is False for e in _image_entries(orchestrator, "dg2").values())


@requires_ffmpeg
def test_regen_rebuilds_scene_and_next_run_keeps_it(orchestrator, providers):
    flaky = _FlakyProvider(set())
    providers.image = flaky
    rep = orchestrator.run(TINY_STORY, project_id="rg1")
    target = rep.project.scenes[1].scene_id
    before = {s.scene_id: orchestrator.store.load_manifest("rg1", s.scene_id).entries["clip"].fingerprint for s in rep.project.scenes}
    calls = flaky.calls
    r = orchestrator.regenerate_scene(orchestrator.store.load("rg1"), target)
    assert r.rebuilt == ["image", "narration", "subtitle", "clip"] and flaky.calls == calls + 1  # 只重做指定景
    after = {s.scene_id: orchestrator.store.load_manifest("rg1", s.scene_id).entries["clip"].fingerprint for s in rep.project.scenes}
    assert after[target] != before[target]  # 雜訊圖內容不同 → clip fingerprint（含圖檔 sha）失效
    assert all(after[s] == before[s] for s in before if s != target)
    rep2 = orchestrator.run(TINY_STORY, project_id="rg1")  # 下一次 run 沿用 regen 結果，不再重做
    assert all(x.rebuilt == [] for x in rep2.scene_reports)


# ---------------------------------------------------------------- D-035: 生成解析度診斷（gen_policy）與 prompt token 證據
def test_native_policy_crops_to_target_aspect_and_records_generation(monkeypatch, tmp_path: Path):
    prov = DiffusersImageProvider("sd15")
    good = np.random.default_rng(2).random((512, 768, 3)).astype(np.float32)
    _prime(monkeypatch, prov, [good])

    def fake_run(pipe, plan, request):
        prov._gen_info = {"gen_policy": request.params.get("gen_policy", "fit"), "gen_width": 768, "gen_height": 512}
        return good

    monkeypatch.setattr(prov, "_run_pipe", fake_run)
    res = prov.generate_image(ImageRequest(prompt="cat", width=2880, height=1620, seed=1, params={"gen_policy": "native"}),
                              tmp_path / "n.png")
    m = res.meta
    assert m["crop_box"] == [0, 40, 768, 472] and m["upscale_factor"] == 3.75 and m["gen_height"] == 512
    assert res.width == 2880 and res.height == 1620


def test_run_pipe_native_size_and_token_evidence(monkeypatch):
    class T:
        def __init__(self, a, dtype="float32"):
            self.a, self.dtype = np.asarray(a, np.float32), dtype

        def __truediv__(self, k):
            return T(self.a / k, self.dtype)

        def to(self, dtype):
            return T(self.a, dtype)

    seen = {}

    class Tok:
        model_max_length = 77

        def __call__(self, text):
            return types.SimpleNamespace(input_ids=[0] * (len(text.split()) + 2))

    class Pipe:
        vae = types.SimpleNamespace(dtype="float32", config=types.SimpleNamespace(scaling_factor=0.18215),
                                    decode=lambda z, return_dict=True: (z,))
        image_processor = types.SimpleNamespace(postprocess=lambda image, output_type="np": [image.a])
        tokenizer = Tok()
        scheduler = types.SimpleNamespace()

        def __call__(self, **kw):
            seen.update(kw)
            return types.SimpleNamespace(images=T(np.full((1, 4, 8, 8), 0.5)))

    fake_torch = types.ModuleType("torch")
    fake_torch.inference_mode = contextlib.nullcontext
    fake_torch.Generator = lambda device="cpu": types.SimpleNamespace(manual_seed=lambda s: s)
    fake_torch.isfinite = lambda t: types.SimpleNamespace(all=lambda: True)
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    prov = DiffusersImageProvider("sd15")
    plan = RuntimePlan("cuda", "float32", True, True, True, True, 512, vae_fp32=True)
    long_prompt = " ".join(["word"] * 100)
    prov._run_pipe(Pipe(), plan, ImageRequest(prompt=long_prompt, width=2880, height=1620, params={"gen_policy": "native"}))
    assert (seen["width"], seen["height"]) == (768, 512)
    g = prov._gen_info
    assert g["prompt_tokens"] == 102 and g["prompt_truncated"] is True and g["negative_truncated"] is False
    assert g["steps"] == 25 and g["guidance"] == 7.0 and g["gen_policy"] == "native"
    prov._run_pipe(Pipe(), plan, ImageRequest(prompt="cat", width=2880, height=1620))
    assert (seen["width"], seen["height"]) == (512, 288) and prov._gen_info["gen_policy"] == "fit"
    with pytest.raises(Exception):
        prov._run_pipe(Pipe(), plan, ImageRequest(prompt="cat", params={"gen_policy": "bogus"}))
