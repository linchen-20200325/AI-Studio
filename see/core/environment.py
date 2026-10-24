"""Environment Doctor／Bootstrap／Manifest／Export（D-064）：可重灌、可搬機、可換 GPU 的環境基礎。

原則（PROJECT_RULES §19）：
- **預設唯讀**：doctor、bootstrap 計畫、export 都不安裝套件、不下載模型、不改 CUDA／driver／PATH／registry、不寫永久環境變數。
  唯一的寫入是使用者明確要求時：`bootstrap --apply-safe`（只建立缺少的空 workspace 資料夾＋workspace_version.json）、
  `doctor --write-manifest`（workspace/environment_manifest.json）、`env-export`（新資料夾；不覆寫既有內容）。
- 固定狀態：OK／PARTIAL／UNAVAILABLE／ERROR。**缺少 ≠ OK**；optional 缺少是 UNAVAILABLE，不使整體失敗；
  只有 required 項目 ERROR 才使 doctor 失敗。介面存在 ≠ 能力完成（Ready／Not ready 依實際檔案與套件判定）。
- 模型以 logical model ID＋相對 `SEE_MODELS_DIR` 的路徑描述；換磁碟只要改 `SEE_MODELS_DIR`。
- 對外輸出（manifest、export）一律去識別化：家目錄 → `~`、使用者名稱 → `<user>`；不輸出 secret／token／API key。
"""
from __future__ import annotations

import getpass
import importlib.metadata
import importlib.util
import json
import os
import platform
import re
import shutil
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from see.core.config import (LOCAL_CONFIG_KEYS, Settings, local_config_path, read_local_config, repo_root as _cfg_repo_root,
                             setting_source)

MANIFEST_SCHEMA_VERSION = 1
WORKSPACE_SCHEMA_VERSION = 1
WORKSPACE_VERSION_FILE = "workspace_version.json"
MANIFEST_FILE = "environment_manifest.json"
MIN_PYTHON = (3, 11)
LOW_DISK_MB = 10 * 1024  # 低於 10 GB → PARTIAL（SD1.5＋checkpoint 約需 7 GB）


class Status(str, Enum):
    OK = "OK"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"
    ERROR = "ERROR"


@dataclass
class Check:
    group: str
    name: str
    status: Status
    required: bool
    detail: str = ""
    hint: str = ""
    data: dict[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.group}.{self.name}"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d


# ---------------------------------------------------------------- 去識別化
_SECRET_KEY = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL)", re.I)


