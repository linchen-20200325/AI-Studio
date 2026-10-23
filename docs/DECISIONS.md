# DECISIONS.md — 已裁示事項（append-only；每筆：ID、日期、決策、理由、範圍；superseded 不刪除）

## 狀態索引（仍有效／已取代）
| ID | 主題 | 狀態 | 可逆 |
|---|---|---|---|
| D-001～D-008 | 專案名、授權、Phase 0 TTS=espeak、LLM=Mock、ffmpeg 合成、字幕、影像規格 | 有效（Phase 0 基線） | 可逆 |
| D-009 | 使用者裁示紀錄（Free First／架構） | 有效 | — |
| D-010/D-011 | Web UI 最小設計；DG-5 限可信任區網無登入 | 有效 | 可逆 |
| D-012 | edge-tts 連網驗證嘗試 | **superseded by D-014** | — |
| D-013 | main 快進與 repo 實況 | 有效 | — |
| D-014 | DG-6 不採用 edge-tts（adapter 保留） | 有效 | 可逆 |
| D-015 | DG-7 預設分支 main、建議 Private | 有效，使用者手動部分未完成 | 可逆 |
| D-016/D-019 | 最小 CI；setup-ffmpeg | 有效 | 可逆 |
| D-017/D-018 | AI Image 盤點；DG-8 採 SD 1.5 | 有效 | 可逆（換模型需新 DG） |
| D-020 | cp950 subprocess、NaN 偵測、fp32 VAE | 有效 | 可逆 |
| D-021 | 黑圖快取／內容驗證／evidence／version 3 | 有效 | 可逆 |
| D-022 | fp32 升級用 fp16 檔 upcast（不下載 fp32） | 有效 | 可逆 |
| D-023 | 降級 fallback 快取自動重試；Fallback info 穩定 | 有效 | 可逆 |
| D-024 | Phase 1 COMPLETE；Phase 2 待裁示 | 有效 | — |
| D-025 | GitHub＝長期記憶 SSOT；canonical 文件；Model/Effort/Token Gate；Windows 互動規則 | 有效 | 治理，可修訂（需裁示） |
| D-026 | DG-9 TTS 候選研究結論（Project AI 建議 Kokoro；待客戶裁示） | 研究紀錄，裁示未下 | 可逆 |
| D-027 | DG-9 裁示：Kokoro-82M v1.1-zh **Candidate Validation Approval**（非 Final Provider Approval）；授權下載 ≈330 MB 權重做 Windows 真機驗證 | 有效 | 可逆 |
| D-028 | Kokoro E2-1 真機技術驗證成功（候選仍非最終）；zm_010 為 Kokoro 內部首選候選（不鎖死）；zf_001 口音＝已知限制；Voice Selection 產品需求入規格；DG-14 預設 voice 裁示 | 有效 | 可逆 |
| DG-2 | Ollama 暫緩 | 有效（Phase 2 候選重開需新裁示 DG-10） | — |

# DECISIONS.md（原文） — 決策紀錄

格式：日期 / 決策 / 理由 / 替代方案 / 影響。

## D-001 2026-10-22 專案名稱與 repo
- 決策：專案名 `see`，Python 套件名 `see`，repo = `linchen-20200325/AI-Studio`。
- 開發分支：`ccr-2968bce1-ym4kkc`（指派分支）。repo 原本無任何 commit，`main` 尚不存在；是否以此分支建立 `main` 由使用者裁示。

## D-002 2026-10-22 參考專案授權
- `Hao0321/video-autopilot-kit` 為 MIT License（Copyright (c) 2026 Hao0321 Studio）。
- 決策：**不複製任何程式碼**，只借鏡思路（見 ARCHITECTURE §10）。因此無需附帶其 LICENSE。
- 其渲染端 Editkin 為 GPL-3.0 且為 Windows 桌面程式，不納入。

