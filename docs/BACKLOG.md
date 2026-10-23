# BACKLOG.md

優先順序：P0（下一步）> P1 > P2。每項都受 PROJECT_RULES 約束（Free First、需核准才可接 PAID）。本檔是**所有未完成工作的唯一正式主清單**（PROJECT_RULES §12）。
標籤：🖥️＝需 Windows 真機驗證｜📦＝可能需下載模型（開工前需裁示）｜💰＝可能產生成本（需核准）｜🚦＝需客戶裁示（Decision Gate）｜🤖＝Project AI 可自行完成。
關閉條件：需 GitHub／code／test／真機證據；Null／Silent／Mock／Placeholder／skeleton 不算完成（§12.4）。

## Decision Gate（需使用者裁示）
- [x] DG-1：以 `026206c` 建立 `main`。
- [x] DG-2：暫緩 Ollama；維持 Mock，架構保留。
- [x] DG-3：edge-tts 待可連網環境驗證（FREE_TIER、零 key）。→ 待辦：在有網路的機器執行 `SEE_TTS_PROVIDER=edge python -m see.app.cli run examples/story_tiny.txt`。
- [x] DG-4：FastAPI + 手機友善單頁（已完成）。
- [x] DG-5：第一版限可信任區網，無登入（D-011）。未來 NAS／遠端部署再開 Access Control DG。
- [x] DG-6：不採用 edge-tts，adapter 保留（D-014）。
- [ ] DG-7：裁示已下（D-015），待使用者在 GitHub 設定手動把預設分支改 main、改 Private。🚦（使用者手動）
- [x] DG-9：裁示 D-027 — Kokoro-82M v1.1-zh 候選驗證核准（非最終採用）。原題：Phase 2 第一目標＝自然中文 TTS（LOCAL_FREE）候選研究與選型。比較面向：中文自然度、台灣國語適用、Windows、CPU／GTX 1650 4 GB／RAM、模型大小、license、離線、下載量、推理速度、角色語音擴充性、未來 lipsync 適配、provider 介面契合。**研究不下載；任何模型下載 → STOP 裁示。** 🚦📦🖥️
- [x] DG-13：裁示 A（D-029）— Kokoro 正式採用為目前 Phase 2 LOCAL_FREE 中文 TTS provider；Provider Agnostic、DG-14／DG-15 獨立。
- [ ] **DG-16**：Phase 2 第二目標方向（BGM/SFX〔素材授權需確認〕／LLM 規劃〔DG-10，需模型下載〕／其他）。🚦
- [ ] **DG-14**：產品永久預設 voice（目前候選 zm_010 僅為內部首選，未鎖死；D-028）。🚦
- [ ] **DG-15**：Voice Selector UI 形式（角色→選 voice→試聽→語速→確認）；屬產品 UI 決策。🚦
- [ ] DG-10：真 LLM 規劃（Ollama 等 LOCAL_FREE；DG-2 暫緩之重開）：模型選擇與下載需裁示。🚦📦🖥️
- [ ] DG-11：真正 VideoProvider（image-to-video）模型／provider：本機模型下載或 API 皆需裁示。🚦📦💰🖥️
- [ ] DG-12：`QueueExecutor`／NAS worker：需客戶提供 NAS／GPU 硬體資訊（停手條件）。🚦