def sanitize(obj: Any, home: str | None = None, user: str | None = None) -> Any:
    """遞迴把家目錄換成 `~`、使用者名稱換成 `<user>`（只處理字串；不改結構）。"""
    home = home if home is not None else str(Path.home())
    if user is None:
        try:
            user = getpass.getuser()
        except Exception:  # noqa: BLE001 — 某些容器沒有使用者資訊
            user = ""
    if isinstance(obj, dict):
        return {k: sanitize(v, home, user) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [sanitize(v, home, user) for v in obj]
    if isinstance(obj, str):
        s = obj
        if home and len(home) > 1:
            s = s.replace(home, "~")
        if user and len(user) >= 3:  # 太短的名稱（例 "a"）會誤傷一般字串
            s = re.sub(rf"(?<![A-Za-z0-9]){re.escape(user)}(?![A-Za-z0-9])", "<user>", s)
        return s
    return obj


# ---------------------------------------------------------------- 設定盤點（portable vs machine-specific）
PORTABLE_SETTINGS = ("SEE_LLM_PROVIDER", "SEE_IMAGE_PROVIDER", "SEE_IMAGE_MODEL_PRESET", "SEE_VIDEO_PROVIDER",
                     "SEE_TTS_PROVIDER", "SEE_TTS_DEFAULT_VOICE", "SEE_AUDIO_PROVIDER", "SEE_LIPSYNC_PROVIDER")
MACHINE_SETTINGS = ("SEE_WORKSPACE", "SEE_MODELS_DIR", "SEE_IMAGE_MODEL_PATH", "SEE_TTS_MODEL_PATH", "SEE_TTS_DEVICE",
                    "SEE_FFMPEG", "SEE_FFPROBE", "SEE_SUBTITLE_FONT")
ESSENTIAL_SETTINGS = ("SEE_MODELS_DIR", "SEE_IMAGE_PROVIDER", "SEE_TTS_PROVIDER")


def settings_snapshot(env: dict[str, str] | None = None, local: dict[str, str] | None = None) -> dict[str, Any]:
    """SEE_* 設定分兩類。值只記錄使用者實際設定的（未設定＝null，代表用程式預設）；secret 類名稱一律遮蔽。
    machine-specific 依 D-065 優先序（env → see.local.json → unset），另附來源。"""
    env = dict(os.environ if env is None else env)
    local = read_local_config()[0] if local is None else local
    machine = {k: setting_source(k, env, local) for k in MACHINE_SETTINGS}

    def val(k: str) -> str | None:
        v = env.get(k)
        if v in (None, ""):
            return None
        return "<redacted>" if _SECRET_KEY.search(k) else v

    others = sorted(k for k in env if k.startswith("SEE_") and k not in PORTABLE_SETTINGS + MACHINE_SETTINGS)
    return {
        "portable": {k: val(k) for k in PORTABLE_SETTINGS},
        "machine_specific": {k: v for k, (v, _) in machine.items()},
        "machine_specific_sources": {k: src for k, (_, src) in machine.items()},
        "other_see_vars": {k: val(k) for k in others},
        "project_level_portable": "style_id／preferences／scene preferences／characters（voice、外觀）存在各 project.json，隨 workspace 搬移",
        "ui_settings": "Web UI 目前沒有持久化設定（無 localStorage／伺服器端 UI 設定）",
    }


# ---------------------------------------------------------------- 個別檢查
CORE_PACKAGES = {"pydantic": "pydantic", "PIL": "pillow", "numpy": "numpy", "fastapi": "fastapi", "uvicorn": "uvicorn"}
OPTIONAL_PACKAGES = {"torch": "torch", "diffusers": "diffusers", "transformers": "transformers", "accelerate": "accelerate",
                     "safetensors": "safetensors", "huggingface_hub": "huggingface_hub", "kokoro": "kokoro", "misaki": "misaki",
                     "psutil": "psutil", "httpx": "httpx", "pytest": "pytest", "edge_tts": "edge-tts"}


def _pkg_version(module: str, dist: str) -> tuple[bool, str]:
    if importlib.util.find_spec(module) is None:
        return False, ""
    try:
        return True, importlib.metadata.version(dist)
    except importlib.metadata.PackageNotFoundError:
        return True, "unknown"


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _git(*args: str) -> str | None:
    git = shutil.which("git")
    if not git:
        return None
    from see.core.proc import run_text

    try:
        p = run_text([git, "-C", str(repo_root()), *args], timeout=15)
    except Exception:  # noqa: BLE001
        return None
    return p.stdout.strip() if p.returncode == 0 else None


def _disk_free_mb(path: Path) -> int | None:
    p = Path(path)
    while not p.exists() and p != p.parent:  # 尚未建立的資料夾 → 量最近的既有上層
        p = p.parent
    try:
        return int(shutil.disk_usage(p).free / 2**20)
    except OSError:
        return None


def _tool_version(exe: str | None, flag: str = "-version") -> str:
    if not exe:
        return ""
    from see.core.proc import run_text

    try:
        p = run_text([exe, flag], timeout=15)
    except Exception:  # noqa: BLE001
        return ""
    return (p.stdout or p.stderr).strip().splitlines()[0] if p.returncode == 0 and (p.stdout or p.stderr) else ""


def check_system(settings: Settings) -> list[Check]:
    out = []
    py_ok = sys.version_info[:2] >= MIN_PYTHON
    out.append(Check("system", "os", Status.OK, True, f"{platform.system()} {platform.release()} {platform.machine()}"))
    out.append(Check("system", "python", Status.OK if py_ok else Status.ERROR, True, platform.python_version(),
                     "" if py_ok else f"需要 Python ≥ {MIN_PYTHON[0]}.{MIN_PYTHON[1]}（建議 3.11／3.12：PyTorch wheel 最齊）"))
    commit = _git("rev-parse", "HEAD")
    out.append(Check("system", "repo", Status.OK if commit else Status.PARTIAL, True, str(repo_root()),
                     "" if commit else "不是 git clone 或沒有 git：無法記錄 commit（GitHub Alone Recovery 需要 git clone）",
                     {"commit": commit, "branch": _git("rev-parse", "--abbrev-ref", "HEAD")}))
    ws = settings.workspace
    out.append(Check("system", "workspace", Status.OK if ws.is_dir() else Status.UNAVAILABLE, True, str(ws),
                     "" if ws.is_dir() else "workspace 尚未建立：`python -m see.app.cli bootstrap --apply-safe` 可安全建立空資料夾"))
    free = _disk_free_mb(ws)
    st = Status.UNAVAILABLE if free is None else Status.PARTIAL if free < LOW_DISK_MB else Status.OK
    out.append(Check("system", "disk_free", st, False, f"{free} MB @ workspace" if free is not None else "無法取得",
                     "可用空間 < 10 GB：SD1.5＋checkpoint 約需 7 GB" if st == Status.PARTIAL else "", {"free_mb": free}))
    return out


def check_python() -> list[Check]:
    out = []
    in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix) or bool(os.environ.get("VIRTUAL_ENV") or os.environ.get("CONDA_PREFIX"))
    out.append(Check("python", "venv", Status.OK if in_venv else Status.PARTIAL, False,
                     "virtual environment" if in_venv else "未使用 venv（系統 Python）",
                     "" if in_venv else "建議：python -m venv .venv 後再安裝（避免污染系統 Python）"))
    out.append(Check("python", "executable", Status.OK, True, sys.executable))
    for mod, dist in CORE_PACKAGES.items():
        ok, ver = _pkg_version(mod, dist)
        out.append(Check("python", dist, Status.OK if ok else Status.ERROR, True, ver or "not installed",
                         "" if ok else "pip install -r requirements.txt", {"version": ver or None}))
    for mod, dist in OPTIONAL_PACKAGES.items():
        ok, ver = _pkg_version(mod, dist)
        out.append(Check("python", dist, Status.OK if ok else Status.UNAVAILABLE, False, ver or "not installed",
                         data={"version": ver or None}))
    return out


def gpu_info() -> dict[str, Any]:
    """torch 可用時回報 CUDA／GPU／VRAM／dtype 能力；不可用 → available=False（不是錯誤）。"""
    info: dict[str, Any] = {"torch": None, "cuda_available": False, "cuda_build": None, "cudnn": None, "devices": [],
                            "source": "torch"}
    if importlib.util.find_spec("torch") is None:
        info["source"] = "torch not installed"
    else:
        try:
            import torch  # type: ignore

            info["torch"] = str(torch.__version__)
            info["cuda_build"] = getattr(torch.version, "cuda", None)
            info["cuda_available"] = bool(torch.cuda.is_available())
            if info["cuda_available"]:
                info["cudnn"] = torch.backends.cudnn.version()
                for i in range(torch.cuda.device_count()):
                    pr = torch.cuda.get_device_properties(i)
                    cc = (pr.major, pr.minor)
                    info["devices"].append({
                        "index": i, "name": pr.name, "vram_mb": int(pr.total_memory / 2**20), "compute_capability": f"{cc[0]}.{cc[1]}",
                        # fp16 運算需 cc ≥ 5.3；bf16 硬體支援需 Ampere（cc ≥ 8.0）
                        "fp16": cc >= (5, 3), "bf16": cc >= (8, 0)})
        except Exception as e:  # noqa: BLE001 — torch 損壞不應讓 doctor 崩潰
            info["error"] = f"{type(e).__name__}: {e}"
    if not info["devices"]:  # 沒有 torch CUDA 時，用既有硬體偵測（nvidia-smi 等）補 GPU 名稱／VRAM（純資訊）
        try:
            from see.core.hardware import _gpus_nvidia

            smi = _gpus_nvidia()
        except Exception:  # noqa: BLE001
            smi = []
        info["system_gpus"] = [{"name": g.name, "vram_mb": g.vram_total_mb, "driver": g.driver, "source": g.source} for g in smi]
    return info


