# CHARACTER_LIBRARY_PROJECT_BINDING.md — 角色資料唯一架構與 Library ↔ Project 綁定設計（D-066；只設計，未實作）

> 範圍：盤點現有角色資料，界定資料責任，比較綁定方案，定義 revision pinning、可重現性、舊 `Project.characters` 遷移規格與 UX。
> **本輪不搬資料、不改 schema、不寫 migration、不改 production 行為。**盤點依實際 code path、序列化與 tests（不是只看文件）。
> **D-067 客戶裁示**：DG-29 選 A（全域穩定 Library ID；舊專案逐專案人工觸發遷移、可 rollback）；核可方案 D（revision pinning）。Batch 2（不可變 revision history）已實作，見 §5 與 DECISIONS D-067。

## 1. 現況盤點（Current state）

### 1.1 角色相關資料來源（6 處）
| # | 位置（程式） | 序列化位置 | 實際用途（code path） |
|---|---|---|---|
| ① | `Project.characters: dict[str, CharacterVoice]`（`see/models/project.py`；別名 `CharacterProfile`） | `workspace/projects/<pid>/project.json` | **production 唯一在用的角色資料**。`Orchestrator.resolve_voice`（scene.narrator_id → voice_id／speed）、`set_character`／`confirm_character`／`unconfirmed_characters`（Final 前 voice 確認閘門，D-030）、`set_character_appearance`＋`image_request`（`appearance.anchor_text` 進 image prompt、`params["characters"]` 進 image fingerprint）、Web API `/api/projects/{pid}/characters/{cid}`、`…/appearance`、`…/confirm`、CLI `character`／`appearance`、Scene 卡角色名稱（`_char_label`） |
| ② | `Project.script.characters: list[Character]`（`see/models/script.py`：character_id、name、description、visual_prompt） | project.json | LLM（目前 Mock）劇本抽出的人物；Mock 以「出現順序」產生 `char_01`、`char_02`…；`Beat.character_ids` → `Scene.character_ids`；UI 角色名稱 fallback |
| ③ | `CharacterDefinition`（`see/models/character_definition.py`） | Character Store `workspace/character_library/<id>.json`（`CharacterRecord`：schema_version、definition、archived、revision、created_at、updated_at） | **尚未接 production pipeline**。用於 style-test 案例（`style_tests.py` A／B v2）、`validate_characters` Gate、`confirmation_payload`、CharacterStore CRUD（D-062） |
| ④ | `ReferenceAsset` sidecar（`<圖>.ref.json`，`workspace/reference_library/<category>/`） | 圖片旁 | Reference Library service（register／bind／primary）、style-test `--identity` 解析 |
| ⑤ | `Scene.character_ids`、`Scene.narrator_id`、`Scene.voice`／`speech_speed`、`Dialogue.character_id` | project.json | 本景登場角色（anchor 進 prompt）、旁白角色（voice 解析）、本景 voice override |
| ⑥ | `Scene.characters: list[SceneCharacter]`（D-063） | project.json | 本景演出覆寫（表情／情緒／動作／視線／姿勢／本幕服裝／位置／景深／中文原話）；必須 ⊆ `Scene.character_ids` |

另有 `ScenePlacement`（character_definition.py；左中右／景深／shot_size／action／pose）只用在 style-test／compose 測試路徑與 Gate。

