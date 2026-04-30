"""Weather-based PV forecast API (Open-Meteo)."""

from __future__ import annotations

from datetime import date as date_type
from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from app.models.schemas import ForecastPvDayResponse, PvCurvePoint
from app.services import config_store
from app.services.forecast_service import (
    ForecastError,
    predicted_curve_cloud_derate,
    predicted_curve_components,
)
from app.services.solar_calculator import validate_ymd

router = APIRouter(prefix="/api/forecast", tags=["forecast"])


@router.get("/pv/day", response_model=ForecastPvDayResponse)
def forecast_pv_day(
    date: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"),
    model: Literal["components", "cloud_derate"] = "components",
) -> ForecastPvDayResponse:
    try:
        d = date_type.fromisoformat(date)
        validate_ymd(d.year, d.month, d.day)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    cfg = config_store.load_config()
    try:
        if model == "cloud_derate":
            fc_pairs, ref_pairs = predicted_curve_cloud_derate(cfg, d)
        else:
            fc_pairs, ref_pairs = predicted_curve_components(cfg, d)
    except ForecastError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    return ForecastPvDayResponse(
        date=date,
        model=model,
        forecast_points=[PvCurvePoint(time=t, power_w=p) for t, p in fc_pairs],
        clear_sky_points=[PvCurvePoint(time=t, power_w=p) for t, p in ref_pairs],
    )
