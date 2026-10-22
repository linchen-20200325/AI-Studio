# BACKLOG.md

優先順序：P0（下一步）> P1 > P2。每項都受 PROJECT_RULES 約束（Free First、需核准才可接 PAID）。

## Decision Gate（需使用者裁示）
- [x] DG-1：以 `026206c` 建立 `main`。
- [x] DG-2：暫緩 Ollama；維持 Mock，架構保留。
- [x] DG-3：edge-tts 待可連網環境驗證（FREE_TIER、零 key）。→ 待辦：在有網路的機器執行 `SEE_TTS_PROVIDER=edge python -m see.app.cli run examples/story_tiny.txt`。
- [x] DG-4：FastAPI + 手機友善單頁（已完成）。
- [x] DG-5：第一版限可信任區網，無登入（D-011）。未來 NAS／遠端部署再開 Access Control DG。
- [x] DG-6：不採用 edge-tts，adapter 保留（D-014）。
- [ ] DG-7：裁示已下（D-015），待使用者在 GitHub 設定手動把預設分支改 main、改 Private。

## P0
- [ ] DG-8：AI Image 方案 A（FLUX.1-schnell）或 B（SD 1.5）；需使用者在 Windows 跑 `python -m see.app.cli hardware` 貼回結果，並同意下載對應模型（見 AI_IMAGE_PROVIDER_PLAN）。
- [ ] `image_prompt_en`：storyboard 多產英文 prompt（Mock 模板）＋ negative prompt 預設（可自主，不需模型）。
- [ ] 真機以 `SEE_IMAGE_PROVIDER=auto` 產生 preview，記錄速度與證據（需模型，待 DG-8）。
- [ ] UI 顯示實際使用的 image provider 與 fallback 原因（可自主）。
- [x] CI workflow（GitHub Actions：pytest + ffmpeg）（D-016）。
- [x] Web UI（手機可用）：輸入文字 → 看 preview → 修改單景 → 核准。
- [ ] `EdgeTTSProvider` 在有網路環境實測（DG-3）。
- [ ] Web UI：處理中顯示每景進度（目前只到 stage 層級）；專案刪除。
- [ ] `OllamaLLMProvider`（LOCAL_FREE）：暫緩（DG-2）。
- [ ] BGM / SFX：`AudioProvider` 實作（免費素材庫或程序化生成），含 ducking。
- [ ] QA 階段：自動檢查（音量 LUFS、黑幀、字幕超長、總長度區間）。

## P1
- [x] 真正 ImageProvider 骨架（D-017）；模型下載與真機驗證待 DG-8。
- [ ] 真正 VideoProvider（image-to-video；本機或 API，皆需核准）。
- [ ] Character 一致性（角色參考圖、seed 管理）。
- [ ] `QueueExecutor`：NAS 排隊 + GPU PC worker 領取（需硬體資訊 → 停手條件）。
- [ ] Final render 與 Preview 分離的品質設定（解析度 / bitrate / 多平台輸出）。
- [ ] 多語系（英文旁白 / 雙語字幕）。

## P2
- [ ] Lip Sync Provider。
- [ ] 登入 / 多使用者。
- [ ] 成本儀表板（每 project 實際花費）。
- [ ] 字幕樣式主題。
- [ ] `cut` 轉場改為真正的硬切（目前以 0.08s fade 模擬）。
