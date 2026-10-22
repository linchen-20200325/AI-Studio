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
