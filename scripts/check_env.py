"""環境檢查：python -m scripts.check_env 或 python scripts/check_env.py"""
import sys
from see.app.cli import main

sys.exit(main(["check-env"]))
