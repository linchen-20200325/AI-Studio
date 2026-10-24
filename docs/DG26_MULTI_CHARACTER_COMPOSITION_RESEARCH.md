# DG-26 Multi-character Composition Route（D-057；研究＋零下載 PoC）

> 起因：S4（D-054／D-056）同 seed 重跑，mapping PASS（`identity_region_map`＋疊圖證明 char_a→left、char_b→right）、兩人分離改善，但 **identity fidelity FAIL**（single-user subjective）。
> 結論方向：不要求 SD1.5 一次同時完成 A／B identity、性別、服裝、位置、背景、構圖；改為**每個角色獨立生成／驗證，再合成到共同 Scene**。
> 限制：NT$0、不下載新模型（含 ControlNet／SAM／RMBG／segmentation）、不新增大型依賴、不用 FaceID／InsightFace、不訓練 LoRA、不 reroll seed、不改 production default。

## 1. 目標流程
`Scene Background` → `Character A isolated generation` → `Character B isolated generation` → `subject extraction / mask` → `placement / scale / depth` → `composite` → `seam / lighting / color harmonization` → `final scene` → human review

## 2. 現有環境盤點（容器實查；不含任何下載）
| 能力 | 現況 | 依據 |
|---|---|---|
| PIL／numpy alpha compositing、mask、feather、resize、placement | ✅ 已是專案依賴（`pillow>=10`、`numpy>=1.26`） | `pyproject.toml` |
| 背景單獨生成 | ✅ 既有 `style-test`（新增案例 `ab_background`） | D-057 |
| 單角色 isolated generation（CyberRealistic） | ✅ 既有 `style-test --checkpoint cyberrealistic_final`（新增 `ab_char_a_isolated`／`ab_char_b_isolated`，角色定義沿用 `two_characters_ab` 同一份結構化設定） | D-057 |
| 既有 IP-Adapter 只用在單角色 | ✅ `--identity` 單一 reference → 單欄（全畫面）mask；已下載權重可重用、無新下載 | `column_bounds(1, w)`、D-054 |
| 去背（subject extraction） | ⚠️ 無 segmentation 模型；零下載替代＝**單色背景鍵控**（邊框估背景色＋與邊框連通的 flood＋收邊＋羽化，numpy 向量化） | `see/core/compose.py` |
| SD1.5 inpainting | ⚠️ 無專用 9-channel inpaint 權重。diffusers 0.41 `StableDiffusionInpaintPipeline` 支援 4-channel UNet（每步把 mask 外的 latents 換回原圖，`num_channels_unet == 4` 分支）→ 可用既有 CyberRealistic，但品質低於專用 inpaint 模型、接縫易明顯；**專案尚未接這條 pipeline** | diffusers 原始碼 `pipeline_stable_diffusion_inpaint.py` |
| img2img | ⚠️ diffusers 有 `StableDiffusionImg2ImgPipeline`（可共用既有元件）；專案尚未接 | 同上 |

