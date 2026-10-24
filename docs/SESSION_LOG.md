# SESSION_LOG.md — 工作階段紀錄（append-only）

每個完整工作階段一筆，固定欄位：Date / Start SHA / End SHA / Batch / Result / Tests / Decision / Next。不記逐步過程。

---
- Date: 2026-10-22
- Start SHA: (empty repo)
- End SHA: 026206c
- Batch: Batch 1 — Phase 0 憲章、架構、pipeline、CLI、測試、證據
- Result: preview.mp4 成功（47 s，H.264/AAC）；成本 NT$0
- Tests: 38 passed
- Decision: D-001～D-008
- Next: DG-1～DG-4 待裁示

---
- Date: 2026-10-22
- Start SHA: 026206c
- End SHA: ff2b6f9
- Batch: Batch 2 — 裁示 DG-1～DG-4；建立 main；FastAPI 手機友善 Web UI
- Result: UI 貼故事 → Preview → 播放 → 單景修改 → 核准 → Final 跑通；main = 026206c
- Tests: 42 passed
- Decision: D-009、D-010
- Next: DG-5、是否併入 main；edge-tts 需連網驗證

---
- Date: 2026-10-22
- Start SHA: ff2b6f9
- End SHA: e38004d
- Batch: Batch 3 — Conversation Handoff & Crash Recovery 治理制度
- Result: PROJECT_RULES §11；STATE / HANDOFF_PROJECT_AI / HANDOFF_CHATGPT / SESSION_LOG 建立；HANDOFF.md 改為索引
- Tests: 42 passed（未動程式碼）
- Decision: 無新裁示
- Next: 等待下一個功能 Batch；待裁示：併入 main、DG-5、edge-tts 連網驗證

---
- Date: 2026-10-22
- Start SHA: 1e42a81
- End SHA: 24ecbc2
- Batch: Batch 4 — main fast-forward、DG-5（loopback 預設入口）、edge-tts 連網驗證嘗試、repo 實況盤點
- Result: main = 1e42a81 → 再 ff 至 24ecbc2；edge-tts 本容器無法連網（D-012）；repo public、預設分支非 main（D-013）
- Tests: 43 passed
- Decision: D-011、D-012、D-013
- Next: 等待 Web UI Batch 範圍；待裁示 DG-6、DG-7

---
- Date: 2026-10-22
- Start SHA: f39d72f
- End SHA: 5a3e05a
- Batch: Batch 5 — 最小 GitHub Actions CI；DG-6/DG-7 裁示入檔
- Result: ci.yml 兩次 run 皆 success（#1 7cad7f8、#2 5a3e05a）；無 secret、無外部 Provider
- Tests: 43 passed（本機 + CI）
- Decision: D-014、D-015、D-016
- Next: Web UI Batch；DG-7 待使用者手動改 GitHub 設定

---
- Date: 2026-10-22
- Start SHA: 16fd107
- End SHA: 088932a
- Batch: Batch 6 — AI Image Provider Phase 第一批：盤點、硬體偵測、diffusers 骨架、fallback、paid stub
- Result: 未下載模型；`hardware` 命令與 /api/hardware 可用；auto 模式缺權重自動退 placeholder
- Tests: 55 passed
- Decision: D-017；開 DG-8
- Next: 使用者貼回 hardware 輸出 → 選 A/B → 同意下載 → 真機驗證

---
- Date: 2026-10-22
- Start SHA: ec669e7
- End SHA: ca7d286
- Batch: Batch 7 — DG-8 方案 B：SD 1.5 低 VRAM runtime plan、image_prompt_en、模型下載器（需 --yes）、Windows 安裝文件
- Result: 程式端就緒；模型未下載（需使用者手動）；CI cancelled 根因＝apt 卡住→job timeout，已加固（ca7d286 success）
- Tests: 66 passed；CI success
- Decision: D-018、D-019
- Next: 使用者在 Windows 依 AI_IMAGE_SD15_WINDOWS.md §4 操作並貼回 hardware / run 輸出

