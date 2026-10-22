# HANDOFF.md — 交接狀態

更新：2026-10-22（Phase 0 + Web UI 完成）

## 目前狀態
- `main` = `026206c`（Phase 0）。Web UI 開發於 `ccr-2968bce1-ym4kkc`，待使用者決定是否併入 main。
- Web UI：`uvicorn see.ui.server:app --host 0.0.0.0 --port 8000` → 貼故事 → 建立 Preview → 播放 → 單景修改／重做 → 核准 → Final。證據：`docs/PHASE0_EVIDENCE.md §7`。
- Phase 0 成功條件達成：短中文故事 → `preview.mp4`（47 秒、H.264/AAC、可解碼）。證據：`docs/PHASE0_EVIDENCE.md`。
- 測試：`python -m pytest -q` → 42 passed。
- 實際成本：0（全部 LOCAL_FREE）。

## 快速開始
```bash
pip install -r requirements.txt       # pydantic, pillow, pytest
# 系統需求：ffmpeg + ffprobe（必要）、espeak-ng（建議；沒有則自動退到 silent TTS）、CJK 字型
python -m see.app.cli check-env
uvicorn see.ui.server:app --host 0.0.0.0 --port 8000     # Web UI（手機開 http://<IP>:8000/）
python -m see.app.cli run examples/story_short.txt --project-id demo01
python -m see.app.cli set-scene demo01 scene_003 --narration "..."     # 只重做 scene_003
python -m see.app.cli approve demo01 --by <name> && python -m see.app.cli final demo01
```

## 先讀
1. `PROJECT_RULES.md`（憲章）
2. `docs/ARCHITECTURE.md`（目錄、資料模型、Provider / Executor 介面、fingerprint 快取）
3. `docs/DECISIONS.md`（為什麼這樣做）
4. `docs/BACKLOG.md`（下一步 + Decision Gates）

## 下一個 Decision Gate
- DG-5：Web UI 存取控制（無登入 vs. 簡單 token）；edge-tts 需在可連網機器驗證（DG-3 待辦）。
在這些裁示前，可自主進行的安全工作：QA 階段（LUFS / 黑幀 / 字幕長度檢查）、BGM 的 AudioProvider（程序化或免費素材）、
`cut` 真硬切、Scene seed 控制。

## SSOT
- Project 狀態唯一來源：`workspace/projects/<id>/project.json`。
- 每景產物與 fingerprint：`scenes/<scene_id>/manifest.json`。
- 規則：`PROJECT_RULES.md`；決策：`docs/DECISIONS.md`。
