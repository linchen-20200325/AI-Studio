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
| anime（P1）＋`girl_city_night`＋native 768×512（診斷） | diffusers-sd15 | （客戶未回報） | 否／否（technical_valid＝true） | （未回報） | 女孩、城市、夜晚都有，但臉部／五官／人體／背景細節嚴重失真；客戶：「這是畢卡索嗎？」→ **technical PASS／scene PASS／style FAIL**；正式產品品質不可接受（D-036） |
| realistic（P1） | ⏳ | | | | |
| cinematic（P1） | ⏳ | | | | |
| 3d（P2，次要） | ⏳ | | | | |
| picture_book（P3）＋native 768×512（診斷 A/B，D-035） | diffusers-sd15 | （客戶未回報） | 否／否（technical_valid＝true） | （未回報） | 場景明顯恢復 → **technical PASS／scene PASS／style PASS**（D-036）；證實 512×288 生成解析度是重要根因（H1） |
| picture_book（P3） | diffusers-sd15 | float32（fp16 numeric failure → 升級；無 OOM、無 fallback） | 否／否（technical_valid＝true） | ≈234.5 s | 「比較像藝術品。」→ **technical PASS／scene FAIL／style FAIL**：幾乎看不到貓、無追蝴蝶、無庭院構圖，高飽和粗黑線＋抽象／水果／幾何圖形（D-034、D-035）。**保留為 regression／failure evidence** |

- 無效嘗試（不計入）：picture_book 第一次 `generated_by=placeholder-image`、`valid_for_style_test=false`（新 cmd 視窗未設 `SEE_MODELS_DIR`）；工具 exit 3 fail-closed，行為正確。
- 人眼判斷皆為單一使用者主觀感受，非客觀品質結論。
- **分層（D-035）**：technical_valid（自動）≠ scene_validated ≠ style_validated（人工）。上表「技術 PASS」不代表場景或風格通過。
- 實際生成解析度 512×288（fit）→ 放大到 1920×1080；根因分析見 `AI_IMAGE_QUALITY_RCA.md`。native A/B 已完成（D-036）：H1 證實。
- **客戶裁示（D-036）：停止用 Base SD1.5 調整 Anime Style Profile**；realistic／cinematic／3d 的 base SD1.5 style-test 不再進行；改走 DG-20 現成專用模型研究。
- 上述 native 兩列只有客戶口頭摘要；dtype、耗時、sha256 等存在本機 `workspace\style_tests\*_native.json`，未入 repo。

## 狀態
E2-1 ✅　E2-2 ✅　→ DG-13 裁示 A：Kokoro 正式採用為目前 Phase 2 LOCAL_FREE 中文 TTS provider（D-029）。E2-3（Audio Layer）自動測試 ✅、真機 BGM／ducking ✅（客戶「OK」）、SFX 真機 ⏳；BGM 預設維持 null（D-032）。

## E2-5 專用 checkpoint 真機驗證（D-039；內部品質驗證，commercial_cleared=false）
共同條件：`--case girl_city_night --gen-policy native`、seed 1234、1920×1080 請求（768×512 生成→裁 16:9）、steps 25、CFG 7、scheduler DPM++ 2M Karras（base 對照組同 scheduler）。人眼判斷皆為**單一使用者主觀驗收**。

