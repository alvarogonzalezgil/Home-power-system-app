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

/**
 * Integral of max(P - thresholdW, 0) over sample segments (clipping / excess energy), kWh.
 */
export function excessEnergyKwh(
  points: PvCurvePoint[],
  thresholdW: number,
): EnergyIntegralResult {
  let kwh = 0;
  let partial = false;
  for (let i = 0; i < points.length - 1; i++) {
    const ptA = points[i]!;
    const ptB = points[i + 1]!;
    if (ptA.power_w == null || ptB.power_w == null) {
      partial = true;
      continue;
    }
    const dtH = (toMinutes(ptB.time) - toMinutes(ptA.time)) / 60;
    if (dtH <= 0) {
      partial = true;
      continue;
    }
    const a = ptA.power_w - thresholdW;
    const b = ptB.power_w - thresholdW;
    let wh = 0;
    if (a >= 0 && b >= 0) {
      wh = ((a + b) / 2) * dtH;
    } else if (a <= 0 && b <= 0) {
      wh = 0;
    } else if (a > 0 && b < 0) {
      const denom = a - b;
      if (denom !== 0) {
        wh = ((a * a) / denom) * dtH * 0.5;
      }
    } else if (a < 0 && b > 0) {
      const denom = b - a;
      if (denom !== 0) {
        wh = ((b * b) / denom) * dtH * 0.5;
      }
    }
    kwh += wh / 1000;
  }
  return { kwh, partial };
}

export function formatKwh(kwh: number): string {
  return `${kwh.toFixed(2)} kWh`;
}
