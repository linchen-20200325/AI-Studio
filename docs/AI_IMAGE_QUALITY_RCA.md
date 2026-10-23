# AI_IMAGE_QUALITY_RCA.md — SD 1.5 scene adherence 異常根因分析（D-035）

> 觸發：E2-4 picture_book 真機 `technical_valid=true`，但人工判定**場景／風格皆不合格**（幾乎看不到貓、沒有追蝴蝶、沒有庭院構圖，畫面是高飽和粗黑線＋抽象／水果／幾何圖形）。
> 本文件只做根因追查與選項整理；**未下載任何模型、未改預設生成行為、未改任何 Style Profile**。

## 1. 實際送進 SD 1.5 的內容（程式碼逐段追查，非推測）
| 階段 | 位置 | 實際值（picture_book／kitten_butterfly） |
|---|---|---|
| scene | `see/core/style_tests.py` `kitten_butterfly` | 小貓咪在院子裡追蝴蝶，陽光很溫暖 |
| base prompt | `see/core/prompting.py` `build_image_prompt_en`（Mock LLM 關鍵詞表，**最長詞優先**排序） | `a kitten, a courtyard, butterflies, warm sunlight, chasing, storybook illustration, soft watercolor, warm light, cinematic composition, highly detailed` |
| style prompt | `see/core/styles.py` `apply_style`：移除 legacy 尾綴，接 positive_terms | `a kitten, a courtyard, butterflies, warm sunlight, chasing, children's picture book illustration, gouache, soft pastel colors, simple shapes, warm light` |
| negative | `default_negative_prompt` ＋ style negative | `text, watermark, logo, signature, lowres, blurry, deformed, extra limbs, bad anatomy, nsfw, photorealistic, 3d render` |
| 請求尺寸 | `IMAGE_SCALE=1.5` × 輸出 1280×720（`Settings` 預設） | **1920×1080** |
| **實際生成解析度** | `gen_size(…, max_side=512)`：長邊壓到 512 | **512×288**（latent 64×36） |
| 放大 | `generate_image`：`Image.resize(LANCZOS)` | 512×288 → 1920×1080，**×3.75** 純插值放大（無 hires-fix／upscaler） |
| model／weights | `stable-diffusion-v1-5/stable-diffusion-v1-5`，`variant=fp16`（唯一下載的 variant） | 正確；fp32 時同一份 fp16 權重載入時 upcast（D-022） |
| scheduler | 未覆寫 → 模型 `scheduler_config.json` 預設（SD 1.5＝PNDM） | 25 steps，guidance 7.0（標準值） |
| seed | `torch.Generator("cpu").manual_seed(1234)` | 跨裝置／跨 dtype 確定性；**同輸入重跑＝同一張圖** |
| dtype | GTX 1650：fp16（VAE fp32）→ NaN → 整條 fp32 | fp32＝參考精度 |
| prompt token | CLIP 上限 77（含 BOS/EOS） | 估 ≈40 token，**未截斷**（容器無 tokenizer；新 evidence 會記錄實測 `prompt_tokens`／`prompt_truncated`） |

## 2. 根因假說與證據強度（分四類）
| # | 類別 | 假說 | 證據 | 判定 |
|---|---|---|---|---|
| H1 | **pipeline bug** | 16:9 長邊壓到 512 → **512×288**，短邊只有 SD 1.5 訓練解析度（512）的 56%。SD 1.5 在顯著低於 512 的尺寸常產生破碎構圖、主體消失、抽象紋理；再 ×3.75 插值放大 → 粗糊線條 | 程式碼＋`gen_size` 計算確定；症狀吻合；**Phase 1 所有真機圖也是 512×288**（Phase 1 驗收只驗技術，未驗場景） | **最高嫌疑**（未經真機 A/B 證實） |
| H2 | style preset | picture_book 的 `simple shapes`、`gouache`、`soft pastel colors` 把模型推向抽象／幾何形狀，壓過場景語意 | 「幾何圖形」症狀與詞彙吻合；只影響此風格 | 中（依 D-034 不調整 picture_book） |
| H3 | prompt 建構（Mock LLM） | 關鍵詞依「詞長」排序，`chasing` 與主體分離，沒有「kitten chasing butterflies in a courtyard」的關係結構 | 程式碼確定 | 中（SD 1.5 CLIP 近似 bag-of-words，影響小於 H1） |
| H4 | SD 1.5 base 能力 | base 模型的 prompt adherence 與 anime／寫實美感本來就弱於後續 fine-tune／新架構 | 業界共識；**本專案尚無乾淨證據**（H1 未排除前無法分離） | 待 H1 排除後評估 |
| H5 | negative prompt | `photorealistic, 3d render` 等不會抑制「貓」這個主體 | 詞義 | 低 |
| H6 | fp32 upcast／CPU offload | fp16→fp32 是無損 upcast；offload 只搬權重不改數值 | 原理 | 極低 |
| H7 | 截斷 | 估 ≈40／77 token | 估算 | 低（新 evidence 實測） |
| H8 | scheduler／steps／CFG | PNDM 25 步、CFG 7 為 SD 1.5 標準值 | 程式碼 | 低 |
| H9 | 硬體 GTX 1650 | 只影響精度（已升 fp32）、速度、可用解析度，不改語意 | 原理 | 低（但限制可選模型，見 §4） |

「與前一次結果沒有實質改善」：同 prompt＋同 seed＋同解析度 → 確定性產生同一張圖，這是預期行為，不是新的失敗訊號。

