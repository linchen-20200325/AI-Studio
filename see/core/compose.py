"""DG-26 Route A（D-057）：角色分開生成 → 去背 → 擺位 → 合成到同一 Scene（Layered Scene 的最小 PoC）。

零下載、零新依賴：只用 PIL＋numpy（向量化）。去背不用 segmentation 模型，而是「單色背景鍵控」：
角色層以 plain／simple background 生成 → 由圖片邊框估背景色 → 與背景色距離小且「與邊框連通」的像素視為背景
（連通性用 numpy 二值膨脹傳播，不會把人物內部同色區域挖空）→ 收邊 1 px → 高斯羽化。
鍵控品質不足（背景不夠單純、髮絲／半透明）是已知限制；若真機不足 → 另提 Decision Gate（segmentation 模型）。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

KEY_TOLERANCE = 38.0  # RGB 歐氏距離；背景色 ±此值內視為背景候選
FEATHER_PX = 2.0
COLOR_MATCH = 0.25  # 角色層亮度／色偏往背景平均值靠近的比例（0＝不調）
SHADOW_OPACITY = 0.25


@dataclass(frozen=True)
class Placement:
    """正規化座標（相對背景寬高）：center_x＝角色水平中心、bottom＝角色底緣、height＝角色高度。"""

    center_x: float
    bottom: float = 1.0
    height: float = 0.9

    @classmethod
    def parse(cls, text: str) -> "Placement":
        parts = [float(p) for p in text.split(",")]
        if not 1 <= len(parts) <= 3:
            raise ValueError(f"placement 應為 center_x[,bottom[,height]]：{text}")
        p = cls(*parts)
        if not (0.0 <= p.center_x <= 1.0 and 0.0 < p.bottom <= 1.5 and 0.05 <= p.height <= 1.5):
            raise ValueError(f"placement 超出範圍：{p}")
        return p


def _dilate(m: Any) -> Any:
    """4-鄰域二值膨脹（numpy；邊界不外溢）。"""
    import numpy as np

    out = m.copy()
    out[1:, :] |= m[:-1, :]
    out[:-1, :] |= m[1:, :]
    out[:, 1:] |= m[:, :-1]
    out[:, :-1] |= m[:, 1:]
    return out


def border_connected(candidate: Any, max_iter: int | None = None) -> Any:
    """candidate 中「與圖片邊框連通」的部分（二值傳播直到收斂）。O(iter·N)，iter ≤ 圖對角線長。"""
    import numpy as np

    seed = np.zeros_like(candidate)
    seed[0, :], seed[-1, :], seed[:, 0], seed[:, -1] = candidate[0, :], candidate[-1, :], candidate[:, 0], candidate[:, -1]
    reached = seed
    for _ in range(max_iter or sum(candidate.shape)):
        nxt = _dilate(reached) & candidate
        if (nxt == reached).all():
            break
        reached = nxt
    return reached


def key_matte(rgb: Any, tolerance: float = KEY_TOLERANCE, feather: float = FEATHER_PX) -> tuple[Any, dict[str, Any]]:
    """rgb（H×W×3 uint8）→ alpha（H×W float32 0..1）＋診斷資訊。背景色＝邊框像素中位數。"""
    import numpy as np
    from PIL import Image, ImageFilter

    a = rgb.astype(np.float32)
    border = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]])
    bg = np.median(border, axis=0)
    border_spread = float(np.median(np.linalg.norm(border - bg, axis=1)))
    dist = np.linalg.norm(a - bg, axis=2)
    background = border_connected(dist < tolerance)
    fg = Image.fromarray((~background).astype(np.uint8) * 255).filter(ImageFilter.MinFilter(3))  # 收邊 1 px，去背景色暈邊
    if feather > 0:
        fg = fg.filter(ImageFilter.GaussianBlur(feather))
    alpha = np.asarray(fg, dtype=np.float32) / 255.0
    coverage = float(alpha.mean())
    warnings = []
    if border_spread > tolerance / 2:
        warnings.append(f"background not plain (border spread {border_spread:.1f} > {tolerance / 2:.1f})")
    if not 0.03 <= coverage <= 0.85:
        warnings.append(f"subject coverage {coverage:.3f} outside 0.03..0.85")
    return alpha, {"method": "border-color key + border-connected flood (numpy) + 1px erode + gaussian feather",
                   "background_rgb": [round(float(v), 1) for v in bg], "border_spread": round(border_spread, 2),
                   "tolerance": tolerance, "feather_px": feather, "coverage": round(coverage, 4),
                   "matte_suspect": bool(warnings), "warnings": warnings}


def alpha_bbox(alpha: Any, thr: float = 0.05) -> tuple[int, int, int, int]:
    import numpy as np

    ys, xs = np.nonzero(alpha > thr)
    if ys.size == 0:
        raise ValueError("matte is empty (no subject found)")
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def color_match(rgb: Any, alpha: Any, target_mean: Any, strength: float = COLOR_MATCH) -> Any:
    """角色像素（alpha 加權）的各通道平均值往 target_mean 平移 strength 比例（簡單光色統一，不重畫）。"""
    import numpy as np

    a = rgb.astype(np.float32)
    w = alpha[..., None]
    mean = (a * w).sum(axis=(0, 1)) / max(float(w.sum()), 1e-6)
    return np.clip(a + strength * (np.asarray(target_mean, np.float32) - mean), 0, 255)


def composite_layers(background: Any, layers: list[dict[str, Any]], color_strength: float = COLOR_MATCH,
                     shadow_opacity: float = SHADOW_OPACITY) -> tuple[Any, list[dict[str, Any]]]:
    """background：H×W×3 uint8；layers 依深度順序（先畫在後方）：{layer_id, rgb, alpha, placement}。
    回傳 (合成圖 uint8, 每層實際放置資訊)。每層獨立：重做某一層只需換該層，其他層原樣重用。"""
    import numpy as np
    from PIL import Image, ImageFilter

    H, W = background.shape[:2]
    canvas = background.astype(np.float32)
    bg_mean = canvas.reshape(-1, 3).mean(axis=0)
    placed = []
    for ly in layers:
        x0, y0, x1, y1 = alpha_bbox(ly["alpha"])
        rgb = color_match(ly["rgb"][y0:y1, x0:x1], ly["alpha"][y0:y1, x0:x1], bg_mean, color_strength)
        al = ly["alpha"][y0:y1, x0:x1]
        p: Placement = ly["placement"]
        th = max(1, int(round(p.height * H)))
        tw = max(1, int(round(al.shape[1] * th / al.shape[0])))
        rgb_s = np.asarray(Image.fromarray(rgb.astype(np.uint8)).resize((tw, th), Image.LANCZOS), np.float32)
        al_s = np.asarray(Image.fromarray((al * 255).astype(np.uint8)).resize((tw, th), Image.LANCZOS), np.float32) / 255.0
        left = int(round(p.center_x * W - tw / 2))
        top = int(round(p.bottom * H - th))
        # 畫布與層的交集（允許部分出界，例如半身像底緣切齊畫面）
        cx0, cy0, cx1, cy1 = max(left, 0), max(top, 0), min(left + tw, W), min(top + th, H)
        if cx0 >= cx1 or cy0 >= cy1:
            raise ValueError(f"layer {ly['layer_id']} placed completely outside the scene: {p}")
        sx0, sy0 = cx0 - left, cy0 - top
        sub_al = al_s[sy0:sy0 + cy1 - cy0, sx0:sx0 + cx1 - cx0][..., None]
        sub_rgb = rgb_s[sy0:sy0 + cy1 - cy0, sx0:sx0 + cx1 - cx0]
        if shadow_opacity > 0:  # 簡單接觸陰影：羽化後的 alpha 往右下偏移、壓暗背景
            sh = Image.fromarray((sub_al[..., 0] * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(max(2, th // 60)))
            dy, dx = max(1, th // 120), max(1, tw // 80)
            sh_a = np.zeros_like(sub_al[..., 0])
            sh_a[dy:, dx:] = (np.asarray(sh, np.float32) / 255.0)[:-dy, :-dx]  # 平移（不 wrap）
            region = canvas[cy0:cy1, cx0:cx1]
            canvas[cy0:cy1, cx0:cx1] = region * (1 - shadow_opacity * sh_a[..., None])
        region = canvas[cy0:cy1, cx0:cx1]
        canvas[cy0:cy1, cx0:cx1] = sub_rgb * sub_al + region * (1 - sub_al)
        placed.append({"layer_id": ly["layer_id"], "source_bbox": [x0, y0, x1, y1], "scaled_size": [tw, th],
                       "scene_box": [left, top, left + tw, top + th], "visible_box": [cx0, cy0, cx1, cy1],
                       "placement": {"center_x": p.center_x, "bottom": p.bottom, "height": p.height}})
    return np.clip(canvas, 0, 255).round().astype(np.uint8), placed


def overlap_ratio(a: list[int], b: list[int]) -> float:
    """兩個 visible_box 的交集面積 ÷ 較小者面積（人工審圖參考：遮擋程度）。"""
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    small = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))
    return round(ix * iy / small, 4) if small > 0 else 0.0
