# STATE.md — 目前狀態快照

> 唯一的「現在在哪」。只寫當下，不寫歷史（歷史在 SESSION_LOG / DECISIONS）。與 GitHub 不一致時以 GitHub 為準並修正本檔。

| 欄位 | 值 |
|---|---|
| Current Phase | Phase 1：AI Image Provider（SD 1.5 方案程式端完成；等使用者實機安裝與下載） |
| Last Verified Commit | `1e81668`（分支 `ccr-2968bce1-ym4kkc` 與 `main`；66 tests passed；CI 見 Actions） |
| Current Branch | `ccr-2968bce1-ym4kkc`（開發）；`main` 與其同步（fast-forward） |
| Open PR | 無 |
| Last Completed Batch | Batch 7：SD 1.5 低 VRAM provider、image_prompt_en、下載器、Windows 文件（`1e81668`） |
| Current Task | 等使用者在 Windows 執行 `docs/AI_IMAGE_SD15_WINDOWS.md` §4 並貼回結果 |
| Current Status | 閒置；可安全換新對話 |
| Blocked By | 使用者手動：安裝 torch/diffusers、下載 SD 1.5（≈2.2 GB）、真機跑 auto |
| Next Action | 收到真機結果 → 記證據（PHASE 文件）→ 修實機問題。期間可自主：UI 顯示 image provider/fallback 原因、Scene 卡 image_prompt_en 欄 |
| Cost Used | NT$0（全部 LOCAL_FREE） |
| Paid Provider Approved | 無（budget = 0） |
| Last Updated | 2026-10-22 |

## 待裁示（細節見 BACKLOG）
- 無新裁示；等待使用者實機操作結果。
- DG-7（殘留）：repo visibility 是否改 Private。
- CI：`ec669e7` 兩個 run 為 cancelled（D-019），請在 Actions 頁 Re-run 或待下一個 push。
