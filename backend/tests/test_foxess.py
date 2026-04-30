"""Unit tests for FoxESS helpers (no live API calls)."""

from __future__ import annotations

import hashlib
from datetime import date, datetime, timezone
from unittest.mock import patch

import pytest

from app.integrations.foxess.client import FoxessAuthError, FoxessClient
from app.services import foxess_service


def test_auth_error_when_pat_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FOXESS_PAT", raising=False)
    with pytest.raises(FoxessAuthError, match="FOXESS_PAT"):
        FoxessClient()


def test_signature_md5_matches_spec() -> None:
    """FoxESS spec: md5 of path + LITERAL '\\r\\n' + token + LITERAL '\\r\\n' + timestamp."""
    token = "test-token"
    path = "/op/v0/device/list"
    with patch("app.integrations.foxess.client.time.time", return_value=1.5):
        c = FoxessClient(token=token)
        h = c._headers(path)
    ts = h["timestamp"]
    expected = hashlib.md5(
        f"{path}\\r\\n{token}\\r\\n{ts}".encode("utf-8")
    ).hexdigest()
    assert h["signature"] == expected
    assert ts == "1500"


def test_parse_foxess_timestamp_space_and_z() -> None:
    a = foxess_service.parse_foxess_timestamp("2025-04-07 14:30:00")
    assert a == datetime(2025, 4, 7, 14, 30, 0, tzinfo=timezone.utc)
    b = foxess_service.parse_foxess_timestamp("2025-04-07T14:30:00Z")
    assert b == datetime(2025, 4, 7, 14, 30, 0, tzinfo=timezone.utc)


def test_parse_foxess_timestamp_local_with_offset_suffix_cst() -> None:
    """CST+0800 example from FoxESS Open API doc."""
    t = foxess_service.parse_foxess_timestamp("2025-11-25 17:58:16 CST+0800")
    assert t.astimezone(timezone.utc) == datetime(
        2025, 11, 25, 9, 58, 16, tzinfo=timezone.utc
    )


def test_parse_foxess_timestamp_uk_bst_suffix() -> None:
    t = foxess_service.parse_foxess_timestamp("2026-04-29 13:00:00 BST+0100")
    assert t.astimezone(timezone.utc) == datetime(
        2026, 4, 29, 12, 0, 0, tzinfo=timezone.utc
    )


def test_parse_foxess_timestamp_default_offset_when_no_suffix() -> None:
    t = foxess_service.parse_foxess_timestamp(
        "2026-04-29 13:00:00", default_offset_h=1.0
    )
    assert t.astimezone(timezone.utc) == datetime(
        2026, 4, 29, 12, 0, 0, tzinfo=timezone.utc
    )


def test_resample_kw_to_w_with_local_offset_suffix() -> None:
    """BST+0100 wall times must bucket to the same local HH:MM labels (no +1 h bug)."""
    day = date(2026, 4, 29)
    tz_h = 1.0
    blocks = [
        {
            "deviceSN": "SN1",
            "datas": [
                {
                    "variable": "pvPower",
                    "data": [
                        {"time": "2026-04-29 13:05:00 BST+0100", "value": 2.0},
                    ],
                }
            ],
        }
    ]
    raw = foxess_service.extract_pv_power_series(blocks, default_offset_h=tz_h)
    out = foxess_service.resample_to_power_watts(
        raw, day, tz_h, 5, power_unit="kW"
    )
    idx = (13 * 60 + 5) // 5
    assert out[idx] == pytest.approx(2000.0)


def test_extract_pv_power_series() -> None:
    blocks = [
        {
            "deviceSN": "SN1",
            "datas": [
                {
                    "variable": "pvPower",
                    "data": [
                        {"time": "2025-04-07 12:00:00", "value": 2.0},
                        {"time": "2025-04-07 12:01:00", "value": 3.0},
                    ],
                },
                {"variable": "other", "data": [{"time": "2025-04-07 12:00:00", "value": 99}]},
            ],
        }
    ]
    pts = foxess_service.extract_pv_power_series(blocks)
    assert len(pts) == 2
    assert pts[0][1] == 2.0 and pts[1][1] == 3.0


def test_resample_kw_to_w_and_gap() -> None:
    """Two samples in same 5-min bucket -> mean kW then x1000 -> W."""
    day = date(2025, 4, 7)
    tz_h = 0.0
    samples = [
        (datetime(2025, 4, 7, 12, 1, tzinfo=timezone.utc), 2.0),
        (datetime(2025, 4, 7, 12, 3, tzinfo=timezone.utc), 4.0),
    ]
    out = foxess_service.resample_to_power_watts(
        samples, day, tz_h, 5, power_unit="kW"
    )
    # slot index for 12:00 = 12*12 = 144
    idx = (12 * 60) // 5
    assert out[idx] == pytest.approx(3000.0)  # mean 3 kW -> 3000 W
    assert out[0] is None


def test_post_raises_foxess_api_error_on_errno(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.integrations.foxess.client import FoxessApiError

    monkeypatch.setenv("FOXESS_PAT", "x")

    class FakeResp:
        status_code = 200
        text = "{}"

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"errno": 40256, "msg": "header bad"}

    class FakeClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def __enter__(self) -> FakeClient:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def post(self, url: str, json: object, headers: object) -> FakeResp:
            return FakeResp()

    monkeypatch.setattr("httpx.Client", FakeClient)
    c = FoxessClient(token="x")
    with pytest.raises(FoxessApiError, match="errno=40256"):
        c.list_devices()
