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

## D-009 2026-10-22 裁示紀錄（使用者）
- DG-1：以 `026206c` 建立 `main`（已完成，local/remote 一致）。
- DG-2：暫緩 Ollama／大型本機 LLM；不下載模型；保留 LLMProvider 架構。
- DG-3：edge-tts 僅在可連網環境驗證；必須 FREE_TIER／零 key／零付費。本容器 DNS 無法解析 `speech.platform.bing.com`，尚未實測。
- DG-4：Web UI 採 FastAPI + 簡單手機友善單頁。

## D-010 2026-10-22 Web UI 最小設計
- 無框架前端（單一 index.html，vanilla JS 輪詢），避免建置鏈與相依。
- `BackgroundRunner`：ThreadPoolExecutor(1) 作為 Phase 0.5 的 queue 替身；介面只有 submit/status，為 NAS queue 預留。
- 影片以 FileResponse 直出並支援 Range；不做轉碼或串流伺服器。
- 「影片長度」設定以旁白語速（0.85/1.0/1.2）實作：總長由字數決定，語速是唯一誠實可調的長度參數；不自動刪改原文。
- 幣別改為 TWD 預設（使用者在台灣），顯示 `NT$0`。
- 已知：headless Chromium 無 H.264 解碼，故 Playwright 煙霧測試只驗證頁面流程與 206 Range，不驗證瀏覽器內播放；手機 Safari/Chrome 皆原生支援 H.264/AAC。

## D-011 2026-10-22 DG-5 裁示：Web UI 第一版限可信任區網
- 暫不開 Internet、不做帳號／OAuth／公開 tunnel。Server 預設不得無意間公開：`python -m see.ui` 只綁 127.0.0.1，`--lan` 才綁 0.0.0.0 並印出警告。
- 未來 NAS 正式部署／遠端使用時另開 Access Control Decision Gate。

## D-012 2026-10-22 edge-tts 連網驗證結果
- 本容器網路政策無法解析 `speech.platform.bing.com`（DNS 失敗），**無法在此環境完成驗證**；需在可連網機器執行 `SEE_TTS_PROVIDER=edge python -m see.app.cli run examples/story_tiny.txt`。
- 授權：`edge-tts` 7.3.1 為 LGPLv3；本專案僅以 optional、延遲 import 使用，不打包、不修改其原始碼，相容。
- 疑義（依裁示停止並回報）：該套件呼叫的是微軟 Edge「大聲朗讀」非官方端點，服務條款未明示允許第三方程式使用，可用性與合規性無保證。因此維持：optional、非預設、不移除 espeak／silent fallback；是否採用待使用者裁示（DG-6）。

## D-013 2026-10-22 main 快進與 repository 實況
- `main` 以 fast-forward 指向已驗證治理版本 `1e42a81`（Recovery Verification：tree clean、remote 未漂移、42 passed）。
- GitHub 實況：`linchen-20200325/AI-Studio`，**visibility = public**；GitHub 預設分支仍是 `ccr-2968bce1-ym4kkc`（非 main）。兩者皆為 repo 設定，非程式問題，由使用者決定是否改為 private / 將預設分支改為 main。