| 組別 | checkpoint | 下載核對 | dtype／OOM／fallback | VRAM peak | 耗時 | scene | style（主觀） |
|---|---|---|---|---|---|---|---|
| anime × base SD1.5（對照） | — | — | ⏳ | | | | |
| anime × MeinaMix V12（第 1 次） | meinamix_v12 | ✅ sha256 `a5e5a941…` verified | 載入 OK；推理 **FAIL**：`'CLIPTextModel' object has no attribute 'text_model'`（diffusers 0.41 clip_skip × transformers 5.x，D-040） | — | — | — | — |
| anime × MeinaMix V12（修復後，girl_city_night） | meinamix_v12 | ✅ | fp16 NaN → float32 ✅；無 OOM；無 fallback；technical_valid=true（D-040 修復驗證） | （未回報） | （未回報） | 城市夜景／人物存在 PASS（主觀） | 日系動畫感 PASS；臉部**無法判定**（背面遠景）；黑色比例偏重＝觀察項（single-user subjective） |
| anime × MeinaMix V12（girl_portrait_closeup，D-041；**fit 512×288**，D-044 實機 JSON 確認） | meinamix_v12 | ✅ | （客戶未回報 JSON） | （未回報） | （未回報） | 正面近景 PASS（主觀） | 「這樣算 OK」：臉部／眼睛／五官／頭髮／日系動畫呈現＝目前可接受（single-user subjective；不鎖模型／畫風、非商用許可，D-042） |
| anime × base SD1.5（girl_portrait_closeup，同 scheduler 對照，D-043） | —（sd15-base） | — | fp16 NaN/black → float32 ✅；oom_downgrade=false；fallback=null；technical_valid=true；768×512→裁切→1920×1080 | （未回報） | ≈646.6 s；NT$0 | 正面近景（主觀，未逐項審） | 「第一張眼睛很怪異」：眼睛／五官品質較差（single-user subjective） |
| anime × MeinaMix V12（girl_portrait_closeup，**native 重跑**，D-045） | meinamix_v12 | ✅ | fp16→float32；無 OOM；無 fallback；technical_valid=true；768×512 crop [0,40,768,472]；clip skip 2；NT$0 | （未回報） | （未回報） | PASS（single-user subjective） | PASS：「這樣 OK」（single-user subjective） |
| realistic × base SD1.5（對照） | — | — | ⏳ | | | | |
| realistic × CyberRealistic（girl_portrait_closeup） | cyberrealistic_final | （客戶未回報 JSON） | technical PASS | | | — | 真人感良好、但人物偏西方臉孔 → 人物控制未判定（single-user subjective observation，D-046） |
| realistic × CyberRealistic（east_asian_female_portrait，D-046／D-047） | cyberrealistic_final | ✅ | technical PASS（其餘數值客戶未回報） | | | — | 「是東方女性沒錯」（single-user subjective） |
| realistic × CyberRealistic（two_characters_ab **v1**・`historical_reversed_character_mapping=true`，D-049／D-050） | cyberrealistic_final | ✅（既有 provenance） | fp16 NaN/black → float32 ✅；OOM=false；fallback=null；technical_valid=true；native；dpmpp_2m_karras；GTX 1650；**prompt_tokens=80＞77 → prompt_truncated=true** | （未回報） | ≈638 s；NT$0 | **FAIL**（style-review scene_validated=false，reviewer=customer） | PASS（style_validated=true；寫實品質可接受）。客戶主觀：A／B 辨識失敗、兩人臉部過度相似、East Asian 外觀模板化；A 紅大衣遺失且錯戴眼鏡、B 灰短髮未遵守、眼鏡污染 A（single-user subjective；非模型排名） |
| realistic × CyberRealistic（two_characters_ab **v1**・`historical_reversed_character_mapping=true`，**S1 --long-prompt**，D-051／D-052） | cyberrealistic_final | ✅ | 生成完成（technical 數值客戶未回報，不補造）；style-compare vs D-049 基準：唯一差異 prompt_mode standard→long_prompt，其餘受控條件全同（D-052 修正後＝single_variable） | | | **FAIL**（scene_validated=false） | style_validated：未經 style-review 正式填寫（不得由 scene FAIL 推論）。客戶觀察（single-user subjective）：寫實攝影質感尚可；女角眼鏡／鼻眼交界局部五官幾何異常；人物外觀仍過度模板化、缺乏自然多樣的現代東亞人物特徵；A 紅大衣遺失；A 錯戴眼鏡；B 灰短髮未遵守；B 灰西裝未遵守 → **S1 解決 prompt truncation，但未解決 multi-character attribute binding，也未解決臉部多樣性／局部品質** |
| realistic × CyberRealistic（two_characters_ab **v1**・`historical_reversed_character_mapping=true`，**S2 --regional**，D-051／D-053） | cyberrealistic_final | ✅ | seed 1234、native、dpmpp_2m_karras、prompt_mode=regional；**technical 數值客戶未回報 stdout／JSON，不補造** | | | **FAIL**（scene_validated=false） | style_validated：未正式填寫（不由 scene FAIL 推論）。客戶觀察（single-user subjective）：應有 2 人卻只剩 1 人；A／B 身份嚴重 collapse／fusion；長髮、眼鏡、灰西裝、紅色衣物等分屬不同角色的特徵混在同一人；性別表徵與屬性交叉污染 → **S2 未改善 attribute binding，反而造成更嚴重的 identity collapse／attribute fusion** |
| realistic × CyberRealistic（two_characters_ab **v1**・`historical_reversed_character_mapping=true`，**S4 --identity ip_adapter_plus_face_sd15**，D-054／D-056） | cyberrealistic_final | adapter：客戶 Windows 完成下載並生成（`--yes` 的逐檔 sha256 stdout 未回報入庫） | seed 1234、native、dpmpp_2m_karras、identity＝ip_adapter_plus_face_sd15；A／B＝**客戶自備本機 reference image**（私人素材，未入 Git）；**technical_valid／VRAM peak／elapsed／OOM／reference sha256 對照：客戶未回報 stdout／JSON，不補造** | | | **FAIL**（scene_validated=false） | style_validated：未正式填寫（**不由 scene FAIL 推論 style FAIL**）。客戶觀察（single-user subjective）：相較 S2 **恢復為 2 個獨立人物、未再融合**；identity reference 對兩張臉都有影響；但 **A／B 身分位置疑似顛倒**——右側橘色衣物人物明顯吸收較多女角 reference 特徵（案例 A 女角應在左）；男角 reference 影響較弱；臉部 fidelity「有部分相似，但未達高 fidelity」。不重抽 seed。程式 mapping 追溯結果見 D-056（mapping verified；真機那次的 `--ref` 指派因無 JSON 無法核對） |
| realistic × CyberRealistic（two_characters_ab **v1**・`historical_reversed_character_mapping=true`，**S4 同 seed 重跑**，D-056／D-057） | cyberrealistic_final | ✅（已下載使用） | seed 1234、native、dpmpp_2m_karras、identity＝ip_adapter_plus_face_sd15、A／B＝客戶本機人物 reference（私人素材，未入 Git）；客戶確認 `identity_region_map`＋`_identity_regions.png` 疊圖顯示 **char_a→left、char_b→right（mapping PASS）**；technical_valid／VRAM／elapsed／reference sha256 數值：客戶未回報 stdout／JSON，不補造 | | | **FAIL**（scene_validated=false） | style_validated：未填（不由 scene FAIL 推論）。客戶觀察（single-user subjective）：兩角色成功分離（無 S2 單人融合）；**identity fidelity FAIL**——女角只保留部分臉型／髮型／氣質，明顯變成另一個人；男角 identity 更弱，臉型、五官、性別呈現皆無法可靠維持；客戶評語「完全不像」，右側角色有明顯陌生卡通／模板感。結論：mapping PASS、separation 改善、identity fidelity FAIL；不 reroll、不再以調 IP-Adapter scale 為主解法；S4 保留為研究證據、不升格 production route |
| realistic × CyberRealistic（**ab_char_a_isolated v2**，A＝男主角，DG-26 Route A 角色層，D-057／D-059） | cyberrealistic_final | ✅ | seed 1234、native、dpmpp_2m_karras、identity＝ip_adapter_plus_face_sd15、單一 reference＝**客戶舊本機男性照片**（私人素材，未入 Git；非正面證件照、背景有人、光線一般、臉部佔比有限）、plain light grey background；**technical_valid／VRAM／elapsed／reference sha256：客戶未回報，不補造** | | | identity_validated=**false** | 客戶觀察（single-user subjective）：單角色成功生成；男性呈現成立；灰西裝、圓眼鏡等文字屬性被採用；但 **reference identity fidelity 明顯 FAIL**——臉型、眼型、鼻型、嘴型、年齡感與 reference 明顯不同，整體是「另一個人」。不由 technical_valid 或畫面好看推論 identity pass。結論：即使拆成單人，`IP-Adapter plus-face＋SD1.5＋CyberRealistic` 仍不足以達到真人角色一致性 → DG-26 暫停、啟動 DG-28 |

