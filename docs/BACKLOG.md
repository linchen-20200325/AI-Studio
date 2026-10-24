# BACKLOG.md

## 封存總覽（2026-10-23；狀態標記：DONE／NEXT／BLOCKED／RESEARCH／NEEDS HUMAN DECISION）
| 項目 | 狀態 |
|---|---|
| Base SD1.5 native 人物近景入庫（D-043） | DONE |
| MeinaMix native 重跑＋style-compare＝model_preset_level（D-045） | DONE |
| DG-23：接受 model_preset_level（D-045） | DONE |
| CyberRealistic 真人／電影感品質驗證：已下載並出西方女性近景（主觀：真人感佳但偏西方臉孔，D-046）；人物控制未通過判定 | NEXT：東亞女性／男性案例 |
| CyberRealistic upstream lineage 釐清 | RESEARCH |
| cinematic 驗證（共用 realistic 模型） | BLOCKED（CyberRealistic 之後） |
| DG-21 native 是否成為預設 | NEEDS HUMAN DECISION（比較完成後） |
| 3D（P2） | BLOCKED（P1 之後） |
| Preference Layer 產品化（ARCHITECTURE §13） | 非 UI 核心 **DONE（D-062）**；待裁示：Character default 優先序、preset→prompt 詞對照；UI＝DG-19 |
| Style／character／voice／BGM UI（DG-19） | NEEDS HUMAN DECISION |
| SFX 人工聽感 | NEXT（需真機人耳） |
| Character consistency：IP-Adapter／LoRA | **HARDWARE_UPGRADE_BLOCKED（D-061）**：plus-face 已證實不足（D-057／D-059）；Identity Preservation／Character LoRA 等 ≥12 GB VRAM 級 GPU 再依 Resume Gate 重評 |
| Lip-sync 實際模型 | BLOCKED（未核准） |
| commercial-safe anime 路徑（DG-22） | RESEARCH／NEEDS HUMAN DECISION |
| 自有／乾淨授權 Anime LoRA（DG-22 c） | RESEARCH（不下載資料、不訓練） |
| MeinaMix 商用 | BLOCKED：commercial_cleared=false，不得商用 |
| DG-14 永久預設 voice（zm_010 僅候選） | NEEDS HUMAN DECISION |
| DG-7 repo Private／預設分支 | NEEDS HUMAN DECISION（使用者手動） |

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
- [x] DG-16：裁示 A（D-031）— Audio Layer（BGM／SFX／ducking），程序生成、NT$0。
- [x] DG-17（部分）：Audio 真機聽感「OK」（D-032）。**BGM 預設開啟與否：延後到完整產品流程／UI 一起決定（維持 null）**；CC0／使用者素材仍需另核准。
- [x] DG-18：裁示 A（D-033）— Style 真機出圖驗收（進行中，E2-4）。B 角色一致性模型研究、C Lip-sync 研究待之後裁示。
- [ ] **E2-4 Style 真機驗收**（順序 D-034）：~~picture_book~~（技術 PASS／主觀 FAIL，不再處理）→ **anime → realistic → cinematic** →（次要）3d（`style-test --style <id>`，一次一條）。🖥️
- [x] **E2-4 RCA（D-035／D-036）**：native A/B 證實 H1；anime 在 Base SD1.5 style FAIL → 停止調 Base SD1.5。
- [x] **DG-20 研究（D-036）**：`DG20_IMAGE_MODEL_RESEARCH.md`（anime：MeinaMix／WD 1.4；realistic：CyberRealistic／Realistic Vision V6 B1；cinematic 共用真人模型；Model Router 提案）。
- [x] **DG-20 原始證據（D-038）**：`docs/evidence/dg20/`。
- [ ] **DG-22 動畫商用路線**：SD 1.5 級無「品質＋血統乾淨」候選 → 選項：內部用 MeinaMix、商用延後｜評估 WD 1.4（pickle、品質未證實）｜自訓動畫 LoRA（授權資料）｜換算力走 SDXL 級乾淨模型。🚦
- [ ] ~~DG-20 證據補完（D-037）~~（已由 D-038 完成）：需客戶開放 `huggingface.co`、`civitai.com`（只讀）→ 取 HF YAML／README／commit SHA／sha256、Civitai Addendum／權限開關／版本 hash；MeinaMix 血統、ACertainModel（乾淨軌）、CyberRealistic 授權不一致。🚦
- [ ] **E2-5（D-039）**：MeinaMix → 驗證 → 真機 ✅ → base native 近景 ✅；MeinaMix native 重跑 ✅ style-compare＝model_preset_level、客戶 OK、DG-23 接受（D-045）→ CyberRealistic（等客戶下一步） → 真機；結果填 PHASE2_EVIDENCE E2-5 → 提 DG-21＋專用 checkpoint 導入裁示。🖥️📦
- [ ] **Preference Layer（D-042，PROJECT_RULES §15）**：生成前選＋生成後改（風格／人物／色彩／構圖／鏡頭）→ 只重生受影響景；結構化可修改設定（自訂 Style Profile、CompositionPrefs、GenerationSettings、偏好快照）；選項式＋自然語言（需 DG-10）；換模型不重建偏好。入口 ARCHITECTURE §13。非 UI 部分可自主；UI 併 DG-19。
- [ ] **DG-22 (c) 研究**：base SD1.5 Anime LoRA 自訓可行性（資料授權來源、GTX 1650 訓練可行性／雲端替代、流程、時間）；**不下載資料、不訓練**。🚦
- [x] DG-20 下載裁示（D-039）。後續（導入時）：授權原文核對（需開放 huggingface.co／civitai.com 或 Windows 端核對）→ 下載器＋provenance → ModelRouter＋preset（license_status／commercial_cleared）→ 真機 anime／realistic／cinematic 驗收。🚦📦🖥️
- [ ] **DG-21**（native A/B 後）：`gen_policy=native` 是否成為產品預設（fingerprint 失效重生、耗時增加）。🚦
- [ ] Mock LLM `build_image_prompt_en` 關鍵詞依詞長排序、無主體—動作—地點結構（H3）；正式解法＝真 LLM（DG-10）。
- [ ] **DG-20**（native A/B＋P1 三張目視後提出）：SD1.5 是否足以支撐 P1（日系動畫／AI 真人／電影感）：A 足夠→角色一致性驗證；B 不足→研究 LOCAL_FREE 替代模型（下載需裁示）；C 依路線分模型／provider。🚦📦
- [ ] （DG-20 之後）`default` Style 與 Mock LLM `image_prompt_en` 模板仍是 storybook watercolor，與產品方向（D-034）不符；改預設會變更舊 fingerprint → 需裁示。🚦
- [ ] DG-19（之後）：BGM 預設開啟、Voice Selector／Style／角色 UI 一併的產品流程 UI 裁示（合併 DG-14／DG-15）。🚦
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
- [x] Web UI Scene 卡加 `image_prompt_en` 編輯欄（D-062；另加畫面說明、影片動態描述、影響範圍確認）。
- [ ] Scene 編輯 UX：編輯欄位完整度（visual_description／video_prompt／voice／duration 已有 API）、編輯後只重做必要資產的提示。🤖🖥️（最終體驗）
- [x] CI workflow（GitHub Actions：pytest + ffmpeg）（D-016）。
- [x] Web UI（手機可用）：輸入文字 → 看 preview → 修改單景 → 核准。
- [ ] `EdgeTTSProvider` 在有網路環境實測（DG-3；D-014 已決定不採用，僅保留 adapter；低優先）。🖥️
- [x] 自然中文 TTS provider（LOCAL_FREE）— Kokoro（D-029；證據 `PHASE2_EVIDENCE.md`）。更適合台灣中文的 provider 可另開 DG 新增。
- [ ] **Voice Selection（規格，D-028）**：使用者流程「角色 → 選擇 voice → 試聽 → 調整語速 → 確認 → 才進正式影片生成」。已有：`VoiceInfo`／`TTSProvider.list_voices()`（provider-agnostic）、kokoro 型錄（可讀名稱／性別／accent_note）、CLI `tts-voices`、`--voice`／`SEE_TTS_DEFAULT_VOICE`。**非 UI 部分已完成（D-030，Batch 19）**：角色 voice／語速依角色保存、試聽 API、per-scene／per-character 語速、確認閘門（CLI＋Web API）。待做：UI（DG-15）；其他 provider 的 `list_voices`；清除景的 narrator（目前 API 無法設回 None）。不得綁死 kokoro；保留 fallback／fail-closed／evidence；不動 SD 1.5 路徑。🤖（UI 需 DG-15）
- [ ] 角色語音（character voices）：`scene.voice` 對應多角色／多音色。kokoro 已可用 voice id（zf_*/zm_*）；更多 voice 需另下載（小檔，仍需裁示）。🖥️
- [ ] Evidence／provenance 擴充到 clip（manifest meta、CLI、UI）。TTS 部分已完成（Batch 15：`tts_evidence`、`narration_meta`、provenance.json）。🤖
- [ ] Web UI：處理中顯示每景進度（目前只到 stage 層級）；專案刪除。🤖
- [ ] Retry／resume：中斷後續跑（per-scene fingerprint 已可續跑）；明確 retry policy 與失敗景標記。🤖
- [ ] `OllamaLLMProvider`（LOCAL_FREE）：暫緩（DG-2）。
- [ ] BGM / SFX：**第一版完成（D-031，Batch 20）**：程序化 BGM／SFX、ducking、limiter、mux、evidence。待做：SFX 真機聽感（E2-3 未涵蓋）；ambience；多段 BGM；CC0／使用者上傳來源（新 AudioProvider，素材授權需核准）；UI 調整 cue（DG-15 相關）。🖥️🚦
- [ ] QA 階段：自動檢查（video QA：黑幀／凍結；audio QA：LUFS／靜音；subtitle QA：超長／重疊；總長度區間）。圖片黑圖／平面檢查已有（`see/core/image_qa.py`，D-021）。🤖

