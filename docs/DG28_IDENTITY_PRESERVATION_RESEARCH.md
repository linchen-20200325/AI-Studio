# DG-28 Identity Preservation Research（D-059；研究，未下載、未安裝）

> 編號說明：DG-27 已在 D-057／DG-26 文件中保留給「去背／segmentation 模型」，故本研究用 **DG-28**。
> 起因（D-059）：v2 `ab_char_a_isolated`（A＝男主角）單人生成，IP-Adapter plus-face SD1.5＋CyberRealistic → **identity fidelity FAIL**（single-user subjective）。雙人污染不是唯一原因：單人也不像。
> 限制：GTX 1650 4 GB（實務 fp32：此卡 fp16 會 NaN，D-021）、Windows、NT$0、Local First。本輪**不下載、不安裝、不訓練、不啟動新 Windows 長時間生成**。
> 一手來源存於 [`docs/evidence/dg28/`](evidence/dg28/)（官方 README／LICENSE／HF API JSON／PyPI JSON，`MANIFEST.sha256`）；VRAM／時間凡未見官方數字者標「估」。

## 1. 排序權重（客戶指定）
1 identity fidelity → 2 4 GB 可行性 → 3 授權／商用風險 → 4 Windows 可維護性 → 5 下載量 → 6 推論速度 → 7 多角色擴充性。不得因「最容易接」選 fidelity 不足的方案。

## 2. InsightFace 獨立 Gate（多數 identity 方案的共同依賴）
| 層 | 授權（官方原文出處） |
|---|---|
| InsightFace Python code | **MIT**，「no limitation for both academic and commercial usage」（`gh_README_insightface.md` L40；`gh_README_insightface_python-package.md` L10） |
| 預訓練模型（buffalo_l／antelopev2 等；手動或自動下載皆同） | **non-commercial research purposes only**（`gh_README_insightface.md` L42–44；`gh_README_insightface_model_zoo.md` L3「ALL models are available for non-commercial research purposes only」） |
| 商用 | 須另洽授權（`gh_README_insightface.md` L49：buffalo_l 等 open-sourced recognition models 聯絡 recognition-oss-pack@insightface.ai） |
| 訓練資料 | annotation 與以其訓練的模型同屬 non-commercial research（L42） |
| 大小（官方 model zoo 表） | buffalo_l 326 MB（ResNet50@WebFace600K）；antelopev2 407 MB（ResNet100@Glint360K） |
| PyPI 套件 | `insightface` 2.1（純 Python wheel 1,169,452 bytes）；需 `onnxruntime`（MIT，Windows wheel ≈14.9 MB） |
| **治理注意** | buffalo_l／antelopev2 內含 **Gender&Age 屬性模型**（model zoo 表「Attributes」欄）。若採用，**只能使用 detection＋recognition embedding**，不得讀取、記錄或使用性別／年齡推論（PROJECT_RULES §17：不從圖片推論敏感身份） |

→ **結論：凡依賴 InsightFace 預訓練模型的方案，程式可商用 ≠ 方案可商用；`commercial_cleared=false`**（研究用途需客戶明確裁示）。

## 3. 候選路線（逐項）
### Route I — InstantID
- 官方：`instantX-research/InstantID`（code **Apache-2.0**）；HF `InstantX/InstantID`（rev `57b32dfe…`，card 標 apache-2.0）。
- 需求：**SDXL**；IdentityNet＝ControlNet `ControlNetModel/diffusion_pytorch_model.safetensors` **2,502,139,136 bytes**＋`ip-adapter.bin` **1,691,134,141 bytes（pickle）**；InsightFace **antelopev2**（407 MB）。
- 授權：官方 README L262 明載「face models from insightface are for non-commercial research purposes only… **Our released checkpoints are also for research purposes only**」→ 模型權重本身也只限研究，雖 HF card 標 apache-2.0。
- 4 GB：SDXL＋ControlNet，fp32 必須（此卡）→ **❌ not suitable**（估：權重 fp32 >13 GB，需 sequential offload，每張數十分鐘以上）。
- 單張 reference：是。多角色：官方無（社群做法）。

