# PROJECT_STATE.md — 目前仍有效的專案狀態（ChatGPT + Project AI 共用快照）

## ⛳ 最終交接 checkpoint（2026-10-23 封存；以 GitHub main HEAD 為準）
- 最後驗證 main：`c716b5d`（CI success；159 passed、1 skipped）＋本封存文件 commit。開發分支 `ccr-297bf146-zrrlk1`。
- 已完成：Phase 0／0.5／1；Phase 2 進行中：Kokoro TTS（D-027／D-029，真機 validated）、Voice Selection／Character Voice（`zm_010`＝目前使用者偏好候選，非永久鎖定，DG-14）、BGM/SFX＋ducking（SFX 人工聽感未驗）、Style Profile、Character Consistency foundation（僅 prompt 錨點，無 IP-Adapter/LoRA）、Lip-sync 介面（無實際模型）、checkpoint 型錄／下載驗證／single-file 載入／clip-skip 相容（D-039／D-040；**不是** Model Router，Router 未實作）。
- E2-5：MeinaMix V12 已下載驗證、真機成功；近景（fit 512×288）主觀 OK。Base SD1.5 native 近景：「眼睛很怪異」；與舊 MeinaMix 那張生成條件不同（not_comparable，D-044）→ **尚無受控比較結論**；MeinaMix native 重跑待做。**未正式採用、未鎖畫風、commercial_cleared=false（所有 checkpoint）**。
- `fair_comparison=false`：metadata 定義問題（已更名 `baseline_condition`）。**實機 `style-compare`（D-044）＝not_comparable**：舊 MeinaMix 近景 evidence 實為 **fit 512×288**（無 crop），Base 為 native 768×512 → 舊比較不是受控比較；人工評語僅保留為 single-user subjective observation。
- CyberRealistic：**尚未下載、尚未真機驗證**；upstream lineage 未釐清。
- production default **未變**（gen_policy=fit、base SD1.5、預設 style）。
- 本機：Windows、GTX 1650 4 GB（fp16 會 NaN → 自動 float32）、SD1.5 於 `D:\ai-models\sd15`、checkpoints 於 `SEE_MODELS_DIR\checkpoints\<id>\`（永不進 Git）。
- **下一唯一安全接手點**：Verification Gate →（Windows 一次一條）`python -m see.app.cli style-test --style anime --case girl_portrait_closeup --gen-policy native --checkpoint meinamix_v12 --scheduler dpmpp_2m_karras`（產出 `anime_seed1234_girl_portrait_closeup_native_ckpt-meinamix_v12_sched-dpmpp_2m_karras`）→ 再 `style-compare anime_seed1234_girl_portrait_closeup_native_sched-dpmpp_2m_karras anime_seed1234_girl_portrait_closeup_native_ckpt-meinamix_v12_sched-dpmpp_2m_karras`，預期只差 model＋clip_skip（model_preset_level）→ 才重新判斷 DG-23。CyberRealistic 暫停直到此比較完成。
- 禁止直接做：付費／API key、下載未核准模型、改 production default、Model Router、DG-19 UI、lip-sync 模型、刪 SD1.5、pickle/ckpt/bin、LoRA 訓練、把 MeinaMix 當商用。


> 只寫「現在仍有效、新 AI 現在需要知道」的事。歷史 → `SESSION_LOG.md`；為什麼 → `DECISIONS.md`；未完成 → `BACKLOG.md`；驗收證據 → `*_EVIDENCE.md`；導航 → `HANDOFF.md`。
> 與 GitHub 實況不一致時以 GitHub 為準並修正本檔。SHA：See GitHub main HEAD; this file is a state snapshot and does not require self-referential SHA churn.

## Project
| 欄位 | 值 |
|---|---|
| Project | `see`（repo `linchen-20200325/AI-Studio`；預設分支 `main`；開發分支 `ccr-297bf146-zrrlk1`，`main` 只以 fast-forward 指向已驗證 SHA） |
| Current Phase | Phase 1 COMPLETE（D-024）。**Phase 2 進行中**：第一目標（自然中文 TTS）**完成**＝Kokoro-82M v1.1-zh 正式採用為目前 LOCAL_FREE provider（D-029）；第二目標待裁示 |
| Product visual direction | **P1＝日系動畫＋AI 真人／寫實＋電影感；P2＝3D；P3＝兒童繪本等（D-034；README canonical）。兒童繪本不是主要方向** |
| Current Status | Batch 24：native A/B 完成（D-036）——H1 證實；anime 在 Base SD1.5 style FAIL → 停止調 Base SD1.5；**E2-5 進行中（D-039～D-043）**：MeinaMix 人物近景主觀 OK（不鎖定、非商用許可）；正式需求「事後可調整風格」入 PROJECT_RULES §15；base SD1.5 native 近景完成；與舊 MeinaMix（fit）not_comparable（D-044）→ MeinaMix native 重跑待做；CyberRealistic 等客戶下一步；SAFE_TO_HANDOFF = **YES** |
| Cost Used | NT$0（全部 LOCAL_FREE；budget = 0；無 PAID 核准） |
| Last Updated | 2026-10-23（Batch 21：D-032 foundation） |

## Current GitHub checkpoint
- Phase 1 真機驗收版本：functional `ada08f9`／checkpoint `ec8ff77`（D-023）。Phase 1 收尾 docs：`1b944aa`（D-024）。之後只有 governance／文件 commit。
- CI：GitHub Actions `ci.yml`（push to `main` / `ccr-*`）；最近 run 皆 success。Tests：155 passed、1 skipped（espeak 缺時 skip）。
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
| Audio（BGM/SFX） | 預設 `null-audio`；`procedural-audio`（D-031，`--audio procedural`） | **Real（BGM／ducking 真機 OK，D-032）**；SFX 真機未驗證；預設維持 null（待產品 UI） |
| Style | `Project.style_id`；內建 6 個 Style Profile（D-032） | **Partial**：default 只有**技術**驗證（Phase 1 未驗場景）；picture_book：fit 512×288 全 FAIL（D-035）、native scene／style PASS（D-036）；anime（native）scene PASS／style FAIL → 停止以 Base SD1.5 調 P1 風格（D-036） |
| Character consistency | `CharacterAppearance` 文字錨點＋結構化 refs（D-032） | **Partial**：prompt 層；無 IP-Adapter／LoRA；未真機驗收 |
| LipSync | `null-lipsync`（介面＋opt-in pipeline stage，D-032） | **Null**（無真實模型；DG-18 C） |
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
- DG-16 **已裁示 A（D-031）**：Audio Layer。
- DG-17：真機聽感 OK（D-032）；**BGM 預設開啟延後**到完整產品流程／UI（維持 null）。
- DG-18 **已裁示 A（D-033）**：Style 真機驗收進行中（E2-4；順序 D-034）。
- **DG-23（D-043／D-044，暫停）**：舊比較 not_comparable（gen_policy fit vs native）→ 先跑 MeinaMix native 重跑＋style-compare，結果為 model_preset_level 後才請客戶裁示是否接受整包比較。
- DG-21（待 native A/B）：`gen_policy=native` 是否成為預設（既有 image fingerprint 全失效重生、每張耗時增加）。
- **DG-20（已提出，等待裁示）**：見 `DG20_IMAGE_MODEL_RESEARCH.md`。舊選項描述：：A SD1.5 足夠→角色一致性驗證｜B 明顯不足→研究更適合 anime／AI 真人的 LOCAL_FREE 模型｜C 依視覺路線分模型／provider。裁示前不下載、不導 IP-Adapter／LoRA、不付費、不做 Lip-sync 模型、不做 DG-19 UI。
- DG-7（殘留，使用者手動 GitHub 設定）：預設分支改 `main`（實況已是 main 與 ccr 同步）、repo 改 Private。

## Current next action
Windows（一次一條）：① `python -m see.app.cli style-test --style anime --case girl_portrait_closeup --gen-policy native --checkpoint meinamix_v12 --scheduler dpmpp_2m_karras` ② `style-compare anime_seed1234_girl_portrait_closeup_native_sched-dpmpp_2m_karras anime_seed1234_girl_portrait_closeup_native_ckpt-meinamix_v12_sched-dpmpp_2m_karras` → 重新判斷 DG-23。CyberRealistic 暫停（不下載、不驗證）。

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
