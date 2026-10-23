# TTS_PROVIDER_PLAN.md — DG-9 自然中文 TTS（LOCAL_FREE）候選研究

> 狀態：DG-9 **已裁示（D-027）**：Kokoro 候選驗證核准（非最終）。程式已實作（Batch 15），真機驗證見 `AI_TTS_KOKORO_WINDOWS.md`；聽感裁示＝DG-13。原研究內容保留如下。本輪**未下載任何模型、未安裝任何大型 dependency、未修改 production 行為**（PROJECT_RULES §10）。
> 研究日期：2026-10-23（Batch 14）。本容器無法連線 huggingface.co／k2-fsa.github.io，體積與速度為公開資料整理值，標 ≈ 者需真機下載後以實測更新本檔。

## 1. 現況（GitHub 實況）
- `TTSProvider` 介面：`synthesize(TTSRequest{text, language, voice, speed}, out_path) -> TTSResult{path, duration, provider}`；`scene.voice` 欄位已存在（provider 自行解讀）。
- Registry：`auto` = `FallbackTTSProvider([espeak, silent])`；`edge`（FREE_TIER，不採用，D-014）。
- 完成度：**Partial**（可聽但機械聲）。espeak-ng 以 `cmn` 發音，非產品級。

## 2. 篩選規則
1. cost_tier 必須 `LOCAL_FREE`、可離線、不需 API key。
2. 權重授權允許商用（Apache-2.0／MIT）；**CC-BY-NC 或自訂「不可商用」授權直接排除**（IndexTTS、F5-TTS 權重、Fish Speech）。
3. 必須能在客戶現有硬體跑：Windows、GTX 1650 **4 GB VRAM**（SD 1.5 已佔用時可能無 VRAM 餘裕 → **CPU 可行者優先**）、RAM 65 GB。
4. 短片需求：每景 1～3 句旁白（≈10–60 字），非即時串流；離線批次，RTF < 1 即可接受。
5. 不因「效果最好」選最大模型。

## 3. 候選比較（LOCAL_FREE）

| 面向 | **A. Kokoro-82M v1.1-zh** | **B. MeloTTS（ZH）** | **C. Piper zh_CN-huayan** |
|---|---|---|---|
| 架構 | StyleTTS2 系、82M 參數 | VITS 系（含中文 BERT 前端） | VITS 系、≈15–20M |
| 中文自然度 | 中高；100 個中文語者；韻律可接受，偶有多音字／聲調錯 | 中；單一 ZH 女聲；多音字錯誤較多 | 中低；單一女聲，略機械 |
| 台灣華語 | 無（大陸普通話口音；用詞需靠文本層處理） | 無 | 無 |
| Windows | `pip install kokoro misaki[zh]`，純 Python＋torch（客戶 .venv 已有 torch cu126）；可行 | 官方僅測 Ubuntu／Python 3.9，Windows 建議 Docker；unidic／pinned deps 常見安裝問題 | 有 Windows 執行檔與 `piper-tts` pip；最容易 |
| CPU 可行 | 是（公開回報 RTF ≈0.1–0.3，現代 CPU 即時以上） | 是（官方標 CPU real-time） | 是（極快） |
| GPU 需求 | 不需要；可選 CUDA 加速 | 不需要 | 不需要 |
| VRAM／RAM | 0 VRAM；RAM ≈1–2 GB | 0 VRAM；RAM ≈2–3 GB（含 BERT） | 0 VRAM；RAM < 0.5 GB |
| 模型體積 | ≈330 MB（.pth；ONNX int8 版 ≈100–200 MB） | ≈200 MB 聲學模型＋中文 BERT ≈1.2 GB → ≈1.5 GB | ≈60 MB（medium） |
| 下載量 | ≈330 MB＋pip（misaki、jieba、pypinyin、cn2an；torch 已有） | ≈1.5 GB＋pip（含 unidic ≈500 MB） | ≈60 MB＋pip |
| 推理速度（每景 1 句） | 秒級以內（CPU） | 秒級（CPU） | 次秒級 |
| License | 權重 Apache-2.0；程式 Apache-2.0 | MIT（程式與權重） | 程式 MIT；**huayan 權重授權需確認**（voices repo 各語者授權不一） |
| 商用 | 可 | 可 | 待確認 |
| 離線 | 是 | 是 | 是 |
| 角色語音擴充 | **強**：55 女／45 男語者可直接對應 `scene.voice`；voice embedding 可混合 | 弱：單語者，需自訓 | 弱：單語者，需自訓 |
| 未來 lipsync | 一般（24 kHz 清晰語音，可餵 wav2lip 類） | 一般 | 一般 |
| Provider 介面契合 | 高：text→24k wav，可量測 duration；speed 參數對應 | 高 | 高 |
| 生態／維護 | 活躍（2025 起持續版本；sherpa-onnx 亦收錄） | 緩（2024 後更新少） | 穩定但低活躍（Piper 原作者已轉向） |
| 風險 | 大陸口音；英文混讀需 `misaki[en]`＋espeak-ng；聲調錯需人工改字 | Windows 安裝；體積大；單聲 | 品質上限低，難達「產品級」 |

