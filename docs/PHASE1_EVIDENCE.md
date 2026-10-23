# PHASE1_EVIDENCE.md — Phase 1（AI Image Provider：SD 1.5 本機生圖）真機證據

日期：2026-10-23。實機：Windows、Python 3.12.10、NVIDIA GeForce GTX 1650（4095 MB）、torch 2.14.1+cu126、CUDA 12.6、diffusers 0.41.0、transformers 5.20.2（版本為使用者回報值）、RAM ≈ 65 GB、SD 1.5 fp16 權重於 `D:\ai-models\sd15`（2.13 GB）。全程 LOCAL_FREE，實際成本 NT$0。程式版本：checkpoint `ec8ff77`（functional `ada08f9`）。

## 1. 命令（使用者執行，未 regen、未手動刪任何檔案）
```
python -m see.app.cli run examples\story_short.txt --project-id sd15test
```

## 2. 每景 image_evidence（使用者回報）
| Scene | 動作 | generated_by | final_dtype | vae_fp32 | numeric_downgrade | oom | fallback | is_black / is_flat |
|---|---|---|---|---|---|---|---|---|
| 001 | `cached artifact rejected: degraded artifact from fallback provider placeholder-image; preferred diffusers-sd15 is available` → rebuilt image + clip；reused narration + subtitle | diffusers-sd15 | float32 | true | true | false | false | false / false |
| 002–005 | reused（Batch 10 真機生成） | diffusers-sd15 | float32 | — | — | — | false | false / false |

五景皆由真正 SD 1.5 生成，無 placeholder、無黑圖。

## 3. 已證明的完整路徑
1. GTX 1650 / CUDA 可用 → 2. fp16 + VAE fp32 首次嘗試 → 3. 偵測 numeric failure（NaN/黑）→ 4. 自動升級 float32 → 5. 以既有 fp16 權重在載入時 upcast（**不需額外下載 fp32 模型**）→ 6. 真正 SD 1.5 成功產圖 → 7. 圖片 QA 通過（image_qa）→ 8. 降級 fallback 快取在首選 provider 恢復後自動淘汰（D-023）→ 9. 依賴的 clip 跟著重建 → 10. 未受影響景正確 reuse → 11. 同程序內後續景沿用已證明的 fp32 plan → 12. NT$0。

## 4. Preview
status=PREVIEW · scenes=5 · 約 42.4 s · 1280×720 · has_video=true · has_audio=true · image provider=diffusers-sd15 · cost=NT$0。

## 5. 對應修正紀錄
D-020（cp950 subprocess、NaN 偵測）→ D-021（黑圖快取／內容驗證／evidence）→ D-022（fp32 upcast、variant 一致）→ D-023（降級快取自動重試、Fallback info 穩定）。測試：89 passed；CI success on `ec8ff77`。

## 6. 已知限制（非 Phase 1 完成條件）
- GTX 1650 每景需先跑一次 fp16 失敗再升 fp32（每個程序一次）；可改由 hardware 偵測直接起 fp32（BACKLOG）。
- 旁白仍為 espeak／silent；BGM/SFX、lipsync、真正 video motion 皆未做（見 BACKLOG 盤點）。
