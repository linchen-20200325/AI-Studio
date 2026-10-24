# HANDOFF.md — 新 AI 對話入口（導航頁，不放狀態）

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
- **D-066**：客戶裁示 Project 層結構化場景預設先不做；visual_description 與 Scene.settings 並存不互相改寫。角色資料唯一架構設計：docs/CHARACTER_LIBRARY_PROJECT_BINDING.md（推薦 revision pinning；DG-29 待裁示）。
- **D-065**：machine-specific 設定改用專案本機設定檔 `see.local.json`（`python -m see.app.cli config set models_dir "E:\AI\models"`；env > local config > unset；不進 Git；doctor 顯示來源）。Scene 結構化設定（背景／環境／地點／時間／天氣／構圖／取景／景別／鏡頭角度／焦點／光線／色調／氣氛；中文；None 不補值；確定性對照＋no_prompt_effect；只重做 image＋clip）；鏡頭運動＝camera_motion（只重做 clip）、視覺風格＝Scene.preferences。
- **D-064**：Environment Bootstrap／Migration Foundation。新電腦／重灌／換 GPU／換磁碟：依 docs/ENVIRONMENT_SETUP.md、docs/MIGRATION_REINSTALL.md；`python -m see.app.cli doctor`（唯讀檢查，Ready／Not ready、Tier A–D）、`bootstrap`（唯讀計畫；`--apply-safe` 只建空資料夾）、`env-export`（可恢復資訊；不含模型與私人圖片）、`smoke`（不需 GPU）。模型以 logical ID＋相對 `SEE_MODELS_DIR`；不進 Git：workspace/、模型、.env。
- **D-063**：客戶裁示一般 UI 全中文輸入（模型語言屬內部實作）。Scene `image_prompt_zh`（圖片描述）→ prompt builder（目前 keyword_fallback_v1，非 AI 翻譯，evidence 標來源）→ 英文 prompt；`image_prompt_en` 保留為 internal／legacy（Advanced 只讀）；Scene Character Override（表情／情緒／動作／視線／姿勢／本幕服裝／位置／景深／中文原話）與角色永久設定分離；Scene 卡中文分區＋人物子卡。
- **D-061／D-062**：Identity Preservation／Character LoRA＝HARDWARE_UPGRADE_BLOCKED（≥12 GB VRAM 級再依 Resume Gate 重評；D-060 crop rerun deferred）。已完成不需 GPU 的安全工作：Preference Layer 非 UI 核心（Project→Scene override、再生成範圍、偏好快照）、Web UI Scene 圖片描述等欄位＋影響範圍確認、Reference Library service／`ref` CLI、Character CRUD（無 hard delete）、Confirmation payload。
- **下一唯一安全接手點**：無 Windows 指令。Identity／LoRA＝**HARDWARE_UPGRADE_BLOCKED**（D-061；重開依 ARCHITECTURE §18 Resume Gate）。角色資料設計已完成（D-066，docs/CHARACTER_LIBRARY_PROJECT_BINDING.md）。**下一唯一安全接手點：等客戶裁示 DG-29（角色 ID 命名空間）並核可 revision pinning 設計**；核可後做 Batch 2（CharacterStore append-only revision history；不影響 pipeline）。Scene 結構化設定已完成（D-065）。Environment Bootstrap／Migration 第一階段已完成（D-064：`doctor`、`bootstrap`、`env-export`、`smoke`；docs/ENVIRONMENT_SETUP.md、docs/MIGRATION_REINSTALL.md）。待客戶裁示：**DG-29 角色 ID 命名空間＋綁定設計核可（阻塞角色遷移批次）**；不阻塞：Preference 規格缺口 4 項、D-063 中文輸入缺口（Advanced 英文覆寫語意、視覺偏好中文輸入、場景卡增減角色）。
- 禁止直接做：付費／API key、下載未核准模型、改 production default、Model Router、DG-19 UI、lip-sync 模型、刪 SD1.5、pickle/ckpt/bin、LoRA 訓練、把 MeinaMix 當商用。


> **Do not depend on previous ChatGPT or Claude conversation context. Reconstruct state from GitHub.**
> GitHub repository `linchen-20200325/AI-Studio` 是唯一長期記憶（PROJECT_RULES §12）；**GitHub 不是備份，而是專案記憶本體**。讀完後以 §12.5 七項自檢（D-055），任一項需靠聊天紀錄 → 先補 GitHub。ChatGPT Memory／Claude Memory／舊對話都不是正式儲存層。

