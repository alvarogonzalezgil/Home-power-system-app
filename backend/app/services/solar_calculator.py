"""
Clear-sky maximum theoretical PV power using PVEducation.org Chapter 2 relations:
solar time, declination, elevation, azimuth, air mass, direct normal irradiance,
and incidence on an arbitrarily tilted surface.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Iterator

# Reference year: non-leap; month/day only are user-selected.
REFERENCE_YEAR = 2025


@dataclass(frozen=True)
class SolarState:
    """Per-timestep intermediate values (useful for debugging)."""

    local_time_h: float
    lst_h: float
    hour_angle_deg: float
    declination_deg: float
    elevation_deg: float
    zenith_deg: float
    sun_azimuth_deg: float
    air_mass: float
    dni_kwm2: float
    cos_incidence: float
    poa_w_m2: float
    power_w: float


def _day_of_year(d: date) -> int:
    return d.timetuple().tm_yday


def solar_declination_deg(day_of_year: int) -> float:
    """Declination (degrees) — B = (360/365)*(d-81) in deg; δ = 23.45° sin B."""
    b_deg = (360.0 / 365.0) * (day_of_year - 81)
    b_rad = math.radians(b_deg)
    return 23.45 * math.sin(b_rad)


def equation_of_time_minutes(day_of_year: int) -> float:
    """Equation of time (minutes)."""
    b_deg = (360.0 / 365.0) * (day_of_year - 81)
    b_rad = math.radians(b_deg)
    return (
        9.87 * math.sin(2.0 * b_rad)
        - 7.53 * math.cos(b_rad)
        - 1.5 * math.sin(b_rad)
    )


def local_solar_time_hours(
    local_time_h: float, lon_deg: float, tz_h: float, eot_min: float
) -> float:
    """Local solar time (decimal hours) — PVEducation 'Solar Time'."""
    lsm_deg = 15.0 * tz_h
    return local_time_h + (eot_min + 4.0 * (lsm_deg - lon_deg)) / 60.0


def hour_angle_deg(lst_h: float) -> float:
    return 15.0 * (lst_h - 12.0)


def solar_elevation_rad(lat_deg: float, dec_deg: float, h_deg: float) -> float:
    """α = arcsin( sinφ sinδ + cosφ cosδ cos H ) — elevation in radians."""
    p = math.radians(lat_deg)
    d = math.radians(dec_deg)
    h = math.radians(h_deg)
    s = (
        math.sin(p) * math.sin(d) + math.cos(p) * math.cos(d) * math.cos(h)
    )
    s = max(-1.0, min(1.0, s))
    return math.asin(s)


def solar_zenith_deg(elevation_rad: float) -> float:
    return 90.0 - math.degrees(elevation_rad)


def sun_azimuth_deg_north_cw(
    lat_deg: float, dec_deg: float, h_deg: float, el_rad: float
) -> float:
    """
    Solar azimuth from North, clockwise 0-360 (degrees) — PVEducation
    'Azimuth Angle' form with hour-angle sign correction.
    (Matches the notebook: acos, flip when H>0).
    """
    p = math.radians(lat_deg)
    d = math.radians(dec_deg)
    h = math.radians(h_deg)
    den = math.cos(el_rad) * math.cos(p)
    if abs(den) < 1e-12:
        return 0.0
    cos_azi = (math.sin(d) - math.sin(el_rad) * math.sin(p)) / den
    cos_azi = max(-1.0, min(1.0, cos_azi))
    azi = math.acos(cos_azi)
    if h > 0:
        azi = 2.0 * math.pi - azi
    return math.degrees(azi) % 360.0


def kasten_young_air_mass(zenith_deg: float) -> float:
    """Kasten-Young (1989) air mass (dimensionless) — for zenith < ~90°."""
    if zenith_deg >= 90.0 or zenith_deg < 0.0:
        return 0.0
    z_rad = math.radians(zenith_deg)
    denom = math.cos(z_rad) + 0.50572 * ((96.07995 - zenith_deg) ** -1.6364)
    if denom <= 0:
        return 0.0
    return 1.0 / denom


def dni_clearsky_kwm2(air_mass: float) -> float:
    """
    Direct normal on clear day (kW/m²) — I_D = 1.353 · 0.7^(AM^0.678).
    """
    if air_mass <= 0.0:
        return 0.0
    return 1.353 * (0.7 ** (air_mass**0.678))


def cos_incidence_on_tilted_surface(
    el_rad: float, sun_azi_north_cw_deg: float, tilt_deg: float, surface_azi_north_cw_deg: float
) -> float:
    """
    cos θ (plane-of-array factor) for a tilted, arbitrarily oriented surface.
    θ is angle of incidence; both azimuths 0=North, clockwise, degrees.
    """
    beta = math.radians(tilt_deg)
    gamma = math.radians(surface_azi_north_cw_deg)
    a = math.radians(sun_azi_north_cw_deg)
    alpha = el_rad
    return math.sin(alpha) * math.cos(beta) + math.cos(alpha) * math.sin(
        beta
    ) * math.cos(a - gamma)


def compute_power_w_at_instant(
    when: datetime,
    day_of_year: int,
    latitude: float,
    longitude: float,
    timezone_offset_h: float,
    tilt_deg: float,
    azimuth_deg: float,
    total_panel_area_m2: float,
    panel_efficiency: float,
) -> tuple[float, SolarState]:
    """Theoretical max DC power (W) at this instant; sun below horizon -> 0."""
    lt = (
        when.hour
        + when.minute / 60.0
        + when.second / 3600.0
    )
    eot = equation_of_time_minutes(day_of_year)
    lst = local_solar_time_hours(
        lt, longitude, timezone_offset_h, eot
    )
    h_deg = hour_angle_deg(lst)
    dec_deg = solar_declination_deg(day_of_year)
    el_rad = solar_elevation_rad(latitude, dec_deg, h_deg)
    alpha_deg = math.degrees(el_rad)
    if alpha_deg <= 0.0 or el_rad <= 0.0:
        st = SolarState(
            local_time_h=lt,
            lst_h=lst,
            hour_angle_deg=h_deg,
            declination_deg=dec_deg,
            elevation_deg=alpha_deg,
            zenith_deg=90.0,
            sun_azimuth_deg=0.0,
            air_mass=0.0,
            dni_kwm2=0.0,
            cos_incidence=0.0,
            poa_w_m2=0.0,
            power_w=0.0,
        )
        return 0.0, st
    z_deg = solar_zenith_deg(el_rad)
    sun_azi = sun_azimuth_deg_north_cw(latitude, dec_deg, h_deg, el_rad)
    am = kasten_young_air_mass(z_deg)
    dni = dni_clearsky_kwm2(am)
    cos_th = cos_incidence_on_tilted_surface(
        el_rad, sun_azi, tilt_deg, azimuth_deg
    )
    if cos_th <= 0.0:
        p_w = 0.0
        poa = 0.0
    else:
        poa = dni * 1000.0 * cos_th
        p_w = poa * total_panel_area_m2 * panel_efficiency
    st = SolarState(
        local_time_h=lt,
        lst_h=lst,
        hour_angle_deg=h_deg,
        declination_deg=dec_deg,
        elevation_deg=alpha_deg,
        zenith_deg=z_deg,
        sun_azimuth_deg=sun_azi,
        air_mass=am,
        dni_kwm2=dni,
        cos_incidence=cos_th,
        poa_w_m2=poa,
        power_w=p_w,
    )
    return p_w, st


def iter_sample_times(
    the_date: date, step_minutes: int
) -> Iterator[datetime]:
    """For one calendar day, samples from 00:00:00 to 23:55:00 (5-min default)."""
    t0 = datetime.combine(the_date, time.min)
    n = 24 * 60 // step_minutes
    for k in range(n):
        yield t0 + timedelta(minutes=k * step_minutes)


def day_curve(
    month: int,
    day: int,
    latitude: float,
    longitude: float,
    timezone_offset_h: float,
    tilt_deg: float,
    azimuth_deg: float,
    panel_count: int,
    panel_width_m: float,
    panel_height_m: float,
    panel_efficiency: float,
    sample_minutes: int,
) -> list[tuple[datetime, float, SolarState]]:
    """Sequence of (timestamp, power_w, state) for the reference-year date."""
    d = date(REFERENCE_YEAR, month, day)
    area = panel_count * panel_width_m * panel_height_m
    out: list[tuple[datetime, float, SolarState]] = []
    for dt in iter_sample_times(d, sample_minutes):
        p, st = compute_power_w_at_instant(
            when=dt,
            day_of_year=_day_of_year(d),
            latitude=latitude,
            longitude=longitude,
            timezone_offset_h=timezone_offset_h,
            tilt_deg=tilt_deg,
            azimuth_deg=azimuth_deg,
            total_panel_area_m2=area,
            panel_efficiency=panel_efficiency,
        )
        out.append((dt, p, st))
    return out


def validate_md(month: int, day: int) -> None:
    if month == 2 and day == 29:
        raise ValueError("Day 29 of February is not valid (use non-leap year).")
    date(REFERENCE_YEAR, month, day)  # invalid calendar date -> ValueError