### 1.2 各欄位現在放哪裡
| 項目 | 現在的位置 |
|---|---|
| voice 綁定 | ① `CharacterVoice.voice_id／speed／provider／confirmed／confirmed_at`；③ `CharacterDefinition.voice_profile`（VoiceAssignment：voice_id、speed、emotion，未接 pipeline）；⑤ `Scene.voice`／`speech_speed`（scene override） |
| reference 綁定 | ① `CharacterAppearance.reference_images`（本機路徑字串，**目前 provider 不使用**，但會進 image fingerprint）；③ `CharacterDefinition.reference_asset_ids`；④ `ReferenceAsset.character_id`＋`is_primary`（Library service 的實際工作索引） |
| style／mood default | ③ `CharacterDefinition.default_style_profile`／`default_mood_profile`（**未參與解析**，D-062 規格缺口）；Project `style_id`＋`preferences`；Scene `preferences`、`settings`（D-065） |
| 外觀 | ① `CharacterAppearance`（description_en、outfit_en、features_en、seed、adapter、`traits: CharacterTraits` 英文自由文字）；③ CharacterDefinition 結構化欄位（經 `to_appearance()` 轉成 ①的格式）；② `Character.visual_prompt`（中文） |
| 名稱 | ① `CharacterVoice.display_name`；② `Character.name`；③ `CharacterDefinition.display_name`；⑥ `SceneCharacter.display_name`（只顯示） |
| 確認狀態 | ① `confirmed`／`confirmed_at`（Project 層人工確認，D-030） |

### 1.3 ID 現況
| 來源 | 格式 | 穩定性 |
|---|---|---|
| ① Project.characters key | `^[A-Za-z0-9_-]+$`（可大寫、連字號；測試用 `hero`、`narrator`） | 專案內穩定（存檔後不改）；**跨專案不唯一**（每個專案都可能有 `char_01`、`hero`） |
| ② Script | 任意非空；Mock 依出現順序產生 `char_01`… | 專案內穩定；跨專案不唯一；重跑劇本可能重新編號 |
| ③ CharacterDefinition | `^[a-z][a-z0-9_]{1,63}$`（建議 `char_001`） | 由建立者指定；CharacterStore 禁止改 ID（rename 只改 display_name） |
| ⑥ SceneCharacter | `^[A-Za-z0-9_-]{1,64}$` | 跟隨 ① |

## 2. 重複／衝突欄位
| 衝突 | 說明 | 處理 |
|---|---|---|
| 名稱三處（①display_name、②name、③display_name） | 可能不一致；①可空 | 遷移需人工確認 |
| voice（①voice_id／speed vs ③voice_profile） | ①有 `provider`、`confirmed`；③有 `emotion` | voice_id／speed 可對應；confirmed 是 **Project 層人工確認**，不屬於 Library |
| reference（①reference_images 路徑 vs ③reference_asset_ids vs ④ReferenceAsset.character_id） | **三個來源**；路徑非可攜（含本機絕對路徑）且進 fingerprint | 設計：Library revision 內的 `reference_bindings`（asset_id＋sha256＋role＋primary）為唯一權威；④ sidecar 為工作索引，不一致 → fail closed |
| expression（③CharacterDefinition.expression vs ⑥SceneCharacter.expression） | ③是「預設表情」且被寫進外觀錨點 features；⑥是本幕覆寫 | 語意不同：建議 ③改名 `default_expression`（未來 schema 版本），本幕 ⑥ 優先 |
| 擺位（ScenePlacement vs ⑥placement／depth／action／pose） | 同概念兩個 model | 產品 SSOT＝⑥；ScenePlacement 只作 Gate 的衍生輸入 |
| 外觀（①CharacterAppearance／CharacterTraits 英文自由文字 vs ③結構化欄位） | ①`traits.gender_presentation` 是自由文字（例 "woman"），③是 enum；①有 `description_en`、`body_type`、`age`（int）③沒有對應；③有 `face_shape`、`character_type` ①沒有 | **不可一對一**（見 §8.3） |
| model-specific（①`seed`、`adapter`） | 屬模型層（PROJECT_RULES §15），不屬角色永久資料 | 不搬入 Library；保留在 Project legacy 區或丟棄需人工確認 |
| narrator（①可有 `narrator` 這類只有 voice、沒有外觀的條目） | 不是故事人物 | 不應自動建立成 person 角色（見 §8.3） |

