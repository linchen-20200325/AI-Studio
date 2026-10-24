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
workspace/identity_refs/<people|animals|characters|backgrounds>/   Reference Library（D-056，§14.6；不進 Git）
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
| 生成後改風格再生成 | `set_style` 使全景回 DRAFT；image fingerprint 含 style terms → 下次 build 只重做 image 與下游 | per-scene override：**DONE（D-062）** `Scene.preferences.visual_style_id` |
| 人物外觀 | `set_character_appearance`（CharacterAppearance 錨點＋結構化 refs） | 外觀變更 → 自動標記「有此角色的景」需重生（目前靠 fingerprint 自然失效，需驗證並加報表） |
| 單景調整 | `update_scene`／`regenerate_scene`；**D-063** 中文圖片描述 `image_prompt_zh`＋人物演出覆寫 `Scene.characters`（§13.1／§13.2） | 構圖／鏡頭欄位（目前混在 visual_description） |
| 色彩／構圖／鏡頭／氛圍／光線 | **DONE（D-062，非 UI）**：`see/models/preferences.py` PreferenceSet（mood／lighting／color_tone／camera／composition＝preset 標籤＋custom_en 詞；generation.gen_policy） | preset → prompt 詞對照無規格（目前只有 custom_en 進 prompt；preset-only 標 `no_prompt_effect`）；UI＝DG-19 |
| 自然語言偏好 | D-063：人物中文原話 `raw_character_direction_zh` 只保存 | 需真 LLM（DG-10）把描述轉成結構化設定；轉換結果需人工確認 |
| 換模型不重建偏好 | 偏好層與 provider 已分離（style terms 由 `apply_style` 附加；checkpoint 參數在 `CheckpointSpec`） | ModelRouter（style.family → preset）未實作 |
| 偏好版本／比較 | **DONE（D-062）**：image evidence（manifest meta）記 `preference_snapshot`（resolved＋每欄來源＋sha256＋no_prompt_effect） | 偏好歷史版本列表／回復 UI |
| 再生成範圍 | **DONE（D-062）**：`regeneration_scope()`／`Orchestrator.edit_impact()`／`set_preferences()` 依 fingerprint 相依推導（偏好／圖片描述 → image＋clip；旁白 → narration＋subtitle＋clip；轉場 → 只重組 render）；只有 resolved 偏好真的改變的景回 DRAFT | — |

**D-062 解析順序**：Project default（`Project.style_id`＋`Project.preferences`）→ Scene override（`Scene.preferences`，逐欄位）。Character default（`CharacterDefinition.default_style_profile／default_mood_profile`）**尚未參與**：多角色同景以誰為準沒有規格 → NEEDS HUMAN DECISION。Project 層 visual style 唯一來源是 `style_id`（不接受 `preferences.visual_style_id`，避免雙來源）。偏好 `extra="forbid"`：身份資料（gender、character_id、reference）不得混入。舊資料沒有這些欄位 → None → request／fingerprint 完全不變。

### 13.1 中文輸入 → 模型 prompt（D-063；PROJECT_RULES §18）
```
一般 UI（繁中）                            內部（Advanced／evidence 才看得到）
Scene.image_prompt_zh「圖片描述」 ──▶ PromptTranslator ──▶ 英文 base prompt ┐
Scene.characters（表情／動作…）    ──▶ preset 直譯／自訂中文經 translator ──┼──▶ apply_style ＋ 偏好詞 ＋ 角色錨點 ──▶ ImageRequest
（無中文描述）image_prompt_en（legacy）／image_prompt ─────────────────────┘
```
- `see/core/scene_prompt.py`：`PromptTranslator`（contract）；`KeywordFallbackTranslator`（預設，確定性關鍵詞，非 AI）；未來 LLM translator 實作同介面即可替換（DG-10）。
- prompt 來源優先序：`image_prompt_zh`（zh_generated）→ `image_prompt_en`（legacy_en）→ `image_prompt`（legacy_image_prompt）。`advanced_override` 保留、未實作。
- evidence（image manifest meta，不進 fingerprint）：`prompt_source`、`scene_characters`（applied_fields／no_prompt_effect／raw_direction_saved／raw_direction_applied=false）。
- 舊 Scene（無 zh、無 characters）→ prompt 與 fingerprint 完全不變。

