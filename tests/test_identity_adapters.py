"""D-053／D-054：S4 Identity adapter 型錄守門、下載驗證、style-test --identity、真實 diffusers 整合（tiny 權重、無下載）。"""

from __future__ import annotations

import pytest

from see.providers.image.adapters import ADAPTERS, AdapterFile, AdapterSpec, assert_usable, get_adapter


def test_ip_adapter_catalog_approved_by_dg25_but_not_commercial():
    a = get_adapter("ip_adapter_plus_face_sd15")
    assert a.approved and not a.commercial_cleared and a.usage == "internal_quality_validation_only"  # DG-25（D-054）
    assert a.total_bytes == 98_183_288 + 2_528_373_448 + 560  # ≈2.63 GB
    assert all(f.path.endswith((".safetensors", ".json")) for f in a.files)
    assert all(f.sha256 and len(f.sha256) == 64 for f in a.files if f.path.endswith(".safetensors"))
    assert_usable(a)
    assert a.weight_file.path == "models/ip-adapter-plus-face_sd15.safetensors"
    assert a.encoder_file.path == "models/image_encoder/model.safetensors"
    with pytest.raises(PermissionError):
        assert_usable(AdapterSpec("y", "ip_adapter", "sd15", "r", "v", a.files, "", ""))  # 未核准一律拒絕
    with pytest.raises(ValueError):
        get_adapter("ip_adapter_faceid_sd15")  # FaceID（pickle＋InsightFace 非商用）不列入


def test_assert_usable_rejects_pickle_even_if_approved():
    bad = AdapterSpec("x", "ip_adapter", "sd15", "r", "v", (AdapterFile("m.bin", 1, "0" * 64),), "", "", approved=True)
    with pytest.raises(ValueError):
        assert_usable(bad)
    assert set(ADAPTERS) == {"ip_adapter_plus_face_sd15"}


# ---------------------------------------------------------------- D-054 下載驗證（無網路：以本機假檔案驗證核對邏輯）
def _fake_spec(tmp_path, approved=True):
    import hashlib

    files = []
    for rel, data in (("models/w.safetensors", b"weights"), ("models/image_encoder/model.safetensors", b"enc"),
                      ("models/image_encoder/config.json", b"{}")):
        files.append(AdapterFile(rel, len(data), hashlib.sha256(data).hexdigest() if rel.endswith(".safetensors") else None))
    return AdapterSpec("fake_ipa", "ip_adapter", "sd15", "r", "v", tuple(files), "", "", approved=approved), {
        "models/w.safetensors": b"weights", "models/image_encoder/model.safetensors": b"enc", "models/image_encoder/config.json": b"{}"}


def test_validate_remote_and_verify_local(tmp_path):
    from see.providers.image import adapters as ad

    spec, blobs = _fake_spec(tmp_path)
    remote = {f.path: {"bytes": f.bytes, "sha256": f.sha256} for f in spec.files}
    assert ad.validate_remote(spec, remote) == []
    assert ad.validate_remote(spec, {**remote, "models/w.safetensors": {"bytes": 1, "sha256": "x"}})
    assert ad.validate_remote(spec, {})[0].startswith("missing remote")
    d = ad.adapter_dir(tmp_path, spec)
    assert ad.verify_local(tmp_path, spec)  # 尚未存在
    for rel, data in blobs.items():
        (d / rel).parent.mkdir(parents=True, exist_ok=True)
        (d / rel).write_bytes(data)
    assert ad.verify_local(tmp_path, spec) == [] and not ad.is_verified(tmp_path, spec)
    ad.write_provenance(tmp_path, spec, remote)
    assert ad.is_verified(tmp_path, spec)
    (d / "models/w.safetensors").write_bytes(b"weightX")  # 同大小、內容被改
    assert ad.verify_local(tmp_path, spec) == ["sha256 mismatch models/w.safetensors"]