## 3. 資料責任邊界（Data ownership；提案）
| 層 | 擁有（唯一來源） | 不得保存 |
|---|---|---|
| **Character Library**（CharacterDefinition＋CharacterRecord＋revision history） | character_id、display_name、character_type、gender_presentation、外觀（臉型／五官／髮型／髮色／固定特徵）、default outfit、default voice profile、default style／mood、default expression、reference bindings、archived、revision | Project／Scene 專屬狀態、模型參數（seed／adapter）、本機絕對路徑 |
| **Project**（新：`cast`） | 用了哪些 character_id、**pinned revision**、project 專屬 role label（男主角／店長／路人）、alias（若需要）、voice 人工確認（綁定 revision）、跟隨模式（pinned／follow_latest） | 角色永久資料的複本（不複製外觀、voice、reference） |
| **Scene** | 登場 character_ids、narrator_id、SceneCharacter 演出覆寫（表情／情緒／動作／視線／姿勢／本幕服裝／位置／景深）、scene voice／style override | 永久 identity |

Voice／Style 解析鏈（設計）：`Character default（pinned revision）→ Project override（目前無規格，不實作）→ Scene override`。Project override 只在客戶裁示後才加。

## 4. 綁定方案比較（3+）
| | A. Live reference（只存 character_id） | B. character_id＋immutable snapshot（Project 內嵌完整快照） | C. Project-local clone（複製成專案專用角色） | **D. character_id＋revision pinning（Library 保存不可變 revision history）** |
|---|---|---|---|---|
| Project 存什麼 | `character_id` | `character_id`＋整份 definition 快照 | 完整角色（新 ID） | `character_id`＋`revision`（＋可選 snapshot hash） |
| 主資料源 | Library（單一） | **雙主資料源**（Library＋各 Project 快照） | 每個 Project 各一份（無共用） | Library（單一；歷史 revision 也在 Library） |
| 可重現性 | ❌ Library 一改，舊 Project 悄悄變樣（anchor 進 fingerprint → 重開就重生） | ✅ | ✅ | ✅（revision 不可變） |
| Library 共用 | ✅ | 🟡（快照與 Library 會分歧） | ❌ | ✅ |
| 更新流程 | 自動跟著變（不可控） | 何時刷新快照需另訂規則；快照可能被手改 | 需手動同步、易分岔 | 顯式「更新到 revision Y」 |
| 搬機風險 | 低 | 中（project.json 變大、含 reference 資訊易帶路徑） | 中（每個 Project 自帶 reference 綁定） | 低（只需搬 Library＋history） |
| archive 處理 | 舊 Project 讀到 archived 最新版 | 不受影響 | 不受影響 | 舊 Project 讀 pinned revision 照常；新綁定被擋（§10） |
| 主要缺點 | 違反可重現性 | 雙主資料源、SSOT 違規 | 失去 Library 價值 | 需要新增 **revision history 儲存**（CharacterStore 目前覆寫檔案、只有 revision 計數） |

**Top 1：D（revision pinning）**，並保留 C 的「fork／detach」作為使用者顯式選項（複製成新 Library 角色，新 character_id，不是 Project 內嵌）。
理由：唯一同時滿足 SSOT（Library 單一來源）、可重現（舊 Project 不悄悄變）、可共用、可搬機的方案；B 的快照好處由「不可變 revision」取得而不產生第二份主資料。

## 5. Revision strategy（revision pinning）
- **（D-067 已實作）儲存**：CharacterStore append-only history：`workspace/character_library/history/<character_id>/r000001.json`（每次 create／update／archive／restore 寫入，永不覆寫、永不刪除）；`<character_id>.json` 仍是 head（相容現有讀取）。
  - 現況限制：目前 store 只保留最新內容，**過去 revision 已不存在**；導入時以當時 head 作為第一份 history（不補造舊 revision）。
- **revision 內容**：definition 全文＋`reference_bindings: [{asset_id, role, sha256, is_primary}]`（凍結當時的 reference hash）＋`content_sha256`（整份正規化 JSON 的 hash，供完整性檢查）。
- **Project 綁定**：`cast: {character_id: {revision, role_label, alias, follow: "pinned"|"latest", voice_confirmed_revision, voice_confirmed_at}}`。
- **讀取規則**：
  1. 指定 revision 存在且 content_sha256 一致 → 使用該 revision。
  2. revision 不存在／hash 不符 → **fail closed**（不生成；顯示「角色版本遺失或被修改」＋遷移／修復指引）；**不得偷偷改用最新版**。
  3. `follow: "latest"` 只能由使用者顯式設定（預設 pinned）；每次採用新版都記入 Project 事件與 evidence。
