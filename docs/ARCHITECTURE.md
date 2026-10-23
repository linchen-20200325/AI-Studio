# ARCHITECTURE.md — see

狀態：Phase 0（2026-10-22）。本文件描述目前實作與預留的擴充點。

## 1. 一句話

**結構化資料驅動、Provider 中立、Compute 中立的「文字 → 影片」管線。**
AI 只負責產出經 schema 驗證的 `Script` / `Scene`；影片由確定性的 `Timeline` + FFmpeg 合成。

## 2. 端到端流程

```
INPUT (中文文字)
  │ ingest
  ▼
Script (title / logline / characters / beats)        ← LLMProvider (task=script)
  │ storyboard
  ▼
Scene[] (narration / visual / prompts / camera / transition / audio_cues)   ← LLMProvider (task=storyboard)
  │ assets        (per-scene, fingerprint cached)
  ▼
Asset: image.png                                      ← ImageProvider
Asset: narration.wav (+ measured duration)            ← TTSProvider
Asset: subtitles.srt                                  ← SubtitleBuilder (deterministic)
Asset: clip.mp4 (Ken Burns, narration, burned subs)   ← VideoProvider (image→clip)
  │ timeline      (deterministic: start/end/transition overlap)
  ▼
Timeline (preview.json)
  │ render
  ▼
renders/preview.mp4                                   ← Renderer (FFmpeg xfade + acrossfade)
  │ human gate
  ▼
DRAFT → PREVIEW → APPROVED → FINAL (renders/final.mp4)
```

Phase 0 的「VideoProvider」是 `KenBurnsVideoProvider`：以 FFmpeg `zoompan` 把靜態圖變成有鏡頭運動的片段。
未來真正的 AI Video Provider（image-to-video / text-to-video）實作同一個介面即可替換，Timeline / Renderer 不必改。

## 3. 目錄結構

```
see/
  app/        cli.py — 命令列入口（run / status / set-scene / regen / approve / final）
  core/       config.py（設定）、prompting.py（中→英 image prompt）、hardware.py（GPU/VRAM/RAM/disk/torch 偵測 + image tier 建議）、cost.py（CostTier / CostEstimate）、approval.py（ApprovalGate）、
              errors.py、hashing.py（fingerprint）、subtitles.py（SRT 切句）、ffmpeg.py（ffmpeg/ffprobe 封裝）、
              image_qa.py（影像產物內容驗證：黑圖／平面／無法解碼；快取重用前與生成後皆驗，D-021）
  models/     Pydantic schema：project / script / character / scene / asset / render_job /
              provider / worker / cost / approval / timeline
  providers/  base.py（六個 Provider 介面 + ProviderInfo）、registry.py（ProviderRegistry）
              llm/mock.py、image/placeholder.py、video/kenburns.py、
              tts/kokoro.py（D-029 採用）、角色 voice＝Project.characters（D-030）、tts/espeak.py、tts/silent.py、tts/edge.py（optional FREE_TIER）、
              audio/null.py、lipsync/null.py
  workers/    base.py（Task / Executor / Worker 介面）、local.py（LocalExecutor）
  pipeline/   stages.py（各階段純函式）、orchestrator.py（串接 + per-scene cache + 狀態機）
  render/     renderer.py（FFmpeg 組裝：xfade / acrossfade / 編碼參數）
  storage/    project_store.py（workspace 目錄佈局 + JSON 持久化）
  ui/         server.py（FastAPI + JSON API）、runner.py（BackgroundRunner）、static/index.html（手機友善單頁）
tests/        pytest（schema / providers / cost gate / incremental / e2e）
examples/     短篇中文故事
docs/         本文件、DECISIONS、BACKLOG、HANDOFF、PHASE0_EVIDENCE
scripts/      check_env.py（環境檢查）
```

## 4. 資料模型（`see/models/`）

