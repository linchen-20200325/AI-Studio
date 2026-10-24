# DG24_MULTI_CHARACTER_IDENTITY_RESEARCH.md — 多角色 attribute binding／Identity 研究（D-050）

> 前提：NT$0、Local First、GTX 1650 4 GB（fp16 會 NaN → 實務 fp32）、SD 1.5 架構。**本文件只研究，未下載任何模型、未安裝依賴、未改 production default。**
> 原始證據：`docs/evidence/dg24/`（HF API JSON＋README，2026-10-24 取得；MANIFEST.sha256）。授權為研究整理，非法律意見。

## 1. 觸發證據（D-049 真機；single-user subjective）
CyberRealistic × `two_characters_ab`：technical_valid=true；**scene FAIL／style PASS**。A／B 辨識失敗（臉部特徵過度相似、East Asian 外觀模板化）、A 紅大衣遺失且錯戴眼鏡、B 灰短髮未遵守、眼鏡污染到 A。另：`prompt_tokens=80`＞77 → `prompt_truncated=true`。

## 2. 根因分層（不把 token 截斷當唯一原因）
| # | 原因 | 證據／原理 | 影響 |
|---|---|---|---|
| R1 | **SD 1.5 CLIP text conditioning 無屬性綁定**：整段 prompt 經 cross-attention 對全圖作用，屬性詞（glasses、grey、red coat）不會綁定到特定人物 | 架構原理（業界共識：attribute leakage／binding problem）；本次眼鏡污染 A、紅大衣遺失吻合 | 主因 |
| R2 | 截斷：80 token → 最後 ~3 token 被丟棄（實際丟的是**尾端的 Style Profile 詞**，不是角色錨點） | evidence；角色錨點在前段 | 次要：影響風格詞，不解釋屬性互換 |
| R3 | 臉部差異不足／模板化：模型對 "East Asian woman/man" 收斂到資料集平均臉；文字無法表達個體臉部 Identity | 原理＋本次觀察 | 只有 Identity 條件（參考圖）能根本解 |
| R4 | 重抽 seed：只改變隨機結果，不改條件機制 | 原理 | **不是解法**（客戶裁示） |

另：D-049 測試中的「詞＋標點粗估 ≤75」守門被真機推翻（實測 80）→ 已移除該啟發式測試；token 數一律以真機 evidence `prompt_tokens` 為準。

## 3. 方案比較
| 方案 | 需新下載？ | 新依賴？ | GTX 1650 可行性（估） | 授權 | 解什麼 | 風險 |
|---|---|---|---|---|---|---|
| **S1 長 prompt 分段編碼**（A1111 式：每 75 token 一段各自編碼後串接 embeds） | 否 | 否（沿用 D-040 自編 embeds 路徑） | 無額外 VRAM 顯著增加 | — | R2（截斷） | 不解 R1／R3 |
| **S2 Regional prompting／區域條件**（每角色一段 prompt＋空間 mask，在 cross-attention 或 latent 層分區合成；MultiDiffusion／Latent Couple 類） | 否（用現有 checkpoint） | 否（需自寫 attention processor 或 latent 分區；diffusers community 版需另抓程式碼，須先審 License） | 實作後修正（D-051）：只在 cross-attention 多算 (區域數+1) 次 attention，UNet 前向次數不變 → 時間增加有限（待真機實測） | 自寫碼無授權問題 | R1（大幅改善綁定） | 邊界融合、需工程；未經真機證實 |
| **S3 分段生成（staged）**：A、B 各自單人生成 → 合成 → 低強度 img2img／inpaint 統一光影 | 否（img2img／inpaint pipeline 可用現有 SD1.5 權重，品質較專用 inpaint 模型差） | 否 | 3 次生成 ≈30 分 | — | R1（徹底分離屬性） | 合成接縫、比例／光線不一致 |
| **S4 IP-Adapter（plus-face_sd15／full-face_sd15）**＋diffusers 內建 `load_ip_adapter`、多 adapter＋**IP-Adapter mask**（每角色一張參考圖＋區域） | **是**：adapter 98 MB／44 MB safetensors＋**image encoder ViT-H 2,528,373,448 bytes safetensors** | 否（diffusers 內建；用既有 transformers CLIPVision） | 4 GB：fp32 UNet＋ViT-H ≈ 偏緊，需 CPU offload；時間估 +30–60% | **repo 標 Apache-2.0**（HF API `cardData.license`）；image encoder 為 OpenCLIP ViT-H（上游授權需另核） | R3（Identity）＋配合 mask 解 R1 | 4 GB 可能 OOM（未證實）；與單檔 checkpoint 相容性需真機 |
| **S5 IP-Adapter-FaceID** | 是（faceid_sd15 主檔**只有 .bin（pickle）**，lora 部分為 safetensors） | **是：insightface（＋onnxruntime）** | 另需人臉偵測模型 | **README 明載：InsightFace 預訓練模型僅限非商業研究 → FaceID 僅供研究、不得商用** | R3（最強臉部 Identity） | **違反 safetensors-only 規則＋非商用 → 不建議** |
| S6 角色 LoRA（每角色訓練） | 訓練資料 | 是（訓練工具） | 4 GB 訓練困難 | 視資料 | R3 | 客戶禁止開始訓練 |