> **D-058 歷史標記（`historical_reversed_character_mapping=true`）**：上列 two_characters_ab v1（D-049～D-057）期間，案例把 char_a 定義為女性（左）、char_b 為男性（右），**與客戶實際裁示 A＝男、B＝女及其 reference 指派相反**。這些圖片與 JSON 不刪、不覆寫、不改名；觀察文字維持當時原樣（文中「A 女角／B 男角」是 v1 定義）。用途：仍可作**模型能力證據**（attribute binding 失敗、S2 融合、S4 identity fidelity 不足、mapping 機制正確）；**不可**用來判定 A／B 性別 assignment 是否正確。v2 起案例改為 A＝男（左）、B＝女（右），檔名加 `-v2`，新 JSON 記 `case_definition_version=2`、`historical_reversed_character_mapping=false`；程式（`historical_reversed_character_mapping()`）會辨識無版本欄位的舊 JSON，`style-compare` 會標示、`compose-scene` 拒收為角色層。
| realistic × CyberRealistic（east_asian_male_portrait，D-046／D-047） | cyberrealistic_final | ✅ | **technical JSON 未入庫（不補造）** | | | — | 外觀確為東亞成年男性（single-user subjective，客戶提供圖） |

**E2-5 人物近景觀察（D-043；single-user subjective；D-044：非受控比較）**：原以為同 case／seed 1234／native 768×512／steps 25／CFG 7／DPM++ 2M Karras／同 prompt 與 negative（同 style、同 base_prompt_en）／fp16→float32 同路徑。客戶判斷：Base SD1.5「眼睛很怪異」；MeinaMix「比較像日本漫畫的角色」（先前已判「這樣算 OK」）→ 對 P1 日系動畫人物呈現有**明顯主觀改善**。
- **D-044 更正：實機 `style-compare`＝not_comparable**——舊 MeinaMix 近景為 fit 512×288（無 crop），Base 為 native 768×512；上方客戶評語僅為 single-user subjective observation，**不是受控比較結論**。待重跑：`style-test --style anime --case girl_portrait_closeup --gen-policy native --checkpoint meinamix_v12 --scheduler dpmpp_2m_karras` 後再 style-compare。
- （D-043 原推論，已被 D-044 推翻其完整性）比較層級＝model_preset_level：除權重（含 checkpoint 內嵌 VAE）外，clip skip 也不同——MeinaMix 依作者建議 A1111 clip skip 2（型錄 preset，D-039／D-040），base 為 1（不跳層）。程式路徑確定（`DiffusersImageProvider._run_pipe`），非推測。
- 證據 `fair_comparison=false` 的原因：舊旗標只表示「fit 基準條件、無診斷覆寫」，native 一律 false（MeinaMix 那張同樣是 false），**不是**跨次比較的判定 → 已更名 `baseline_condition`，跨次比較改用 `style-compare`（D-043）。
- 實機 JSON 已逐欄比對（D-044）：not_comparable，見上。
- **D-045 受控比較**：`style-compare anime_seed1234_girl_portrait_closeup_native_sched-dpmpp_2m_karras anime_seed1234_girl_portrait_closeup_native_ckpt-meinamix_v12_sched-dpmpp_2m_karras` → **model_preset_level**、unexpected_differences=[]；唯一差異 model（sd15-base vs meinamix_v12）＋clip_skip_a1111（1 vs 2）；其餘 14 項一致；兩張 technical_valid=true。客戶看 MeinaMix native：「這樣 OK」scene PASS／style PASS（single-user subjective）。DG-23 客戶裁示接受此比較層級。
- 限定：不鎖定 MeinaMix、不鎖定人物畫風、`commercial_cleared=false`、僅內部品質驗證。
