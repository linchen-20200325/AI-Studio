# ENVIRONMENT_SETUP.md — 新電腦安裝與環境檢查（D-064）

> 目標：只靠 GitHub（不靠聊天記憶）就能在新電腦／重灌後的電腦重建可用環境。
> 程式**不會**自動安裝套件、下載模型、改 CUDA／driver、改系統 PATH 或 registry、寫永久環境變數。
> 搬機／重灌／換 GPU／換磁碟請接著看 [`MIGRATION_REINSTALL.md`](MIGRATION_REINSTALL.md)。

## 0. 三個指令（全部唯讀，除非加旗標）
| 指令 | 做什麼 | 會寫入嗎 |
|---|---|---|
| `python -m see.app.cli doctor` | 檢查系統、Python／套件、GPU／CUDA、ffmpeg／git、模型、workspace；列出 Ready／Not ready 與 Tier A–D | 否（`--write-manifest` 才寫 `workspace/environment_manifest.json`；`--hash` 重算模型 sha256，大檔很慢；`--json` 機器可讀） |
| `python -m see.app.cli bootstrap` | 列出建置計畫：①可自動 ②需使用者操作 ③需下載／安裝裁示 ④blocked（`--check` 同義） | 否（`--apply-safe` 只建立缺少的**空** workspace 資料夾與 `workspace_version.json`，不刪、不搬、不覆寫） |
| `python -m see.app.cli smoke` | 不需 GPU 的冒煙測試：Web API 可匯入、TTS 介面、mock→placeholder→silent→ffmpeg 預覽影片（暫存資料夾，不碰你的 workspace） | 否 |

狀態只有四種：`OK`／`PARTIAL`／`UNAVAILABLE`／`ERROR`。**缺少不等於 OK**。只有 `REQUIRED` 項目是 ERROR 時 doctor 才回傳失敗；optional 缺少（例如沒有 GPU、沒有 espeak-ng）是 `UNAVAILABLE`，不算整體失敗。

## 1. 必要設定只有一個
| 環境變數 | 何時需要 | 說明 |
|---|---|---|
| `SEE_MODELS_DIR` | 要用 SD1.5／Kokoro／checkpoint 時 | 模型資料夾（建議大容量磁碟，例 `E:\AI\models`）。換磁碟只改這一個。 |
| `SEE_IMAGE_PROVIDER` | 想用真 AI 生圖時設 `auto` | 預設 `placeholder`（production default，不改） |
| `SEE_TTS_PROVIDER` | 通常不用設 | 預設 `auto`（Kokoro → espeak-ng → silent） |

其他變數見 [`.env.example`](../.env.example)。程式不會自動讀 `.env`；Windows 用下列方式設定：
- 只對目前視窗：PowerShell `$env:SEE_MODELS_DIR="E:\AI\models"`；cmd `set SEE_MODELS_DIR=E:\AI\models`
- 永久（使用者自行決定）：`setx SEE_MODELS_DIR "E:\AI\models"`，然後**重開**終端機。doctor 只會提示，不會替你執行。

## 2. 安裝分層（每層可獨立判斷 readiness：`doctor` 最後的 Tiers）

### Tier A — 基礎環境（必要）
Python ≥ 3.11（建議 3.12；PyTorch wheel 最齊）、git、venv、專案依賴（`requirements.txt`，小型套件）、ffmpeg＋ffprobe。
Windows（每行一步，在專案根目錄；winget 安裝屬使用者操作）：
```
winget install Git.Git
winget install Gyan.FFmpeg
git clone https://github.com/linchen-20200325/AI-Studio.git
cd AI-Studio
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m see.app.cli doctor
```

### Tier B — CPU 功能（不需 GPU）
Web UI（fastapi／uvicorn，Tier A 已含）、TTS、程序生成音效（預設 null，DG-17）、字幕＋預覽影片組裝（ffmpeg）。
- Kokoro 中文 TTS（D-029）：`pip install "kokoro>=0.9" "misaki[zh]>=0.9"`（會帶入 torch），權重放 `%SEE_MODELS_DIR%\kokoro-v1_1-zh`（舊機搬來或 `tts-download --yes`；見 [`AI_TTS_KOKORO_WINDOWS.md`](AI_TTS_KOKORO_WINDOWS.md)）。
- 選用：espeak-ng（Kokoro 不可用時的 fallback）、中文字型（字幕）。
- 驗證：`python -m see.app.cli smoke`，再 `python -m see.ui --lan` 開 Web UI。

