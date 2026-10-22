"""PlaceholderImageProvider：PIL 產生確定性漸層圖 + 場景文字。LOCAL_FREE。"""

from __future__ import annotations

import colorsys
import hashlib
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from see.core.errors import ProviderError
from see.models.cost import CostEstimate
from see.models.enums import CostTier, ProviderKind
from see.models.provider import ProviderInfo
from see.providers.base import ImageProvider, ImageRequest, ImageResult

_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
    "/System/Library/Fonts/PingFang.ttc",
    "C:/Windows/Fonts/msjh.ttc",
]


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for p in _FONT_CANDIDATES:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def _palette(seed_text: str) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    h = int(hashlib.sha256(seed_text.encode("utf-8")).hexdigest()[:8], 16)
    hue = (h % 360) / 360.0
    c1 = tuple(int(v * 255) for v in colorsys.hsv_to_rgb(hue, 0.55, 0.35))
    c2 = tuple(int(v * 255) for v in colorsys.hsv_to_rgb((hue + 0.12) % 1.0, 0.45, 0.75))
    return c1, c2  # type: ignore[return-value]


def _wrap(text: str, max_chars: int) -> list[str]:
    return [text[i:i + max_chars] for i in range(0, len(text), max_chars)] or [""]


class PlaceholderImageProvider(ImageProvider):
    def __init__(self) -> None:
        self.calls = 0

    @property
    def info(self) -> ProviderInfo:
        return ProviderInfo(name="placeholder-image", kind=ProviderKind.IMAGE, cost_tier=CostTier.LOCAL_FREE,
                            model="pil-gradient", version="1")

    def estimate_cost(self, request: ImageRequest) -> CostEstimate:
        return self._estimate(units=1, unit_name="image")

    def generate_image(self, request: ImageRequest, out_path: Path) -> ImageResult:
        self.calls += 1
        w, h = request.width, request.height
        if w <= 0 or h <= 0:
            raise ProviderError(f"invalid size {w}x{h}")
        c1, c2 = _palette(request.prompt + str(request.seed or ""))
        img = Image.new("RGB", (w, h), c1)
        draw = ImageDraw.Draw(img)
        # 垂直漸層（逐列填色，h ≤ 2160，成本可忽略）
        for y in range(h):
            t = y / max(h - 1, 1)
            col = tuple(int(c1[k] * (1 - t) + c2[k] * t) for k in range(3))
            draw.line([(0, y), (w, y)], fill=col)
        # 裝飾：半透明圓
        overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        od = ImageDraw.Draw(overlay)
        r = int(min(w, h) * 0.28)
        od.ellipse([w * 0.62 - r, h * 0.5 - r, w * 0.62 + r, h * 0.5 + r], fill=(255, 255, 255, 40))
        img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
        draw = ImageDraw.Draw(img)
        # 文字：caption（場景描述）
        font_big = _load_font(int(h * 0.075))
        font_small = _load_font(int(h * 0.035))
        caption = request.caption or request.prompt
        lines = _wrap(caption, 12)[:3]
        y = int(h * 0.30)
        for line in lines:
            draw.text((int(w * 0.14) + 3, y + 3), line, font=font_big, fill=(0, 0, 0))
            draw.text((int(w * 0.14), y), line, font=font_big, fill=(255, 255, 255))
            y += int(h * 0.11)
        draw.text((int(w * 0.14), int(h * 0.84)), "placeholder · see phase 0", font=font_small, fill=(255, 255, 255))
        out_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(out_path, format="PNG", optimize=True)
        return ImageResult(path=str(out_path), width=w, height=h, provider=self.info.name, model=self.info.model)
