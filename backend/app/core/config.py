"""Application paths and settings."""

from __future__ import annotations

import os
from pathlib import Path

# backend/app -> repo root = parents[2]
APP_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = APP_DIR / "data"
DEFAULT_CONFIG_PATH = DATA_DIR / "system_config.json"

# Allow override for tests
CONFIG_PATH = Path(
    os.environ.get("HOME_POWER_CONFIG_PATH", str(DEFAULT_CONFIG_PATH))
)