| Model | 重點欄位 |
|---|---|
| `Project` | project_id, title, input_text, status(DRAFT/PREVIEW/APPROVED/FINAL), budget=0, currency, script, scenes[], approvals[], render_jobs[] |
| `Script` | title, logline, language, characters[], beats[]（每個 beat = 一段旁白 + 視覺摘要） |
| `Character` | character_id, name, description, visual_prompt |
| `Scene` | scene_id, index, duration, narration, dialogue[], visual_description, image_prompt, video_prompt, camera_motion, transition, audio_cues[], character_ids[], status, subtitle_override, overrides fingerprint 相關欄位 |
| `Asset` | asset_id, scene_id, kind(image/audio/subtitle/clip/video), path, fingerprint, provider, model, duration |
| `RenderJob` | job_id, kind(preview/final), status, provider, model, estimated_cost, actual_cost, currency, output_path, created_at, finished_at, error |
| `ProviderInfo` | name, kind, cost_tier(LOCAL_FREE/FREE_TIER/PAID), model, version, requires_network, requires_api_key |
| `WorkerInfo` / `Task` | worker_id, capabilities[]；task_id, kind, requires[], payload |
| `CostEstimate` | provider, model, units, unit_name, estimated_cost, currency |
| `Approval` | approval_id, kind(PAID_PROVIDER/FINAL_RENDER/...), target, approved_by, approved_at, note |
| `Timeline` | fps, width, height, items[]（scene_id, start, end, clip_path, transition, transition_duration） |

所有 AI 輸出必須先轉成 `ScriptDraft` / `StoryboardDraft`（response_model）再進入 pipeline；驗證失敗 fail-closed。

## 5. Provider 層

```python
class LLMProvider:   complete_json(request: LLMRequest) -> BaseModel
class ImageProvider: generate_image(req: ImageRequest, out_path) -> ImageResult
class VideoProvider: generate_clip(req: VideoRequest, out_path) -> VideoResult   # image→clip 或 text→clip
class TTSProvider:   synthesize(req: TTSRequest, out_path) -> TTSResult          # 回傳量測 duration
class AudioProvider: generate_audio(req: AudioRequest, out_path) -> AudioResult  # BGM / SFX
class LipSyncProvider: lipsync(req, out_path) -> LipSyncResult
```

每個 Provider 回傳 `ProviderInfo` 與 `estimate_cost(req) -> CostEstimate`。
`ProviderRegistry` 依設定建立 Provider；pipeline 只拿介面，不知道實作。

### Phase 0 已實作

| 介面 | 實作 | cost_tier | 備註 |
|---|---|---|---|
| LLM | `MockLLMProvider` | LOCAL_FREE | 確定性規則切句分景；不需要網路 |
| Image | `PlaceholderImageProvider` | LOCAL_FREE | PIL 漸層 + 文字（預設；永遠保留為 fallback） |
| Image | `DiffusersImageProvider` | LOCAL_FREE | 本機 open-weight（preset `sd15` 預設／`flux-schnell`），`local_files_only`，低 VRAM 自動策略，缺權重即拒絕 |
| Image | `FallbackImageProvider`（`auto`） | LOCAL_FREE | diffusers → placeholder；不跨 PAID |
| Image | `PaidImageProviderStub` | PAID | 占位，永不連線；證明 ApprovalGate 接線 |
| Video | `KenBurnsVideoProvider` | LOCAL_FREE | FFmpeg zoompan；camera_motion → 鏡頭運動 |
| TTS | `KokoroTTSProvider` | LOCAL_FREE | Kokoro-82M v1.1-zh（Apache-2.0，≈330 MB，CPU）；D-029 正式採用（目前）；權重僅由 `tts-download --yes` 取得 |
| TTS | `EspeakTTSProvider` | LOCAL_FREE | espeak-ng `cmn`；品質低但離線可用 |
| TTS | `SilentTTSProvider` | LOCAL_FREE | 靜音 + 以字數估算時長；測試與無 TTS 環境 fallback |
| TTS | `EdgeTTSProvider` | FREE_TIER | 需網路、不需 key；本環境無法連線，未啟用 |
| Audio | `NullAudioProvider` | LOCAL_FREE | 不產生 BGM/SFX（預設；Audio Layer 停用） |
| LipSync | `NullLipSyncProvider` | LOCAL_FREE | 安全 fallback（applies=False）；真實模型未選（DG-18） |
| Audio | `ProceduralAudioProvider` | LOCAL_FREE | 程式生成確定性 BGM／SFX（D-031）；`see/audio/layer.py`＋`mixer.py` 在 render 階段混音（ducking、limiter），per-scene clip 不變 |

## 6. 成本與核准（`see/core/approval.py`）

