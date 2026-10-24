# HANDOFF_PROJECT_AI.md — 給 Coding Agent（Claude Code 等）的恢復手冊

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
- **D-063**：客戶裁示一般 UI 全中文輸入（模型語言屬內部實作）。Scene `image_prompt_zh`（圖片描述）→ prompt builder（目前 keyword_fallback_v1，非 AI 翻譯，evidence 標來源）→ 英文 prompt；`image_prompt_en` 保留為 internal／legacy（Advanced 只讀）；Scene Character Override（表情／情緒／動作／視線／姿勢／本幕服裝／位置／景深／中文原話）與角色永久設定分離；Scene 卡中文分區＋人物子卡。
- **D-061／D-062**：Identity Preservation／Character LoRA＝HARDWARE_UPGRADE_BLOCKED（≥12 GB VRAM 級再依 Resume Gate 重評；D-060 crop rerun deferred）。已完成不需 GPU 的安全工作：Preference Layer 非 UI 核心（Project→Scene override、再生成範圍、偏好快照）、Web UI Scene 圖片描述等欄位＋影響範圍確認、Reference Library service／`ref` CLI、Character CRUD（無 hard delete）、Confirmation payload。
- **下一唯一安全接手點**：無 Windows 指令、無待裁示阻塞。Identity／LoRA＝**HARDWARE_UPGRADE_BLOCKED**（D-061；重開依 ARCHITECTURE §18 Resume Gate）。下一批可自主安全工作（BACKLOG）：**Environment Bootstrap**（持久化模型目錄設定＋啟動自檢；錯誤訊息區分「目錄未設定」與「未驗證」）→ Migration／Reinstall 第一階段（只檢查不下載）→ Scene 結構化設定資料模型（background／time_of_day／weather／environment／composition）。待客戶裁示（不阻塞）：Preference 規格缺口 4 項、Character Library 與 Project 綁定、D-063 中文輸入缺口（Advanced 英文覆寫語意、視覺偏好中文輸入、場景卡增減角色）。
- 禁止直接做：付費／API key、下載未核准模型、改 production default、Model Router、DG-19 UI、lip-sync 模型、刪 SD1.5、pickle/ckpt/bin、LoRA 訓練、把 MeinaMix 當商用。


> 入口是 `docs/HANDOFF.md`；本文件是 Coding Agent 專用補充（工作方式、慣例、快速啟動）。本文件描述「規則與做法」，不描述「現在在哪」——現況一律看 `PROJECT_STATE.md` 並與 GitHub 比對。

## 0. 開工第一件事：Recovery Protocol（PROJECT_RULES §11.5）
```bash
git fetch origin && git status -sb && git branch -a
git log --oneline -10 origin/main; git log --oneline -10            # main 與目前分支
# open/draft PR 與 CI：用 GitHub 工具查 Actions workflow `ci.yml` 最近一次 run 的 conclusion
python -m pytest -q                                                   # 必須全綠才算「已驗證」
```
然後讀：`PROJECT_RULES.md` → `docs/PROJECT_STATE.md` → `docs/DECISIONS.md` → `docs/BACKLOG.md` → 本文件 → `docs/ARCHITECTURE.md`。
文件與 GitHub 不一致 → GitHub 為準，先修文件再動功能。

## 1. 專案目標
使用者在手機／電腦的 Web UI 貼入中文文章／故事，系統自動完成：
文字理解 → 劇本 → 分鏡 → 圖片 → 動畫 → 配音 → 音效/BGM → 字幕 → 剪輯 → QA → Preview → 人工修改/核准 → Final Video。
目前只做「最小、可驗證、免費優先」的階段性 MVP；不一次開發完整產品。

## 2. 架構摘要（細節見 ARCHITECTURE.md）
- 結構化資料驅動：AI 只產出經 Pydantic 驗證的 `Script` / `Scene`；影片由確定性 `Timeline` + FFmpeg 合成。
- `see/providers/base.py`：LLM / Image / Video / TTS / Audio / LipSync 六個介面；`registry.py` 依設定組裝。
- `see/workers/`：`Task` / `Executor`；Phase 0 只有 `LocalExecutor`。
- `see/pipeline/orchestrator.py`：串接、per-scene fingerprint 快取（改一景不重做其他景）、狀態機、成本閘門。
- `see/ui/`：FastAPI + 單頁 HTML + `BackgroundRunner`（單 worker，未來換 queue）。
- Storage SSOT：`workspace/projects/<id>/project.json` 與 `scenes/<id>/manifest.json`。

## 3. 永久護欄（PROJECT_RULES.md 全文有效，這裡只是提醒）
Free First／Provider Agnostic／Compute Agnostic／Local First AI／Human Approval Gate／結構化 schema／成本標記／不 commit secrets 與大型媒體／第三方碼先查 License／§11 交接與恢復制度。
**PAID provider 無 Approval 一律拒絕執行；Local 失敗不得自動切 PAID。**