### Route II — IP-Adapter FaceID 系列（h94/IP-Adapter-FaceID，rev `43907e6f44d0…`）
- 與現有 Plus Face 差異：Plus Face 用 **CLIP 影像 embedding**（偏整體外觀，非身份）；FaceID 用 **人臉辨識 embedding（InsightFace buffalo_l）**＋LoRA；**FaceID-Plus-V2** 同時用 face ID embedding＋CLIP ViT-H 臉部影像 embedding（可調權重）。PhotoMaker 官方比較稱 FaceID-Plus-V2 為「best of IP-Adapter-FaceID」（`gh_README_pmv2.md` L25）。
- SD1.5 檔案（HF API）：
  - `ip-adapter-faceid-plusv2_sd15.bin` 156,558,509 bytes，sha256 `26d0d86a1d60d6cc811d3b8862178b461e1eeb651e6fe2b72ba17aa95411e313`（**pickle .bin**，無官方 safetensors）
  - `ip-adapter-faceid-plusv2_sd15_lora.safetensors` 51,059,544 bytes，sha256 `8abff87a15a049f3e0186c2e82c1c8e77783baf2cfb63f34c412656052eb57b0`
  - `ip-adapter-faceid-portrait-v11_sd15.bin` 64,586,623 bytes（Portrait：多張臉圖，預設 5 張，無 LoRA；只做人像）
  - image encoder：**沿用已下載驗證的 OpenCLIP ViT-H-14**（D-054，0 額外下載）
- 授權：README L405–406「AS InsightFace pretrained models are available for non-commercial research purposes, **IP-Adapter-FaceID models are released exclusively for research purposes and is not intended for commercial use**」。
- 依賴：`insightface`＋`onnxruntime`＋buffalo_l（326 MB）。
- 4 GB：SD1.5，結構同現行 S4（UNet fp32＋adapter≈0.16 GB；ViT-H 與 InsightFace 皆可在 CPU 算一次後快取）→ **✅ realistic**（估：時間≈現行單張 638～770 s；InsightFace CPU 每張參考圖數秒）。
- 多張 reference：Portrait 版原生支援；Plus-V2 可平均多張 face embedding（社群做法，需驗證）。多角色：沿用現有 per-character mask／或 DG-26 分層生成。

### Route III — PhotoMaker（V1／V2）
- 官方：`TencentARC/PhotoMaker`（code Apache-2.0）；HF `TencentARC/PhotoMaker-V2`（card apache-2.0；`photomaker-v2.bin` 1,799,993,138 bytes，pickle）。
- 需求：**SDXL**；官方「minimum GPU memory requirement for PhotoMaker is **11G**」（README L47）；V2 requirements 含 `insightface==0.7.3`、`peft`、`torchvision`；V2「relies on InsightFace… needs to comply with its license」（`gh_README_pmv2.md` L76）。
- Reference：1～N 張，官方建議多張提升 fidelity；V2 對單張與亞洲臉 fidelity 有改善（`gh_README_pmv2.md` L20）。
- 4 GB：**❌**（官方最低 11 GB）。商用：InsightFace 層 → false。

### Route IV — PuLID
- 官方：`ToTheBeginning/PuLID`（code Apache-2.0）；HF `guozinan/PuLID`（`pulid_v1.1.safetensors` 984,405,232 bytes〔SDXL〕、`pulid_flux_v0.9.1.safetensors` 1,142,099,520 bytes〔FLUX〕）。
- 需求：SDXL 或 FLUX；requirements 含 insightface、facexlib、onnxruntime、timm（EVA-CLIP）；官方：FLUX 版「can run on a 16GB graphic card」、gradio 12 GB。
- 4 GB：**❌**。商用：InsightFace 層 → false（FLUX 版另受 FLUX.1-dev 授權限制；該授權本次未存證，需另核）。

