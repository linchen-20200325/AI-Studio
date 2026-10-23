# PHASE2_EVIDENCE.md — Phase 2（自然中文 TTS）真機證據

> 驗收證據只寫事實與使用者回報；裁示在 `DECISIONS.md`，現況在 `PROJECT_STATE.md`。

## E2-1 Kokoro-82M v1.1-zh 候選技術驗證（2026-10-23，使用者 Windows 真機）
核准依據：D-027（Candidate Validation Approval，**非** Final Provider Approval）。程式版本：`59bbdd2`（Batch 15）。

### 環境
Windows · GTX 1650 4 GB（**TTS 走 CPU**，`SEE_TTS_DEVICE=cpu`）· torch 2.14.1+cu126 · `.venv`。

### 下載／provenance（使用者回報，來自 `provenance.json`）
| 欄位 | 值 |
|---|---|
| repo | `hexgrad/Kokoro-82M-v1.1-zh` |
| revision | `01e7505bd6a7a2ac4975463114c3a7650a9f7218` |
| 權重 | `kokoro-v1_1-zh.pth` ≈329.3 MB |
| model sha256 | `b1d8410fa44dfb5c15471fd6c4225ea6b4e9ac7fa03c98e8bea47a9928476e2b` |
| voices | `zf_001`、`zf_002`、`zm_009`、`zm_010` |
| 授權 | Apache-2.0 |
| 成本 | NT$0 |

### 技術結果
- `tts-check`：`available=true`；四個 voice 皆被辨識並實際產出 WAV；無 fallback、無 silent provider。
- 未量到：`synth_seconds`／`rtf`／`load_seconds`、CPU／RAM 峰值、與 SD 1.5 同一次 `run` 共存、五景 pipeline（`tts_evidence`、duration／字幕對齊）→ 見 E2-2（待做）。

### 使用者主觀聽感（**單一使用者真機聽感，不是模型客觀品質排名**）
| voice | 回報 |
|---|---|
| zf_001 | 大陸口音很明顯；不建議作預設 |
| zf_002 | 比 zf_001 好一些；仍非目前最佳 |
| zm_009 | 無明顯大陸口音；自然度「還行」 |
| zm_010 | 比 zm_009 更自然；四者中使用者目前最偏好 |

結論（事實層）：Kokoro 在此環境**技術可用**；聽感可接受度依 voice 差異大；zf_001 口音為已知使用者體驗限制。

## E2-2 Kokoro 五景 pipeline 整合（待真機）
命令：`python -m see.app.cli run examples\story_short.txt --project-id kokorotest --voice zm_010`。需回報：每景 `tts_evidence.generated_by=kokoro-tts`、`voice`、`rtf`、`duration`；preview 有聲且字幕對齊；`image_evidence` 仍為 `diffusers-sd15`（Phase 1 路徑未受影響）；工作管理員 CPU／RAM 峰值；總耗時。