## P0
- [x] DG-8：採 B（SD 1.5），D-018。
- [x] `image_prompt_en` + negative prompt（D-018）。
- [x] 使用者已安裝 torch/diffusers 並下載 SD 1.5（D-020）。
- [x] **使用者手動**：重跑 `run` 貼回 `image_evidence` → 五景皆 `generated_by=diffusers-sd15`（`PHASE1_EVIDENCE.md`，2026-10-23）。**Phase 1 完成條件已滿足。**
- [x] 若 GTX 1650 fp32 全程仍 OOM：真機未發生 OOM（`oom_downgrade=false`）；memory 階梯保留。
- [ ] 備案（D-022 C）：fp16 UNet + upcast_attention／部分層 fp32，僅在 fp32 全程太慢時評估（目前不需要）。
- [ ] 效能：GTX 16xx 直接以 fp32 起跑（跳過每個程序一次的 fp16 失敗嘗試），或把已證明的 floor 持久化到 workspace（可自主；需真機量時間）。
- [x] UI 顯示實際使用的 image provider 與 fallback 原因（D-021：Scene 卡 `image_meta`）。
- [ ] Web UI Scene 卡加 `image_prompt_en` 編輯欄（API 已支援）。🤖
- [ ] Scene 編輯 UX：編輯欄位完整度（visual_description／video_prompt／voice／duration 已有 API）、編輯後只重做必要資產的提示。🤖🖥️（最終體驗）
- [x] CI workflow（GitHub Actions：pytest + ffmpeg）（D-016）。
- [x] Web UI（手機可用）：輸入文字 → 看 preview → 修改單景 → 核准。
- [ ] `EdgeTTSProvider` 在有網路環境實測（DG-3；D-014 已決定不採用，僅保留 adapter；低優先）。🖥️
- [x] 自然中文 TTS provider（LOCAL_FREE）— Kokoro（D-029；證據 `PHASE2_EVIDENCE.md`）。更適合台灣中文的 provider 可另開 DG 新增。
- [ ] **Voice Selection（規格，D-028）**：使用者流程「角色 → 選擇 voice → 試聽 → 調整語速 → 確認 → 才進正式影片生成」。已有：`VoiceInfo`／`TTSProvider.list_voices()`（provider-agnostic）、kokoro 型錄（可讀名稱／性別／accent_note）、CLI `tts-voices`、`--voice`／`SEE_TTS_DEFAULT_VOICE`。待做：角色（character）模型與 voice 依角色保存；試聽 API（單句合成、不進 manifest）；語速 per-scene／per-character；UI（DG-15）；其他 provider 的 `list_voices`。不得綁死 kokoro；保留 fallback／fail-closed／evidence；不動 SD 1.5 路徑。🤖（UI 需 DG-15）
- [ ] 角色語音（character voices）：`scene.voice` 對應多角色／多音色。kokoro 已可用 voice id（zf_*/zm_*）；更多 voice 需另下載（小檔，仍需裁示）。🖥️
- [ ] Evidence／provenance 擴充到 clip（manifest meta、CLI、UI）。TTS 部分已完成（Batch 15：`tts_evidence`、`narration_meta`、provenance.json）。🤖
- [ ] Web UI：處理中顯示每景進度（目前只到 stage 層級）；專案刪除。🤖
- [ ] Retry／resume：中斷後續跑（per-scene fingerprint 已可續跑）；明確 retry policy 與失敗景標記。🤖
- [ ] `OllamaLLMProvider`（LOCAL_FREE）：暫緩（DG-2）。
- [ ] BGM / SFX：`AudioProvider` 實作（免費素材庫或程序化生成），含 audio mixing 與 ducking；素材授權需確認。🖥️（🚦若素材授權不明）
- [ ] QA 階段：自動檢查（video QA：黑幀／凍結；audio QA：LUFS／靜音；subtitle QA：超長／重疊；總長度區間）。圖片黑圖／平面檢查已有（`see/core/image_qa.py`，D-021）。🤖

## P1
- [x] 真正 ImageProvider 骨架（D-017）；SD 1.5 真機驗證完成（D-018～D-023，`PHASE1_EVIDENCE.md`）。
- [ ] 真正 VideoProvider（image-to-video；本機或 API，皆需核准 DG-11）。🚦📦💰🖥️
- [ ] Character 一致性（角色參考圖、seed 管理）。🖥️
- [ ] `QueueExecutor`：NAS 排隊 + GPU PC worker 領取（DG-12）。🚦
- [ ] Final render 與 Preview 分離的品質設定（解析度 / bitrate / 多平台輸出）＝ final production workflow。🤖🖥️
- [ ] 多語系（英文旁白 / 雙語字幕）。🤖

## P2
- [ ] Lip Sync Provider（必要時才做；模型需裁示）。🚦📦🖥️
- [ ] 登入 / 多使用者（NAS／遠端部署時開 Access Control DG）。🚦
- [ ] 成本儀表板（每 project 實際花費）。🤖
- [ ] 字幕樣式主題。🤖
- [ ] `cut` 轉場改為真正的硬切（目前以 0.08s fade 模擬）＝ transition correctness。🤖

---

## Phase 1 收尾盤點（2026-10-23，依 code / tests / 真機證據；圖例 ✅ 完成 🟡 部分 ⬜ 未開始 🔴 blocker／待裁示）
「架構介面存在」≠「使用者可用」；Null／Silent provider 不算完成。