### Route V — LoRA／DreamBooth／Textual Inversion（每角色個人化訓練）
- 工具：kohya `sd-scripts`（**Apache-2.0**）；SD1.5 base（CreativeML OpenRAIL-M）；訓練資料＝使用者自己的照片（需同意紀錄）→ **唯一不依賴 InsightFace 的高 fidelity 路線**，商用風險最低（仍需 base／checkpoint 授權逐一確認；CyberRealistic 為 commercial_cleared=false）。
- Reference：社群常見 10～30 張（多角度、多光線）；Textual Inversion fidelity 一般較 LoRA 低（不建議為主）。
- 4 GB：**⚠️ technically possible but impractical**（估：SD1.5 LoRA 訓練社群常見下限 6～8 GB 且依賴 fp16／8-bit optimizer；此卡 fp16 不穩 → fp32 幾乎必 OOM；CPU 訓練以天計）。每個新角色都要訓練一次（數十分鐘～數小時，取決硬體），可自動化成 UI workflow，但使用者負擔最高。
- 客戶既有裁示：不開始 LoRA 訓練（本輪只研究）。

### Route VI — 其他 2026 現行方案
| 方案 | 官方來源 | base | 下載（HF API） | 依賴 | 授權（code／weights／encoder／data） | 4 GB |
|---|---|---|---|---|---|---|
| **Arc2Face** | `foivospar/Arc2Face`；HF `FoivosPar/Arc2Face`（rev `321709b2…`，card MIT） | **SD1.5**（fine-tuned UNet＋CLIP encoder） | UNet 3,438,167,536＋encoder 492,308,829（.bin）＋arcface.onnx 260,694,151；ControlNet（pose）1,445,157,120 選用 | insightface（antelopev2 detector）＋自帶 ArcFace（**WebFace42M** 訓練） | code／card MIT；detector＝InsightFace 非商用；ArcFace 訓練資料 WebFace42M → **unverified／非商用風險** | ✅（SD1.5 同級，估） |
| ConsistentID | `JackAILab/ConsistentID`（Apache-2.0 badge）；HF `JackAILab/ConsistentID`（card mit） | SD1.5／SDXL | `ConsistentID-v1.bin` 669,123,998＋`face_parsing.pth` 53,289,463（皆 pickle） | insightface＋face parsing | InsightFace 層非商用 → false | ✅（估） |
| InfiniteYou | `bytedance/InfiniteYou`；HF `ByteDance/InfiniteYou` | **FLUX.1-dev** | 大 | insightface 等 | InsightFace → false（FLUX.1-dev 授權另核，本次未存證） | **❌**（官方峰值 VRAM 43 GB；offload＋8-bit 仍約 16 GB） |
- Arc2Face 限制：官方定位「ID-to-face generation, conditioned solely on ID vectors」→ **主要產生臉部人像**，服裝／場景／構圖的文字控制有限（不符角色在 Scene 中的需求；可作 Layered Scene 的臉部層研究，但整合成本高）。

## 4. 比較表
| Route | Fidelity（官方／文獻定位） | 4GB | Download（新增） | Dependencies | Windows | Commercial | Multi-ref | Multi-character | Training | Recommendation |
|---|---|---|---|---|---|---|---|---|---|---|
| 現行 IP-Adapter plus-face SD1.5 | 低（CLIP 影像 embedding；真機 FAIL×2） | ✅ | 0 | 無新增 | ✅ 已驗證 | false（ViT-H 資料集） | 弱 | mask／分層 | 否 | 已證實不足 |
| **II FaceID-Plus-V2 SD1.5** | 中高（face-ID embedding＋CLIP；SD1.5 中最強之一） | **✅** | **≈0.53 GB**（0.157＋0.051＋buffalo_l 0.326） | insightface、onnxruntime | ✅（純 Python wheel＋ONNX CPU） | **false**（權重＋InsightFace 皆 research only） | 平均多張 embedding（待驗）；Portrait 版原生 | 沿用 mask／DG-26 | 否 | **Top 1（研究用）** |
| II FaceID-Portrait SD1.5 | 中高（多圖，只做人像） | ✅ | ≈0.39 GB | 同上 | ✅ | false | ✅ 原生（預設 5） | 人像層 | 否 | 搭配 Top 1 對照 |
| VI Arc2Face SD1.5 | 高（臉部 ID 相似度導向） | ✅ | ≈4.2 GB（＋ControlNet 1.4） | insightface | ✅ | unverified／false | 單 embedding | 只臉部，整合難 | 否 | 備註（臉部層研究） |
| VI ConsistentID SD1.5 | 中高 | ✅ | ≈0.72 GB（pickle） | insightface＋parsing | ⚠️ | false | 是 | 待研究 | 否 | 淘汰（pickle、資料少） |
| **V SD1.5 角色 LoRA** | **高**（每角色專屬權重；資料好時最穩） | **⚠️ 訓練不實際**；推論 ✅ | 工具＋依賴（無新模型權重） | sd-scripts（torch、accelerate、bitsandbytes…） | ⚠️（訓練環境維護重） | **最佳**（Apache-2.0 工具＋自有照片；base／checkpoint 另核） | ✅ 10～30 張 | ✅ 每角色一個 LoRA，天然 per-character | **是（每角色）** | **Top 2（長期、商用路線）** |
| I InstantID | 高 | ❌ | ≈4.2 GB＋antelopev2 0.41 GB＋SDXL | insightface、ControlNet、SDXL | ⚠️ | false（checkpoints research only） | 單張 | 社群 | 否 | 淘汰：4 GB ❌ |
| III PhotoMaker V2 | 高 | ❌（官方 11 GB） | ≈1.8 GB＋SDXL | insightface、peft、torchvision | ⚠️ | false | ✅ | — | 否 | 淘汰：4 GB ❌ |
| IV PuLID | 高（FLUX 版更高） | ❌（12～16 GB） | ≈1～1.6 GB＋SDXL/FLUX | insightface、EVA-CLIP | ⚠️ | false | — | 社群 | 否 | 淘汰：4 GB ❌ |
| VI InfiniteYou | 高 | ❌（≥16 GB） | 大＋FLUX | insightface | ⚠️ | false | — | — | 否 | 淘汰：4 GB ❌ |