## D-003 2026-10-22 Phase 0 TTS 選擇
- 本環境可用：`espeak-ng`（apt 安裝，LOCAL_FREE，Mandarin `cmn` 語音，品質低）。
- `edge-tts`（FREE_TIER，不需 key）在本環境被網路政策擋下（DNS 解析失敗），實作為 optional provider 但預設不啟用。
- 決策：`SEE_TTS_PROVIDER=auto` → 順序 espeak → silent。`silent` 為靜音 + 字數估時長，保證離線 pipeline 永遠可跑。
- 不自動 fallback 到任何 PAID TTS（PROJECT_RULES §4）。

## D-004 2026-10-22 Phase 0 LLM
- 環境無本機 LLM（無 Ollama / 權重），無免費 API。
- 決策：`MockLLMProvider` 以確定性規則（句號／驚嘆號／問號切句、按字數分景、3–12 秒/景、目標 30–60 秒）產出 `ScriptDraft` / `StoryboardDraft`。
- 介面 `LLMProvider.complete_json(LLMRequest) -> BaseModel` 已為真正 LLM 預留；接 Ollama 時只需新增 provider。

## D-005 2026-10-22 影片合成策略
- 兩段式：每景先產 `clip.mp4`（zoompan Ken Burns + 旁白 + 燒錄字幕），再以 `xfade` + `acrossfade` 組裝。
- 理由：每景 clip 可 fingerprint 快取，修改單一 Scene 不重做其他 Scene；組裝階段成本低可每次重做。
- 替代方案（單一 filter_complex 一次合成）被否決：無法做 per-scene 快取。
- 限制：`cut` 轉場以極短（0.08s）fade 模擬；字幕在轉場重疊區會跟著淡入淡出。

## D-006 2026-10-22 字幕
- 以 libass `subtitles` filter 燒錄 SRT，字型用 fontconfig 偵測 CJK 字型（本環境：WenQuanYi Zen Hei）。
- 切句：按中文標點切，每行上限 18 字，時間按字數比例分配在旁白實際時長內。

## D-007 2026-10-22 影像規格
- 預設 1280×720 @ 25fps、H.264 yuv420p、AAC 44.1kHz stereo。Placeholder 圖以 1920×1080 產生再縮放以減少 zoompan 抖動。

## D-008 2026-10-22 不做的事（放 BACKLOG）
- 付費 API、Lip Sync、真正 AI Video、登入系統、NAS 部署、GPU Worker、Web UI。

## D-009 2026-10-22 裁示紀錄（使用者）
- DG-1：以 `026206c` 建立 `main`（已完成，local/remote 一致）。
- DG-2：暫緩 Ollama／大型本機 LLM；不下載模型；保留 LLMProvider 架構。
- DG-3：edge-tts 僅在可連網環境驗證；必須 FREE_TIER／零 key／零付費。本容器 DNS 無法解析 `speech.platform.bing.com`，尚未實測。
- DG-4：Web UI 採 FastAPI + 簡單手機友善單頁。

## D-010 2026-10-22 Web UI 最小設計
- 無框架前端（單一 index.html，vanilla JS 輪詢），避免建置鏈與相依。
- `BackgroundRunner`：ThreadPoolExecutor(1) 作為 Phase 0.5 的 queue 替身；介面只有 submit/status，為 NAS queue 預留。
- 影片以 FileResponse 直出並支援 Range；不做轉碼或串流伺服器。
- 「影片長度」設定以旁白語速（0.85/1.0/1.2）實作：總長由字數決定，語速是唯一誠實可調的長度參數；不自動刪改原文。
- 幣別改為 TWD 預設（使用者在台灣），顯示 `NT$0`。
- 已知：headless Chromium 無 H.264 解碼，故 Playwright 煙霧測試只驗證頁面流程與 206 Range，不驗證瀏覽器內播放；手機 Safari/Chrome 皆原生支援 H.264/AAC。

## D-011 2026-10-22 DG-5 裁示：Web UI 第一版限可信任區網
- 暫不開 Internet、不做帳號／OAuth／公開 tunnel。Server 預設不得無意間公開：`python -m see.ui` 只綁 127.0.0.1，`--lan` 才綁 0.0.0.0 並印出警告。
- 未來 NAS 正式部署／遠端使用時另開 Access Control Decision Gate。

