from see.core.prompting import build_image_prompt_en, default_negative_prompt, zh_to_en_keywords
from see.models import ScriptDraft, StoryboardDraft
from see.providers.base import LLMRequest
from see.providers.llm.mock import MockLLMProvider
from tests.conftest import TINY_STORY


def test_keywords_longest_match_and_dedupe():
    kws = zh_to_en_keywords("廟裡住著一位老和尚和一個小和尚，廟旁有一間小廟")
    assert "an old monk" in kws and "a young monk boy" in kws
    assert sum(1 for k in kws if k.endswith("temple")) == 1


def test_prompt_en_always_english_nonempty():
    p = build_image_prompt_en("完全沒有關鍵詞的句子")
    assert p.startswith("a scene from a Chinese folk story") and p.isascii()
    assert "storybook" in build_image_prompt_en("小貓咪在院子裡追蝴蝶")


def test_mock_storyboard_fills_en_prompt_and_negative():
    llm = MockLLMProvider()
    sc = llm.complete_json(LLMRequest(task="script", inputs={"story": TINY_STORY}), ScriptDraft)
    sb = llm.complete_json(LLMRequest(task="storyboard", inputs={"script": sc.model_dump()}), StoryboardDraft)
    for s in sb.scenes:
        assert s.image_prompt_en.isascii() and len(s.image_prompt_en) > 20
        assert s.negative_prompt == default_negative_prompt()
