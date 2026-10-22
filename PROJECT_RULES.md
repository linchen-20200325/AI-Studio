# PROJECT_RULES.md — see 專案憲章

本文件是永久規則。任何 Phase、任何貢獻者（人或 AI agent）都必須遵守。
修改本文件需要人工核准並在 `docs/DECISIONS.md` 留下紀錄。

---

## 1. Free First（免費優先）

選擇任何 Provider / 服務時，順序固定：

1. 免費本機方案（`LOCAL_FREE`）
2. 免費額度（`FREE_TIER`）
3. 低成本服務（`PAID`，低價）
4. 高品質付費服務（`PAID`，高價）

**任何 `PAID` Provider 不得自行執行。** 執行前必須提出：

- Provider
- Model
- 工作量（units，例如秒數／張數／tokens）
- 預估費用（含幣別）
- 是否已取得人工核准（`Approval` 紀錄）

預設每個 Project：`budget = 0`。
系統層級由 `see/core/approval.py` 的 `ApprovalGate` 強制執行：PAID 且無對應 Approval → 拒絕執行（raise），不是警告。

## 2. Provider Agnostic（供應商中立）

核心流程（`see/pipeline/`、`see/render/`、`see/models/`）不得直接 import 或綁定：
Claude、OpenAI、Kling、Veo、Wan、LTX、ElevenLabs、HeyGen 或任何特定供應商。

一律透過 `see/providers/base.py` 的介面：

- `LLMProvider`
- `ImageProvider`
- `VideoProvider`
- `TTSProvider`
- `AudioProvider`
- `LipSyncProvider`

更換 Provider 只能透過 `ProviderRegistry` 設定，不得要求重寫核心 Workflow。
每個 Provider 必須提供 `ProviderInfo`（name、kind、cost_tier、model、requires_network、requires_api_key）。

## 3. Compute Agnostic（運算位置中立）

工作不得假定一定執行於 NAS、PC、GPU PC、Cloud GPU 或 API。
所有需要運算的工作都包成 `Task`，透過 `see/workers/base.py` 的 `Executor` 抽象層執行。

預計拓樸（Phase 0 全部單機，但架構不得阻止拆分）：

| 角色 | 節點 |
|---|---|
| Controller / Storage / Queue / Web UI | NAS |
| AI Compute Worker | GPU PC |
| Web Client | Mobile |
| Optional Worker | Cloud / API |

Task 必須宣告所需能力（capabilities，例如 `ffmpeg`、`gpu`、`network`），Worker 宣告所提供能力；配對由 Executor 負責。

## 4. Local First AI（本機優先）

若本機模型可合理完成工作，優先本機。Local Provider 不計 API Token 成本。
付費模型只作為升級或 fallback。

**不得因 Local AI 失敗而自動切換到 PAID Provider。** 必須停下等待人工批准。
Fallback 鏈中若下一個候選是 PAID，流程必須停在 `ApprovalGate`。

## 5. Human Approval Gate（人工核准閘門）

Project 與 Scene 狀態至少保留：`DRAFT` → `PREVIEW` → `APPROVED` → `FINAL`。

- `PREVIEW` 不等於 `FINAL`。
- `APPROVED` / `FINAL` 只能由人工操作（CLI/UI 的 approve 動作）寫入；pipeline 自動流程不得寫入。
- 使用者必須能：重新產生單一 Scene、修改 Prompt、修改旁白、修改字幕、核准 Final Render。
- **禁止因修改 Scene N 而無必要地重新生成其他 Scene。** 每個 Scene 的每個產物都有 fingerprint；fingerprint 不變則重用產物。

## 6. 結構化資料，不是自由文字

AI 不得以自由文字直接控制影片。所有 AI 輸出必須經過 Pydantic schema 驗證（`see/models/`），驗證失敗即 fail-closed。

## 7. 成本模型

Provider 必須標記 `cost_tier ∈ {LOCAL_FREE, FREE_TIER, PAID}`。
每個 `RenderJob` 保存：`estimated_cost`、`actual_cost`（若可取得）、`currency`、`provider`、`model`。

## 8. GitHub / 保密

禁止 commit：API key、Token、Secret、生成的大型影片、模型權重、私人素材。
`.gitignore` 已涵蓋；`.env.example` 只放鍵名不放值。

## 9. 第三方程式碼

使用第三方程式碼前必須確認 License，並在 `docs/DECISIONS.md` 記錄來源與授權。
參考專案只研究思路，不直接複製、不 fork 後大改。

## 10. 停手條件（Agent 必須停止並詢問）

