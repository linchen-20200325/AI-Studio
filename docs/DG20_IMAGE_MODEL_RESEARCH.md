# DG20_IMAGE_MODEL_RESEARCH.md — P1 專用影像模型研究（D-036；只研究、未下載）

> 範圍：P1-A 日系動畫、P1-B AI 真人／寫實、P1-C 電影感。硬體：Windows、GTX 1650 4 GB、RAM ≈65 GB、Python 3.12；fp16 會 NaN → 實務 fp32。
> 本 Batch：**未下載任何模型、未安裝套件、未改預設模型、未改 cache 語意**。
>
> **證據等級（重要）**：本容器網路政策**擋 `huggingface.co`、`civitai.com`**（DNS 無法解析），無法直接開啟原始 model card／授權頁；以下授權資訊來自 Web 搜尋對原始頁面的摘錄與第三方彙整。依客戶規則，**所有候選一律標 `LICENSE_UNVERIFIED`**，括號內註明現有證據方向。下載前必須逐一開啟原始頁面核對（§6 清單）。

## 1. 前提與篩選原則
1. **架構必須是 SD 1.5 系**（或同量級）：已證實 SD 1.5 fp32＋CPU offload 能在 4 GB 卡跑 768×512（D-036）。SDXL（≈6.9 GB fp16 權重，fp32 ×2）、SD 3.5、FLUX 在此卡不實用 → 只列為未來換算力後的路線。
2. 同架構 = 直接沿用現有 `DiffusersImageProvider` 的 RuntimePlan、fp16→fp32 階梯、OOM 階梯、evidence；不需新 dependency（`from_single_file` 是 diffusers 內建）。
3. **NovelAI 洩漏模型血統（NAI lineage）**：2022-10 NovelAI 模型外洩，Anything V3 被廣泛指出由其 fine-tune；大量 SD 1.5 動畫 merge（Anything、Counterfeit、AbyssOrangeMix／OrangeMix 等）被社群指稱含此血統，Anlatan（NovelAI）曾發 DMCA。這是**商用法律風險**，不是授權字面問題；目前無法院判決。NovelAI 後來官方公開的 V1／V2 權重為**非商用**授權。
4. 不因「社群很多人用」推定可商用。

## 2. P1-A 日系動畫 shortlist
| 項目 | **候選 A：MeinaMix**（V11／V12 Final） | **候選 B：Waifu Diffusion 1.4**（hakurei） |
|---|---|---|
| 正式來源 | Civitai `models/7240`（作者 Meina）；HF `Meina/MeinaMix_V11`、`Meina/MeinaMix` | HF `hakurei/waifu-diffusion-v1-4` |
| 架構 | SD 1.5（block-weighted merge：MeinaPastel、PastelMix、Facebomb 等） | SD 2.1-base fine-tune（次級來源；非 merge） |
| 大小 | 單檔 ≈2.13 GB（`meinamix_meinaV11.safetensors`，mirror 列示） | `wd-1-4-anime_e1.ckpt` 5.16 GB（**.ckpt＝pickle，有安全風險**；需找 safetensors／diffusers 版） |
| VRAM／RAM | 同現行 SD 1.5（fp32 UNet ≈3.4 GB，靠 CPU offload）；RAM 充足 | UNet 同量級；OpenCLIP-H 文字編碼器較大（fp32 ≈1.4 GB）；靠 offload |
| GTX 1650 可行性 | **高**（與已驗證路徑同架構） | 中（SD 2.x 未在本機驗證；訓練解析度 768 → 512 可能偏離最佳） |
| fp32 速度（估） | 與現行 SD 1.5 相同級距（每張數分鐘，首景含 fp16 失敗一次） | 略慢於 SD 1.5 |
| 授權 | **LICENSE_UNVERIFIED**（HF 標 `creativeml-openrail-m`；Civitai 標「CreativeML Open RAIL-M Addendum」，商用開關未能讀取） | **LICENSE_UNVERIFIED**（HF 卡片摘錄：OpenRAIL-M，**明文允許商用／作為服務與再散布**，需傳遞同等使用限制；致謝欄列 NovelAI，需確認無血統關係） |
| 模型商用 | 未確認 | 摘錄顯示允許 |
| 生成內容商用 | 未確認（Civitai「Sell images」開關未讀到） | 摘錄顯示允許（OpenRAIL-M：授權方不主張輸出權利） |
| 再散布 | OpenRAIL-M 允許（需附授權＋限制）；Addendum 未確認 | 允許（附授權＋限制） |
| NAI 血統 | **NAI_LINEAGE_UNVERIFIED（高風險族群）**：merge 來源含 PastelMix 等，未找到公開檢測結果 | 非 merge；致謝 NovelAI 的意義未確認 |
| 額外 VAE | 未確認是否內建；常見搭配 anime VAE（≈0.33 GB，可選） | 未確認 |
| 接 diffusers | `from_single_file`（以本機 `D:\ai-models\sd15` 當 config，離線）或 HF diffusers 版 | `from_pretrained`（需確認 diffusers 版存在） |
| 特殊設定 | **clip skip 2**；Euler a 40–60 步或 DPM++ SDE Karras；CFG 4–9（V10 卡片） | 標準 SD 2.1 設定；需確認 epsilon／v-prediction |
| 社群成熟度 | **非常高**；作者宣告永遠免費；V12 為 Final | 低到中；e1 為測試版，品質明顯落後現代動畫 merge |
| 角色一致性後續 | **SD 1.5 生態最完整**：LoRA、IP-Adapter（SD1.5 版）、ControlNet | **弱**：SD 2.x 的 LoRA／IP-Adapter 生態稀少 |
| 畫質預期 | 高（臉／五官穩定度遠優於 base SD 1.5） | 中（優於 base，但落後 A） |
| 主要風險 | 授權開關未核、**NAI 血統法律風險** | 品質不足、SD 2.x 生態薄、.ckpt pickle |

