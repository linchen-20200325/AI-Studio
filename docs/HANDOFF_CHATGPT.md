# HANDOFF_CHATGPT.md — 給治理／協作 AI（ChatGPT 等）的恢復手冊

## ⛳ 最終交接 checkpoint（2026-10-23 封存；以 GitHub main HEAD 為準）
- 最後驗證 main：以 GitHub main HEAD 為準（D-045 文件 commit；CI 見 Actions）。開發分支 `ccr-297bf146-zrrlk1`。
- 已完成：Phase 0／0.5／1；Phase 2 進行中：Kokoro TTS（D-027／D-029，真機 validated）、Voice Selection／Character Voice（`zm_010`＝目前使用者偏好候選，非永久鎖定，DG-14）、BGM/SFX＋ducking（SFX 人工聽感未驗）、Style Profile、Character Consistency foundation（僅 prompt 錨點，無 IP-Adapter/LoRA）、Lip-sync 介面（無實際模型）、checkpoint 型錄／下載驗證／single-file 載入／clip-skip 相容（D-039／D-040；**不是** Model Router，Router 未實作）。
- E2-5：MeinaMix V12 native 近景真機成功；`style-compare` vs Base native＝**model_preset_level**（只差 model＋clip skip 2 vs 1，unexpected=[]）；客戶「這樣 OK」scene PASS／style PASS（single-user subjective）；DG-23 已裁示接受（D-045）→ MeinaMix＝目前 P1 日系動畫**品質驗證通過**；**不永久鎖定模型／畫風**（§15 Preference Layer）、**commercial_cleared=false**、不得商用。
- `fair_comparison`：已更名 `baseline_condition`；跨次比較一律 `style-compare`（D-043／D-044）。
- CyberRealistic：已下載；東亞女性 technical PASS＋客戶確認東方女性；東亞男性外觀確認但 JSON 未入庫（single-user subjective，D-047）；commercial_cleared=false；upstream lineage 未釐清；未鎖定為預設。
- production default **未變**（gen_policy=fit、base SD1.5、預設 style）。
- 本機：Windows、GTX 1650 4 GB（fp16 會 NaN → 自動 float32）、SD1.5 於 `D:\ai-models\sd15`、checkpoints 於 `SEE_MODELS_DIR\checkpoints\<id>\`（永不進 Git）。
- S4（D-054／D-056／D-057）：同 seed 重跑 mapping PASS（char_a→left、char_b→right）、兩人分離改善，但 **identity fidelity FAIL**（single-user subjective；scene FAIL；technical 未回報）→ S4 只作研究證據、不升格 production。DG-26：角色分開生成再合成（Route A 零下載 PoC 完成：`ab_background`／`ab_char_a_isolated`／`ab_char_b_isolated`＋`compose-scene`／`compose-review`）；Layered Scene 原則見 ARCHITECTURE §16。Reference Library＝`workspace/identity_refs/`（只 people）。
- **角色身份定義（D-058）**：客戶裁示 **A＝男、B＝女**；v1（D-049～D-057）寫反 → 舊 evidence 標 `historical_reversed_character_mapping=true`（不刪不改，只作模型能力證據）；A／B 案例改 v2（檔名 `-v2`）。character_id 不代表性別／位置／style／voice（PROJECT_RULES §17）；Character／Reference schema、Reference Library 主路徑 `workspace/reference_library/`、Validation Gate、Confirmation Card、Style／Voice 解耦見 ARCHITECTURE §17。
- **D-059**：v2 A 男主角 isolated（plus-face）**identity fidelity FAIL**（主觀；單人也不像；technical 未回報）→ DG-26 暫停；DG-28 Identity Preservation 研究完成（InsightFace 模型全為非商用研究；SDXL／FLUX 全部 4 GB ❌）；Reference Quality Check（ARCHITECTURE §17.7）、Identity Consistency 驗收（§17.8）入規格。
- **D-071**：Batch 5 migration engine：`character-migrate <pid> --apply --decisions <file> --confirm <apply_confirmation_token>`（preflight、atomic backup、staged transaction、post-verify、自動恢復）、`--rollback <migration_id>`、`--list-migrations`。v1 只支援 create_new／bind_existing（script／scene-only 條目）；narrator_setting 與 Project.characters 條目 fail closed。**Batch 5 engine implemented ≠ any real project migrated.** Project.cast is not yet production source of truth（Batch 6 才切換）。
- **D-070**：Batch 4.1 Migration Human Decisions Layer：`character-migrate <pid> --dry-run --decisions-template [--out]`（輸出決定檔範本）、`--decisions <file>`（versioned 決定檔；actions＝create_new／bind_existing／keep_legacy／narrator_setting／ignore_unused；source_report_input_hash＋source_report_sha256 不符 → stale；任何錯誤整份不採用 fail closed；重算 migration_ready 與 proposed rewrite plan；zero-write）。create_new 只用 placeholder `pending_new_character_id`，不產生正式 ID。migration_ready=true 只代表可進入經審查的 migration planning，不代表已遷移、不代表 Batch 5 已核准。**Batch 4.1 remains analysis-only. No project has been migrated.**
- **D-069**：Batch 4 `character-migrate <pid> --dry-run`（只分析；5 種分類、固定 conflict code、reference sha256、Scene／對白／旁白引用影響、report_input_hash、zero-write）。**Batch 4 only analyzes. No project has been migrated.**
- **D-068**：Batch 3 `Project.cast`（list[CharacterBinding]，預設空）＋`resolve_project_cast()`（pinned、不 fallback latest、fail closed）＋doctor／export／唯讀 CLI／API。**Project.cast exists but is not yet production source of truth.**（production 角色來源仍是 `Project.characters`；尚未遷移任何專案）
- **D-067**：DG-29 裁示 A（全域穩定 Library ID，系統產生；舊專案逐專案人工觸發遷移：dry-run → report → 客戶確認 → backup → migration → verify → 可 rollback；未遷移維持原行為）；核可 revision pinning（Project 綁 character_id＋character_revision，預設鎖定，不自動更新，缺失／hash 不符 fail closed）。Batch 2 完成：`character_library/history/<id>/r000001.json` 不可變 revision、canonical hash、reference snapshot、legacy baseline、`CharacterBinding`（未接 Project）。
- **D-066**：客戶裁示 Project 層結構化場景預設先不做；visual_description 與 Scene.settings 並存不互相改寫。角色資料唯一架構設計：docs/CHARACTER_LIBRARY_PROJECT_BINDING.md（推薦 revision pinning；DG-29 待裁示）。
- **D-065**：machine-specific 設定改用專案本機設定檔 `see.local.json`（`python -m see.app.cli config set models_dir "E:\AI\models"`；env > local config > unset；不進 Git；doctor 顯示來源）。Scene 結構化設定（背景／環境／地點／時間／天氣／構圖／取景／景別／鏡頭角度／焦點／光線／色調／氣氛；中文；None 不補值；確定性對照＋no_prompt_effect；只重做 image＋clip）；鏡頭運動＝camera_motion（只重做 clip）、視覺風格＝Scene.preferences。
- **D-064**：Environment Bootstrap／Migration Foundation。新電腦／重灌／換 GPU／換磁碟：依 docs/ENVIRONMENT_SETUP.md、docs/MIGRATION_REINSTALL.md；`python -m see.app.cli doctor`（唯讀檢查，Ready／Not ready、Tier A–D）、`bootstrap`（唯讀計畫；`--apply-safe` 只建空資料夾）、`env-export`（可恢復資訊；不含模型與私人圖片）、`smoke`（不需 GPU）。模型以 logical ID＋相對 `SEE_MODELS_DIR`；不進 Git：workspace/、模型、.env。
- **D-063**：客戶裁示一般 UI 全中文輸入（模型語言屬內部實作）。Scene `image_prompt_zh`（圖片描述）→ prompt builder（目前 keyword_fallback_v1，非 AI 翻譯，evidence 標來源）→ 英文 prompt；`image_prompt_en` 保留為 internal／legacy（Advanced 只讀）；Scene Character Override（表情／情緒／動作／視線／姿勢／本幕服裝／位置／景深／中文原話）與角色永久設定分離；Scene 卡中文分區＋人物子卡。
- **D-061／D-062**：Identity Preservation／Character LoRA＝HARDWARE_UPGRADE_BLOCKED（≥12 GB VRAM 級再依 Resume Gate 重評；D-060 crop rerun deferred）。已完成不需 GPU 的安全工作：Preference Layer 非 UI 核心（Project→Scene override、再生成範圍、偏好快照）、Web UI Scene 圖片描述等欄位＋影響範圍確認、Reference Library service／`ref` CLI、Character CRUD（無 hard delete）、Confirmation payload。
- **下一唯一安全接手點**：無 Windows 指令。Identity／LoRA＝**HARDWARE_UPGRADE_BLOCKED**（D-061；重開依 ARCHITECTURE §18 Resume Gate）。角色資料設計（D-066）已獲裁示：DG-29 選 A、核可 revision pinning（D-067）；Batch 2（Character Store 不可變 revision history＋CharacterBinding 基礎）已完成。Batch 3 已完成（D-068）：`Project.cast`＋`resolve_project_cast()`＋唯讀 `cast show`。**Project.cast exists but is not yet production source of truth.**（production 角色來源仍是 `Project.characters`；尚未遷移任何專案） Batch 4 已完成（D-069）：`python -m see.app.cli character-migrate <pid> --dry-run [--json]`。**Batch 4 only analyzes. No project has been migrated.** 客戶已在 Windows 對真實專案 `sd15test` 跑 dry-run（客戶回報：Project.characters=0；char_01～char_04 全為 SCRIPT_ONLY_CHARACTER／HUMAN_REQUIRED；affected scenes 5；rewrite references 26；migration_ready=false；zero-write PASS；報告檔在客戶本機 repo 根目錄、不在 GitHub）。Batch 4.1 已完成（D-070）：人工決定檔＋重算 migration_ready（仍唯讀）。**Batch 4.1 remains analysis-only. No project has been migrated.** 客戶已在 Windows 完成 sd15test Batch 4.1 唯讀驗證（char_01～char_04 全 create_new；applied；migration_ready=true；planned rewrites 26；未遷移）。Batch 5 engine 已完成（D-071）；**sd15test 尚未 migration**。**下一唯一安全接手點：客戶在 Windows 執行 `python -m see.app.cli character-migrate sd15test --dry-run --decisions sd15test_decisions.json`（唯讀）取得 apply_confirmation_token；是否 `--apply` 由客戶決定並親自執行（AI 不代執行）**；Batch 6（pipeline 改用 pinned revision）需另行裁示。Scene 結構化設定已完成（D-065）。Environment Bootstrap／Migration 第一階段已完成（D-064：`doctor`、`bootstrap`、`env-export`、`smoke`；docs/ENVIRONMENT_SETUP.md、docs/MIGRATION_REINSTALL.md）。待客戶裁示（不阻塞）：Preference 規格缺口 4 項、D-063 中文輸入缺口（Advanced 英文覆寫語意、視覺偏好中文輸入、場景卡增減角色）。
- 禁止直接做：付費／API key、下載未核准模型、改 production default、Model Router、DG-19 UI、lip-sync 模型、刪 SD1.5、pickle/ckpt/bin、LoRA 訓練、把 MeinaMix 當商用。


> 入口是 `docs/HANDOFF.md`；本文件是治理 AI 專用補充（治理方式、審核清單）。GitHub 是唯一長期記憶（PROJECT_RULES §12）。本文件不描述「現在在哪」——現況看 `PROJECT_STATE.md` 並與 GitHub 比對。

## 0. ChatGPT 協作規則（不依賴 ChatGPT Memory）
- 角色：治理／審核／協助使用者下指令給 Project AI；任何專案判斷前先查 GitHub（main、PR、CI、PROJECT_STATE）。HANDOFF／聊天記憶不是事實來源。
- 回覆繁中、極簡，第一行 🟢/🟡/🔴；使用者不是工程師 → 一步一步、Windows 一次一條命令。
- 給 Project AI 的提示語須附 Model／Effort 建議；使用者偏好靜默自主巡航。
- 對話變長或額度將盡 → 提醒換對話並要求先把狀態寫回 GitHub；重要實機結果一律要求寫回 GitHub（PHASE2_EVIDENCE／DECISIONS）。

## 1. 專案目的
`see`：使用者貼入中文文章／故事 → 自動產生影片（劇本 → 分鏡 → 圖片 → 動畫 → 配音 → 音效 → 字幕 → 剪輯 → QA → Preview → 人工核准 → Final）。採階段性 MVP，目前完成 Phase 0（pipeline）與 Phase 0.5（最小 Web UI）。Repo：`linchen-20200325/AI-Studio`（GitHub 上為 public；`main` 為已驗證版本，開發分支 `ccr-297bf146-zrrlk1`）。

## 2. 使用者核心偏好
- 全程繁體中文（台灣）。
- 「AI 總管」模式：複雜工作由總管拆解、指派虛擬專家；需裁示時主動提供「推薦選項 + 評估理由」。
- 靜默自主巡航：安全、免費、可逆、規格明確的工作不逐步回報；只在需裁示、停手條件、整批完成時回報。
- 回報精簡：SHA、測試、產出、成本、已完成、未完成、下一個 Decision Gate。
- 每批標示 Model / Mode / Minimum Sufficient Effort；Project AI 自行評估模型與 Effort，只在需客戶切換時回報 `MODEL/EFFORT CHANGE REQUIRED`（PROJECT_RULES §13）。
- Windows 指令一次一個（§14）。
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
- Phase 1（AI Image）：SD 1.5 於 Windows GTX 1650 真機五景成功（D-018～D-024，`PHASE1_EVIDENCE.md`）。Phase 2 進行中（現況看 PROJECT_STATE 最終交接 checkpoint）。

## 5. Current Phase
看 `docs/PROJECT_STATE.md`。

## 6. 尚待客戶裁示
看 `docs/PROJECT_STATE.md`「待裁示」與 `docs/BACKLOG.md` Decision Gates。已裁示的項目記錄在 `docs/DECISIONS.md`（D-009 起）。

## 7. GitHub 驗證規則（Verification Gate）
在提供「下一步、Project AI 提示語、完成度判斷、PR 合併建議、架構重大裁示」之前，**必須先獨立重新查 GitHub 最新實況**：
1. `main` HEAD 與開發分支 HEAD 的 SHA、最近 commits。
2. open/draft PR 與 CI 狀態：Actions workflow `ci.yml` 在該 SHA 的 conclusion 必須為 success。
3. `docs/PROJECT_STATE.md` 內容是否與上述一致；`docs/SESSION_LOG.md` 最後一筆的 End SHA。
4. 測試數與結果以 commit 內 `tests/` 與最近回報為準；有疑慮要求 Project AI 重跑。
不得只依 Claude 的回報或 HANDOFF 文件下判斷。文件與 GitHub 不一致 → GitHub 為準，先要求修正文件。

## 8. 對 Project AI 的治理方式
- 指派工作時給：目標、範圍邊界（明確列「不要做」）、停手條件、回報格式、Model / Mode / Effort。
- 要求 Project AI 開工先跑 Recovery Protocol（§11.5），收工跑 End Protocol（§11.4）。
- 每個 Batch 單一目標；超過一小批的工作要求 checkpoint commit。
- 審核 Project AI 回報時核對：SHA 存在於 GitHub、測試數合理、證據檔在 repo、無 secrets／媒體進 Git。
- 需要裁示時，要求 Project AI 給「推薦選項 + 評估理由」，由使用者裁示後記入 DECISIONS。

## 9. 下一個 Decision Gate
看 `docs/PROJECT_STATE.md`「待裁示」。
