# STATE.md — 目前狀態快照

> 唯一的「現在在哪」。只寫當下，不寫歷史（歷史在 SESSION_LOG / DECISIONS）。與 GitHub 不一致時以 GitHub 為準並修正本檔。

| 欄位 | 值 |
|---|---|
| Current Phase | **Phase 1 COMPLETE**（SD 1.5 本機生圖，GTX 1650 真機五景驗收，D-024）；Phase 2 方向待裁示 |
| Last Verified Commit | `ada08f9`（functional）／`ec8ff77`（checkpoint，真機驗收版本；CI success；89 tests passed） |
| Current Branch | `ccr-2968bce1-ym4kkc`（開發）；`main` 與其同步（fast-forward） |
| Open PR | 無 |
| Last Completed Batch | Batch 12：Phase 1 收尾、PHASE1_EVIDENCE、BACKLOG 盤點、Phase 2 排序（文件 only） |
| Current Task | 無進行中功能；等使用者裁示 Phase 2 第一目標（BACKLOG「Phase 2 建議」） |
| Current Status | 閒置；工作樹乾淨；可安全換新對話 |
| Blocked By | Phase 2 方向裁示（停手條件：新模型下載／provider 選擇） |
| Next Action | 使用者選 Phase 2 目標 → 新對話開 Batch 13；期間可自主：`image_prompt_en` UI 欄、evidence 擴充到 TTS/clip、QA 規則（不下載模型） |
| Cost Used | NT$0（全部 LOCAL_FREE） |
| Paid Provider Approved | 無（budget = 0） |
| Last Updated | 2026-10-23 |

## 待裁示（細節見 BACKLOG）
- Phase 2 第一目標（建議：自然中文 TTS，LOCAL_FREE；候選模型下載需同意）。
- DG-7（殘留）：repo visibility 是否改 Private。

## 實機事實（使用者回報 2026-10-23）
Windows · Python 3.12.10 · GTX 1650 4 GB · torch 2.14.1+cu126 · CUDA 12.6 · diffusers 已裝 · SD 1.5 於 `D:\ai-models\sd15`（2.13 GB，載入成功）· 成本 NT$0。
第三次執行（Batch 9 程式）：黑圖 QA 生效；fp16+VAE fp32 仍 NaN；fp32 升級因只有 fp16 檔失敗 → placeholder（已修 D-022）。模型資料夾只有 `*.fp16.safetensors`（unet/vae/text_encoder）。
第四次執行（Batch 10 程式）：Scene 002–005 `generated_by=diffusers-sd15, final_dtype=float32, fallback=false`（真機成功）；Scene 001 仍舊 placeholder 快取（D-023 已修）。
第五次執行（`ec8ff77`）：Scene 001 自動淘汰降級快取並由 diffusers-sd15 fp32 生成；五景皆真 SD 1.5；Phase 1 驗收通過（PHASE1_EVIDENCE.md）。