- **evidence**：image／narration manifest meta 記 `character_id@revision`＋content_sha256；fingerprint 只受 anchor 等實際生成輸入影響（與現行一致）。

## 6. 可重現性（Reproducibility）
| Library 之後的變更 | Live（A） | Pinned（D，推薦） |
|---|---|---|
| 換髮型（外觀） | anchor 改 → fingerprint 改 → 舊 Project 重開重生、畫面變樣 | 舊 Project 仍用 revision X，畫面不變；UI 提示有新版 |
| 換 voice | 旁白重新合成、聲音變 | 不變；若更新到新版，voice 確認重置（需重新試聽確認，沿用 D-030） |
| reference 更新（換圖） | 綁定的 sha 變 | revision X 凍結舊 sha；舊圖若已不在本機 → fail closed（§7） |
| archive | 讀到 archived | 不影響舊 Project |
| 被 fork | — | 新角色、新 ID；原 Project 不變 |

**角色更新 UX（規格；DG-19 前不做最終視覺）**：角色卡顯示「目前使用 Library 版本 X」；Library 有 Y＞X 時顯示「有新版本」，提供三個顯式選項：
1. **保持目前版本**（預設，不做任何事）
2. **更新到最新版**（顯示差異：外觀／服裝／voice／reference；確認後 pin 到 Y、受影響景回 DRAFT、voice 確認重置）
3. **複製成 Project 專用角色**（fork：在 Library 建新 character_id，記 `forked_from: id@X`；本 Project 改綁新 ID）
**永不自動更新。**

## 7. Reference 綁定與 missing 行為
- Project 不複製 reference 圖、也不存路徑；reference 由「pinned revision 的 `reference_bindings`」解析到 Reference Library（`<category>/<file>`＋sha256，D-064 可攜）。
- 解析失敗（圖不在、sha 不符、metadata 不一致）→ **fail closed**：Gate 回報 `reference_missing`／`reference_hash_mismatch`，UI 顯示 missing asset，**不自動改用其他 reference、不降級成無 reference 生成**（若使用者要無 reference 生成，必須顯式移除綁定 → 產生新 revision）。
- 私人 reference 圖不進 Git（PROJECT_RULES §16）；搬機靠使用者備份 workspace（MIGRATION_REINSTALL）。

## 8. 舊 `Project.characters` 遷移設計（只設計；不執行）

### 8.1 機制
| 要求 | 設計 |
|---|---|
| migration version | `project.json` 新增 `character_binding_version`（無＝v0 legacy；遷移後 v1）；遷移器只處理 v0 → v1 |
| backup | 遷移前複製 `project.json` → `workspace/backups/projects/<pid>/project-<時間>.json`（＋寫入 checksum）；Character Library 新增前先 `CharacterStore.backup()` |
| dry-run（預設） | `character-migrate <pid> --dry-run`：只產生 mapping report＋conflict report，不寫任何檔 |
| mapping report | 每個舊條目：來源欄位 → 目標欄位、分類（auto／manual／not_migratable）、理由 |
| conflict report | 名稱不一致、ID 格式不合、跨專案同名、voice 不明、reference 無法確認、narrator 類條目 |
| apply | 只在 `--apply` 且 conflict report 中所有 manual 項目已有使用者決定（決定檔 `decisions.json`）時執行 |
| rollback | 以 backup 還原 project.json；Library 只新增不改寫既有角色 → rollback 時把本次新增的角色 **archive**（不 hard delete），history 保留；rollback 本身也寫 log |
| idempotent | 以 `character_binding_version`＋migration log（`workspace/migrations/<pid>/<run_id>.json`）判斷；重跑 v1 專案＝no-op |
| old data preservation | 舊 `characters` 原樣保留在 project.json 的 `legacy_characters`（唯讀、不再被 pipeline 使用）＋backup；不刪除任何舊欄位內容 |

