# STATE.md — 目前狀態快照

> 唯一的「現在在哪」。只寫當下，不寫歷史（歷史在 SESSION_LOG / DECISIONS）。與 GitHub 不一致時以 GitHub 為準並修正本檔。

| 欄位 | 值 |
|---|---|
| Current Phase | Phase 1：AI Image Provider（SD 1.5 已在使用者 Windows 實機安裝並載入成功；第一次執行的 Windows 編碼失敗已修，等重跑驗證） |
| Last Verified Commit | `3597e1e`（分支 `ccr-2968bce1-ym4kkc` 與 `main`；CI success；73 tests passed） |
| Current Branch | `ccr-2968bce1-ym4kkc`（開發）；`main` 與其同步（fast-forward） |
| Open PR | 無 |
| Last Completed Batch | Batch 8：Windows 真機 root cause 修復 + CI 改用 setup-ffmpeg（`3597e1e`） |
| Current Task | Batch 9（未開工）：Windows 真機 SD 1.5 產出純黑 PNG 卻回報成功——追查與修復；追查筆記見本檔「Batch 9 交接筆記」 |
| Current Status | 使用者要求換新對話；工作樹乾淨；可安全換新對話 |
| Blocked By | 無（本容器無 GPU，CUDA 路徑只能靠使用者實機驗證） |
| Next Action | 新對話：先 Verification Gate，再依「Batch 9 交接筆記」逐項驗證假設、修復、加回歸測試、加 evidence 輸出，CI 綠後再請使用者做唯一一次重跑 |
| Cost Used | NT$0（全部 LOCAL_FREE） |
| Paid Provider Approved | 無（budget = 0） |
| Last Updated | 2026-10-23 |

## 待裁示（細節見 BACKLOG）
- 無新裁示；等待使用者實機重跑結果。
- DG-7（殘留）：repo visibility 是否改 Private。

## 實機事實（使用者回報 2026-10-23）
Windows · Python 3.12.10 · GTX 1650 4 GB · torch 2.14.1+cu126 · CUDA 12.6 · diffusers 已裝 · SD 1.5 於 `D:\ai-models\sd15`（2.13 GB，載入成功）· 成本 NT$0。

## Batch 9 交接筆記（2026-10-23，尚未修復，只追查到這裡）
使用者實機事實：GTX 1650 4095 MB、torch 2.14.1+cu126、`RuntimePlan(device=cuda, dtype=float16, low_vram, slicing, cpu_offload, max_side=512, vae_fp32=True)`、CLI 正常結束、`providers.image.name=diffusers-sd15`，但 `scene_001/image.png` 全黑（min=max=mean=0）。

程式路徑追查（以 `02fac28` 程式碼為準，待新對話驗證）：
1. **cache 假設（最可疑）**：`Orchestrator._build_scene` 以 `manifest.valid("image", fingerprint)` 判定重用，只比 fingerprint 與檔案存在，**不檢查內容**。image fingerprint 含 `ProviderInfo.version`，`diffusers_local.py` 自 Batch 7 起為 `"2"`，Batch 8 修 NaN 邏輯時**未 bump**；第一次真機（舊 fp16 路徑）若已把黑圖與 manifest 寫下，第二次就直接重用黑圖、不呼叫新版生成。修法：bump version、manifest 重用前驗證影像內容（全黑／無法解碼即重做）。
2. **`providers.image.name` 不是生成證據**：`FallbackImageProvider.info` 回傳 `active`（第一個可用候選），即使該次實際退回 placeholder 也顯示 `diffusers-sd15`。需在 `ImageResult` 加 `meta`（provider、attempts、final plan、regenerated、elapsed、image stats）並寫入 manifest／CLI 輸出／UI。
3. **`is_numeric_failure()` 只看生成當下 ndarray**：存檔後與快取重用時都沒有再驗；修法：存檔後重開 PNG 驗 stats，黑圖直接刪檔並 raise。
4. **VAE fp32 + UNet fp16 的 dtype 風險**：`pipe.vae.to(float32)` 後，SD1.5 pipeline 把 fp16 latents 直接送進 fp32 VAE 可能 dtype 不匹配而丟例外（→ ProviderError → fallback placeholder，但黑圖非 placeholder，故此點不是本次黑圖主因，但要修）；建議改 `output_type="latent"` 後自行 `latents.to(vae.dtype)` 再 decode，並先檢查 latents 是否 NaN（NaN → 升級整個 pipeline fp32）。
5. 新對話的回歸測試至少：黑既有 artifact 不得當有效 cache；numeric failure 不得留下黑圖；fp32 降級階梯可追蹤（把重試階梯抽成純函式測）。
6. **不要再請使用者重做已完成的診斷**；修好、CI 綠後只請他做一次 `git pull` + `run`。
