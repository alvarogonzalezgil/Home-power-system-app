"""Tests for clear-sky PV model."""

from __future__ import annotations

import pytest
from datetime import date, datetime, time, timedelta

from app.services.solar_calculator import (
    REFERENCE_YEAR,
    day_curve,
    dni_clearsky_kwm2,
    kasten_young_air_mass,
    validate_md,
    compute_power_w_at_instant,
    iter_sample_times,
)


def test_midnight_june21_power_zero() -> None:
    """Sun below horizon in UK; power should be zero at 00:00 on mid-summer night."""
    lat, lon, tz = 51.64, -1.31, 0.0
    june_21 = date(REFERENCE_YEAR, 6, 21)
    dt0 = datetime.combine(june_21, time(0, 0))
    doy = june_21.timetuple().tm_yday
    p, _ = compute_power_w_at_instant(
        when=dt0,
        day_of_year=doy,
        latitude=lat,
        longitude=lon,
        timezone_offset_h=tz,
        tilt_deg=40,
        azimuth_deg=225,
        total_panel_area_m2=16 * 1.722 * 1.134,
        panel_efficiency=0.207,
    )
    assert p == 0.0


def test_solar_noon_summer_power_positive() -> None:
    """At solar peak near noon in summer, clear-sky power is positive (UK)."""
    series = day_curve(
        6, 21,
        latitude=51.64, longitude=-1.31, timezone_offset_h=0.0,
        tilt_deg=40, azimuth_deg=225, panel_count=16,
        panel_width_m=1.722, panel_height_m=1.134, panel_efficiency=0.207,
        sample_minutes=5,
    )
    # Max around midday; take max of day
    max_p = max(p for _, p, _ in series)
    assert max_p > 0.0


def test_sunrise_ramp_monotone_morning() -> None:
    """
    In morning after first positive sample, 5-min samples should
    be non-decreasing (clear sky, no clouds).
    """
    series = day_curve(
        3, 21,  # vernal equinox: symmetric sun path
        latitude=51.64, longitude=-1.31, timezone_offset_h=0.0,
        tilt_deg=40, azimuth_deg=225, panel_count=16,
        panel_width_m=1.722, panel_height_m=1.134, panel_efficiency=0.207,
        sample_minutes=5,
    )
    powers = [p for _, p, _ in series]
    # find first two positive consecutive steps and check non-decrease until first local max
    idx_first = next(i for i, p in enumerate(powers) if p > 0)
    # for next ~20 points (1h40) expect roughly increasing until near local max
    sub = powers[idx_first : idx_first + 20]
    if len(sub) < 2:
        pytest.skip("Not enough morning samples after sunrise")
    for i in range(1, len(sub)):
        assert sub[i] >= sub[i - 1] * 0.99  # allow tiny float noise / slight dip


def test_spring_fall_symmetry_around_solar_noon() -> None:
    """Vernal and autumnal equinox same declination: peak power and shape roughly comparable."""
    s1 = day_curve(3, 20, 51.64, -1.31, 0, 40, 225, 16, 1.722, 1.134, 0.207, 5)
    s2 = day_curve(9, 22, 51.64, -1.31, 0, 40, 225, 16, 1.722, 1.134, 0.207, 5)
    m1 = max(p for _, p, _ in s1)
    m2 = max(p for _, p, _ in s2)
    assert m1 > 0 and m2 > 0
    assert 0.85 < m1 / m2 < 1.15  # not identical day length but same δ ≈ 0 (±1 day ok)


def test_feb_29_rejected() -> None:
    with pytest.raises(ValueError, match="February|29|invalid|Day"):
        validate_md(2, 29)
    with pytest.raises(ValueError):
        validate_md(2, 30)  # invalid month-day


def test_dni_kasten_zenith() -> None:
    """DNI and AM behave at a representative zenith."""
    am = kasten_young_air_mass(30.0)
    assert 0.9 < am < 2.0
    d = dni_clearsky_kwm2(am)
    assert 0.5 < d < 1.1


def test_iter_sample_count() -> None:
    d = date(2025, 1, 1)
    t = list(iter_sample_times(d, 5))
    assert len(t) == 24 * 12
    assert t[0] == datetime.combine(d, time(0, 0))
    assert t[-1].hour == 23 and t[-1].minute == 55