### 13.2 Scene Character Override（D-063；PROJECT_RULES §17）
| 永久（CharacterDefinition／CharacterAppearance） | 每幕（`Scene.characters: list[SceneCharacter]`） |
|---|---|
| 臉型、五官、髮型、髮色、基本服裝、固定特徵、default voice、default style／mood | 表情 expression、情緒 emotion、動作 action、視線 gaze（＋看誰）、姿勢 pose、本幕服裝 outfit_override、畫面位置 placement（左／中／右）、景深 depth（前／中／後）、notes、中文原話 raw_character_direction_zh |
- 結構化欄位：preset 或「自訂」中文；只在使用者明確選擇／填寫時存在。中文原話只保存（無可靠解析前不拆欄位、不進 prompt）。
- 驗證（fail closed）：覆寫角色 ⊆ `Scene.character_ids`、不重複、視線對象在本幕、`extra="forbid"`。
- 再生成：`characters.<欄位>` → image＋clip（＋lipsync）；display_name／notes／raw direction → 無。旁白／字幕不受影響。
- 與 §17 `ScenePlacement`（CharacterDefinition 路線，Layered Scene 用）並存：兩者合併需 Character Library 與 Project 綁定裁示後再做（不做不可逆遷移）。

## 14. Character Identity／Reference Image（D-046；規格入口，未實作）
目標流程：參考照片 →（本機）擷取／維持辨識特徵 → 選風格 → 角色預覽 → 人工確認 → 跨場景保持同一角色。
- 偏好層：`CharacterAppearance`（現有：description_en／outfit_en／features_en／reference_images／seed／adapter）。缺口：結構化欄位（gender_presentation、age_range、appearance_region、hair、facial_features、outfit、body_type、distinctive_marks）→ 由確定性組裝成 prompt 錨點；舊欄位相容。
- 模型層：prompt 型 provider 用文字錨點；Identity 型 provider（未來 IP-Adapter／FaceID 類）讀 `reference_images`＋`adapter`（model-specific）。核心不依賴任何特定 adapter。
- 隱私：參考照片只在本機 workspace，不進 Git／fixture／第三方（PROJECT_RULES §16）。
- 驗證案例：`east_asian_female_portrait`、`east_asian_male_portrait`（與 `girl_portrait_closeup` 只差人物描述）。

## 15. 長期目標：連續劇情 AI 短劇（D-047；能力缺口地圖，未實作）
三條視覺路線（真人／電影感、日系動畫、半寫實 3D）＝ Style Profile＋模型 preset 的組合，皆走 Provider Agnostic 介面；路線不綁模型。

| 能力 | 現況（已有） | 缺口 |
|---|---|---|
| Character Identity | `CharacterAppearance` 文字錨點、`reference_images` 欄位（未使用）、§14 規格 | 結構化欄位；Identity provider（IP-Adapter／FaceID 類，RESEARCH）；跨鏡頭／服裝 Identity 驗證案例 |
| Multi-character Scene | 單一人物 prompt | 多角色 layout／區域 prompt；不交換臉／衣服／設定的 controlled test |
| Image-to-Video | Ken Burns（靜態圖推拉）；`VideoProvider` 介面 | 真動態（人物動作、表情、鏡頭）；LOCAL_FREE＋GTX 1650 4 GB 可行性**未知／可能不足**（RESEARCH，須明說） |
| Dialogue Performance | Kokoro TTS、角色 voice、字幕 | 真 Lip-sync provider（目前僅介面）；多角色台詞→角色→聲音對應；字幕／timeline 對齊驗證 |
| Audio／Editing | BGM＋ducking（E2-3）、SFX（聽感未驗）、FFmpeg timeline | ambience、shot transition、自動剪輯節奏 |

