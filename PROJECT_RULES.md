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
5. 以 §12.5 七項自檢；任一項須靠聊天紀錄才知道 → 先補 GitHub。
6. 才開始功能工作。

### 11.6 ChatGPT Verification Gate
治理 AI 在提供「下一步、Project AI 提示語、完成度判斷、PR 合併建議、架構重大裁示」之前，必須先獨立重新查 GitHub 最新實況，不得只依 Claude 回報或 HANDOFF。

### 11.7 Silent Autonomous Cruise
安全、免費、可逆且規格明確的工作靜默自主完成；只有需要客戶裁示、遇到停手條件、整批完成時才回報。checkpoint commit 不逐次通知。

## 12. GitHub Memory Rule（長期記憶 SSOT；D-025）

**GitHub repository is the long-term project memory and Source of Truth. ChatGPT Memory, Claude Memory, and conversation history are not project storage. Any information required by a future AI session must be persisted to the appropriate canonical GitHub document.**

**客戶需求入庫（D-052，永久）**：凡客戶提出且會影響產品功能、UX、架構、資料、模型策略、待辦或驗收標準的需求，都必須在**當輪工作結束前**寫入 GitHub canonical docs（BACKLOG／ARCHITECTURE／DECISIONS／PROJECT_RULES 等依責任分流）；不得只存在 ChatGPT、Claude 對話或 AI 記憶。

**永久判定（D-055）：GitHub 不是備份，而是專案記憶本體；AI 對話只是暫時工作介面。** ChatGPT／Claude／其他 AI 的 Memory、聊天紀錄、口頭回報都只能是暫時工作 context，不得作為正式狀態來源。

角色：GitHub＝長期記憶／正式事實；ChatGPT＝獨立協作、研究、驗證、裁示輔助；Claude／Project AI＝實作者；AI Memory＝非正式、不可依賴；對話 context＝暫時工作記憶。只存在聊天或 AI Memory 的資訊一律視為**尚未正式保存**。禁止「AI 記得，所以不用寫」。

### 12.1 Knowledge Persistence Check
每個 Batch、Decision、真機驗證、重大需求、Phase、對話結束前，必須檢查並寫入（並以 §12.5 的 GitHub Alone Recovery 測試自問）：
永久規則 → `PROJECT_RULES.md`｜現況 → `docs/PROJECT_STATE.md`｜未完成 → `docs/BACKLOG.md`｜裁示 → `docs/DECISIONS.md`｜歷史 → `docs/SESSION_LOG.md`｜驗收證據 → `docs/*_EVIDENCE.md`｜導航 → `docs/HANDOFF.md`。

### 12.2 文件責任與防漂移
PROJECT_STATE 只寫現在；BACKLOG 只管未完成；DECISIONS 只管裁示；SESSION_LOG 只管歷史；EVIDENCE 只管驗收；HANDOFF 只管導航；PROJECT_RULES 只管永久治理。同一資訊需出現兩處時：一處 canonical detail，另一處只摘要＋連結。新 AI 不應掃完整 SESSION_LOG 才能知道現況。

### 12.3 GitHub Verification Gate（擴充 §11.5／§11.6）
任何 completion judgment、next step、merge、PR、branch cleanup、Phase／Batch 變更、handoff、backlog closure 之前，先重新驗證 GitHub（main、PR、CI、tests、code、working tree）。事實優先順序：commit/tree/code → PR/CI/tests → canonical docs → 對話／AI memory。

### 12.4 完成度判斷（永久）
Real／Completed＝使用者真正可用且已驗證；Partial＝部分可用；Mock＝僅 deterministic 開發用；Null＝無能力；Silent＝無真正音訊；Placeholder＝fallback 非生成能力。`MockLLMProvider`≠LLM 規劃完成、`silent-tts`≠TTS 完成、`null-audio`≠BGM/SFX 完成、`null-lipsync`≠lipsync 完成、placeholder 圖≠生圖完成。Skeleton／interface ≠ user-usable capability。關閉 BACKLOG 需 GitHub／code／test／真機證據。

### 12.5 GitHub Alone Recovery（D-055，永久）
目標：換 AI 可以、換對話可以、聊天紀錄不完整甚至遺失也可以；只要 GitHub 還在，就必須能把專案正確接回來。
一個**完全沒有舊聊天紀錄**的新 AI，只靠 GitHub（依 §11.5 順序閱讀）必須能還原：
1. 現在做到哪裡（`PROJECT_STATE`）
2. 為什麼這樣設計（`DECISIONS`／`ARCHITECTURE`）
3. 哪些已完成／未完成（`PROJECT_STATE`／`BACKLOG`）
4. 使用者做過哪些裁示（`DECISIONS`）
5. 真機／CI／人工驗收證據（`*_EVIDENCE`、`docs/evidence/`、Actions）
6. 已知限制與失敗路線（`DECISIONS`／`BACKLOG`／研究文件）
7. 唯一下一步（`PROJECT_STATE`「下一唯一安全接手點」）

若新 AI 必須依賴聊天紀錄才能知道上述任一項 → 視為**治理缺口**：先補 GitHub canonical docs，再繼續開發。
**工作完成定義（追加於 §12.4）**：在「換一個 AI」「開空白新對話」「舊聊天紀錄遺失」三種情況下仍能依 GitHub 正確接續，才算完成。

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
- **Reference Library（D-056／D-058）**：所有 reference assets 統一放 `workspace/reference_library/{people,animals,characters,backgrounds,styles}/`（本機、不進 Git；舊 `workspace/identity_refs/` 僅 legacy 相容）。GitHub 只保存規則、schema、路徑慣例與 provenance metadata（sha256／bytes／類別），不得提交任何私人參考圖。某類別尚無對應 conditioning 時必須明確拒絕，不得假裝支援。