---
- Date: 2026-10-23
- Start SHA: e220890
- End SHA: 3597e1e
- Batch: Batch 8 — Windows 真機第一次 SD 1.5 執行失敗之 root cause 修復
- Result: root cause = cp950 subprocess 解碼（非 warning）；修 UTF-8 subprocess、fp16 NaN 偵測與 fp32 升級、feature_extractor=None；模型未重下載
- Tests: 73 passed（+7 Windows 回歸）；CI 先因 Azure apt 鏡像慢紅、改 setup-ffmpeg 後因漏列 numpy 紅、補上後 success
- Decision: D-020、D-019 修正二
- Next: 使用者 git pull 重跑並貼回結果

---
- Date: 2026-10-23
- Start SHA: 02fac28
- End SHA: 02fac28（本輪無程式變更；僅 STATE/SESSION_LOG 追查筆記 commit 於其後）
- Batch: Batch 9 前置 — Verification Gate 通過；追查「黑 PNG 卻回報成功」路徑，列出 4 個假設與修法（見 STATE「Batch 9 交接筆記」）
- Result: 未修復；使用者要求換新對話，依 §11.4 收尾
- Tests: 73 passed；CI success @ 02fac28
- Decision: 無
- Next: 新對話依 STATE 筆記執行 Batch 9

---
- Date: 2026-10-23
- Start SHA: 1b0bce5
- End SHA: 63e7855
- Batch: Batch 9 — Windows 真機「純黑 PNG 卻回報成功」root cause 與修復
- Result: 主因＝黑圖被 manifest 當有效快取重用（version 未 bump、不驗內容）；修 image_qa 內容驗證（快取前／生成後／fallback／存檔後）、version 3、VAE dtype cast、evidence（manifest meta／CLI image_evidence／UI image_meta）
- Tests: 83 passed（+10 回歸）；CI 見 STATE
- Decision: D-021
- Next: 使用者 `git pull` 後重跑同一條 run 命令並貼回 `image_evidence`

---
- Date: 2026-10-23
- Start SHA: 8d6ad06
- End SHA: ab91f93
- Batch: Batch 10 — fp32 升級找不到權重（runtime 階梯 vs fp16-only 下載不一致）
- Result: 採方案 B：同一份 fp16 權重以 dtype=float32 載入 upcast（零下載）；pick_variant 依實際檔案決定；dtype= kwarg；VAE 單獨 fp32 載入；階梯跨景延續；evidence +weights_variant/fp32_source/plan_origin
- Tests: 86 passed（+3）；CI 見 STATE
- Decision: D-022
- Next: 使用者 `git pull` 後重跑同一條 run 命令並貼回 `image_evidence`

---
- Date: 2026-10-23
- Start SHA: 11d90c5
- End SHA: ada08f9
- Batch: Batch 11 — fallback 產物被當有效快取／regen 語意
- Result: root cause＝placeholder fallback 產物以首選 provider fingerprint 快取，首選修好後永不重試；修 degraded-cache 規則、Fallback info 穩定、regen 印 evidence；regen 本身語意正確
- Tests: 89 passed（+3）；CI 見 STATE
- Decision: D-023
- Next: 使用者 `git pull` 後重跑同一條 run 命令；scene_001 應自動重試並由 diffusers-sd15 生成

---
- Date: 2026-10-23
- Start SHA: ec8ff77
- End SHA: ec8ff77（本輪無程式變更；文件 checkpoint 另列）
- Batch: Batch 12 — Phase 1 真機收尾、PHASE1_EVIDENCE、BACKLOG 完整盤點、Phase 2 排序
- Result: Phase 1 COMPLETE（五景真 SD 1.5、fp32 upcast、降級快取自動重試、NT$0）；盤點 25 項能力 ✅13 🟡8 ⬜5 🔴1；Phase 2 第一目標建議＝自然中文 TTS
- Tests: 89 passed（未動程式）
- Decision: D-024
- Next: 使用者裁示 Phase 2 方向（停手條件）；可安全換新對話