### 較大模型（本輪**不建議**為第一步，列為未來 DG）
| 模型 | License | 體積／硬體 | 不選原因 |
|---|---|---|---|
| CosyVoice2-0.5B | Apache-2.0 | ≈2–2.5 GB；GPU 建議，4 GB VRAM 邊緣；CPU 很慢；Windows 需改用 wetext | 零樣本音色複製最強，但硬體與安裝成本高 → 可作 Phase 2 後段「角色音色」升級 DG |
| GPT-SoVITS（v2Pro/v4） | MIT | Windows 整合包 ≈4.5–5 GB；推理 4–6 GB VRAM | 中文佳、少量樣本訓練，但下載／磁碟大，與 SD 1.5 同時難共存 4 GB |
| IndexTTS-2／Fish Speech／F5-TTS | 不可商用（權重） | — | 授權不符 §9／商用需求 → 排除 |

### FREE_TIER（非本輪範圍）
- edge-tts：唯一有 `zh-TW-HsiaoChenNeural` 台灣口音者，但非官方端點、需網路，已裁示不採用（D-014）。若客戶日後**只為台灣口音**願接受線上非官方服務，需重開 DG。

## 4. Project AI 首選：**A. Kokoro-82M v1.1-zh**
理由：
1. 唯一同時滿足「商用授權清楚（Apache-2.0）＋ CPU 即時 ＋ 體積小（≈330 MB）＋ 多語者（100）」。多語者直接解鎖 BACKLOG「角色語音」項，不必自訓。
2. 不占 GTX 1650 VRAM，可與 SD 1.5 同一程序串行執行而無 OOM 風險。
3. 相依純 Python，進客戶既有 `.venv`；不需 Docker、不需系統套件（中文路徑 misaki[zh] 不依賴 espeak-ng；英文混讀才需）。
4. 失敗時維持現有 fallback 鏈：`kokoro → espeak → silent`，不自動切 PAID。
缺點已知：非台灣口音；少量多音字錯誤（可在 scene 文本層以同音字修正，不需模型改動）。

## 5. 裁示後的實作計畫（尚未開始）
- Batch 15（Medium）：`see/providers/tts/kokoro.py`（optional import、`is_available()`、voice 對應、speed、24 kHz→44.1 kHz mono wav、duration 量測、ProviderInfo LOCAL_FREE）；registry 加 `kokoro` 並讓 `auto` 鏈前置；evidence／provenance 擴充到 TTS（BACKLOG 既有項）；deterministic 測試用 fake backend，CI 不下載模型。
- Windows 真機（§14，一次一指令）：安裝 pip 套件 → 由客戶執行一次下載（`kokoro` 首次使用時從 HF 取權重 ≈330 MB；需明確同意）→ 以 `examples/story_tiny.txt` 聽感與時長驗證 → 寫 `PHASE2_EVIDENCE.md`。
- 驗收：五景 `generated_by=kokoro`、時長量測與字幕對齊、無靜音 fallback、NT$0。

## 6. 唯一需要客戶裁示的問題（DG-9）
**是否同意採 Kokoro-82M v1.1-zh 為 Phase 2 第一目標，並授權在 Windows 真機下載 ≈330 MB 權重＋相關 pip 套件（Apache-2.0，LOCAL_FREE，大陸口音）？**
備選：B（MeloTTS，≈1.5 GB，單聲）／C（Piper，≈60 MB，品質較低、授權待確認）／暫不做 TTS，改做 Phase 2 其他目標。
