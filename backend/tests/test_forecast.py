"""Tests for Open-Meteo forecast helpers and API."""

from __future__ import annotations

import math
from datetime import date
from unittest.mock import MagicMock

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.forecast_service import (
    ForecastError,
    cloud_cover_derate_factor,
    fetch_open_meteo_hourly,
    poa_components_wm2,
    power_from_poa_wm2,
)


def test_components_known_inputs_poa_formula() -> None:
    """POA = DNI*cos(theta) + DHI*(1+cos b)/2 + GHI*rho*(1-cos b)/2."""
    cos_theta = 0.9
    tilt_deg = 30.0
    beta = math.radians(tilt_deg)
    cos_b = math.cos(beta)
    expected = (
        800.0 * cos_theta
        + 100.0 * (1.0 + cos_b) / 2.0
        + 500.0 * 0.2 * (1.0 - cos_b) / 2.0
    )
    poa = poa_components_wm2(800.0, 100.0, 500.0, cos_theta, tilt_deg)
    assert poa == pytest.approx(expected, rel=1e-9)


def test_cloud_derate_extremes() -> None:
    assert cloud_cover_derate_factor(0.0) == pytest.approx(1.0)
    assert cloud_cover_derate_factor(100.0) == pytest.approx(1.0 - 0.75 * (1.0**3.4))


def test_temp_derate_at_25c() -> None:
    poa = 600.0
    area = 10.0
    eff = 0.2
    raw = poa * area * eff
    assert power_from_poa_wm2(poa, area, eff, 25.0) == pytest.approx(raw)


def test_open_meteo_url_and_parse(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_get(self: httpx.Client, url: str, params: object | None = None) -> MagicMock:
        captured["url"] = url
        captured["params"] = params
        resp = MagicMock()
        resp.status_code = 200

        def json_fn() -> dict:
            return {
                "hourly": {
                    "time": ["2025-06-01T10:00", "2025-06-01T11:00"],
                    "temperature_2m": [20.0, 21.0],
                    "cloud_cover": [10.0, 20.0],
                    "shortwave_radiation": [400.0, 450.0],
                    "direct_normal_irradiance": [700.0, 720.0],
                    "diffuse_radiation": [80.0, 85.0],
                    "wind_speed_10m": [2.0, 2.5],
                }
            }

        resp.json = json_fn
        resp.raise_for_status = MagicMock()
        return resp

    monkeypatch.setattr(httpx.Client, "get", fake_get)
    samples = fetch_open_meteo_hourly(51.5, -1.2)
    assert len(samples) == 2
    assert samples[0].temp_c == 20.0
    assert samples[0].ghi_wm2 == 400.0

    assert "/forecast" in str(captured["url"])
    params = captured["params"]
    assert isinstance(params, dict)
    assert params.get("forecast_days") == 16
    assert params.get("timezone") == "UTC"
    hourly = str(params.get("hourly", ""))
    for key in (
        "temperature_2m",
        "cloud_cover",
        "shortwave_radiation",
        "direct_normal_irradiance",
        "diffuse_radiation",
        "wind_speed_10m",
    ):
        assert key in hourly


def test_forecast_error_on_http_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    req = httpx.Request("GET", "https://api.open-meteo.com/v1/forecast")
    bad = httpx.Response(502, request=req)

    def fake_get(self: httpx.Client, url: str, params: object | None = None) -> MagicMock:
        resp = MagicMock()
        resp.status_code = 502

        def raise_status() -> None:
            raise httpx.HTTPStatusError("bad", request=req, response=bad)

        resp.raise_for_status = raise_status
        return resp

    monkeypatch.setattr(httpx.Client, "get", fake_get)
    with pytest.raises(ForecastError, match="502"):
        fetch_open_meteo_hourly(0.0, 0.0)


def test_api_maps_forecast_error_to_502(monkeypatch: pytest.MonkeyPatch) -> None:
    today = date.today().isoformat()

    def boom(_cfg: object, _d: date) -> tuple[list, list]:
        raise ForecastError("upstream down")

    monkeypatch.setattr(
        "app.api.forecast.predicted_curve_components",
        boom,
    )
    client = TestClient(app)
    r = client.get("/api/forecast/pv/day", params={"date": today, "model": "components"})
    assert r.status_code == 502
    assert r.json()["detail"] == "upstream down"


def test_api_bad_calendar_date_returns_400() -> None:
    client = TestClient(app)
    r = client.get("/api/forecast/pv/day", params={"date": "2025-02-30"})
    assert r.status_code == 400
