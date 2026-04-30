"""FoxESS measured PV curve API."""

from __future__ import annotations

from datetime import date as date_type

from fastapi import APIRouter, HTTPException, Query

from app.integrations.foxess.client import FoxessApiError, FoxessAuthError
from app.models.schemas import PvCurvePoint, PvCurveResponse
from app.services import config_store
from app.services import foxess_service
from app.services.solar_calculator import validate_ymd

router = APIRouter(prefix="/api/foxess", tags=["foxess"])


@router.get("/pv/day", response_model=PvCurveResponse)
def foxess_pv_day(
    date: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"),
) -> PvCurveResponse:
    try:
        d = date_type.fromisoformat(date)
        validate_ymd(d.year, d.month, d.day)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    cfg = config_store.load_config()
    try:
        sn, cfg = foxess_service.resolve_sn(cfg)
        pairs = foxess_service.get_actual_pv_curve_points(d, cfg, sn)
    except FoxessAuthError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except FoxessApiError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    return PvCurveResponse(
        date=date,
        points=[PvCurvePoint(time=t, power_w=p) for t, p in pairs],
    )
