# HANDOFF.md — 新 AI 對話入口（導航頁，不放狀態）

> **Do not depend on previous ChatGPT or Claude conversation context. Reconstruct state from GitHub.**
> GitHub repository `linchen-20200325/AI-Studio` 是唯一長期記憶（PROJECT_RULES §12）。ChatGPT Memory／Claude Memory／舊對話都不是正式儲存層。

## 1. First read（依序）
1. [`PROJECT_RULES.md`](../PROJECT_RULES.md) — 永久規則（Free First、Provider/Compute Agnostic、Human Approval、停手條件、§11 交接、§12 GitHub Memory、§13 Model/Effort/Token Gate、§14 Windows 互動）
2. [`docs/PROJECT_STATE.md`](PROJECT_STATE.md) — 現在仍有效的狀態、Decision Gate、下一步、已驗證環境
3. [`docs/BACKLOG.md`](BACKLOG.md) — 所有未完成工作（含能力盤點、Phase 2 建議、Windows／模型／裁示標示）
4. [`docs/DECISIONS.md`](DECISIONS.md) — 已裁示事項（D-001～；superseded 有標示）
5. 證據：[`PHASE0_EVIDENCE.md`](PHASE0_EVIDENCE.md)、[`PHASE1_EVIDENCE.md`](PHASE1_EVIDENCE.md)、[`TTS_PROVIDER_PLAN.md`](TTS_PROVIDER_PLAN.md)（DG-9 研究）
6. 技術文件：[`ARCHITECTURE.md`](ARCHITECTURE.md)、[`AI_IMAGE_SD15_WINDOWS.md`](AI_IMAGE_SD15_WINDOWS.md)、[`AI_IMAGE_PROVIDER_PLAN.md`](AI_IMAGE_PROVIDER_PLAN.md)
7. 歷史：[`SESSION_LOG.md`](SESSION_LOG.md)（不必掃完才能知道現況）

## 2. Then verify GitHub（Verification Gate，PROJECT_RULES §11.5／§11.6）
`main` HEAD 與開發分支 HEAD、最近 commits、open/draft PR、Actions `ci.yml` conclusion、`python -m pytest -q`、working tree。文件與 GitHub 不一致 → GitHub 為準，先修文件再動功能。

## 3. Current handoff（細節一律看 PROJECT_STATE／BACKLOG，這裡不複製）
- Phase：見 `PROJECT_STATE.md`「Current Phase」。
- Decision Gate：見 `PROJECT_STATE.md`「Current Decision Gate」。
- Next action：見 `PROJECT_STATE.md`「Current next action」。

## 4. 角色專用補充（與本頁不重複；漂移時以本頁 + PROJECT_STATE 為準）
| 我是 | 看 |
|---|---|
| Coding Agent（Claude Code／Project AI） | [`HANDOFF_PROJECT_AI.md`](HANDOFF_PROJECT_AI.md)（工作方式、快速啟動、程式慣例） |
| 治理／協作 AI（ChatGPT） | [`HANDOFF_CHATGPT.md`](HANDOFF_CHATGPT.md)（治理方式、審核清單） |

## 5. 文件責任（PROJECT_RULES §12.2）
PROJECT_RULES＝永久規則｜PROJECT_STATE＝現在｜BACKLOG＝未完成｜DECISIONS＝裁示｜SESSION_LOG＝歷史｜*_EVIDENCE＝驗收｜HANDOFF＝導航。`docs/STATE.md` 僅為相容指標，內容在 PROJECT_STATE。
