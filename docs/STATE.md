# STATE.md — 目前狀態快照

> 唯一的「現在在哪」。只寫當下，不寫歷史（歷史在 SESSION_LOG / DECISIONS）。與 GitHub 不一致時以 GitHub 為準並修正本檔。

| 欄位 | 值 |
|---|---|
| Current Phase | Phase 1：AI Image Provider（SD 1.5 已在 Windows 實機載入成功；SD 1.5 fp32 upcast 已真機成功（Scene 002–005）；fallback 快取不再卡住（D-023），等第五次重跑讓 Scene 001 也由 diffusers 生成） |
| Last Verified Commit | `ada08f9`（分支 `ccr-2968bce1-ym4kkc`；本機 89 passed；CI 見 Actions） |
| Current Branch | `ccr-2968bce1-ym4kkc`（開發）；`main` 與其同步（fast-forward） |
| Open PR | 無 |
| Last Completed Batch | Batch 11：fallback 產物不得當有效快取／Fallback info 穩定／regen evidence（`ada08f9`，D-023） |
| Current Task | 等使用者 `git pull` 後重跑 `python -m see.app.cli run examples\story_short.txt --project-id sd15test` 並貼回 `image_evidence` |
| Current Status | 閒置；可安全換新對話 |
| Blocked By | 使用者實機重跑（本容器無 GPU） |
| Next Action | 收到 `image_evidence` → 記入證據；若 `generated_by=placeholder-image` 看 `fallback_from`；五景皆 `generated_by=diffusers-sd15` 才算 Phase 1 真機完成（scene_001 預期 reason=degraded artifact…）；仍 placeholder 看 `fallback_from` |
| Cost Used | NT$0（全部 LOCAL_FREE） |
| Paid Provider Approved | 無（budget = 0） |
| Last Updated | 2026-10-23 |

## 待裁示（細節見 BACKLOG）
- 無新裁示；等待使用者實機重跑結果。
- DG-7（殘留）：repo visibility 是否改 Private。

## 實機事實（使用者回報 2026-10-23）
Windows · Python 3.12.10 · GTX 1650 4 GB · torch 2.14.1+cu126 · CUDA 12.6 · diffusers 已裝 · SD 1.5 於 `D:\ai-models\sd15`（2.13 GB，載入成功）· 成本 NT$0。
第三次執行（Batch 9 程式）：黑圖 QA 生效；fp16+VAE fp32 仍 NaN；fp32 升級因只有 fp16 檔失敗 → placeholder（已修 D-022）。模型資料夾只有 `*.fp16.safetensors`（unet/vae/text_encoder）。
第四次執行（Batch 10 程式）：Scene 002–005 `generated_by=diffusers-sd15, final_dtype=float32, fallback=false`（真機成功）；Scene 001 仍舊 placeholder 快取（D-023 已修）。