---
- Date: 2026-10-23
- Start SHA: 1b944aa
- End SHA: 1b944aa（無程式變更；本輪為 governance/docs commit，SHA 見 GitHub main HEAD）
- Batch: Batch 13 — Knowledge Consolidation / Memory Migration / PROJECT_STATE 建立 / Handoff Closeout
- Result: CI 一次紅（setup-ffmpeg 外部 action readme 讀取失敗，非本次 diff）→ ci.yml 改 best-effort + apt fallback；PROJECT_RULES §10 補齊、§12–§14 新增；PROJECT_STATE 建立；STATE→指標；HANDOFF→導航頁；BACKLOG 加 DG-9～DG-12 與標示；DECISIONS 狀態索引＋D-025；README 產品願景；Dry-run 24 題可由 repo 回答
- Tests: 89 passed（未動程式）
- Decision: D-025
- Next: 使用者裁示 DG-9；可安全換新對話

---
- Date: 2026-10-23
- Start SHA: 6d17dbc
- End SHA: 6d17dbc（無程式變更；本輪 docs only）
- Batch: Batch 14 — 新對話接手驗證 + DG-9 TTS 候選研究（不下載）
- Result: main=HEAD=6d17dbc、CI success、無 PR；新增 `docs/TTS_PROVIDER_PLAN.md`；STATE／BACKLOG／DECISIONS（D-026）同步
- Tests: 88 passed、1 skipped（本容器，無 espeak）
- Decision: D-026（研究紀錄；DG-9 待裁示）
- Next: 客戶裁示 DG-9 → Batch 15 kokoro provider；可安全換新對話

---
- Date: 2026-10-23
- Start SHA: cd19ce5
- End SHA: （本 Batch 功能 commit，見 GitHub）
- Batch: Batch 15 — Kokoro TTS provider（D-027 候選）＋ CLI tts-setup/download/check ＋ TTS evidence/provenance ＋ Fallback info 穩定化
- Result: `kokoro` provider（fake backend 可測、fail-closed、voice 對應、CPU 預設）；auto 鏈 kokoro→espeak→silent；narration meta 進 manifest／CLI／UI；降級旁白自動重做；下載器寫 provenance.json；未下載任何權重
- Tests: 98 passed、1 skipped
- Decision: D-027（實作）；DG-13 待真機
- Next: Windows 真機一次一步（AI_TTS_KOKORO_WINDOWS.md §3）→ PHASE2_EVIDENCE → DG-13

---
- Date: 2026-10-23
- Start SHA: 59bbdd2
- End SHA: （本 Batch commit，見 GitHub）
- Batch: Batch 16 — Kokoro E2-1 真機證據入庫 ＋ Voice Selection 規格（VoiceInfo／list_voices／--voice／tts-voices）
- Result: PHASE2_EVIDENCE E2-1（revision 01e7505b、329.3 MB、sha256、四 voice 成功、使用者聽感）；D-028；BACKLOG Voice Selection 規格＋DG-14/15；`VoiceInfo` 介面、kokoro 型錄、`SEE_TTS_DEFAULT_VOICE`／`--voice`（未鎖死預設）；未下載新模型
- Tests: 100 passed、1 skipped
- Decision: D-028；DG-13 待 E2-2
- Next: Windows E2-2：`run examples\story_short.txt --project-id kokorotest --voice zm_010`

---
- Date: 2026-10-23
- Start SHA: 4bcae5c
- End SHA: 4bcae5c（無程式變更；docs only）
- Batch: Batch 17 — E2-2 真機證據入庫 ＋ DG-13 收斂
- Result: PHASE2_EVIDENCE E2-2（五景 kokoro-tts zm_010 CPU、SD 1.5 共存、RTF 0.30、NT$0）；STATE／BACKLOG／Windows guide 更新；停在 DG-13（A/B/C/D）
- Tests: 100 passed、1 skipped（未動程式）
- Decision: 無新裁示；等待 DG-13
- Next: 客戶裁示 DG-13 → D-029；可安全換新對話

---
- Date: 2026-10-23
- Start SHA: 80c9808
- End SHA: 80c9808（docs only）
- Batch: Batch 18 — DG-13 裁示 A 入庫（D-029）
- Result: DECISIONS D-029；STATE Phase 2 第一目標完成、TTS=Real（並修正 Batch 16/17 未更新的 TTS 列漂移）；BACKLOG TTS 項關閉、Narration ✅、新增 DG-16；DG-14／DG-15 維持獨立
- Tests: 100 passed、1 skipped（未動程式）
- Decision: D-029
- Next: Batch 19 Voice Selection 非 UI（可自主）；DG-16 待裁示；可安全換新對話