### 14.1 已實作（D-048）：結構化 Character 設定（非 UI）
- `CharacterTraits`（`see/models/project.py`）：gender_presentation、age／age_range、appearance_region、hair_style、hair_color、facial_features、body_type、distinctive_marks——全部可選、自由文字、**無任何預設值或 enum**。
- `CharacterAppearance.traits`（可選）；`anchor_text`＝traits 確定性組裝（主體→年齡區間→體型→髮→五官→辨識特徵）＋舊欄位（description／outfit／features）。`traits=None` → anchor 與舊版逐字相同 → 既有 image fingerprint 不變；舊 project.json 可直接載入。
- 角色 A／B：同景多角色各自錨點、順序依 `scene.character_ids`，`params.characters` 帶 character_id（未來 Identity provider 用）；改某角色只讓其出現的景回 DRAFT。
- `reference_images` 只收本機路徑（拒絕 URL，§16）；仍無 provider 使用。
- 入口：CLI `appearance <pid> <cid> --gender --age --age-range --region --hair-style --hair-color --facial-feature --body-type --mark`；API `POST /api/projects/{pid}/characters/{cid}/appearance`（`traits` 物件，驗證失敗 422）。
- 限制（誠實）：SD 1.5 prompt 型 provider 對同框多角色屬性綁定能力弱（可能互換臉／衣服），文字錨點**不保證** Identity → 需 Multi-character controlled test 與 Identity provider 研究。

### 14.2 Multi-character controlled test（D-049）
- 案例 `two_characters_ab`（`see/core/style_tests.py`）：`CaseCharacter` 以產品同一條路徑（`CharacterAppearance`／`CharacterTraits` → `anchor_text`）產生 A／B 錨點；`multi_character_prompt` 確定性組裝「人數 → 錨點＋位置 → 共用構圖」。
- A／B 屬性刻意互斥（女／男、黑長直髮／灰短髮、紅大衣／灰西裝、圓眼鏡只在 B）→ 人工審圖可判斷互換或混合；evidence 記 `case_characters`（anchor＋swap_checks）。是否互換**只由人工判定**，不做自動評分。
- 構圖詞為 portrait 系列精簡子集，以守 CLIP 77 token（測試粗估 P1 各風格 ≤75；真機 evidence 另記實測 `prompt_tokens／prompt_truncated`）。

### 14.3 D-049 真機結論（D-050）
prompt-only 文字錨點在 SD 1.5 同框時**無法綁定屬性**（眼鏡、髮色、服裝互相污染），臉部 Identity 也無法以文字表達 → 架構上 Identity 需「區域條件（regional）」＋「參考圖條件（IP-Adapter 類）」兩種 provider 能力；偏好層（CharacterTraits／reference_images）不變，能力差異屬 provider／模型層。研究見 `DG24_MULTI_CHARACTER_IDENTITY_RESEARCH.md`。

### 14.4 S1／S2 prompt 條件模式（D-051；opt-in 診斷）
- `ImageRequest.params["prompt_mode"]`：`{"long_prompt": true}` 或 `{"long_prompt": true, "regional": {"base", "regions", "layout": "columns"}}`；不帶＝既有行為與 fingerprint 完全不變。
- 實作在 provider 層（`see/providers/image/diffusers_local.py`：`chunk_token_ids`、`encode_text_chunks`、`RegionalAttnProcessor`、`regional_processors`）；偏好層（CharacterTraits）不變 → 未來 regional 能力可由其他 provider 以不同方式實作（Provider Agnostic）。
- regional prompt 由案例資料組裝（`regional_prompts(case)`：base 不含任何角色屬性）；產品化前需把「角色 → 畫面區域」從測試案例提升到 Scene／Storyboard 資料（BACKLOG）。

### 14.5 S4 Identity conditioning（D-054；opt-in）
- `ImageRequest.params["identity"]＝{adapter_id, references:[{character_id, path, sha256, bytes, source}], layout:"columns"}`；不帶＝既有行為。
- Provider（`diffusers_local.py`）：image encoder 在 CPU 產生 embeddings（快取鍵＝encoder sha＋參考圖 sha）→ `load_ip_adapter(image_encoder_folder=None)` → 每角色一張分欄 mask（IP-Adapter 內建 masking）→ 生成 → `unload_ip_adapter`＋還原 processors。不與 S2 regional 疊加。
- Adapter 型錄／下載／provenance：`see/providers/image/adapters.py`（模型層；偏好層只持有 reference_images）。
- **Binding 鏈（D-056 已追溯驗證）**：character `position` →`region_of`→ 左→右排序 → refs[i] ↔ `ip_adapter_image_embeds[0][:, i]` ↔ `ip_adapter_masks[0][:, i]`（adapter 0）。執行期自檢 mask 幾何；evidence 記 `assigned_region`／`adapter_index`／`image_index`／`mask_bounds_gen_px`，style-test 另記 `identity_region_map`（輸出圖座標）＋本機疊圖 `<stem>_identity_regions.png`。
- 已知限制：mask 只限制臉部特徵殘差的作用區，**不控制人物站位或性別呈現**（站位仍由文字＋模型決定）；位置控制另走 DG-26。

