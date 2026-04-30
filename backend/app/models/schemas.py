"""Pydantic models for API and persisted config."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SystemConfig(BaseModel):
    latitude: float
    longitude: float
    tilt_deg: float = Field(ge=0, le=90, description="Panel tilt from horizontal (°)")
    azimuth_deg: float = Field(
        ge=0,
        le=360,
        description="Panel surface azimuth from North clockwise (0=N, 90=E)",
    )
    panel_count: int = Field(ge=1, le=10_000)
    panel_width_m: float = Field(gt=0)
    panel_height_m: float = Field(gt=0)
    panel_efficiency: float = Field(gt=0, le=1)
    timezone_offset_h: float = Field(
        ge=-12,
        le=12,
        description=(
            "UTC + offset in hours (e.g. 0 for GMT, +1 for BST). "
            "Update manually at DST transitions (or via Settings)."
        ),
    )
    sample_minutes: int = Field(default=5, ge=1, le=60)
    inverter_sn: str | None = Field(
        default=None,
        description="FoxESS inverter serial; empty or absent triggers auto-detect",
    )
    foxess_power_unit: Literal["kW", "W"] = Field(
        default="kW",
        description="Unit of pvPower from FoxESS history API",
    )


class PvCurvePoint(BaseModel):
    time: str
    power_w: float | None = Field(
        default=None,
        description="Power in watts; null when no sample in interval",
    )


class PvCurveResponse(BaseModel):
    date: str
    points: list[PvCurvePoint]


class ForecastPvDayResponse(BaseModel):
    """Weather forecast curve plus clear-sky reference for the same sample grid."""

    date: str
    model: Literal["components", "cloud_derate"]
    forecast_points: list[PvCurvePoint]
    clear_sky_points: list[PvCurvePoint]