def test_download_adapter_deletes_on_mismatch(tmp_path, monkeypatch):
    import sys
    import types

    from see.providers.image import adapters as ad

    spec, blobs = _fake_spec(tmp_path)
    remote = {f.path: {"bytes": f.bytes, "sha256": f.sha256} for f in spec.files}
    monkeypatch.setattr(ad, "fetch_remote_metadata", lambda sp: remote)

    def fake_dl(repo_id, filename, revision, local_dir, corrupt=False):
        p = ad.Path(local_dir) / filename
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(blobs[filename] if not corrupt else b"x" * len(blobs[filename]))
        return str(p)

    hub = types.ModuleType("huggingface_hub")
    hub.hf_hub_download = fake_dl
    monkeypatch.setitem(sys.modules, "huggingface_hub", hub)
    prov = ad.download_adapter(tmp_path, spec)
    assert prov["verified"] and ad.is_verified(tmp_path, spec)
    assert (tmp_path / "adapters" / ".gitignore").read_text() == "*\n"
    spec2 = AdapterSpec("fake2", "ip_adapter", "sd15", "r", "v", spec.files, "", "", approved=True)
    hub.hf_hub_download = lambda **kw: fake_dl(corrupt=True, **kw)
    with pytest.raises(ValueError):
        ad.download_adapter(tmp_path, spec2)
    assert not any((ad.adapter_dir(tmp_path, spec2) / f.path).exists() for f in spec2.files)  # 不符即刪除


def test_adapter_download_cli_plan_and_verify(tmp_path, monkeypatch, capsys):
    from see.app.cli import main

    monkeypatch.setenv("SEE_MODELS_DIR", str(tmp_path / "models"))
    assert main(["adapter-download", "ip_adapter_plus_face_sd15"]) == 0  # 只印計畫
    assert main(["adapter-download", "ip_adapter_plus_face_sd15", "--verify"]) == 3  # 本機沒有檔案
    capsys.readouterr()


