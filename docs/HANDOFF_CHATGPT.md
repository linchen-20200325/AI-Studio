# HANDOFF_CHATGPT.md — 給治理／協作 AI（ChatGPT 等）的恢復手冊

> 讓新的治理 AI 對話重新查 GitHub 後直接接手，不需要使用者重新解釋專案。本文件不描述「現在在哪」——現況看 `STATE.md` 並與 GitHub 比對。

## 1. 專案目的
`see`：使用者貼入中文文章／故事 → 自動產生影片（劇本 → 分鏡 → 圖片 → 動畫 → 配音 → 音效 → 字幕 → 剪輯 → QA → Preview → 人工核准 → Final）。採階段性 MVP，目前完成 Phase 0（pipeline）與 Phase 0.5（最小 Web UI）。Repo：`linchen-20200325/AI-Studio`（GitHub 上為 public；`main` 為已驗證版本，開發分支 `ccr-2968bce1-ym4kkc`）。

## 2. 使用者核心偏好
- 全程繁體中文（台灣）。
- 「AI 總管」模式：複雜工作由總管拆解、指派虛擬專家；需裁示時主動提供「推薦選項 + 評估理由」。
- 靜默自主巡航：安全、免費、可逆、規格明確的工作不逐步回報；只在需裁示、停手條件、整批完成時回報。
- 回報精簡：SHA、測試、產出、成本、已完成、未完成、下一個 Decision Gate。
- 每批標示 Model / Mode / Minimum Sufficient Effort。
- 程式碼需防禦性設計、向量化；附內部審核（邏輯／邊界／效能）。
- SSOT 原則；每次先讀規則與紀錄。

## 3. 架構原則（PROJECT_RULES.md 為準）
- **Free First**：LOCAL_FREE → FREE_TIER → 低價 PAID → 高價 PAID。PAID 需人工核准，預設 budget = 0。
- **Provider Agnostic**：核心只依賴 LLM / Image / Video / TTS / Audio / LipSync 介面；不綁任何供應商。
- **Compute Agnostic**：`Task` / `Executor` 抽象；NAS=控制/儲存/佇列/UI、GPU PC=運算、Mobile=client、Cloud=optional。
- **Local First AI**：本機可做就本機；Local 失敗不得自動切 PAID。
- **Human Approval Gate**：DRAFT → PREVIEW → APPROVED → FINAL；APPROVED/FINAL 只能由人工寫入；改一景不重做其他景。
- 另有：結構化 schema fail-closed、成本標記、禁 commit secrets／媒體／權重、第三方碼先查 License、§11 交接與恢復制度。

## 4. 已完成 Phase
- Phase 0：中文文字 → 劇本 → 分鏡 → placeholder 圖 + Ken Burns + espeak 旁白 + 字幕 → FFmpeg → `preview.mp4`（證據：`docs/PHASE0_EVIDENCE.md`）。
- Phase 0.5：FastAPI 手機友善 Web UI（貼故事 → Preview → 播放 → 單景修改／重做 → 核准 → Final）。
- 治理：Conversation Handoff & Crash Recovery 制度（PROJECT_RULES §11）；最小 CI。
- AI Image Phase 第一批：盤點 + 硬體偵測 + Provider 骨架（未下載模型，D-017）。

## 5. Current Phase
看 `docs/STATE.md`。

## 6. 尚待客戶裁示
看 `docs/STATE.md`「待裁示」與 `docs/BACKLOG.md` Decision Gates。已裁示的項目記錄在 `docs/DECISIONS.md`（D-009 起）。

## 7. GitHub 驗證規則（Verification Gate）
在提供「下一步、Project AI 提示語、完成度判斷、PR 合併建議、架構重大裁示」之前，**必須先獨立重新查 GitHub 最新實況**：
1. `main` HEAD 與開發分支 HEAD 的 SHA、最近 commits。
2. open/draft PR 與 CI 狀態：Actions workflow `ci.yml` 在該 SHA 的 conclusion 必須為 success。
3. `docs/STATE.md` 內容是否與上述一致；`docs/SESSION_LOG.md` 最後一筆的 End SHA。
4. 測試數與結果以 commit 內 `tests/` 與最近回報為準；有疑慮要求 Project AI 重跑。
不得只依 Claude 的回報或 HANDOFF 文件下判斷。文件與 GitHub 不一致 → GitHub 為準，先要求修正文件。

## 8. 對 Project AI 的治理方式
- 指派工作時給：目標、範圍邊界（明確列「不要做」）、停手條件、回報格式、Model / Mode / Effort。
- 要求 Project AI 開工先跑 Recovery Protocol（§11.5），收工跑 End Protocol（§11.4）。
- 每個 Batch 單一目標；超過一小批的工作要求 checkpoint commit。
- 審核 Project AI 回報時核對：SHA 存在於 GitHub、測試數合理、證據檔在 repo、無 secrets／媒體進 Git。
- 需要裁示時，要求 Project AI 給「推薦選項 + 評估理由」，由使用者裁示後記入 DECISIONS。

## 9. 下一個 Decision Gate
看 `docs/STATE.md`「待裁示」。