- [ ] **Style Profile**（D-032 foundation 完成）：待做——非 default 風格真機視覺驗收（DG-18 A，無下載）；自訂風格（使用者建立）；UI（DG-19）。🖥️
- [ ] **Character Consistency**（D-032 foundation 完成：外觀錨點＋結構化 refs）：待做——Script.characters 自動建立角色設定（同 id）；真機一致性驗收；IP-Adapter／LoRA／參考圖 provider（DG-18 B，需下載裁示）。🖥️🚦
- [ ] **Lip-sync**（D-032 foundation 完成：介面、opt-in stage、fallback、evidence）：待做——模型研究與授權（DG-18 C）；人臉偵測前置檢查；與角色/旁白對應。🚦📦🖥️

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
| Character voices | 🟡 | 角色 voice／語速／試聽／確認（D-030，CLI＋API）；UI 未做（DG-15） |
| Subtitle | ✅ | 切句、SRT、燒錄、覆寫（Phase 0） |
| Background music | 🟡 | 程序化 BGM（D-031；預設關閉）；真機聽感 OK（D-032）；無外部素材來源；預設開啟待產品 UI |
| Sound effects | 🟡 | 程序化 SFX（scene `sfx` cue；chime／whoosh／thud／pop）；真機聽感未驗證 |
| Audio mixing / ducking | ✅ | numpy 混音＋ducking＋limiter（13 tests）；真機 ducking OK（D-032） |
| Lipsync | 🟡 | 介面＋pipeline stage（D-032，opt-in，null 預設）；**無真實模型**（DG-18 C） |
| Preview rendering | ✅ | ffmpeg 組裝、轉場、字幕、1280×720（真機 42.4 s） |
| Human approval | ✅ | PREVIEW→APPROVED→FINAL 狀態機，CLI/UI `approve` |
| Scene-level regeneration | ✅ | `regen`／`set-scene`／UI 單景重做；D-023 語意驗證 |
| Final rendering | 🟡 | 可產 final.mp4；Final／Preview 品質設定未分離（P1） |
| Provider abstraction | ✅ | 六介面＋registry＋Fallback；核心不 import 具體供應商 |
| Local / free provider strategy | ✅ | LOCAL_FREE 全程 NT$0；PAID 需核准（ApprovalGate 測試） |
| Windows GPU support | ✅ | cp950 修正、4 GB runtime plan、fp32 upcast（D-020～D-022） |
| Cache / resume | ✅ | per-scene fingerprint、內容驗證、降級快取重試（D-021/D-023） |
| Evidence / provenance | ✅ | image／TTS（`tts_evidence`、provenance.json）／audio（`audio_evidence`）；clip 尚無同等 evidence |
| Failure / fallback handling | ✅（image／TTS／audio）🟡（video） | image 階梯；TTS kokoro→espeak→silent；audio 來源 unavailable 照實記錄；video 無 fallback |
| Configuration / setup UX | 🟡 | env 變數＋`image-setup`／`image-download`／`hardware`；UI 無設定頁；`image_prompt_en` UI 欄未做 |
| Access control / 部署 | 🔴 | 限可信任區網（D-011）；DG-7 repo Private 待使用者手動 |