## 4. 目前 Phase、已完成、未完成
以 `PROJECT_STATE.md` 為準。摘要：Phase 0 pipeline（CLI）與最小 Web UI 已完成並有證據（`PHASE0_EVIDENCE.md`）；Phase 1 SD 1.5 本機生圖已於 GTX 1650 真機完成（`PHASE1_EVIDENCE.md`，D-024）；真正 Video、自然 TTS、Ollama、BGM/SFX、lipsync、QA、NAS/GPU、登入皆未做（BACKLOG「Phase 1 收尾盤點」表）。Phase 2 方向待使用者裁示。

## 5. Current Task 與下一個安全動作
- Current Task：看 `PROJECT_STATE.md`。
- 若 STATE 顯示在等裁示：只能做 BACKLOG 標示「可自主」的安全、免費、可逆項目，或修文件／測試；不得自行選 Provider、不得開新功能線。

## 6. 停手條件（停止並詢問）
需要付費／API Key／OAuth／新外部帳號／下載大型模型／License 不清楚／不可逆重大架構改動／必須選特定 AI Provider／需要 NAS/GPU 硬體資訊／Spec 重大缺口。

## 7. 工作方式
- Checkpoint Rule（§11.3）：implementation → tests → commit → 更新 STATE → 下一批。
- Conversation End Protocol（§11.4）：換對話前必須完成 10 步並在 SESSION_LOG append。
- 靜默自主巡航（§11.7）：只有需裁示、停手條件、整批完成才回報。
- 回報格式：SHA、測試結果、產出是否成功、實際成本、已完成、未完成、下一個 Decision Gate。
- 每批開頭標示 **Model / Mode / Effort**。預設 Model：Claude Fable 5.1；Mode：靜默自主巡航；Effort：Minimum Sufficient Effort——架構／憲章級工作 High，一般實作 Medium，文件／小修 Low。可自行下調，不可因省事跳過測試與證據。
- 使用者偏好：全程繁體中文（台灣）；程式碼附內部審核（邏輯審查／邊界測試／效能評估）；防禦性設計與向量化；SSOT 原則。
- Commit 訊息不含模型識別字串；不得 push 到未授權分支；不自行開 PR。
- 分支慣例：功能開發在指派分支；`main` 只以 fast-forward 指向已驗證 SHA（tests 全綠、tree clean、remote 未漂移），不在 main 上重新產生內容。
- AI Image：`DiffusersImageProvider` 絕不自動下載權重；下載是人工步驟且需使用者同意（停手條件）。實機已有模型於 `D:\ai-models\sd15`（使用者 Windows PC，GTX 1650 4 GB）。
- 影像產物一律經 `see/core/image_qa.image_defect` 驗證（快取重用前、生成後、fallback 候選後）；fingerprint 只證明輸入沒變，不證明產物可用；`providers.image.name` 不是生成證據，看 manifest `meta` / CLI `image_evidence`（D-021）。改變 provider 輸出行為時必須 bump `ProviderInfo.version`。runtime 降級階梯所需的權重必須與 `image-download` 實際下載內容一致（`pick_variant`，D-022）；fp32 升級用 fp16 檔 upcast，不另外下載。fallback 產物會標 `meta.degraded=true`，首選 provider 可用時下一次 run 自動重試（D-023）；`regen <project> <scene>` 清該景 manifest 並重做全部資產，無 asset 參數。
- 所有 subprocess 一律走 `see/core/proc.run_text`（UTF-8，不依賴 Windows locale）；不得再用 `subprocess.run(text=True)`（D-020）。
- Web UI 只綁 127.0.0.1 或可信任區網（`--lan`）；不得開到 Internet（D-011）。

## 8. 必讀文件順序
1. `PROJECT_RULES.md` 2. `docs/PROJECT_STATE.md` 3. `docs/DECISIONS.md` 4. `docs/BACKLOG.md` 5. 本文件 6. `docs/ARCHITECTURE.md` 7. `docs/PHASE0_EVIDENCE.md`（需要證據時） 8. `docs/AI_IMAGE_PROVIDER_PLAN.md`、`docs/AI_IMAGE_SD15_WINDOWS.md`、`docs/PHASE1_EVIDENCE.md`（AI Image Phase）

## 9. 快速啟動
```bash
pip install -r requirements.txt            # 系統另需 ffmpeg/ffprobe；建議 espeak-ng + CJK 字型
python -m see.app.cli check-env
python -m see.app.cli run examples/story_short.txt --project-id demo01
python -m see.ui --lan      # 手機開 http://<IP>:8000/
python -m pytest -q
```
