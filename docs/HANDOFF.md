# HANDOFF.md — 新 AI 對話入口（導航頁，不放狀態）

## ⛳ 最終交接 checkpoint（2026-10-23 封存；以 GitHub main HEAD 為準）
- 最後驗證 main：以 GitHub main HEAD 為準（D-045 文件 commit；CI 見 Actions）。開發分支 `ccr-297bf146-zrrlk1`。
- 已完成：Phase 0／0.5／1；Phase 2 進行中：Kokoro TTS（D-027／D-029，真機 validated）、Voice Selection／Character Voice（`zm_010`＝目前使用者偏好候選，非永久鎖定，DG-14）、BGM/SFX＋ducking（SFX 人工聽感未驗）、Style Profile、Character Consistency foundation（僅 prompt 錨點，無 IP-Adapter/LoRA）、Lip-sync 介面（無實際模型）、checkpoint 型錄／下載驗證／single-file 載入／clip-skip 相容（D-039／D-040；**不是** Model Router，Router 未實作）。
- E2-5：MeinaMix V12 native 近景真機成功；`style-compare` vs Base native＝**model_preset_level**（只差 model＋clip skip 2 vs 1，unexpected=[]）；客戶「這樣 OK」scene PASS／style PASS（single-user subjective）；DG-23 已裁示接受（D-045）→ MeinaMix＝目前 P1 日系動畫**品質驗證通過**；**不永久鎖定模型／畫風**（§15 Preference Layer）、**commercial_cleared=false**、不得商用。
- `fair_comparison`：已更名 `baseline_condition`；跨次比較一律 `style-compare`（D-043／D-044）。
- CyberRealistic：已下載；東亞女性 technical PASS＋客戶確認東方女性；東亞男性外觀確認但 JSON 未入庫（single-user subjective，D-047）；commercial_cleared=false；upstream lineage 未釐清；未鎖定為預設。
- production default **未變**（gen_policy=fit、base SD1.5、預設 style）。
- 本機：Windows、GTX 1650 4 GB（fp16 會 NaN → 自動 float32）、SD1.5 於 `D:\ai-models\sd15`、checkpoints 於 `SEE_MODELS_DIR\checkpoints\<id>\`（永不進 Git）。
- **下一唯一安全接手點**：DG-25 已核准（D-054），程式完成。Windows 一次一條：`git pull` → `python -m see.app.cli adapter-download ip_adapter_plus_face_sd15 --check` → `--yes` → `style-test --style realistic --case two_characters_ab --gen-policy native --checkpoint cyberrealistic_final --scheduler dpmpp_2m_karras --identity ip_adapter_plus_face_sd15 --ref char_a=<東亞女性 portrait stem> --ref char_b=<東亞男性 portrait stem>` → style-compare 對 D-049 基準 → style-review。
- 禁止直接做：付費／API key、下載未核准模型、改 production default、Model Router、DG-19 UI、lip-sync 模型、刪 SD1.5、pickle/ckpt/bin、LoRA 訓練、把 MeinaMix 當商用。


> **Do not depend on previous ChatGPT or Claude conversation context. Reconstruct state from GitHub.**
> GitHub repository `linchen-20200325/AI-Studio` 是唯一長期記憶（PROJECT_RULES §12）。ChatGPT Memory／Claude Memory／舊對話都不是正式儲存層。

## 1. First read（依序）
1. [`PROJECT_RULES.md`](../PROJECT_RULES.md) — 永久規則（Free First、Provider/Compute Agnostic、Human Approval、停手條件、§11 交接、§12 GitHub Memory、§13 Model/Effort/Token Gate、§14 Windows 互動）
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
