"""PV clear-sky curve API."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.models.schemas import PvCurvePoint, PvCurveResponse
from app.services import config_store
from app.services.solar_calculator import day_curve, validate_ymd

router = APIRouter(prefix="/api/pv", tags=["pv"])


@router.get("/day", response_model=PvCurveResponse)
def get_day(
    year: int = Query(2025, ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
    day: int = Query(..., ge=1, le=31),
) -> PvCurveResponse:
    try:
        validate_ymd(year, month, day)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    cfg = config_store.load_config()
    try:
        series = day_curve(
            year=year,
            month=month,
            day=day,
            latitude=cfg.latitude,
            longitude=cfg.longitude,
            timezone_offset_h=cfg.timezone_offset_h,
            tilt_deg=cfg.tilt_deg,
            azimuth_deg=cfg.azimuth_deg,
            panel_count=cfg.panel_count,
            panel_width_m=cfg.panel_width_m,
            panel_height_m=cfg.panel_height_m,
            panel_efficiency=cfg.panel_efficiency,
            sample_minutes=cfg.sample_minutes,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    points = [
        PvCurvePoint(
            time=dt.strftime("%H:%M"),
            power_w=round(p, 2),
        )
        for dt, p, _ in series
    ]
    return PvCurveResponse(
        date=f"{year:04d}-{month:02d}-{day:02d}",
        points=points,
    )