## D-012 2026-10-22 edge-tts 連網驗證結果
- 本容器網路政策無法解析 `speech.platform.bing.com`（DNS 失敗），**無法在此環境完成驗證**；需在可連網機器執行 `SEE_TTS_PROVIDER=edge python -m see.app.cli run examples/story_tiny.txt`。
- 授權：`edge-tts` 7.3.1 為 LGPLv3；本專案僅以 optional、延遲 import 使用，不打包、不修改其原始碼，相容。
- 疑義（依裁示停止並回報）：該套件呼叫的是微軟 Edge「大聲朗讀」非官方端點，服務條款未明示允許第三方程式使用，可用性與合規性無保證。因此維持：optional、非預設、不移除 espeak／silent fallback；是否採用待使用者裁示（DG-6）。

## D-013 2026-10-22 main 快進與 repository 實況
- `main` 以 fast-forward 指向已驗證治理版本 `1e42a81`（Recovery Verification：tree clean、remote 未漂移、42 passed）。
- GitHub 實況：`linchen-20200325/AI-Studio`，**visibility = public**；GitHub 預設分支仍是 `ccr-2968bce1-ym4kkc`（非 main）。兩者皆為 repo 設定，非程式問題，由使用者決定是否改為 private / 將預設分支改為 main。

## D-014 2026-10-22 DG-6 裁示：不採用 edge-tts
- 保留 optional adapter（`see/providers/tts/edge.py`），不再投入時間處理其非官方端點；espeak／silent fallback 保留。未來另開 TTS Provider Decision Gate。

## D-015 2026-10-22 DG-7 裁示：預設分支改 main、建議改 Private
- 本 session 的 GitHub 工具無修改 repo 設定的權限／工具（無 gh CLI，MCP 無 update-repository），**不繞過權限**，由使用者在 GitHub 手動操作：
  - Settings → General → Default branch → 切換為 `main`。
  - Settings → General → Danger Zone → Change repository visibility → Private。
- 改 Private 後需確認 ChatGPT GitHub connector 與 Claude GitHub App 仍被授權此 repo。

## D-016 2026-10-22 最小 CI
- `.github/workflows/ci.yml`：ubuntu-latest、Python 3.12、apt 安裝 ffmpeg／espeak-ng／fonts-wqy-zenhei、`pip install -r requirements.txt`、`check-env`、`pytest`。
- 不使用任何 secret；`permissions: contents: read`；不呼叫外部／付費 AI Provider（測試只用 Mock／Placeholder／espeak／silent）。
- 觸發：push 到 `main` 與 `ccr-*`、pull_request、手動。

## D-017 2026-10-22 AI Image Provider Phase — 盤點與骨架（未下載模型）
- 盤點結果與三方案見 `docs/AI_IMAGE_PROVIDER_PLAN.md`：A 推薦 FLUX.1-schnell（Apache-2.0）、B 低需求 SD 1.5（OpenRAIL-M）、C 付費 stub（永不連線）。
- 不採用：FLUX.1-dev、SDXL-Turbo、Sana（非商用授權）。SD 3.5 Medium 因 Community License 營收門檻列備選。
- 不引入 ComfyUI：diffusers in-process，使用者只操作 AI-Studio。
- 實作：`see/core/hardware.py`（能力偵測 + 建議）、`DiffusersImageProvider`（`local_files_only=True`，缺權重即拒絕，絕不自動下載）、`FallbackImageProvider`、`PaidImageProviderStub`、`SEE_IMAGE_PROVIDER=auto`、CLI `hardware`、API `/api/hardware`。預設仍為 `placeholder`。
- 停手點：下載模型需使用者明確同意；方案 A/B 擇一需使用者先貼回 `python -m see.app.cli hardware` 結果（DG-8）。