### 8.2 欄位對應（mapping）
| 舊欄位（① CharacterVoice） | 目標 | 分類 |
|---|---|---|
| key（project-local ID，例 `char_01`、`hero`） | Library `character_id`（**依 DG-29 裁示**） | 需人工／依裁示 |
| display_name | CharacterDefinition.display_name | 自動（非空時）；空 → 用 ② Script.name，兩者不同 → 人工 |
| voice_id、speed | CharacterDefinition.voice_profile.voice_id／speed | 自動（voice_id≠default 時）；default → 不建立 voice_profile（不補值） |
| provider | revision 註記（資訊） | 自動（只記錄） |
| confirmed、confirmed_at | Project `cast.voice_confirmed_revision／at` | 自動（綁到遷移後的 revision） |
| appearance.outfit_en | CharacterDefinition.outfit | 自動 |
| appearance.traits.hair_style／hair_color／facial_features／distinctive_marks | 同名欄位 | 自動 |
| appearance.traits.age_range | age_impression | 自動 |
| appearance.traits.age（int） | age_impression（字串化需確認措辭） | 人工 |
| appearance.traits.gender_presentation（自由文字） | GenderPresentation enum | **人工**（不得由文字推論；未確認＝unspecified） |
| appearance.traits.appearance_region | appearance_region | 自動（使用者原本就明確填寫） |
| appearance.traits.body_type | 無對應欄位 | 不可搬（保留在 legacy；需 schema 擴充裁示） |
| appearance.description_en、features_en | 無一對一欄位（自由文字錨點） | 人工（可放 notes 或拆入結構化欄位，由使用者決定） |
| appearance.reference_images（路徑） | Reference Library 登記＋reference_bindings | 人工（需登記、計算 sha、確認用途與 consent）；找不到檔 → 不可搬 |
| appearance.seed、adapter | 模型層，不進 Library | 不可搬（保留 legacy） |
| ② Script.Character.description／visual_prompt | notes（參考） | 人工 |

### 8.3 分類
- **可自動搬**：display_name（與 Script.name 一致或只有一方）、voice_id≠default／speed、outfit_en、hair／facial_features／distinctive_marks、age_range、appearance_region（使用者原填）、confirmed（轉成綁定 revision 的確認）。
- **需人工確認**：ID（DG-29）、名稱衝突、gender_presentation（自由文字 → enum）、age（int）、description_en／features_en、reference_images、跨專案同名角色（是否同一人）、voice 為 default 的條目是否需要 voice profile、narrator 類條目（建議成為 Project 的「旁白聲音」設定，不建 person 角色）。
- **不可搬**：seed、adapter（模型層）、body_type（schema 無欄位）、找不到檔案的 reference 路徑、空殼條目（只有 ID 沒有任何設定）。全部保留在 `legacy_characters`，**不補造**。

### 8.4 Dry-run 實作規則（D-069 Batch 4；**Batch 4 only analyzes. No project has been migrated.**）
分類（依序判斷）：
1. **EMPTY_UNUSED**：Project.characters 條目沒有有效資料（無名稱、voice=default、無 speed、無外觀）。被引用時仍需人工決定如何處理引用。
2. **NARRATOR_SETTING**：只被當作 `narrator_id`、沒有畫面引用、沒有外觀、沒有 blocking conflict → 建議成為 Project 旁白設定，不建立 CharacterDefinition。
3. **LEGACY_ONLY**：未被引用，且唯一的資料是 seed／adapter／body_type。
4. **HUMAN_REQUIRED**：任何 blocking conflict。
5. **AUTO_MAPPABLE**：其餘（所有資料語意明確）；proposed_character_id＝`pending_new_character_id`。

