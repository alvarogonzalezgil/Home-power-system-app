"""Advisory optimization: Octopus half-hour rates + forecast PV clipping."""

from __future__ import annotations

from datetime import date as date_type

from fastapi import APIRouter, HTTPException, Query

from app.models.schemas import OptimizationDayResponse
from app.services import config_store
from app.services.optimization_service import OptimizationError, build_optimization_day
from app.services.solar_calculator import validate_ymd

router = APIRouter(prefix="/api/optimization", tags=["optimization"])


@router.get("/today", response_model=OptimizationDayResponse)
def optimization_today(
    date: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"),
) -> OptimizationDayResponse:
    try:
        d = date_type.fromisoformat(date)
        validate_ymd(d.year, d.month, d.day)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    cfg = config_store.load_config()
    try:
        return build_optimization_day(cfg, d)
    except OptimizationError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