## D-018 2026-10-22 DG-8 裁示：採方案 B（Stable Diffusion 1.5）
- 實機：Windows、GTX 1650 4 GB、RAM 64 GB、磁碟 2.7 TB。預設 preset 改為 `sd15`；低 VRAM 策略見 `docs/AI_IMAGE_SD15_WINDOWS.md`。
- 模型與 repo 分離：`SEE_MODELS_DIR`（預設 `./models`）整個 gitignore，另加 `*.bin`、`huggingface/`；下載器在模型資料夾再寫 `.gitignore`。
- 下載是人工單步：`python -m see.app.cli image-download --preset sd15 --yes`（無 `--yes` 只印計畫）。
- `image_prompt_en` 路徑：`see/core/prompting.py` 關鍵詞對照（Mock／fallback）；Scene 新增 `image_prompt_en`、`negative_prompt`；Orchestrator 以 `effective_image_prompt` 餵 ImageProvider。真正 LLM 接上後可直接產生。
- 核心 pipeline 未綁 SD 1.5：仍透過 `ImageProvider`／registry `auto`；Placeholder 永遠保留為 fallback。

## D-019 2026-10-22 CI run 被 cancelled 的紀錄
- `16fd107`（分支 run）與 `ec669e7`（分支與 main 兩個 run）狀態為 cancelled，非 failed；同 SHA 的 main run 在 `16fd107` 成功。本 session 以 GitHub App 身分 re-run／dispatch 皆 403。
- 根因（`bc5f568` 兩個 run 的 jobs API）：`System packages` 步驟 apt-get 卡住約 20 分鐘，被 job `timeout-minutes: 20` 取消 → GitHub 顯示 cancelled。成功的 run 該步驟只需 1 分鐘，屬 apt 鏡像偶發卡死。
- 修正一：該步驟加非互動、timeout、重試、`timeout-minutes: 8`（`ca7d286` 綠）。
- 2026-10-23 `495ef83` 再紅：日誌顯示 Azure apt 鏡像下載 ffmpeg 相依（75 MB）速度約 50 KB/s，8 分鐘逾時 → failure。根因是 runner 鏡像，不是程式差異。
- 修正二：ffmpeg 改用 `FedericoCarboni/setup-ffmpeg@v3`（MIT，取 GitHub release 的靜態 GPL build，含 libass）；espeak-ng／字型改為 best-effort（`continue-on-error`），缺少時 espeak 測試自動 skip、字幕用預設字型。CI 不再依賴 apt 鏡像速度。隨後一次紅為 requirements 漏列 `numpy`（本容器預裝掩蓋），已補；`3597e1e` success。

## D-020 2026-10-23 Windows 真機第一次 SD 1.5 執行：root cause 與修正
- 實機：Windows、Python 3.12.10、GTX 1650 4 GB、PyTorch 2.14.1+cu126、CUDA 12.6、diffusers 已裝、模型 `D:\ai-models\sd15`（2.13 GB）。模型載入 100% 成功 → 模型未損壞，不重新下載。
- **真正 failure**：`UnicodeDecodeError: 'cp950' codec can't decode byte 0x89`——我們的 `subprocess.run(text=True)` 在 Windows 以 locale（cp950）解碼 ffmpeg／espeak 的 UTF-8 輸出，reader thread 丟例外，pipeline 中斷。修正：`see/core/proc.py` `run_text()` 以 bytes 模式執行並 UTF-8 `errors=replace` 解碼；所有 subprocess 呼叫（ffmpeg、ffprobe、espeak、fc-list、nvidia-smi 等）改走此函式；CLI／UI 入口 `ensure_utf8_stdio()`。
- **`RuntimeWarning: invalid value encountered in cast`**：numpy 把含 NaN 的浮點影像轉 uint8 的警告 → 代表 fp16 推理出現 NaN，產物會是黑圖。GTX 16xx（Turing、無 tensor core）在 fp16 跑 SD 1.5 VAE／UNet 出 NaN 是已知現象（社群對策 `--no-half-vae` / `--no-half`）。修正：生成改 `output_type="np"` 並以 `is_numeric_failure()` 檢查 NaN／全黑；GTX 16xx 預設 VAE fp32（`vae_fp32`）；仍失敗 → 整個 pipeline fp32 + CPU offload（4 GB 可容納 SD 1.5 fp32 UNet 3.4 GB 單元件）；再失敗才 ProviderError → Fallback 退回 Placeholder。
- **torchvision warning**：`CLIPImageProcessor requires torchvision` 來自 feature_extractor，只有 safety_checker 用得到；已 `feature_extractor=None`，**不新增 torchvision 依賴**。
- 4 GB 安全策略（fp16、slicing、offload、≤512）與 Placeholder fallback 全部保留；OOM 降級與數值降級為兩條獨立階梯。
- 回歸測試：`tests/test_windows_regressions.py`（7 項）。

