# PROJECT_STATE.md — 目前仍有效的專案狀態（ChatGPT + Project AI 共用快照）

> 只寫「現在仍有效、新 AI 現在需要知道」的事。歷史 → `SESSION_LOG.md`；為什麼 → `DECISIONS.md`；未完成 → `BACKLOG.md`；驗收證據 → `*_EVIDENCE.md`；導航 → `HANDOFF.md`。
> 與 GitHub 實況不一致時以 GitHub 為準並修正本檔。SHA：See GitHub main HEAD; this file is a state snapshot and does not require self-referential SHA churn.

## Project
| 欄位 | 值 |
|---|---|
| Project | `see`（repo `linchen-20200325/AI-Studio`；預設分支 `main`；開發分支 `ccr-2968bce1-ym4kkc`，`main` 只以 fast-forward 指向已驗證 SHA） |
| Current Phase | Phase 1 COMPLETE（D-024）。**Phase 2 進行中**：第一目標（自然中文 TTS）**完成**＝Kokoro-82M v1.1-zh 正式採用為目前 LOCAL_FREE provider（D-029）；第二目標待裁示 |
| Current Status | Batch 18（D-029 入庫）完成；工作樹乾淨；無待做 Windows 步驟；SAFE_TO_HANDOFF = **YES** |
| Cost Used | NT$0（全部 LOCAL_FREE；budget = 0；無 PAID 核准） |
| Last Updated | 2026-10-23（Batch 18：DG-13=A，D-029） |

## Current GitHub checkpoint
- Phase 1 真機驗收版本：functional `ada08f9`／checkpoint `ec8ff77`（D-023）。Phase 1 收尾 docs：`1b944aa`（D-024）。之後只有 governance／文件 commit。
- CI：GitHub Actions `ci.yml`（push to `main` / `ccr-*`）；最近 run 皆 success。Tests：100 passed、1 skipped（espeak 缺時 skip）。
- Open / draft PR：無（流程不開 PR；開發分支驗證後 fast-forward `main`）。

## Current validated environment（last known validated snapshot，非永久硬體假設）
來源：使用者 Windows 真機回報 2026-10-23（`PHASE1_EVIDENCE.md`、D-020～D-023）。版本號為使用者回報值，repo 內無自動量測。
- Windows · Python 3.12.10 · NVIDIA GeForce GTX 1650（VRAM 4095 MB）· RAM ≈ 65 GB · torch 2.14.1+cu126 · CUDA 12.6 · diffusers 0.41.0 · transformers 5.20.2 · ffmpeg/ffprobe 可用。
- SD 1.5 權重：`D:\ai-models\sd15`，≈2.13 GB，**只有 fp16 variant**（`unet/vae/text_encoder/*.fp16.safetensors`，無 safety_checker）。
- 環境變數（非 secret）：`SEE_MODELS_DIR=D:\ai-models`、`SEE_IMAGE_PROVIDER=auto`；專案使用 `.venv`。
- GTX 1650 限制：fp16 推理出 NaN/黑圖 → 自動升 float32（以 fp16 檔 upcast 載入，不另下載）；4 GB 以 `enable_model_cpu_offload` + slicing + max_side 512 執行；OOM 階梯會降到 384（真機未發生 OOM）。每個程序第一景會先失敗一次 fp16 再升 fp32（BACKLOG 效能項）。
- 本容器（Project AI 雲端環境）無 GPU：CUDA 路徑只能靠使用者 Windows 真機驗證。