## 5. 結論（總管建議；待客戶裁示）
- **Top 1：IP-Adapter FaceID-Plus-V2 SD1.5（研究用途）**——在 4 GB 硬限制下 fidelity 最有機會明顯高於現行 plus-face 的路線：改用人臉辨識 embedding（真正的身份特徵）且自帶人臉偵測＋對齊（現行只做 CLIP 中心裁切，見 §7）；沿用已下載的 ViT-H 與現有 diffusers IP-Adapter／mask／分層架構，新增下載最小（≈0.53 GB）。**代價：commercial_cleared=false（InsightFace 預訓練模型與 FaceID 權重皆 research only）＋主權重為 pickle .bin（違反現行「只收 safetensors」規則，需例外裁示）＋新增 insightface／onnxruntime 依賴。**
- **Top 2：SD1.5 角色 LoRA（長期商用候選）**——唯一不依賴 InsightFace、授權最乾淨、per-character 天然適合 Layered Scene；但 GTX 1650 4 GB 本機訓練不實際，且客戶目前禁止訓練 → 需另一個 Gate（訓練硬體／時間／使用者負擔）。
- 淘汰：InstantID、PhotoMaker、PuLID、InfiniteYou（全部 SDXL／FLUX，4 GB ❌，且同樣卡 InsightFace）；ConsistentID（pickle、證據少）；Arc2Face 保留為「臉部層」研究備註（輸出以臉為主、整合成本高）。
- **誠實限制**：沒有任何路線同時滿足「高 fidelity＋4 GB＋可商用＋零訓練」。研究用 Top 1 可回答「技術上能否像」；商用路線需 Top 2 或日後取得 InsightFace 商用授權（另議）。

