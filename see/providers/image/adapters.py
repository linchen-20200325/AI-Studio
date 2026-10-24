"""Identity conditioning（S4，IP-Adapter 類）adapter 型錄——**只有資料與守門，沒有下載、沒有載入**（D-053）。

- 型錄是候選清單，不是核准：`approved=False` 時任何下載／載入都必須拒絕（等 DG-25 客戶裁示）。
- 只收 `.safetensors`；sha256／bytes 取自 HF API（固定 revision，原始證據 `docs/evidence/dg24/`）。
- `commercial_cleared` 一律 False：adapter 權重 Apache-2.0，但 image encoder（OpenCLIP ViT-H-14，MIT）訓練資料 LAION-5B
  官方建議研究用途；且底模（SD 1.5／CyberRealistic／MeinaMix）各自另有限制。
"""

from __future__ import annotations

from dataclasses import dataclass

USAGE = "internal_quality_validation_only"


@dataclass(frozen=True)
class AdapterFile:
    path: str  # repo 內路徑
    bytes: int
    sha256: str | None  # LFS sha256；小型 config 無 LFS → None（以 bytes＋revision 固定）


@dataclass(frozen=True)
class AdapterSpec:
    adapter_id: str
    kind: str  # "ip_adapter"
    base_arch: str  # "sd15"
    repo: str
    revision: str
    files: tuple[AdapterFile, ...]
    license_status: str
    license_evidence: str
    approved: bool = False  # DG-25 裁示前一律 False
    commercial_cleared: bool = False
    usage: str = USAGE
    notes: tuple[str, ...] = ()

    @property
    def total_bytes(self) -> int:
        return sum(f.bytes for f in self.files)


ADAPTERS: dict[str, AdapterSpec] = {a.adapter_id: a for a in [
    AdapterSpec(
        adapter_id="ip_adapter_plus_face_sd15", kind="ip_adapter", base_arch="sd15",
        repo="h94/IP-Adapter", revision="018e402774aeeddd60609b4ecdb7e298259dc729",
        files=(
            AdapterFile("models/ip-adapter-plus-face_sd15.safetensors", 98_183_288,
                        "1c9edc21af6f737dc1d6e0e734190e976cfacf802d6b024b77aa3be922f7569b"),
            AdapterFile("models/image_encoder/model.safetensors", 2_528_373_448,
                        "6ca9667da1ca9e0b0f75e46bb030f7e011f44f86cbfb8d5a36590fcd7507b030"),
            AdapterFile("models/image_encoder/config.json", 560, None),
        ),
        license_status=("adapter：Apache-2.0（HF cardData＋tencent-ailab/IP-Adapter LICENSE）；image encoder：OpenCLIP ViT-H-14 "
                        "laion2B-s32B-b79K，MIT（HF cardData），訓練資料 LAION-5B 官方建議研究用途、不建議直接做工業產品"),
        license_evidence=("docs/evidence/dg24/hf_h94_IP-Adapter.api.json；hf_h94_IP-Adapter.README.md；"
                          "github_tencent-ailab_IP-Adapter.LICENSE；hf_laion_CLIP-ViT-H-14.api.json／README.md"),
        notes=("臉部參考（cropped face）條件；patch embeddings（plus）比 global（base）更貼近參考",
               "diffusers 0.41 內建 load_ip_adapter＋IPAdapterMaskProcessor（每角色一張參考＋區域 mask）"),
    ),
]}


def get_adapter(adapter_id: str) -> AdapterSpec:
    if adapter_id not in ADAPTERS:
        raise ValueError(f"unknown adapter '{adapter_id}'; available: {sorted(ADAPTERS)}")
    return ADAPTERS[adapter_id]


def assert_usable(spec: AdapterSpec) -> None:
    """下載／載入前的守門（fail-closed）。"""
    bad = [f.path for f in spec.files if not (f.path.endswith(".safetensors") or f.path.endswith(".json"))]
    if bad:
        raise ValueError(f"only .safetensors weights are allowed: {bad}")
    if not spec.approved:
        raise PermissionError(f"adapter {spec.adapter_id} is not approved (Decision Gate DG-25); nothing downloaded or loaded")