### 14.6 Reference Library（D-056；D-058 升級 → 見 §17.3）
- 舊路徑 `workspace/identity_refs/` 保留為 **legacy 相容路徑**；主路徑與 metadata 規格見 §17.3。

## 16. Layered Scene（D-057；客戶裁示的正式產品方向；PoC 見 DG26 研究）
角色一致性**不靠「一個模型一次畫完整 Scene」**。Scene 由獨立層組成，各層各自生成／驗證／保存 provenance，最後合成：
```
Scene
 ├─ Background Layer          （環境；Reference Library backgrounds/ 未來接入）
 ├─ Character Layer A／B／…    （people／animals／characters 各自 conditioning；目前只 people）
 ├─ Props Layer               （BACKLOG）
 ├─ Effects Layer             （BACKLOG）
 └─ Text／Subtitles Layer      （既有字幕燒錄；尚未納入 layer 模型）
```
- 修改單一人物或元素時**只重做受影響的層**再重新合成，不整張 Scene／整支影片重生（與 §13「生成後調整→再生成」、per-scene fingerprint 一致）。
- 每層輸出＝圖片＋mask＋evidence（來源 stem、sha256、case、seed、checkpoint、identity reference sha256）；合成 evidence 記 placement、深度、重疊、harmonization 參數。
- **每層欄位（D-058）**：`layer_id`、`layer_type`（background／character／props／effects／text）、source asset（stem＋sha256）、`character_id`（角色層必填；**身份主鍵一律是穩定 character_id，不用 A／B、左右或男女**）、provenance、placement、`style_override`、`regeneration_scope`。`compose-scene` 會驗證角色層來源 evidence 的 character_id 等於 layer_id，否則 fail closed；舊 A／B 定義（historical_reversed_character_mapping）的來源拒收。
- 判定分層：technical（自動）與 scene／identity／貼上感（人工）分開；commercial_cleared 隨模型走，與技術品質分開。
- 現行實作（D-057 PoC）：`see/core/compose.py`（鍵控去背、擺位、色彩平移、接觸陰影）＋CLI `compose-scene`／`compose-review`；輸出 `workspace/compositions/<name>/`（不進 Git）。

## 17. Character Definition、Reference Asset、Reference Library 與角色 UI（D-058；PROJECT_RULES §17）
起因：v1 測試案例把 char_a 定義為女性、char_b 為男性，與客戶「A＝男、B＝女」及 reference 指派相反——reference 綁對了，角色定義卻錯（隱性錯誤）。修正方向：身份鍵與所有屬性分離、全部顯式、生成前 gate＋人工確認卡。

### 17.1 Character Definition Schema（`see/models/character_definition.py:CharacterDefinition`）
| 欄位 | 型別／規則 |
|---|---|
| `character_id` | 穩定 slug（`^[a-z][a-z0-9_]{1,63}$`，產品建議 `char_001`）；**不隱含性別／位置／style／voice／類型** |
| `display_name` | 使用者看到的名稱（例「男主角」） |
| `character_type` | `person`／`animal`／`fictional_character` |
| `gender_presentation` | `male`／`female`／`nonbinary`／`unspecified`（預設 unspecified；≠ biological sex；unspecified 時 prompt 不輸出性別詞） |
| `age_impression`、`appearance_region` | 自由文字；appearance_region 只有使用者明確指定才填，空＝unspecified；**不從圖片推論** |
| `face_shape`、`facial_features[]`、`hair_style`、`hair_color`、`distinctive_marks[]`、`outfit`、`expression` | 外觀（可空、不補值） |
| `reference_asset_ids[]` | 指向 ReferenceAsset（歸屬以 asset 的 character_id 為準，gate 檢查一致） |
| `default_style_profile`、`default_mood_profile` | 預設引用；Scene 可 override（§17.5） |
| `voice_profile` | `VoiceAssignment{voice_id, speed, emotion}`；預設值，Scene 可 override |
| `notes` | 備註 |
- 與既有層的關係：`to_appearance()` 產生既有 `CharacterAppearance`／`CharacterTraits`（D-048 prompt 錨點層）；style／mood／voice 不進外觀錨點。現有 `Project.characters`（`CharacterVoice`）尚未遷移到本 schema（BACKLOG；不做不可逆 migration）。
- 位置是 Scene 屬性：`ScenePlacement{character_id, horizontal(left/center/right), depth(foreground/midground/background), shot_size, action, pose}`。

