"""D-056：S4 A／B identity binding 追溯——角色 position → region → mask 欄位 → IP-Adapter image index，並以真實 diffusers
processor 證明「交換 A／B 參考圖時，對應區域跟著交換」（不只是輸出不同）。"""
import dataclasses
import types

import pytest

from tests.test_identity_adapters import _tiny_ip_adapter, _ws


def test_region_of_is_explicit_and_fail_closed():
    from see.core.style_tests import region_of

    assert region_of("on the left") == ("left", 0) and region_of("On the Right ") == ("right", 2)
    with pytest.raises(ValueError):
        region_of("somewhere")


def test_identity_refs_ordered_by_position_not_tuple_order(tmp_path, monkeypatch):
    from see.app.cli import _identity_references
    from see.core.config import Settings
    from see.core.style_tests import get_case

    _ws(tmp_path, monkeypatch)
    case = get_case("two_characters_ab")
    args = ["char_b=ref_male", "char_a=ref_female"]  # --ref 給的順序不影響
    refs, err = _identity_references(Settings(), case, args)
    assert err is None and [(r["character_id"], r["region"]) for r in refs] == [("char_a", "left"), ("char_b", "right")]
    # characters tuple 反過來排（B 在前）→ 仍依 position 排成 A=left、B=right
    flipped = dataclasses.replace(case, characters=case.characters[::-1])
    refs2, err2 = _identity_references(Settings(), flipped, args)
    assert err2 is None and [(r["character_id"], r["region"]) for r in refs2] == [("char_a", "left"), ("char_b", "right")]
    # 兩人同一位置 → 拒絕
    same = dataclasses.replace(case, characters=tuple(dataclasses.replace(c, position="on the left") for c in case.characters))
    assert _identity_references(Settings(), same, args)[1]


def test_identity_region_map_output_coordinates():
    from see.app.cli import identity_region_map

    ident = {"references": [
        {"character_id": "char_a", "sha256": "a" * 64, "assigned_region": "left", "adapter_index": 0, "image_index": 0,
         "mask_bounds_gen_px": [0, 0, 384, 512]},
        {"character_id": "char_b", "sha256": "b" * 64, "assigned_region": "right", "adapter_index": 0, "image_index": 1,
         "mask_bounds_gen_px": [384, 0, 768, 512]}]}
    m = identity_region_map(ident, [0, 40, 768, 472])  # native 768×512 → 16:9 中心裁切（只裁上下）
    assert [r["mask_bounds_output_px"] for r in m] == [[0, 0, 384, 432], [384, 0, 768, 432]]
    assert [(r["character_id"], r["assigned_region"], r["image_index"]) for r in m] == [("char_a", "left", 0), ("char_b", "right", 1)]


def test_provider_rejects_right_to_left_reference_order():
    pytest.importorskip("torch")
    pytest.importorskip("diffusers")
    from see.core.errors import ProviderError
    from see.providers.image.diffusers_local import DiffusersImageProvider

    prov = DiffusersImageProvider("sd15")
    prov.identity_adapter, prov.identity_dir = types.SimpleNamespace(adapter_id="x"), "x"
    with pytest.raises(ProviderError):
        prov._identity_kwargs(None, {"adapter_id": "x", "references": [{"region": "right"}, {"region": "left"}]}, 96, 64, None)


def test_real_diffusers_swapping_refs_swaps_regions(tmp_path):
    """真實 diffusers 0.41 IPAdapterAttnProcessor2_0：攔截第一個 step 第一個 attn2（其輸入與 IP 條件無關、三次執行完全相同），
    比較 [A,B]／[A,A]／[B,B] 的 cond 輸出：左欄只受 refs[0] 影響、右欄只受 refs[1] 影響；A／B 對調 → 區域跟著對調。"""
    torch = pytest.importorskip("torch")
    pytest.importorskip("diffusers")
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
    pipe.enable_attention_slicing()
    spec, root = _tiny_ip_adapter(tmp_path, unet)
    ref = {}
    for name, color in (("A", (220, 60, 60)), ("B", (60, 60, 220))):
        p = tmp_path / f"{name}.png"
        Image.new("RGB", (48, 48), color).save(p)
        ref[name] = {"path": str(p), "sha256": name * 64, "bytes": 1, "source": "local_file"}
    plan = RuntimePlan("cpu", "float32", True, True, False, False, 64, vae_fp32=True)
    attn2 = pipe.unet.down_blocks[0].attentions[0].transformer_blocks[0].attn2

    def probe(left, right):
        refs = [{**ref[left], "character_id": "char_a", "region": "left"}, {**ref[right], "character_id": "char_b", "region": "right"}]
        cap = []
        h = attn2.register_forward_hook(lambda m, i, o: cap.append(o.detach().clone()) if not cap else None)
        try:
            prov = DiffusersImageProvider("sd15", identity_adapter=spec, identity_dir=str(root))
            prov.steps = 1
            prov._run_pipe(pipe, plan, ImageRequest(prompt="two people", negative_prompt="", width=96, height=54, seed=3,
                                                    params={"gen_policy": "native", "identity": {"adapter_id": "tiny_ipa",
                                                                                                 "references": refs}}))
        finally:
            h.remove()
        info = prov._gen_info
        f = pipe.vae_scale_factor  # tiny VAE＝2（SD1.5＝8）；96×64 → latent 48×32（非正方形，驗 downsample 幾何）
        gh, gw = info["gen_height"] // f, info["gen_width"] // f
        return cap[0][1].reshape(gh, gw, -1), info["identity"]  # CFG batch 的 cond 半邊

    ab, info = probe("A", "B")
    aa, _ = probe("A", "A")
    bb, _ = probe("B", "B")
    ba, _ = probe("B", "A")
    half = ab.shape[1] // 2
    # tiny VAE 只縮 2 倍 → diffusers bicubic 下採樣在交界欄有 overshoot（SD1.5 的 8～64 倍無此現象，見下一個測試）；排除交界兩欄
    L, R = slice(0, half - 1), slice(half + 1, None)

    def diff(x, y):
        return (x - y).abs().amax().item()

    assert diff(ab[:, L], aa[:, L]) < 1e-5 and diff(ab[:, R], aa[:, R]) > 1e-3  # 右欄只受 refs[1]
    assert diff(ab[:, R], bb[:, R]) < 1e-5 and diff(ab[:, L], bb[:, L]) > 1e-3  # 左欄只受 refs[0]
    # 對調 A／B：[B,A] 的左欄＝[B,B] 的左欄、右欄＝[A,A] 的右欄 → 區域跟著交換
    assert diff(ba[:, L], bb[:, L]) < 1e-5 and diff(ba[:, R], aa[:, R]) < 1e-5
    r = info["references"]
    assert [(x["character_id"], x["assigned_region"], x["adapter_index"], x["image_index"]) for x in r] == \
        [("char_a", "left", 0, 0), ("char_b", "right", 0, 1)]
    assert r[0]["mask_bounds_gen_px"] == [0, 0, 48, 64] and r[1]["mask_bounds_gen_px"] == [48, 0, 96, 64]


