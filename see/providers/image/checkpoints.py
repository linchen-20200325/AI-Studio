"""SD 1.5 單檔 checkpoint 型錄、下載器與 provenance（DG-20 裁示，D-039）。

- 型錄是**資料**（不是 Model Router）：只列客戶核准、已研究原始授權的 checkpoint。
- 只接受 `.safetensors`；下載前核對遠端檔名／大小／sha256，下載後再算 sha256，不符就刪檔。
- 每個 checkpoint 帶 `license_status` 與 `commercial_cleared`；目前全部 False，用途限「內部品質驗證」。
- 架構相容：沿用本機 SD 1.5 diffusers 資料夾當 config（`from_single_file(config=...)`，離線、不另下載）。
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from see.core.hashing import file_sha256

PROVENANCE_FILE = "provenance.json"
USAGE = "internal_quality_validation_only"


@dataclass(frozen=True)
class CheckpointSpec:
    checkpoint_id: str
    display_name: str
    version: str
    family: str  # 對應 StyleProfile.family（未來 Router 用；目前只供 style-test 明確指定）
    filename: str
    bytes: int
    sha256: str  # 官方發布處公告的 sha256（小寫）
    official_source: str
    download_repo: str  # Hugging Face repo（實際下載處）
    download_revision: str  # 固定 commit
    download_note: str
    license_status: str
    license_evidence: str
    attribution: str
    commercial_cleared: bool = False
    usage: str = USAGE
    approval: str = "DG-20（D-039）"
    # 生成參數（模型差異需要的部分；evidence 一律記錄）
    clip_skip_a1111: int = 1  # A1111「Clip skip」數值；diffusers clip_skip = 此值 − 1
    scheduler: str = "default"
    vae_baked: bool | None = None
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def diffusers_clip_skip(self) -> int | None:
        n = self.clip_skip_a1111 - 1
        return n if n > 0 else None

    def provenance_base(self) -> dict[str, Any]:
        d = asdict(self)
        d["notes"] = list(self.notes)
        return d


CHECKPOINTS: dict[str, CheckpointSpec] = {c.checkpoint_id: c for c in [
    CheckpointSpec(
        checkpoint_id="meinamix_v12", display_name="MeinaMix", version="V12 Final（Civitai modelVersionId 948574）",
        family="anime", filename="meinamix_v12Final.safetensors", bytes=2_132_651_786,
        sha256="a5e5a941a3217247dbceceee5b67f8d6b1ef2514260e08a5757436bec7035f93",
        official_source="https://civitai.com/models/7240?modelVersionId=948574",
        download_repo="xuanha31/meinamix_v12", download_revision="034320de2751631524a60cc106d4d69328e358d6",
        download_note="Civitai 官方下載需登入 API key（401）；改由 HF 鏡像下載，sha256 必須與 Civitai 官方公告值完全一致（逐位元相同檔案）",
        license_status="CreativeML Open RAIL-M + Civitai Attachment B（須署名、禁營利生成服務、禁售模型／merge）；上游 PastelMix→basil_mix 現行條款衍生物禁商用；NAI lineage 無法排除",
        license_evidence="docs/evidence/dg20/civitai_license_948574.txt；civitai_model_7240.json；hf_nuigurumi_basil_mix.License.md",
        attribution="Model: MeinaMix https://civitai.com/models/7240?modelVersionId=948574 / Creator: Meina https://civitai.com/user/Meina / License: https://civitai.com/models/license/948574",
        clip_skip_a1111=2, scheduler="dpmpp_2m_karras", vae_baked=None,
        notes=("作者建議：CFG 4–9、DPM++ 2M Karras 20–60 步、clip skip 2、landscape 768×512",)),
    CheckpointSpec(
        checkpoint_id="cyberrealistic_final", display_name="CyberRealistic", version="Final（Civitai modelVersionId 2681234）",
        family="realistic", filename="CyberRealistic_FINAL_FP16.safetensors", bytes=2_132_651_162,
        sha256="2209c07b331a06cb28cf7c830ec758ae5b49eb97fab21f5de6b18c7be8b41554",
        official_source="https://huggingface.co/cyberdelia/CyberRealistic（作者官方 HF）；https://civitai.com/models/15003?modelVersionId=2681234",
        download_repo="cyberdelia/CyberRealistic", download_revision="99827f96edd717dacb28c68560680c201c55df05",
        download_note="作者官方 HF repo；sha256 與 Civitai 公告值一致（交叉驗證）",
        license_status="CreativeML Open RAIL-M；Civitai Attachment B 無附加限制；HF 卡片要求署名（保守採署名）；merge 上游未公開（未證實）",
        license_evidence="docs/evidence/dg20/civitai_license_2681234.txt；civitai_model_15003.json；hf_cyberdelia_CyberRealistic.README.md",
        attribution="Model: CyberRealistic by Cyberdelia https://huggingface.co/cyberdelia/CyberRealistic",
        clip_skip_a1111=1, scheduler="dpmpp_2m_karras", vae_baked=True,
        notes=("作者建議：DPM++ SDE／2M Karras、30 步、CFG 5、512×768",)),
]}


def get_checkpoint(checkpoint_id: str) -> CheckpointSpec:
    if checkpoint_id not in CHECKPOINTS:
        raise ValueError(f"unknown checkpoint '{checkpoint_id}'; available: {sorted(CHECKPOINTS)}")
    return CHECKPOINTS[checkpoint_id]


def checkpoint_dir(models_dir: Path, spec: CheckpointSpec) -> Path:
    return Path(models_dir) / "checkpoints" / spec.checkpoint_id


def checkpoint_file(models_dir: Path, spec: CheckpointSpec) -> Path:
    return checkpoint_dir(models_dir, spec) / spec.filename


def read_provenance(models_dir: Path, spec: CheckpointSpec) -> dict[str, Any] | None:
    p = checkpoint_dir(models_dir, spec) / PROVENANCE_FILE
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def validate_remote(spec: CheckpointSpec, remote: dict[str, Any]) -> list[str]:
    """遠端 metadata（檔名／bytes／sha256／revision）與型錄比對；回傳不符清單（空＝通過）。純函式。"""
    errs = []
    if not spec.filename.endswith(".safetensors"):
        errs.append(f"not a safetensors file: {spec.filename}")
    if remote.get("filename") != spec.filename:
        errs.append(f"filename mismatch: remote={remote.get('filename')} expected={spec.filename}")
    if remote.get("bytes") != spec.bytes:
        errs.append(f"size mismatch: remote={remote.get('bytes')} expected={spec.bytes}")
    if (remote.get("sha256") or "").lower() != spec.sha256:
        errs.append(f"sha256 mismatch: remote={remote.get('sha256')} expected={spec.sha256}")
    if remote.get("revision") and remote.get("revision") != spec.download_revision:
        errs.append(f"revision mismatch: remote={remote.get('revision')} expected={spec.download_revision}")
    return errs


def fetch_remote_metadata(spec: CheckpointSpec) -> dict[str, Any]:
    """只讀 HF metadata（不下載權重）：固定 revision 下該檔的大小與 LFS sha256。"""
    from huggingface_hub import HfApi  # type: ignore

    info = HfApi().model_info(spec.download_repo, revision=spec.download_revision, files_metadata=True)
    for s in info.siblings or []:
        if s.rfilename == spec.filename:
            lfs = getattr(s, "lfs", None)
            sha = getattr(lfs, "sha256", None) if lfs is not None else None
            if sha is None and isinstance(lfs, dict):
                sha = lfs.get("sha256")
            return {"filename": s.rfilename, "bytes": s.size, "sha256": sha, "revision": info.sha}
    return {"filename": None, "bytes": None, "sha256": None, "revision": info.sha}


def verify_local(path: Path, spec: CheckpointSpec) -> list[str]:
    if not path.exists():
        return [f"missing: {path}"]
    errs = []
    if path.stat().st_size != spec.bytes:
        errs.append(f"size mismatch: local={path.stat().st_size} expected={spec.bytes}")
    else:
        h = file_sha256(path)
        if h != spec.sha256:
            errs.append(f"sha256 mismatch: local={h} expected={spec.sha256}")
    return errs


def write_provenance(models_dir: Path, spec: CheckpointSpec, path: Path, remote: dict[str, Any]) -> dict[str, Any]:
    prov = {**spec.provenance_base(), "downloaded_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "local_file": path.name, "local_bytes": path.stat().st_size, "local_sha256": file_sha256(path),
            "remote_metadata": remote, "verified": True}
    (checkpoint_dir(models_dir, spec) / PROVENANCE_FILE).write_text(json.dumps(prov, ensure_ascii=False, indent=2), encoding="utf-8")
    return prov


def download_checkpoint(models_dir: Path, spec: CheckpointSpec) -> dict[str, Any]:
    """下載單一 safetensors（固定 revision），核對 bytes＋sha256；不符即刪檔並 raise。"""
    from huggingface_hub import hf_hub_download  # type: ignore

    remote = fetch_remote_metadata(spec)
    errs = validate_remote(spec, remote)
    if errs:
        raise ValueError("remote check failed, nothing downloaded: " + "; ".join(errs))
    dest = checkpoint_dir(models_dir, spec)
    dest.mkdir(parents=True, exist_ok=True)
    (Path(models_dir) / "checkpoints" / ".gitignore").write_text("*\n", encoding="utf-8")  # 永不進 Git
    p = Path(hf_hub_download(repo_id=spec.download_repo, filename=spec.filename, revision=spec.download_revision,
                             local_dir=str(dest)))
    errs = verify_local(p, spec)
    if errs:
        p.unlink(missing_ok=True)
        raise ValueError("downloaded file rejected and deleted: " + "; ".join(errs))
    return write_provenance(models_dir, spec, p, remote)