### 17.2 Reference Asset Schema（`ReferenceAsset`）
`asset_id`、`category`（people／animals／characters／backgrounds／styles）、`file_path`（本機、不收 URL）、`character_id`（角色用途必填）、`role`（identity_face／full_body／outfit／pose／style_reference／background_reference）、`provenance`（dict）、`sha256`、`source_type`（user_supplied／generated／imported）、`commercial_clearance_status`（cleared／not_cleared／unknown，預設 unknown）、`is_primary`、`notes`。
- role 與 category 必須相容（例 style_reference 只能是 styles；identity_face 只能是 people／animals／characters）。
- 檔名可自由（例 `hero_male_v1.jpg`）；**誰、用途、來源、可否商用只看 metadata**，不看檔名（禁止 `char_a.jpg` 式猜測）。
- 目前支援矩陣：只有 (people, identity_face) → S4 `--identity`（研究用）；其他組合 `support_status()`＝`not yet supported`。

### 17.3 Reference Library（正式規格）
```
workspace/reference_library/          ← 主路徑（本機；workspace/ 已 gitignore，不進 Git）
  people/        人物身份／臉／全身／服裝／pose     identity_face：研究用（S4）；其他 not yet supported
  animals/       動物外觀                          not yet supported
  characters/    虛構角色／角色設計                 not yet supported
  backgrounds/   場景／環境                         not yet supported
  styles/        風格／色調／畫風                   not yet supported
  <任意檔名>.<ext> ＋ 選用 sidecar <檔名>.<ext>.ref.json（ReferenceAsset metadata）
workspace/identity_refs/              ← legacy 相容路徑（D-056），只讀，不再新增
```
- CLI：`--ref <character_id>=<category>/<檔名>`（先找 reference_library，再找 legacy）；evidence 記 `source=reference_library`／`reference_library_legacy`、類別、sha256、bytes、asset metadata。
- sidecar 存在時：character_id、sha256、role 必須與本次綁定一致，否則 fail closed；不存在時，綁定只來自使用者顯式 `--ref`。
- 未來 UI 以 metadata 為主，不依賴資料夾或檔名判定身份；資料夾存在 ≠ 功能完成。
- GitHub 只保存 schema、規則、provenance metadata 與路徑慣例；私人圖片永不 commit。

### 17.4 Character Validation Gate（`validate_characters()`）
生成前檢查，blocking 衝突 → **fail closed**（不生成、列出需修正項目）：
character_id 唯一｜asset_id 唯一｜角色用途 reference 必須綁定存在的角色｜role 與 category 相容｜角色類型與 reference 類別相符｜同一 reference（sha256）不得綁多個角色｜角色引用的 asset 確實屬於該角色｜每個角色恰好一個明確 placement、不得兩人同位｜（選用）每角色需有 identity_face｜主要 reference 至多一張｜私人圖片不得在 repo 內 workspace/ 以外位置｜商用授權 unknown／not_cleared：內部診斷為警告，正式輸出（`final_output=True`）為 blocking。
- `gender_presentation` 由 enum 保證為明確值或 unspecified。
- 現接線：`style-test --identity` 的 `--ref` 路徑（`_character_gate`）、`compose-scene` 角色層 character_id 驗證。UI 接線見 BACKLOG。

### 17.4.1 後端服務（D-062）
- `see/core/reference_library.py:ReferenceLibrary`：list（含 legacy 唯讀、未登記／支援度／問題）、register（算 sha256、寫 sidecar；legacy 不可登記）、validate（sha256、類別、檔名、role×category、primary 必須綁角色）、bind／unbind、mark_primary（同角色唯一）；只寫 metadata，不碰圖片。CLI：`ref list|register|bind|primary`。
- `see/storage/character_store.py:CharacterStore`：`workspace/character_library/<id>.json`；create／get／list／update（revision＋1、character_id 不可改、封存中不可改）／archive／restore；**無 hard delete**。與 `Project.characters` 的綁定／遷移待裁示。
- `confirmation_payload()`（`character_definition.py`）：每角色 display_name、character_type、gender_presentation、primary reference、outfit、style、mood、voice、placement；同時跑 Validation Gate，`can_generate=False` 時 UI 不得允許生成。