統計（上表 25 項，Batch 21 重算）：✅ 16　🟡 8　⬜ 0　🔴 1（DG-7，待使用者手動）。
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

- [ ] **CyberRealistic × east_asian_female_portrait／east_asian_male_portrait（D-046）**：NEXT（Windows 真機；native、seed 1234、25 步、CFG 7、DPM++ 2M Karras）。
- [x] **結構化 Character 設定（D-048，ARCHITECTURE §14.1）**：DONE；原 NEXT（非 UI 可自主；性別／年齡區間／外貌地區／髮／五官／服裝／體型／辨識特徵，舊欄位相容）。
- [ ] **Reference Image／Character Identity（IP-Adapter／FaceID 類）**：RESEARCH（授權、GTX 1650 可行性、品質；不下載、不實作）→ NEEDS HUMAN DECISION。
- [ ] **evidence backlog**：CyberRealistic 西方女性近景、東亞男性近景 technical JSON 未入庫（可選補）。

## 短劇 Roadmap（D-047；長期目標＝連續劇情 AI 短劇；三路線：真人／電影感、日系動畫、半寫實 3D）
| P1 能力 | 項目 | 狀態 |
|---|---|---|
| Character Identity／Reference Image | 角色 A／B 定義（結構化設定，ARCHITECTURE §14.1，D-048） | DONE（非 UI） |
| | 跨鏡頭／背景／服裝維持 Identity；Identity provider 研究（IP-Adapter／FaceID 類：授權、4 GB 可行性） | RESEARCH → NEEDS HUMAN DECISION |
| | 真人照片 Local First／不進 Git（§16） | 規則已生效 |
| Multi-character Scene | `two_characters_ab` 真機：scene FAIL（D-050）；DG-24＝A，S1／S2 已實作（D-051） | NEXT：Windows 真機 S1 → S2 → style-compare → 人工 |
| Image-to-Video | 人物動作／表情／鏡頭動態（超越 Ken Burns）；LOCAL_FREE＋GTX 1650 4 GB 可行性研究，不足須明說 | RESEARCH（不下載、不用付費 API）→ NEEDS HUMAN DECISION |
| Dialogue Performance | 角色聲音接 TTS（已有基礎）；真 Lip-sync provider；多角色台詞對應；字幕／timeline 對齊 | Lip-sync：BLOCKED（未核准模型）；其餘 NEXT |
| Audio／Editing | BGM ✅／ducking ✅；SFX 聽感未驗；ambience、轉場、自動剪輯 | NEXT |
| 真機證據 | CyberRealistic × east_asian_male_portrait technical JSON 入庫 | NEXT（需客戶回傳 JSON） |

