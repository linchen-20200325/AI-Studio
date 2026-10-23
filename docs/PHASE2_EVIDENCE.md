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

## E2-2 Kokoro 五景 pipeline 整合（2026-10-23，使用者 Windows 真機）— 完成
程式版本：`4bcae5c`（Batch 16）。命令：
```
python -m see.app.cli run examples\story_short.txt --project-id kokorotest --voice zm_010
```
### 結果（使用者回報）
- 整體：status=PREVIEW · 5 景 · preview 42.4 s · 1280×720 · has_video=true · has_audio=true · 成本 NT$0。
- Image（Phase 1 路徑未受影響）：五景 `generated_by=diffusers-sd15`（GTX 1650）；scene_001 fp16 numeric failure → 自動升 float32，002–005 沿用 float32 plan；五景 is_black=false、is_flat=false、fallback=false。
- TTS：五景 `provider=generated_by=kokoro-tts`、`model=hexgrad/Kokoro-82M-v1.1-zh`、`voice=zm_010`、`device=cpu`、`degraded=false`、`fallback_from=[]`、`sample_rate=24000`；revision `01e7505bd6a7a2ac4975463114c3a7650a9f7218`、sha256 `b1d8410f…76e2b`（同 E2-1）。

| scene | narration duration (s) | synth (s) | RTF |
|---|---|---|---|
| 001 | 6.675 | 5.384 | 0.807（含模型載入） |
| 002 | 6.250 | 1.922 | 0.307 |
| 003 | 6.175 | 1.845 | 0.299 |
| 004 | 6.650 | 2.044 | 0.307 |
| 005 | 5.350 | 1.621 | 0.303 |

事實結論：Kokoro（CPU）與 SD 1.5（GTX 1650）在同一次 `run` 中共存成功；旁白 duration 正確進入影片流程（has_audio、字幕由實測時長切）；無任何 TTS fallback；LOCAL_FREE、NT$0。穩態 RTF ≈0.30（CPU），首景含載入 ≈0.81。
聽感：沿用 E2-1 使用者主觀回報（zm_010 最偏好；zf_001 口音明顯），**非客觀排名**。

## E2-3 Audio Layer（BGM／SFX／ducking；D-031）
### 自動測試證據（雲端容器，2026-10-23，Batch 20）
`tests/test_audio_layer.py` 13 項：程序化來源確定性；ducking 在人聲中衰減至 −12 dB、hold 期間不恢復、release 後平順恢復且無階梯跳變；無人聲 → 不 duck；narration-only 不被改動；limiter 在 0 dB 疊加下仍 ≤ −1 dBFS；SFX 定位與超出時間軸標示；BGM 比人聲低 > 20 dB；null 預設與舊版相容（無 dry 檔、不建 audio 目錄）；加 BGM／SFX 不觸發任何 scene 重做；來源失敗照實標 unavailable；PAID 來源被 ApprovalGate 擋下。CLI 實跑：`run --audio procedural` → status=mixed、peak −24 dBFS；`set-scene --sfx 一陣風@0.3` → whoosh 於 0.3 s。
### Windows 真機（2026-10-23，使用者回報）— 完成（BGM／ducking）
命令：`python -m see.app.cli run examples\story_short.txt --project-id audiotest --voice zm_010 --audio procedural`（程式版本 `9acce55`）。
- audiotest 成功輸出；Kokoro `zm_010` 正常；procedural BGM 正常；ducking 正常；`degraded=false`；成本 NT$0。
- 客戶主觀驗收：**「OK」**（單一使用者聽感，非客觀評分）。
- **本次 SFX = 0**（mock 分鏡不產生 sfx cue）→ **SFX 真機聽感尚未驗證**；需以 `set-scene … --sfx 描述@秒數 --audio procedural` 另測。

## E2-4 Style Profile 真機出圖驗收（D-033；進行中；順序依 D-034：anime → realistic → cinematic →〔次要〕3d）
方法：`python -m see.app.cli style-test --style <id>`（固定場景／seed 1234／同尺寸／同 base prompt，只換 style terms；不建專案、不動快取）。輸出 `workspace\style_tests\<id>_seed1234.png`＋`.json`。

| style | generated_by | dtype | is_black/flat | 耗時 | 客戶人眼判斷（主觀） |
|---|---|---|---|---|---|
| anime（P1） | ⏳ | | | | |
| realistic（P1） | ⏳ | | | | |
| cinematic（P1） | ⏳ | | | | |
| 3d（P2，次要） | ⏳ | | | | |
| picture_book（P3） | diffusers-sd15 | float32（fp16 numeric failure → 升級；無 OOM、無 fallback） | 否／否（technical_valid＝true） | ≈234.5 s | 「比較像藝術品。」→ **technical PASS／scene FAIL／style FAIL**：幾乎看不到貓、無追蝴蝶、無庭院構圖，高飽和粗黑線＋抽象／水果／幾何圖形（D-034、D-035）。**保留為 regression／failure evidence** |

- 無效嘗試（不計入）：picture_book 第一次 `generated_by=placeholder-image`、`valid_for_style_test=false`（新 cmd 視窗未設 `SEE_MODELS_DIR`）；工具 exit 3 fail-closed，行為正確。
- 人眼判斷皆為單一使用者主觀感受，非客觀品質結論。
- **分層（D-035）**：technical_valid（自動）≠ scene_validated ≠ style_validated（人工）。上表「技術 PASS」不代表場景或風格通過。
- 實際生成解析度 512×288（fit）→ 放大到 1920×1080；根因分析見 `AI_IMAGE_QUALITY_RCA.md`。E2-4 其餘風格暫停，待 native 解析度 A/B。

## 狀態
E2-1 ✅　E2-2 ✅　→ DG-13 裁示 A：Kokoro 正式採用為目前 Phase 2 LOCAL_FREE 中文 TTS provider（D-029）。E2-3（Audio Layer）自動測試 ✅、真機 BGM／ducking ✅（客戶「OK」）、SFX 真機 ⏳；BGM 預設維持 null（D-032）。
