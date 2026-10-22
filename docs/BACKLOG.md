# BACKLOG.md

優先順序：P0（下一步）> P1 > P2。每項都受 PROJECT_RULES 約束（Free First、需核准才可接 PAID）。

## Decision Gate（需使用者裁示）
- [ ] DG-1：是否以 `ccr-2968bce1-ym4kkc` 建立 `main`（repo 尚無 main）。
- [ ] DG-2：Phase 1 LLM 路線：本機 Ollama（需下載模型，數 GB）vs. 免費額度 API（需 key）vs. 維持 Mock。
- [ ] DG-3：Phase 1 TTS 路線：edge-tts（FREE_TIER，需網路）vs. 本機神經 TTS（需下載模型）vs. 維持 espeak。
- [ ] DG-4：Web UI 技術選型（Streamlit 最快 / FastAPI + 簡單前端 較適合手機）。

## P0
- [ ] Web UI（手機可用）：輸入文字 → 看 preview → 修改單景 → 核准。
- [ ] `OllamaLLMProvider`（LOCAL_FREE）：真正的劇本／分鏡生成（待 DG-2）。
- [ ] `EdgeTTSProvider` 在有網路環境實測（待 DG-3）。
- [ ] BGM / SFX：`AudioProvider` 實作（免費素材庫或程序化生成），含 ducking。
- [ ] QA 階段：自動檢查（音量 LUFS、黑幀、字幕超長、總長度區間）。

## P1
- [ ] 真正 ImageProvider（本機 SD / Flux 等，需 GPU + 下載權重 → 停手條件）。
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