| 能力 | 狀態 | 實況（證據） |
|---|---|---|
| Story / script input | ✅ | CLI 檔案／stdin、Web UI 貼文（PHASE0_EVIDENCE） |
| LLM / scene planning | 🟡 | 只有 `MockLLMProvider`（規則式切 beat）；Ollama 暫緩（DG-2）；真 LLM 規劃未做 |
| Structured scene schema | ✅ | Pydantic `Script`/`Scene`/`Timeline`，schema 驗證＋測試 |
| SD 1.5 image generation | ✅ | GTX 1650 真機五景（PHASE1_EVIDENCE） |
| Image QA | ✅ | `image_qa`（黑／平面／無法解碼）＋ fail-closed（D-021） |
| Video / motion generation | 🟡 | 只有 Ken Burns（ffmpeg zoompan）；真正 image-to-video 未做（P1） |
| Narration / TTS | ✅ | Kokoro-82M v1.1-zh（D-029，CPU，LOCAL_FREE）→ espeak → silent fallback；台灣口音 provider 未有（可新增） |
| Character voices | ⬜ | `scene.voice` 欄位存在；無多角色語音 provider |
| Subtitle | ✅ | 切句、SRT、燒錄、覆寫（Phase 0） |
| Background music | ⬜ | `AudioProvider` 介面＋`null-audio`；`AudioCue` schema 有，無實作 |
| Sound effects | ⬜ | 同上 |
| Audio mixing / ducking | ⬜ | 未做 |
| Lipsync | ⬜ | `null-lipsync` 介面而已 |
| Preview rendering | ✅ | ffmpeg 組裝、轉場、字幕、1280×720（真機 42.4 s） |
| Human approval | ✅ | PREVIEW→APPROVED→FINAL 狀態機，CLI/UI `approve` |
| Scene-level regeneration | ✅ | `regen`／`set-scene`／UI 單景重做；D-023 語意驗證 |
| Final rendering | 🟡 | 可產 final.mp4；Final／Preview 品質設定未分離（P1） |
| Provider abstraction | ✅ | 六介面＋registry＋Fallback；核心不 import 具體供應商 |
| Local / free provider strategy | ✅ | LOCAL_FREE 全程 NT$0；PAID 需核准（ApprovalGate 測試） |
| Windows GPU support | ✅ | cp950 修正、4 GB runtime plan、fp32 upcast（D-020～D-022） |
| Cache / resume | ✅ | per-scene fingerprint、內容驗證、降級快取重試（D-021/D-023） |
| Evidence / provenance | ✅ | manifest meta、CLI `image_evidence`、UI `image_meta`（僅 image；TTS/clip 尚無同等 evidence → 🟡 整體） |
| Failure / fallback handling | ✅（image）🟡（其他） | image 階梯＋fail-closed；TTS 有 auto fallback；video/audio 無 |
| Configuration / setup UX | 🟡 | env 變數＋`image-setup`／`image-download`／`hardware`；UI 無設定頁；`image_prompt_en` UI 欄未做 |
| Access control / 部署 | 🔴 | 限可信任區網（D-011）；DG-7 repo Private 待使用者手動 |

統計（上表 25 項）：✅ 13　🟡 8　⬜ 5（character voices、BGM、SFX、mixing、lipsync）　🔴 1（DG-7，待使用者手動）。
未完成 BACKLOG 條目：P0 7、P1 5、P2 5（全部保留於上方清單，無刪除）。

## Phase 2 建議（排序；第 1 項已完成 D-029；第 2、3 項開工前需裁示 DG-16）
**第一目標建議：自然中文旁白（真正可聽的 TTS，LOCAL_FREE）。** 理由：目前成品「畫面是 AI、聲音是 espeak」是離可看短片最遠的一環；不需新 GPU 模型即可大幅提升；Provider 介面與 fallback 已就緒；可獨立驗收（聽得出中文、時長量測正確、字幕對齊）。候選須先盤點授權與體積（例如 Piper／其他 open TTS），**任何新模型下載前先裁示**。

| 優先 | 項目 | 為什麼現在做 | Windows 真機 | 可能下載模型 | 可能成本 | Effort |
|---|---|---|---|---|---|---|
| 1 | 自然中文 TTS provider（LOCAL_FREE，含 voice 欄位對應） | 成品可聽性最大缺口；架構已備 | 是（聽感、速度） | 是（小型語音模型，需裁示） | 否 | Medium |
| 2 | BGM／SFX `AudioProvider` + ducking（程序化或免費授權素材） | 完整「聲音層」；無需 GPU；`AudioCue` schema 已有 | 是（最終播放） | 否（素材需授權確認） | 否 | Medium |
| 3 | 真 LLM 規劃（Ollama，LOCAL_FREE；Mock 保留為 fallback） | 分鏡／prompt 品質決定畫面；DG-2 曾暫緩，需重新裁示 | 是（GTX 1650 4 GB 跑小模型可行性） | 是（LLM 權重，需裁示） | 否 | Medium–High |

備註：真正 image-to-video、lipsync、character 一致性屬 Phase 3 以後（GPU／模型需求大，先裁示）。

## Windows 真機需求分類（後續）
- **A. Project AI 可自行完成**：provider 程式碼與介面、deterministic／mock 測試、CI、文件、UI 欄位（`image_prompt_en`、進度顯示）、QA 規則（LUFS／黑幀）、fingerprint／evidence 擴充到 TTS/clip、fp32 直起／floor 持久化邏輯。
- **B. 必須 Windows 真機驗證**：任何 GPU 推理（SD、未來 video/LLM）、TTS 真實聽感與時長、BGM/SFX 混音最終播放、lipsync、Windows 字型／ffmpeg 行為、效能（每景秒數）。
- **C. 必須客戶先裁示**：下載任何新模型（TTS／LLM／video）、新 API key／OAuth／付費 provider、授權不明素材或模型、大量磁碟需求、QueueExecutor 等需硬體資訊的架構變更、repo visibility（DG-7）。