## 1. First read（依序）
1. [`PROJECT_RULES.md`](../PROJECT_RULES.md) — 永久規則（Free First、Provider/Compute Agnostic、Human Approval、停手條件、§11 交接、§12 GitHub Memory／§12.5 GitHub Alone Recovery、§13 Model/Effort/Token Gate、§14 Windows 互動、§15～§17 偏好／角色多樣性／角色身份定義）
2. [`docs/PROJECT_STATE.md`](PROJECT_STATE.md) — 現在仍有效的狀態、Decision Gate、下一步、已驗證環境
3. [`docs/BACKLOG.md`](BACKLOG.md) — 所有未完成工作（含能力盤點、Phase 2 建議、Windows／模型／裁示標示）
4. [`docs/DECISIONS.md`](DECISIONS.md) — 已裁示事項（D-001～；superseded 有標示）
5. 證據：[`PHASE0_EVIDENCE.md`](PHASE0_EVIDENCE.md)、[`PHASE1_EVIDENCE.md`](PHASE1_EVIDENCE.md)、[`TTS_PROVIDER_PLAN.md`](TTS_PROVIDER_PLAN.md)（DG-9 研究）、[`PHASE2_EVIDENCE.md`](PHASE2_EVIDENCE.md)（Kokoro 真機）
6. 技術文件：[`ARCHITECTURE.md`](ARCHITECTURE.md)、[`AI_IMAGE_SD15_WINDOWS.md`](AI_IMAGE_SD15_WINDOWS.md)、[`AI_IMAGE_PROVIDER_PLAN.md`](AI_IMAGE_PROVIDER_PLAN.md)、[`AI_TTS_KOKORO_WINDOWS.md`](AI_TTS_KOKORO_WINDOWS.md)（Audio Layer 見 D-031；產品流程對照見 `ARCHITECTURE.md` §12／D-032）
7. 歷史：[`SESSION_LOG.md`](SESSION_LOG.md)（不必掃完才能知道現況）

## 2. Then verify GitHub（Verification Gate，PROJECT_RULES §11.5／§11.6）
`main` HEAD 與開發分支 HEAD、最近 commits、open/draft PR、Actions `ci.yml` conclusion、`python -m pytest -q`、working tree。文件與 GitHub 不一致 → GitHub 為準，先修文件再動功能。

## 3. Current handoff（細節一律看 PROJECT_STATE／BACKLOG，這裡不複製）
- Phase：見 `PROJECT_STATE.md`「Current Phase」。
- **產品視覺方向（必讀，D-034）**：P1＝日系動畫＋AI 真人／寫實＋電影感；P2＝3D；P3＝兒童繪本。**不要把兒童繪本當主要方向**（程式 `default` 繪本水彩只是歷史相容預設）。見 README「產品視覺方向」。
- **使用者偏好 ≠ 模型實作（必讀，PROJECT_RULES §15／D-041／D-042）**：不得把任何模型／人物／prompt／畫風／參數寫死為唯一預設；生成後可改偏好再生成；入口 ARCHITECTURE §13。
- **跨次比較（D-043）**：evidence 的 `baseline_condition`（舊名 fair_comparison）只表示 fit 基準條件；兩張圖是否只差一個變數一律用 `style-compare` 判定，不得憑單張旗標宣稱公平比較。
- **驗收分層（必讀，D-035）**：`technical_valid`（自動）≠ `scene_validated` ≠ `style_validated`（人工 `style-review`）。不得把技術有效寫成場景／風格通過。影像品質根因見 [`AI_IMAGE_QUALITY_RCA.md`](AI_IMAGE_QUALITY_RCA.md)；P1 專用模型研究見 [`DG20_IMAGE_MODEL_RESEARCH.md`](DG20_IMAGE_MODEL_RESEARCH.md)（原始證據 `docs/evidence/dg20/`；全部 commercial_cleared=false；D-039 核准 MeinaMix／CyberRealistic 下載**僅限內部品質驗證**）。
- Decision Gate：見 `PROJECT_STATE.md`「Current Decision Gate」。
- Next action：見 `PROJECT_STATE.md`「Current next action」。

## 4. 角色專用補充（與本頁不重複；漂移時以本頁 + PROJECT_STATE 為準）
| 我是 | 看 |
|---|---|
| Coding Agent（Claude Code／Project AI） | [`HANDOFF_PROJECT_AI.md`](HANDOFF_PROJECT_AI.md)（工作方式、快速啟動、程式慣例） |
| 治理／協作 AI（ChatGPT） | [`HANDOFF_CHATGPT.md`](HANDOFF_CHATGPT.md)（治理方式、審核清單） |

## 5. 文件責任（PROJECT_RULES §12.2）
PROJECT_RULES＝永久規則｜PROJECT_STATE＝現在｜BACKLOG＝未完成｜DECISIONS＝裁示｜SESSION_LOG＝歷史｜*_EVIDENCE＝驗收｜HANDOFF＝導航。`docs/STATE.md` 僅為相容指標，內容在 PROJECT_STATE。
