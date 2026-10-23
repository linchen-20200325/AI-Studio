# SESSION_LOG.md — 工作階段紀錄（append-only）

每個完整工作階段一筆，固定欄位：Date / Start SHA / End SHA / Batch / Result / Tests / Decision / Next。不記逐步過程。

---
- Date: 2026-10-22
- Start SHA: (empty repo)
- End SHA: 026206c
- Batch: Batch 1 — Phase 0 憲章、架構、pipeline、CLI、測試、證據
- Result: preview.mp4 成功（47 s，H.264/AAC）；成本 NT$0
- Tests: 38 passed
- Decision: D-001～D-008
- Next: DG-1～DG-4 待裁示

---
- Date: 2026-10-22
- Start SHA: 026206c
- End SHA: ff2b6f9
- Batch: Batch 2 — 裁示 DG-1～DG-4；建立 main；FastAPI 手機友善 Web UI
- Result: UI 貼故事 → Preview → 播放 → 單景修改 → 核准 → Final 跑通；main = 026206c
- Tests: 42 passed
- Decision: D-009、D-010
- Next: DG-5、是否併入 main；edge-tts 需連網驗證

---
- Date: 2026-10-22
- Start SHA: ff2b6f9
- End SHA: e38004d
- Batch: Batch 3 — Conversation Handoff & Crash Recovery 治理制度
- Result: PROJECT_RULES §11；STATE / HANDOFF_PROJECT_AI / HANDOFF_CHATGPT / SESSION_LOG 建立；HANDOFF.md 改為索引
- Tests: 42 passed（未動程式碼）
- Decision: 無新裁示
- Next: 等待下一個功能 Batch；待裁示：併入 main、DG-5、edge-tts 連網驗證

---
- Date: 2026-10-22
- Start SHA: 1e42a81
- End SHA: 24ecbc2
- Batch: Batch 4 — main fast-forward、DG-5（loopback 預設入口）、edge-tts 連網驗證嘗試、repo 實況盤點
- Result: main = 1e42a81 → 再 ff 至 24ecbc2；edge-tts 本容器無法連網（D-012）；repo public、預設分支非 main（D-013）
- Tests: 43 passed
- Decision: D-011、D-012、D-013
- Next: 等待 Web UI Batch 範圍；待裁示 DG-6、DG-7

---
- Date: 2026-10-22
- Start SHA: f39d72f
- End SHA: 5a3e05a
- Batch: Batch 5 — 最小 GitHub Actions CI；DG-6/DG-7 裁示入檔
- Result: ci.yml 兩次 run 皆 success（#1 7cad7f8、#2 5a3e05a）；無 secret、無外部 Provider
- Tests: 43 passed（本機 + CI）
- Decision: D-014、D-015、D-016
- Next: Web UI Batch；DG-7 待使用者手動改 GitHub 設定

---
- Date: 2026-10-22
- Start SHA: 16fd107
- End SHA: 088932a
- Batch: Batch 6 — AI Image Provider Phase 第一批：盤點、硬體偵測、diffusers 骨架、fallback、paid stub
- Result: 未下載模型；`hardware` 命令與 /api/hardware 可用；auto 模式缺權重自動退 placeholder
- Tests: 55 passed
- Decision: D-017；開 DG-8
- Next: 使用者貼回 hardware 輸出 → 選 A/B → 同意下載 → 真機驗證

---
- Date: 2026-10-22
- Start SHA: ec669e7
- End SHA: ca7d286
- Batch: Batch 7 — DG-8 方案 B：SD 1.5 低 VRAM runtime plan、image_prompt_en、模型下載器（需 --yes）、Windows 安裝文件
- Result: 程式端就緒；模型未下載（需使用者手動）；CI cancelled 根因＝apt 卡住→job timeout，已加固（ca7d286 success）
- Tests: 66 passed；CI success
- Decision: D-018、D-019
- Next: 使用者在 Windows 依 AI_IMAGE_SD15_WINDOWS.md §4 操作並貼回 hardware / run 輸出

---
- Date: 2026-10-23
- Start SHA: e220890
- End SHA: 3597e1e
- Batch: Batch 8 — Windows 真機第一次 SD 1.5 執行失敗之 root cause 修復
- Result: root cause = cp950 subprocess 解碼（非 warning）；修 UTF-8 subprocess、fp16 NaN 偵測與 fp32 升級、feature_extractor=None；模型未重下載
- Tests: 73 passed（+7 Windows 回歸）；CI 先因 Azure apt 鏡像慢紅、改 setup-ffmpeg 後因漏列 numpy 紅、補上後 success
- Decision: D-020、D-019 修正二
- Next: 使用者 git pull 重跑並貼回結果

