import shutil
from pathlib import Path

import pytest

from see.core.errors import SchemaViolation
from see.models import CostTier, ScriptDraft, StoryboardDraft
from see.models.enums import CameraMotion
from see.providers.base import ImageRequest, LLMRequest, TTSRequest
from see.providers.image.placeholder import PlaceholderImageProvider
from see.providers.llm.mock import MockLLMProvider
from see.providers.tts.espeak import EspeakTTSProvider
from see.providers.tts.silent import SilentTTSProvider
from see.providers.video.kenburns import zoompan_expr
from tests.conftest import TINY_STORY


def test_mock_llm_is_deterministic_and_schema_valid():
    llm = MockLLMProvider()
    a = llm.complete_json(LLMRequest(task="script", inputs={"story": TINY_STORY}), ScriptDraft)
    b = llm.complete_json(LLMRequest(task="script", inputs={"story": TINY_STORY}), ScriptDraft)
    assert a == b and len(a.beats) >= 1
    assert "".join(x.narration for x in a.beats) == TINY_STORY.replace(" ", "")
    sb = llm.complete_json(LLMRequest(task="storyboard", inputs={"script": a.model_dump()}), StoryboardDraft)
    assert len(sb.scenes) == len(a.beats)
    assert all(3.0 <= s.duration <= 12.0 for s in sb.scenes)
    assert llm.info.cost_tier == CostTier.LOCAL_FREE


def test_mock_llm_rejects_empty_story_and_unknown_task():
    llm = MockLLMProvider()
    with pytest.raises(SchemaViolation):
        llm.complete_json(LLMRequest(task="script", inputs={"story": "   "}), ScriptDraft)
    with pytest.raises(SchemaViolation):
        llm.complete_json(LLMRequest(task="poem", inputs={}), ScriptDraft)


def test_mock_llm_long_story_caps_scene_count():
    llm = MockLLMProvider()
    story = "這是一句話。" * 200
    d = llm.complete_json(LLMRequest(task="script", inputs={"story": story}), ScriptDraft)
    assert 1 <= len(d.beats) <= 60  # 長文不會爆炸成數百景


def test_placeholder_image_writes_png(tmp_path: Path):
    prov = PlaceholderImageProvider()
    res = prov.generate_image(ImageRequest(prompt="山上的小廟", width=320, height=180, caption="場景一"), tmp_path / "a.png")
    assert Path(res.path).exists() and res.width == 320
    from PIL import Image
    with Image.open(res.path) as im:
        assert im.size == (320, 180)
    # 不同 prompt → 不同畫面
    prov.generate_image(ImageRequest(prompt="海邊", width=320, height=180), tmp_path / "b.png")
    assert (tmp_path / "a.png").read_bytes() != (tmp_path / "b.png").read_bytes()


def test_silent_tts_duration_scales_with_text(tmp_path: Path):
    tts = SilentTTSProvider()
    r1 = tts.synthesize(TTSRequest(text="短"), tmp_path / "1.wav")
    r2 = tts.synthesize(TTSRequest(text="這是一段比較長的旁白文字喔"), tmp_path / "2.wav")
    assert r2.duration > r1.duration >= 0.5
    assert (tmp_path / "1.wav").stat().st_size > 44


@pytest.mark.skipif(shutil.which("espeak-ng") is None or shutil.which("ffprobe") is None, reason="espeak-ng not installed")
def test_espeak_tts_produces_audio(tmp_path: Path):
    tts = EspeakTTSProvider()
    r = tts.synthesize(TTSRequest(text="你好，這是測試。", language="zh-TW"), tmp_path / "e.wav")
    assert r.duration > 0.5 and Path(r.path).stat().st_size > 1000


def test_zoompan_expressions_cover_all_motions():
    for m in CameraMotion:
        e = zoompan_expr(m.value, 50)
        assert e.startswith("z='") and ":x='" in e and ":y='" in e
    assert zoompan_expr("nonsense", 50) == "z='1':x='0':y='0'"
