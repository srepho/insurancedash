"""Shared paths for Observable data loaders (run with the project's uv venv)."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
PARQUET = ROOT / "data" / "parquet"
