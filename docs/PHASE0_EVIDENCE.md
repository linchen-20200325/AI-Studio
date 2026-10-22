# PHASE0_EVIDENCE.md — Phase 0 驗證證據

日期：2026-10-22。環境：Linux 容器、Python 3.13.16、ffmpeg 6.1.1（libx264/libass）、espeak-ng 1.51、字型 WenQuanYi Zen Hei。
所有步驟皆為 LOCAL_FREE，實際成本 0。

## 1. 端到端命令

```bash
python -m see.app.cli run examples/story_short.txt --project-id demo01
# 138 字中文故事 → 5 景 → preview.mp4（約 23 秒 wall time，4 核 CPU）
```

## 2. 輸出檔驗證（`workspace/projects/demo01/renders/preview.mp4`，未 commit）

```
codec_name=h264  width=1280 height=720 r_frame_rate=25/1
codec_name=aac   sample_rate=44100 channels=2
duration=46.83 s  size=3,489,724 bytes  bit_rate=596 kbps
ffmpeg -v error -i preview.mp4 -f null -   → rc=0，無解碼錯誤
sha256(preview.mp4) = e498271ede46287b695aac8024aafdf26cc57a3e1a3eb22e2d4cd1eee71aaa55
sha256(final.mp4)   = b9c3fa4d61bbca81e9cb5b5960661f2a44f36a68294a1b481745252459842e24
volumedetect: mean −23.6 dB / max −4.1 dB（旁白確實有聲音，非靜音）
```

Timeline（`renders/preview.json`）：

| scene | start | end | transition_in | dur |
|---|---|---|---|---|
| scene_001 | 0.000 | 10.593 | fade | 0.0 |
| scene_002 | 10.093 | 19.523 | dissolve | 0.5 |
| scene_003 | 19.023 | 29.125 | wipe_left | 0.5 |
| scene_004 | 28.625 | 39.703 | fade | 0.5 |
| scene_005 | 39.203 | 46.763 | fade | 0.5 |

畫面抽樣（每 2 景取一幀 + 轉場中幀）：[`evidence/preview_contact_sheet.jpg`](evidence/preview_contact_sheet.jpg)
可見：placeholder 圖、Ken Burns 位移、燒錄中文字幕、wipe 轉場、第 3 景修改後的新字幕。

## 3. 單景修改不重做其他景（Human Approval Gate 技術基礎）

```bash
python -m see.app.cli set-scene demo01 scene_003 --narration "老和尚用草藥替小鳥敷了傷口，叮嚀小和尚每天餵牠喝水、陪牠說話。"
scene_001: rebuilt=[] reused=['image', 'narration', 'subtitle', 'clip']
scene_002: rebuilt=[] reused=['image', 'narration', 'subtitle', 'clip']
scene_003: rebuilt=['narration', 'subtitle', 'clip'] reused=['image']
scene_004: rebuilt=[] reused=['image', 'narration', 'subtitle', 'clip']
scene_005: rebuilt=[] reused=['image', 'narration', 'subtitle', 'clip']
```

`tests/test_pipeline_e2e.py::test_editing_one_scene_does_not_touch_others` 以 sha256 驗證其他景的檔案 byte-for-byte 不變。

## 4. 核准閘門

```bash
python -m see.app.cli final demo01      # → ERROR [InvalidTransition] final render requires APPROVED, project is PREVIEW
python -m see.app.cli approve demo01 --by user   # → demo01: APPROVED
python -m see.app.cli final demo01      # → status FINAL, renders/final.mp4
```

PAID provider 無核准 → `PaidProviderNotApproved`；有核准但超過 budget（預設 0）→ `BudgetExceeded`（`tests/test_cost_gate.py`）。
Fallback 鏈遇到 PAID 候選即停止、不呼叫（`test_fallback_never_crosses_into_paid`）。

## 5. 測試

```
python -m pytest -q
38 passed
```

涵蓋：schema 驗證、字幕切句、Mock LLM 確定性、placeholder 圖、Silent/espeak TTS、zoompan 表達式、
成本閘門、Executor 能力配對、E2E（preview 可播放、二次重跑全部重用、單景修改、字幕覆寫、單景重做、核准→final、CLI）。

## 6. 已知限制

- 旁白品質：espeak-ng 中文為機械音，僅證明鏈路；神經 TTS 待 DG-3。
- 分鏡品質：Mock LLM 為規則切句，無理解能力；待 DG-2。
- 總長度由輸入字數與 TTS 語速決定（約 3 字/秒 @ 200 wpm）；138 字 → 47 秒。超過 60 秒不會自動刪減原文。
- `cut` 轉場以 0.08 秒 fade 模擬；字幕在轉場重疊區會跟著淡出。
- 無 BGM / SFX（NullAudioProvider）。
- edge-tts（FREE_TIER）在此容器因網路政策無法連線，未實測。
