# HANDOFF_PROJECT_AI.md — 給 Coding Agent（Claude Code 等）的恢復手冊

> 新的 Project AI 對話只靠 GitHub + 本文件即可恢復工作。本文件描述「規則與做法」，不描述「現在在哪」——現況一律看 `STATE.md` 並與 GitHub 比對。

## 0. 開工第一件事：Recovery Protocol（PROJECT_RULES §11.5）
```bash
git fetch origin && git status -sb && git branch -a
git log --oneline -10 origin/main; git log --oneline -10            # main 與目前分支
# open/draft PR 與 CI：用 GitHub 工具查 Actions workflow `ci.yml` 最近一次 run 的 conclusion
python -m pytest -q                                                   # 必須全綠才算「已驗證」
```
然後讀：`PROJECT_RULES.md` → `docs/STATE.md` → `docs/DECISIONS.md` → `docs/BACKLOG.md` → 本文件 → `docs/ARCHITECTURE.md`。
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
以 `STATE.md` 為準。摘要：Phase 0 pipeline（CLI）與最小 Web UI 已完成並有證據（`PHASE0_EVIDENCE.md`）；真正 AI Image/Video、神經 TTS、Ollama、BGM、QA、NAS/GPU、登入皆未做（BACKLOG）。

## 5. Current Task 與下一個安全動作
- Current Task：看 `STATE.md`。
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
- 影像產物一律經 `see/core/image_qa.image_defect` 驗證（快取重用前、生成後、fallback 候選後）；fingerprint 只證明輸入沒變，不證明產物可用；`providers.image.name` 不是生成證據，看 manifest `meta` / CLI `image_evidence`（D-021）。改變 provider 輸出行為時必須 bump `ProviderInfo.version`。runtime 降級階梯所需的權重必須與 `image-download` 實際下載內容一致（`pick_variant`，D-022）；fp32 升級用 fp16 檔 upcast，不另外下載。
- 所有 subprocess 一律走 `see/core/proc.run_text`（UTF-8，不依賴 Windows locale）；不得再用 `subprocess.run(text=True)`（D-020）。
- Web UI 只綁 127.0.0.1 或可信任區網（`--lan`）；不得開到 Internet（D-011）。

## 8. 必讀文件順序
1. `PROJECT_RULES.md` 2. `docs/STATE.md` 3. `docs/DECISIONS.md` 4. `docs/BACKLOG.md` 5. 本文件 6. `docs/ARCHITECTURE.md` 7. `docs/PHASE0_EVIDENCE.md`（需要證據時） 8. `docs/AI_IMAGE_PROVIDER_PLAN.md`、`docs/AI_IMAGE_SD15_WINDOWS.md`（AI Image Phase）

## 9. 快速啟動
```bash
pip install -r requirements.txt            # 系統另需 ffmpeg/ffprobe；建議 espeak-ng + CJK 字型
python -m see.app.cli check-env
python -m see.app.cli run examples/story_short.txt --project-id demo01
python -m see.ui --lan      # 手機開 http://<IP>:8000/
python -m pytest -q
```