## D-021 2026-10-23 Windows 真機 SD 1.5「純黑 PNG 卻回報成功」：root cause 與修正（Batch 9）
- 實機事實：GTX 1650 4 GB、torch 2.14.1+cu126、`RuntimePlan(cuda, float16, low_vram, cpu_offload, max_side=512, vae_fp32=True)`、CLI 正常結束、`providers.image.name=diffusers-sd15`，但 `scene_001/image.png` min=max=mean=0。
- 四個假設逐項驗證結果（以 `02fac28` 程式碼 + diffusers 0.41.0 原始碼）：
  1. **cache 重用不驗內容 + version 未 bump（主因，已確認）**：`SceneManifest.valid()` 只比 fingerprint 與檔案存在；`diffusers-sd15` 的 `ProviderInfo.version` 自 Batch 7（`1e81668`）起為 `"2"`，Batch 8 修 NaN 時未 bump → 第一次真機（舊 fp16 路徑）留下的黑圖 + manifest，在第二次 `run --project-id sd15test` 被當成有效快取直接重用，新版生成程式碼根本沒被呼叫，pipeline 因而「成功」。
  2. **`providers.image.name` 不是生成證據（已確認）**：`FallbackImageProvider.info` 回傳第一個「可用」候選；快取重用時任何 provider 都沒被呼叫，顯示 `diffusers-sd15` 只代表它可用。
  3. **`is_numeric_failure()` 只驗生成當下 ndarray（已確認）**：存檔後、快取重用時、Fallback 收到候選結果時都沒有再驗。
  4. **VAE fp32 + fp16 latents dtype（已確認為潛在 bug，非本次黑圖主因）**：diffusers 0.41.0 `StableDiffusionPipeline` 直接 `vae.decode(latents / scaling_factor)`，不 cast dtype；`vae_fp32=True` 時會丟 dtype 不匹配例外 → ProviderError → Placeholder（會是漸層圖而非黑圖，故非主因，但下一次真機必踩）。
- 修正（全部 LOCAL_FREE、Provider Agnostic、4 GB 策略與 Placeholder fallback 不變）：
  - `see/core/image_qa.py`：唯一的影像內容檢查（全黑 max≤5／單色平面 std<1／無法解碼／缺檔）。
  - Orchestrator：快取重用前驗證內容，黑圖→刪檔重生並記 `reasons["image"]`；生成後再驗，任何 provider 交出黑圖 → 刪檔、manifest 移除、`RenderError`（pipeline 不得回報成功）；clip fingerprint 加入圖檔 sha256（圖內容變 → clip 必重做）。
  - `DiffusersImageProvider`：version `"3"`（舊 fingerprint 全部失效，強制重生）；`output_type="latent"` 後自行 `latents.to(vae.dtype)` decode（修 4.）；latents NaN 直接視為數值失敗；存檔後重開驗證，黑圖刪檔 raise；`ImageResult.meta` 記 initial/final plan、attempts、numeric/oom downgrade、elapsed、image_stats；logging 輸出每次嘗試。
  - `FallbackImageProvider`：候選輸出經 `image_defect` 驗證，黑圖視同失敗換下一候選；`meta.generated_by / fallback / fallback_from`；`last_generated_by`。
  - Evidence：`AssetRecord.meta` 入 manifest；CLI `run` 輸出 `image_evidence[]`（generated_by / regenerated / reason / final_dtype / final_vae_fp32 / numeric_downgrade / oom_downgrade / fallback / attempts / image_stats）與 stderr 每景 rebuilt/reused/reasons；UI `/api/projects/{id}` 每景 `image_meta`，Scene 卡顯示「圖：生成者 · dtype · 降級 · fallback · 快取」。
