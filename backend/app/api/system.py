"""System configuration API."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.models.schemas import SystemConfig
from app.services import config_store

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/config", response_model=SystemConfig)
def get_config() -> SystemConfig:
    try:
        return config_store.load_config()
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail="Config file missing") from e
    except OSError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.put("/config", response_model=SystemConfig)
def put_config(config: SystemConfig) -> SystemConfig:
    try:
        config_store.save_config(config)
        return config
    except OSError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