## 新正式產品需求（D-050；客戶）
| 需求 | 內容 | 狀態 |
|---|---|---|
| User-defined Style／Mood Profile | 使用者新增／修改／儲存風格，不寫死；分層：Visual style（日系動漫／真人電影感／3D／繪本…）、Mood（恐怖／溫馨／陽光／悲傷／浪漫／懸疑…）、Cinematography、Lighting、Audio mood、Character appearance；可組合（例「日系動漫＋溫馨＋黃昏」）；自然語言 → AI 產生 Style Profile → 試生成 → 人工確認 → 存成「我的風格」 | NEXT（資料模型非 UI 可自主；自然語言需 DG-10 LLM） |
| Mobile-first Preference Layer | 手機／Web：輸入故事 → 選角色 → 選風格／氛圍 → 選聲音試聽 → 調整 → 生成 → Preview → 局部修改 → Final；使用者不接觸 CMD／checkpoint／CUDA／模型路徑／環境變數 | NEEDS HUMAN DECISION（UI＝DG-19） |
| Environment Bootstrap | 不得要求每次 `set SEE_MODELS_DIR=...`；persistent configuration（設定檔／啟動腳本）＋啟動自檢。實例：新 CMD 未設 SEE_MODELS_DIR → 既有 CyberRealistic 被誤判 provenance 不可用 | NEXT（可自主；錯誤訊息應提示「模型目錄未設定」而非「未驗證」） |
| Migration／Reinstall | 安裝／還原 → GPU／VRAM 檢測 → Python／runtime／CUDA 相容檢查 → dependency 檢查 → 模型存在性＋provenance 驗證（搬移後驗 sha256，不強迫重下載）→ 只補缺 → 還原使用者設定；備份／還原 Style／Character／Voice／Project settings | NEXT（可自主，分階段） |

