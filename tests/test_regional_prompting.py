"""D-051（DG-24 A）：S1 長 prompt 分段編碼、S2 regional prompting。

純函式測試在 CI 執行；真實 diffusers／torch 整合測試（tiny 隨機權重、無下載）只在有 diffusers 的環境執行，
CI 無 torch 時 skip。真機品質由 Windows E2-5 證據覆蓋。
"""

from __future__ import annotations

import pytest

from see.providers.image.diffusers_local import CHUNK_TOKENS, chunk_token_ids, column_bounds, latent_level_shape


def test_chunk_token_ids_single_chunk_matches_standard_padding():
    bos, eos, pad = 1, 2, 2
    ids = [bos, 10, 11, 12, eos]
    (c,) = chunk_token_ids(ids, bos, eos, pad)
    assert c == [bos, 10, 11, 12, eos] + [pad] * (77 - 5)  # = tokenizer(padding="max_length", max_length=77)


def test_chunk_token_ids_long_prompt_splits_without_loss_and_aligns_negative():
    bos, eos, pad = 1, 2, 0
    body = list(range(100, 100 + 80))  # 80 內容 token（D-049 實測量級）
    chunks = chunk_token_ids([bos] + body + [eos], bos, eos, pad)
    assert len(chunks) == 2 and all(len(c) == 77 for c in chunks)
    assert [t for c in chunks for t in c if t not in (bos, eos, pad)] == body  # 不丟任何 token
    assert chunks[0][1:1 + CHUNK_TOKENS] == body[:CHUNK_TOKENS]
    neg = chunk_token_ids([bos, 50, eos], bos, eos, pad, n_chunks=2)
    assert len(neg) == 2 and neg[1] == [bos, eos] + [pad] * 75
    with pytest.raises(ValueError):
        chunk_token_ids([bos] + body + [eos], bos, eos, pad, n_chunks=1)


def test_latent_level_shape_and_columns():
    assert latent_level_shape(96 * 64, 64, 96) == (64, 96)
    assert latent_level_shape(48 * 32, 64, 96) == (32, 48)
    assert latent_level_shape(12 * 8, 64, 96) == (8, 12)
    assert latent_level_shape(3 * 2, 5, 3) == (3, 2)  # 奇數尺寸 ceil
    with pytest.raises(Exception):
        latent_level_shape(7, 64, 96)
    assert column_bounds(2, 12) == [(0, 6), (6, 12)]
    assert column_bounds(3, 8) == [(0, 3), (3, 5), (5, 8)]
    b = column_bounds(2, 7)
    assert b[0][0] == 0 and b[-1][1] == 7 and b[0][1] == b[1][0]


def test_regional_prompts_keep_attributes_out_of_base():
    from see.core.style_tests import get_case, regional_prompts

    base, (ra, rb) = regional_prompts(get_case("two_characters_ab"))
    assert base.startswith("two people side by side, ")
    for attr in ("glasses", "red coat", "grey", "black hair", "woman", "man,"):
        assert attr not in base
    assert "round glasses" in rb and "glasses" not in ra and "red coat" in ra and "red coat" not in rb
    with pytest.raises(ValueError):
        regional_prompts(get_case("girl_portrait_closeup"))


