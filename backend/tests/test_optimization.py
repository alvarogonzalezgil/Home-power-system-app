"""Tests for advisory optimization (Octopus + forecast blending)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.integrations.octopus.client import UnitRateHalfHour
from app.main import app
from app.models.schemas import SystemConfig
from app.services.optimization_service import excess_energy_kwh


def test_excess_energy_above_threshold_rectangle() -> None:
    pairs = [
        ("10:00", 8000.0),
        ("10:30", 8000.0),
    ]
    kwh, partial = excess_energy_kwh(pairs, 5000.0)
    assert partial is False
    assert kwh == pytest.approx(1.5, rel=1e-6)


def test_optimization_endpoint_builds_curve(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    day = date.today() + timedelta(days=2)

    def fake_fetch(
        product_code: str,
        tariff_code: str,
        *,
        period_from_utc_iso: str,
        period_to_utc_iso: str,
    ):
        _ = product_code
        start = datetime.fromisoformat(
            period_from_utc_iso.replace("Z", "+00:00")
        ).astimezone(timezone.utc)
        end = datetime.fromisoformat(
            period_to_utc_iso.replace("Z", "+00:00")
        ).astimezone(timezone.utc)
        gbp_imp = 0.21
        gbp_exp = 0.12
        if "IMPORT" not in tariff_code.upper():
            return [UnitRateHalfHour(start, end, gbp_exp)]
        return [UnitRateHalfHour(start, end, gbp_imp)]
    monkeypatch.setattr(
        "app.services.optimization_service.fetch_standard_unit_rates",
        fake_fetch,
    )

    def fake_pc(_cfg: SystemConfig, _day: date, hourly=None):
        pairs = []
        for h in range(24):
            for m in range(0, 60, 5):
                pairs.append((f"{h:02d}:{m:02d}", 1200.0))
        return pairs, pairs

    monkeypatch.setattr(
        "app.services.optimization_service.predicted_curve_components",
        fake_pc,
    )

    def fake_cfg() -> SystemConfig:
        return SystemConfig(
            latitude=51.5,
            longitude=-1.2,
            tilt_deg=40.0,
            azimuth_deg=180.0,
            panel_count=10,
            panel_width_m=1.0,
            panel_height_m=1.7,
            panel_efficiency=0.2,
            timezone_offset_h=1.0,
            sample_minutes=5,
            inverter_capacity_kw=5.0,
            battery_capacity_kwh=5.2,
            battery_min_soc_pct=10.0,
            battery_round_trip_efficiency=0.88,
            octopus_region="K",
            octopus_import_product="FLUX-IMPORT-23-02-14",
            octopus_export_product="FLUX-EXPORT-23-02-14",
        )

    monkeypatch.setattr("app.api.optimization.config_store.load_config", fake_cfg)

    client = TestClient(app)
    r = client.get("/api/optimization/today", params={"date": day.isoformat()})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["date"] == day.isoformat()
    assert len(data["half_hours"]) == 48
    assert data["tariff_code_import"].startswith("E-1R-")
    assert data["estimates"]["clipped_pv_energy_kwh"] == 0.0
    assert data["half_hours"][0]["import_p_per_kwh"] == pytest.approx(21.0, rel=1e-3)


def test_config_store_rejects_bad_region(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from pathlib import Path

    from app.services import config_store

    p = tmp_path / "cfg.json"
    p.write_text(
        '{"latitude":0,"longitude":0,"tilt_deg":30,"azimuth_deg":180,'
        '"panel_count":1,"panel_width_m":1,"panel_height_m":1,"panel_efficiency":0.2,'
        '"timezone_offset_h":0,"sample_minutes":5,"octopus_region":"I"}',
        encoding="utf-8",
    )
    monkeypatch.setattr(config_store, "CONFIG_PATH", Path(str(p)))
    with pytest.raises(Exception):
        config_store.load_config()