Conflict code（blocking）：ID_NAMESPACE_CONFLICT、NAME_CONFLICT、MISSING_DISPLAY_NAME、GENDER_MAPPING_AMBIGUOUS、AGE_MAPPING_AMBIGUOUS、FREE_TEXT_APPEARANCE、REFERENCE_MISSING、REFERENCE_UNREGISTERED、REFERENCE_HASH_CONFLICT、MULTIPLE_LIBRARY_MATCHES、LIBRARY_MATCH_CANDIDATE、VOICE_ROLE_AMBIGUOUS、UNUSED_CHARACTER、SCRIPT_ONLY_CHARACTER、UNKNOWN_FIELD、SCENE_REFERENCE_INCONSISTENT、PROJECT_ALREADY_HAS_CAST；（info）ID_FORMAT_LEGACY、LEGACY_ONLY_FIELDS、VOICE_DEFAULT_UNSPECIFIED、VOICE_CONFIRMATION_REBIND、NARRATOR_NOT_CHARACTER、EMPTY_CHARACTER。

Reference：legacy 路徑（相對路徑以 workspace 上層解析）存在 → 只讀計算 sha256；Library 唯一且未綁定、無 metadata 問題 → `mapped`（提出 binding，不寫）；唯一但已綁 Library 角色 → LIBRARY_MATCH_CANDIDATE；多筆／metadata 不一致 → REFERENCE_HASH_CONFLICT；不在 Library → REFERENCE_UNREGISTERED；不存在 → REFERENCE_MISSING（sha256=None）。
migration_ready＝沒有 blocking conflict、沒有 requires_human_decision、專案沒有 cast、且有可分析的角色。

### 8.5 人工決定檔（D-070 Batch 4.1；**Batch 4.1 remains analysis-only. No project has been migrated.**）
- 指令：`character-migrate <pid> --dry-run --decisions-template --out <workspace 外>` → 人工填 action → `character-migrate <pid> --dry-run --decisions <file> [--json]`。
- schema v1（`character_migration_decisions`）：project_id、source_report_input_hash、source_report_sha256、decisions[{legacy_id, action, note?, display_name?, library_character_id?, library_revision?}]；未知欄位拒絕。範例：`docs/examples/character_migration_decisions.example.json`。
- action 與適用條件：

| action | 適用 | 效果（只在報告中；不寫入） |
|---|---|---|
| create_new | 任何條目 | placeholder `pending_new_character_id`；缺名稱或名稱衝突時必須給 display_name；**不產生正式 ID** |
| bind_existing | 任何條目 | pinned `character_id@revision`；角色須存在、未封存、revision 存在且 hash 通過；legacy 資料不合併 |
| keep_legacy | 來源為 Project.characters 且無任何引用 | 留在 legacy_characters，不建 Library 角色 |
| narrator_setting | 有旁白引用、無畫面引用 | `pending_project_narrator_setting`，不建 CharacterDefinition |
| ignore_unused | 無任何 Scene／對白／旁白／beat 引用 | 不建 Library 角色；legacy 資料（若有）原樣保留，不刪除 |

- Fail closed：stale（兩個 source hash 任一不符）或任何驗證錯誤 → 整份不採用、migration_ready=false（CLI exit 4）。
- 決定只解決處置類衝突；create_new 不解決欄位層級衝突（GENDER／AGE／FREE_TEXT_APPEARANCE／REFERENCE_*／UNKNOWN_FIELD）與 VOICE_ROLE_AMBIGUOUS → 需決定檔 v2（BACKLOG）。PROJECT_ALREADY_HAS_CAST 永不解決。
- migration_ready=true＝ready for reviewed migration planning only；不代表已遷移、不代表 Batch 5 已核准。
- 例：sd15test 的 char_01～char_04（SCRIPT_ONLY_CHARACTER）全選 create_new → migration_ready=true、4 個 placeholder、計畫改寫引用數＝基礎報告的 total_rewrite_references。