def check_gpu(info: dict[str, Any]) -> list[Check]:
    if info.get("error"):
        return [Check("gpu", "cuda", Status.ERROR, False, info["error"], "torch 安裝可能損壞；重新安裝前先確認 CUDA wheel 版本（需裁示）", info)]
    if not info["cuda_available"]:
        why = "torch 未安裝" if not info["torch"] else f"torch {info['torch']} 無可用 CUDA（CPU-only build 或沒有 NVIDIA GPU／driver）"
        return [Check("gpu", "cuda", Status.UNAVAILABLE, False, why, "CPU-only 仍可跑 Web UI／TTS／預覽影片；SD1.5 生圖需 CUDA torch（Tier C）", info)]
    d = info["devices"][0]
    return [Check("gpu", "cuda", Status.OK, False,
                  f"{d['name']} · VRAM {d['vram_mb']} MB · torch {info['torch']} · CUDA {info['cuda_build']} · cc {d['compute_capability']}"
                  f" · fp16={'yes' if d['fp16'] else 'no'} bf16={'yes' if d['bf16'] else 'no'}", data=info)]


def check_config(env: dict[str, str] | None = None) -> list[Check]:
    """D-065：專案本機設定檔狀態＋每個 machine-specific 設定的實際值與來源（env／local_config／unset）。"""
    env = dict(os.environ if env is None else env)
    p = local_config_path()
    local, err = read_local_config(p)
    shown = p.name if p.resolve().parent == _cfg_repo_root() else str(p)
    if err:
        out = [Check("config", "local_config", Status.ERROR, False, f"{shown} 格式錯誤，整份未採用：{err}",
                     "修正或刪除後重建（python -m see.app.cli config set …）；只允許 machine-specific key", {"path": shown})]
    elif p.is_file():
        out = [Check("config", "local_config", Status.OK, False, f"{shown}（{len(local)} 項）", data={"path": shown})]
    else:
        out = [Check("config", "local_config", Status.UNAVAILABLE, False, f"{shown} 不存在（選用）",
                     'python -m see.app.cli config set models_dir "E:\\AI\\models"', {"path": shown})]
    for key, env_name in LOCAL_CONFIG_KEYS.items():
        v, src = setting_source(env_name, env, local)
        out.append(Check("config", key, Status.OK if v else Status.UNAVAILABLE, False,
                         f"{v}（來源：{src}）" if v else "（來源：unset → 程式預設）", data={"env": env_name, "source": src, "value": v}))
    return out


def check_tools(settings: Settings) -> list[Check]:
    out = []
    for name, exe, required, hint in (
        ("ffmpeg", settings.ffmpeg, True, "Windows：winget install Gyan.FFmpeg（需使用者操作）；Linux：apt install ffmpeg"),
        ("ffprobe", settings.ffprobe, True, "隨 ffmpeg 安裝"),
        ("git", "git", True, "Windows：winget install Git.Git（需使用者操作）"),
        ("espeak-ng", "espeak-ng", False, "選用：Kokoro 不可用時的 TTS fallback"),
    ):
        path = shutil.which(exe)
        ver = _tool_version(path, "--version" if name in ("git", "espeak-ng") else "-version")
        st = Status.OK if path else (Status.ERROR if required else Status.UNAVAILABLE)
        out.append(Check("tools", name, st, required, ver or (path or "not installed"), "" if path else hint, {"path": path}))
    font = settings.subtitle_font
    out.append(Check("tools", "cjk_font", Status.OK if font else Status.UNAVAILABLE, False, font or "未偵測到中文字型",
                     "" if font else "字幕中文可能顯示為方框：安裝 Noto Sans CJK 或設定 SEE_SUBTITLE_FONT"))
    return out


# ---------------------------------------------------------------- 模型（logical ID ＋ 相對 SEE_MODELS_DIR）
def _rel(path: Path, root: Path) -> tuple[str, bool]:
    """回傳 (路徑表示, 是否在 SEE_MODELS_DIR 之下)。在之下 → 相對路徑；否則 → 外部路徑（只在本機有意義）。"""
    try:
        return Path(path).resolve().relative_to(root.resolve()).as_posix(), True
    except ValueError:
        return str(path), False


