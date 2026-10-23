"""硬體能力偵測：GPU / VRAM / RAM / disk / CUDA / torch。純標準函式庫 + 可選工具，不下載任何東西。

用途：自動判斷本機能跑哪一級的 AI Image Provider，避免要求使用者自行研究硬體。
"""

from __future__ import annotations

import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class GPUInfo(BaseModel):
    vendor: str = Field(description="nvidia | amd | intel | apple | unknown")
    name: str = ""
    vram_total_mb: int | None = None
    vram_free_mb: int | None = None
    driver: str = ""
    source: str = Field(default="", description="偵測來源：nvidia-smi | rocm-smi | wmic | torch | system_profiler")


class TorchInfo(BaseModel):
    installed: bool = False
    version: str = ""
    cuda_available: bool = False
    cuda_version: str = ""
    rocm: bool = False
    mps: bool = False
    directml: bool = False
    diffusers_installed: bool = False
    transformers_installed: bool = False


class HardwareProfile(BaseModel):
    os: str
    os_version: str = ""
    arch: str = ""
    python: str = ""
    cpu: str = ""
    cpu_cores: int | None = None
    ram_total_mb: int | None = None
    ram_available_mb: int | None = None
    disk_free_mb: int | None = None
    disk_path: str = ""
    gpus: list[GPUInfo] = Field(default_factory=list)
    torch: TorchInfo = Field(default_factory=TorchInfo)
    notes: list[str] = Field(default_factory=list)

    @property
    def best_gpu(self) -> GPUInfo | None:
        if not self.gpus:
            return None
        return max(self.gpus, key=lambda g: g.vram_total_mb or 0)

    @property
    def max_vram_mb(self) -> int:
        g = self.best_gpu
        return (g.vram_total_mb or 0) if g else 0


# ---------------------------------------------------------------- helpers
def _run(cmd: list[str], timeout: float = 15) -> str | None:
    if shutil.which(cmd[0]) is None:
        return None
    from see.core.proc import run_text

    try:
        p = run_text(cmd, timeout=timeout)
    except (subprocess.SubprocessError, OSError):
        return None
    return p.stdout if p.returncode == 0 else None


