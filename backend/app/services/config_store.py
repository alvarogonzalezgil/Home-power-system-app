"""Load and save system configuration as JSON."""

from __future__ import annotations

import json
from pathlib import Path

from app.core.config import CONFIG_PATH
from app.models.schemas import SystemConfig


def load_config(path: Path | None = None) -> SystemConfig:
    p = path or CONFIG_PATH
    with open(p, encoding="utf-8") as f:
        data = json.load(f)
    return SystemConfig.model_validate(data)


def save_config(config: SystemConfig, path: Path | None = None) -> None:
    p = path or CONFIG_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(
            config.model_dump_json(indent=2) + "\n"
        )