### Tier C — GPU 生圖（需 NVIDIA GPU；大型依賴需裁示）
CUDA 版 torch、diffusers、transformers、SD1.5 base（`%SEE_MODELS_DIR%\sd15`）、選用 checkpoint（`%SEE_MODELS_DIR%\checkpoints\<id>\`）。
已在客戶 Windows（GTX 1650 4 GB）實測過的組合見 [`AI_IMAGE_SD15_WINDOWS.md`](AI_IMAGE_SD15_WINDOWS.md) §4（torch cu126 wheel）。換 GPU／driver 後 wheel 版本可能不同 → 先跑 doctor，依 `gpu.cuda` 結果再決定；**安裝 torch 屬「需裁示」項目，程式不會自動執行**。
`doctor` 會回報：CUDA available、GPU 名稱、VRAM、torch 版本、CUDA build、cuDNN、compute capability、fp16／bf16 硬體支援。

### Tier D — 未來／目前 blocked（不要安裝）
| 能力 | 狀態 |
|---|---|
| Identity／Character LoRA 訓練 | HARDWARE_UPGRADE_BLOCKED（D-061；重開依 [`ARCHITECTURE.md`](ARCHITECTURE.md) §18 Resume Gate） |
| Identity Preservation（FaceID／InsightFace 等） | HARDWARE_UPGRADE_BLOCKED（D-061） |
| SDXL／Flux | 未核准下載（Decision Gate） |
| 真 image-to-video | 沒有已實作模型（目前 Ken Burns） |
| 真 lip-sync | 沒有已實作模型（介面存在、預設 null） |

## 3. 模型目錄結構（logical model ID → 相對 `SEE_MODELS_DIR`）
| model_id | 相對路徑 | doctor 判定 |
|---|---|---|
| `sd15_base` | `sd15/`（或 `SEE_IMAGE_MODEL_PATH`） | `model_index.json`＋unet／vae／text_encoder 權重 |
| `kokoro_v1_1_zh` | `kokoro-v1_1-zh/`（或 `SEE_TTS_MODEL_PATH`） | `.pth`＋`config.json`＋`voices/*.pt`；缺 `provenance.json` → PARTIAL |
| `cyberrealistic_final` | `checkpoints/cyberrealistic_final/CyberRealistic_FINAL_FP16.safetensors` | 大小＋provenance 的本機 sha256；`--hash` 才重算 |
| `meinamix_v12` | `checkpoints/meinamix_v12/meinamix_v12Final.safetensors` | 同上 |
| `ip_adapter_plus_face_sd15` | `adapters/ip_adapter_plus_face_sd15/` | 檔案＋provenance（identity 路線 blocked，只做存在檢查） |

## 4. 哪些檔案不進 Git
`workspace/`（專案、Reference Library 私人圖片、角色庫、evidence 圖、environment manifest、exports）、`/models/` 與所有權重（`*.safetensors`、`*.pth`…）、`.env`。
GitHub 只保存：程式、規則、schema、文件、[`environment_manifest.example.json`](environment_manifest.example.json)（去識別化範例）、`.env.example`（只有鍵名）。

## 5. Environment Manifest（machine-local）
`python -m see.app.cli doctor --write-manifest` → `workspace/environment_manifest.json`：schema_version、generated_at、OS、Python、torch、CUDA、GPU、VRAM、ffmpeg、repo commit、models_dir（變數名＋本機路徑）、models（logical ID／相對路徑／狀態）、detected_model_ids、workspace_version、readiness、settings（portable／machine-specific）。
家目錄一律寫成 `~`、使用者名稱寫成 `<user>`；secret 類變數只記 `<redacted>`。比程式新的 schema_version → 讀取時拒絕（fail safe）。