def model_inventory(settings: Settings, hash_files: bool = False) -> list[dict[str, Any]]:
    """已知模型的存在／provenance 檢查（只看檔案；不下載、不載入）。hash_files=True 才重算 sha256（大檔很慢）。"""
    from see.core.hashing import file_sha256
    from see.providers.image import adapters as ad
    from see.providers.image import checkpoints as ck
    from see.providers.image.diffusers_local import WEIGHT_COMPONENTS, local_weight_variants
    from see.providers.tts import kokoro as kk

    root = settings.models_dir
    items: list[dict[str, Any]] = []

    def add(model_id: str, kind: str, path: Path, status: Status, detail: str, **extra: Any) -> None:
        rel, inside = _rel(path, root)
        items.append({"model_id": model_id, "kind": kind, "root": "SEE_MODELS_DIR" if inside else "external",
                      "rel_path": rel if inside else None, "status": status.value, "detail": detail, **extra})

    # SD1.5 base（diffusers 資料夾）
    sd = Path(settings.image_model_path) if settings.image_model_path else root / "sd15"
    if (sd / "model_index.json").is_file():
        var = local_weight_variants(sd)
        missing = [c for c in WEIGHT_COMPONENTS if not var.get(c)]
        add("sd15_base", "image_base", sd, Status.PARTIAL if missing else Status.OK,
            f"元件缺權重 {missing}" if missing else "model_index＋unet／vae／text_encoder 權重存在（無 provenance：HF snapshot）",
            variants={k: sorted(map(str, v)) for k, v in var.items()}, provenance=None)
    else:
        add("sd15_base", "image_base", sd, Status.UNAVAILABLE, "未找到 model_index.json", provenance=None)

    # Kokoro TTS
    kd = Path(settings.tts_model_path) if settings.tts_model_path else root / kk.KokoroTTSProvider.DEFAULT_DIRNAME
    prov = kd / kk.PROVENANCE_FILE
    if kk.weights_present(kd):
        add("kokoro_v1_1_zh", "tts", kd, Status.OK if prov.is_file() else Status.PARTIAL,
            "權重＋voices 存在" + ("" if prov.is_file() else "；缺 provenance.json"), voices=kk.local_voices(kd),
            provenance=prov.is_file())
    else:
        add("kokoro_v1_1_zh", "tts", kd, Status.UNAVAILABLE, "權重或 voices 不完整", provenance=prov.is_file())

    # 單檔 checkpoint（CyberRealistic、MeinaMix…）
    for spec in ck.CHECKPOINTS.values():
        f = ck.checkpoint_file(root, spec)
        p = ck.read_provenance(root, spec)
        if not f.is_file():
            add(spec.checkpoint_id, "image_checkpoint", f, Status.UNAVAILABLE, "檔案不存在", expected_sha256=spec.sha256, provenance=p is not None)
            continue
        size_ok = f.stat().st_size == spec.bytes
        prov_ok = bool(p) and (p.get("local_sha256") or "").lower() == spec.sha256  # 只認本機實算值（provenance 另含型錄公告值）
        sha = file_sha256(f) if hash_files else None
        hash_ok = None if sha is None else sha == spec.sha256
        ok = size_ok and (hash_ok if hash_ok is not None else prov_ok)
        add(spec.checkpoint_id, "image_checkpoint", f, Status.OK if ok else (Status.ERROR if hash_ok is False or not size_ok else Status.PARTIAL),
            "大小＋" + ("sha256 重算一致" if hash_ok else "provenance sha256 一致" if prov_ok else "缺 provenance（可用 --hash 重算）")
            if ok or (size_ok and hash_ok is None) else ("sha256 不符" if hash_ok is False else "大小不符"),
            bytes=f.stat().st_size, expected_sha256=spec.sha256, sha256_verified=hash_ok, provenance=p is not None,
            provenance_sha256=(p or {}).get("local_sha256"),
            commercial_cleared=spec.commercial_cleared)

    # Identity adapter（IP-Adapter＋image encoder；D-061：identity 路線 HARDWARE_UPGRADE_BLOCKED，只做存在檢查）
    for spec in ad.ADAPTERS.values():
        d = ad.adapter_dir(root, spec)
        present = [f.path for f in spec.files if (d / f.path).is_file()]
        if not present:
            add(spec.adapter_id, "identity_adapter", d, Status.UNAVAILABLE, "未下載", provenance=False)
            continue
        errs = ad.verify_local(root, spec) if hash_files else []
        verified = ad.is_verified(root, spec)
        st = Status.OK if verified and not errs else Status.ERROR if errs else Status.PARTIAL
        add(spec.adapter_id, "identity_adapter", d, st,
            "檔案＋provenance 一致" if st == Status.OK else "; ".join(errs) if errs else f"不完整：{len(present)}/{len(spec.files)} 檔或缺 provenance",
            provenance=ad.read_provenance(root, spec) is not None)
    return items


def check_models(settings: Settings, models: list[dict[str, Any]], env: dict[str, str] | None = None) -> list[Check]:
    env = dict(os.environ if env is None else env)
    root = settings.models_dir
    out = []
    _, source = setting_source("SEE_MODELS_DIR", env)
    configured = source != "unset"
    if not configured:
        out.append(Check("models", "models_dir", Status.UNAVAILABLE, False, f"模型目錄未設定（來源：unset；目前使用預設 {root}）",
                         'python -m see.app.cli config set models_dir "E:\\AI\\models"（寫入專案本機設定檔 see.local.json；不改系統）',
                         {"source": source}))
    elif not root.is_dir():
        out.append(Check("models", "models_dir", Status.ERROR, False, f"{root} 不存在（來源：{source}）",
                         "確認磁碟代號／路徑；搬機後只需改 models_dir（config set）或 SEE_MODELS_DIR", {"source": source}))
    elif not os.access(root, os.R_OK):
        out.append(Check("models", "models_dir", Status.ERROR, False, f"{root} 無讀取權限"))
    else:
        free = _disk_free_mb(root)
        sub = sorted(p.name for p in root.iterdir() if p.is_dir())
        out.append(Check("models", "models_dir", Status.OK, False, f"{root}（來源：{source}）· free {free} MB · 子目錄 {sub}",
                         "" if (root / "checkpoints").is_dir() else "尚無 checkpoints/ 子目錄（只用 base SD1.5 時可忽略）",
                         {"free_mb": free, "subdirs": sub, "source": source}))
    for m in models:
        out.append(Check("models", m["model_id"], Status(m["status"]), False, m["detail"], data=m))
    return out


# ---------------------------------------------------------------- Workspace
WORKSPACE_DIRS = {
    "projects": "專案（project.json、scenes、renders）",
    "reference_library": "Reference Library（私人圖片＋.ref.json；不進 Git）",
    "character_library": "Character Store（角色定義 JSON）",
    "style_tests": "style-test evidence（圖片＋json）",
    "compositions": "compose-scene 產出",
    "voice_previews": "試聽音檔",
    "exports": "env-export 輸出",
}
LEGACY_DIRS = {"identity_refs": "legacy reference（唯讀相容）"}