## 多角色／Identity（D-050；研究見 DG24_MULTI_CHARACTER_IDENTITY_RESEARCH.md）
| 項目 | 狀態 |
|---|---|
| D-049 真機證據入庫（scene FAIL／style PASS，主觀） | DONE |
| S1 長 prompt 分段編碼（修 80＞77 截斷；opt-in `--long-prompt`） | DONE：真機解決截斷；scene FAIL（屬性綁定／臉部多樣性未解，主觀，D-052） |
| style-compare 實驗變數語意（prompt_mode 被誤判） | DONE（D-052） |
| S2 Regional prompting 原型（零下載；opt-in `--regional`） | DONE：真機 FAIL（單人融合／identity collapse，主觀，D-053）；保留為 opt-in 診斷，不再調參 |
| 角色 → 畫面區域提升到 Scene／Storyboard 資料（regional 產品化） | 待 S2 真機結果 |
| S3 分段生成＋合成（零下載） | RESEARCH（S2 不足再評估） |
| S4 IP-Adapter plus-face SD1.5＋ViT-H image encoder（2,626,557,296 bytes ≈2.63 GB） | DG-25 已核准（D-054）；程式 DONE；NEXT：Windows `adapter-download --check`→`--yes`→真機 |
| S4 PoC：每角色 reference image＋IP-Adapter mask | 實作 DONE（D-054）；真機一次：2 人恢復、identity 有影響、A／B 位置疑似顛倒、fidelity 部分（主觀，scene FAIL，D-056） |
| S4 A／B binding 追溯 | DONE（D-056）：mapping verified、非程式 bug；加 position 排序／mask 幾何自檢／`identity_region_map`＋疊圖 |
| S4 同 seed 重跑取 evidence | DONE（D-057）：mapping PASS、分離改善、**identity fidelity FAIL**（主觀）→ S4 只作研究證據，不升格 production；不再以調 scale 為主解法 |
| DG-26 Multi-character Composition（研究：DG26_MULTI_CHARACTER_COMPOSITION_RESEARCH.md） | **PAUSED（D-059；人物 fidelity 驗證 HARDWARE_UPGRADE_BLOCKED，D-061）**：`ab_background` 與 A isolated（identity FAIL）保留為 evidence；B isolated、compose-scene、Route C、去背優化暫停，待 identity preservation 解決 |
| **DG-28 Identity Preservation Research**（DG28_IDENTITY_PRESERVATION_RESEARCH.md） | 研究 DONE（D-059）→ 裁示 B（D-060）後由 D-061 改為 **HARDWARE_UPGRADE_BLOCKED**；FaceID-Plus-V2 未核准、不下載；硬體升級後依 Resume Gate 重新研究（研究結果屆時可能已過時） |
| 零下載 reference 裁臉對照（手動裁成臉部大近照，同 seed 重跑 A isolated） | **DEFERRED（D-061：superseded by hardware block）**；D-060 歷史保留，不執行 |
| Reference Quality Check UI（ARCHITECTURE §17.7） | BACKLOG（規格 DONE） |
| Identity Consistency 跨 Scene 驗收矩陣（ARCHITECTURE §17.8） | 規格 DONE；待 identity 路線確定後執行 |
| DG-26 Route C：合成後只修接縫（4-ch inpaint 或低 strength img2img，既有權重） | BACKLOG（Route A 真機後評估） |
| DG-26 Route B：inpaint 依序合成 | 不優先（D-057） |
| DG-27 去背／segmentation 模型（若單色背景鍵控不足） | 未觸發；需授權審查＋Gate，不得自行下載 |
| Face crop（參考圖目前為 CLIP 中心裁切、無人臉偵測） | RESEARCH（若 Identity 不足再評估，不新增 insightface） |
| ControlNet（openpose 等）兩人佈局控制 | RESEARCH（需另下載；S4 後評估） |
| S5 IP-Adapter-FaceID | D-053 不建議（pickle＋InsightFace 非商用＋新依賴）；**D-059 重新評估**：FaceID-Plus-V2 SD1.5 為 DG-28 Top 1（研究用），仍需客戶裁示 pickle 例外、InsightFace 非商用、新依賴 |
| 重抽 seed | 非解法（客戶裁示） |

