"""設定：環境變數 → Settings。不含任何 secret 的預設值。"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from see.audio.mixer import MixParams


def _env(name: str, default: str) -> str:
    value = os.environ.get(name)
    return value if value not in (None, "") else default


# ---------------------------------------------------------------- 本機設定檔（D-065；客戶裁示方案 A）
# 優先序：OS 環境變數 → 專案本機設定檔 → 未設定（程式預設）。只放 machine-specific 設定；不放 secret、不放 portable 偏好。
# 檔案：<repo>/see.local.json（.gitignore；GitHub 只放 see.local.example.json）。測試／特殊情況可用 SEE_LOCAL_CONFIG 指定路徑。
LOCAL_CONFIG_NAME = "see.local.json"
LOCAL_CONFIG_SCHEMA_VERSION = 1
LOCAL_CONFIG_KEYS: dict[str, str] = {  # local config key → 對應環境變數
    "models_dir": "SEE_MODELS_DIR",
    "workspace_dir": "SEE_WORKSPACE",
    "image_model_path": "SEE_IMAGE_MODEL_PATH",
    "tts_model_path": "SEE_TTS_MODEL_PATH",
    "tts_device": "SEE_TTS_DEVICE",
    "ffmpeg": "SEE_FFMPEG",
    "ffprobe": "SEE_FFPROBE",
    "subtitle_font": "SEE_SUBTITLE_FONT",
}
PATH_KEYS = {"models_dir", "workspace_dir", "image_model_path", "tts_model_path"}


class LocalConfigError(ValueError):
    pass


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def local_config_path() -> Path:
    override = os.environ.get("SEE_LOCAL_CONFIG")
    return Path(override) if override else repo_root() / LOCAL_CONFIG_NAME


def validate_local_config(data: object) -> dict[str, str]:
    """只接受已知 machine-specific key 與字串值；其他（含 portable 偏好、secret、未來版本）→ LocalConfigError（fail closed）。"""
    if not isinstance(data, dict):
        raise LocalConfigError("local config must be a JSON object")
    ver = data.get("schema_version", LOCAL_CONFIG_SCHEMA_VERSION)
    if not isinstance(ver, int) or ver > LOCAL_CONFIG_SCHEMA_VERSION:
        raise LocalConfigError(f"unsupported schema_version {ver!r} (supported ≤ {LOCAL_CONFIG_SCHEMA_VERSION})")
    unknown = sorted(set(data) - set(LOCAL_CONFIG_KEYS) - {"schema_version", "_comment"})
    if unknown:
        raise LocalConfigError(f"keys not allowed in local config (machine-specific only; no secrets/preferences): {unknown}")
    out: dict[str, str] = {}
    for k in LOCAL_CONFIG_KEYS:
        v = data.get(k)
        if v is None or v == "":
            continue
        if not isinstance(v, str):
            raise LocalConfigError(f"{k} must be a string")
        out[k] = v
    return out


def read_local_config(path: Path | None = None) -> tuple[dict[str, str], str | None]:
    """(有效值, 錯誤)。檔案不存在 → ({}, None)；格式錯 → ({}, 錯誤訊息)：整份不採用（fail closed），由 doctor 顯示。"""
    p = path or local_config_path()
    if not p.is_file():
        return {}, None
    try:
        data = validate_local_config(json.loads(p.read_text(encoding="utf-8")))
    except (ValueError, OSError) as e:
        return {}, f"{p.name}: {e}"
    base = p.resolve().parent
    for k in PATH_KEYS & set(data):  # 相對路徑以設定檔所在資料夾為基準（不寫死磁碟代號；整個資料夾搬走仍有效）
        if not Path(data[k]).is_absolute() and not _looks_windows_abs(data[k]):
            data[k] = str((base / data[k]).resolve())
    return data, None


def _looks_windows_abs(v: str) -> bool:
    return len(v) >= 3 and v[1] == ":" and v[2] in "\\/"


def write_local_config(updates: dict[str, str | None], path: Path | None = None) -> Path:
    """使用者明確要求才寫（`config set／unset`）。只改指定 key；驗證後原子寫入。"""
    p = path or local_config_path()
    current = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
    current = {k: v for k, v in current.items() if k != "_comment"}
    current["schema_version"] = LOCAL_CONFIG_SCHEMA_VERSION
    for k, v in updates.items():
        if k not in LOCAL_CONFIG_KEYS:
            raise LocalConfigError(f"unknown local config key {k!r}; allowed: {sorted(LOCAL_CONFIG_KEYS)}")
        if v in (None, ""):
            current.pop(k, None)
        else:
            current[k] = v
    validate_local_config(current)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(p)
    return p


def setting_source(env_name: str, env: dict[str, str] | None = None, local: dict[str, str] | None = None) -> tuple[str | None, str]:
    """(值, 來源)：來源為 env／local_config／unset。"""
    env = os.environ if env is None else env
    v = env.get(env_name)
    if v not in (None, ""):
        return v, "env"
    local = read_local_config()[0] if local is None else local
    key = next((k for k, e in LOCAL_CONFIG_KEYS.items() if e == env_name), None)
    if key and local.get(key):
        return local[key], "local_config"
    return None, "unset"


def _machine(env_name: str, default: str) -> str:
    """machine-specific 設定：env → local config → 預設。"""
    v, _ = setting_source(env_name)
    return v if v is not None else default


def detect_cjk_font() -> str:
    """用 fontconfig 找可顯示中文的字型；找不到回傳空字串（libass 會用預設字型）。"""
    fc_list = shutil.which("fc-list")
    if not fc_list:
        return ""
    try:
        from see.core.proc import run_text

        out = run_text([fc_list, ":lang=zh", "family"], timeout=10).stdout
    except (subprocess.SubprocessError, OSError):
        return ""
    families: list[str] = []
    for line in out.splitlines():
        for fam in line.split(","):
            fam = fam.strip()
            if fam:
                families.append(fam)
    preferred = ("Noto Sans CJK TC", "Noto Sans CJK SC", "Noto Sans CJK", "WenQuanYi Zen Hei",
                 "WenQuanYi Micro Hei", "Microsoft JhengHei", "PingFang TC", "Droid Sans Fallback")
    for p in preferred:
        if p in families:
            return p
    for p in preferred:
        for fam in families:
            if fam.startswith(p):
                return fam
    return families[0] if families else ""


@dataclass
class Settings:
    workspace: Path = field(default_factory=lambda: Path(_machine("SEE_WORKSPACE", "./workspace")).resolve())
    llm_provider: str = field(default_factory=lambda: _env("SEE_LLM_PROVIDER", "mock"))
    image_provider: str = field(default_factory=lambda: _env("SEE_IMAGE_PROVIDER", "placeholder"))
    image_model_preset: str = field(default_factory=lambda: _env("SEE_IMAGE_MODEL_PRESET", "sd15"))
    image_model_path: str = field(default_factory=lambda: _machine("SEE_IMAGE_MODEL_PATH", ""))
    models_dir: Path = field(default_factory=lambda: Path(_machine("SEE_MODELS_DIR", "./models")).resolve())
    video_provider: str = field(default_factory=lambda: _env("SEE_VIDEO_PROVIDER", "kenburns"))
    tts_provider: str = field(default_factory=lambda: _env("SEE_TTS_PROVIDER", "auto"))
    tts_model_path: str = field(default_factory=lambda: _machine("SEE_TTS_MODEL_PATH", ""))  # 空 = models_dir/kokoro-v1_1-zh
    tts_device: str = field(default_factory=lambda: _machine("SEE_TTS_DEVICE", "cpu"))  # cpu 預設：不與 SD 1.5 搶 4 GB VRAM
    tts_default_voice: str = field(default_factory=lambda: _env("SEE_TTS_DEFAULT_VOICE", ""))  # scene.voice=default 時用；空=provider 自定（永久預設待 DG-14）
    audio_provider: str = field(default_factory=lambda: _env("SEE_AUDIO_PROVIDER", "null"))  # null = Audio Layer 停用（預設，舊行為）
    mix_params: MixParams = field(default_factory=MixParams)  # BGM/SFX/ducking/limiter 參數（D-031）
    lipsync_provider: str = field(default_factory=lambda: _env("SEE_LIPSYNC_PROVIDER", "null"))
    subtitle_font: str = field(default_factory=lambda: _machine("SEE_SUBTITLE_FONT", "") or detect_cjk_font())
    width: int = 1280
    height: int = 720
    fps: int = 25
    transition_duration: float = 0.5
    min_scene_duration: float = 3.0
    max_scene_duration: float = 12.0
    target_total_min: float = 30.0
    target_total_max: float = 60.0
    narration_pad: float = 0.6
    ffmpeg: str = field(default_factory=lambda: _machine("SEE_FFMPEG", "ffmpeg"))
    ffprobe: str = field(default_factory=lambda: _machine("SEE_FFPROBE", "ffprobe"))

    def fingerprint_params(self) -> dict[str, object]:
        """會影響產物內容的設定；進 fingerprint。"""
        return {
            "width": self.width, "height": self.height, "fps": self.fps,
            "transition_duration": self.transition_duration, "subtitle_font": self.subtitle_font,
            "narration_pad": self.narration_pad,
        }
