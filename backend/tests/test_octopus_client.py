"""Octopus REST client URL shape and errors."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.integrations.octopus.client import OctopusError, fetch_standard_unit_rates


def test_fetch_standard_unit_rates_uses_product_scoped_path() -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value={"results": [], "next": None})
    mock_client = MagicMock()
    mock_client.get = MagicMock(return_value=mock_resp)

    with patch("app.integrations.octopus.client.httpx.Client") as client_cls:
        client_cls.return_value.__enter__.return_value = mock_client
        client_cls.return_value.__exit__.return_value = None
        fetch_standard_unit_rates(
            "FLUX-IMPORT-23-02-14",
            "E-1R-FLUX-IMPORT-23-02-14-K",
            period_from_utc_iso="2026-05-01T00:00:00Z",
            period_to_utc_iso="2026-05-02T00:00:00Z",
        )

    first_url = mock_client.get.call_args_list[0][0][0]
    assert first_url == (
        "https://api.octopus.energy/v1/products/FLUX-IMPORT-23-02-14/"
        "electricity-tariffs/E-1R-FLUX-IMPORT-23-02-14-K/standard-unit-rates/"
    )
    params = mock_client.get.call_args_list[0][1]["params"]
    assert params["period_from"] == "2026-05-01T00:00:00Z"
    assert params["period_to"] == "2026-05-02T00:00:00Z"


def test_fetch_standard_unit_rates_404_actionable_message() -> None:
    mock_client = MagicMock()

    def _get_fail(url: str, params=None):
        req = httpx.Request("GET", url)
        r = httpx.Response(404, request=req, text="<!doctype html>")
        raise httpx.HTTPStatusError(
            "Not Found",
            request=req,
            response=r,
        )

    mock_client.get = MagicMock(side_effect=_get_fail)

    with patch("app.integrations.octopus.client.httpx.Client") as client_cls:
        client_cls.return_value.__enter__.return_value = mock_client
        client_cls.return_value.__exit__.return_value = None
        with pytest.raises(OctopusError) as exc_info:
            fetch_standard_unit_rates(
                "X",
                "E-1R-Y-K",
                period_from_utc_iso="2026-05-01T00:00:00Z",
                period_to_utc_iso="2026-05-02T00:00:00Z",
            )

    assert "Octopus tariff not found" in str(exc_info.value)