## 4. 結論（Project AI 建議；非客戶裁示）
1. **零下載先做（可自主，需真機驗證）**：S1 修截斷（小、可逆、opt-in）→ S2 regional prompting 原型（opt-in 診斷旗標，預設不變）→ 以同一 `two_characters_ab`、同 seed 對照（style-compare 只差 `composition_mode`）。
2. **Identity（R3）文字方案無法根本解**；最可行候選＝**S4 IP-Adapter plus-face／full-face SD1.5**（Apache-2.0、safetensors、無新依賴）。需 **DG-24 裁示下載 ≈2.67 GB**（ViT-H 2.53 GB＋adapter ≈0.1 GB），並先做 image encoder 上游授權核對與 4 GB 可行性真機。
3. **S5 FaceID 不建議**（pickle＋InsightFace 非商用＋新依賴）。S6 依客戶禁令不做。
4. 參考圖一律本機（PROJECT_RULES §16）；測試用參考人像不得是真人照片進 Git——可用本專案自己生成的角色圖當參考（無隱私問題）。

## 5. DG-24 裁示與實作（D-051）
客戶裁示 A。S1＝`--long-prompt`、S2＝`--regional` 已實作（opt-in）。真機受控比較順序：D-049 基準（standard）→ S1 → S2；每次 style-compare 須只差 `prompt_mode`。預期：S1 修截斷（風格詞完整）；S2 針對屬性綁定；**兩者都不解決臉部 Identity／模板化（R3）**——若 S2 後 A／B 屬性正確但臉仍過度相似，即回 DG-24 評估 S4。

## 6. S4 Reference Image／Identity conditioning 研究（D-053；**未下載**）
### 6.1 真機結論回顧
S1 修截斷但綁定／臉部多樣性未解；S2 單人融合（D-052／D-053）。純 prompt 路線結案（客戶）。