def read_workspace_version(workspace: Path) -> tuple[int | None, str]:
    """(版本, 來源)。沒有版本檔 → 視為 legacy v1（舊 workspace 相容）；未來版本 → 由呼叫端 fail safe。"""
    f = Path(workspace) / WORKSPACE_VERSION_FILE
    if not f.is_file():
        return (WORKSPACE_SCHEMA_VERSION if Path(workspace).is_dir() else None), "implicit (legacy, no version file)"
    try:
        v = int(json.loads(f.read_text(encoding="utf-8"))["workspace_schema_version"])
    except (ValueError, KeyError, TypeError) as e:
        raise ValueError(f"unreadable {WORKSPACE_VERSION_FILE}: {e}") from e
    return v, "file"


def check_workspace(settings: Settings) -> list[Check]:
    from see.core.reference_library import ReferenceLibrary, ReferenceLibraryError
    from see.storage.character_store import CharacterStore, CharacterStoreError
    from see.storage.project_store import ProjectStore

    ws = settings.workspace
    out = []
    try:
        ver, src = read_workspace_version(ws)
        if ver is not None and ver > WORKSPACE_SCHEMA_VERSION:
            out.append(Check("workspace", "schema_version", Status.ERROR, True, f"workspace v{ver} 比程式支援的 v{WORKSPACE_SCHEMA_VERSION} 新",
                             "請更新程式（git pull）；不要用舊程式寫入新版 workspace"))
        else:
            out.append(Check("workspace", "schema_version", Status.OK if ver else Status.UNAVAILABLE, True,
                             f"v{ver}（{src}）" if ver else "workspace 不存在", data={"version": ver, "source": src}))
    except ValueError as e:
        out.append(Check("workspace", "schema_version", Status.ERROR, True, str(e)))
    for name, desc in {**WORKSPACE_DIRS, **LEGACY_DIRS}.items():
        d = ws / name
        legacy = name in LEGACY_DIRS
        if not d.is_dir():
            out.append(Check("workspace", name, Status.UNAVAILABLE, False, f"{desc}：尚未建立",
                             "" if legacy else "可用 bootstrap --apply-safe 建立空資料夾"))
            continue
        out.append(Check("workspace", name, Status.OK, False, f"{desc}：{sum(1 for _ in d.iterdir())} 項", data={"legacy": legacy}))
    # 內容可載入性（只讀）
    store = ProjectStore(ws)
    bad = []
    for pid in store.list_projects():
        try:
            store.load(pid)
        except Exception as e:  # noqa: BLE001
            bad.append(f"{pid}: {type(e).__name__}")
    n = len(store.list_projects())
    if n:
        out.append(Check("workspace", "projects_loadable", Status.OK if not bad else Status.PARTIAL, False,
                         f"{n - len(bad)}/{n} 個 project.json 可載入", "; ".join(bad[:5]), {"failed": bad}))
    try:
        entries = ReferenceLibrary(ws).list()
        probs = [e.rel_path for e in entries if e.problems]
        if entries:
            out.append(Check("workspace", "reference_metadata", Status.OK if not probs else Status.PARTIAL, False,
                             f"{len(entries)} 張圖、{sum(1 for e in entries if e.asset)} 份 metadata、{len(probs)} 筆不一致",
                             "用 `ref list` 查看不一致項目（sha256／類別／檔名）" if probs else "", {"problems": probs}))
    except ReferenceLibraryError as e:
        out.append(Check("workspace", "reference_metadata", Status.ERROR, False, str(e)))
    try:
        cs = CharacterStore(ws)
        recs = cs.list(include_archived=True)
        if recs:
            # D-067：逐一驗證不可變 revision history（hash 不符 → ERROR，不自動修復）；沒有 history 的 legacy 角色照實標示
            hist_problems = [p for r in recs for p in cs.verify_history(r.definition.character_id)]
            no_hist = [r.definition.character_id for r in recs if not cs.has_history(r.definition.character_id)]
            st = Status.ERROR if hist_problems else Status.PARTIAL if no_hist else Status.OK
            out.append(Check("workspace", "character_store", st, False,
                             f"{len(recs)} 個角色（封存 {sum(r.archived for r in recs)}；尚無 revision history {len(no_hist)}）",
                             "; ".join(hist_problems[:3]) if hist_problems else
                             ("legacy 角色下次修改時會自動建立 baseline revision（不補造更早歷史）" if no_hist else ""),
                             {"history_problems": hist_problems, "no_history": no_hist}))
    except (CharacterStoreError, ValueError) as e:
        out.append(Check("workspace", "character_store", Status.ERROR, False, str(e), "不要用舊程式改寫；先更新程式並備份"))
    return out


# ---------------------------------------------------------------- 能力判定（Ready / Not ready）
BLOCKED = {
    "identity_lora": "Identity／Character LoRA：HARDWARE_UPGRADE_BLOCKED（D-061；重開依 ARCHITECTURE §18 Resume Gate）",
    "identity_advanced": "Identity Preservation（FaceID／InsightFace 等）：HARDWARE_UPGRADE_BLOCKED（D-061）",
    "sdxl_flux": "SDXL／Flux：未核准下載（需 Decision Gate；硬體需求依 ARCHITECTURE §18 Resume Gate 重評）",
    "image_to_video": "真 image-to-video：沒有已實作的模型（目前只有 Ken Burns 鏡頭運動）",
    "lipsync_model": "真 lip-sync：沒有已實作的模型（provider 介面存在、預設 null）",
}


