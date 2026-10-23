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
| D-029 | DG-13 裁示 A：正式採用 Kokoro 為「目前 Phase 2 LOCAL_FREE 中文 TTS provider」；Provider Agnostic 保留；zm_010 非永久預設；DG-14／DG-15 獨立 | 有效 | 可逆（換 provider 需新 DG） |
| D-030 | Voice Selection 非 UI 實作：角色 voice／語速、優先序、試聽、確認閘門（使用角色時 Final 需確認） | 有效 | 可逆 |
| D-031 | DG-16 裁示 A：Phase 2 第二目標＝Audio Layer（BGM／SFX／ducking）；第一版程序生成、NT$0、無外部素材；預設 audio=null（開啟與否 → DG-17） | 有效 | 可逆 |
| D-032 | E2-3 真機 OK（BGM／ducking）；BGM 預設維持 null 延後到完整產品流程/UI；產品流程確立；Style Profile／Character Consistency／Lip-sync foundation（介面與 schema，無模型） | 有效 | 可逆 |
| D-033 | DG-18 裁示 A：5 種非 default Style Profile Windows 真機出圖驗收（不改 Style 內容、不下載、不研究 IP-Adapter／LoRA／Lip-sync） | 進行中（順序依 D-034 調整） | 可逆 |
| D-035 | **E2-4 暫停於 RCA**：`technical_valid`≠scene／style 通過（分層驗收）；主要嫌疑＝生成解析度 512×288（pipeline）；診斷參數 opt-in、預設不變；DG-20 延後到真機 A/B 之後 | 有效 | 可逆 |
| D-034 | **產品視覺方向**：P1＝日系動畫＋AI 真人／寫實＋電影感；P2＝3D；P3＝兒童繪本等。picture_book 技術 PASS／主觀 FAIL，不重跑不修正；E2-4 目的改為判斷 SD1.5 是否足以支撐 P1 | 有效 | 可逆 |
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

## D-029 2026-10-23 DG-13 裁示：A — 正式採用 Kokoro 為目前 Phase 2 LOCAL_FREE 中文 TTS provider
- 依據：`PHASE2_EVIDENCE.md` E2-1／E2-2（五景 kokoro-tts、CPU、無 fallback、與 SD 1.5 GTX 1650 共存、NT$0）。D-027 的 Candidate Validation 至此升級為 **Provider Approval（目前）**。
- 嚴格保留：(1) Provider Agnostic，核心不得綁死 Kokoro（仍經 `TTSProvider`／`ProviderRegistry`，`auto` 鏈 kokoro→espeak→silent）；(2) 未來可新增／替換更適合台灣中文的 TTS provider（需新 DG）；(3) `zm_010` 僅為目前人耳偏好 voice candidate，**不**因本裁示成為永久產品預設；(4) DG-14 永久預設 voice 獨立裁示；(5) DG-15 Voice Selector UI 獨立裁示。
- 效果：BACKLOG「自然中文 TTS provider（LOCAL_FREE）」關閉；Phase 2 第一目標達成；下一目標依 BACKLOG Phase 2 排序（BGM/SFX、Voice Selection 非 UI 部分、LLM 規劃）由後續 Batch 評估，涉及模型下載／素材授權者需新 DG。

## D-030 2026-10-23 Voice Selection 非 UI 部分（Batch 19；依 D-028 規格，Project AI 自主實作）
- 資料：`Project.characters: dict[id, CharacterVoice{display_name, voice_id, provider(資訊), speed, confirmed, confirmed_at}]`；`Scene.narrator_id`、`Scene.speech_speed`。舊專案無新欄位 → 行為與 fingerprint 不變（測試保證）。
- 優先序：voice＝`scene.voice`（非 default）> 角色 voice > provider 預設；語速＝scene > 角色 > project。未知 narrator fail-closed。
- 流程：設定角色 → 試聽（`preview_voice`：單句合成到 `workspace/voice_previews/`，不寫 manifest；PAID 一律拒絕）→ 人工確認 → **使用角色的專案 Final render 需全部角色已確認**（未使用角色者不受影響）。任何角色變更清掉 confirmed、相關景回 DRAFT。
- 介面：CLI `character`、`voice-preview`、`set-scene --voice/--narrator/--speed`；Web API `GET /api/voices`、`POST /api/voices/preview`、`GET /api/voice-previews/{id}.wav`、`POST /api/projects/{pid}/characters/{cid}`、`…/confirm`。**HTML UI 未改（DG-15）**；預設 voice 未鎖（DG-14）。
- espeak 作 fallback 時遇到其他 provider 的 voice id（如 zm_010）改用語言預設聲，不直接掉到 silent。

