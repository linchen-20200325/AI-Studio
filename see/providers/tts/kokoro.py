"""KokoroTTSProvider：Kokoro-82M v1.1-zh 本機中文 TTS（LOCAL_FREE；D-027 候選驗證階段，非最終採用）。

- 權重：`hexgrad/Kokoro-82M-v1.1-zh`（Apache-2.0，≈330 MB）。**本模組永不自行下載**；權重只能由使用者執行
  `python -m see.app.cli tts-download --yes` 取得（PROJECT_RULES §10），並寫入 provenance.json（來源／版本／大小／sha256）。
- 執行：純 Python（`kokoro` + `misaki[zh]` + torch），預設 CPU（不與 SD 1.5 搶 GTX 1650 的 4 GB VRAM）。
- 失敗一律 raise ProviderError（fail-closed）；FallbackTTSProvider 會接著嘗試 espeak / silent，絕不自動切 PAID。
- 測試以注入的 fake backend 執行，CI 不需套件、不需權重。
"""

from __future__ import annotations

import importlib.util
import json
import logging
import time
import wave
from pathlib import Path
from typing import Any, Protocol

import numpy as np

from see.core.errors import ProviderError, ProviderUnavailable
from see.core.ffmpeg import FFmpeg
from see.models.cost import CostEstimate
from see.models.enums import CostTier, ProviderKind
from see.models.provider import ProviderInfo
from see.providers.base import TTSProvider, TTSRequest, TTSResult, VoiceInfo

log = logging.getLogger(__name__)

REPO_ID = "hexgrad/Kokoro-82M-v1.1-zh"
MODEL_FILE = "kokoro-v1_1-zh.pth"
CONFIG_FILE = "config.json"
PROVENANCE_FILE = "provenance.json"
LICENSE = "Apache-2.0"
APPROVAL = "D-027 (Candidate Validation Approval)"
ESTIMATED_MB = 330
SAMPLE_RATE = 24000
# 預設先抓 2 女 2 男做角色差異驗證；repo 若無該檔名，下載器會改抓實際存在的前幾個 zf_/zm_
PREFERRED_VOICES = ("zf_001", "zf_002", "zm_009", "zm_010")
MIN_AUDIO_SECONDS = 0.2
# 可讀名稱／已知限制型錄（Voice Selector 規格）。accent_note 來自使用者 2026-10-23 真機主觀聽感（PHASE2_EVIDENCE），不是客觀排名。
VOICE_CATALOG: dict[str, dict[str, Any]] = {
    "zf_001": {"display_name": "女聲 1", "tags": ["narration"], "accent_note": "使用者真機聽感：大陸口音明顯；不建議作預設"},
    "zf_002": {"display_name": "女聲 2", "tags": ["narration"], "accent_note": "使用者真機聽感：較 zf_001 好，仍非首選"},
    "zm_009": {"display_name": "男聲 9", "tags": ["narration"], "accent_note": "使用者真機聽感：無明顯大陸口音，自然度尚可"},
    "zm_010": {"display_name": "男聲 10", "tags": ["narration"], "accent_note": "使用者真機聽感：四者中最自然；目前 Kokoro 內部首選候選（D-028，未鎖死）"},
}


def download_plan() -> dict[str, Any]:
    """只描述要下載什麼，不做任何網路動作。"""
    return {"repo_id": REPO_ID, "files": [CONFIG_FILE, MODEL_FILE], "voices": list(PREFERRED_VOICES),
            "estimated_mb": ESTIMATED_MB, "license": LICENSE, "approval": APPROVAL,
            "pip": ["kokoro>=0.9", "misaki[zh]>=0.9"], "device_default": "cpu"}


def local_voices(model_dir: Path) -> list[str]:
    d = Path(model_dir) / "voices"
    return sorted(p.stem for p in d.glob("*.pt")) if d.is_dir() else []


def weights_present(model_dir: Path) -> bool:
    d = Path(model_dir)
    return (d / MODEL_FILE).is_file() and (d / CONFIG_FILE).is_file() and bool(local_voices(d))


