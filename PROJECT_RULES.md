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
- 需要下載**任何新模型**（含小型 TTS／LLM 模型；大型模型更是）
- License 不清楚
- 需要大量磁碟空間
- 架構需要不可逆重大改動
- 必須選擇特定 AI Provider 才能繼續（forced provider choice）
- 需要新硬體
- 需要客戶提供 NAS / GPU 硬體資訊
- Spec 有重大缺口
- 產品方向必須由客戶裁示（例如下一個 Phase 的目標）

其餘安全、免費、可逆的工作可自主完成。

## 11. Conversation Handoff & Crash Recovery（對話交接與中斷恢復）

**對話不是正式狀態來源；GitHub 才是。** 任何 AI 對話（Claude Code、ChatGPT 或其他）都可能因 token、額度、context 或意外而消失。

### 11.1 Source of Truth 優先順序
1. GitHub 實際 commit / tree / code
2. PR / CI / tests
3. `docs/PROJECT_STATE.md`（`docs/STATE.md` 僅為相容指標）
4. `docs/DECISIONS.md`
5. `docs/BACKLOG.md`
6. `docs/HANDOFF_PROJECT_AI.md` / `docs/HANDOFF_CHATGPT.md`
7. 對話內容

HANDOFF 不得單獨作為事實證據。新 AI 對話接手時必須重新驗證 GitHub 實況；文件與 GitHub 不一致時 GitHub 優先，先修正文件再繼續功能工作。禁止依靠「上一個 AI 說已完成」直接繼續。

### 11.2 文件職責（各司其職，不重複）
| 文件 | 職責 | 長度 |
|---|---|---|
| `docs/PROJECT_STATE.md` | 目前狀態快照（唯一的「現在在哪」；`STATE.md` 僅相容指標） | 極短，不寫歷史 |
| `docs/DECISIONS.md` | 為什麼這樣做（含使用者裁示） | append |
| `docs/BACKLOG.md` | 還沒做的事與 Decision Gates | 持續整理 |
| `docs/HANDOFF_PROJECT_AI.md` | 給 Coding Agent 的恢復手冊 | 穩定，少改 |
| `docs/HANDOFF_CHATGPT.md` | 給治理／協作 AI 的恢復手冊 | 穩定，少改 |
| `docs/SESSION_LOG.md` | 每個工作階段一筆 append-only 紀錄 | 每筆 ≤ 8 行 |
| `docs/HANDOFF.md` | 新 AI 對話導航入口（讀什麼、驗什麼、指向現況） | 不放狀態 |
| `docs/*_EVIDENCE.md` | Phase／真機／測試驗收證據 | 歷史證據，不複製到 STATE |

### 11.3 Checkpoint Rule
超過一個小型 Batch 的工作不得長時間只存在 working tree。切分原則是「可獨立恢復」：
implementation → tests → commit → 更新 STATE → 再進下一批。不為極小修改製造無意義 commit。
SHA 慣例：`PROJECT_STATE.md` 的 checkpoint 欄位 與 `SESSION_LOG.md` 的 End SHA 指向「已跑過測試的功能 commit」；更新這兩個檔案本身的 `chore(state)` checkpoint commit 緊跟其後，不再回填自己的 SHA。

### 11.4 Conversation End Protocol
出現以下任一：context 接近上限、token／額度接近上限、準備換對話、客戶要求結束、長工作階段完成 → 必須依序：
1. 停止開始新功能。
2. 完成目前可安全完成的 checkpoint。
3. 跑必要測試。
4. commit / push。
5. 更新 `PROJECT_STATE.md`。
6. 更新相關 HANDOFF（只在規則／架構／Phase 改變時）。
7. 在 `SESSION_LOG.md` append 一筆。
8. 確認 secrets / 生成影片 / 模型權重未進 Git（`git ls-files | grep -E '\.(mp4|wav|safetensors|key)$|\.env$'` 應為空）。
9. 回報最後 SHA、未完成工作、下一步。
10. 明確告知「可安全換新對話」。
若意外中斷未能完成，下一個 session 以 GitHub 實況重建狀態，不猜測前一個對話做到哪裡。

### 11.5 New Conversation Recovery Protocol（Project AI）
1. 讀 `PROJECT_RULES.md`。
2. 重新取得：remote、branches、main HEAD、open/draft PR、CI、working tree（同一環境時）、最近 commits。
3. 讀 `PROJECT_STATE.md` → `BACKLOG.md` → `DECISIONS.md` → `HANDOFF.md`（及角色專用 handoff）。
4. 比對文件與 GitHub；不一致以 GitHub 為準，先修正文件。
5. 才開始功能工作。