---
- Date: 2026-10-23
- Start SHA: c4df10c
- End SHA: （本 Batch commit，見 GitHub）
- Batch: Batch 19 — Voice Selection 非 UI（角色 voice／語速、試聽、確認閘門、CLI＋Web API）
- Result: D-030；舊專案 fingerprint 不變；espeak fallback 改用語言預設聲；HTML UI 未改（DG-15）、預設 voice 未鎖（DG-14）
- Tests: 106 passed、1 skipped
- Decision: D-030
- Next: 客戶裁示 DG-16；可安全換新對話

---
- Date: 2026-10-23
- Start SHA: f323765
- End SHA: （本 Batch commit，見 GitHub）
- Batch: Batch 20 — Audio Layer 第一版（BGM／SFX／ducking／limiter／evidence）
- Result: D-031；`see/audio/`（pcm、mixer、layer）、`procedural-audio` provider、CLI `--audio`／`--sfx`、`audio_evidence`；預設 null（舊行為、fingerprint 不變）；BACKLOG 能力表重算
- Tests: 119 passed、1 skipped
- Decision: D-031（DG-16=A）；DG-17 待真機
- Next: Windows E2-3：`run examples\story_short.txt --project-id audiotest --voice zm_010 --audio procedural`

---
- Date: 2026-10-23
- Start SHA: 9acce55
- End SHA: （本 Batch commit，見 GitHub）
- Batch: Batch 21 — E2-3 真機入庫 ＋ Style Profile／Character Consistency／Lip-sync foundation
- Result: PHASE2_EVIDENCE E2-3 真機（BGM／ducking OK、SFX 未驗證）；D-032（BGM 預設維持 null、產品流程、foundation）；StyleProfile＋6 內建、CharacterAppearance 錨點、LipSync 介面＋opt-in stage；CLI style／appearance／set-scene --characters/--lipsync；API styles／style／appearance；舊專案 fingerprint 不變
- Tests: 130 passed、1 skipped
- Decision: D-032；DG-18 待裁示
- Next: 客戶裁示 DG-18；可安全換新對話

---
- Date: 2026-10-23
- Start SHA: 6950a7f
- End SHA: （本 Batch commit，見 GitHub）
- Batch: Batch 22（進行中）— E2-4 Style 真機驗收；客戶確立產品視覺方向
- Result: picture_book 無效嘗試一次（placeholder，未設 SEE_MODELS_DIR，fail-closed 正確）；重跑 diffusers-sd15／fp32／234.5 s 技術 PASS、主觀「比較像藝術品」FAIL，不再處理。D-034：P1 anime＋realistic＋cinematic、P2 3d、P3 繪本；README 新增 canonical「產品視覺方向」；E2-4 順序改 anime → realistic → cinematic →（次要）3d；DG-20 預告
- Tests: 131 passed、1 skipped（僅文件變更）
- Decision: D-034
- Next: Windows `python -m see.app.cli style-test --style anime`

---
- Date: 2026-10-23
- Start SHA: a4f684f
- End SHA: （本 Batch commit，見 GitHub）
- Batch: Batch 23 — picture_book scene adherence 失敗 RCA＋分層驗收
- Result: D-035；追查 scene→prompt→negative→尺寸→scheduler→seed→dtype：實際生成 512×288 再 ×3.75 放大（主要嫌疑）；新增 `see/core/style_tests.py`（technical_valid／prompt_subject_check／人工 scene/style）、`style-review`、`--case/--gen-policy native/--base-prompt/--scene`、生成證據（gen 尺寸／scheduler／token）；`AI_IMAGE_QUALITY_RCA.md`（假說表＋候選模型初步表）；預設行為與 fingerprint 不變；未下載、NT$0
- Tests: 138 passed、1 skipped
- Decision: D-035；DG-21／DG-20 待真機 A/B
- Next: Windows `git pull` → `style-test --style picture_book --gen-policy native`

