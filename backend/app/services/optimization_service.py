"""Advisory Octopus Flux + PV clipping optimization for a calendar day."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

from app.integrations.octopus.client import (
    UnitRateHalfHour,
    fetch_standard_unit_rates,
    tariff_code_for_region,
)
from app.models.schemas import (
    OptimizationDayResponse,
    OptimizationEstimates,
    OptimizationHalfHour,
    OptimizationRecommendation,
    SystemConfig,
)
from app.services.forecast_service import (
    ForecastError,
    predicted_curve_components,
    validate_forecast_day,
)
from app.services.solar_calculator import validate_ymd

# windows in local-clock hours since midnight [start, end)
_OVERNIGHT_IMP = (2.0, 6.0)
_DAYTIME_IMP_FOR_CLIP = (7.5, 19.5)
_PEAK_EXP = (16.0, 20.0)


class OptimizationError(RuntimeError):
    """Build failure (rates, forecast, or validation)."""


def _cfg_tz(cfg: SystemConfig) -> timezone:
    return timezone(timedelta(hours=cfg.timezone_offset_h))


def _local_day_utc_bounds(day: date, cfg: SystemConfig) -> tuple[datetime, datetime]:
    tz = _cfg_tz(cfg)
    start = datetime.combine(day, time(0, 0), tzinfo=tz)
    end = start + timedelta(days=1)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def _period_params(day: date, cfg: SystemConfig) -> tuple[str, str]:
    u0, u1 = _local_day_utc_bounds(day, cfg)
    return (
        u0.strftime("%Y-%m-%dT%H:%M:%SZ"),
        u1.strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


def _to_minutes(hhmm: str) -> int:
    parts = hhmm.strip().split(":")
    h = int(parts[0])
    m = int(parts[1]) if len(parts) > 1 else 0
    return h * 60 + m


def excess_energy_kwh(
    pairs: list[tuple[str, float | None]],
    threshold_w: float,
) -> tuple[float, bool]:
    """Integral of max(P − threshold, 0) over trapezoids; mirrors frontend ``excessEnergyKwh``."""
    kwh = 0.0
    partial = False
    for i in range(len(pairs) - 1):
        t_a, p_a = pairs[i]
        t_b, p_b = pairs[i + 1]
        if p_a is None or p_b is None:
            partial = True
            continue
        dt_h = (_to_minutes(t_b) - _to_minutes(t_a)) / 60.0
        if dt_h <= 0:
            partial = True
            continue
        a = p_a - threshold_w
        b = p_b - threshold_w
        if a >= 0 and b >= 0:
            wh = ((a + b) / 2.0) * dt_h
        elif a <= 0 and b <= 0:
            wh = 0.0
        elif a > 0 and b < 0:
            denom = a - b
            wh = (((a * a) / denom) * dt_h * 0.5) if denom != 0 else 0.0
        elif a < 0 and b > 0:
            denom = b - a
            wh = (((b * b) / denom) * dt_h * 0.5) if denom != 0 else 0.0
        else:
            wh = 0.0
        kwh += wh / 1000.0
    return kwh, partial


def _weighted_avg_gbp(
    interval_start: datetime,
    interval_end: datetime,
    rates: list[UnitRateHalfHour],
) -> float | None:
    """Average GBP/kWh weighted by overlap; None if interval empty or uncovered."""
    if interval_end <= interval_start:
        return None
    total_s = (interval_end - interval_start).total_seconds()
    if total_s <= 0:
        return None
    acc = 0.0
    covered = 0.0
    for r in rates:
        lo = max(r.valid_from_utc, interval_start)
        hi = min(r.valid_to_utc, interval_end)
        if hi > lo:
            w = (hi - lo).total_seconds() / total_s
            acc += w * r.value_inc_vat_gbp_per_kwh
            covered += (hi - lo).total_seconds()
    if covered < total_s * 0.999:
        return None
    return acc


def _flux_import_band(mid_local: datetime) -> str:
    h = mid_local.hour + mid_local.minute / 60.0 + mid_local.second / 3600.0
    if _OVERNIGHT_IMP[0] <= h < _OVERNIGHT_IMP[1]:
        return "Cheap import window"
    if _PEAK_EXP[0] <= h < _PEAK_EXP[1]:
        return "Peak import window"
    return "Standard import"


def _flux_export_band(mid_local: datetime) -> str:
    h = mid_local.hour + mid_local.minute / 60.0 + mid_local.second / 3600.0
    if _PEAK_EXP[0] <= h < _PEAK_EXP[1]:
        return "Peak export window"
    if _OVERNIGHT_IMP[0] <= h < _OVERNIGHT_IMP[1]:
        return "Overnight export"
    return "Off-peak / shoulder export"


def _pv_kw_half_hours(pairs: list[tuple[str, float | None]]) -> tuple[list[float | None], list[bool]]:
    """Bucket mean PV power (kW) per half-hour start; marks partial buckets."""
    slot_sum = [0.0] * 48
    slot_n = [0] * 48
    partial = [False] * 48
    for hhmm, p in pairs:
        m = _to_minutes(hhmm)
        idx = min(47, m // 30)
        if m < 0 or m >= 24 * 60:
            partial[idx] = True
            continue
        if p is None:
            partial[idx] = True
            continue
        slot_sum[idx] += p
        slot_n[idx] += 1
    out_kw: list[float | None] = []
    out_part: list[bool] = []
    for i in range(48):
        if slot_n[i] == 0:
            out_kw.append(None)
            out_part.append(True)
        else:
            out_kw.append(round((slot_sum[i] / slot_n[i]) / 1000.0, 3))
            out_part.append(partial[i])
    return out_kw, out_part


def _window_avg_prices_pp(
    half_hours: list[OptimizationHalfHour],
    *,
    use_import: bool,
    h0: float,
    h1: float,
) -> float | None:
    ps: list[float] = []
    for row in half_hours:
        t = datetime.fromisoformat(row.interval_start_iso.replace("Z", "+00:00"))
        h = (t.hour + t.minute / 60.0) % 24.0
        if not (h0 <= h < h1):
            continue
        pp = row.import_p_per_kwh if use_import else row.export_p_per_kwh
        if pp is not None:
            ps.append(pp)
    if not ps:
        return None
    return round(sum(ps) / len(ps), 2)


@dataclass(frozen=True)
class _RecoCtx:
    spread_pp: float | None
    rte: float
    clipped_kwh: float
    overnight_imp: float | None
    peak_exp: float | None


def _recommendations(ctx: _RecoCtx) -> list[OptimizationRecommendation]:
    recs: list[OptimizationRecommendation] = []
    recs.append(
        OptimizationRecommendation(
            title="Advisory only",
            detail=(
                "Suggestions use published Octopus standing rates and weather PV forecast; "
                "they do not control your inverter or charger. Confirm prices in your "
                "Octopus account — product codes vary by tariff version."
            ),
        )
    )
    if ctx.clipped_kwh >= 0.05:
        recs.append(
            OptimizationRecommendation(
                title="Forecast PV clipping (inverter AC cap)",
                detail=(
                    f"About {ctx.clipped_kwh:.2f} kWh sits above your configured inverter AC cap "
                    "today — pre-cooling discharge or load shifting overnight can soak more of it "
                    "(advisory only)."
                ),
            )
        )
    if ctx.spread_pp is not None and ctx.overnight_imp is not None and ctx.peak_exp is not None:
        rte = ctx.rte
        marginal = ctx.peak_exp * rte - ctx.overnight_imp / rte if rte > 1e-6 else None
        if marginal is not None and marginal > 1.5:
            recs.append(
                OptimizationRecommendation(
                    title="Rate spread vs round-trip losses",
                    detail=(
                        f"Overnight import avg ~{ctx.overnight_imp:.2f}p vs peak export "
                        f"~{ctx.peak_exp:.2f}p (spread ~{ctx.spread_pp:.2f}p); at RTE "
                        f"{rte:.0%} this can favour charging cheap and discharging into peak export "
                        "subject to your equipment limits and comfort."
                    ),
                )
            )
        elif marginal is not None and marginal <= 0:
            recs.append(
                OptimizationRecommendation(
                    title="Limited full-cycle arbitrage on published averages",
                    detail=(
                        "Today's average overnight import vs peak export (after a simple "
                        "round-trip efficiency factor) does not suggest a large spread — "
                        "still check individual half-hours on the chart."
                    ),
                )
            )
    return recs


def build_optimization_day(cfg: SystemConfig, day: date) -> OptimizationDayResponse:
    validate_ymd(day.year, day.month, day.day)
    try:
        validate_forecast_day(day)
    except ForecastError as e:
        raise OptimizationError(str(e)) from e

    tariff_imp = tariff_code_for_region(cfg.octopus_import_product, cfg.octopus_region)
    tariff_exp = tariff_code_for_region(cfg.octopus_export_product, cfg.octopus_region)
    pf, pt = _period_params(day, cfg)
    try:
        imp_rates = fetch_standard_unit_rates(
            cfg.octopus_import_product.strip(),
            tariff_imp,
            period_from_utc_iso=pf,
            period_to_utc_iso=pt,
        )
        exp_rates = fetch_standard_unit_rates(
            cfg.octopus_export_product.strip(),
            tariff_exp,
            period_from_utc_iso=pf,
            period_to_utc_iso=pt,
        )
    except Exception as e:
        raise OptimizationError(f"Octopus rates: {e}") from e

    try:
        fc_pairs, _ref = predicted_curve_components(cfg, day)
    except ForecastError as e:
        raise OptimizationError(str(e)) from e

    threshold_w = cfg.inverter_capacity_kw * 1000.0
    clipped_kwh, clip_partial = excess_energy_kwh(fc_pairs, threshold_w)
    pv_kw_slots, _ = _pv_kw_half_hours(fc_pairs)
    usable_kwh = cfg.battery_capacity_kwh * max(0.0, (100.0 - cfg.battery_min_soc_pct)) / 100.0

    if usable_kwh > 1e-6:
        ratio = max(0.0, min(1.5, clipped_kwh / usable_kwh))
        headroom = cfg.battery_min_soc_pct + (100.0 - cfg.battery_min_soc_pct) * min(
            1.0, ratio * 0.65
        )
        headroom_hint = round(max(cfg.battery_min_soc_pct + 5.0, min(95.0, headroom)), 1)
    else:
        headroom_hint = float(cfg.battery_min_soc_pct)

    tz = _cfg_tz(cfg)
    hh_rows: list[OptimizationHalfHour] = []
    start_local = datetime.combine(day, time(0, 0), tzinfo=tz)
    for slot in range(48):
        t0_loc = start_local + timedelta(minutes=30 * slot)
        t1_loc = t0_loc + timedelta(minutes=30)
        u0, u1 = t0_loc.astimezone(timezone.utc), t1_loc.astimezone(timezone.utc)
        mid_loc = t0_loc + timedelta(minutes=15)

        avg_imp_gbp = _weighted_avg_gbp(u0, u1, imp_rates)
        avg_exp_gbp = _weighted_avg_gbp(u0, u1, exp_rates)

        hh_rows.append(
            OptimizationHalfHour(
                interval_start_iso=t0_loc.isoformat(timespec="minutes"),
                label_hhmm=t0_loc.strftime("%H:%M"),
                import_p_per_kwh=(
                    None if avg_imp_gbp is None else round(avg_imp_gbp * 100.0, 3)
                ),
                export_p_per_kwh=(
                    None if avg_exp_gbp is None else round(avg_exp_gbp * 100.0, 3)
                ),
                import_band=_flux_import_band(mid_loc),
                export_band=_flux_export_band(mid_loc),
                pv_kw=pv_kw_slots[slot],
            )
        )

    overnight_imp = _window_avg_prices_pp(
        hh_rows, use_import=True, h0=_OVERNIGHT_IMP[0], h1=_OVERNIGHT_IMP[1]
    )
    peak_exp = _window_avg_prices_pp(
        hh_rows, use_import=False, h0=_PEAK_EXP[0], h1=_PEAK_EXP[1]
    )
    day_imp_clip = _window_avg_prices_pp(
        hh_rows, use_import=True, h0=_DAYTIME_IMP_FOR_CLIP[0], h1=_DAYTIME_IMP_FOR_CLIP[1]
    )
    spread_pp = (
        round(peak_exp - overnight_imp, 2)
        if peak_exp is not None and overnight_imp is not None
        else None
    )
    clip_value_p = (
        round(clipped_kwh * day_imp_clip / 100.0, 1)
        if day_imp_clip is not None
        else None
    )

    est = OptimizationEstimates(
        clipped_pv_energy_kwh=round(clipped_kwh, 4),
        clipped_energy_partial_forecast=clip_partial,
        usable_battery_energy_kwh=round(usable_kwh, 4),
        target_soc_headroom_pct_hint=headroom_hint,
        overnight_import_avg_p_per_kwh=overnight_imp,
        peak_export_avg_p_per_kwh=peak_exp,
        theoretical_arbitrage_spread_pp=spread_pp,
        clipped_value_vs_grid_import_pence=clip_value_p,
    )
    reco = _recommendations(
        _RecoCtx(
            spread_pp=spread_pp,
            rte=cfg.battery_round_trip_efficiency,
            clipped_kwh=clipped_kwh,
            overnight_imp=overnight_imp,
            peak_exp=peak_exp,
        )
    )

    return OptimizationDayResponse(
        date=day.isoformat(),
        tariff_code_import=tariff_imp,
        tariff_code_export=tariff_exp,
        half_hours=hh_rows,
        recommendations=reco,
        estimates=est,
    )
