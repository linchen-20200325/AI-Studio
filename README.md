# see

**see** — 把中文文章／故事，自動變成一支可播放的影片。

> 文字理解 → 劇本 → 分鏡 → 圖片 → 動畫 → 配音 → 音效/BGM → 字幕 → 剪輯 → QA → Preview → 人工修改/核准 → Final Video

目前階段：**Phase 0（最小可驗證 MVP）**。

```
中文文字 → 結構化劇本 → Storyboard → Timeline → 免費 TTS → 字幕 → FFmpeg 合成 → preview.mp4
```

Phase 0 不做真正的 AI Video，只用 placeholder 圖片 + Ken Burns + 轉場 + 中文旁白 + 字幕，證明整條鏈路成立。

## 文件

- [PROJECT_RULES.md](PROJECT_RULES.md) — 永久規則（Free First / Provider Agnostic / Compute Agnostic / Local First AI / Human Approval Gate）
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — 架構與資料模型
- [docs/DECISIONS.md](docs/DECISIONS.md) — 決策紀錄
- [docs/BACKLOG.md](docs/BACKLOG.md) — 待辦
- [docs/STATE.md](docs/STATE.md) — 目前狀態快照
- [docs/HANDOFF.md](docs/HANDOFF.md) — 交接文件索引（Project AI / ChatGPT / SESSION_LOG）

## 快速開始

```bash
pip install -r requirements.txt
# 系統需求：ffmpeg + ffprobe（必要）、espeak-ng（建議）、CJK 字型（字幕）
python -m see.app.cli check-env
python -m see.ui --lan   # Web UI：手機開 http://<IP>:8000/
python -m see.app.cli run examples/story_short.txt --project-id demo01
#   → workspace/projects/demo01/renders/preview.mp4
python -m see.app.cli set-scene demo01 scene_003 --narration "新的旁白"   # 只重做 scene_003
python -m see.app.cli approve demo01 --by <name>
python -m see.app.cli final demo01                                       # → renders/final.mp4
python -m pytest -q
```

Phase 0 證據：[docs/PHASE0_EVIDENCE.md](docs/PHASE0_EVIDENCE.md)