def read_provenance(model_dir: Path) -> dict[str, Any]:
    p = Path(model_dir) / PROVENANCE_FILE
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


class KokoroBackend(Protocol):
    """可替換的推理後端（測試注入 fake）。回傳 (float32 mono samples, sample_rate)。"""

    def synthesize(self, text: str, voice_path: Path, speed: float) -> tuple[np.ndarray, int]: ...

    def describe(self) -> dict[str, Any]: ...


class _RealKokoroBackend:
    """真正的 kokoro 推理；lazy import，只有 synthesize 時才載入模型（一個程序載一次）。"""

    def __init__(self, model_dir: Path, device: str) -> None:
        self.model_dir = Path(model_dir)
        self.device = device
        self._pipeline: Any = None
        self._voice_cache: dict[Path, Any] = {}
        self.torch_version: str | None = None

    def _load(self) -> Any:
        if self._pipeline is not None:
            return self._pipeline
        try:
            import torch  # type: ignore
            from kokoro import KModel, KPipeline  # type: ignore
        except ImportError as e:  # pragma: no cover - 依環境
            raise ProviderUnavailable(f"kokoro/torch not installed: {e}") from e
        self.torch_version = getattr(torch, "__version__", None)
        if self.device.startswith("cuda") and not torch.cuda.is_available():
            log.warning("SEE_TTS_DEVICE=%s but CUDA unavailable; using cpu", self.device)
            self.device = "cpu"
        t0 = time.perf_counter()
        # 以本機檔案建模：給了 config/model 路徑後 KModel 不會向 HF 下載
        model = KModel(repo_id=REPO_ID, config=str(self.model_dir / CONFIG_FILE), model=str(self.model_dir / MODEL_FILE)).eval()
        model = model.to(self.device)
        self._pipeline = KPipeline(lang_code="z", repo_id=REPO_ID, model=model, device=self.device)
        self.load_seconds = round(time.perf_counter() - t0, 3)
        return self._pipeline

    def synthesize(self, text: str, voice_path: Path, speed: float) -> tuple[np.ndarray, int]:
        import torch  # type: ignore

        pipeline = self._load()
        voice = self._voice_cache.get(voice_path)
        if voice is None:
            voice = torch.load(str(voice_path), map_location=self.device, weights_only=True)
            self._voice_cache[voice_path] = voice
        chunks: list[np.ndarray] = []
        for result in pipeline(text, voice=voice, speed=speed):
            audio = getattr(result, "audio", None)
            if audio is None:
                continue
            arr = audio.detach().cpu().numpy() if hasattr(audio, "detach") else np.asarray(audio)
            chunks.append(np.asarray(arr, dtype=np.float32).reshape(-1))
        if not chunks:
            return np.zeros(0, dtype=np.float32), SAMPLE_RATE
        return np.concatenate(chunks), SAMPLE_RATE

    def describe(self) -> dict[str, Any]:
        return {"device": self.device, "torch": self.torch_version, "load_seconds": getattr(self, "load_seconds", None)}


def write_wav(path: Path, samples: np.ndarray, sample_rate: int) -> None:
    """float32 [-1,1] → 16-bit PCM mono wav（不新增 soundfile 相依）。"""
    pcm = (np.clip(samples, -1.0, 1.0) * 32767.0).astype("<i2")
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm.tobytes())


