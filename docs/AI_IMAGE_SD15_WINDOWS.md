# AI_IMAGE_SD15_WINDOWS.md — 方案 B：Stable Diffusion 1.5 在 Windows + GTX 1650 4 GB

DG-8 裁示：採 SD 1.5（CreativeML OpenRAIL-M）。本文件是使用者在 Windows 實機要做的事；程式端已就緒。

## 1. 實機盤點（2026-10-22 使用者回報）
Windows AMD64 · Python 3.12.10 · 16 核 · RAM 64 GB · 磁碟 2.7 TB · **GTX 1650 4 GB**（Turing，CUDA 支援）· torch／CUDA／diffusers 未安裝。

## 2. 低 VRAM 推理設定（程式自動套用，`make_runtime_plan`）
VRAM ≤ 6.5 GB 判定為 low_vram：fp16、attention slicing、VAE slicing + tiling、model CPU offload、生成長邊 ≤ 512（16:9 → 512×288，再放大到輸出尺寸由 Ken Burns 使用）。OOM 時自動降 128 px 重試一次（下限 384），仍失敗才退回 placeholder。SD 1.5 fp16 UNet ≈1.7 GB + VAE/文字編碼器 ≈0.4 GB，CPU offload 下 4 GB 卡預期峰值 ≈2.5–3 GB。
預估速度：GTX 1650 約 15–40 秒／張（512×288、25 步）；5 景約 2–3 分鐘。

## 3. 下載內容（≈2.2 GB，只抓需要的檔）
`stable-diffusion-v1-5/stable-diffusion-v1-5` 的 fp16 權重：`unet`、`vae`、`text_encoder` 各一個 `.fp16.safetensors` + tokenizer/scheduler/config。**不下載 safety_checker**（省 600 MB，載入時 `safety_checker=None`）。
存放：`SEE_MODELS_DIR`（預設 `./models`，已 `.gitignore`；建議改到大容量磁碟，例如 `D:\ai-models`）。下載器會在該資料夾寫入 `.gitignore` 雙重保險。

## 4. 使用者要手動執行的步驟（每行一步，在專案根目錄）
```
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install torch --index-url https://download.pytorch.org/whl/cu126
pip install diffusers transformers accelerate safetensors huggingface_hub
set SEE_MODELS_DIR=D:\ai-models
python -m see.app.cli image-download --preset sd15 --yes
python -m see.app.cli hardware
set SEE_IMAGE_PROVIDER=auto
python -m see.app.cli run examples\story_short.txt --project-id sd15test
```
`python -m see.app.cli image-setup` 會依偵測結果印出同樣的步驟。`hardware` 必須顯示 `torch installed=True cuda=True diffusers=True`。

## 5. 驗收
- `run` 輸出的 `providers.image.name` 為 `diffusers-sd15`（不是 placeholder）。
- `workspace/projects/sd15test/scenes/scene_001/image.png` 為 AI 圖；preview.mp4 可播。
- 把 `hardware`、`run` 輸出與一張 image.png 縮圖貼回 → 記入 PHASE 證據。

## 6. 失敗處理
- `torch.cuda.is_available()` 為 False：NVIDIA 驅動版本過舊（需 ≥ 550）或裝到 CPU 版 torch；重裝 cu126 wheel。
- OOM 仍發生：設 `SEE_IMAGE_MODEL_PRESET=sd15` 不變，降低輸出比例（1:1 比 16:9 省）；或關閉其他佔 VRAM 程式。
- 任何失敗 pipeline 都會退回 placeholder，Web UI `/api/health` 的 `image_skipped` 會顯示原因。
