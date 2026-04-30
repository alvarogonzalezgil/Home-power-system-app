"""Weather-based PV forecast via Open-Meteo (hourly → site sample grid)."""

from __future__ import annotations

import bisect
import math
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx

from app.integrations.http_verify import build_default_verify
from app.models.schemas import SystemConfig
from app.services.solar_calculator import (
    compute_power_w_at_instant,
    day_curve,
    validate_ymd,
    _day_of_year,
)

DEFAULT_OPEN_METEO_BASE = "https://api.open-meteo.com/v1/forecast"
HOURLY_VARS = (
    "temperature_2m,cloud_cover,shortwave_radiation,"
    "direct_normal_irradiance,diffuse_radiation,wind_speed_10m"
)

# Liu–Jordan isotropic diffuse + ground albedo
RHO_GROUND = 0.2
# PV temperature coefficient (/°C); -0.4 %/°C
GAMMA_PER_C = -0.004
NOCT_C = 45.0


class ForecastError(RuntimeError):
    """Open-Meteo fetch or parse failure."""


@dataclass(frozen=True)
class ForecastHourSample:
    """One Open-Meteo hourly bucket (UTC instant at hour start)."""

    time_utc: datetime
    temp_c: float
    cloud_pct: float
    ghi_wm2: float
    dni_wm2: float
    dhi_wm2: float
    wind_ms: float


def open_meteo_base() -> str:
    return (os.environ.get("OPEN_METEO_BASE") or DEFAULT_OPEN_METEO_BASE).rstrip("/")


def _cfg_tz(cfg: SystemConfig) -> timezone:
    return timezone(timedelta(hours=cfg.timezone_offset_h))


def local_naive_to_utc(dt_naive: datetime, cfg: SystemConfig) -> datetime:
    aware = dt_naive.replace(tzinfo=_cfg_tz(cfg))
    return aware.astimezone(timezone.utc)


def cloud_cover_derate_factor(cloud_cover_pct: float) -> float:
    """Kasten–Czeplak-style factor from total cloud cover (0–100)."""
    c = max(0.0, min(1.0, cloud_cover_pct / 100.0))
    return 1.0 - 0.75 * (c**3.4)


def poa_components_wm2(
    dni: float,
    dhi: float,
    ghi: float,
    cos_theta: float,
    tilt_deg: float,
) -> float:
    """Plane-of-array irradiance (W/m²), isotropic sky + ground reflection."""
    cos_t = max(0.0, cos_theta)
    beta = math.radians(tilt_deg)
    cos_b = math.cos(beta)
    return (
        dni * cos_t
        + dhi * (1.0 + cos_b) / 2.0
        + ghi * RHO_GROUND * (1.0 - cos_b) / 2.0
    )


def cell_temp_c_simple(t_amb_c: float, ghi_wm2: float) -> float:
    """Simple NOCT-based cell temperature from horizontal GHI."""
    return t_amb_c + (NOCT_C - 20.0) / 800.0 * ghi_wm2


def power_from_poa_wm2(
    poa_wm2: float,
    area_m2: float,
    panel_efficiency: float,
    t_cell_c: float,
) -> float:
    """DC-ish power (W) from POA with linear temperature derate."""
    return max(
        0.0,
        poa_wm2
        * area_m2
        * panel_efficiency
        * (1.0 + GAMMA_PER_C * (t_cell_c - 25.0)),
    )


def _parse_om_time(s: str) -> datetime:
    raw = str(s).strip()
    if raw.endswith("Z"):
        raw = raw[:-1]
    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt


def fetch_open_meteo_hourly(
    lat: float,
    lon: float,
    *,
    forecast_days: int = 16,
) -> list[ForecastHourSample]:
    """Download hourly forecast series (UTC times)."""
    # Base URL already includes /v1/forecast; do not append /forecast again (404).
    url = open_meteo_base()
    params: dict[str, Any] = {
        "latitude": lat,
        "longitude": lon,
        "hourly": HOURLY_VARS,
        "timezone": "UTC",
        "forecast_days": forecast_days,
        "windspeed_unit": "ms",
    }
    timeout = httpx.Timeout(25.0)
    try:
        with httpx.Client(timeout=timeout, verify=build_default_verify()) as client:
            r = client.get(url, params=params)
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPStatusError as e:
        raise ForecastError(f"Open-Meteo HTTP {e.response.status_code}") from e
    except httpx.RequestError as e:
        raise ForecastError(f"Open-Meteo request failed: {e}") from e

    hourly = data.get("hourly") or {}
    times = hourly.get("time") or []
    if not times:
        raise ForecastError("Open-Meteo returned no hourly.time")

    def series(key: str) -> list[float]:
        raw_list = hourly.get(key)
        if raw_list is None or len(raw_list) != len(times):
            raise ForecastError(f"Open-Meteo missing or mismatched hourly.{key}")
        out: list[float] = []
        for v in raw_list:
            if v is None:
                out.append(0.0)
            else:
                out.append(float(v))
        return out

    t2m = series("temperature_2m")
    cc = series("cloud_cover")
    ghi = series("shortwave_radiation")
    dni = series("direct_normal_irradiance")
    dhi = series("diffuse_radiation")
    ws = series("wind_speed_10m")

    samples: list[ForecastHourSample] = []
    for i, ts in enumerate(times):
        samples.append(
            ForecastHourSample(
                time_utc=_parse_om_time(str(ts)),
                temp_c=t2m[i],
                cloud_pct=cc[i],
                ghi_wm2=ghi[i],
                dni_wm2=dni[i],
                dhi_wm2=dhi[i],
                wind_ms=ws[i],
            )
        )
    samples.sort(key=lambda s: s.time_utc)
    return samples


def _interp_scalar(
    xs: list[float],
    ys: list[float],
    x: float,
) -> float:
    """Linear interpolation; clamps outside range."""
    if not xs:
        return 0.0
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    i = bisect.bisect_right(xs, x) - 1
    i = max(0, min(i, len(xs) - 2))
    x0, x1 = xs[i], xs[i + 1]
    y0, y1 = ys[i], ys[i + 1]
    if x1 == x0:
        return y0
    t = (x - x0) / (x1 - x0)
    return y0 + t * (y1 - y0)


def interpolate_hourly_at(
    hourly: list[ForecastHourSample],
    t_utc: datetime,
) -> ForecastHourSample:
    """Linear interpolation of all fields at instant t_utc (UTC)."""
    if not hourly:
        raise ForecastError("No hourly samples to interpolate")
    ts = [s.time_utc.timestamp() for s in hourly]
    tx = t_utc.timestamp()
    return ForecastHourSample(
        time_utc=t_utc,
        temp_c=_interp_scalar(ts, [s.temp_c for s in hourly], tx),
        cloud_pct=_interp_scalar(ts, [s.cloud_pct for s in hourly], tx),
        ghi_wm2=_interp_scalar(ts, [s.ghi_wm2 for s in hourly], tx),
        dni_wm2=_interp_scalar(ts, [s.dni_wm2 for s in hourly], tx),
        dhi_wm2=_interp_scalar(ts, [s.dhi_wm2 for s in hourly], tx),
        wind_ms=_interp_scalar(ts, [s.wind_ms for s in hourly], tx),
    )


def validate_forecast_day(day: date) -> None:
    """Restrict to rolling window aligned with small UI (today .. today+6)."""
    today = date.today()
    if day < today:
        raise ForecastError("Forecast date cannot be in the past")
    if (day - today).days > 6:
        raise ForecastError("Forecast date out of range (select within 7 days)")