def readiness(checks: list[Check]) -> dict[str, Any]:
    st = {c.key: c.status for c in checks}

    def ok(*keys: str) -> bool:
        return all(st.get(k) == Status.OK for k in keys)

    ready: dict[str, str] = {}
    not_ready: dict[str, str] = {}

    def put(name: str, cond: bool, yes: str, no: str) -> None:
        (ready if cond else not_ready)[name] = yes if cond else no

    core = ok("python.pydantic", "python.pillow", "python.numpy")
    put("web_ui", core and ok("python.fastapi", "python.uvicorn"), "FastAPI＋uvicorn 已安裝", "缺 fastapi／uvicorn")
    put("preview_render", core and ok("tools.ffmpeg", "tools.ffprobe"), "ffmpeg＋ffprobe 可用", "缺 ffmpeg／ffprobe")
    put("procedural_audio", core and ok("tools.ffmpeg"), "程序生成 BGM／SFX（預設仍為 null，DG-17）", "缺 ffmpeg")
    kokoro = ok("python.kokoro", "python.misaki", "python.torch", "models.kokoro_v1_1_zh")
    put("tts_kokoro", kokoro, "Kokoro 套件＋權重存在（裝置預設 CPU）",
        "Kokoro 未就緒（需 kokoro／misaki／torch 套件＋models/kokoro-v1_1-zh）；仍可用 espeak-ng 或 silent fallback")
    put("tts_fallback", ok("tools.espeak-ng"), "espeak-ng 可用", "espeak-ng 未安裝（選用；最後退回 silent）")
    sd_keys = ("python.torch", "python.diffusers", "python.transformers", "models.sd15_base")
    sd_soft = ok(*sd_keys)
    cuda = ok("gpu.cuda")
    sd_missing = [k.split(".", 1)[1] for k in (*sd_keys, "gpu.cuda") if st.get(k) != Status.OK]
    put("sd15_image", sd_soft and cuda, "SD1.5 權重＋CUDA torch＋diffusers",
        "SD1.5 生圖未就緒：缺 " + "、".join(sd_missing) + ("（只缺 CUDA：CPU 可跑但每張數分鐘，僅診斷用）" if sd_soft else ""))
    for cid in ("cyberrealistic_final", "meinamix_v12"):
        put(f"checkpoint_{cid}", sd_soft and cuda and ok(f"models.{cid}"), f"{cid} 檔案＋sha 驗證一致",
            f"{cid} 未就緒（需 SD1.5 就緒＋checkpoint 檔與 provenance）")
    not_ready.update(BLOCKED)
    return {"ready": ready, "not_ready": not_ready}


def tiers(checks: list[Check], ready: dict[str, Any]) -> dict[str, dict[str, Any]]:
    st = {c.key: c.status for c in checks}
    r = ready["ready"]

    def tier(items: list[str], blockers: list[str]) -> dict[str, Any]:
        missing = [i for i in items if st.get(i) != Status.OK]
        return {"status": (Status.OK if not missing else Status.PARTIAL if len(missing) < len(items) else Status.UNAVAILABLE).value,
                "missing": missing + blockers}

    a = tier(["system.python", "system.repo", "tools.git", "python.pydantic", "python.pillow", "python.numpy", "python.fastapi",
              "python.uvicorn", "tools.ffmpeg", "tools.ffprobe"], [])
    if st.get("python.venv") != Status.OK:
        a["missing"].append("python.venv（建議）")
    b_missing = [k for k in ("web_ui", "preview_render", "procedural_audio") if k not in r]
    b = {"status": (Status.OK if not b_missing and "tts_kokoro" in r else Status.PARTIAL if not b_missing else Status.UNAVAILABLE).value,
         "missing": b_missing + ([] if "tts_kokoro" in r else ["tts_kokoro（目前會用 fallback TTS）"])}
    c = tier(["gpu.cuda", "python.torch", "python.diffusers", "python.transformers", "models.sd15_base"], [])
    c["optional_checkpoints"] = {k: k in r for k in ("checkpoint_cyberrealistic_final", "checkpoint_meinamix_v12")}
    d = {"status": "BLOCKED", "missing": list(BLOCKED.values())}
    return {"A_base": a, "B_cpu": b, "C_gpu_image": c, "D_future_blocked": d}


# ---------------------------------------------------------------- 主入口
@dataclass
class DoctorReport:
    checks: list[Check]
    gpu: dict[str, Any]
    models: list[dict[str, Any]]
    readiness: dict[str, Any]
    tiers: dict[str, Any]
    settings: dict[str, Any]

    @property
    def failed_required(self) -> list[str]:
        return [c.key for c in self.checks if c.required and c.status == Status.ERROR]

    def to_dict(self) -> dict[str, Any]:
        return {"checks": [c.to_dict() for c in self.checks], "gpu": self.gpu, "models": self.models,
                "readiness": self.readiness, "tiers": self.tiers, "settings": self.settings,
                "failed_required": self.failed_required}


def run_doctor(settings: Settings | None = None, hash_files: bool = False, env: dict[str, str] | None = None) -> DoctorReport:
    settings = settings or Settings()
    gpu = gpu_info()
    models = model_inventory(settings, hash_files=hash_files)
    checks = [*check_system(settings), *check_config(env), *check_python(), *check_gpu(gpu), *check_tools(settings),
              *check_models(settings, models, env), *check_workspace(settings)]
    rd = readiness(checks)
    return DoctorReport(checks, gpu, models, rd, tiers(checks, rd), settings_snapshot(env))


