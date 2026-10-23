# HANDOFF.md — 新 AI 對話入口（導航頁，不放狀態）

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