## 17. Character Identity Definition（D-058，永久）
- **`character_id` 是穩定身份鍵**，不代表性別、位置、style、mood、voice 或角色類型。產品使用穩定 ID（例 `char_001`、`char_002`）；A／B 只允許作測試槽位、UI 暫時排序或比較標籤。禁止「A 永遠＝男／B 永遠＝女」、禁止從 character_id 推論性別、位置或風格。
- 性別呈現、位置、reference、style、mood、voice **全部是顯式欄位**（schema：ARCHITECTURE §17）。`gender_presentation`（male／female／nonbinary／unspecified）是畫面呈現，**不是生理性別**；未指定＝`unspecified`，缺資料不得自行補值。
- **不得從 reference image 自動推論**敏感身份、國籍或族群；`appearance_region` 只有使用者明確指定時才填。
- Reference asset 的歸屬（character_id）、用途（role）、來源（source_type）與商用授權狀態由 **metadata** 決定，禁止靠檔名或資料夾猜。
- **Identity 與 Style／Mood／Voice 分離**：角色只持有預設引用，Scene 可 override；改 style 不得改變身份設定。
- **Character Validation Gate**：生成前檢查（ID 唯一、reference 綁定、性別欄位、placement、role、跨角色重複 reference、私人圖片只在本機、商用授權）；任何衝突 **fail closed**（不生成，顯示需要修正）。
- **Character Confirmation Card**：正式 UI 在生成前必須顯示每個角色的名稱、性別呈現、reference、服裝、位置、style、mood、voice，且可在該步直接修改。
- 一般使用者 UI 不暴露技術名稱（char_a、IP-Adapter、checkpoint、CUDA、model path、prompt token）；技術參數只在 Advanced／Debug。
- **人物身份永久設定與每 Scene 演出覆寫分離（D-063）**：臉型、五官、髮型、髮色、基本服裝、固定特徵、default voice、default style／mood 屬角色永久設定（CharacterDefinition／CharacterAppearance）；表情、情緒、動作、視線、姿勢、本幕服裝、畫面位置、景深屬 Scene Character Override（`Scene.characters`）。**Scene override 不得靜默改寫角色永久設定**（本幕服裝只屬於本幕）。
- **歷史 evidence 定義錯誤時**：不刪、不覆寫、不改名假裝正確；以 metadata／文件標記（例 `historical_reversed_character_mapping=true`）並說明可用與不可用的結論；修正後的案例定義版本 +1，新檔名不得與舊檔衝突。

## 18. 一般使用者 UX 以中文為主（D-063，永久）
- **一般使用者 UX 以中文為主；模型語言屬內部實作細節。** 使用者只需輸入繁體中文；系統內部自行轉成模型需要的英文 prompt／技術參數。
- 一般 UI 不要求使用者編輯 `image_prompt_en`、checkpoint、CUDA、prompt token、char_a／char_b、其他模型技術名稱；這些只能出現在 Advanced／Debug、evidence、backend。一般 UI 標籤一律繁體中文（例：圖片描述、場景視覺描述、影片動態描述、重新生成影響、儲存、重新生成）。
- 中文 → 英文 prompt 必須經明確的 translator／prompt builder service contract；**沒有真 AI 翻譯時不得假裝有**：UI 與 evidence 必須標示 prompt 來源（`zh_generated`／`legacy_en`／`legacy_image_prompt`／`advanced_override`）與 translator 名稱、`ai_translated`。
- 中文自然語言描述（例：人物描述原文）在沒有可靠解析前只保存原文，不自動拆成結構化欄位、不宣稱已解析；結構化欄位只在使用者明確選擇／填寫時成立。

## 19. Environment／Migration（D-064，永久）
- **GitHub 必須足以讓新電腦／新 AI 重建環境**（不靠聊天記憶）：安裝、檢查、搬機流程以 [`docs/ENVIRONMENT_SETUP.md`](docs/ENVIRONMENT_SETUP.md)、[`docs/MIGRATION_REINSTALL.md`](docs/MIGRATION_REINSTALL.md) 為準，內容必須與實際 CLI 一致（`doctor`／`bootstrap`／`env-export`／`smoke`）。
- 環境工具**預設唯讀**：不自動 pip install、不安裝 torch／CUDA／driver、不下載模型、不改系統 PATH／registry、不寫永久環境變數。安全寫入只限使用者明確旗標（`bootstrap --apply-safe` 只建空資料夾＋版本檔；`doctor --write-manifest`；`env-export` 只寫新資料夾）。
- 固定狀態 OK／PARTIAL／UNAVAILABLE／ERROR；**缺少 ≠ OK**；optional 缺少不使整體失敗；介面存在 ≠ 能力完成。
- 模型以 logical model ID＋相對 `SEE_MODELS_DIR` 的路徑描述，**不得寫死磁碟代號**；換磁碟只改 `SEE_MODELS_DIR`。新寫入的 metadata 不存本機絕對路徑。
- 匯出物去識別化（家目錄 → `~`、使用者名稱 → `<user>`、secret → `<redacted>`）；不打包模型、不複製私人圖片；machine-local manifest 不進 Git，GitHub 只放去識別化範例。
- 資料 schema 帶版本；舊資料相容讀取且不偷偷改寫；比程式新 → fail safe；遷移前先備份；**禁止 silent destructive migration；不可逆遷移 → Decision Gate**。