---
- Date: 2026-10-23
- Start SHA: b344f71
- End SHA: （本 Batch commit，見 GitHub）
- Batch: Batch 24（進行中）— native A/B 真機結果入庫；DG-20 研究啟動
- Result: D-036：picture_book native scene/style PASS（H1 證實）；anime＋girl_city_night native scene PASS／style FAIL（「這是畢卡索嗎？」）；客戶裁示停止以 Base SD1.5 調 Anime；DG-20 改為現成專用模型研究（不下載）
- Tests: 138 passed、1 skipped（僅文件）
- Decision: D-036
- Next: DG-20 研究（Effort Gate：客戶已調 High）

---
- Date: 2026-10-23
- Start SHA: c0e0eb6
- End SHA: （本 Batch commit，見 GitHub）
- Batch: Batch 25 — DG-20 P1 專用影像模型研究（Effort High；只研究）
- Result: `docs/DG20_IMAGE_MODEL_RESEARCH.md`：anime shortlist MeinaMix／Waifu Diffusion 1.4；realistic shortlist CyberRealistic／Realistic Vision V6.0 B1；cinematic 共用真人模型；排除 Anything／Counterfeit／OrangeMix（NAI 洩漏血統爭議）、Cool Japan Diffusion（禁商用）、NovelAI 官方權重（非商用）、SDXL 系（硬體）；Model Router 架構提案；容器網路擋 huggingface.co／civitai.com → 全部 LICENSE_UNVERIFIED。未下載、未安裝、NT$0
- Tests: 138 passed、1 skipped（僅文件）
- Decision: DG-20 待裁示
- Next: 客戶裁示 DG-20；研究完成可降回 Medium／Low（DOWNSHIFT RECOMMENDED）

---
- Date: 2026-10-23
- Start SHA: 62aae00
- End SHA: （本 Batch commit，見 GitHub）
- Batch: Batch 26 — DG-20 授權／來源／血統證據補完（不下載）
- Result: D-037；可達性實測：huggingface.co、civitai.com、各 archive 皆不可達，僅 Web 搜尋摘錄 → 無法取得授權全文／revision／sha256／Civitai 開關；CyberRealistic YAML（openrail-m）vs 內文（RAIL++-M）不一致確認；MeinaMix merge 無官方 recipe、NAI lineage 無法排除 → commercial_cleared=false；新增乾淨軌 ACertainModel；Mitsua 評估後排除（品質）
- Tests: 138 passed、1 skipped（僅文件）
- Decision: D-037
- Next: 客戶開放 huggingface.co、civitai.com（只讀）後補證據

---
- Date: 2026-10-23
- Start SHA: c3bdc53
- End SHA: （本 Batch commit，見 GitHub）
- Batch: Batch 27 — DG-20 原始證據補完（客戶開放 huggingface.co／civitai.com）
- Result: D-038；`docs/evidence/dg20/`（24 檔、MANIFEST）；三份 Civitai license 原文（Attachment B）；HF revision／sha256；MeinaMix→PastelMix→basil_mix（2023-04 起衍生物禁商用）＋NAI 無法排除 → false；ACertainModel 排除（Anything-3.0 合成資料）；CyberRealistic hash 交叉一致、作者層全開放、上游未證實；未下載
- Tests: 138 passed、1 skipped（僅文件）
- Decision: D-038；DG-20 下載／DG-22 待裁示
- Next: 客戶裁示

---
- Date: 2026-10-23
- Start SHA: ade24ee
- End SHA: （本 Batch commit，見 GitHub）
- Batch: Batch 28 — DG-20 核准下載的安全機制（checkpoint 型錄／下載驗證／single-file 載入／style-test 接線）
- Result: D-039；`see/providers/image/checkpoints.py`、`checkpoint-download`、`style-test --checkpoint/--scheduler`、evidence（vram_peak、clip skip、scheduler、checkpoint provenance、commercial_cleared=false）；Civitai 下載需 API key（401）→ MeinaMix 改 HF 鏡像＋官方 sha256 強制比對；production default 不變；容器未下載任何權重
- Tests: 149 passed、1 skipped
- Decision: D-039
- Next: Windows `git pull`