- 回歸測試：`tests/test_image_integrity.py`（10 項）+ CLI/Web API 斷言；共 83 passed。
- 下一次真機驗證只需一次 `git pull` + 同一條 `run` 命令：version bump 保證 image 重生，`image_evidence` 會寫明實際發生了什麼。

## D-022 2026-10-23 fp16 numeric failure → fp32 升級時「找不到 fp32 權重」：root cause 與方案（Batch 10）
- 實機（Batch 9 程式）：黑圖 QA 生效；attempt 1 `float16 + vae_fp32` 仍 NaN/黑 → 升級 full fp32 → `OSError: no file named model.safetensors … text_encoder` → ProviderError → Placeholder（5 景皆如此，evidence 正確顯示 `generated_by=placeholder-image`、`fallback_from`）。
- Root cause（程式碼驗證）：`_load()` 只在 `plan.dtype=="float16"` 時傳 `variant="fp16"`；`image-download` 的 `allow_patterns` 只抓 `*.fp16.safetensors`。fp32 plan 不帶 variant → diffusers 去找無 variant 的 fp32 檔 → 不存在。runtime 階梯與下載內容不一致。
- 方案比較：
  - A. 補下載 fp32 權重：官方 repo 無 variant 檔 unet 3.44 GB + text_encoder 0.49 GB + vae 0.33 GB ≈ **4.3 GB** 額外下載（CreativeML OpenRAIL-M，同授權）。可行但非必要。
  - B.（採用）**同一份 fp16 權重以 `dtype=float32` 載入**：diffusers `load_model_dict_into_meta` 會把浮點參數 cast 成傳入 dtype（0.41.0 原始碼確認），text_encoder（transformers）同理。fp16 儲存精度不是 NaN 成因（成因是 fp16 計算時 activation 溢位），等同 A1111 `--no-half` 對 fp16 ckpt 的做法。**零下載、可逆、Free First。**
  - C. 其他 LOCAL_FREE 數值手段（upcast_attention、部分層 fp32）：在 SDPA attention processor 下不保證生效，且仍是 fp16 UNet；列為 BACKLOG 備案，不採用。
- 實作：`pick_variant()` 依各元件實際存在的 variant 決定（fp16 齊→fp16；僅 fp32 檔→None；不齊→ProviderError 指向 `image-download`）；`load_kwargs()` 純函式，variant 不再綁 dtype；diffusers ≥0.36 用 `dtype=`（以 `_resolve_dtype` 判斷）消除 `torch_dtype` FutureWarning；`vae_fp32` 改為單獨以 fp32 載入 VAE（消除 `.to()` 警告，失敗退回 `.to()`）；同程序內數值失敗後的階梯 `_floor` 延續到下一景（不再每景 fp16→NaN→fp32 重跑）；evidence 新增 `weights_variant`、`fp32_source`、`plan_origin`；`image-download` 對已存在模型印出各元件 variant 與 fp32 策略。
- 4 GB 可行性：fp32 UNet 3.44 GB 以 `enable_model_cpu_offload` 逐元件上卡，512×512 + attention/VAE slicing 預期可跑；若 OOM 由既有 memory 階梯降到 384。Placeholder 永遠是最後一層，但 **placeholder 不算 SD 1.5 真機成功**（evidence `generated_by` 必須是 `diffusers-sd15`）。
- 回歸測試：`tests/test_image_integrity.py` +3（fp16-only 權重供 fp32 plan 使用、variant 完整性、階梯延續）；共 86 passed。