# ---------------------------------------------------------------- D-054 style-test --identity（CI：參考圖與守門）
def _ws(tmp_path, monkeypatch):
    from PIL import Image

    monkeypatch.setenv("SEE_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.setenv("SEE_IMAGE_PROVIDER", "placeholder")
    monkeypatch.setenv("SEE_MODELS_DIR", str(tmp_path / "models"))
    d = tmp_path / "ws" / "style_tests"
    d.mkdir(parents=True)
    Image.new("RGB", (64, 64), (200, 100, 100)).save(d / "ref_female.png")
    Image.new("RGB", (64, 64), (100, 100, 200)).save(d / "ref_male.png")
    return d


def test_identity_references_validation(tmp_path, monkeypatch, capsys):
    from see.app.cli import main

    _ws(tmp_path, monkeypatch)
    base = ["style-test", "--style", "realistic", "--case", "two_characters_ab", "--gen-policy", "native", "--identity",
            "ip_adapter_plus_face_sd15"]
    assert main(base + ["--ref", "char_a=ref_female"]) == 2  # 每角色都要一張
    assert main(base + ["--ref", "char_a=ref_female", "--ref", "char_b=ref_female"]) == 2  # A／B 不可相同
    assert main(base + ["--ref", "char_a=https://x/y.png", "--ref", "char_b=ref_male"]) == 2  # 只收本機（§16）
    assert main(base + ["--ref", "char_a=ref_female", "--ref", "char_b=ref_male", "--regional"]) == 2  # 不疊 S2
    # 參考圖都對，但 adapter 未下載驗證 → fail-closed（不 fallback 到 placeholder／一般生成）
    assert main(base + ["--ref", "char_a=ref_female", "--ref", "char_b=ref_male"]) == 2
    err = capsys.readouterr().err
    assert "adapter-download ip_adapter_plus_face_sd15" in err
    assert main(["style-test", "--style", "realistic", "--case", "girl_portrait_closeup", "--identity",
                 "ip_adapter_plus_face_sd15", "--ref", "char_a=ref_female"]) == 2  # 單人案例無 characters


def test_identity_references_resolve_stems_with_provenance(tmp_path, monkeypatch):
    from see.app.cli import _identity_references
    from see.core.style_tests import get_case
    from see.core.config import Settings

    d = _ws(tmp_path, monkeypatch)
    refs, err = _identity_references(Settings(), get_case("two_characters_ab"), ["char_a=ref_female", f"char_b={d / 'ref_male.png'}"])
    assert err is None and [r["character_id"] for r in refs] == ["char_a", "char_b"]
    assert refs[0]["source"] == "style_test_output" and refs[0]["source_evidence"] == "ref_female.json"
    assert refs[1]["source"] == "local_file" and len(refs[1]["sha256"]) == 64 and refs[0]["sha256"] != refs[1]["sha256"]


def test_compare_identity_mode_is_experiment_variable():
    from see.core.style_tests import compare_conditions

    g = {"gen_policy": "native", "gen_width": 768, "gen_height": 512, "steps": 25, "guidance": 7.0,
         "scheduler_name": "dpmpp_2m_karras", "clip_skip_a1111": 1}
    a = {"case_id": "two_characters_ab", "seed": 1234, "prompt": "p", "negative_prompt": "n", "width": 1920, "height": 1080,
         "final_dtype": "float32", "checkpoint": {"checkpoint_id": "cyberrealistic_final", "sha256": "2209c07b331a"}, "generation": g}
    b = {**a, "generation": {**g, "identity": {"adapter_id": "ip_adapter_plus_face_sd15"}}}
    r = compare_conditions(a, b)
    assert r["verdict"] == "single_variable" and r["differences"] == {"identity_mode": ["none", "ip_adapter_plus_face_sd15"]}
    c = {**b, "generation": {**b["generation"], "prompt_mode": "long_prompt"}}
    assert compare_conditions(a, c)["verdict"] == "not_comparable"  # identity＋prompt_mode 同時變


# ---------------------------------------------------------------- 真實 diffusers 整合（tiny 隨機權重；無下載；CI 無 torch → skip）
def _tiny_ip_adapter(tmp_path, unet):
    """依 diffusers 0.41 `_convert_ip_adapter_image_proj_to_diffusers` 的 IP-Adapter Plus 原始鍵格式產生 tiny 權重（safetensors）。"""
    import torch
    from safetensors.torch import save_file
    from transformers import CLIPVisionConfig, CLIPVisionModelWithProjection

    g = torch.Generator().manual_seed(0)

    def r(*shape):
        return torch.randn(*shape, generator=g) * 0.02

    embed, cross, hid, q = 32, 32, 64, 4
    d = {"image_proj.latents": r(1, q, hid), "image_proj.proj_in.weight": r(hid, embed), "image_proj.proj_in.bias": r(hid),
         "image_proj.proj_out.weight": r(cross, hid), "image_proj.proj_out.bias": r(cross),
         "image_proj.norm_out.weight": torch.ones(cross), "image_proj.norm_out.bias": torch.zeros(cross)}
    for i in range(4):
        p = f"image_proj.layers.{i}."
        d.update({p + "0.norm1.weight": torch.ones(hid), p + "0.norm1.bias": torch.zeros(hid),
                  p + "0.norm2.weight": torch.ones(hid), p + "0.norm2.bias": torch.zeros(hid),
                  p + "0.to_q.weight": r(hid, hid), p + "0.to_kv.weight": r(2 * hid, hid), p + "0.to_out.weight": r(hid, hid),
                  p + "1.0.weight": torch.ones(hid), p + "1.0.bias": torch.zeros(hid), p + "1.1.weight": r(4 * hid, hid),
                  p + "1.3.weight": r(hid, 4 * hid)})
    for key_id, name in enumerate(unet.attn_processors):
        if name.endswith("attn2.processor"):
            hs = unet.get_submodule(name.rsplit(".processor", 1)[0]).to_k.out_features
            d[f"ip_adapter.{key_id}.to_k_ip.weight"] = r(hs, cross) * 50
            d[f"ip_adapter.{key_id}.to_v_ip.weight"] = r(hs, cross) * 50
    root = tmp_path / "ipa"
    (root / "models").mkdir(parents=True)
    save_file(d, str(root / "models" / "w.safetensors"))
    enc = CLIPVisionModelWithProjection(CLIPVisionConfig(hidden_size=embed, intermediate_size=37, num_hidden_layers=3,
                                                         num_attention_heads=4, image_size=32, patch_size=8, projection_dim=32))
    enc.save_pretrained(str(root / "models" / "image_encoder"))
    files = (AdapterFile("models/w.safetensors", 1, None), AdapterFile("models/image_encoder/model.safetensors", 1, None))
    return AdapterSpec("tiny_ipa", "ip_adapter", "sd15", "r", "v", files, "", "", approved=True), root


def test_real_diffusers_identity_two_refs_masks_and_unload(tmp_path):
    torch = pytest.importorskip("torch")
    pytest.importorskip("diffusers")
    import numpy as np
    from PIL import Image

    from see.providers.base import ImageRequest
    from see.providers.image.diffusers_local import DiffusersImageProvider, RuntimePlan
    from tests.test_regional_prompting import _FakeTok

    from diffusers import AutoencoderKL, DPMSolverMultistepScheduler, StableDiffusionPipeline, UNet2DConditionModel
    from transformers import CLIPTextConfig, CLIPTextModel

    torch.manual_seed(0)
    unet = UNet2DConditionModel(block_out_channels=(32, 64), layers_per_block=1, sample_size=16, in_channels=4, out_channels=4,
                                down_block_types=("CrossAttnDownBlock2D", "DownBlock2D"),
                                up_block_types=("UpBlock2D", "CrossAttnUpBlock2D"), cross_attention_dim=32, attention_head_dim=8)
    vae = AutoencoderKL(block_out_channels=[32, 64], in_channels=3, out_channels=3, latent_channels=4,
                        down_block_types=["DownEncoderBlock2D"] * 2, up_block_types=["UpDecoderBlock2D"] * 2)
    te = CLIPTextModel(CLIPTextConfig(vocab_size=1000, hidden_size=32, intermediate_size=37, num_hidden_layers=3, num_attention_heads=4,
                                      max_position_embeddings=77, bos_token_id=1, eos_token_id=2, pad_token_id=2, projection_dim=32))
    pipe = StableDiffusionPipeline(vae=vae, text_encoder=te.eval(), tokenizer=_FakeTok(), unet=unet.eval(),
                                   scheduler=DPMSolverMultistepScheduler(use_karras_sigmas=True, algorithm_type="dpmsolver++"),
                                   safety_checker=None, feature_extractor=None, requires_safety_checker=False).to("cpu")
    pipe.enable_attention_slicing()  # 同 GTX 1650 低 VRAM 計畫
    spec, root = _tiny_ip_adapter(tmp_path, unet)
    refs = []
    for cid, color in (("char_a", (220, 60, 60)), ("char_b", (60, 60, 220))):
        p = tmp_path / f"{cid}.png"
        Image.new("RGB", (48, 48), color).save(p)
        refs.append({"character_id": cid, "path": str(p), "sha256": cid * 8, "bytes": 1, "source": "local_file"})
    plan = RuntimePlan("cpu", "float32", True, True, False, False, 64, vae_fp32=True)
    before = {k: type(v).__name__ for k, v in pipe.unet.attn_processors.items()}

    def run(identity):
        prov = DiffusersImageProvider("sd15", identity_adapter=spec, identity_dir=str(root))
        prov.steps = 2
        params = {"gen_policy": "native", **({"identity": identity} if identity else {})}
        arr = prov._run_pipe(pipe, plan, ImageRequest(prompt="two people", negative_prompt="", width=96, height=54, seed=3,
                                                      params=params))
        return arr, prov

    plain, _ = run(None)
    ident, prov = run({"adapter_id": "tiny_ipa", "references": refs, "layout": "columns"})
    info = prov._gen_info["identity"]
    assert info["image_encoder_device"] == "cpu" and info["mask"]["order"] == ["char_a", "char_b"]
    assert [r["character_id"] for r in info["references"]] == ["char_a", "char_b"] and not info["combined_with_regional"]
    assert not np.allclose(plain, ident, atol=1e-4)  # identity 條件確實影響輸出
    # 兩張參考圖對調 → 輸出不同（每角色分區條件，不是單一全圖平均）
    swapped, _ = run({"adapter_id": "tiny_ipa", "references": refs[::-1], "layout": "columns"})
    assert not np.allclose(ident, swapped, atol=1e-5)
    # 卸載後 processor 與 encoder_hid_proj 還原 → 之後一般生成與最初逐像素相同
    assert {k: type(v).__name__ for k, v in pipe.unet.attn_processors.items()} == before
    assert getattr(pipe.unet, "encoder_hid_proj", None) is None
    again, _ = run(None)
    assert np.allclose(plain, again, atol=1e-6)
    # 同一 provider 第二次用相同參考圖 → embeds 快取命中
    prov._run_pipe(pipe, plan, ImageRequest(prompt="two people", width=96, height=54, seed=3,
                                            params={"gen_policy": "native", "identity": {"adapter_id": "tiny_ipa", "references": refs}}))
    assert prov._gen_info["identity"]["embeds_cache_hit"]