---
- Date: 2026-10-23
- Start SHA: 3341965
- End SHA: （本 Batch commit，見 GitHub）
- Batch: Batch 29 — E2-5 真機失敗 RCA（clip skip × transformers 5.x）與修復
- Result: D-040；MeinaMix 下載 verified；真機 AttributeError 根因＝diffusers 0.41 `text_encoder.text_model.final_layer_norm` vs transformers 5.20 攤平 CLIPTextModel（原始碼逐行核對）；修復＝`encode_prompt_clip_skip`（A1111 語意、4.x／5.x 版面、執行期順序驗證、evidence）；回歸測試 4 個；條件不變
- Tests: 153 passed、1 skipped
- Decision: D-040
- Next: Windows `git pull` → 重跑 MeinaMix style-test（新一條）

---
- Date: 2026-10-23
- Start SHA: 04eccb3
- End SHA: （本 Batch commit，見 GitHub）
- Batch: Batch 30 — MeinaMix 真機成功入庫＋人物近景案例
- Result: D-041；D-040 真機驗證成功（主觀：動畫感 PASS、人物／夜景 PASS、臉部無法判定、黑色偏重觀察）；`girl_portrait_closeup`（中性 base_prompt_en＋review_checklist、prompt_source）；`--scene <case_id>` 防呆；PROJECT_RULES §15
- Tests: 155 passed、1 skipped
- Decision: D-041
- Next: Windows `git pull` → MeinaMix × girl_portrait_closeup

---
- Date: 2026-10-23
- Start SHA: 29b7d26
- End SHA: （本 Batch commit，見 GitHub）
- Batch: Batch 31 — 人物近景主觀 OK 入庫＋「事後可調整風格」正式需求
- Result: D-042；PHASE2_EVIDENCE E2-5；PROJECT_RULES §15 擴充（生成後改偏好再生成、結構化設定、選項式＋自然語言、換模型不重建偏好）；ARCHITECTURE §13 能力對照與缺口；BACKLOG Preference Layer
- Tests: 155 passed、1 skipped（僅文件）
- Decision: D-042
- Next: Windows base SD1.5 對照（girl_portrait_closeup）

---
- Date: 2026-10-23
- Start SHA: 4ce2159
- End SHA: （本 Batch commit，見 GitHub）
- Batch: Batch 32 — E2-5 base SD1.5 人物近景對照入庫＋fair_comparison 釐清
- Result: D-043；base「眼睛很怪異」vs MeinaMix「比較像日本漫畫的角色」（single-user subjective）；fair_comparison=false＝metadata 定義（native 一律 false），但實際另有 clip skip 2 vs 1 差異 → model_preset_level，不宣稱嚴格公平；`baseline_condition`、`comparison_conditions`、base 記 clip_skip=1、`style-compare`；DG-23 待裁示
- Tests: 159 passed、1 skipped
- Decision: D-043
- Next: 客戶裁示 DG-23；Windows `git pull` → `style-compare`；CyberRealistic 等客戶下一步

---
- Date: 2026-10-23 約 23:50（台灣）
- Start SHA: c716b5d
- Batch: Batch 33 — 最終交接封存
- Why: 10/24 起 Project AI 額度可能取消 → 提前把所有狀態 GitHub 化
- Result: PROJECT_STATE／HANDOFF／HANDOFF_CHATGPT／HANDOFF_PROJECT_AI 加最終交接 checkpoint；BACKLOG 狀態總覽；過期分支名修正
- 最後已驗證：見 PROJECT_STATE 最終交接 checkpoint
- Next: 見 PROJECT_STATE「下一唯一安全接手點」

---
- Date: 2026-10-23
- Start SHA: 8f3fd0c
- Batch: Batch 34 — style-compare 實機 not_comparable 入庫
- Result: D-044；舊 MeinaMix 近景為 fit 512×288 → 與 Base native 不可比；D-042 誤記更正；D-043 推論撤回；免改程式（現有 CLI 支援 native＋checkpoint＋scheduler）
- Tests: 未改程式
- Next: Windows MeinaMix native 重跑 → style-compare → DG-23

---
- Date: 2026-10-23
- Start SHA: e09fce0
- Batch: Batch 35 — MeinaMix native 受控比較＋DG-23 裁示入庫
- Result: D-045；model_preset_level、客戶 OK（scene／style PASS，主觀）；DG-23 接受；commercial_cleared=false
- Tests: 未改程式
- Next: Decision Gate CyberRealistic

