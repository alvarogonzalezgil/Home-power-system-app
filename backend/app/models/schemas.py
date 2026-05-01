"""Pydantic models for API and persisted config."""

from __future__ import annotations

from typing import Literal

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
    # Octopus Flux (or compatible) published half-hour rates — no API key; verify codes in dashboard.
    octopus_region: str = Field(
        default="K",
        description=(
            "GB electricity region suffix (letters A–H, J–N, P as on your bill)."
        ),
    )
    octopus_import_product: str = Field(
        default="FLUX-IMPORT-23-02-14",
        min_length=3,
        description="Octopus IMPORT product ``code`` (not the standing-charge tariff name).",
    )
    octopus_export_product: str = Field(
        default="FLUX-EXPORT-23-02-14",
        min_length=3,
        description=(
            "Octopus EXPORT product ``code`` for your export tariff (update if you are on a "
            "different outgoing product)."
        ),
    )
    inverter_capacity_kw: float = Field(
        default=5.0,
        gt=0,
        description="AC export cap / inverter limit for advisory PV clipping (kW).",
    )
    battery_capacity_kwh: float = Field(
        default=5.2,
        gt=0,
        description="Usable nameplate battery energy (kWh).",
    )
    battery_min_soc_pct: float = Field(
        default=10.0,
        ge=0,
        le=95,
        description="Minimum state of charge you want to keep (%) for advisory headroom.",
    )
    battery_round_trip_efficiency: float = Field(
        default=0.88,
        gt=0,
        le=1.0,
        description="DC round-trip efficiency for simple arbitrage checks (advisory).",
    )

    @field_validator("octopus_region")
    @classmethod
    def _octopus_region_ok(cls, v: str) -> str:
        s = v.strip().upper()
        allowed = set("ABCDEFGHJKLMNP")
        if len(s) != 1 or s not in allowed:
            raise ValueError(
                "octopus_region must be a single letter A–H, J–N, or P (GB region)."
            )
        return s


class OptimizationHalfHour(BaseModel):
    interval_start_iso: str
    label_hhmm: str
    import_p_per_kwh: float | None = Field(
        default=None,
        description="Standing import price inc VAT (p/kWh)",
    )
    export_p_per_kwh: float | None = Field(
        default=None,
        description="Standing export price inc VAT (p/kWh)",
    )
    import_band: str | None = None
    export_band: str | None = None
    pv_kw: float | None = Field(default=None)


class OptimizationRecommendation(BaseModel):
    title: str
    detail: str


class OptimizationEstimates(BaseModel):
    clipped_pv_energy_kwh: float
    clipped_energy_partial_forecast: bool
    usable_battery_energy_kwh: float
    target_soc_headroom_pct_hint: float = Field(
        description=(
            "Advisory ceiling state-of-charge (percent) below which to bias pre-PV discharge "
            "when clipping is forecast (rough heuristic)."
        ),
    )
    overnight_import_avg_p_per_kwh: float | None = None
    peak_export_avg_p_per_kwh: float | None = None
    theoretical_arbitrage_spread_pp: float | None = Field(
        default=None,
        description="peak export − overnight import (p/kWh), not net of RTE",
    )
    clipped_value_vs_grid_import_pence: float | None = Field(
        default=None,
        description="clipped_kWh × daytime import average (pence), illustrative only",
    )


class OptimizationDayResponse(BaseModel):
    date: str
    tariff_code_import: str
    tariff_code_export: str
    half_hours: list[OptimizationHalfHour]
    recommendations: list[OptimizationRecommendation]
    estimates: OptimizationEstimates


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