## 3. 三條免費路線比較
| | Route A：分開生成＋alpha/mask 合成 | Route B：Inpaint 依序合成 | Route C：Hybrid（A 之後低強度整合） |
|---|---|---|---|
| 做法 | A、B、背景各自生成；鍵控去背；擺位／縮放／深度；羽化、色彩平移、接觸陰影 | 先背景；左 mask 只畫 A；固定 A 後右 mask 再畫 B | Route A 合成後，只對接縫帶做 inpaint／低 strength img2img |
| 每次控制的角色數 | 1（生成時完全不知道另一角色存在） | 1（但在既有畫面上下文中生成） | 1（＋最後整合） |
| Identity fidelity 預期 | 最高：等同單人 S4 | 中：inpaint 區小、臉更小；4-ch 非專用 inpaint 模型品質較差 | 同 A；整合強度過高會重畫臉 → 必須只動接縫 |
| 「貼上感」 | 最高風險（光影、邊緣、比例） | 最低（同一次去噪上下文） | 低（接縫被重新去噪） |
| 修改 A 只重做 A | ✅ 只重跑 A 的 style-test＋重新合成（秒級） | ⚠️ 改 A 後 B 的上下文改變，通常需重做 B | ✅ 重做 A 層＋重跑整合 |
| 零下載 | ✅ | ✅（4-ch 退化 inpaint） | ✅（同 B 機制） |
| 新程式量 | 小（已完成 PoC） | 中（inpaint pipeline＋mask 流程＋provider 參數） | 中（依賴 B 的 inpaint 或 img2img 接線） |
| GTX 1650 4 GB | ✅ 3 次單張生成（每張 ≈ 現行 native 單張；CyberRealistic 實測 ≈638 s，identity 預估再 +10～20%）＋合成 CPU 秒級 | ✅ 記憶體同 txt2img（＋VAE encode）；時間 ≈ 背景＋2 次 inpaint | ✅ 同 A＋1 次 inpaint |
| 主要風險 | 單色背景不一定被遵守、髮絲邊緣、光源不一致 | 非專用 inpaint 權重接縫／內容延續差；兩人臉更小 → fidelity 降 | 強度調不好會洗掉 identity |

## 4. 推薦（總管）
**Route A 先做 Windows 真機 PoC**（零下載、改動最小、最直接回答「單人 identity 是否明顯高於雙人同框」），**Route C 作為第二步**（只修接縫，需先接 inpaint／img2img）。Route B 不優先：它重新把兩角色放回同一去噪上下文、臉更小，且違反「改 A 只重做 A」。

## 5. 已完成 PoC（Route A，D-057）
- 案例：`ab_background`、`ab_char_a_isolated`、`ab_char_b_isolated`（皆可加 `--checkpoint`／`--scheduler`／`--gen-policy native`；角色層可加 `--identity … --ref char_x=…`，單一 reference＝全畫面 mask）。
- `compose-scene --background <stem> --layer char_a=<stem> --layer char_b=<stem> --place char_a=0.3 --place char_b=0.7 [--order …]`：
  - 只收 style-test 產出（technical_valid=true）；**不生成新圖、不改任何 style-test evidence**。
  - 輸出 `workspace/compositions/<name>/`：`composite.png`、`composite.json`、`layers/<id>_mask.png`、`layers/<id>_cutout.png`。
  - provenance：背景與每層的 source stem／image sha256／case／seed／checkpoint／identity reference sha256、去背參數與 `matte_suspect`、placement、scene_box／visible_box、重疊比、深度順序、harmonization 參數。
  - 判定分層：`technical_valid`（自動）；`scene_validated`、`identity_validated[layer]`、`pasted_look` 只由 `compose-review`（single-user subjective）。
  - 改 A＝只重跑 A 的 style-test，再以新 stem 合成；B 層來源與 cutout 位元相同（測試證明）。
- 只做 people；animals／characters／backgrounds 的 layer conditioning **未完成**（Reference Library taxonomy 見 ARCHITECTURE §14.6）。

## 6. 驗收問題（DG-26 最終要回答；待 Windows 真機）
1. 單角色生成 identity fidelity 是否明顯高於雙人 simultaneous S4？
2. 分開生成後 A 是 A、B 是 B（性別呈現、髮型、服裝）？
3. 合成後是否看起來「貼上去」？
4. NT$0、GTX 1650 4 GB 可完成？（預估可；待實測）
5. 修改 A 是否只需重做 A layer？（程式層已證明）
6. 是否值得進 Route C／產品化？

## 7. 會觸發 Decision Gate 的情況（不得自行下載）
- 鍵控去背不足（背景不單純、髮絲）→ **DG-27 去背／segmentation 模型**（候選需逐一查授權；例如部分去背模型權重為非商用授權，須 Gate 判定）。
- 需要姿勢／站位精準控制 → ControlNet Gate。
- 接縫整合需專用 inpaint 權重 → 模型下載 Gate。
