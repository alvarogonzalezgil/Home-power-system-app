"""Pydantic models for API and persisted config."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


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
        ge=-12, le=12, description="UTC + offset (e.g. 0 for winter UK if times are UTC)"
    )
    sample_minutes: int = Field(default=5, ge=1, le=60)


class PvCurvePoint(BaseModel):
    time: str
    power_w: float


class PvCurveResponse(BaseModel):
    date: str
    points: list[PvCurvePoint]