# ---------------------------------------------------------------- Environment Manifest（machine-local）
def build_manifest(report: DoctorReport, settings: Settings) -> dict[str, Any]:
    st = {c.key: c for c in report.checks}
    dev = (report.gpu.get("devices") or [None])[0]
    ws_ver = st.get("workspace.schema_version")
    m = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "os": {"system": platform.system(), "release": platform.release(), "machine": platform.machine()},
        "python": {"version": platform.python_version(), "in_venv": st["python.venv"].status == Status.OK},
        "torch": report.gpu.get("torch"),
        "cuda": {"available": report.gpu.get("cuda_available"), "build": report.gpu.get("cuda_build"), "cudnn": report.gpu.get("cudnn")},
        "gpu": {"name": dev["name"], "vram_mb": dev["vram_mb"], "compute_capability": dev["compute_capability"]} if dev else None,
        "ffmpeg": st["tools.ffmpeg"].detail if st["tools.ffmpeg"].status == Status.OK else None,
        "repo": {"commit": st["system.repo"].data.get("commit"), "branch": st["system.repo"].data.get("branch")},
        "models_dir": {"variable": "SEE_MODELS_DIR", "configured": bool(report.settings["machine_specific"].get("SEE_MODELS_DIR")),
                       "source": report.settings["machine_specific_sources"].get("SEE_MODELS_DIR"),
                       "local_path": str(settings.models_dir)},
        "models": [{k: m.get(k) for k in ("model_id", "kind", "root", "rel_path", "status", "expected_sha256", "bytes")}
                   for m in report.models],
        "detected_model_ids": [m["model_id"] for m in report.models if m["status"] == Status.OK.value],
        "workspace_version": (ws_ver.data.get("version") if ws_ver else None),
        "readiness": report.readiness,
        "settings": report.settings,
    }
    return sanitize(m)


def load_manifest(path: Path) -> dict[str, Any]:
    """讀 manifest；未來版本 → ValueError（fail safe，不猜欄位意義）。"""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    v = data.get("schema_version")
    if not isinstance(v, int) or v > MANIFEST_SCHEMA_VERSION:
        raise ValueError(f"unsupported environment manifest schema_version {v!r} (supported ≤ {MANIFEST_SCHEMA_VERSION})")
    return data


def write_manifest(report: DoctorReport, settings: Settings) -> Path:
    settings.workspace.mkdir(parents=True, exist_ok=True)
    p = settings.workspace / MANIFEST_FILE
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(build_manifest(report, settings), ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)  # 本檔是可重產的機器快照（非使用者內容），覆寫安全
    return p


# ---------------------------------------------------------------- Bootstrap plan（預設唯讀）
def bootstrap_plan(report: DoctorReport, settings: Settings) -> dict[str, list[dict[str, str]]]:
    st = {c.key: c for c in report.checks}
    auto, user, approval = [], [], []
    missing_ws = [n for n in WORKSPACE_DIRS if st.get(f"workspace.{n}") and st[f"workspace.{n}"].status != Status.OK]
    if not settings.workspace.is_dir() or missing_ws:
        auto.append({"item": "建立缺少的 workspace 空資料夾", "detail": ", ".join(missing_ws) or "workspace/",
                     "command": "python -m see.app.cli bootstrap --apply-safe"})
    if not (settings.workspace / WORKSPACE_VERSION_FILE).is_file():
        auto.append({"item": f"寫入 {WORKSPACE_VERSION_FILE}（v{WORKSPACE_SCHEMA_VERSION}）", "detail": "舊 workspace 視為 v1；不改動既有檔案",
                     "command": "python -m see.app.cli bootstrap --apply-safe"})
    if st["python.venv"].status != Status.OK:
        user.append({"item": "建立並啟用 venv", "detail": "Windows：python -m venv .venv ；.venv\\Scripts\\activate", "command": "python -m venv .venv"})
    if any(st[f"python.{d}"].status != Status.OK for d in CORE_PACKAGES.values()):
        user.append({"item": "安裝專案基礎依賴", "detail": "只裝 requirements.txt（小型套件）", "command": "pip install -r requirements.txt"})
    for t in ("ffmpeg", "ffprobe", "git"):
        if st[f"tools.{t}"].status != Status.OK:
            user.append({"item": f"安裝 {t}", "detail": st[f"tools.{t}"].hint, "command": ""})
    if st["models.models_dir"].status != Status.OK:
        user.append({"item": "設定模型目錄（寫入專案本機設定檔；D-065）", "detail": "優先序：環境變數 > see.local.json > 預設",
                     "command": 'python -m see.app.cli config set models_dir "E:\\AI\\models"'})
    missing_models = {m["model_id"] for m in report.models if m["status"] != Status.OK.value}
    if missing_models:
        user.append({"item": "放回模型（從舊機／備份複製到 SEE_MODELS_DIR）", "detail": ", ".join(sorted(missing_models)),
                     "command": "複製後執行 python -m see.app.cli doctor --hash 驗證"})
    if st["gpu.cuda"].status != Status.OK:
        approval.append({"item": "安裝 CUDA 版 torch（大型依賴；需裁示版本）", "detail": "依 GPU／driver 選 wheel；不自動安裝",
                         "command": "見 docs/ENVIRONMENT_SETUP.md Tier C"})
    if {"sd15_base", "kokoro_v1_1_zh", "cyberrealistic_final", "meinamix_v12"} & missing_models:
        approval.append({"item": "下載模型（僅限既有核准項目；需 --yes）", "detail": "若無法從舊機搬移才下載",
                         "command": "image-download --preset sd15 --yes ／ tts-download --yes ／ checkpoint-download <id> --yes"})
    blocked = [{"item": k, "detail": v, "command": ""} for k, v in BLOCKED.items()]
    return {"auto_safe": auto, "user_action": user, "needs_approval": approval, "blocked": blocked}