## 3. 本批修正（低風險，預設行為不變）
1. **分層驗收**（`see/core/style_tests.py`）：`technical_valid`（自動）｜`prompt_subject_check`（自動，只驗 prompt 有沒有帶到主體）｜`scene_validated`／`style_validated`（**只能人工** `style-review`，預設 `null`）。舊欄位 `valid_for_style_test` 移除；舊 `style_validated`（其實是型錄旗標）改名 `style_profile_catalog_validated`，避免混淆。不做不可靠的自動美感評分。
2. **案例與風格分離**：`STYLE_TEST_CASES`（`kitten_butterfly` 基準、`girl_city_night` 人物案例，供 P1 動畫／真人／電影感）；新增風格只加 StyleProfile，新增案例只加 StyleTestCase。
3. **診斷參數（opt-in）**：`style-test --gen-policy native`（短邊 512、長邊 ≤768 → 768×512 生成 → 中心裁成 768×432 → 放大 ×2.5）、`--base-prompt`（手寫結構化 prompt）、`--scene`。診斷結果標 `fair_comparison=false`，檔名加後綴，**永不覆寫基準失敗證據**。
4. **生成證據補齊**：`gen_width/gen_height`、`gen_policy`、`crop_box`、`upscale_factor`、`scheduler`、`steps`、`guidance`、`prompt_tokens`、`prompt_truncated`。
5. 預設 `gen_policy=fit` 不進 `ImageRequest.params` → 既有專案 image fingerprint 不變、不需 PROVIDER_VERSION bump。

## 4. 若 H1 修正後仍不足：候選方案（**初步整理；未下載；授權須在下載前逐一核對 model card**）
GTX 1650 前提：fp16 會 NaN → 實務上必須 fp32（權重記憶體 ×2）；4 GB VRAM。

| 方案 | 架構 | 下載量 | GTX 1650 可行性／速度（估） | 授權（初步） | 優點 | 缺點 |
|---|---|---|---|---|---|---|
| A. 現有 SD 1.5 base＋native 解析度 | SD 1.5 | 0 | 已驗證可跑；768×512 fp32 估 ×2–3 時間（約 5–10 分／張） | CreativeML OpenRAIL-M | NT$0、無新下載 | base 美感／adherence 上限低 |
| B1. SD 1.5 anime fine-tune checkpoint | SD 1.5 | ≈2 GB／個 | 與現況相同 VRAM／速度 | 多為 OpenRAIL-M 衍生，常附額外限制（商用／再散布） | 動畫風格大幅提升，介面零改動（新 preset） | 每路線一個 checkpoint；授權需逐一判斷；多在 Civitai |
| B2. SD 1.5 photoreal fine-tune checkpoint | SD 1.5 | ≈2 GB／個 | 同上 | 同上 | AI 真人／寫實明顯提升 | 同上；人像倫理／肖像風險需規範 |
| B3. SD 1.5 LoRA（風格） | SD 1.5＋LoRA | 10–150 MB | 同現況，略增載入 | 各自不同 | 小、可疊加、可對應 Style Profile | 需 `peft` 類依賴；品質依 LoRA |
| C1. SDXL 系（含 anime／photoreal 衍生） | SDXL | ≈7 GB（fp16） | 4 GB 需 sequential offload＋fp32 → 估每張十數分鐘以上；高 OOM 風險 | SDXL base＝OpenRAIL++-M；衍生模型授權差異大 | adherence／美感明顯較好 | 本硬體不實用 |
| C2. SD 3.5 Medium | MMDiT＋T5 | 數 GB＋T5 | 官方建議 VRAM 遠高於 4 GB | Stability Community License（營收門檻） | adherence 強 | 本硬體不實用；授權有門檻 |
| C3. FLUX.1-schnell（preset 已存在） | 12B | ≈24 GB | 不可行 | Apache-2.0 | adherence 很強 | 本硬體不可行 |
| D. 換算力（Compute Agnostic） | 任意 | — | 新 GPU／NAS／雲端 | — | 解鎖 C 系 | 新硬體／付費＝停手條件 |

## 5. 下一步與 Decision Gate
1. **先做零成本真機 A/B（只換一個變數）**：`python -m see.app.cli style-test --style picture_book --gen-policy native`（輸出 `picture_book_seed1234_native.png`，與失敗基準 `picture_book_seed1234.png` 並排人工比較）。這是 pipeline 診斷，不是調整 picture_book 風格（D-034 仍有效）。
2. 依結果：
   - 場景明顯改善 → H1 證實 → **DG-21**：是否把 `native` 設為產品預設（會讓所有既有專案 image fingerprint 失效並重生、每張耗時增加）→ 之後再用 native 做 anime／realistic／cinematic 公平比較。
   - 無改善 → 再以 `--base-prompt "a kitten chasing butterflies in a sunny courtyard"` 分離 H3；仍無改善 → 證據指向 H4 → **DG-20**（A 維持 SD 1.5｜B 研究 SD 1.5 fine-tune／LoRA｜C 依路線分 provider）。
3. 任何新 checkpoint／LoRA／依賴／下載 → 停在 Decision Gate。

## 6. 真機 A/B 結果（D-036）
- picture_book native：scene PASS／style PASS → **H1 證實**（pipeline 生成解析度）。
- anime＋girl_city_night native：scene PASS／style FAIL（臉部／人體／背景嚴重失真）→ 解析度修正後仍不足，指向 **H4：SD 1.5 base 對動畫人物能力不足**。
- 客戶裁示：不再以 prompt 調 Base SD1.5；進入 DG-20 專用模型研究（§4 表為舊初稿，以 DG-20 研究文件為準）。