def test_style_test_cli_regional_and_long_prompt_flags(tmp_path, monkeypatch, capsys):
    import json as _json

    from see.app.cli import main

    monkeypatch.setenv("SEE_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.setenv("SEE_IMAGE_PROVIDER", "placeholder")
    monkeypatch.setenv("SEE_MODELS_DIR", str(tmp_path / "no-models"))
    main(["style-test", "--style", "realistic", "--case", "two_characters_ab", "--gen-policy", "native", "--regional"])
    main(["style-test", "--style", "realistic", "--case", "two_characters_ab", "--gen-policy", "native", "--long-prompt"])
    assert main(["style-test", "--style", "realistic", "--case", "girl_portrait_closeup", "--regional"]) == 2  # 單人案例不可 regional
    capsys.readouterr()
    d = tmp_path / "ws" / "style_tests"
    reg = _json.loads((d / "realistic_seed1234_two_characters_ab_native_regional.json").read_text(encoding="utf-8"))
    lp = _json.loads((d / "realistic_seed1234_two_characters_ab_native_longprompt.json").read_text(encoding="utf-8"))
    assert reg["diagnostic_overrides"]["regional"] and reg["diagnostic_overrides"]["long_prompt"]
    assert lp["diagnostic_overrides"]["long_prompt"] and not lp["diagnostic_overrides"]["regional"]
    assert reg["prompt"] == lp["prompt"]  # evidence 的 prompt 不變 → style-compare 只差 prompt_mode
    assert not (d / "realistic_seed1234_two_characters_ab_native.json").exists()  # 不覆寫 D-049 基準


def test_compare_prompt_mode_is_its_own_variable():
    from see.core.style_tests import compare_conditions

    g = {"gen_policy": "native", "gen_width": 768, "gen_height": 512, "steps": 25, "guidance": 7.0, "scheduler_name": "dpmpp_2m_karras"}
    ck = {"checkpoint_id": "cyberrealistic_final", "sha256": "2209c07b331a"}
    old = {"case_id": "two_characters_ab", "seed": 1234, "prompt": "p", "negative_prompt": "n", "width": 1920, "height": 1080,
           "final_dtype": "float32", "checkpoint": ck, "generation": {**g, "clip_skip_a1111": 1}}
    new = {**old, "generation": {**g, "clip_skip_a1111": 1, "prompt_mode": "regional"}}
    r = compare_conditions(old, new, intended=("prompt_mode",))
    assert r["verdict"] == "single_variable" and r["differences"] == {"prompt_mode": ["standard", "regional"]}


# ---------------------------------------------------------------- 真實 diffusers 整合（tiny 隨機權重；無下載）
class _FakeTok:
    """最小 CLIP 風格 tokenizer（空白／逗號切詞、雜湊成 id）；bos=1、eos=pad=2（同 SD 1.5：pad＝eos）。"""

    bos_token_id, eos_token_id, pad_token_id, model_max_length = 1, 2, 2, 77
    added_tokens_encoder: dict = {}

    def tokenize(self, text):
        return [w for w in text.replace(",", " , ").split() if w]

    def _ids(self, text):
        return [3 + (sum(ord(ch) * 31 ** i for i, ch in enumerate(w)) % 990) for w in self.tokenize(text)]

    def __call__(self, text, padding=None, max_length=None, truncation=False, return_tensors=None, add_special_tokens=True):
        import torch

        texts = [text] if isinstance(text, str) else list(text)
        rows = []
        for t in texts:
            ids = self._ids(t)
            if add_special_tokens:
                ids = [1] + ids + [2]
                if truncation and max_length and len(ids) > max_length:
                    ids = ids[:max_length - 1] + [2]
            rows.append(ids)
        if padding == "max_length":
            rows = [r + [2] * (max_length - len(r)) for r in rows]
        elif padding == "longest":
            m = max(len(r) for r in rows)
            rows = [r + [2] * (m - len(r)) for r in rows]
        out = type("Enc", (), {})()
        out.input_ids = torch.tensor(rows) if return_tensors == "pt" else (rows[0] if isinstance(text, str) else rows)
        out.attention_mask = None
        return out

    def batch_decode(self, ids):
        return ["" for _ in ids]


@pytest.fixture(scope="module")
def tiny_pipe():
    torch = pytest.importorskip("torch")
    pytest.importorskip("diffusers")
    pytest.importorskip("transformers")
    from diffusers import AutoencoderKL, DPMSolverMultistepScheduler, StableDiffusionPipeline, UNet2DConditionModel
    from transformers import CLIPTextConfig, CLIPTextModel

    torch.manual_seed(0)
    unet = UNet2DConditionModel(block_out_channels=(32, 64), layers_per_block=1, sample_size=16, in_channels=4, out_channels=4,
                                down_block_types=("CrossAttnDownBlock2D", "DownBlock2D"),
                                up_block_types=("UpBlock2D", "CrossAttnUpBlock2D"), cross_attention_dim=32, attention_head_dim=8)
    vae = AutoencoderKL(block_out_channels=[32, 64], in_channels=3, out_channels=3, latent_channels=4,
                        down_block_types=["DownEncoderBlock2D"] * 2, up_block_types=["UpDecoderBlock2D"] * 2)
    te = CLIPTextModel(CLIPTextConfig(vocab_size=1000, hidden_size=32, intermediate_size=37, num_hidden_layers=3,
                                      num_attention_heads=4, max_position_embeddings=77, bos_token_id=1, eos_token_id=2,
                                      pad_token_id=2, projection_dim=32))
    pipe = StableDiffusionPipeline(vae=vae, text_encoder=te.eval(), tokenizer=_FakeTok(), unet=unet.eval(),
                                   scheduler=DPMSolverMultistepScheduler(use_karras_sigmas=True, algorithm_type="dpmsolver++"),
                                   safety_checker=None, feature_extractor=None, requires_safety_checker=False)
    return pipe.to("cpu")


def _run(pipe, prompt, params):
    from see.providers.base import ImageRequest
    from see.providers.image.diffusers_local import DiffusersImageProvider, RuntimePlan

    prov = DiffusersImageProvider("sd15")
    prov.steps = 3
    plan = RuntimePlan("cpu", "float32", False, False, False, False, 64, vae_fp32=True)
    arr = prov._run_pipe(pipe, plan, ImageRequest(prompt=prompt, negative_prompt="lowres", width=96, height=54, seed=7,
                                                  params={"gen_policy": "native", **params}))
    return arr, prov._gen_info


def test_real_diffusers_s1_single_chunk_equals_standard_path(tiny_pipe):
    import numpy as np

    std, _ = _run(tiny_pipe, "a woman, red coat", {})
    lp, info = _run(tiny_pipe, "a woman, red coat", {"prompt_mode": {"long_prompt": True}})
    assert info["prompt_mode"] == "long_prompt" and info["prompt_encoding"]["chunks"] == 1
    assert np.allclose(std, lp, atol=1e-5)  # 短 prompt：分段編碼與 pipeline 標準編碼逐像素相同


def test_real_diffusers_s1_long_prompt_uses_two_chunks(tiny_pipe):
    long = ", ".join(f"word{i}" for i in range(60))  # >75 token
    arr, info = _run(tiny_pipe, long, {"prompt_mode": {"long_prompt": True}})
    assert info["prompt_encoding"]["chunks"] == 2 and info["prompt_truncated_effective"] is False and arr is not None


def test_real_diffusers_s2_identical_regions_equal_plain_and_processors_restored(tiny_pipe):
    import numpy as np

    before = {k: type(v).__name__ for k, v in tiny_pipe.unet.attn_processors.items()}
    lp, _ = _run(tiny_pipe, "a woman, red coat", {"prompt_mode": {"long_prompt": True}})
    same, info = _run(tiny_pipe, "a woman, red coat", {"prompt_mode": {"long_prompt": True, "regional": {
        "base": "a woman, red coat", "regions": ["a woman, red coat", "a woman, red coat"], "layout": "columns"}}})
    assert info["prompt_mode"] == "regional" and info["prompt_encoding"]["regions"] == 2
    assert np.allclose(lp, same, atol=1e-4)  # 各區相同 → 數學上等於一般 cross-attention（mask 總和＝1）
    diff, _ = _run(tiny_pipe, "x", {"prompt_mode": {"long_prompt": True, "regional": {
        "base": "two people", "regions": ["a woman, red coat", "a man, round glasses"], "layout": "columns"}}})
    assert not np.allclose(diff, same, atol=1e-3)
    after = {k: type(v).__name__ for k, v in tiny_pipe.unet.attn_processors.items()}
    assert before == after  # 快取 pipe 的 processor 已還原


def test_real_diffusers_s2_with_attention_slicing_and_clip_skip2(tiny_pipe):
    """GTX 1650 真機會開 attention slicing（低 VRAM）；MeinaMix preset clip skip 2 也要能走 regional。"""
    from see.providers.base import ImageRequest
    from see.providers.image.checkpoints import get_checkpoint
    from see.providers.image.diffusers_local import DiffusersImageProvider, RuntimePlan

    tiny_pipe.enable_attention_slicing()
    try:
        before = {k: type(v).__name__ for k, v in tiny_pipe.unet.attn_processors.items()}
        prov = DiffusersImageProvider("sd15")
        prov.steps, prov.checkpoint = 2, get_checkpoint("meinamix_v12")
        plan = RuntimePlan("cpu", "float32", True, True, False, False, 64, vae_fp32=True)
        arr = prov._run_pipe(tiny_pipe, plan, ImageRequest(prompt="x", negative_prompt="", width=96, height=54, seed=1, params={
            "gen_policy": "native", "prompt_mode": {"long_prompt": True, "regional": {
                "base": "two people", "regions": ["a woman", "a man"], "layout": "columns"}}}))
        assert arr is not None and prov._gen_info["prompt_encoding"]["clip_skip_a1111"] == 2
        assert {k: type(v).__name__ for k, v in tiny_pipe.unet.attn_processors.items()} == before
        assert "SlicedAttnProcessor" in set(before.values())
    finally:
        tiny_pipe.disable_attention_slicing()