## D-023 2026-10-23 fallback 產物被當成有效快取；`regen` 語意（Batch 11）
- 實機：Scene 002–005 已由 `diffusers-sd15` fp32 生成成功（Batch 10 真機證據）；Scene 001 仍是舊 placeholder，`regen sd15test scene_001` 後下一次 `run` 仍 `reused=['image', …]`，evidence 為舊 fallback 資料。
- `regen` 現行語意（程式碼驗證）：`regenerate_scene()` 刪除該景 manifest.json（唯一快取真相）→ 立刻重建四種資產 → 重新組裝 preview。本機重現：regen 確實重寫 manifest，下一次 run 合法 reuse regen 的結果；**不需要 asset 參數**，語意正確。使用者看到「無輸出」與舊 evidence 無法在此容器重現；最可能是 regen 在 Batch 10 `git pull` 前執行（產物＝同樣的 fallback placeholder），之後的 run 當然 reuse。
- **真正的設計缺口（程式 bug）**：fallback 產物（placeholder）以**首選 provider**（diffusers-sd15）的 fingerprint key 寫入 manifest；之後首選 provider 修好／可用時，fingerprint 不變、圖也不黑 → 永遠 reuse，pipeline 永遠不再嘗試真正的生成。這正是 scene_001 卡住的機制，與 regen 是否執行無關。
- 另一個相關 bug：`FallbackImageProvider.generate_image` 成功後把 `_active` 改成實際生成者，使 `info.name` / `fingerprint_key` 在同一次 run 內漂移（一景 fallback 後其餘景的 key 變成 placeholder 的）。
- 修正：
  - Orchestrator 快取重用多一條規則：`cached.provider != 首選 provider`（Fallback 目前第一個可用候選）→ 視為「降級產物」，刪除並重試真正生成；首選不可用時（無權重）placeholder 快取仍合法，不 churn。manifest meta 新增 `degraded`。
  - Fallback `info` 穩定指向首選可用候選，不再隨生成結果漂移；實際生成者一律看 `meta.generated_by` / `last_generated_by`。
  - `regen` CLI 於 stderr 印出該景 image evidence（generated_by / final_dtype / numeric_downgrade / fallback）。
- 不需手動刪 workspace／manifest／PNG：下一次 `run` 會自動重試 scene_001。
- 回歸測試 +3：fallback 產物在首選修好後被重試（只重做該景 image+clip，其他景 reuse，再跑不 churn）；首選不可用時 placeholder 快取保留；regen 只重做指定景、clip fingerprint 隨圖內容失效、下一次 run 沿用。共 89 passed。

## D-024 2026-10-23 Phase 1 正式 COMPLETE；Phase 2 方向待裁示
- 完成條件（STATE／BACKLOG 定義：五景 `generated_by=diffusers-sd15`、無黑圖、無 placeholder、NT$0）於 GTX 1650 真機以 `ec8ff77` 程式達成，證據見 `PHASE1_EVIDENCE.md`。本輪無 production 行為變更，只有文件同步。
- Phase 2 建議排序見 BACKLOG「Phase 2 建議」；第一目標建議為自然中文 TTS（LOCAL_FREE）。涉及新模型下載／方向選擇 → 停手條件，等使用者裁示後開工。

## D-025 2026-10-23 客戶裁示：GitHub 為唯一長期專案記憶 SSOT；canonical 文件架構；Model／Effort／Token Gate；Windows 互動規則（Batch 13）
- 裁示原文要旨：«從現在開始，AI-Studio 的長期專案記憶以 GitHub 為唯一 SSOT。ChatGPT Memory、Claude Memory、舊對話都不是正式專案儲存層。新的 ChatGPT 與 Project AI 對話必須能只讀 GitHub 就重建足夠完整的專案狀態並繼續工作。»
- 落實：`PROJECT_RULES.md` §10 停手條件補齊（任何新模型下載、大量磁碟、新硬體、forced provider、產品方向）；新增 §12 GitHub Memory Rule／Knowledge Persistence Check／文件責任／完成度定義、§13 Model-Reasoning-Token Efficiency Gate、§14 Windows Customer Interaction。新增 `docs/PROJECT_STATE.md`（現況快照）；`docs/STATE.md` 降為相容指標；`docs/HANDOFF.md` 改為導航頁；角色專用 handoff 保留為補充。
- 客戶協作偏好（會影響專案協作者）：繁體中文；極簡回報；Decision Gate 才打擾客戶；Windows 一次一個指令；安全工作靜默自主巡航、整批完成再回報；每批標示 Model／Mode／Effort；Minimum Sufficient Effort；對話切換前 GitHub 化；不依賴 AI Memory。
- 範圍：治理層；可逆（修訂需新裁示並記錄）。不涉及 production 行為。
- Phase 2：**未開始**。待裁示 DG-9（第一目標＝自然中文 TTS 候選研究；任何模型下載需同意）。