## Current working providers（Real / Partial / Mock / Null / Silent / Placeholder；介面存在 ≠ 完成）
| 介面 | 預設／可用實作 | 等級 |
|---|---|---|
| LLM | `MockLLMProvider`（規則式切 beat、模板 image_prompt_en） | **Mock**（真 LLM 規劃未做；Ollama 暫緩 DG-2） |
| Image | `diffusers-sd15`（LOCAL_FREE，真機驗證）→ fallback `placeholder-image`；`paid-stub` 永遠被 ApprovalGate 擋 | **Real**（SD 1.5）；placeholder 只是 fallback |
| Video | `KenBurnsVideoProvider`（ffmpeg zoompan 靜態圖運鏡） | **Partial**（非真正 image-to-video） |
| TTS | `auto` → **kokoro**（**D-029 正式採用**；E2-1／E2-2 真機驗證；CPU；voice 由 `scene.voice`／`--voice`／`SEE_TTS_DEFAULT_VOICE` 指定，程式預設未鎖 zm_010）→ espeak-ng → silent；`edge-tts` 不採用（D-014） | **Real**（provider-agnostic 保留；永久預設 voice 待 DG-14） |
| Audio（BGM/SFX） | `null-audio` | **Null** |
| LipSync | `null-lipsync` | **Null** |
| Subtitle／Timeline／Render | 確定性 SRT、燒錄、xfade、preview/final.mp4 | **Real** |
| Web UI | FastAPI 單頁（貼文→Preview→單景修改／重做→核准→Final），限可信任區網（D-011） | **Real**（缺 `image_prompt_en` 欄、每景進度、專案刪除） |

## Current Phase completion
Phase 0（pipeline + Web UI）：證據 `PHASE0_EVIDENCE.md`。Phase 1（SD 1.5 真機五景 `generated_by=diffusers-sd15`、無黑圖、無 placeholder、fp16→fp32 upcast、降級快取自動重試、NT$0）：證據 `PHASE1_EVIDENCE.md`，裁示 D-024。

## Current blockers
- 無 blocker。

## Current Decision Gate（現在正等待的裁示）
- DG-9 **已裁示（D-027）**：Kokoro-82M v1.1-zh 為候選，Candidate Validation Approval（非最終採用）；授權下載 ≈330 MB 做真機驗證。**尚未下載。**
- DG-13 **已裁示 A（D-029）**。
- 開放、非阻塞：DG-14 永久預設 voice（zm_010 僅目前人耳偏好候選）；DG-15 Voice Selector UI；DG-10 LLM／DG-11 Video／DG-12 Queue。
- **DG-16（下一個需裁示）**：Phase 2 第二目標方向（BACKLOG Phase 2 排序：BGM/SFX → LLM 規劃）。
- DG-7（殘留，使用者手動 GitHub 設定）：預設分支改 `main`（實況已是 main 與 ccr 同步）、repo 改 Private。

## Current next action
Batch 19（可自主，Medium）：Voice Selection 非 UI 部分——角色（character）→ voice／語速保存、試聽 API（單句合成、不進 manifest）、per-scene 語速；不動 SD 1.5、不鎖預設 voice、不做 UI（DG-15）。之後需裁示 DG-16。其他可自主：evidence 擴充到 clip、QA 規則、`image_prompt_en` UI 欄、GTX 16xx 直起 fp32。

## Current external / manual setup（已由使用者完成且仍有效；不含 secret）
- Windows：`.venv`、torch cu126、diffusers/transformers/accelerate/safetensors/huggingface_hub 已安裝（validated）。
- SD 1.5 fp16 權重已下載至 `D:\ai-models\sd15`（validated；`image-download --yes` 為人工步驟）。
- Kokoro v1.1-zh 權重已下載至 `SEE_MODELS_DIR\kokoro-v1_1-zh`（329.3 MB，revision `01e7505b…`，4 voices；validated E2-1；`tts-download --yes` 為人工步驟）。`kokoro`／`misaki[zh]` 已 pip 安裝。
- GitHub：repo public、Actions 啟用（validated）；DG-7 Private 未做（optional，待使用者）。
- 無任何 API key／OAuth／付費服務（not configured，也不需要）。

## Current Windows validation status
- 仍有效結論：GTX 1650 SD 1.5 fp32 路徑五景成功（2026-10-23，`ec8ff77`）。
- 已完成：Kokoro E2-1、E2-2（五景 pipeline 與 SD 1.5 共存、RTF ≈0.30 CPU）→ D-029 採用。下一個需真機事項：無。
- Windows 操作規則：一次只給一個指令，等結果再給下一個（PROJECT_RULES §14）。