排除（理由）：Anything V3／V4／V5、Counterfeit V2.5／V3.0、AbyssOrangeMix／OrangeMixs——社群與 DMCA 討論普遍指稱含 NAI 洩漏血統；Anything 系另有「Fair AI Public License 1.0-SD」說法互相矛盾。Cool Japan Diffusion（aipicasso）——卡片明文**禁止商用**（例外除外）。NovelAI 官方 V1／V2 權重——非商用。Animagine XL／Illustrious 等——SDXL，本硬體不實用。

## 3. P1-B AI 真人／寫實 shortlist
| 項目 | **候選 A：CyberRealistic**（SD1.5 Final，cyberdelia） | **候選 B：Realistic Vision V6.0 B1 noVAE**（SG161222） |
|---|---|---|
| 正式來源 | HF `cyberdelia/CyberRealistic`；Civitai（作者 Cyberdelia，SD1.5 最終版） | HF `SG161222/Realistic_Vision_V6.0_B1_noVAE`；Civitai `models/4201` |
| 架構 | SD 1.5 | SD 1.5 |
| 大小 | 卡片列 ≈6.3 GB（完整檔）；有 `CyberRealistic_FINAL_FP16.safetensors`（fp16 精簡檔，大小待核，SD1.5 fp16 通常 ≈2 GB） | diffusers 資料夾版（unet／vae 等子資料夾）≈2 GB 級；**另需 VAE** `sd-vae-ft-mse`（≈0.33 GB） |
| VRAM／RAM | 同現行 SD 1.5 | 同現行 SD 1.5 |
| GTX 1650 可行性 | **高** | **高** |
| fp32 速度（估） | 同現行 | 同現行；官方建議解析度較高（如 896×896）在 4 GB 不可行，需維持 768×512 |
| 授權 | **LICENSE_UNVERIFIED**（官方卡片摘錄：CreativeML Open RAIL++-M，**允許商用與非商用、需署名、禁止惡意使用**；但同作者各 repo 標籤不一致：openrail-m／RAIL++-M／cc0-1.0） | **LICENSE_UNVERIFIED**（HF 標 `creativeml-openrail-m`；Civitai 標「Open RAIL-M Addendum」，附加條款未能讀取） |
| 模型商用 | 摘錄顯示允許（需署名） | 未確認 |
| 生成內容商用 | 摘錄顯示允許 | 未確認 |
| 再散布 | RAIL 系允許（附限制）；標籤不一致待核 | 允許（附限制）；Addendum 待核 |
| 額外 VAE | **不需要**（內建 baked VAE） | **需要** sd-vae-ft-mse |
| 接 diffusers | `from_single_file`（本機 sd15 config，離線） | **`from_pretrained` 直接可用**（已有 diffusers 子資料夾） |
| 特殊設定 | DPM++ 2M Karras／Euler a；CFG 5–8；25–30 步 | 卡片建議外接 VAE；B1 為「尚非完整版」 |
| 社群成熟度 | 高；SD1.5 版已「Final」（不再更新＝穩定但凍結） | 非常高；但 V6 B1 為 beta |
| 角色一致性後續 | SD 1.5 生態完整（LoRA／IP-Adapter／ControlNet） | 同左 |
| 畫質預期 | 高（寫實人像） | 高（寫實人像，社群基準之一） |
| 主要風險 | 授權標籤不一致；寫實人像的**肖像／深偽／NSFW 風險**需產品政策 | Addendum 未核；需額外 VAE；beta 版 |