### 11.6 ChatGPT Verification Gate
治理 AI 在提供「下一步、Project AI 提示語、完成度判斷、PR 合併建議、架構重大裁示」之前，必須先獨立重新查 GitHub 最新實況，不得只依 Claude 回報或 HANDOFF。

### 11.7 Silent Autonomous Cruise
安全、免費、可逆且規格明確的工作靜默自主完成；只有需要客戶裁示、遇到停手條件、整批完成時才回報。checkpoint commit 不逐次通知。

## 12. GitHub Memory Rule（長期記憶 SSOT；D-025）

**GitHub repository is the long-term project memory and Source of Truth. ChatGPT Memory, Claude Memory, and conversation history are not project storage. Any information required by a future AI session must be persisted to the appropriate canonical GitHub document.**

角色：GitHub＝長期記憶／正式事實；ChatGPT＝獨立協作、研究、驗證、裁示輔助；Claude／Project AI＝實作者；AI Memory＝非正式、不可依賴；對話 context＝暫時工作記憶。只存在聊天或 AI Memory 的資訊一律視為**尚未正式保存**。禁止「AI 記得，所以不用寫」。

### 12.1 Knowledge Persistence Check
每個 Batch 結束、Phase 結束、對話結束、重大裁示、真機驗證完成，必須檢查並寫入：
永久規則 → `PROJECT_RULES.md`｜現況 → `docs/PROJECT_STATE.md`｜未完成 → `docs/BACKLOG.md`｜裁示 → `docs/DECISIONS.md`｜歷史 → `docs/SESSION_LOG.md`｜驗收證據 → `docs/*_EVIDENCE.md`｜導航 → `docs/HANDOFF.md`。

### 12.2 文件責任與防漂移
PROJECT_STATE 只寫現在；BACKLOG 只管未完成；DECISIONS 只管裁示；SESSION_LOG 只管歷史；EVIDENCE 只管驗收；HANDOFF 只管導航；PROJECT_RULES 只管永久治理。同一資訊需出現兩處時：一處 canonical detail，另一處只摘要＋連結。新 AI 不應掃完整 SESSION_LOG 才能知道現況。

### 12.3 GitHub Verification Gate（擴充 §11.5／§11.6）
任何 completion judgment、next step、merge、PR、branch cleanup、Phase／Batch 變更、handoff、backlog closure 之前，先重新驗證 GitHub（main、PR、CI、tests、code、working tree）。事實優先順序：commit/tree/code → PR/CI/tests → canonical docs → 對話／AI memory。

### 12.4 完成度判斷（永久）
Real／Completed＝使用者真正可用且已驗證；Partial＝部分可用；Mock＝僅 deterministic 開發用；Null＝無能力；Silent＝無真正音訊；Placeholder＝fallback 非生成能力。`MockLLMProvider`≠LLM 規劃完成、`silent-tts`≠TTS 完成、`null-audio`≠BGM/SFX 完成、`null-lipsync`≠lipsync 完成、placeholder 圖≠生圖完成。Skeleton／interface ≠ user-usable capability。關閉 BACKLOG 需 GitHub／code／test／真機證據。

## 13. Model / Reasoning / Token Efficiency Gate（D-025）

目標：**Minimum Sufficient Intelligence + Minimum Sufficient Context + Minimum Sufficient Effort**，不是 Minimum Token At Any Cost。Project AI 不得固定用同一模型或同一 Effort 處理所有工作；每個新的完整工作階段／Batch 開始前自行評估：工作複雜度、目前模型是否足夠、所需最低 Effort、是否值得更高理解力、能否降級而不影響正確性與安全。

### 13.1 Effort 原則
- **Low**：GitHub status、文件同步、BACKLOG／STATE／HANDOFF 更新、機械性修改、小型低風險修正、規格完全明確的工作、簡單測試／CI 檢查。
- **Medium**：一般功能實作、provider wiring、一般 UI/UX、單模組 bug、一般測試、低風險跨檔修改、需推理但不涉核心架構。
- **High**（僅必要時）：核心 architecture、跨模組重大修改、高風險 migration、不可逆變更、核心 pipeline semantics、複雜 concurrency／queue、重大模型／provider 選型、難定位的系統性 bug、影響大量既有功能的修改。不得因「High 比較聰明」而預設 High。

### 13.2 Model Gate／Effort Gate
目前模型與 Effort 足夠 → 以最低足夠 Effort 靜默執行，**不要為了詢問而打斷客戶**。判斷不足以可靠完成下一階段 → 停下，不得硬做；只回報 `MODEL CHANGE REQUIRED`（Current model、Recommended model、原因、用於哪段工作、完成後可否降回）或 `EFFORT CHANGE REQUIRED`（Current／Recommended Effort、原因、哪段需要、完成後可否降回），等客戶調整。不得先用不足的理解力大量修改再要求升級。