### 17.5 Style／Mood／Voice 與身份解耦
- Style 不是一個不可拆的 prompt 字串：至少拆 **Visual Style、Mood、Lighting、Color Tone、Camera**（現有 `StyleProfile` 仍是合併的 prompt 詞，拆分為 BACKLOG）。
- 角色可有 `default_style_profile`／`default_mood_profile`，**每個 Scene 可 override**；同一角色可有寫實／動畫／3D／恐怖／溫暖版本，身份欄位不變。
- Voice：角色可有預設 `voice_profile`；Scene 可 override voice／speech speed／emotion；voice 資料與身份資料分離，經 character_id 綁定（既有 `CharacterVoice` 的 confirm 流程 D-030 沿用）。

### 17.6 角色 UI／UX（正式需求；實作在 BACKLOG）
主流程：**角色 → 參考圖 → 外觀 → 風格 → 聲音 → 場景位置 → 確認 → 生成**。
- A 基本資料：角色名稱、Character ID（唯讀顯示）、角色類型、性別呈現、年齡感、備註。
- B 外觀：臉型、五官、髮型、髮色、服裝、特徵、表情。
- C Reference：上傳、從 Reference Library 選、每張顯示綁定角色與用途、多張、更換、刪除、指定主要 reference、顯示來源與 provenance。
- D Visual Style（獨立於身份）：寫實、日系動畫、3D、繪本、自訂。
- E Mood：溫暖、恐怖、陽光、悲傷、浪漫、懸疑、自訂。
- F 其他視覺：Lighting、Color tone、Camera、Composition。
- G Voice：聲音、語速、情緒、試聽。
- H Scene Placement：左／中／右、前景／中景／後景、景別、動作、姿勢。
- **Character Confirmation Card**（生成前必經）：每角色一行，例「男主角｜男性｜hero_male_v1.jpg｜灰西裝｜左側｜寫實｜冷色｜Voice A」「女主角｜女性｜heroine_v1.jpg｜紅大衣｜右側｜寫實｜暖色｜Voice B」；至少顯示 display_name、gender_presentation、reference image、outfit、position、style、mood、voice；任一不一致可在此步直接修改；Gate 有衝突時不能按「生成」。目的：杜絕「reference 綁對但角色定義錯」。
- 一般 UI 不顯示 char_a／IP-Adapter／checkpoint／CUDA／model path／prompt token；技術參數放 Advanced／Debug。

### 17.7 Reference Quality Check（D-059；UI 規格，尚未實作；不做自動臉辨識）
上傳／選取 reference 時，UI 以檢查清單引導（目前由使用者自評勾選；日後若導入人臉偵測，需另經授權 Gate，且不得輸出性別／年齡等敏感推論）：
- 臉部尺寸：臉部高度建議 ≥ 圖片高度的 40%（近照）；過小 → 建議裁切或換圖。
- 遮擋：口罩、墨鏡、手、頭髮遮臉 → 警告。
- 模糊／過暗／過曝 → 警告。
- 多人：畫面有其他人 → 必須裁成只剩本人，或換圖。
- 角度：至少一張正面；建議再補 1～2 張側面／半側面。
- 張數：建議 2～5 張（不同光線／角度），並指定一張主要 reference。
- 每張圖仍需 ReferenceAsset metadata（綁定角色、用途、來源、商用授權）；私人圖只在本機。

### 17.8 Identity Consistency 驗收標準（D-059）
- 驗收單位是 **character_id 跨 Scene**，不是「生成一張像」：同一角色在 **不同背景、不同服裝、不同表情、不同角度、不同鏡頭、不同 Style** 下，仍可被人工辨識為同一角色。
- 判定欄位分離：`technical_valid`（自動）≠ `identity_validated`（人工，single-user subjective）≠ scene／style；不可由 technical_valid 或畫面好看推論 identity pass。
- 最小驗收矩陣（建議）：每個角色 ≥ 6 張（背景×2、服裝×2、表情／角度×2，至少一張不同 Style），逐張人工判定「像／不像」，並記錄 reference asset sha256 與生成條件。
- 單張 PoC 只能證明「可能像」，不能證明 Identity Consistency。