## Preference Layer 規格缺口（D-062；需客戶裁示，不自行決定）
| 缺口 | 狀態 |
|---|---|
| Character default（default_style_profile／default_mood_profile）在解析中的優先序（多角色同景以誰為準） | NEEDS HUMAN DECISION |
| Mood／Lighting／Color／Camera／Composition preset → prompt 詞對照（產品字句；或 DG-10 LLM 轉換） | NEEDS HUMAN DECISION |
| Voice per-scene emotion（TTS 目前無情緒參數） | BLOCKED（provider 能力） |
| GenerationSettings 品質／速度欄位 | NEEDS HUMAN DECISION（無規格值） |

## Hardware Upgrade Resume Gate（D-061；架構見 ARCHITECTURE §18）
| 項目 | 狀態 |
|---|---|
| Identity Preservation／Character LoRA | **HARDWARE_UPGRADE_BLOCKED**（GTX 1650 4 GB） |
| 重開前必查：GPU 型號、VRAM、CUDA／torch、可用硬碟、當時最新 identity route、模型授權、商用授權、訓練時間、reference 數量 | 待硬體升級 |
| 重評範圍：SD1.5 Character LoRA、Identity Preservation、FaceID 類研究方案、SDXL／新模型 | 待硬體升級 |
| VRAM 規劃參考（非永久需求）：4 GB 不再投入 Character LoRA 訓練；12 GB 可重評 SD1.5 Character LoRA；16 GB 較適合長期角色 LoRA／部分 SDXL；24 GB 再評更大型 identity／SDXL／video | planning only |