### 13.3 Downshift Rule
高難度工作完成後若只剩 tests／docs／GitHub status／checkpoint／BACKLOG／HANDOFF／CI monitoring，應主動降級；若切換需客戶操作，回報 `DOWNSHIFT RECOMMENDED` 並給建議設定。

### 13.4 Token Efficiency Rule
禁止：重複讀取已確認且本 Batch 未變更的大型文件、重複輸出相同狀態、每步回報、長篇重述 GitHub 已有內容、無必要重跑大型分析、用 High 做機械工作、派重複 agent 做相同檢查、無新資訊時反覆回報「等待 CI」、把完整 BACKLOG／STATE 複製進聊天。應：先讀 canonical files、只讀本工作需要的 code／docs、diff／targeted inspection、安全工作靜默執行、整批結束才摘要、Decision Gate 只給真正需要決定的資訊。
**優先級**：correctness > safety > GitHub verification > tests／evidence > stop conditions > token efficiency。不得為省 token 跳過測試、Verification Gate、evidence，或猜測 code 狀態、把 missing 當成功。

## 14. Windows Customer Interaction（D-025）

客戶不是工程師。Windows 操作**一次只能給一個 action／command**，必須等客戶回傳結果後才給下一個；不得一次給一串指令。回報精簡：Decision Gate 才需要客戶處理；安全、免費、可逆、規格明確的工作靜默自主完成，整批完成後一次回報；每個 Batch 標示 Model／Mode／Effort；全程繁體中文（台灣）。對話切換前必須完成 §11.4 與 §12.1（GitHub 化）。

## 15. User Preference ≠ Model Implementation（D-041、D-042，永久）
- 任何模型（例：MeinaMix、CyberRealistic、base SD 1.5）、人物設定、Prompt、畫風、生成參數**不得寫死成產品唯一預設**。模型只是可替換的底層引擎。
- 使用者偏好層（Style Profile、Character Profile、構圖／鏡頭、Generation Settings、模型偏好）與模型實作層分離；偏好以資料表達，經 Provider Agnostic 介面交給引擎。
- 驗證用的測試案例（`see/core/style_tests.py`）必須是模型／風格中性的構圖描述，可套用於任何 Style Profile 與 checkpoint。
- 授權狀態（`commercial_cleared` 等）隨模型走，不因偏好設定而改變。
- **事後可調（D-042，客戶明確要求）**：生成前可選偏好；**生成後可修改風格／人物／色彩／構圖／鏡頭等偏好並重新生成**（只重做受影響的景與下游，沿用 per-scene fingerprint）。
- Style Profile、Character Profile、Generation Settings 是**可修改的結構化設定**（資料、可序列化、可版本化），不是寫在程式裡的常數。
- 偏好表達方向：同時支援「選項式調整」與「自然語言描述偏好」（自然語言 → 經 LLM／規則轉成同一份結構化設定，而非另一套路徑）。
- **更換底層模型時，使用者偏好原則上不需重建**：偏好描述「要什麼」，模型路由／provider 決定「怎麼產生」；模型特有參數（clip skip、scheduler 等）屬於模型 preset，不寫進使用者偏好。
- 任何測試參數（seed、測試 prompt、測試人物外觀、MeinaMix 等）不得成為產品唯一預設；真機「品質 OK」只代表目前可接受，不等於鎖定模型或畫風。

## 16. Character Diversity & Reference Image Privacy（D-046，永久）
- 產品**不以任何性別、族群外貌或年齡為預設**。固定比較案例（如 `girl_portrait_closeup`）只是受控測試，不代表產品預設人物。
- Character／Persona 以**結構化設定**表達且全部可改：性別呈現、年齡／年齡區間、地區外貌特徵（東亞／西方等，只作可描述外觀，**不得寫成固定刻板臉型**）、髮型／髮色、五官與可描述外觀、服裝、體型、其他辨識特徵。
- Character Preference／Identity 屬偏好層（§15），**Provider Agnostic**：換 image model 原則上沿用；model-specific 參數（adapter 權重、clip skip 等）放模型層。
- **使用者真人照片＝敏感素材**：不得提交 GitHub、不得做測試 fixture、不得上傳第三方 provider（除非使用者另行明確同意）；Local First，只存本機 workspace（不進 Git）。
- Reference Image 技術（IP-Adapter／FaceID 類）下載、導入前須另做授權、硬體可行性、品質研究並經 Decision Gate。
