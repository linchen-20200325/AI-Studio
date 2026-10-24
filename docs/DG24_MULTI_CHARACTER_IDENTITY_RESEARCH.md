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