## D-031 2026-10-23 DG-16 裁示 A：Audio Layer（BGM／SFX／ducking）— Batch 20 實作
- 客戶裁示限制：NT$0；不下載 AI 模型；不用 PAID；第一版以程式生成測試 BGM／SFX；Provider／Source Agnostic；未經核准不新增外部音樂素材庫；SD 1.5／Kokoro／Voice Selection 不得回歸。
- 架構：per-scene clip 仍只含 narration（**既有 fingerprint 不變**）；render 階段 `see/audio/layer.py` 取已組裝的 narration 音軌 → BGM（第一個 `bgm` cue，整支一條，loop＋淡入淡出）＋ SFX（`sfx` cue，scene start + start_offset）→ `see/audio/mixer.py`（ducking、gain、look-ahead limiter）→ mux 回影片。來源只經 `AudioProvider`；第一個來源 `procedural-audio`（確定性 pad／chime／whoosh／thud／pop，license=generated）。
- 參數集中 `MixParams`（`Settings.mix_params`）：narration 0 dB、BGM −18 dB、SFX −6 dB、ducking depth −12 dB／threshold −40 dB／attack 60 ms／release 450 ms／hold 200 ms、limiter ceiling −1 dBFS。
- Evidence：`renders/<kind>.audio.json`（CLI `audio_evidence`、Web view）：status（disabled／no_cues／mixed／mixed_degraded／unavailable）、BGM／SFX 的 provider／source_type／license／seed／cost_tier／status、ducking 統計、peak／limiter 衰減、skipped cue。來源失敗 → unavailable 照實寫、輸出 narration-only；PAID 來源 → ApprovalGate 拒絕（render 失敗，fail-closed）。
- **預設 `SEE_AUDIO_PROVIDER=null`（舊行為）**：是否預設開啟 BGM 屬產品聲音體驗 → **DG-17**（需 Windows 真機聽感）。開啟：`run --audio procedural`／`SEE_AUDIO_PROVIDER=procedural`；SFX：`set-scene --sfx 描述@秒數`。
- 第一版限制：ambience 未支援（記為 skipped）；僅一條 BGM；程序化音訊是測試等級，非產品級配樂。

## D-032 2026-10-23 Audio 真機驗收＋產品流程確立＋Style／Character／Lip-sync foundation（Batch 21）
- 客戶回報 E2-3：BGM、ducking、Kokoro zm_010 正常，degraded=false，聽感「OK」，NT$0；SFX 未真機驗證（本次 0 個）。
- 客戶裁示：**DG-17 的「BGM 是否預設開啟」暫不改**，`SEE_AUDIO_PROVIDER` 預設維持 `null`，待完整產品流程／UI 一起決定。CC0／使用者素材來源仍需另核准。
- 產品流程（客戶確立）：故事 → Style Profile → 角色設定 → Voice 選擇／試聽／語速 → 分鏡與影像 → narration → BGM／SFX → Lip-sync → Preview → 人工微調 → Final（對照表見 `ARCHITECTURE.md` §12）。
- Foundation（Project AI 自主；無模型下載、無 PAID、無新素材）：
  - **Style Profile**：`StyleProfile`（positive／negative terms、params、provider_overrides、family、validated）＋內建型錄 default／picture_book／anime／realistic／cinematic／3d；`Project.style_id`（預設 default＝Phase 1 行為，prompt 與 fingerprint 不變）。非 default 風格是 prompt 層 + 參數提示，**未經真機視覺驗收（validated=False）**，不是模型選型。
  - **Character Consistency**：`CharacterAppearance`（description_en／outfit_en／features_en／reference_images／seed／adapter）掛在 `Project.characters`（與 voice 同一角色實體，`CharacterProfile` 別名）；`scene.character_ids` 中有外觀者 → 文字錨點前置到 image prompt，結構化 refs 進 `ImageRequest.params["characters"]` 供未來 IP-Adapter／LoRA 類 provider。SD 1.5 目前只吃文字錨點；不綁 SD 1.5。
  - **Lip-sync**：`LipSyncRequest`（clip、實際 narration 音檔、靜態圖、character、fps）／`LipSyncResult.meta`、能力旗標（applies／requires_face／accepts_image_input／requires_gpu）；pipeline 新增 per-scene lipsync stage（`scene.lipsync` opt-in；null provider → 跳過，clip 與 fingerprint 不變；失敗 → 保留原 clip 記 degraded；PAID → ApprovalGate 拒絕）；timeline 有同步產物才使用。**未選定任何 lip-sync 模型**。
- 下一個 Decision Gate：DG-18（見 BACKLOG）。

## D-033 2026-10-23 DG-18 裁示 A：Style Profile 真機出圖驗收（進行中）
- 範圍：picture_book（繪本）、anime（日系動畫）、realistic（寫實）、cinematic（電影感）、3d（3D）在既有 SD 1.5 上是否產生可辨識且合理的視覺差異。
- 規則：不下載模型、不用 PAID、不研究 IP-Adapter／LoRA／Lip-sync；**不修改 Style Profile 內容迎合結果（先驗證現況）**；NT$0。
- 方法（公平比較）：CLI `style-test --style <id>`：固定場景「小貓咪在院子裡追蝴蝶，陽光很溫暖」、seed 1234（CPU generator，跨風格確定性）、尺寸 1920×1080 請求（SD 1.5 低 VRAM 計畫自動縮到 512 長邊）、同一 base prompt／negative，只換 style terms。輸出 `workspace/style_tests/<style>_seed1234.png/.json`；**不建立專案、不寫 manifest、不動任何快取**；非 diffusers 產生者標 `valid_for_style_test=false`（exit 3）。
- 每張：技術證據（generated_by、dtype、fallback、image_stats、sha256、耗時、實際 prompt）＋客戶人眼判斷（主觀，不寫成客觀品質結論）。Windows 一次一條命令。