### 8.6 Apply／Rollback（D-071 Batch 5；首個真實遷移：sd15test，2026-10-25 committed，未 rollback；production 仍用 Project.characters）
- 指令：`character-migrate <pid> --dry-run --decisions <file>`（取得 `apply_confirmation_token`）→ `character-migrate <pid> --apply --decisions <file> --confirm <token>` → 需要時 `--rollback <migration_id>`；`--list-migrations` 查紀錄。
- 寫入位置（workspace 內、不進 Git）：backup `backups/character_migrations/<pid>/<migration_id>/`；record `migrations/<pid>/<migration_id>.json`；staging `migrations/<pid>/<migration_id>.staging/`（完成即移除）。
- 與 §8.1 原設計的差異（實作現況）：不新增 `character_binding_version`／`legacy_characters` 欄位；已遷移判定＝Project.cast 非空＋committed record；legacy→Library 對照、決定、hash、rewrite 數、backup ID 記在 record 與新角色 revision provenance。
- v1 只支援 create_new／bind_existing（script／scene-only 條目）；narrator_setting 與 Project.characters 條目 fail closed（需規格，BACKLOG）。
- 失敗／rollback：project.json 回到原始 bytes；本次新角色 archive（不 hard delete）；被其他專案 cast 使用者保持 active；rollback 前專案若已被修改 → 拒絕。
- Project.cast is not yet production source of truth（Batch 6 才切換）。

### 8.7 Production source 切換（D-073 Batch 6A）
| 條件 | production 角色來源 |
|---|---|
| 無 Project.cast、無 committed／committing migration record | legacy `Project.characters`（行為、fingerprint 不變） |
| Project.cast 非空＋剛好一筆 committed record，且 id／revision／content_sha256 一致 | pinned cast（`resolve_project_cast`；不 fallback latest、不讀 Project.characters） |
| 其他（cast 無 record、record committing／無法讀、cast 與 record 不一致、cast 空但有 committed record、revision 缺失／hash 不符、reference 遺失、Scene 引用不在 cast） | **fail closed**（CharacterSourceError），不 fallback |
- 切換的 production path：image anchor／params（fingerprint）、旁白 voice／speed（fingerprint）、Final 前 voice 確認、narrator_id 驗證。
- 未解：cast 角色 voice 確認 schema（目前一律未確認）、Project.characters 條目 migration、narrator_setting、Audio architecture（Batch 6B／D-072）。

## 9. ID 策略與 Decision Gate（DG-29：角色 ID 命名空間）
**發現（stop condition）**：舊 Project 的角色 ID 是「專案內」ID（Mock 依出現順序產生 `char_01`；手動設定可為 `hero`、`narrator`，可含大寫／連字號），**跨專案不唯一**，也不一定符合 CharacterDefinition 的 `^[a-z][a-z0-9_]{1,63}$`。客戶規則要求「Library／Project／Scene 使用同一穩定 ID」→ 舊專案綁到 Library 時，**專案內所有引用（Scene.character_ids、narrator_id、SceneCharacter、Dialogue、Beat、Script）都要改寫成 Library ID**；這是每個專案內的 ID 重寫（非全庫重編，但屬資料改寫）→ 需裁示。

| 選項 | 內容 | 優點 | 缺點 |
|---|---|---|---|
| **A（總管推薦）** | Library ID 由系統產生（`char_` ＋ 短隨機碼，不由名稱生成，rename 不變）；舊專案**按需、逐案、使用者觸發**遷移：dry-run → 使用者確認 → 備份 → 專案內引用一次改寫成 Library ID（mapping 記在 migration log，可 rollback）；未遷移的舊專案維持 legacy 模式可讀可用 | 符合「同一穩定 ID」；新舊並存期間無破壞；可回復 | 舊專案遷移要改寫 project.json 內引用（有 backup／rollback） |
| B | Project 保留專案內 cast ID，`cast` 對照 local ID → Library ID@revision；Scene 繼續用 local ID | 不改寫舊資料 | 兩套 ID 命名空間，違反客戶「同一 ID」規則；長期維護成本高 |
| C | 全部舊專案一次性批次遷移 | 一次到位 | 大規模資料改寫、風險集中；違反「不做大規模不可逆 migration」 |