```
ApprovalGate.check(estimate, project) :
  tier == LOCAL_FREE            → 通過
  tier == FREE_TIER             → 通過（記錄 units）
  tier == PAID:
     無 Approval(kind=PAID_PROVIDER, target=provider.name) → raise PaidProviderNotApproved
     estimated_cost > project.budget → raise BudgetExceeded
```

Fallback 鏈（`FallbackTTSProvider` 等）遇到 PAID 候選一律先經過 Gate；Local 失敗不會自動切 PAID。

## 7. 增量重算（Human Approval Gate 的技術基礎）

每個 Scene 產物有 fingerprint = sha256(相關欄位 + provider name/model/version + 參數)。
`scenes/<scene_id>/manifest.json` 記錄每個產物的 fingerprint 與路徑；
Orchestrator 只重做 fingerprint 改變的產物。依賴鏈：

```
image.png     ← image_prompt, visual_description, size, image provider
narration.wav ← narration, voice, tts provider
subtitles.srt ← subtitle text, narration duration
clip.mp4      ← image fp + narration fp + srt fp + camera_motion + duration + video provider
preview.mp4   ← 所有 clip fp + transitions（組裝很快，永遠重做）
```

修改 Scene 3 的旁白 → 只重做 Scene 3 的 narration/srt/clip，Scene 1–2、4–N 的檔案 byte-for-byte 不變（有測試保證）。

## 8. Worker / Executor（`see/workers/`）

```python
@dataclass Task: task_id, kind, requires: set[str], fn, kwargs
class Executor: submit(task) -> TaskResult
class LocalExecutor(Executor): capabilities = {"cpu","ffmpeg",...}; 同步執行
```

Phase 0：所有階段都透過 `LocalExecutor` 執行。
未來：`QueueExecutor`（NAS 排隊、GPU PC 領取）實作同一介面，Orchestrator 不改。

## 9. Storage 佈局

```
workspace/projects/<project_id>/
  project.json              Project（含 script、scenes、approvals、render_jobs）
  input.txt
  scenes/<scene_id>/{image.png, narration.wav, subtitles.srt, clip.mp4, manifest.json}
  renders/{preview.mp4, preview.json(timeline), final.mp4}
```

## 10. 借鏡（video-autopilot-kit，MIT；只借思路不複製碼）

- 證據鏈 / receipt：每個產物都有 hash，下游依賴上游 hash（本專案以 fingerprint manifest 實作）。
- 人工審片不可由機器代填：`APPROVED`/`FINAL` 只能由 approve 命令寫入。
- Fail-closed schema：只接受驗證通過的結構化輸出。
- 逐景時間預算：每景 3–12 秒、整支 30–60 秒的規劃約束放在 storyboard 階段。
- 離線合成 fixture 測 CI：e2e 測試不依賴網路或付費服務。

## 11. Web UI（Phase 0.5）

```
瀏覽器 ──HTTP──▶ FastAPI (see/ui/server.py) ──▶ BackgroundRunner (單 worker thread) ──▶ Orchestrator ──▶ Executor
                     │                                                                       ▲
                     └── GET /api/projects/{id}  (每 2 秒輪詢 job state / stage / scenes) ────┘
                     └── GET /api/projects/{id}/preview.mp4  (FileResponse, HTTP Range → 手機可播)
```

- 一個 Project 同時只允許一個 job（409）；job 狀態 idle / queued / running / done / failed 與 stage（script / storyboard / assets / render）。
- 每個 Project 有 `OutputSpec`（16:9 / 9:16 / 1:1）與 `speech_speed`；兩者都進 fingerprint，改了才重做。
- 幣別預設 TWD，UI 顯示 `NT$0`；成本區同時列出每個 Provider 的 cost_tier。
- UI 的修改／重做／核准／Final 全部走 Orchestrator 的同一套方法，與 CLI 行為一致。

