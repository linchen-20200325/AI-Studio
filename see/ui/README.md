# see/ui — Web UI（Phase 0.5）

```bash
python -m see.ui --lan
# 手機瀏覽器開啟 http://<主機IP>:8000/
```

- `server.py`：FastAPI。`/` 單頁 UI；`/api/*` JSON；`/api/projects/{id}/preview.mp4` 支援 HTTP Range（手機播放器需要）。
- `runner.py`：`BackgroundRunner`（單機、單 worker 的最小排程）。未來 NAS queue + GPU worker 以同介面替換，UI 不改。
- `static/index.html`：無框架、無建置步驟的手機友善單頁。
- 無登入（BACKLOG）。請只在信任網路內使用。
