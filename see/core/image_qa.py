"""影像產物內容驗證（Provider Agnostic）。

背景（D-021）：fingerprint 只能證明「輸入沒變」，不能證明「產物是好的」。Windows 真機上舊版 fp16 路徑留下的
全黑 image.png 曾被 manifest 當成有效快取重用，pipeline 因而回報成功。這裡提供唯一的影像內容檢查，
Orchestrator（快取重用前／生成後）、FallbackImageProvider（候選輸出後）、DiffusersImageProvider（存檔後）共用。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

BLACK_MAX_LEVEL = 5  # uint8；max ≤ 5 視為全黑（允許 PNG 壓縮／抖動造成的 1–2 階雜訊）
FLAT_STD_LEVEL = 1.0  # 標準差 < 1 視為單色平面（任何顏色）；平面圖對影片無意義


@dataclass(frozen=True)
class ImageStats:
    width: int
    height: int
    min: int
    max: int
    mean: float
    std: float

    @property
    def is_black(self) -> bool:
        return self.max <= BLACK_MAX_LEVEL

    @property
    def is_flat(self) -> bool:
        return self.std < FLAT_STD_LEVEL

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["is_black"], d["is_flat"] = self.is_black, self.is_flat
        return d


def image_stats(path: Path) -> ImageStats:
    """讀取影像並以 numpy 向量化計算統計；無法解碼時拋出例外（呼叫端決定如何處理）。"""
    import numpy as np
    from PIL import Image

    with Image.open(path) as im:
        arr = np.asarray(im.convert("RGB"), dtype=np.uint8)
    if arr.size == 0:
        raise ValueError(f"empty image: {path}")
    return ImageStats(width=int(arr.shape[1]), height=int(arr.shape[0]), min=int(arr.min()), max=int(arr.max()),
                      mean=round(float(arr.mean()), 3), std=round(float(arr.std()), 3))


def image_defect(path: Path) -> str | None:
    """回傳產物缺陷描述；None 代表可用。缺檔／無法解碼／全黑／單色平面皆為缺陷。"""
    p = Path(path)
    if not p.exists():
        return "missing"
    try:
        st = image_stats(p)
    except Exception as e:  # noqa: BLE001
        return f"undecodable ({type(e).__name__}: {e})"
    if st.is_black:
        return f"black (max={st.max} mean={st.mean})"
    if st.is_flat:
        return f"flat (std={st.std})"
    return None