## 12. 產品流程對照（D-032；客戶確立的目標流程）
| 步驟 | 模組／資料 | 現況 |
|---|---|---|
| 故事 | `Project.input_text` → `write_script`（`LLMProvider`） | Mock（DG-10） |
| Style Profile | `Project.style_id` → `see/core/styles.py` `apply_style` → `ImageRequest` | 6 個內建；default 已驗證；產品優先序 P1 anime／realistic／cinematic（D-034） |
| 角色設定 | `Project.characters[id]`（voice＋`appearance`）；`scene.character_ids` | 文字錨點＋結構化 refs |
| Voice 選擇／試聽／語速 | `set_character`／`preview_voice`／`confirm_character`（D-030） | CLI＋API；UI 待 DG-19 |
| 分鏡與影像 | `storyboard` → `image_request` → `ImageProvider`（SD 1.5） | Real |
| narration | `resolve_voice` → `TTSProvider`（Kokoro） | Real |
| BGM／SFX | render 階段 `AudioLayer`（`AudioProvider`） | Real（procedural；預設 null） |
| Lip-sync | per-scene `_lipsync_stage`（`LipSyncProvider`，opt-in） | 介面＋stage；無模型 |
| Preview → 人工微調 → Final | `render(PREVIEW)` → `update_scene`／`regen` → `approve` → `render(FINAL)`（需角色確認） | Real |

相容性原則：每個新層都在「未設定」時與舊版逐位元相同（style=default、無 appearance、lipsync=False／null、audio=null）。

## 13. 使用者偏好層與「生成後調整→再生成」（D-042；入口，未完整實作）
```
使用者偏好（結構化、可修改、可版本化）            模型／引擎（可替換）
  StyleProfile（風格、色彩、光影）                 ModelRouter（未來；DG-20 後）
  CharacterProfile（外觀、服裝、聲音）   ──資料──▶   └ preset：checkpoint、scheduler、clip skip、VAE、授權
  CompositionPrefs（構圖、鏡頭、景別）               ImageProvider／TTSProvider／…（Provider Agnostic）
  GenerationSettings（解析度政策、品質／速度）
        ▲
  選項式調整 ／ 自然語言描述 →（LLM／規則）→ 同一份結構
```
| 能力 | 現況 | 缺口 |
|---|---|---|
| 生成前選風格 | `set_style`（`Project.style_id`，6 內建 Style Profile） | 使用者自訂／微調 Style Profile（目前只能選內建） |
| 生成後改風格再生成 | `set_style` 使全景回 DRAFT；image fingerprint 含 style terms → 下次 build 只重做 image 與下游 | 只改部分景的風格（per-scene override） |
| 人物外觀 | `set_character_appearance`（CharacterAppearance 錨點＋結構化 refs） | 外觀變更 → 自動標記「有此角色的景」需重生（目前靠 fingerprint 自然失效，需驗證並加報表） |
| 單景調整 | `update_scene`／`regenerate_scene` | 構圖／鏡頭欄位（目前混在 visual_description／image_prompt_en） |
| 色彩／構圖／鏡頭 | 無結構欄位 | `CompositionPrefs`、色彩偏好（Style Profile 子欄位或獨立） |
| 自然語言偏好 | 無 | 需真 LLM（DG-10）把描述轉成結構化設定；轉換結果需人工確認 |
| 換模型不重建偏好 | 偏好層與 provider 已分離（style terms 由 `apply_style` 附加；checkpoint 參數在 `CheckpointSpec`） | ModelRouter（style.family → preset）未實作 |
| 偏好版本／比較 | 無 | 偏好快照（每次再生成記錄使用的偏好版本，供 A/B 與回復） |

## 14. Character Identity／Reference Image（D-046；規格入口，未實作）
目標流程：參考照片 →（本機）擷取／維持辨識特徵 → 選風格 → 角色預覽 → 人工確認 → 跨場景保持同一角色。
- 偏好層：`CharacterAppearance`（現有：description_en／outfit_en／features_en／reference_images／seed／adapter）。缺口：結構化欄位（gender_presentation、age_range、appearance_region、hair、facial_features、outfit、body_type、distinctive_marks）→ 由確定性組裝成 prompt 錨點；舊欄位相容。
- 模型層：prompt 型 provider 用文字錨點；Identity 型 provider（未來 IP-Adapter／FaceID 類）讀 `reference_images`＋`adapter`（model-specific）。核心不依賴任何特定 adapter。
- 隱私：參考照片只在本機 workspace，不進 Git／fixture／第三方（PROJECT_RULES §16）。
- 驗證案例：`east_asian_female_portrait`、`east_asian_male_portrait`（與 `girl_portrait_closeup` 只差人物描述）。
