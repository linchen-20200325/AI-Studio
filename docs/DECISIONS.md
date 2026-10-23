# DECISIONS.md — 決策紀錄

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
