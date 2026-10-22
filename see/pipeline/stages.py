"""各階段的純函式：輸入 model → 輸出 model。不碰檔案系統（除 provider 本身寫檔）。"""

from __future__ import annotations

from see.core.errors import SchemaViolation
from see.models.scene import Scene, StoryboardDraft
from see.models.script import Script, ScriptDraft
from see.providers.base import LLMProvider, LLMRequest

SCRIPT_SYSTEM = (
    "你是影片編劇。把輸入的中文故事改寫成結構化劇本 JSON：title、logline、characters、beats。"
    "每個 beat 是一段 2–4 句的旁白，依故事順序，不新增原文沒有的情節。"
)
STORYBOARD_SYSTEM = (
    "你是分鏡師。把劇本的每個 beat 轉成一個 scene：規劃秒數、旁白、視覺描述、圖片 prompt、"
    "影片 prompt、鏡頭運動（static/zoom_in/zoom_out/pan_left/pan_right/pan_up/pan_down）、"
    "轉場（cut/fade/dissolve/wipe_left/slide_left/fade_black）、音效提示。輸出 JSON。"
)


def write_script(llm: LLMProvider, story: str, title: str | None = None, language: str = "zh-TW") -> Script:
    story = story.strip()
    if not story:
        raise SchemaViolation("input story is empty")
    req = LLMRequest(task="script", system=SCRIPT_SYSTEM, user=story,
                     inputs={"story": story, "title": title, "language": language})
    draft = llm.complete_json(req, ScriptDraft)
    return Script.model_validate(draft.model_dump())


def make_storyboard(llm: LLMProvider, script: Script) -> list[Scene]:
    req = LLMRequest(task="storyboard", system=STORYBOARD_SYSTEM, user=script.model_dump_json(),
                     inputs={"script": script.model_dump()})
    draft = llm.complete_json(req, StoryboardDraft)
    if len(draft.scenes) != len(script.beats):
        raise SchemaViolation(f"storyboard returned {len(draft.scenes)} scenes for {len(script.beats)} beats")
    return [Scene.from_draft(s, scene_id=f"scene_{s.index + 1:03d}") for s in draft.scenes]