- 需要付費
- 需要 API Key / OAuth
- 需要新增外部帳號
- 需要下載大型模型
- License 不清楚
- 架構需要不可逆重大改動
- 必須選擇特定 AI Provider 才能繼續
- 需要客戶提供 NAS / GPU 硬體資訊
- Spec 有重大缺口

其餘安全、免費、可逆的工作可自主完成。

## 11. Conversation Handoff & Crash Recovery（對話交接與中斷恢復）

**對話不是正式狀態來源；GitHub 才是。** 任何 AI 對話（Claude Code、ChatGPT 或其他）都可能因 token、額度、context 或意外而消失。

### 11.1 Source of Truth 優先順序
1. GitHub 實際 commit / tree / code
2. PR / CI / tests
3. `docs/STATE.md`
4. `docs/DECISIONS.md`
5. `docs/BACKLOG.md`
6. `docs/HANDOFF_PROJECT_AI.md` / `docs/HANDOFF_CHATGPT.md`
7. 對話內容

HANDOFF 不得單獨作為事實證據。新 AI 對話接手時必須重新驗證 GitHub 實況；文件與 GitHub 不一致時 GitHub 優先，先修正文件再繼續功能工作。禁止依靠「上一個 AI 說已完成」直接繼續。

### 11.2 文件職責（各司其職，不重複）
| 文件 | 職責 | 長度 |
|---|---|---|
| `docs/STATE.md` | 目前狀態快照（唯一的「現在在哪」） | 極短，不寫歷史 |
| `docs/DECISIONS.md` | 為什麼這樣做（含使用者裁示） | append |
| `docs/BACKLOG.md` | 還沒做的事與 Decision Gates | 持續整理 |
| `docs/HANDOFF_PROJECT_AI.md` | 給 Coding Agent 的恢復手冊 | 穩定，少改 |
| `docs/HANDOFF_CHATGPT.md` | 給治理／協作 AI 的恢復手冊 | 穩定，少改 |
| `docs/SESSION_LOG.md` | 每個工作階段一筆 append-only 紀錄 | 每筆 ≤ 8 行 |
| `docs/HANDOFF.md` | 只是索引，指向以上文件 | 不放狀態 |

### 11.3 Checkpoint Rule
超過一個小型 Batch 的工作不得長時間只存在 working tree。切分原則是「可獨立恢復」：
implementation → tests → commit → 更新 STATE → 再進下一批。不為極小修改製造無意義 commit。
SHA 慣例：`STATE.md` 的 Last Verified Commit 與 `SESSION_LOG.md` 的 End SHA 指向「已跑過測試的功能 commit」；更新這兩個檔案本身的 `chore(state)` checkpoint commit 緊跟其後，不再回填自己的 SHA。

### 11.4 Conversation End Protocol
出現以下任一：context 接近上限、token／額度接近上限、準備換對話、客戶要求結束、長工作階段完成 → 必須依序：
1. 停止開始新功能。
2. 完成目前可安全完成的 checkpoint。
3. 跑必要測試。
4. commit / push。
5. 更新 `STATE.md`。
6. 更新相關 HANDOFF（只在規則／架構／Phase 改變時）。
7. 在 `SESSION_LOG.md` append 一筆。
8. 確認 secrets / 生成影片 / 模型權重未進 Git（`git ls-files | grep -E '\.(mp4|wav|safetensors|key)$|\.env$'` 應為空）。
9. 回報最後 SHA、未完成工作、下一步。
10. 明確告知「可安全換新對話」。
若意外中斷未能完成，下一個 session 以 GitHub 實況重建狀態，不猜測前一個對話做到哪裡。

### 11.5 New Conversation Recovery Protocol（Project AI）
1. 讀 `PROJECT_RULES.md`。
2. 重新取得：remote、branches、main HEAD、open/draft PR、CI、working tree（同一環境時）、最近 commits。
3. 讀 `STATE.md` → `DECISIONS.md` → `BACKLOG.md` → `HANDOFF_PROJECT_AI.md`。
4. 比對文件與 GitHub；不一致以 GitHub 為準，先修正文件。
5. 才開始功能工作。

### 11.6 ChatGPT Verification Gate
治理 AI 在提供「下一步、Project AI 提示語、完成度判斷、PR 合併建議、架構重大裁示」之前，必須先獨立重新查 GitHub 最新實況，不得只依 Claude 回報或 HANDOFF。

### 11.7 Silent Autonomous Cruise
安全、免費、可逆且規格明確的工作靜默自主完成；只有需要客戶裁示、遇到停手條件、整批完成時才回報。checkpoint commit 不逐次通知。
