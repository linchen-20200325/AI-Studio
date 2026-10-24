# MIGRATION_REINSTALL.md — 重灌、搬機、換 GPU、換磁碟（D-064）

> 原則：GitHub 保存「怎麼重建」；使用者自己保存「私人資料與模型檔」。程式只檢查、匯出可恢復資訊，**不打包模型、不複製私人圖片、不刪除舊 workspace**。
> 安裝細節見 [`ENVIRONMENT_SETUP.md`](ENVIRONMENT_SETUP.md)。

## 1. 舊機（搬走前）
1. `python -m see.app.cli doctor --hash` — 確認模型完整（大檔重算 sha256，需數分鐘）。
2. `python -m see.app.cli env-export` — 產生 `workspace/exports/env-<時間>/`：
   - `environment_manifest.json`（去識別化；不含本機模型路徑）
   - `python_packages.txt`（目前 Python 套件與版本）
   - `models_manifest.json`（logical model ID、相對路徑、大小、期望／provenance sha256）
   - `workspace_inventory.json`（workspace schema 版本、專案清單、Reference Library metadata〔相對路徑＋sha256＋角色綁定〕、角色庫〔含 archived／revision〕）
   - `settings.json`（portable／machine-specific 分開）
3. 備份 workspace（使用者自行複製整個 `workspace\` 資料夾到外接碟／雲端）。內含私人 reference 圖片——**不要**放進 Git。
4. 依 `models_manifest.json` 列出的路徑，備份 `%SEE_MODELS_DIR%` 整個資料夾（或只複製 status=OK 的項目）。
5. 私人 reference 圖片清單在 `workspace_inventory.json`（只有路徑、sha256、綁定；圖片本身在第 3 步的 workspace 備份中）。

## 2. 新機
1. `git clone https://github.com/linchen-20200325/AI-Studio.git`
2. 建 venv：`py -3.12 -m venv .venv` → `.venv\Scripts\activate`
3. `python -m see.app.cli bootstrap`（唯讀；列出缺什麼）
4. `pip install -r requirements.txt`（基礎依賴）；GPU 相關（torch CUDA）依 doctor 結果與 ENVIRONMENT_SETUP Tier C 決定（需裁示）
5. 放回模型：複製到新位置（例 `E:\AI\models`），設定 `SEE_MODELS_DIR`
6. 放回 workspace：複製到專案根目錄的 `workspace\`（或設定 `SEE_WORKSPACE`）
7. `python -m see.app.cli doctor --hash`（模型 sha256 與舊機一致才算 OK）
8. `python -m see.app.cli smoke`
9. `python -m see.ui --lan` 啟動 Web UI

## 3. 情境
| 情境 | 要做的事 |
|---|---|
| **重灌（同一台）** | 第 1 節備份 → 重灌 → 第 2 節。模型若在另一顆未格式化的磁碟，只要重設 `SEE_MODELS_DIR`。 |
| **換 GPU** | 不需搬資料。`doctor` 看 `gpu.cuda`（名稱、VRAM、compute capability、fp16／bf16）；torch wheel 可能需更換（需裁示）。VRAM 升級後 identity 路線依 ARCHITECTURE §18 Resume Gate 重評，**不自動解除 blocked**。 |
| **換磁碟／搬模型** | 例 `D:\ai-models` → `E:\AI\models`：複製資料夾、改 `SEE_MODELS_DIR`、`doctor --hash`。模型以 logical ID＋相對路徑描述，沒有任何地方寫死磁碟代號。 |
| **搬 workspace** | 整個資料夾複製即可。專案 manifest 舊的絕對路徑會在讀取時自動對應到新位置的同名檔（fingerprint 不含路徑 → 產物沿用、不重做）。 |
| **Reference Library** | 隨 workspace 複製。`.ref.json` 以「類別資料夾＋檔名＋sha256」對應圖片；路徑改變但檔案 hash 相同 → 仍是同一份 reference、角色綁定與 primary 不變（不會被當成新角色）。檔案內容變了 → `sha256 mismatch`，fail closed。 |
| **Character Store** | 隨 workspace 複製；`schema_version`、archived、revision 都在檔案內。舊檔（無 schema_version）以 v1 讀取、不改寫。 |
| **GitHub Alone Recovery** | 新 AI／新電腦只讀 GitHub：`README` → `docs/HANDOFF.md` → `docs/PROJECT_STATE.md` → 本文件與 ENVIRONMENT_SETUP。不需要聊天紀錄。 |

## 4. Schema 版本與遷移規則（foundation）
| 資料 | 版本欄位 | 舊資料 | 比程式新 |
|---|---|---|---|
| workspace | `workspace/workspace_version.json` | 沒有檔案 → 視為 v1（`bootstrap --apply-safe` 可補寫，不改其他檔） | doctor `workspace.schema_version` ERROR（REQUIRED）→ 先更新程式 |
| Character Store | 每檔 `schema_version` | 無欄位 → v1 | 讀取拒絕（CharacterStoreError），不改寫 |
| Reference sidecar | `.ref.json` `schema_version` | 無欄位 → v1；舊絕對 `file_path` 仍可（只比對檔名） | 該筆標為問題（fail closed） |
| Environment manifest | `schema_version` | — | 讀取拒絕 |

- 禁止 silent destructive migration。任何遷移**先備份**（`CharacterStore.backup()` → `workspace/backups/character_library-<時間>/`），`CharacterStore.migration_plan()` 只列出、不改。
- 不可逆遷移 → Decision Gate（本輪沒有任何 schema 遷移）。

## 5. 設定：portable vs machine-specific
| 類別 | 內容 | 搬機時 |
|---|---|---|
| portable | `SEE_LLM_PROVIDER`、`SEE_IMAGE_PROVIDER`、`SEE_IMAGE_MODEL_PRESET`、`SEE_VIDEO_PROVIDER`、`SEE_TTS_PROVIDER`、`SEE_TTS_DEFAULT_VOICE`、`SEE_AUDIO_PROVIDER`、`SEE_LIPSYNC_PROVIDER`；專案內的 style／preferences／scene preferences／角色 voice 與外觀（在 project.json） | 照抄 |
| machine-specific | `SEE_WORKSPACE`、`SEE_MODELS_DIR`、`SEE_IMAGE_MODEL_PATH`、`SEE_TTS_MODEL_PATH`、`SEE_TTS_DEVICE`、`SEE_FFMPEG`、`SEE_FFPROBE`、`SEE_SUBTITLE_FONT`；CUDA、GPU、暫存路徑 | 依新機重設 |
| UI 設定 | Web UI 目前沒有持久化設定 | — |
