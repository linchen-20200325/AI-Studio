"""Web UI 啟動入口（DG-5：第一版限可信任區網內使用，預設只綁 127.0.0.1）。

    python -m see.ui              # 只有本機可開 http://127.0.0.1:8000/
    python -m see.ui --lan        # 綁 0.0.0.0，讓同一區網的手機可開；僅限可信任區網
"""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    from see.core.proc import ensure_utf8_stdio

    ensure_utf8_stdio()
    ap = argparse.ArgumentParser(prog="python -m see.ui", description="see Web UI")
    ap.add_argument("--lan", action="store_true", help="綁定 0.0.0.0 供同一可信任區網的裝置使用（預設只綁 127.0.0.1）")
    ap.add_argument("--host", default=None, help="明確指定綁定位址（覆寫 --lan）")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args(argv)
    host = args.host or ("0.0.0.0" if args.lan else "127.0.0.1")
    if host not in ("127.0.0.1", "localhost", "::1"):
        print("⚠ Web UI 無登入機制。只能在可信任區網使用；不要開放到 Internet、不要透過公開 tunnel 轉發。"
              "（PROJECT_RULES / DECISIONS D-011）", file=sys.stderr)
    try:
        import uvicorn
    except ImportError:
        print("需要 uvicorn：pip install -r requirements.txt", file=sys.stderr)
        return 1
    uvicorn.run("see.ui.server:app", host=host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    sys.exit(main())
