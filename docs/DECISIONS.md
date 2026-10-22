# DECISIONS.md — 決策紀錄

格式：日期 / 決策 / 理由 / 替代方案 / 影響。

## D-001 2026-10-22 專案名稱與 repo
- 決策：專案名 `see`，Python 套件名 `see`，repo = `linchen-20200325/AI-Studio`。
- 開發分支：`ccr-2968bce1-ym4kkc`（指派分支）。repo 原本無任何 commit，`main` 尚不存在；是否以此分支建立 `main` 由使用者裁示。

## D-002 2026-10-22 參考專案授權
- `Hao0321/video-autopilot-kit` 為 MIT License（Copyright (c) 2026 Hao0321 Studio）。
- 決策：**不複製任何程式碼**，只借鏡思路（見 ARCHITECTURE §10）。因此無需附帶其 LICENSE。
- 其渲染端 Editkin 為 GPL-3.0 且為 Windows 桌面程式，不納入。

## D-003 2026-10-22 Phase 0 TTS 選擇
- 本環境可用：`espeak-ng`（apt 安裝，LOCAL_FREE，Mandarin `cmn` 語音，品質低）。
- `edge-tts`（FREE_TIER，不需 key）在本環境被網路政策擋下（DNS 解析失敗），實作為 optional provider 但預設不啟用。
- 決策：`SEE_TTS_PROVIDER=auto` → 順序 espeak → silent。`silent` 為靜音 + 字數估時長，保證離線 pipeline 永遠可跑。
- 不自動 fallback 到任何 PAID TTS（PROJECT_RULES §4）。

## D-004 2026-10-22 Phase 0 LLM
- 環境無本機 LLM（無 Ollama / 權重），無免費 API。
- 決策：`MockLLMProvider` 以確定性規則（句號／驚嘆號／問號切句、按字數分景、3–12 秒/景、目標 30–60 秒）產出 `ScriptDraft` / `StoryboardDraft`。
- 介面 `LLMProvider.complete_json(LLMRequest) -> BaseModel` 已為真正 LLM 預留；接 Ollama 時只需新增 provider。

## D-005 2026-10-22 影片合成策略
- 兩段式：每景先產 `clip.mp4`（zoompan Ken Burns + 旁白 + 燒錄字幕），再以 `xfade` + `acrossfade` 組裝。
- 理由：每景 clip 可 fingerprint 快取，修改單一 Scene 不重做其他 Scene；組裝階段成本低可每次重做。
- 替代方案（單一 filter_complex 一次合成）被否決：無法做 per-scene 快取。
- 限制：`cut` 轉場以極短（0.08s）fade 模擬；字幕在轉場重疊區會跟著淡入淡出。

## D-006 2026-10-22 字幕
- 以 libass `subtitles` filter 燒錄 SRT，字型用 fontconfig 偵測 CJK 字型（本環境：WenQuanYi Zen Hei）。
- 切句：按中文標點切，每行上限 18 字，時間按字數比例分配在旁白實際時長內。

## D-007 2026-10-22 影像規格
- 預設 1280×720 @ 25fps、H.264 yuv420p、AAC 44.1kHz stereo。Placeholder 圖以 1920×1080 產生再縮放以減少 zoompan 抖動。

## D-008 2026-10-22 不做的事（放 BACKLOG）
- 付費 API、Lip Sync、真正 AI Video、登入系統、NAS 部署、GPU Worker、Web UI。
