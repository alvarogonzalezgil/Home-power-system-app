"""Fetch and resample FoxESS pvPower history for overlay with theoretical PV."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any

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


def parse_foxess_timestamp(s: str | Any) -> datetime:
    """FoxESS returns UTC wall times as strings; normalize to aware UTC."""
    raw = str(s).strip()
    if raw.endswith("Z"):
        raw = raw[:-1]
        naive = datetime.strptime(raw[:19], "%Y-%m-%dT%H:%M:%S")
        return naive.replace(tzinfo=timezone.utc)
    raw = raw.replace("T", " ")
    if len(raw) >= 19:
        naive = datetime.strptime(raw[:19], "%Y-%m-%d %H:%M:%S")
        return naive.replace(tzinfo=timezone.utc)
    raise ValueError(f"Unrecognized FoxESS time: {s!r}")


def extract_pv_power_series(history_blocks: list[dict[str, Any]]) -> list[tuple[datetime, float]]:
    """Collect (utc_datetime, value) for variable pvPower from history/query result."""
    points: list[tuple[datetime, float]] = []
    for block in history_blocks:
        for ds in block.get("datas") or []:
            if ds.get("variable") != "pvPower":
                continue
            for pt in ds.get("data") or []:
                if pt is None:
                    continue
                t = parse_foxess_timestamp(pt["time"])
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
    raw_series = extract_pv_power_series(blocks)
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