---
- Date: 2026-10-23
- Start SHA: bff6f82
- Batch: Batch 36 — 角色多樣性＋Reference Image 規格收斂
- Result: D-046；PROJECT_RULES §16；ARCHITECTURE §14；案例 east_asian_female_portrait／east_asian_male_portrait；未下載、未實作 Reference Image
- Tests: 160 passed、1 skipped
- Next: Windows `git pull` → CyberRealistic 東亞女性

---
- Date: 2026-10-23
- Start SHA: 477ae11
- Batch: Batch 37 — 長期目標（連續劇情 AI 短劇）＋Roadmap 入庫
- Result: D-047；ARCHITECTURE §15；BACKLOG 短劇 Roadmap；CyberRealistic 東亞女性／男性主觀入庫（男性 JSON 未入庫）；DECISIONS 索引補 D-043～D-047
- Tests: 僅文件
- Next: 結構化 Character 設定（非 UI）

---
- Date: 2026-10-23
- Start SHA: f918b17
- Batch: Batch 38 — 角色 A／B 結構化 Character 設定（非 UI）
- Result: D-048；CharacterTraits、traits 欄位、anchor 組裝、reference_images 本機路徑檢查、CLI／API；舊 fingerprint 不變
- Tests: 164 passed、1 skipped
- Next: Multi-character controlled test 設計

---
- Date: 2026-10-23
- Start SHA: 39af70b
- Batch: Batch 39 — A／B 多角色同框受控測試設計
- Result: D-049；two_characters_ab、CaseCharacter、multi_character_prompt、evidence case_characters、77 token 守門測試
- Tests: 167 passed、1 skipped
- Next: Windows `git pull` → CyberRealistic × two_characters_ab

---
- Date: 2026-10-24
- Start SHA: 2b22802
- Batch: Batch 40 — D-049 真機入庫＋多角色／Identity 研究＋新產品需求
- Result: D-050；PHASE2_EVIDENCE two_characters_ab（scene FAIL／style PASS，主觀；80＞77 截斷）；DG24 研究文件＋evidence/dg24；BACKLOG：Style/Mood Profile、Mobile-first、Env Bootstrap、Migration；移除被實測推翻的 token 粗估測試
- Next: DG-24 裁示

---
- Date: 2026-10-24
- Start SHA: eab3860
- Batch: Batch 41 — DG-24 A：S1 長 prompt 分段＋S2 regional prompting（opt-in）
- Result: D-051；chunk_token_ids／encode_text_chunks／RegionalAttnProcessor；style-test --long-prompt／--regional；evidence prompt_mode；style-compare prompt_mode；暫時 venv（torch CPU＋diffusers 0.41＋transformers 5.20，tiny 隨機權重、無下載）整合測試 10 passed
- Tests: CI 環境 172 passed、5 skipped（torch 整合測試 skip）
- Next: Windows git pull → S1 → S2

---
- Date: 2026-10-24
- Start SHA: 5406b67
- Batch: Batch 42 — style-compare 實驗變數修正＋S1 真機觀察＋需求入庫治理
- Result: D-052；compare_conditions 自動 intended（model／prompt_mode 恰一）；S1 evidence（scene FAIL，主觀）；PROJECT_RULES §12 需求當輪入庫；BACKLOG 生成後可調整總表
- Tests: 176 passed、5 skipped
- Next: Windows git pull → S2

---
- Date: 2026-10-24
- Start SHA: 6b5f655
- Batch: Batch 43 — S2 真機入庫＋S4 研究／規格
- Result: D-053；S2 FAIL（單人融合，主觀；technical 未回報不補造）；prompt-only 結案；S4 研究 §6（plus-face SD1.5＋ViT-H，2.63 GB，無新依賴，diffusers 0.41 原始碼核對 mask／embeds）；adapters.py 型錄骨架（未核准）；evidence/dg24 補 laion encoder 與 IP-Adapter LICENSE
- Tests: 178 passed、5 skipped
- Next: DG-25

---
- Date: 2026-10-24
- Start SHA: e66cf0a
- Batch: Batch 44 — DG-25 核准：IP-Adapter 下載守門＋`--identity` S4 路線
- Result: D-054；adapter-download（check／verify／yes）；style-test --identity/--ref；encoder CPU embeddings＋分欄 IP-Adapter mask；修 slicing×load_ip_adapter TypeError；容器 --check match；容器無法下載 LFS（403）→ 實檔驗證在 Windows
- Tests: 184 passed、6 skipped（CI）；venv 整合 38 passed
- Next: Windows git pull → adapter-download --check

