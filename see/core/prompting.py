"""中文 visual_description → 英文 image prompt（確定性關鍵詞對照；Phase 1 無 LLM 時的 prompt 路徑）。

真正的 LLM Provider 接上後可直接產生 image_prompt_en；本模組作為 Mock 與 fallback。
"""

from __future__ import annotations

import re

# 依「最長詞優先」比對；只涵蓋常見故事名詞／場景／動作，未命中則退回通用描述
ZH_EN: dict[str, str] = {
    "老和尚": "an old monk", "小和尚": "a young monk boy", "和尚": "a monk", "小廟": "a small temple", "廟": "a temple",
    "山": "mountains", "溪邊": "by a stream", "溪": "a stream", "河": "a river", "海": "the sea", "天空": "the sky",
    "遠方": "far away horizon", "石階": "stone steps", "石頭": "rocks", "院子": "a courtyard", "森林": "a forest",
    "樹": "trees", "花": "flowers", "草藥": "herbs", "小鳥": "a small bird", "鳥": "a bird", "翅膀": "wings",
    "小貓咪": "a kitten", "小貓": "a kitten", "貓": "a cat", "小狗": "a puppy", "狗": "a dog", "蝴蝶": "butterflies",
    "兔子": "a rabbit", "魚": "fish", "龍": "a dragon", "村莊": "a village", "城市": "a city", "房子": "a house",
    "學校": "a school", "教室": "a classroom", "老師": "a teacher", "媽媽": "a mother", "爸爸": "a father",
    "爺爺": "a grandfather", "奶奶": "a grandmother", "小孩": "a child", "女孩": "a girl", "男孩": "a boy",
    "清晨": "early morning light", "夜晚": "night", "月亮": "the moon", "星星": "stars", "陽光": "warm sunlight",
    "雨": "rain", "雪": "snow", "風": "wind", "雲": "clouds", "挑水": "carrying water buckets", "飛": "flying",
    "睡著": "sleeping", "追": "chasing", "受傷": "injured", "回家": "going home", "修行": "meditation",
}
_STYLE = "storybook illustration, soft watercolor, warm light, cinematic composition, highly detailed"
_NEGATIVE = "text, watermark, logo, signature, lowres, blurry, deformed, extra limbs, bad anatomy, nsfw"
_KEYS = sorted(ZH_EN, key=len, reverse=True)


def zh_to_en_keywords(text: str, limit: int = 8) -> list[str]:
    found: list[str] = []
    remaining = text
    for k in _KEYS:
        if k in remaining:
            en = ZH_EN[k]
            if en not in found and not any(f.split()[-1] == en.split()[-1] for f in found):
                found.append(en)
            remaining = remaining.replace(k, " ")
        if len(found) >= limit:
            break
    return found


def build_image_prompt_en(visual_description: str, extra: str = "") -> str:
    kws = zh_to_en_keywords(visual_description)
    subject = ", ".join(kws) if kws else "a scene from a Chinese folk story"
    parts = [subject, _STYLE]
    if extra:
        parts.insert(1, extra)
    return ", ".join(parts)


def default_negative_prompt() -> str:
    return _NEGATIVE


def strip_scene_tag(text: str) -> str:
    return re.sub(r"（場景 \d+）", "", text).strip()