def apply_safe(settings: Settings) -> list[str]:
    """只建立缺少的空資料夾與版本檔；**不刪除、不搬移、不覆寫**任何既有內容。"""
    done = []
    ws = settings.workspace
    from see.models.character_definition import RefCategory

    for name in [*WORKSPACE_DIRS, *(f"reference_library/{c.value}" for c in RefCategory)]:
        d = ws / name
        if not d.exists():
            d.mkdir(parents=True)
            done.append(f"mkdir {name}/")
    f = ws / WORKSPACE_VERSION_FILE
    if not f.exists():
        f.write_text(json.dumps({"workspace_schema_version": WORKSPACE_SCHEMA_VERSION,
                                 "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}, indent=2), encoding="utf-8")
        done.append(f"write {WORKSPACE_VERSION_FILE}")
    return done


# ---------------------------------------------------------------- Export（可恢復資訊；不含模型與私人圖片）
def python_packages() -> list[str]:
    seen = {}
    for d in importlib.metadata.distributions():
        name = d.metadata.get("Name")
        if name:
            seen[name.lower()] = f"{name}=={d.version}"
    return [seen[k] for k in sorted(seen)]


def workspace_inventory(settings: Settings) -> dict[str, Any]:
    from see.core.reference_library import ReferenceLibrary
    from see.storage.character_store import CharacterStore
    from see.storage.project_store import ProjectStore

    ws = settings.workspace
    store = ProjectStore(ws)
    projects = []
    for pid in store.list_projects():
        try:
            p = store.load(pid)
            projects.append({"project_id": pid, "title": p.title, "status": str(p.status.value if hasattr(p.status, "value") else p.status),
                             "scenes": len(p.scenes), "style_id": p.style_id, "has_preferences": p.preferences is not None,
                             "characters": sorted(p.characters)})
        except Exception as e:  # noqa: BLE001
            projects.append({"project_id": pid, "error": type(e).__name__})
    refs = []
    for e in ReferenceLibrary(ws).list():
        a = e.asset.model_dump(mode="json") if e.asset else None
        if a:
            a["file_path"] = e.rel_path  # 不輸出本機絕對路徑；搬移後以 <category>/<file>＋sha256 重新解析
        refs.append({"rel_path": e.rel_path, "legacy": e.legacy, "problems": list(e.problems), "asset": a})
    cs = CharacterStore(ws)
    chars = [{**r.model_dump(mode="json"), "history_revisions": cs.list_revisions(r.definition.character_id)}
             for r in cs.list(include_archived=True)]
    ver, src = read_workspace_version(ws)
    return {"workspace_schema_version": ver, "workspace_version_source": src, "projects": projects,
            "reference_library": refs, "character_store": chars,
            "note": "私人 reference 圖片與專案媒體不在此匯出；請使用者自行備份 workspace/（見 docs/MIGRATION_REINSTALL.md）"}


def export_environment(settings: Settings, out_dir: Path | None = None, hash_files: bool = False) -> Path:
    report = run_doctor(settings, hash_files=hash_files)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = Path(out_dir) if out_dir else settings.workspace / "exports" / f"env-{stamp}"
    if out.exists() and any(out.iterdir()):
        raise FileExistsError(f"export target is not empty (refusing to overwrite): {out}")
    out.mkdir(parents=True, exist_ok=True)
    manifest = build_manifest(report, settings)
    manifest["models_dir"].pop("local_path", None)  # export 不帶本機路徑
    files = {
        MANIFEST_FILE: manifest,
        "models_manifest.json": sanitize([{k: v for k, v in m.items() if k not in ("detail",)} for m in report.models]),
        "workspace_inventory.json": sanitize(workspace_inventory(settings)),
        "settings.json": sanitize(report.settings),
    }
    for name, data in files.items():
        (out / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "python_packages.txt").write_text("\n".join(python_packages()) + "\n", encoding="utf-8")
    return out


# ---------------------------------------------------------------- Smoke test（不需 GPU）
def smoke_test() -> list[tuple[str, Status, str]]:
    """暫存 workspace＋mock LLM＋placeholder 圖＋silent TTS＋Ken Burns＋ffmpeg 組裝；不碰使用者 workspace、不需 GPU、不下載。"""
    import tempfile

    results: list[tuple[str, Status, str]] = []
    try:
        from see.ui.server import create_app  # noqa: F401 — 只驗證 Web API 可匯入

        results.append(("web_api_import", Status.OK, "see.ui.server 可匯入"))
    except Exception as e:  # noqa: BLE001
        results.append(("web_api_import", Status.ERROR, f"{type(e).__name__}: {e}"))
    with tempfile.TemporaryDirectory(prefix="see-smoke-") as tmp:
        s = Settings()
        s.workspace = Path(tmp) / "ws"
        s.llm_provider, s.image_provider, s.tts_provider, s.audio_provider, s.lipsync_provider = "mock", "placeholder", "silent", "null", "null"
        s.width, s.height, s.fps, s.min_scene_duration = 320, 180, 10, 1.0
        try:
            from see.pipeline.orchestrator import Orchestrator
            from see.providers.registry import ProviderRegistry
            from see.render.renderer import Renderer
            from see.storage.project_store import ProjectStore
            from see.workers.local import LocalExecutor

            reg = ProviderRegistry(s)
            prov = reg.build()
            results.append(("tts_interface", Status.OK, f"TTS provider 可建立：{prov.tts.info.name}"))
            if not reg.ffmpeg.available():
                results.append(("pipeline", Status.UNAVAILABLE, "ffmpeg 不可用：略過 pipeline／render"))
                return results
            orch = Orchestrator(s, prov, LocalExecutor(), ProjectStore(s.workspace), Renderer(reg.ffmpeg))
            rep = orch.run("小貓在院子裡玩。月亮出來了。", title="smoke")
            again = ProjectStore(s.workspace).load(rep.project.project_id)
            out = Path(rep.job.output_path or "")
            good = out.is_file() and out.stat().st_size > 0 and len(again.scenes) == len(rep.project.scenes)
            results.append(("pipeline", Status.OK if good else Status.ERROR,
                            f"mock pipeline → preview {out.stat().st_size if out.is_file() else 0} bytes；project 重新載入 {len(again.scenes)} 景"))
        except Exception as e:  # noqa: BLE001
            results.append(("pipeline", Status.ERROR, f"{type(e).__name__}: {e}"))
    return results