## 4. P1-C 電影感
不另加第三套大型模型：以**真人 checkpoint（P1-B）＋ cinematic Style Profile 詞彙**（`cinematic still, dramatic lighting, film grain…`）＋ 16:9 構圖，並可在 render 階段以 ffmpeg 調色（LUT／曲線，NT$0、無模型）。若之後不足，再評估電影感 LoRA（需另開 DG）。

## 5. 架構建議：Model Router（提案，未實作）
```
使用者選「日系動畫／AI 真人／電影感」（StyleProfile，UX 不露 checkpoint 名稱）
        ↓ style.family
ModelRouter（設定檔路由表：anime→anime_ckpt、realistic／cinematic→realistic_ckpt、其他→sd15）
        ↓ preset（model 來源、scheduler、clip_skip、VAE、license_status、commercial_cleared）
DiffusersImageProvider（同一個 provider、同一套 RuntimePlan／fp32 階梯／evidence）
        ↓ 權重缺 → 退回 base sd15 → placeholder（既有 FallbackImageProvider；evidence 記 route_fallback）
```
- **Provider／Model Agnostic**：路由表是資料，不是程式分支；換模型只改設定與 preset。
- **cache 語意不變**：fingerprint 已含 provider name／model／version → 不同 checkpoint 自然分開快取；`default` 風格仍走 base sd15 → 既有專案 fingerprint 不變。
- **授權閘門**：preset 帶 `license_status`；`LICENSE_UNVERIFIED` 的模型可做內部驗證，但 **FINAL render 標 `commercial_cleared=false`**（或依裁示 fail-closed），避免誤商用。
- **記憶體**：4 GB 一次只載一個 pipeline；同專案通常單一風格，切換成本可接受。
- 下載沿用 Kokoro 模式：`*-download --yes`、只抓 safetensors、寫 provenance（revision、sha256、授權頁快照）。

## 6. 下載前必須完成的核對清單（客戶核准後、下載前執行）
1. 直接開啟原始 HF model card 與 Civitai 授權頁，記錄授權全文與「Sell images／Use on generation services／Sell model／No credit」各開關，存進 provenance。
2. merge 類（MeinaMix）：查公開 merge recipe／NAI 混入檢測結果；無法排除 → 維持 `NAI_LINEAGE_UNVERIFIED`，只做內部驗證。
3. 只接受 `.safetensors`（拒絕 `.ckpt` pickle）。
4. 記錄 revision／sha256；大小與磁碟空間確認。
5. 需要直連 `huggingface.co`、`civitai.com`：本容器目前被網路政策擋，可由客戶在環境設定把這兩個網域加入 Allowed domains，或由 Windows 端核對。

## 7. 來源（搜尋摘錄；原始頁面未能直接開啟）
- Realistic Vision：<https://huggingface.co/SG161222/Realistic_Vision_V6.0_B1_noVAE>、<https://civitai.com/models/4201>、mirror 卡片 <https://huggingface.co/zw89/Realistic_Vision_V6.0_B1_noVAE>
- CyberRealistic：<https://huggingface.co/cyberdelia/CyberRealistic>、<https://huggingface.co/LocalMuseAI/coreml-cyberrealistic-v8-inpaint-fp16>、<https://huggingface.co/Mouserat/CyberRealistic-mnn>
- MeinaMix：<https://civitai.com/models/7240/meinamix>、<https://huggingface.co/Meina/MeinaMix_V11>、<https://huggingface.co/Meina/MeinaMix_V10>、<https://huggingface.co/licyk/sd-model>
- Waifu Diffusion 1.4：<https://huggingface.co/hakurei/waifu-diffusion-v1-4>、<https://scrapbox.io/motoso/Waifu%20Diffusion%201.4>
- Cool Japan Diffusion（排除）：<https://huggingface.co/aipicasso/cool-japan-diffusion-2-1-0-beta>
- NAI 血統爭議：<https://huggingface.co/WarriorMama777/OrangeMixs/discussions/98>、<https://huggingface.co/xyn-ai/anything-v4.0/discussions/2>、<https://x.com/novelaiofficial/status/1942537982658920901>
- Anything V5 授權矛盾：<https://huggingface.co/genai-archive/anything-v5>、<https://civitai.com/models/9409/or-anything-v5>
- Civitai 授權開關說明：<https://education.civitai.com/guide-to-licensing-options-on-civitai/>
- CreativeML OpenRAIL-M 原文：<https://huggingface.co/spaces/CompVis/stable-diffusion-license/raw/main/index.html>
- DreamShaper 8（未入選；授權標籤互相矛盾）：<https://huggingface.co/Lykon/dreamshaper-8>