class KokoroTTSProvider(TTSProvider):
    DEFAULT_DIRNAME = "kokoro-v1_1-zh"

    def __init__(self, model_dir: str | Path, ffmpeg: FFmpeg | None = None, device: str = "cpu",
                 backend: KokoroBackend | None = None, default_voice: str = "") -> None:
        self.model_dir = Path(model_dir)
        self.ffmpeg = ffmpeg or FFmpeg()
        self.device = device
        self.default_voice = default_voice  # 空 = 第一個 zf_*（程式既有行為）；設定值缺檔 → fail-closed
        self._backend = backend
        self.calls = 0

    @property
    def info(self) -> ProviderInfo:
        return ProviderInfo(name="kokoro-tts", kind=ProviderKind.TTS, cost_tier=CostTier.LOCAL_FREE,
                            model=REPO_ID, version="1", requires_network=False)

    def is_available(self) -> bool:
        if self._backend is not None:
            return weights_present(self.model_dir) or bool(local_voices(self.model_dir))
        return (importlib.util.find_spec("kokoro") is not None and importlib.util.find_spec("torch") is not None
                and weights_present(self.model_dir))

    def estimate_cost(self, request: TTSRequest) -> CostEstimate:
        return self._estimate(units=len(request.text), unit_name="chars")

    @staticmethod
    def _gender(voice_id: str) -> str:
        return "female" if voice_id.startswith("zf_") else "male" if voice_id.startswith("zm_") else "unknown"

    def list_voices(self) -> list[VoiceInfo]:
        out = []
        for v in local_voices(self.model_dir):
            c = VOICE_CATALOG.get(v, {})
            out.append(VoiceInfo(voice_id=v, provider=self.info.name, display_name=c.get("display_name", v), language="zh",
                                 gender=self._gender(v), tags=list(c.get("tags", [])), accent_note=c.get("accent_note", "")))
        return out

    def resolve_voice(self, voice: str) -> Path:
        """`scene.voice` → 本機 voices/<id>.pt；default = `default_voice`（SEE_TTS_DEFAULT_VOICE／--voice），
        未設定則第一個女聲（zf_*），找不到就第一個；未知 voice 或缺檔一律 fail-closed。"""
        available = local_voices(self.model_dir)
        if not available:
            raise ProviderUnavailable(f"no kokoro voices in {self.model_dir / 'voices'}; run `tts-download --yes`")
        if voice in ("", "default") and self.default_voice:
            if self.default_voice not in available:
                raise ProviderError(f"default voice '{self.default_voice}' not downloaded; available: {available}")
            chosen = self.default_voice
        elif voice in ("", "default"):
            chosen = next((v for v in available if v.startswith("zf_")), available[0])
        elif voice in available:
            chosen = voice
        else:
            raise ProviderError(f"unknown kokoro voice '{voice}'; available: {available}")
        return self.model_dir / "voices" / f"{chosen}.pt"

    def synthesize(self, request: TTSRequest, out_path: Path) -> TTSResult:
        if not self.is_available():
            raise ProviderUnavailable(f"kokoro not available (package or weights missing at {self.model_dir})")
        backend = self._backend or _RealKokoroBackend(self.model_dir, self.device)
        self._backend = backend
        voice_path = self.resolve_voice(request.voice)
        self.calls += 1
        t0 = time.perf_counter()
        try:
            samples, sr = backend.synthesize(request.text, voice_path, request.speed)
        except (ProviderError, ProviderUnavailable):
            raise
        except Exception as e:  # 任何推理錯誤 → ProviderError，由 Fallback 決定下一步，不自動切 PAID
            raise ProviderError(f"kokoro synthesis failed: {e}") from e
        elapsed = time.perf_counter() - t0
        samples = np.asarray(samples, dtype=np.float32).reshape(-1)
        duration = samples.size / float(sr) if sr > 0 else 0.0
        if duration < MIN_AUDIO_SECONDS:
            raise ProviderError(f"kokoro produced {duration:.3f}s of audio for {len(request.text)} chars (empty output)")
        peak = float(np.max(np.abs(samples))) if samples.size else 0.0
        if peak < 1e-4:
            raise ProviderError("kokoro produced silent audio (peak≈0); refusing to pass silence as narration")
        write_wav(out_path, samples, sr)
        info = self.ffmpeg.probe(out_path)
        prov = read_provenance(self.model_dir)
        meta = {"generated_by": self.info.name, "voice": voice_path.stem, "speed": request.speed,
                "synth_seconds": round(elapsed, 3), "rtf": round(elapsed / duration, 3) if duration else None,
                "peak": round(peak, 4), "model_sha256": (prov.get("files") or {}).get(MODEL_FILE, {}).get("sha256"),
                "model_revision": prov.get("revision"), **backend.describe()}
        return TTSResult(path=str(out_path), duration=info.duration, provider=self.info.name,
                         model=self.info.model, sample_rate=info.sample_rate, meta=meta)