@pytest.mark.parametrize("gw,gh", [(768, 512), (576, 384)])  # GTX 1650 native；OOM 降級後
def test_sd15_mask_downsample_is_exact_columns(gw, gh):
    """diffusers 0.41 `IPAdapterMaskProcessor.downsample` 在 SD1.5 各 attention 層（latent 1/8～1/64）的實際 mask：
    左欄恰為 1、右欄恰為 0，無轉置／翻轉／交界滲漏。"""
    pytest.importorskip("torch")
    pytest.importorskip("diffusers")
    from diffusers.image_processor import IPAdapterMaskProcessor

    from see.providers.image.diffusers_local import identity_column_masks

    m = IPAdapterMaskProcessor().preprocess(identity_column_masks(2, gw, gh), height=gh, width=gw).reshape(1, 2, gh, gw)
    for f in (8, 16, 32, 64):
        h, w = gh // f, gw // f
        # 欄 j 覆蓋像素 [j·f, (j+1)·f)：完全在左半＝左欄、完全在右半＝右欄；寬度為奇數時正中一欄跨界（576 寬的 1/64 層＝9 欄）
        left = [j for j in range(w) if (j + 1) * f <= gw // 2]
        right = [j for j in range(w) if j * f >= gw // 2]
        assert len(left) + len(right) >= w - 1
        for i in (0, 1):
            d = IPAdapterMaskProcessor.downsample(m[:, i], 1, h * w, 4)[0, :, 0].reshape(h, w)
            assert d[:, left].eq(1 - i).all() and d[:, right].eq(i).all()


def test_reference_library_people_only(tmp_path, monkeypatch):
    from PIL import Image

    from see.app.cli import _identity_references
    from see.core.config import Settings
    from see.core.style_tests import get_case

    _ws(tmp_path, monkeypatch)
    lib = tmp_path / "ws" / "reference_library"
    for sub, color in (("people", (10, 20, 30)), ("animals", (30, 20, 10))):
        (lib / sub).mkdir(parents=True)
        Image.new("RGB", (32, 32), color).save(lib / sub / "x.png")
    case = get_case("two_characters_ab")
    refs, err = _identity_references(Settings(), case, ["char_a=people/x.png", "char_b=ref_male"])
    assert err is None and refs[0]["source"] == "reference_library" and refs[0]["library_category"] == "people"
    _, err = _identity_references(Settings(), case, ["char_a=animals/x.png", "char_b=ref_male"])
    assert err and "not yet supported" in err  # 動物／角色／背景／風格尚未支援，不得假裝
    # legacy identity_refs/ 仍可用（相容路徑）
    legacy = tmp_path / "ws" / "identity_refs" / "people"
    legacy.mkdir(parents=True)
    Image.new("RGB", (32, 32), (90, 10, 10)).save(legacy / "y.png")
    refs, err = _identity_references(Settings(), case, ["char_a=people/y.png", "char_b=ref_male"])
    assert err is None and refs[0]["source"] == "reference_library_legacy"


def test_identity_overlay_written_next_to_output(tmp_path):
    from PIL import Image

    from see.app.cli import _identity_overlay

    p = tmp_path / "out.png"
    Image.new("RGB", (96, 54), (0, 0, 0)).save(p)
    rm = [{"character_id": "char_a", "assigned_region": "left", "reference_sha256": "a" * 64, "mask_bounds_output_px": [0, 0, 48, 54]},
          {"character_id": "char_b", "assigned_region": "right", "reference_sha256": "b" * 64, "mask_bounds_output_px": [48, 0, 96, 54]}]
    out = _identity_overlay(p, rm)
    assert out.name == "out_identity_regions.png" and Image.open(out).size == (96, 54)
    assert Image.open(p).getpixel((5, 5)) == (0, 0, 0)  # 原圖不被改動（evidence sha256 不變）