## 8. 證據補完（Batch 26，客戶裁示：不下載、先補授權／來源／血統）
### 8.1 可達性實測（本容器）
| 網域 | 結果 | 用途 |
|---|---|---|
| `huggingface.co` | ✗ DNS／proxy 403 | model card 原文、YAML license、revision（commit SHA）、檔案清單與 sha256（HF API `/api/models/<id>?blobs=true`） |
| `civitai.com` | ✗ | 授權頁（Addendum 全文）、權限開關、版本 id、檔案 hash（Civitai API `/api/v1/models/<id>`） |
| `civarchive.com`、`web.archive.org`、`archive.ph`、`hf-mirror.com`、`note.com` | ✗ | 備援快照 |
| `github.com` | ✓ | 但 GitHub 存取限本專案 repo，不用於讀他人 repo |
| Web 搜尋 | ✓ | 只能取得原頁摘錄，**無法取得 revision／sha256／授權全文** |

### 8.2 證據可信度
| 候選 | 作者／正式來源 | 授權證據 | Civitai 權限開關 | 血統 | 可信度 | commercial_cleared |
|---|---|---|---|---|---|---|
| MeinaMix | Meina；Civitai `7240`（V12 Final）、HF `Meina/*`（摘錄一致） | HF 標 `creativeml-openrail-m`；Civitai 標「CreativeML Open RAIL-M **Addendum**」（全文未取得） | **未取得**（Civitai 官方說法：開關是「作者的請求」，預設全允許，可逐項關閉） | merge（MeinaPastel、PastelMix、Facebomb、YOZORA 等）；無官方 recipe；同生態大量 merge 混用 Anything／AOM（NAI 血統爭議族群） | **低** | **false**（NAI lineage 無法合理排除） |
| ACertainModel（新增候選） | JosephusCheung；HF `JosephusCheung/ACertainModel` | HF 標 `creativeml-openrail-m`；卡片摘錄**明文允許商用／作為服務／再散布**（需傳遞使用限制） | 不適用（HF 發布） | 作者設計為**非 NAI 的 fine-tune**（自 SD 初始化，非 merge）；未找到第三方檢測 | 中（來源較乾淨；但僅摘錄、無 revision；品質較舊） | 暫 false（原文核對前） |
| Waifu Diffusion 1.4 | hakurei；HF `hakurei/waifu-diffusion-v1-4` | 卡片摘錄：OpenRAIL-M，明文允許商用／服務／再散布 | 不適用 | fine-tune（SD 2.1-base）；致謝 NovelAI（意義未確認） | 中 | 暫 false |
| Mitsua Diffusion（評估後排除） | Mitsua／ELAN MITSUA | 資料最乾淨（CC0／授權資料、U-Net 從零訓練）；但卡片自述畫質很低、無動畫資料；「Mitsua Likes」授權為非商用（例外除外） | — | 最乾淨 | — | 不適用（品質不符 P1） |
| CyberRealistic | Cyberdelia；HF `cyberdelia/CyberRealistic`、Civitai | **確認不一致**：README YAML＝`creativeml-openrail-m`，同頁內文＝「CreativeML Open RAIL++-M」；同作者其他 repo 另見 `cc0-1.0` 標籤；商用：第三方轉檔者稱 Civitai 原頁允許商用與衍生散布，另一彙整站稱非商用（互相矛盾） | 未取得 | 寫實 fine-tune／merge，未見 NAI 相關（NAI 為動畫模型，寫實模型血統風險較低但未排除） | **低～中** | **false** |
| Realistic Vision V6.0 B1 | SG161222；HF、Civitai `4201` | HF 標 `creativeml-openrail-m`；Civitai「Open RAIL-M Addendum」全文未取得 | 未取得 | 同上 | 低～中 | false |

attribution：OpenRAIL-M 本身**無強制署名條款**（只要求傳遞授權與使用限制）；CyberRealistic 卡片摘錄提到「需署名」，條文未取得 → 以「需署名」保守處理。

### 8.3 結論
- 依公開可達來源，**無任一候選能取得 revision、檔案 sha256、授權全文與 Civitai 權限開關** → 證據不完整，維持不下載。
- 需客戶開放網域（環境設定 → Network access → Allowed domains）：`huggingface.co`、`civitai.com`（只讀 API／頁面，不下載權重）。開放後可在一個 Batch 內取得並存檔：HF YAML／README 原文、commit SHA、檔案大小與 sha256；Civitai Addendum 全文、權限開關、版本 id、檔案 hash。
- Anime 建議改為雙軌：**品質軌 MeinaMix**（內部驗證，`commercial_cleared=false`）＋**乾淨軌 ACertainModel**（商用候選，待原文與真機品質驗證）。