## Character Identity Definition／角色 UI（D-058；規格：ARCHITECTURE §17；規則：PROJECT_RULES §17）
| 項目 | 狀態 |
|---|---|
| A／B 定義修正（A＝男、B＝女；`two_characters_ab`／`ab_char_a_isolated`／`ab_char_b_isolated` v2、檔名 `-v2`） | DONE（D-058） |
| 舊 evidence 標記 `historical_reversed_character_mapping=true`（不刪、不覆寫、不改名） | DONE（文件＋程式辨識；style-compare 標示、compose-scene 拒收） |
| Character Definition Schema、ReferenceAsset Schema、ScenePlacement、VoiceAssignment | DONE（`see/models/character_definition.py`） |
| Character Validation Gate（fail closed） | DONE（library＋`style-test --identity`／`compose-scene` 接線）；UI 接線 → BACKLOG |
| Reference Library service（list／register／validate／bind／primary；legacy 唯讀）＋`ref` CLI | DONE（D-062） |
| Character CRUD 後端（`workspace/character_library/`；archive／restore，無 hard delete） | DONE（D-062）；與 Project 綁定／遷移 → NEEDS HUMAN DECISION |
| Confirmation payload（含 gate、can_generate） | DONE（D-062，後端）；卡片 UI → DG-19 |
| Reference Library 主路徑 `workspace/reference_library/`（含 styles/）＋sidecar `.ref.json`；legacy `identity_refs/` 相容 | DONE（CLI）；非 people 類別一律 not yet supported |
| `Project.characters`（CharacterVoice）遷移到 CharacterDefinition | BACKLOG（需可逆 migration 設計；不做不可逆遷移） |
| StyleProfile 拆分：Visual Style／Mood／Lighting／Color Tone／Camera＋Scene override | BACKLOG |
| Voice per-scene override（voice／speed／emotion） | BACKLOG（角色預設 voice 既有 D-030） |
| UI A 基本資料（名稱、ID、類型、性別呈現、年齡感、備註） | BACKLOG（DG-19 UI） |
| UI B 外觀（臉型、五官、髮型、髮色、服裝、特徵、表情） | BACKLOG |
| UI C Reference（上傳／Library 選取／綁定角色與用途顯示／多張／更換／刪除／主要 reference／provenance） | BACKLOG |
| UI D Visual Style（寫實、日系動畫、3D、繪本、自訂） | BACKLOG |
| UI E Mood（溫暖、恐怖、陽光、悲傷、浪漫、懸疑、自訂） | BACKLOG |
| UI F Lighting／Color tone／Camera／Composition | BACKLOG |
| UI G Voice（聲音、語速、情緒、試聽） | BACKLOG（試聽 CLI 既有） |
| UI H Scene Placement（左中右、前中後景、景別、動作、姿勢） | BACKLOG |
| **Character Confirmation Card**（生成前必經、可直接修改、Gate 衝突時禁止生成） | BACKLOG（規格 ARCHITECTURE §17.6） |
| 一般 UI 不暴露技術名稱；Advanced／Debug 區 | BACKLOG |

## Layered Scene（D-057；客戶裁示；架構見 ARCHITECTURE §16）
| 層 | 狀態 |
|---|---|
| Background Layer | PoC（style-test 背景案例＋compose-scene） |
| Character Layer（people） | PoC（單人 style-test＋可選 `--identity` 單一 reference） |
| Animal／Fictional character／Environment layer conditioning | BACKLOG（Reference Library 類別已定義；conditioning 未做） |
| Props Layer、Effects Layer | BACKLOG |
| Text／Subtitles Layer | 既有字幕燒錄（影片管線），尚未納入 Scene layer 資料模型 |
| Scene layer 資料模型（layer_id、layer_type、source asset、**character_id 為角色層主鍵**、provenance、placement、style override、regeneration scope；沿用 per-scene fingerprint） | 欄位已定（ARCHITECTURE §16，D-058）；compose-scene evidence 已含；正式資料模型 BACKLOG |