def _ram() -> tuple[int | None, int | None]:
    """(total_mb, available_mb)。優先 psutil；否則 Linux /proc、Windows ctypes、macOS sysctl。"""
    if importlib.util.find_spec("psutil"):
        import psutil  # type: ignore

        vm = psutil.virtual_memory()
        return int(vm.total / 2**20), int(vm.available / 2**20)
    system = platform.system()
    if system == "Linux":
        try:
            info: dict[str, int] = {}
            for line in Path("/proc/meminfo").read_text().splitlines():
                k, _, v = line.partition(":")
                info[k.strip()] = int(v.strip().split()[0])
            return info["MemTotal"] // 1024, info.get("MemAvailable", 0) // 1024 or None
        except (OSError, KeyError, ValueError):
            return None, None
    if system == "Windows":
        try:
            import ctypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

            st = MEMORYSTATUSEX()
            st.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st))  # type: ignore[attr-defined]
            return int(st.ullTotalPhys / 2**20), int(st.ullAvailPhys / 2**20)
        except Exception:  # noqa: BLE001
            return None, None
    if system == "Darwin":
        out = _run(["sysctl", "-n", "hw.memsize"])
        return (int(out.strip()) // 2**20, None) if out else (None, None)
    return None, None


def _gpus_nvidia() -> list[GPUInfo]:
    out = _run(["nvidia-smi", "--query-gpu=name,memory.total,memory.used,driver_version", "--format=csv,noheader,nounits"])
    gpus: list[GPUInfo] = []
    if not out:
        return gpus
    for line in out.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 4:
            continue
        try:
            total, used = int(float(parts[1])), int(float(parts[2]))
        except ValueError:
            total, used = 0, 0
        gpus.append(GPUInfo(vendor="nvidia", name=parts[0], vram_total_mb=total, vram_free_mb=max(total - used, 0),
                            driver=parts[3], source="nvidia-smi"))
    return gpus


def _gpus_amd() -> list[GPUInfo]:
    out = _run(["rocm-smi", "--showproductname", "--showmeminfo", "vram", "--json"])
    gpus: list[GPUInfo] = []
    if not out:
        return gpus
    try:
        data = json.loads(out)
    except ValueError:
        return gpus
    for key, card in data.items():
        if not isinstance(card, dict):
            continue
        name = card.get("Card series") or card.get("Card SKU") or key
        total = card.get("VRAM Total Memory (B)")
        used = card.get("VRAM Total Used Memory (B)")
        t = int(total) // 2**20 if total else None
        u = int(used) // 2**20 if used else 0
        gpus.append(GPUInfo(vendor="amd", name=str(name), vram_total_mb=t, vram_free_mb=(t - u) if t else None, source="rocm-smi"))
    return gpus


def _gpus_windows_generic() -> list[GPUInfo]:
    """Windows：PowerShell CIM 查所有顯示卡（AdapterRAM 在 >4GB 卡上可能不準，只作備援）。"""
    ps = _run(["powershell", "-NoProfile", "-Command",
               "Get-CimInstance Win32_VideoController | Select-Object Name,AdapterRAM,DriverVersion | ConvertTo-Json"], timeout=25)
    gpus: list[GPUInfo] = []
    if not ps:
        return gpus
    try:
        data = json.loads(ps)
    except ValueError:
        return gpus
    for item in data if isinstance(data, list) else [data]:
        name = str(item.get("Name", ""))
        low = name.lower()
        vendor = "nvidia" if "nvidia" in low else "amd" if ("amd" in low or "radeon" in low) else "intel" if "intel" in low else "unknown"
        ram = item.get("AdapterRAM")
        gpus.append(GPUInfo(vendor=vendor, name=name, vram_total_mb=int(ram) // 2**20 if ram else None,
                            driver=str(item.get("DriverVersion", "")), source="wmic"))
    return gpus


def _gpus_macos() -> list[GPUInfo]:
    out = _run(["system_profiler", "SPDisplaysDataType", "-json"], timeout=25)
    if not out:
        return []
    try:
        items = json.loads(out).get("SPDisplaysDataType", [])
    except ValueError:
        return []
    return [GPUInfo(vendor="apple" if "Apple" in str(i.get("sppci_model", "")) else "unknown",
                    name=str(i.get("sppci_model", "")), source="system_profiler") for i in items]


def _torch_info() -> TorchInfo:
    info = TorchInfo(diffusers_installed=importlib.util.find_spec("diffusers") is not None,
                     transformers_installed=importlib.util.find_spec("transformers") is not None,
                     directml=importlib.util.find_spec("torch_directml") is not None)
    if importlib.util.find_spec("torch") is None:
        return info
    try:
        import torch  # type: ignore

        info.installed = True
        info.version = str(torch.__version__)
        info.cuda_available = bool(torch.cuda.is_available())
        info.cuda_version = str(getattr(torch.version, "cuda", "") or "")
        info.rocm = bool(getattr(torch.version, "hip", None))
        info.mps = bool(getattr(getattr(torch, "backends", None), "mps", None) and torch.backends.mps.is_available())
    except Exception:  # noqa: BLE001 — torch 損壞也不能讓偵測失敗
        pass
    return info


def detect_hardware(disk_path: str | os.PathLike[str] = ".") -> HardwareProfile:
    system = platform.system()
    total, avail = _ram()
    try:
        du = shutil.disk_usage(disk_path)
        disk_free = int(du.free / 2**20)
    except OSError:
        disk_free = None
    gpus = _gpus_nvidia() or _gpus_amd()
    if not gpus and system == "Windows":
        gpus = _gpus_windows_generic()
    if not gpus and system == "Darwin":
        gpus = _gpus_macos()
    prof = HardwareProfile(
        os=system, os_version=platform.version(), arch=platform.machine(), python=platform.python_version(),
        cpu=platform.processor() or platform.machine(), cpu_cores=os.cpu_count(),
        ram_total_mb=total, ram_available_mb=avail, disk_free_mb=disk_free, disk_path=str(Path(disk_path).resolve()),
        gpus=gpus, torch=_torch_info(),
    )
    if not gpus:
        prof.notes.append("未偵測到獨立 GPU（或缺 nvidia-smi / rocm-smi）；只能走 CPU-only 路線。")
    if any(g.source == "wmic" for g in gpus):
        prof.notes.append("VRAM 由 Windows CIM 回報，>4GB 顯示卡可能不準；裝好 NVIDIA 驅動後以 nvidia-smi 為準。")
    if sys.version_info >= (3, 13) and not prof.torch.installed:
        prof.notes.append("Python 3.13：PyTorch 2.6+ 才有官方 wheel；若安裝失敗建議用 Python 3.11/3.12 的 venv。")
    return prof


# ---------------------------------------------------------------- recommendation
class ImageTier(BaseModel):
    key: str
    label: str
    model_id: str
    license: str
    download_gb: float
    min_vram_mb: int
    recommended_vram_mb: int
    min_ram_mb: int
    min_disk_gb: float
    cost_tier: str = "LOCAL_FREE"
    notes: str = ""


IMAGE_TIERS: list[ImageTier] = [
    ImageTier(key="flux-schnell", label="推薦：FLUX.1-schnell（Apache-2.0，4 步快速）", model_id="black-forest-labs/FLUX.1-schnell",
              license="Apache-2.0（商用可）", download_gb=24.0, min_vram_mb=12_000, recommended_vram_mb=16_000, min_ram_mb=32_000,
              min_disk_gb=30, notes="fp16/bf16 全精度；8–12GB VRAM 可改 NF4/GGUF 量化（約 7–12GB 下載），畫質略降。英文 prompt 最佳。"),
    ImageTier(key="flux-schnell-nf4", label="FLUX.1-schnell 量化（NF4/GGUF）", model_id="black-forest-labs/FLUX.1-schnell",
              license="Apache-2.0（商用可）", download_gb=12.0, min_vram_mb=8_000, recommended_vram_mb=12_000, min_ram_mb=16_000,
              min_disk_gb=16, notes="需 bitsandbytes 或 gguf；速度較慢但 8GB 卡可跑。"),
    ImageTier(key="sd15", label="低需求 fallback：Stable Diffusion 1.5", model_id="stable-diffusion-v1-5/stable-diffusion-v1-5",
              license="CreativeML OpenRAIL-M（商用可，附使用限制）", download_gb=4.0, min_vram_mb=4_000, recommended_vram_mb=6_000,
              min_ram_mb=8_000, min_disk_gb=6, notes="512×512；CPU-only 可跑（每張約 1–4 分鐘）；畫質與文字理解較弱。"),
    ImageTier(key="paid-api", label="未來付費 fallback（需人工核准）", model_id="(any PAID image API)", license="依供應商",
              download_gb=0, min_vram_mb=0, recommended_vram_mb=0, min_ram_mb=0, min_disk_gb=0, cost_tier="PAID",
              notes="需 API key 與 Approval；本專案預設 budget=0，不會自動呼叫。"),
]


class ImageRecommendation(BaseModel):
    recommended: ImageTier | None
    fallback: ImageTier | None
    cpu_only: bool
    reasons: list[str] = Field(default_factory=list)


def recommend_image_tier(profile: HardwareProfile) -> ImageRecommendation:
    vram = profile.max_vram_mb
    ram = profile.ram_total_mb or 0
    disk_gb = (profile.disk_free_mb or 0) / 1024
    gpu = profile.best_gpu
    reasons: list[str] = []
    cuda_ok = gpu is not None and gpu.vendor == "nvidia"
    if gpu is not None and gpu.vendor == "amd":
        reasons.append("AMD GPU：Windows 需 torch-directml 或 ROCm（支援度有限），效能與相容性低於 NVIDIA；預估以 CPU/DirectML 為準。")
    if gpu is not None and gpu.vendor == "apple":
        reasons.append("Apple Silicon：可用 MPS 後端；VRAM 為共用記憶體，以 RAM 判斷。")
        vram = ram
        cuda_ok = True
    cpu_only = not cuda_ok and not (gpu is not None and gpu.vendor == "amd")

    def fits(t: ImageTier) -> bool:
        if t.cost_tier != "LOCAL_FREE":
            return False
        if t.min_vram_mb > 0 and (cpu_only or vram < t.min_vram_mb):
            return False
        if ram and ram < t.min_ram_mb:
            return False
        if disk_gb and disk_gb < t.min_disk_gb:
            return False
        return True

    local = [t for t in IMAGE_TIERS if t.cost_tier == "LOCAL_FREE"]
    rec = next((t for t in local if fits(t)), None)
    fb = next((t for t in local if t is not rec and fits(t)), None)
    if rec is None:
        sd15 = next(t for t in IMAGE_TIERS if t.key == "sd15")
        if cpu_only and ram >= sd15.min_ram_mb and disk_gb >= sd15.min_disk_gb:
            rec = sd15
            reasons.append("無可用 CUDA GPU：僅 SD 1.5 CPU-only 可行，每張約 1–4 分鐘。")
        else:
            reasons.append("硬體不足以在本機跑任何候選模型；需升級硬體或走付費 fallback（需核准）。")
    if gpu is None:
        reasons.append("未偵測到 GPU。")
    else:
        reasons.append(f"GPU：{gpu.name}，VRAM {gpu.vram_total_mb or '?'} MB（{gpu.source}）。")
    if not profile.torch.installed:
        reasons.append("尚未安裝 PyTorch / diffusers；安裝後才會嘗試本機生圖。")
    reasons.append(f"RAM {ram} MB，可用磁碟 {disk_gb:.1f} GB（{profile.disk_path}）。")
    return ImageRecommendation(recommended=rec, fallback=fb, cpu_only=cpu_only, reasons=reasons)


def hardware_report(disk_path: str | os.PathLike[str] = ".") -> dict[str, Any]:
    prof = detect_hardware(disk_path)
    rec = recommend_image_tier(prof)
    return {"hardware": prof.model_dump(), "image_recommendation": rec.model_dump()}
