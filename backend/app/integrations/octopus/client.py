"""Octopus Energy public REST client (half-hour unit rates — no auth)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin

import httpx

from app.integrations.http_verify import build_default_verify

BASE = "https://api.octopus.energy"


class OctopusError(RuntimeError):
    """Rates fetch or JSON parse failure."""


@dataclass(frozen=True)
class UnitRateHalfHour:
    """One row from ``standard-unit-rates``."""

    valid_from_utc: datetime  # timezone-aware UTC
    valid_to_utc: datetime
    value_inc_vat_gbp_per_kwh: float  # GBP; multiply by 100 for p/kWh UI


def _parse_dt(s: str) -> datetime:
    raw = (s or "").strip().replace("+00:00", "Z")
    if raw.endswith("Z"):
        raw = raw[:-1]
    dt = datetime.fromisoformat(raw)
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(
        timezone.utc
    )


def fetch_standard_unit_rates(
    product_code: str,
    tariff_code: str,
    *,
    period_from_utc_iso: str,
    period_to_utc_iso: str,
) -> list[UnitRateHalfHour]:
    """
    Paginate GET
    ``/v1/products/{product_code}/electricity-tariffs/{tariff_code}/standard-unit-rates/``.

    Octopus exposes half-hour slices with ``valid_from``, ``valid_to``,
    ``value_inc_vat`` in GBP per kWh.
    """
    product_c = product_code.strip()
    path = (
        f"/v1/products/{product_c}/electricity-tariffs/"
        f"{tariff_code}/standard-unit-rates/"
    )
    params_start: dict[str, Any] = {
        "period_from": period_from_utc_iso,
        "period_to": period_to_utc_iso,
        "page_size": 250,
    }
    rows: list[UnitRateHalfHour] = []
    url = BASE + path
    next_url: str | None = None
    try:
        with httpx.Client(
            timeout=httpx.Timeout(30.0), verify=build_default_verify()
        ) as client:
            while True:
                if next_url:
                    resp = client.get(next_url)
                else:
                    resp = client.get(url, params=params_start)
                resp.raise_for_status()
                data = resp.json()
                for rw in data.get("results") or []:
                    rows.append(
                        UnitRateHalfHour(
                            valid_from_utc=_parse_dt(str(rw.get("valid_from", ""))),
                            valid_to_utc=_parse_dt(str(rw.get("valid_to", ""))),
                            value_inc_vat_gbp_per_kwh=float(rw["value_inc_vat"]),
                        )
                    )
                next_rel = data.get("next")
                if not next_rel:
                    break
                next_url = next_rel if str(next_rel).startswith("http") else urljoin(
                    BASE + "/", next_rel.lstrip("/")
                )
            return rows
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise OctopusError(
                "Octopus tariff not found ("
                f"{tariff_code}) — check Settings: import/export product "
                "code and GB DNO region letter (A–H, J–N, P)."
            ) from e
        snippet = (e.response.text or "").strip()
        if snippet.startswith("<!DOCTYPE") or snippet.startswith("<!doctype"):
            snippet = "HTML error page (non-JSON response)."
        else:
            snippet = snippet[:300]
        raise OctopusError(
            f"Octopus HTTP {e.response.status_code} for "
            f"{product_c}/{tariff_code}: {snippet}"
        ) from e
    except httpx.RequestError as e:
        raise OctopusError(f"Octopus request failed: {e}") from e


def tariff_code_for_region(product_code: str, region: str) -> str:
    region_u = region.strip().upper()
    product_c = product_code.strip()
    return f"E-1R-{product_c}-{region_u}"