## 2026-10-24 — Batch 45
- Batch: Batch 45 — 治理：GitHub Alone Recovery（只改文件）
- Result: D-055；PROJECT_RULES §12 永久判定＋§12.5 七項還原／治理缺口／完成定義；§12.1、§11.5 擴充；HANDOFF 入口指向 §12.5
- Tests: 無程式變更
- Next: 不變——Windows git pull → adapter-download --check

## 2026-10-24 — Batch 46
- Batch: Batch 46 — S4 真機人工結果入庫＋A／B binding 追溯＋Reference Library 規格
- Result: D-056；mapping verified（非 bug）；position→region 明確排序、mask 幾何自檢、identity_region_map＋疊圖；`workspace/identity_refs/` taxonomy（只 people 支援）
- Tests: 見 commit（CI＋venv 真實 diffusers region-swap 測試）
- Next: Windows git pull → 同 seed S4 重跑取 evidence

## 2026-10-24 — Batch 47
- Batch: Batch 47 — S4 identity fidelity FAIL 入庫＋DG-26 角色分開生成再合成（Route A 零下載 PoC）
- Result: D-057；DG26 研究文件（三 route 比較、環境盤點）；`see/core/compose.py`、`compose-scene`／`compose-review`、`ab_*` 層案例；Layered Scene → ARCHITECTURE §16
- Tests: 見 commit
- Next: Windows git pull → ab_background → A／B 單人層 → compose-scene

## 2026-10-24 — Batch 48
- Batch: Batch 48 — 角色身份定義治理（A＝男、B＝女修正；schema／gate／Reference Library／UI 規格）
- Result: D-058；PROJECT_RULES §17；ARCHITECTURE §16 欄位＋§17；`see/models/character_definition.py`；A／B 案例 v2；舊 evidence `historical_reversed_character_mapping`
- Tests: 見 commit
- Next: Windows git pull → ab_char_a_isolated（A＝男）→ ab_char_b_isolated（B＝女）→ compose-scene

## 2026-10-24 — Batch 49
- Batch: Batch 49 — A 男主角 isolated identity FAIL 入庫；DG-26 暫停；DG-28 Identity Preservation 研究
- Result: D-059；DG28 研究文件＋docs/evidence/dg28（官方 README／LICENSE／HF API／PyPI，MANIFEST.sha256）；ARCHITECTURE §17.7／§17.8
- Tests: 無程式變更
- Next: 等 DG-28 裁示（不下載、不給 Windows 指令）

## 2026-10-24 — Batch 50
- Batch: Batch 50 — DG-28 裁示 B（reference crop controlled rerun）入庫
- Result: D-060；style-test identity 檔名加 `_ref-<sha8>`（換 reference 不覆寫舊 evidence）；其餘不需程式
- Tests: 全套通過（見 commit）
- Next: Windows git pull → 放裁臉近照 → style-test ab_char_a_isolated（只此一次）

## 2026-10-24 — Batch 51
- Batch: Batch 51 — D-061 硬體封鎖＋D-062 安全工作（Preference 核心、Scene 編輯欄位、Character／Reference 後端）
- Result: preferences.py、edit_impact／set_preferences、Scene 卡新欄位＋impact 確認、reference_library.py＋`ref` CLI、character_store.py、confirmation_payload；ARCHITECTURE §13／§17.4.1／§18
- Tests: 見 commit（含 Playwright UI 實測）
- Next: Environment Bootstrap（可自主）

## 2026-10-24 — Batch 52
- Batch: Batch 52 — D-063 一般 UI 全中文輸入；Scene 中文圖片描述；Scene Character Override
- Result: scene_character.py、scene_prompt.py（PromptTranslator＋keyword fallback）、Scene.image_prompt_zh／characters、再生成範圍子欄位、Scene 卡中文分區＋人物子卡＋進階只讀；PROJECT_RULES §17／§18；ARCHITECTURE §13.1／§13.2
- Tests: 見 commit（含 Playwright UI 實測）
- Next: Environment Bootstrap（可自主）