### 6.2 推薦方案：IP-Adapter **plus-face SD1.5**＋OpenCLIP ViT-H-14 image encoder
| 項目 | 內容（原始證據 `docs/evidence/dg24/`） |
|---|---|
| 檔案（固定 revision `018e4027…`） | `models/ip-adapter-plus-face_sd15.safetensors` 98,183,288 B（sha256 `1c9edc21…f7569b`）；`models/image_encoder/model.safetensors` 2,528,373,448 B（sha256 `6ca9667d…07b030`，fp16，632.08M params）；`models/image_encoder/config.json` 560 B |
| **下載總量** | **2,626,557,296 bytes ≈ 2.63 GB**（全部 safetensors／json；無 pickle） |
| 為何 plus-face | patch embeddings（比 global 版更貼近參考）＋以裁切臉部為條件 → 直接對應「A／B 臉部 Identity 分離、不靠文字模板臉」。full-face（43.6 MB）可作備案，同一 encoder |
| 不選 | FaceID（pickle＋InsightFace 非商用＋新依賴）；vit-G 版（需 bigG encoder 3.69 GB）；SDXL 系（4 GB 不實用） |
| diffusers 0.41.0 相容 | 已在同版本原始碼核對：`load_ip_adapter(path, subfolder, weight_name, image_encoder_folder)` 支援本機路徑與 list（多 adapter）；`IPAdapterAttnProcessor` 支援 `ip_adapter_masks`（每張參考圖一個 mask，形狀 `[1, num_images, h, w]`，`IPAdapterMaskProcessor` 前處理）；可傳 `ip_adapter_image_embeds`（預先算好、可快取） |
| 額外 dependency | **不需要**：image encoder 用既有 transformers `CLIPVisionModelWithProjection`；feature extractor 由 diffusers 自建 `CLIPImageProcessor`——transformers 5.20 無 torchvision 時自動退回 PIL 版（容器實測 `CLIPImageProcessorPil` 輸出 1×3×224×224）。**不需 torchvision、insightface、peft**（plus-face 無 LoRA 部分） |
| Multi-reference／per-character | 一個 plus-face adapter＋**兩張參考圖**（A、B 各一）＋**兩個 IP-Adapter mask**（左欄／右欄）→ 每個角色的臉部條件只作用在自己的區域；文字 prompt 走標準或 S1 長 prompt。**不與 S2 RegionalAttnProcessor 同時使用**（兩者都替換 attn2 processor；改用 IP-Adapter 內建 mask） |
| ControlNet 協作 | diffusers 支援 IP-Adapter＋ControlNet 併用，但 ControlNet（openpose 等）需另下載約 1.4 GB → 不在本次範圍，S4 後若兩人佈局仍崩再評估 |
| GTX 1650 4 GB（估，**未證實**） | UNet fp32 ≈3.44 GB（現況已靠 offload）；adapter 權重 fp32 ≈0.2 GB 掛在 UNet；image encoder fp32 ≈2.5 GB **不上 GPU**：在 CPU（64 GB RAM）算一次參考圖 embeddings 後快取，生成時傳 `ip_adapter_image_embeds` → GPU 峰值預期接近現況＋0.2 GB。風險：OOM → 走既有 OOM 降級；仍 OOM → fail-closed 回報，不切付費 |
| RAM／disk／時間（估） | RAM：encoder fp32 載入 ≈2.5–5 GB（64 GB 足夠）；disk ≈2.63 GB；時間：encoder CPU 每張參考圖數秒～數十秒（一次性）；生成每步 attn2 多一組 k/v → 估 +10–20%（現況 ≈640 s／張 → ≈700–770 s）。皆待真機 |
| License／commercial | adapter：Apache-2.0；encoder 權重：MIT，但訓練資料 LAION-5B 官方「建議研究用途、不建議直接用於工業產品」；底模 CyberRealistic／MeinaMix 另有限制 → **commercial_cleared=false**，僅內部品質驗證 |
| 失敗 fallback | 無 adapter／未核准 → 現行文字錨點路徑（行為不變）；載入失敗 → fail-closed（不產生假結果）；Identity 仍不足 → 回 DG（ControlNet 佈局、或接受 SD 1.5 上限、或換算力） |

### 6.3 與產品整合（Provider Agnostic）
- 偏好層不變：`CharacterAppearance.reference_images`（本機路徑，§16）＋`CharacterTraits`；Identity provider 讀 `params.characters[*].reference_images`（D-032 已預留）。model-specific（adapter id、scale、mask 方式）放 `adapter` 欄位／模型層。
- 參考圖 embeddings 以 (adapter_id, encoder sha, 參考圖 sha256) 快取 → 改單一角色參考圖只讓該角色出現的 Scene 失效重生（沿用 per-scene fingerprint）。
- 不把臉型等同族群：參考圖決定臉部 Identity；`appearance_region` 只是文字描述，不再是臉的唯一來源。
- 測試參考圖：用本專案自己生成的角色圖（例：東亞女性／男性 portrait 結果）或客戶明確同意的本機圖；**真人照片不進 Git／fixture／第三方**。

### 6.4 PoC 設計與測試規格（DG-25 核准後）
1. `checkpoint-download` 同等守門：只下載型錄內檔案、核 bytes＋sha256、寫 provenance；`approved` 由裁示記錄後才改 True。
2. style-test 新 opt-in：`--identity ip_adapter_plus_face_sd15 --ref-a <本機圖> --ref-b <本機圖>`；evidence 記 adapter／encoder sha、參考圖 sha256（不記路徑內容）、scale、mask、VRAM peak。
3. 受控比較：同 `two_characters_ab`、seed 1234、CyberRealistic；style-compare 新實驗變數 `identity_mode`（none→ip_adapter），其餘全同。
4. 人工判定（single-user subjective）：兩人存在、A／B 臉部可區分、屬性不互換、臉部自然度與局部幾何。
5. 單元測試：型錄守門（已完成）、mask 產生、參考圖 sha 快取鍵、未核准拒絕。
