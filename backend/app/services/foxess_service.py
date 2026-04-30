"""Fetch and resample FoxESS pvPower history for overlay with theoretical PV."""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

# Trailing zone suffix on FoxESS history times, e.g. ' BST+0100', ' CST+0800', ' +0100'.
_FOXESS_TZ_SUFFIX_RE = re.compile(
    r"\s*[A-Za-z]{0,5}\s*([+-])(\d{2}):?(\d{2})\s*$"
)

from app.integrations.foxess.client import FoxessApiError, FoxessClient
from app.models.schemas import SystemConfig
from app.services import config_store
from app.services.solar_calculator import iter_sample_times


def civil_day_bounds_utc_ms(day: date, timezone_offset_h: float) -> tuple[int, int]:
    """Local civil calendar day [day 00:00, next day 00:00) as UTC epoch ms."""
    tz = timezone(timedelta(hours=timezone_offset_h))
    start_local = datetime.combine(day, time.min, tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    start_utc = start_local.astimezone(timezone.utc)
    end_utc = end_local.astimezone(timezone.utc)
    return int(start_utc.timestamp() * 1000), int(end_utc.timestamp() * 1000)


def parse_foxess_timestamp(
    s: str | Any,
    default_offset_h: float | None = None,
) -> datetime:
    """
    Parse a FoxESS history ``time`` string.

    FoxESS often returns plant-local wall time with a trailing offset suffix,
    e.g. ``2026-04-29 13:00:00 BST+0100`` or ``2025-11-25 17:58:16 CST+0800``.
    Some payloads use ``YYYY-MM-DDTHH:MM:SSZ`` (UTC). If no suffix is present,
    ``default_offset_h`` is applied as the zone offset (hours east of UTC); if
    that is also ``None``, UTC is assumed (backward compatible).
    """
    raw = str(s).strip().replace("T", " ")
    if raw.endswith("Z"):
        wall = raw[:-1].rstrip()[:19]
        naive = datetime.strptime(wall, "%Y-%m-%d %H:%M:%S")
        return naive.replace(tzinfo=timezone.utc)

    m = _FOXESS_TZ_SUFFIX_RE.search(raw)
    if m:
        sign, hh_s, mm_s = m.group(1), m.group(2), m.group(3)
        hh, mm = int(hh_s), int(mm_s)
        delta = timedelta(hours=hh, minutes=mm)
        tzinfo = timezone(delta if sign == "+" else -delta)
        wall = raw[: m.start()].rstrip()[:19]
    elif default_offset_h is not None:
        tzinfo = timezone(timedelta(hours=default_offset_h))
        wall = raw[:19]
    else:
        tzinfo = timezone.utc
        wall = raw[:19]

    naive = datetime.strptime(wall, "%Y-%m-%d %H:%M:%S")
    return naive.replace(tzinfo=tzinfo)


def extract_pv_power_series(
    history_blocks: list[dict[str, Any]],
    default_offset_h: float | None = None,
) -> list[tuple[datetime, float]]:
    """Collect (aware datetime instant, value) for pvPower from history/query."""
    points: list[tuple[datetime, float]] = []
    for block in history_blocks:
        for ds in block.get("datas") or []:
            if ds.get("variable") != "pvPower":
                continue
            for pt in ds.get("data") or []:
                if pt is None:
                    continue
                t = parse_foxess_timestamp(pt["time"], default_offset_h)
                v = float(pt["value"])
                points.append((t, v))
    points.sort(key=lambda x: x[0])
    return points


def resample_to_power_watts(
    samples_kw_or_w: list[tuple[datetime, float]],
    day: date,
    timezone_offset_h: float,
    sample_minutes: int,
    *,
    power_unit: str,
) -> list[float | None]:
    """
    Mean power per clock bucket in local civil time; missing buckets -> None.
    Input values use FoxESS units (kW or W); output is always watts.
    """
    slots = 24 * 60 // sample_minutes
    tz_off = timezone(timedelta(hours=timezone_offset_h))
    buckets: list[list[float]] = [[] for _ in range(slots)]

    scale_to_w = 1000.0 if power_unit == "kW" else 1.0

    for utc_dt, raw_val in samples_kw_or_w:
        local = utc_dt.astimezone(tz_off)
        if local.date() != day:
            continue
        idx = (local.hour * 60 + local.minute) // sample_minutes
        if 0 <= idx < slots:
            buckets[idx].append(raw_val * scale_to_w)

    out: list[float | None] = []
    for b in buckets:
        if not b:
            out.append(None)
        else:
            out.append(sum(b) / len(b))
    return out


def resolve_sn(cfg: SystemConfig) -> tuple[str, SystemConfig]:
    """Return inverter SN; auto-detect first PV device and persist SN if missing."""
    if cfg.inverter_sn and str(cfg.inverter_sn).strip():
        return str(cfg.inverter_sn).strip(), cfg

    client = FoxessClient()
    devices = client.list_devices()
    pv_devices = [d for d in devices if d.get("hasPV")]
    if not pv_devices:
        raise FoxessApiError("No inverter with hasPV=true in FoxESS account")

    sn = str(pv_devices[0]["deviceSN"])
    updated = cfg.model_copy(update={"inverter_sn": sn})
    config_store.save_config(updated)
    return sn, updated


def get_actual_pv_curve_points(
    day: date,
    cfg: SystemConfig,
    sn: str,
) -> list[tuple[str, float | None]]:
    """288 (time HH:MM, power_w or None) aligned to cfg.sample_minutes."""
    begin_ms, end_ms = civil_day_bounds_utc_ms(day, cfg.timezone_offset_h)

    client = FoxessClient()
    blocks = client.history_query(
        sn,
        ["pvPower"],
        begin_ms,
        end_ms,
    )
    raw_series = extract_pv_power_series(blocks, cfg.timezone_offset_h)
    watts_per_slot = resample_to_power_watts(
        raw_series,
        day,
        cfg.timezone_offset_h,
        cfg.sample_minutes,
        power_unit=cfg.foxess_power_unit,
    )

    times = list(iter_sample_times(day, cfg.sample_minutes))
    if len(times) != len(watts_per_slot):
        raise FoxessApiError(
            f"Internal slot mismatch: times={len(times)} slots={len(watts_per_slot)}"
        )

    return [
        (dt.strftime("%H:%M"), (round(w, 2) if w is not None else None))
        for dt, w in zip(times, watts_per_slot)
    ]