## D-034 2026-10-23 產品視覺方向（客戶裁示）＋ E2-4 順序調整
- 決策：**主要產品方向不是兒童繪本**。P1：日系動畫（anime）、AI 真人／寫實（realistic）、電影感真人（cinematic）；P2：3D；P3：兒童繪本（picture_book）等其他風格。寫入 README「產品視覺方向」為 canonical。
- picture_book 真機（`style-test`）：`generated_by=diffusers-sd15`、`final_dtype=float32`（fp16 numeric failure → 正常升 fp32）、`valid_for_style_test=true`、非黑圖非 flat、≈234.5 s、無 OOM、無 fallback、NT$0 → **技術生成 PASS**。客戶主觀：「比較像藝術品。」→ **主觀風格驗收 FAIL**（場景語意呈現不足；單一使用者主觀，非客觀品質結論）。
- 裁示：picture_book **不重跑、不調整、不投入修正**。
- 同場先一次無效嘗試：`generated_by=placeholder-image`、`valid_for_style_test=false`（新 cmd 視窗未設 `SEE_MODELS_DIR`）；工具正確 fail-closed，不計入比較。
- E2-4 後續順序：anime → realistic → cinematic →（次要）3d；公平比較條件不變（同 scene、seed 1234、同尺寸、同 base prompt，只換 style terms；不改 Style Profile；不下載；不用 PAID；NT$0）。
- E2-4 真正目的：判斷**既有 SD1.5 是否足以支撐 P1 方向**。anime／realistic／cinematic 目視比較完成後提 DG-20：A 足夠→角色一致性驗證；B 明顯不足→研究更適合 anime／AI 真人的 LOCAL_FREE 模型；C 依視覺路線採不同模型／provider。
- 裁示前不下載新模型、不導入 IP-Adapter／LoRA、不新增付費服務、不開始 Lip-sync 模型、不開始 DG-19 UI。
- 已知待裁事項（記錄，不擅改）：`default` Style 與 Mock LLM `image_prompt_en` 模板仍內含 storybook watercolor；改預設會改變舊專案 fingerprint → 併入 DG-20 之後處理。

## D-035 2026-10-23 picture_book scene adherence 失敗 → 根因分析與分層驗收
- 真機（客戶回報）：`style-test --style picture_book`，GTX 1650；fp16 NaN → 自動 fp32；`fallback=false`；舊欄位 `valid_for_style_test=true`；≈234 s；NT$0。人工：幾乎看不到貓、沒有追蝴蝶、沒有庭院構圖，畫面是高飽和粗黑線＋抽象／水果／幾何圖形；與前次無實質差異（同輸入同 seed＝確定性同圖，屬預期）。
- 判定：**技術路徑 PASS（真機生成＋fp32 自動升級）；scene FAIL；style FAIL**。`technical_valid=true` 只代表「產生了技術上有效的圖」，**禁止**推論 scene／prompt／style 通過或風格已驗證。
- 根因追查（`docs/AI_IMAGE_QUALITY_RCA.md`）：主要嫌疑 H1＝pipeline 把 16:9 長邊壓到 512 → **512×288 生成**（短邊僅 SD 1.5 訓練解析度 56%）再 ×3.75 插值放大；Phase 1 真機圖同樣是 512×288（Phase 1 只驗技術）。次要：H2 picture_book 詞彙（simple shapes/gouache）、H3 Mock LLM 關鍵詞排序無關係結構、H4 SD 1.5 base 能力（H1 排除前無法分離）。fp32 upcast、offload、seed、scheduler（PNDM 25 步 CFG 7）、截斷（估 ≈40/77）判定為低嫌疑。
- 修正（低風險、預設不變、舊 fingerprint 不變）：分層欄位 `technical_valid`（自動）／`prompt_subject_check`（自動，僅驗 prompt）／`scene_validated`、`style_validated`（僅人工 `style-review`）；舊 `style_validated` 改名 `style_profile_catalog_validated`；`STYLE_TEST_CASES`（kitten_butterfly、girl_city_night）；診斷 `--gen-policy native`、`--base-prompt`、`--scene`（`fair_comparison=false`、檔名加後綴、不覆寫基準證據）；evidence 增 gen 尺寸、crop、upscale、scheduler、steps、guidance、prompt token／截斷。
- 失敗證據保留：`workspace\style_tests\picture_book_seed1234.png/.json`（不入 repo；sha256 在該 json 的 `image_sha256`）。
- 下一步：真機 A/B 只換解析度（`--gen-policy native`）；結果決定 DG-21（native 是否成為預設；會使既有 image fingerprint 失效並增加耗時）或 DG-20（模型路線）。候選模型表為初步、未下載，授權須下載前逐一核對。