## 18. Hardware Upgrade Resume Gate（D-061）
`Identity Preservation / Character LoRA = HARDWARE_UPGRADE_BLOCKED`（GTX 1650 4 GB：plus-face 已證實不足，D-057／D-059；FaceID 類需 InsightFace 非商用模型；LoRA 訓練與 SDXL／FLUX 在 4 GB 不實際，DG-28）。
重新開啟前必須重新檢查並寫入 GitHub：
1. GPU 型號、VRAM、CUDA／torch 版本相容（`python -m see.app.cli hardware`）
2. 可用硬碟（模型＋訓練暫存）
3. 當時最新 identity route（DG-28 研究結果視為過期，需重查一手來源）
4. 模型授權、face encoder／detector 授權、訓練資料限制、商用授權（分層，見 DG-28 §2）
5. 訓練時間與每角色 reference 數量（使用者負擔）
VRAM 規劃參考（**只是 resume planning，不得硬編為永久硬體需求**）：4 GB 不再投入 Character LoRA 訓練｜12 GB 可重評 SD1.5 Character LoRA｜16 GB 較適合長期角色 LoRA／部分 SDXL workflow｜24 GB 再評更大型 identity／SDXL／video。

## 19. Environment Bootstrap 與 Migration Foundation（D-064；PROJECT_RULES §19）
```
doctor（唯讀）──▶ checks[OK|PARTIAL|UNAVAILABLE|ERROR] ──▶ readiness（Ready／Not ready）＋ Tier A–D
   │  system／python／gpu／tools／models（logical ID＋相對 SEE_MODELS_DIR）／workspace（schema＋可載入性）
   ├─▶ --write-manifest → workspace/environment_manifest.json（machine-local；docs/environment_manifest.example.json 為範例）
bootstrap（唯讀計畫）──▶ auto_safe／user_action／needs_approval／blocked；--apply-safe 只建空資料夾＋workspace_version.json
env-export ──▶ workspace/exports/env-<時間>/（manifest、套件清單、模型 manifest、workspace inventory、settings）
smoke ──▶ 暫存 workspace：mock→placeholder→silent→Ken Burns→ffmpeg＋Web API 匯入
```
- 程式：`see/core/environment.py`；CLI：`doctor`、`bootstrap`、`env-export`、`smoke`（`see/app/cli.py`）。
- 搬移相容：Reference sidecar 存 `<category>/<file>`＋sha256（只比對檔名＋hash）；ProjectStore 讀 manifest 時把不存在的舊絕對路徑對應到本景資料夾同名檔（fingerprint 不含路徑）。
- Schema 版本：workspace（`workspace_version.json`）、CharacterRecord、ReferenceAsset、environment manifest；缺欄位＝v1，比程式新＝fail safe。遷移：先 `CharacterStore.backup()`，`migration_plan()` 只列出；不可逆遷移 → Decision Gate。
- 設定分類：portable（provider 選擇、預設 voice、專案內偏好）vs machine-specific（workspace、models_dir、模型路徑、TTS 裝置、ffmpeg、字型、CUDA／GPU）。持久化設定機制待裁示。
- 流程與指令：docs/ENVIRONMENT_SETUP.md、docs/MIGRATION_REINSTALL.md。

### 19.1 專案本機設定檔（D-065）
`see.local.json`（repo 根、`.gitignore`）→ `Settings` 的 machine-specific 欄位（models_dir、workspace、模型路徑、tts_device、ffmpeg／ffprobe、subtitle_font）。優先序 env > local config > 程式預設；`see.core.config.setting_source()`；CLI `config`；doctor `config` 群組顯示來源。只收 machine-specific key、不收 secret／偏好；壞檔整份不採用。