## 6. Top 1 若核准：下載／安裝清單（**未執行**，待裁示）
| 項目 | 檔名 | 大小 | 官方來源／revision | sha256 | License | 硬碟 |
|---|---|---|---|---|---|---|
| FaceID-Plus-V2 adapter | `ip-adapter-faceid-plusv2_sd15.bin` | 156,558,509 B | HF `h94/IP-Adapter-FaceID` @ `43907e6f44d079bf1a9102d9a6e56aef7a219bae` | `26d0d86a…11e313` | research only（README L405–406） | 0.16 GB |
| FaceID-Plus-V2 LoRA | `ip-adapter-faceid-plusv2_sd15_lora.safetensors` | 51,059,544 B | 同上 | `8abff87a…eb57b0` | 同上 | 0.05 GB |
| 臉部偵測＋辨識 | InsightFace `buffalo_l`（zip） | 326 MB（官方 model zoo 表） | InsightFace 官方（下載前須再核 URL／hash；本 session 無法查 GitHub release API） | 待核 | **non-commercial research only** | ≈0.33 GB |
| Python 套件 | `insightface` 2.1（wheel 1,169,452 B）、`onnxruntime` 1.31.0（win_amd64 ≈14.9 MB） | — | PyPI | PyPI 提供 | MIT（code） | ≈0.1 GB |
| image encoder | OpenCLIP ViT-H-14 | 0（已下載驗證，D-054） | — | 已驗 | MIT（LAION 資料研究建議） | 0 |
- 合計新增下載 ≈ **0.53 GB**（權重）＋ ≈0.02 GB（套件）。VRAM（估）：同現行 S4（UNet fp32＋adapter≈0.2 GB；InsightFace／ViT-H 在 CPU）。
- **pickle 處理需裁示**：選項 (a) 例外核准以 `torch.load(weights_only=True)` 在隔離步驟轉成 safetensors 後只用 safetensors；(b) 不核准 → Top 1 不可行。
- 合規：只用 detection＋recognition embedding；**不得讀取／記錄 InsightFace 的 gender／age 輸出**；reference 仍只在本機。

## 6.5 客戶裁示（D-060）
選 **B：零下載 reference crop 對照**（一次 controlled rerun，唯一變因＝男性 reference 改臉部大近照）。仍不像或只「有進步」＝FAIL → 停止 crop 路線、回到選項 A（FaceID-Plus-V2 研究 PoC，須再裁示）。FaceID-Plus-V2 未核准下載／安裝。

## 6.6 後續（D-061）
客戶裁示 **HARDWARE_UPGRADE_BLOCKED**：D-060 的 reference crop rerun 改為 DEFERRED（未執行）；FaceID／InsightFace／LoRA 全部不做。硬體升級（≥12 GB VRAM 級）後依 ARCHITECTURE §18 Resume Gate 重新研究；本文件屆時視為過期參考。

## 7. Reference 品質（研究）
- 本次男性 reference：非正面證件照、背景有人、光線一般、臉部佔比有限（客戶描述）。
- 現行管線**沒有人臉偵測**：`_identity_embeds` 對整張圖做 CLIP 224 中心裁切 → 臉小時，送進 plus-face 的多半不是臉（背景、身體、其他人）。這是**本專案前處理造成的可歸因因素之一**，但不是全部原因：plus-face 本質是 CLIP 外觀 embedding、非身份 embedding（Route II 的差異）。
- 不把責任全部推給 reference：同一張 reference 在 FaceID 類（自帶偵測／對齊）上的結果才能分離兩個因素。
- 可選零下載對照（未排程）：使用者手動把 reference 裁成臉部佔 60～80% 的正面近照，同 seed／同條件重跑 A isolated → 若 fidelity 明顯上升，證明前處理因素顯著。
- **Reference Quality Check 規格**（UI；本輪只做規格，不做自動臉辨識）見 ARCHITECTURE §17.7。

## 8. 產品 UX 對照（建立角色 → 上傳 1～N 張 → 建身份 → 試生成 → 使用者確認像不像 → 確認角色 → Scene 重用）
| 需求 | FaceID-Plus-V2（Top 1） | 角色 LoRA（Top 2） |
|---|---|---|
| 一張圖 | ✅ | ❌（需多張） |
| 多張圖／正側面 | 平均 embedding（待驗）；Portrait 版原生多張 | ✅（越多越好） |
| reference 更新 | ✅ 立即（重算 embedding） | 需重訓 |
| 角色資料保存 | 存 embedding＋asset metadata（不存臉照到 Git） | 存 LoRA 檔（本機） |
| 不必每 Scene 重訓 | ✅ | ✅（每角色訓一次） |
| 只重做某角色 | ✅（Layered Scene） | ✅ |
| 多角色 | mask 或分層 | 每角色一 LoRA（多 LoRA 同框需 regional，否則分層） |
| Style 改變身份不變 | 中（style 強時 fidelity 降，需驗） | 較佳（需驗） |

## 9. Identity Consistency 驗收（定義見 ARCHITECTURE §17.8）
不是「生成一張像」：同一 character_id 在不同背景、服裝、表情、角度、鏡頭、Style 下，仍可被人工辨識為同一角色。
