import { PvCurvePoint } from '../models/pv-curve.model';

export interface EnergyIntegralResult {
  /** Daily energy from trapezoidal integration of W vs time (kWh). */
  kwh: number;
  /** True if any segment was skipped (null endpoint or non-positive dt). */
  partial: boolean;
}

function toMinutes(hhmm: string): number {
  const parts = hhmm.split(':').map(Number);
  const h = parts[0] ?? 0;
  const m = parts[1] ?? 0;
  return h * 60 + m;
}

/**
 * Trapezoidal integral of average power (W) vs HH:MM samples → energy (kWh).
 * Skips segments with null power_w at either end.
 */
export function integrateEnergyKwh(points: PvCurvePoint[]): EnergyIntegralResult {
  let kwh = 0;
  let partial = false;
  for (let i = 0; i < points.length - 1; i++) {
    const a = points[i]!;
    const b = points[i + 1]!;
    if (a.power_w == null || b.power_w == null) {
      partial = true;
      continue;
    }
    const dtH = (toMinutes(b.time) - toMinutes(a.time)) / 60;
    if (dtH <= 0) {
      partial = true;
      continue;
    }
    kwh += ((a.power_w + b.power_w) / 2) * dtH / 1000;
  }
  return { kwh, partial };
}

export function formatKwh(kwh: number): string {
  return `${kwh.toFixed(2)} kWh`;
}
