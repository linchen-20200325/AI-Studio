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
- [docs/HANDOFF.md](docs/HANDOFF.md) — 交接狀態
