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
- End SHA: 1e81668
- Batch: Batch 7 — DG-8 方案 B：SD 1.5 低 VRAM runtime plan、image_prompt_en、模型下載器（需 --yes）、Windows 安裝文件
- Result: 程式端就緒；模型未下載（需使用者手動）；CI cancelled 記錄 D-019
- Tests: 66 passed
- Decision: D-018、D-019
- Next: 使用者在 Windows 依 AI_IMAGE_SD15_WINDOWS.md §4 操作並貼回 hardware / run 輸出