def predicted_curve_cloud_derate(
    cfg: SystemConfig,
    day: date,
    hourly: list[ForecastHourSample] | None = None,
) -> tuple[list[tuple[str, float | None]], list[tuple[str, float | None]]]:
    """
    Weather-adjusted forecast (cloud derate on clear-sky direct) and clear-sky reference.
    Returns (forecast_pairs, clear_sky_pairs) as (HH:MM, power_w).
    """
    validate_ymd(day.year, day.month, day.day)
    validate_forecast_day(day)
    if hourly is None:
        hourly = fetch_open_meteo_hourly(cfg.latitude, cfg.longitude)

    curve = day_curve(
        day.year,
        day.month,
        day.day,
        cfg.latitude,
        cfg.longitude,
        cfg.timezone_offset_h,
        cfg.tilt_deg,
        cfg.azimuth_deg,
        cfg.panel_count,
        cfg.panel_width_m,
        cfg.panel_height_m,
        cfg.panel_efficiency,
        cfg.sample_minutes,
    )

    fc_out: list[tuple[str, float | None]] = []
    ref_out: list[tuple[str, float | None]] = []
    for dt_naive, p_clear, _st in curve:
        s = interpolate_hourly_at(hourly, local_naive_to_utc(dt_naive, cfg))
        k = cloud_cover_derate_factor(s.cloud_pct)
        p_fc = max(0.0, p_clear * k)
        fc_out.append((dt_naive.strftime("%H:%M"), round(p_fc, 2)))
        ref_out.append((dt_naive.strftime("%H:%M"), round(p_clear, 2)))
    return fc_out, ref_out


def predicted_curve_components(
    cfg: SystemConfig,
    day: date,
    hourly: list[ForecastHourSample] | None = None,
) -> tuple[list[tuple[str, float | None]], list[tuple[str, float | None]]]:
    """
    POA from Open-Meteo DNI/DHI/GHI + Liu–Jordan diffuse + temperature derate.
    Returns (forecast_pairs, clear_sky_pairs).
    """
    validate_ymd(day.year, day.month, day.day)
    validate_forecast_day(day)
    if hourly is None:
        hourly = fetch_open_meteo_hourly(cfg.latitude, cfg.longitude)

    area = cfg.panel_count * cfg.panel_width_m * cfg.panel_height_m
    doy = _day_of_year(day)

    curve = day_curve(
        day.year,
        day.month,
        day.day,
        cfg.latitude,
        cfg.longitude,
        cfg.timezone_offset_h,
        cfg.tilt_deg,
        cfg.azimuth_deg,
        cfg.panel_count,
        cfg.panel_width_m,
        cfg.panel_height_m,
        cfg.panel_efficiency,
        cfg.sample_minutes,
    )

    fc_out: list[tuple[str, float | None]] = []
    ref_out: list[tuple[str, float | None]] = []
    for dt_naive, p_clear, _st in curve:
        ref_out.append((dt_naive.strftime("%H:%M"), round(p_clear, 2)))

        wx = interpolate_hourly_at(hourly, local_naive_to_utc(dt_naive, cfg))
        _, st = compute_power_w_at_instant(
            when=dt_naive,
            day_of_year=doy,
            latitude=cfg.latitude,
            longitude=cfg.longitude,
            timezone_offset_h=cfg.timezone_offset_h,
            tilt_deg=cfg.tilt_deg,
            azimuth_deg=cfg.azimuth_deg,
            total_panel_area_m2=area,
            panel_efficiency=cfg.panel_efficiency,
        )
        if st.elevation_deg <= 0.0:
            fc_out.append((dt_naive.strftime("%H:%M"), 0.0))
            continue

        cos_th = max(0.0, st.cos_incidence)
        poa = poa_components_wm2(
            wx.dni_wm2,
            wx.dhi_wm2,
            wx.ghi_wm2,
            cos_th,
            cfg.tilt_deg,
        )
        t_cell = cell_temp_c_simple(wx.temp_c, wx.ghi_wm2)
        p_fc = power_from_poa_wm2(poa, area, cfg.panel_efficiency, t_cell)
        fc_out.append((dt_naive.strftime("%H:%M"), round(p_fc, 2)))

    return fc_out, ref_out