## Reference Library（D-056；客戶裁示；規格見 ARCHITECTURE §14.6）
| 項目 | 狀態 |
|---|---|
| `workspace/identity_refs/{people,animals,characters,backgrounds}/` 路徑慣例、`--ref char_x=people/<檔>`、provenance（sha256／bytes／category） | DONE（CLI；不進 Git）；D-058 起為 legacy，主路徑 `workspace/reference_library/`（含 styles/） |
| people → 人物臉部 identity（S4 `--identity`） | DONE（唯一支援類別） |
| animals → 動物外觀 conditioning | BACKLOG（需另研究／Gate；不得走 face-only pipeline） |
| characters → 虛構角色／角色設計 conditioning | BACKLOG（同上） |
| backgrounds → 場景／環境 conditioning | BACKLOG（同上） |
| Library metadata（每張圖 sidecar：類別、角色綁定、同意紀錄、來源；不含圖片本身） | DONE（ReferenceAsset schema＋`<檔名>.ref.json`，D-058）；Library 管理 UI → BACKLOG |
| UI 從 Reference Library 選 reference | BACKLOG（DG-19 UI 之後） |

## 生成後可調整項目總表（D-052；客戶需求；已存在者只指向原項，不重複）
| 需求 | 對應／狀態 |
|---|---|
| 生成後修改風格、氛圍、光線、色調 | 見「新正式產品需求」User-defined Style／Mood Profile＋Preference Layer（D-042／D-050）；**光線、色調**明列為 Style／Mood 可調欄位 — NEXT |
| 修改臉型／五官／髮型／年齡感／服裝／表情 | CharacterTraits 已有五官／髮型／年齡／服裝（D-048 DONE，非 UI）；**臉型、表情**欄位缺 → NEXT（補欄位）；臉部 Identity 品質見 DG-24 |
| 修改背景、時間、天氣、環境、構圖 | **新增**：Scene 層結構化設定（background／time_of_day／weather／environment／composition）→ NEXT（資料模型非 UI 可自主） |
| 修改鏡位、景別、人物位置、動作 | **新增**：Shot 設定（camera_angle／shot_size／character_positions／action）；人物位置與 S2 regional 對應 → NEXT（待 S2 真機）；動作需 Image-to-Video（RESEARCH） |
| 局部重生，只重做受影響鏡頭 | 已有：per-scene fingerprint 快取（改一景不重做其他景；角色設定只讓出現的景回 DRAFT）— DONE（基礎）；Preference 層級的影響範圍判定見 ARCHITECTURE §13 |
| 最終真正 lip-sync | 見 P1「Lip-sync」與短劇 Roadmap Dialogue Performance — BLOCKED（未核准模型） |
| 角色聲音／語速／情緒／SFX／環境音 | 聲音／語速 DONE（D-030）；**情緒**、**環境音（ambience）** NEXT；SFX 聽感未驗 |
| BGM 選擇或生成、音量、情緒、ducking | 程序化 BGM＋ducking DONE（D-031／D-032）；**BGM 選擇／情緒／音量 UI 化** NEXT（UI＝DG-19） |
| 自動剪接＋人工微調、轉場、字幕、音畫同步 | FFmpeg timeline／轉場／字幕 DONE（基礎）；**自動剪接節奏＋人工微調**、真硬切 NEXT（見 P2 `cut`） |
| Preview → 指定鏡頭修改 → 再預覽 → Final | Web UI 單景修改／重做／核准 DONE（Phase 0.5）；與 Preference Layer 串接 NEXT |
| 自訂 Style／Mood；UI 不要求 CMD／CUDA／模型路徑 | 見「新正式產品需求」Style／Mood＋Mobile-first＋Environment Bootstrap（D-050） |
| 換電腦部署、模型搬移、設定備份還原 | 見「新正式產品需求」Migration／Reinstall（D-050） |
