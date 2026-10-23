# AI_TTS_KOKORO_WINDOWS.md — Phase 2 候選：Kokoro-82M v1.1-zh 在 Windows（CPU）

D-027：**Candidate Validation Approval**（候選驗證核准，不是最終採用）。程式端已就緒（`see/providers/tts/kokoro.py`）；本文件是使用者在 Windows 真機要做的事。一次只做一步，回報結果再做下一步（PROJECT_RULES §14）。

## 1. 要下載什麼（≈330 MB，只抓需要的檔）
`hexgrad/Kokoro-82M-v1.1-zh`（Apache-2.0）：`config.json`、`kokoro-v1_1-zh.pth`（≈327 MB）、4 個 voice（`zf_001`、`zf_002`、`zm_009`、`zm_010`，各 ≈0.5 MB；repo 缺該名稱時自動改抓前 2 女 2 男）。
存放：`%SEE_MODELS_DIR%\kokoro-v1_1-zh`（與 SD 1.5 同一個 `D:\ai-models`）。下載器寫 `provenance.json`（repo、commit sha、每檔 bytes／sha256、時間、授權、核准編號）。**程式永不自行下載**；只有 `tts-download --yes` 會下載。

## 2. 執行方式（程式自動）
- 預設 `SEE_TTS_DEVICE=cpu`：不占 GTX 1650 的 4 GB VRAM，與 SD 1.5 串行共存。可改 `cuda` 實驗。
- `auto` 鏈：`kokoro → espeak → silent`。kokoro 套件或權重缺少 → 跳過；推理失敗／輸出靜音 → ProviderError → 下一候選，並在 manifest 記 `degraded=true`；kokoro 恢復後該景旁白自動重做（同 D-023）。
- `scene.voice`：`default` → 第一個 `zf_*`；或填 voice id（例如 `zm_009`）；未知 id fail-closed。
- 證據：CLI 總結 `tts_evidence`（generated_by／voice／device／rtf／model_sha256）、UI 景卡「聲：…」。

## 3. 使用者步驤（在專案根目錄、已 `.venv\Scripts\activate`；每行一步）
```
pip install "kokoro>=0.9" "misaki[zh]>=0.9"
set SEE_MODELS_DIR=D:\ai-models
python -m see.app.cli tts-download --yes
python -m see.app.cli tts-check
python -m see.app.cli tts-check --voice zm_009 --out tts_check_m.wav
set SEE_TTS_PROVIDER=auto
python -m see.app.cli run examples\story_short.txt --project-id kokorotest
```
`python -m see.app.cli tts-setup` 會印出同樣的步驟與目前狀態。

## 4. 真機要回報的項目（DG-13 裁示依據）
中文發音是否正確、自然度、大陸口音明顯度、`zf_*` 與 `zm_*` 差異、`tts-check` 的 `synth_seconds`／`rtf`／`load_seconds`、工作管理員 CPU／RAM（VRAM 應為 0）、與 SD 1.5 同一次 `run` 是否共存、`tts_evidence` 每景 `generated_by=kokoro-tts`、`duration` 與字幕對齊、刻意填錯 voice 時是否 fail-closed。

## 5. 真機結果
- 2026-10-23 E2-1（安裝／下載／`tts-check` 四 voice）：成功；細節與聽感見 `PHASE2_EVIDENCE.md`。
- 2026-10-23 E2-2（五景 `run … --voice zm_010`）：成功，Kokoro CPU 與 SD 1.5 GTX 1650 共存、無 fallback、穩態 RTF ≈0.30；見 `PHASE2_EVIDENCE.md`。目前無待做 Windows 步驟，等待 DG-13。
- `python -m see.app.cli tts-voices` 列出本機 voice 的 id／可讀名稱／性別／已知限制。