## 20. Scene 結構化設定（D-065；PROJECT_RULES §20）
```
Scene.settings（SceneSettings：13 欄，preset 或中文自訂；None＝未指定）
   └─ scene_prompt.settings_terms：preset 逐字直譯／自訂中文 keyword_fallback → 英文詞（轉不到 → no_prompt_effect）
base prompt（zh／legacy）→ ＋Scene 設定詞 → ＋角色演出詞 → apply_style → ＋偏好詞（被 Scene 結構化欄位取代的維度除外）→ ImageRequest
```
| 一般 UI | 欄位 | 單一來源 | 重做 |
|---|---|---|---|
| 背景／環境／地點／時間／天氣 | settings.background…weather | Scene.settings | image＋clip |
| 構圖／取景／景別／鏡頭角度／焦點 | settings.composition…focus_target | Scene.settings | image＋clip |
| 光線／色調／氣氛 | settings.lighting／color_tone／mood | Scene.settings（取代同名偏好維度） | image＋clip |
| 視覺風格 | preferences.visual_style_id | Scene.preferences | image＋clip |
| 鏡頭運動 | camera_motion | Scene（既有） | 只有 clip |
- 與 Scene Character Override（§13.2）、CharacterDefinition（§17）分離；舊 Scene 無 settings → prompt／fingerprint 不變，evidence `scene_settings.source=legacy_none`。
- **D-066 客戶裁示**：(1) 不做 Project 層結構化場景預設（Scene.settings 只在 Scene 層）；(2) `visual_description` 與 `Scene.settings` 並存、不互相自動改寫（visual_description＝畫面說明／caption；settings＝prompt builder 詞）。

## 21. 角色資料唯一架構（D-066 設計；未實作；全文：docs/CHARACTER_LIBRARY_PROJECT_BINDING.md）
```
Character Library（唯一來源）                         Project                              Scene
 CharacterRecord head ＋ history/<id>/r<n>.json  ◀── cast: {character_id: {revision,  ◀── character_ids／narrator_id
 （definition、default voice／style／mood、           role_label, alias, follow,            SceneCharacter 演出覆寫
   reference_bindings{asset_id,sha256}、archived）    voice_confirmed_revision}}            scene voice／style override
          │ reference_bindings → Reference Library（<category>/<file>＋sha256）
```
- 現況：production 只用 `Project.characters`（CharacterVoice）；CharacterDefinition／Store 未接 pipeline。**D-067 Batch 2**：Store 已有不可變 revision history（`character_library/history/<id>/r000001.json`，append-only、canonical content_sha256、凍結 reference metadata；legacy 角色首次修改前建立 baseline，不補造更早歷史）；`CharacterBinding`＋`resolve_binding()`（pinned revision，缺失／hash 不符 fail closed，reference 遺失 → generation_ready=False 且不改綁）尚未接 Project。
- 推薦綁定：**revision pinning**（D）；revision 缺失或 hash 不符 → fail closed；跟隨最新只能顯式設定；永不自動更新。
- 解析鏈：Character default（pinned revision）→〔Project override：無規格，不實作〕→ Scene override。
- **D-070 Batch 4.1**：`see/core/migration_decisions.py`：versioned 人工決定檔（create_new／bind_existing／keep_legacy／narrator_setting／ignore_unused）驗證＋重算 migration_ready 與 proposed rewrite plan（stale／錯誤 fail closed；只讀；不改 analyze()）。規則見 CHARACTER_LIBRARY_PROJECT_BINDING §8.5。**Batch 4.1 remains analysis-only. No project has been migrated.**
- **D-069 Batch 4**：`character-migrate <pid> --dry-run`（`see/core/character_migration.py`）只分析：versioned JSON（migration_report_schema_version 1）＋中文摘要、5 種分類、固定 conflict code、reference sha256 分析、Scene／對白／旁白引用與改寫數、report_input_hash、zero-write proof。**Batch 4 only analyzes. No project has been migrated.**
- **D-068 Batch 3**：`Project.cast: list[CharacterBinding]`（預設空）＋`cast_schema_version`；`see/core/cast.py` `resolve_project_cast()`（只讀 pinned revision；缺失／hash 不符 integrity=error；reference 遺失 generation_ready=False；archived 歷史 revision 可解析）；doctor `workspace.project_cast`、env-export、唯讀 `cast show`／`GET /api/projects/{pid}/cast`。**Project.cast exists but is not yet production source of truth.**（production 角色來源仍是 `Project.characters`；尚未遷移任何專案）
- **D-067 客戶裁示**：DG-29 選 A（全域穩定 Library ID，系統產生；舊專案逐專案人工觸發遷移、可 rollback）；核可方案 D（Project 綁 character_id＋character_revision，預設鎖定，不自動更新，跟隨最新只能顯式 opt-in，缺失／hash 不符 fail closed）。

