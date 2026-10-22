# AI_IMAGE_PROVIDER_PLAN.md — AI Image Provider Phase 盤點（2026-10-22）

目的：讓每個 Scene 產生真正符合 `image_prompt` 的 AI 圖片，交給既有 Ken Burns + FFmpeg pipeline。
本文件是盤點與方案；**尚未下載任何模型**。裁示後才進入實作。

## 1. 現有架構是否足以接真實生圖
- `ImageProvider.generate_image(ImageRequest, out_path) -> ImageResult` 已含 prompt / negative_prompt / width / height / seed / caption，足夠。
- Orchestrator 以 `ImageRequest` + `ProviderInfo.fingerprint_key` 做 fingerprint：換 provider 或模型即自動重做圖片，其他產物不動。
- 新增（本批）：`DiffusersImageProvider`（骨架，`local_files_only=True`，缺權重即拒絕）、`FallbackImageProvider`（diffusers → placeholder，不跨 PAID）、`PaidImageProviderStub`（PAID 占位，永不連線）。`SEE_IMAGE_PROVIDER=auto` 即「有本機模型就用，沒有就 placeholder」。
- 缺口（待下一批）：`image_prompt` 目前是中文；FLUX / SD 對英文 prompt 效果最好。需在 storyboard 階段多產一個 `image_prompt_en`（Mock 可先用固定模板 + 關鍵詞表；真正翻譯待 LLM Provider）。Z-Image / Qwen-Image 類模型原生支援中文可免翻譯。

## 2. 候選模型（免費／open-weight）

| 候選 | License | 下載 | 最低 VRAM | 建議 VRAM | 備註 |
|---|---|---|---|---|---|
| **FLUX.1-schnell** | Apache-2.0（商用可） | ≈24 GB（含 T5 文字編碼器） | 12 GB（CPU offload） | 16 GB+ | 4 步出圖、畫質高；8–12 GB 卡可用 NF4/GGUF 量化（≈7–12 GB） |
| FLUX.1-dev | 非商用（FLUX.1-dev Non-Commercial License） | ≈24 GB | 12 GB | 16 GB+ | **商用受限，不採用** |
| Stable Diffusion 3.5 Medium | Stability Community License（年營收 < US$1M 免費） | ≈10 GB | 8 GB | 12 GB | 商用條款有門檻，列為備選 |
| **Stable Diffusion 1.5** | CreativeML OpenRAIL-M（商用可，附使用限制） | ≈4 GB（fp16 單檔 ≈2 GB） | 4 GB | 6 GB | 512×512；**CPU-only 可跑**（1–4 分/張）；畫質較弱 |
| SDXL base 1.0 | CreativeML Open RAIL++-M | ≈7 GB | 8 GB | 10 GB | 1024×1024，30 步較慢 |
| SDXL-Turbo | 非商用研究授權 | ≈7 GB | 6 GB | 8 GB | **商用受限，不採用** |
| Qwen-Image（20B） | Apache-2.0 | ≈40 GB | 24 GB | 48 GB | 中文 prompt 與文字渲染強；硬體門檻高 |
| Z-Image-Turbo（6B） | Apache-2.0 | ≈12 GB | 12 GB | 16 GB | 8 步、中文 prompt 佳；較新，diffusers 支援與實測待確認 |
| Sana 1.6B | CC-BY-NC | — | — | — | **非商用，不採用** |

（VRAM／下載數字為一般經驗值，實際依精度與量化而異。）

## 3. 三個方案

### A. 推薦免費本機方案：FLUX.1-schnell（Apache-2.0）
- 硬體：NVIDIA 12 GB+ VRAM（16 GB 更順）、RAM 32 GB、磁碟 30 GB。
- 8–12 GB 卡：同一模型改 NF4（bitsandbytes）或 GGUF Q4/Q8 量化，下載 ≈7–12 GB。
- 執行：diffusers in-process（`AutoPipelineForText2Image`），**不需要 ComfyUI**，使用者仍只操作 AI-Studio。
- 速度（參考）：RTX 4070 12 GB 約 5–15 秒/張（1024×576）；RTX 3060 12 GB 約 20–40 秒。
- Prompt：英文最佳 → 需 `image_prompt_en`。

### B. 較低硬體需求 fallback：Stable Diffusion 1.5（OpenRAIL-M）
- 硬體：任何 4 GB+ NVIDIA、或 CPU-only（16 GB RAM，1–4 分/張 @512）。
- 畫質與 prompt 理解明顯較弱，但能證明「真實 AI 圖 → Ken Burns → Preview」鏈路；適合先在低階機器跑通。
- 注意：原 `runwayml/stable-diffusion-v1-5` 已下架，改用社群鏡像 `stable-diffusion-v1-5/stable-diffusion-v1-5`（同權重、同授權）。

### C. 未來付費 fallback（不得連線或消費）
- 任一 PAID image API（例如 FLUX Pro API、Stability API、OpenAI 圖像 API）。本批只放 `PaidImageProviderStub`：`is_available()=False`、`estimate_cost` 回傳 PAID 估價、`generate_image` 直接拒絕；`ApprovalGate` 測試證明無核准不可執行。真正實作需另開 Decision Gate、API key 與 budget 核准。

## 4. Windows 本機執行需求

| 項目 | 需求 |
|---|---|
| Python | 3.11 或 3.12 的獨立 venv（3.13 需 PyTorch ≥ 2.6；若安裝失敗改 3.12） |
| NVIDIA | 驅動 ≥ 550（CUDA 12.x）；`pip install torch --index-url https://download.pytorch.org/whl/cu124`（或 cu126） |
| AMD | Windows 走 `torch-directml`（速度慢、相容性有限）或 WSL2 + ROCm（僅部分卡）；建議視為 CPU-only 等級 |
| CPU-only | 一般 `pip install torch`；只建議 SD 1.5 |
| Python 套件 | `diffusers transformers accelerate safetensors sentencepiece protobuf huggingface_hub`；量化另加 `bitsandbytes`（NF4）或 `gguf` |
| 磁碟 | HF cache 預設在 `%USERPROFILE%\.cache\huggingface`；可用 `HF_HOME` 改到大容量磁碟 |
| 下載 | 人工執行 `huggingface-cli download <model_id>`（FLUX.1-schnell 不需登入；某些模型需同意授權） |

程式端：`SEE_IMAGE_PROVIDER=auto`、`SEE_IMAGE_MODEL_PRESET=flux-schnell|sd15`、`SEE_IMAGE_MODEL_PATH=<已下載資料夾>`（選填）。

## 5. 能力偵測（已實作）
`python -m see.app.cli hardware`（或 Web `/api/hardware`）自動回報：OS、Python、CPU、RAM、磁碟、GPU（nvidia-smi → rocm-smi → Windows CIM → macOS）、VRAM、torch/CUDA/ROCm/MPS/DirectML/diffusers 安裝狀態，並依 `IMAGE_TIERS` 給出 recommended / fallback / cpu_only 與理由。**使用者不需自行研究硬體，只需貼回這個輸出。**

## 6. 下一批（待裁示後）
1. 使用者在 Windows PC 執行 `python -m see.app.cli hardware` 並貼回結果 → 決定方案 A 或 B。
2. 人工下載對應模型（停手條件：下載大型模型需明確同意）。
3. 實作 `image_prompt_en`（Mock 模板）與 negative prompt 預設。
4. 真機跑 `SEE_IMAGE_PROVIDER=auto` 產生 preview，記錄速度與證據。
5. 失敗路徑：diffusers 失敗 → 自動退回 placeholder 並在 UI 顯示原因（已接線）。