---
- Date: 2026-10-23
- Start SHA: 02fac28
- End SHA: 02fac28（本輪無程式變更；僅 STATE/SESSION_LOG 追查筆記 commit 於其後）
- Batch: Batch 9 前置 — Verification Gate 通過；追查「黑 PNG 卻回報成功」路徑，列出 4 個假設與修法（見 STATE「Batch 9 交接筆記」）
- Result: 未修復；使用者要求換新對話，依 §11.4 收尾
- Tests: 73 passed；CI success @ 02fac28
- Decision: 無
- Next: 新對話依 STATE 筆記執行 Batch 9

---
- Date: 2026-10-23
- Start SHA: 1b0bce5
- End SHA: 63e7855
- Batch: Batch 9 — Windows 真機「純黑 PNG 卻回報成功」root cause 與修復
- Result: 主因＝黑圖被 manifest 當有效快取重用（version 未 bump、不驗內容）；修 image_qa 內容驗證（快取前／生成後／fallback／存檔後）、version 3、VAE dtype cast、evidence（manifest meta／CLI image_evidence／UI image_meta）
- Tests: 83 passed（+10 回歸）；CI 見 STATE
- Decision: D-021
- Next: 使用者 `git pull` 後重跑同一條 run 命令並貼回 `image_evidence`

---
- Date: 2026-10-23
- Start SHA: 8d6ad06
- End SHA: ab91f93
- Batch: Batch 10 — fp32 升級找不到權重（runtime 階梯 vs fp16-only 下載不一致）
- Result: 採方案 B：同一份 fp16 權重以 dtype=float32 載入 upcast（零下載）；pick_variant 依實際檔案決定；dtype= kwarg；VAE 單獨 fp32 載入；階梯跨景延續；evidence +weights_variant/fp32_source/plan_origin
- Tests: 86 passed（+3）；CI 見 STATE
- Decision: D-022
- Next: 使用者 `git pull` 後重跑同一條 run 命令並貼回 `image_evidence`

---
- Date: 2026-10-23
- Start SHA: 11d90c5
- End SHA: ada08f9
- Batch: Batch 11 — fallback 產物被當有效快取／regen 語意
- Result: root cause＝placeholder fallback 產物以首選 provider fingerprint 快取，首選修好後永不重試；修 degraded-cache 規則、Fallback info 穩定、regen 印 evidence；regen 本身語意正確
- Tests: 89 passed（+3）；CI 見 STATE
- Decision: D-023
- Next: 使用者 `git pull` 後重跑同一條 run 命令；scene_001 應自動重試並由 diffusers-sd15 生成

---
- Date: 2026-10-23
- Start SHA: ec8ff77
- End SHA: ec8ff77（本輪無程式變更；文件 checkpoint 另列）
- Batch: Batch 12 — Phase 1 真機收尾、PHASE1_EVIDENCE、BACKLOG 完整盤點、Phase 2 排序
- Result: Phase 1 COMPLETE（五景真 SD 1.5、fp32 upcast、降級快取自動重試、NT$0）；盤點 25 項能力 ✅13 🟡8 ⬜5 🔴1；Phase 2 第一目標建議＝自然中文 TTS
- Tests: 89 passed（未動程式）
- Decision: D-024
- Next: 使用者裁示 Phase 2 方向（停手條件）；可安全換新對話

---
- Date: 2026-10-23
- Start SHA: 1b944aa
- End SHA: 1b944aa（無程式變更；本輪為 governance/docs commit，SHA 見 GitHub main HEAD）
- Batch: Batch 13 — Knowledge Consolidation / Memory Migration / PROJECT_STATE 建立 / Handoff Closeout
- Result: CI 一次紅（setup-ffmpeg 外部 action readme 讀取失敗，非本次 diff）→ ci.yml 改 best-effort + apt fallback；PROJECT_RULES §10 補齊、§12–§14 新增；PROJECT_STATE 建立；STATE→指標；HANDOFF→導航頁；BACKLOG 加 DG-9～DG-12 與標示；DECISIONS 狀態索引＋D-025；README 產品願景；Dry-run 24 題可由 repo 回答
- Tests: 89 passed（未動程式）
- Decision: D-025
- Next: 使用者裁示 DG-9；可安全換新對話
