# STATE.md — 目前狀態快照

> 唯一的「現在在哪」。只寫當下，不寫歷史（歷史在 SESSION_LOG / DECISIONS）。與 GitHub 不一致時以 GitHub 為準並修正本檔。

| 欄位 | 值 |
|---|---|
| Current Phase | Phase 1 啟動：AI Image Provider（盤點＋骨架完成，模型未下載） |
| Last Verified Commit | `088932a`（分支 `ccr-2968bce1-ym4kkc` 與 `main`；55 tests passed；CI 見 Actions） |
| Current Branch | `ccr-2968bce1-ym4kkc`（開發）；`main` 與其同步（fast-forward） |
| Open PR | 無 |
| Last Completed Batch | Batch 6：AI Image Provider 盤點、硬體偵測、Provider 骨架（`088932a`） |
| Current Task | 無；等待 DG-8（使用者貼回 `python -m see.app.cli hardware` 結果並同意模型下載） |
| Current Status | 閒置；可安全換新對話 |
| Blocked By | 無 |
| Next Action | DG-8 裁示後：人工下載模型 → `image_prompt_en` → 真機 auto 生圖驗證。期間可自主：image_prompt_en Mock 模板、UI 顯示 provider/fallback 原因 |
| Cost Used | NT$0（全部 LOCAL_FREE） |
| Paid Provider Approved | 無（budget = 0） |
| Last Updated | 2026-10-22 |

## 待裁示（細節見 BACKLOG）
- DG-8：AI Image 方案 A（FLUX.1-schnell，12GB+ VRAM）或 B（SD 1.5，4GB VRAM／CPU）；需 Windows 端 `python -m see.app.cli hardware` 輸出 + 同意下載模型。
- DG-7（殘留）：repo visibility 是否改 Private（預設分支已改 main）。
