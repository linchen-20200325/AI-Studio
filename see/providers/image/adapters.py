"""Identity conditioning（S4，IP-Adapter 類）adapter 型錄＋下載驗證（D-053／D-054）。

- 型錄是候選清單：`approved=False` 時任何下載／載入都必須拒絕；DG-25 客戶已核准 `ip_adapter_plus_face_sd15`（D-054）。
- 只收 `.safetensors`；sha256／bytes 取自 HF API（固定 revision，原始證據 `docs/evidence/dg24/`）。
- `commercial_cleared` 一律 False：adapter 權重 Apache-2.0，但 image encoder（OpenCLIP ViT-H-14，MIT）訓練資料 LAION-5B
  官方建議研究用途；且底模（SD 1.5／CyberRealistic／MeinaMix）各自另有限制。
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from see.core.hashing import file_sha256

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

    @property
    def weight_file(self) -> AdapterFile:
        return next(f for f in self.files if "image_encoder" not in f.path and f.path.endswith(".safetensors"))

    @property
    def encoder_file(self) -> AdapterFile:
        return next(f for f in self.files if f.path.endswith("image_encoder/model.safetensors"))


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
        approved=True,  # DG-25 客戶核准（D-054）：僅內部 S4 PoC／品質驗證；commercial_cleared 仍 False
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


PROVENANCE_FILE = "provenance.json"


def adapter_dir(models_dir: Path, spec: AdapterSpec) -> Path:
    """本機存放處：models_dir/adapters/<id>/（保留 repo 內路徑，例 models/image_encoder/…）；永不進 Git。"""
    return Path(models_dir) / "adapters" / spec.adapter_id


def read_provenance(models_dir: Path, spec: AdapterSpec) -> dict[str, Any] | None:
    p = adapter_dir(models_dir, spec) / PROVENANCE_FILE
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def validate_remote(spec: AdapterSpec, remote: dict[str, dict[str, Any]]) -> list[str]:
    """remote：path → {bytes, sha256}（HF API 固定 revision）。回傳不符清單（空＝通過）。純函式。"""
    errs = []
    for f in spec.files:
        r = remote.get(f.path)
        if r is None:
            errs.append(f"missing remote file: {f.path}")
            continue
        if r.get("bytes") != f.bytes:
            errs.append(f"size mismatch {f.path}: remote={r.get('bytes')} expected={f.bytes}")
        if f.sha256 and (r.get("sha256") or "").lower() != f.sha256:
            errs.append(f"sha256 mismatch {f.path}: remote={r.get('sha256')} expected={f.sha256}")
    return errs


def verify_local(models_dir: Path, spec: AdapterSpec) -> list[str]:
    """本機檔案逐一核對 bytes＋sha256（搬移自他機也適用：不需重新下載）。"""
    errs = []
    for f in spec.files:
        p = adapter_dir(models_dir, spec) / f.path
        if not p.exists():
            errs.append(f"missing: {p}")
        elif p.stat().st_size != f.bytes:
            errs.append(f"size mismatch {f.path}: local={p.stat().st_size} expected={f.bytes}")
        elif f.sha256 and file_sha256(p) != f.sha256:
            errs.append(f"sha256 mismatch {f.path}")
    return errs


def fetch_remote_metadata(spec: AdapterSpec) -> dict[str, dict[str, Any]]:
    """只讀 HF metadata（不下載權重）。"""
    from huggingface_hub import HfApi  # type: ignore

    info = HfApi().model_info(spec.repo, revision=spec.revision, files_metadata=True)
    out: dict[str, dict[str, Any]] = {}
    for s in info.siblings or []:
        lfs = getattr(s, "lfs", None)
        sha = getattr(lfs, "sha256", None) if lfs is not None and not isinstance(lfs, dict) else (lfs or {}).get("sha256")
        out[s.rfilename] = {"bytes": s.size, "sha256": sha}
    return out


def write_provenance(models_dir: Path, spec: AdapterSpec, remote: dict[str, dict[str, Any]]) -> dict[str, Any]:
    d = asdict(spec)
    d.update({"downloaded_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "verified": True,
              "local_files": {f.path: {"bytes": (adapter_dir(models_dir, spec) / f.path).stat().st_size,
                                       "sha256": file_sha256(adapter_dir(models_dir, spec) / f.path)} for f in spec.files},
              "remote_metadata": {f.path: remote.get(f.path) for f in spec.files}})
    (adapter_dir(models_dir, spec) / PROVENANCE_FILE).write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    return d


def is_verified(models_dir: Path, spec: AdapterSpec) -> bool:
    prov = read_provenance(models_dir, spec)
    if not prov or not prov.get("verified"):
        return False
    lf = prov.get("local_files") or {}
    return all((adapter_dir(models_dir, spec) / f.path).exists()
               and (adapter_dir(models_dir, spec) / f.path).stat().st_size == f.bytes
               and (not f.sha256 or (lf.get(f.path) or {}).get("sha256") == f.sha256) for f in spec.files)


def download_adapter(models_dir: Path, spec: AdapterSpec) -> dict[str, Any]:
    """固定 revision 逐檔下載 → 核 bytes＋sha256；任一不符即刪除該 adapter 已下載檔並 raise。"""
    from huggingface_hub import hf_hub_download  # type: ignore

    assert_usable(spec)
    remote = fetch_remote_metadata(spec)
    errs = validate_remote(spec, remote)
    if errs:
        raise ValueError("remote check failed, nothing downloaded: " + "; ".join(errs))
    dest = adapter_dir(models_dir, spec)
    dest.mkdir(parents=True, exist_ok=True)
    (Path(models_dir) / "adapters" / ".gitignore").write_text("*\n", encoding="utf-8")  # 永不進 Git
    for f in spec.files:
        hf_hub_download(repo_id=spec.repo, filename=f.path, revision=spec.revision, local_dir=str(dest))
    errs = verify_local(models_dir, spec)
    if errs:
        for f in spec.files:
            (dest / f.path).unlink(missing_ok=True)
        raise ValueError("downloaded files rejected and deleted: " + "; ".join(errs))
    return write_provenance(models_dir, spec, remote)