## D-026 2026-10-23 DG-9 研究紀錄：自然中文 TTS 候選（尚未裁示）
- 比較表與理由：`docs/TTS_PROVIDER_PLAN.md`。排除不可商用權重（IndexTTS、F5-TTS、Fish Speech）；大模型（CosyVoice2、GPT-SoVITS）列為未來 DG。
- Project AI 建議：Kokoro-82M v1.1-zh（Apache-2.0、CPU、≈330 MB、100 中文語者，可對應 `scene.voice`）。備選 MeloTTS（MIT，≈1.5 GB）、Piper zh_CN-huayan（≈60 MB，權重授權待確認）。
- 本輪未下載模型、未改 production。客戶裁示後補記 D-027。

## D-027 2026-10-23 DG-9 裁示：Kokoro-82M v1.1-zh 候選驗證核准（Candidate Validation Approval）
- 使用者裁示：同意採 Kokoro-82M v1.1-zh 為 Phase 2 第一個自然中文 TTS **候選**，授權下載約 330 MB 權重於 Windows 真機驗證。
- **本裁示性質＝Candidate Validation Approval，不是 Final TTS Provider Approval。** 技術成功不得直接宣布 Kokoro 為最終 TTS；真機驗證後停在新 Decision Gate（DG-13），由客戶依聽感裁示：正式採用／繼續調整／測試第二候選／放棄。
- 實作約束：依 provider-agnostic 架構加入 `kokoro` provider；保留既有 fallback（kokoro → espeak → silent），不綁死；LOCAL_FREE、NT$0、不用付費 API；不改 SD 1.5 成功路徑；不自行新增其他大型模型；下載僅限已核准之 v1.1-zh ≈330 MB；下載來源／版本／實際大小／hash／provenance 必須記錄（`PHASE2_EVIDENCE.md`）；自動測試通過後才進真機。
- 真機驗證至少確認：中文發音正確、自然度、大陸口音明顯度、不同 voice 差異、生成速度、CPU／RAM／VRAM、與 GTX 1650＋SD 1.5 工作流共存、narration duration 正確進影片流程、fallback／fail-closed 正常。
- Windows 操作：一次一個 action／command（§14）。

## D-028 2026-10-23 Kokoro 候選真機驗證紀錄與 Voice Selection 規格
- 事實：Kokoro-82M v1.1-zh 於使用者 Windows（CPU）技術驗證成功（`PHASE2_EVIDENCE.md` E2-1）：四 voice 皆可生成、無 fallback、NT$0、provenance 已記錄。
- **「Kokoro 成為最終 TTS provider」尚未核准；D-027 仍屬 Candidate Validation。** 五景 pipeline 整合（E2-2）後才進 DG-13 聽感裁示。
- `zm_010`：依使用者主觀聽感作為 **Kokoro 內部首選候選**，可用 `--voice zm_010`／`SEE_TTS_DEFAULT_VOICE` 指定；**不鎖死、不寫成程式永久預設**（程式未設定時仍為既有行為：第一個 zf_*）。永久預設 voice 屬產品語意 → **DG-14**。
- `zf_001` 明顯大陸口音＝已知使用者體驗限制，記入 voice 型錄 `accent_note`（標明為使用者聽感，非客觀排名）。
- 產品需求（入 BACKLOG 規格）：使用者必須能「角色 → 選 voice → 試聽 → 調語速 → 確認 → 才進正式生成」。約束：provider-agnostic（`VoiceInfo` + `TTSProvider.list_voices()` 介面已加，Batch 16）；未來其他 LOCAL_FREE／台灣中文 provider 可進同一 Voice Selector；UI 顯示可讀名稱／性別／聲線 metadata 而非只 id；voice 選擇依角色保存；保留 fallback／fail-closed／evidence；不得影響 SD 1.5 Phase 1 路徑。UI 形式屬產品決策 → **DG-15**。