新專案（客戶裁示後實作）：Script／Storyboard 產生角色時直接在 Library 建立（或挑選既有）角色並使用 Library ID；不再產生 `char_01` 類順序 ID。

### 9.1 可重現性 contract（D-067，測試 `tests/test_character_history.py` 證明）
Project 未來 pin `char_x@3`：即使 Library 已到 revision 7，重新開啟舊 Project 仍取得 revision 3；revision 3 不存在或 hash 不符 → fail closed，**不 fallback latest**；revision 3 凍結的 reference 遺失 → revision 仍可讀、generation_ready=false、列出 missing asset，不改綁其他圖。

## 10. Archive／Delete
- Library：archive 可（可 restore）；**hard delete 禁止**（需高風險 Gate 另裁；history 永不刪）。
- 已引用 archived 角色的舊 Project：照常讀取與重生（用 pinned revision）。
- 新 Project：**不可新增** archived 角色（UI 不列出；API 拒絕）；要用 → 先 restore（產生新 revision）。
- 更新到最新版時，若最新 revision 是 archived 狀態 → 不提供「更新到最新版」（只能保持或 fork）。

## 11. Portable／搬機
- Project 只存 `character_id`＋revision＋label，不存任何路徑；reference 經 Library 相對路徑＋sha256 解析（D-064）。
- Library＋history 都在 `workspace/character_library/`，隨 workspace 備份搬移；`env-export` 的 workspace inventory 未來需加入 history 清單（Batch 2）。
- GitHub Alone Recovery：本文件＋ARCHITECTURE §21＋DECISIONS D-066 即可重建設計脈絡。

## 12. 風險
| 風險 | 緩解 |
|---|---|
| CharacterStore 沒有歷史 revision，導入前的舊版本無法還原 | 只從導入時的 head 開始保存；文件明示不補造 |
| 遷移改寫專案內 ID 出錯 | dry-run＋mapping report＋backup＋rollback＋idempotent log；逐案、使用者觸發 |
| 舊專案 image fingerprint 因 anchor 文字細微改變而重生 | 遷移後 anchor 由 revision `to_appearance()` 產生，與舊 `CharacterAppearance.anchor_text` 可能不同 → dry-run 必須預報「哪些景會重生」，使用者確認 |
| reference_images 舊路徑含本機絕對路徑、且進 fingerprint | 遷移改為 reference_bindings（不含路徑）；預報受影響景 |
| 多角色預設 style／mood 衝突 | 維持 D-062 缺口，不自行決定 |
| narrator 被誤建成人物角色 | 分類為人工；建議成為 Project 旁白聲音設定 |

## 13. 未來實作批次（客戶裁示 DG-29 後才開始；每批可獨立回復）
| Batch | 內容 | 前提 |
|---|---|---|
| 1 | （本輪）設計文件 | — |
| 2 | CharacterStore append-only revision history＋content_sha256＋reference_bindings 凍結；read_revision()；CharacterBinding／resolve_binding 基礎；不影響 pipeline | **DONE（D-067）** |
| 3 | Project `cast` schema（cast_schema_version、pinned revision、role_label、alias、follow=pinned）＋`resolve_project_cast()`（revision 缺失 fail closed）；pipeline 仍只用 legacy `Project.characters` | **DONE（D-068）；not yet production source of truth** |
| 4 | `character-migrate --dry-run`（mapping／conflict report；不寫檔） | **DONE（D-069）；only analyzes, nothing migrated** |
| 4.1 | 人工決定檔（versioned）＋重算 migration_ready／rewrite plan（只讀；§8.5） | **DONE（D-070）；analysis-only, nothing migrated** |
| 5 | `--apply`／rollback（備份、ID 改寫、migration log；§8.6） | **ENGINE DONE（D-071）**；sd15test committed 2026-10-25 |
| 6 | pipeline 切換：voice／anchor／reference 由 pinned revision 解析；legacy 專案相容 | **6A DONE（D-073；§8.7）**；6B BACKLOG |
| 7 | 角色更新 UX（保持／更新／fork）、角色庫挑選 | DG-19 |
