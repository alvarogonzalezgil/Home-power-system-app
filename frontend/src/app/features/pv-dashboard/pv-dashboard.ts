import { HttpErrorResponse } from '@angular/common/http';
import { CommonModule } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { PlotlyModule } from 'angular-plotly.js';
import { PvService } from '../../core/api/pv.service';
import { FoxessService } from '../../core/api/foxess.service';
import { ForecastService } from '../../core/api/forecast.service';
import { formatKwh, integrateEnergyKwh } from '../../core/util/energy';
import {
  ForecastPvDayResponse,
  PvCurvePoint,
  PvCurveResponse,
} from '../../core/models/pv-curve.model';

function todayIsoLocal(): string {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

/** Shift YYYY-MM-DD by whole calendar days in the browser local calendar. */
function shiftDateIso(iso: string, deltaDays: number): string {
  const parts = iso.split('-').map(Number);
  const y = parts[0]!;
  const mo = parts[1]!;
  const d = parts[2]!;
  const dt = new Date(y, mo - 1, d + deltaDays);
  const yy = dt.getFullYear();
  const mm = String(dt.getMonth() + 1).padStart(2, '0');
  const dd = String(dt.getDate()).padStart(2, '0');
  return `${yy}-${mm}-${dd}`;
}

@Component({
  selector: 'app-pv-dashboard',
  imports: [CommonModule, FormsModule, PlotlyModule],
  templateUrl: './pv-dashboard.html',
  styleUrl: './pv-dashboard.scss',
})
export class PvDashboard implements OnInit {
  private readonly pv = inject(PvService);
  private readonly foxess = inject(FoxessService);
  private readonly forecast = inject(ForecastService);

  /** YYYY-MM-DD */
  readonly dateIso = signal(todayIsoLocal());
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);
  readonly foxessBanner = signal<string | null>(null);
  /** Shown when Open-Meteo forecast fails (today only). */
  readonly forecastBanner = signal<string | null>(null);
  readonly metLabel = signal<string | null>(null);
  readonly dailyTotalsLabel = signal<string | null>(null);

  readonly graphData = signal<unknown[]>([]);
  readonly graphLayout = signal<Record<string, unknown>>({});

  ngOnInit(): void {
    this.load();
  }

  onDateIso(value: string): void {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) {
      return;
    }
    this.dateIso.set(value);
    this.load();
  }

  shiftDay(deltaDays: number): void {
    const next = shiftDateIso(this.dateIso(), deltaDays);
    this.onDateIso(next);
  }

  private load(): void {
    const iso = this.dateIso();
    const parts = iso.split('-').map(Number);
    const year = parts[0]!;
    const month = parts[1]!;
    const day = parts[2]!;

    this.loading.set(true);
    this.error.set(null);
    this.foxessBanner.set(null);
    this.forecastBanner.set(null);

    const isToday = iso === todayIsoLocal();

    this.pv.getDay(year, month, day).subscribe({
      next: (theoretical: PvCurveResponse) => {
        if (isToday) {
          let actual: PvCurveResponse | null = null;
          let forecastRes: ForecastPvDayResponse | null = null;
          let remaining = 2;
          const finishParallel = () => {
            remaining -= 1;
            if (remaining > 0) {
              return;
            }
            this.loading.set(false);
            this.setDashboardMetLabel(theoretical, actual, forecastRes, isToday);
            this.applyChart(theoretical, actual, forecastRes);
          };

          this.foxess.getDay(iso).subscribe({
            next: (a: PvCurveResponse) => {
              actual = a;
              finishParallel();
            },
            error: (e: unknown) => {
              this.foxessBanner.set(
                `Actual (FoxESS) unavailable — ${this.detailFromHttp(e)}. Showing theoretical and any forecast only.`,
              );
              finishParallel();
            },
          });
          this.forecast.getDay(iso, 'components').subscribe({
            next: (f: ForecastPvDayResponse) => {
              forecastRes = f;
              finishParallel();
            },
            error: (e: unknown) => {
              this.forecastBanner.set(
                `Weather forecast unavailable — ${this.detailFromHttp(e)}. Compare clear-sky and actual only.`,
              );
              finishParallel();
            },
          });
        } else {
          this.foxess.getDay(iso).subscribe({
            next: (a: PvCurveResponse) => {
              this.loading.set(false);
              this.setDashboardMetLabel(theoretical, a, null, false);
              this.applyChart(theoretical, a, null);
            },
            error: (e: unknown) => {
              this.loading.set(false);
              const msg = this.detailFromHttp(e);
              this.foxessBanner.set(
                `Actual (FoxESS) unavailable — ${msg}. Showing theoretical curve only.`,
              );
              this.setDashboardMetLabel(theoretical, null, null, false);
              this.applyChart(theoretical, null, null);
            },
          });
        }
      },
      error: (e: unknown) => {
        this.loading.set(false);
        this.graphData.set([]);
        this.graphLayout.set({});
        this.dailyTotalsLabel.set(null);
        if (e instanceof HttpErrorResponse) {
          const d = e.error;
          const msg =
            d && typeof d === 'object' && 'detail' in d
              ? String((d as { detail: string }).detail)
              : e.message;
          this.error.set(msg || 'Request failed');
        } else {
          this.error.set(String(e));
        }
      },
    });
  }

  private detailFromHttp(e: unknown): string {
    if (e instanceof HttpErrorResponse) {
      if (e.status === 0) {
        return 'could not reach API (status 0 — restart `ng serve` after updating env; ensure backend is on 8000)';
      }
      const d = e.error;
      if (d && typeof d === 'object' && 'detail' in d) {
        return String((d as { detail: string }).detail);
      }
      return e.message;
    }
    return String(e);
  }

  private setDashboardMetLabel(
    theoretical: PvCurveResponse,
    actual: PvCurveResponse | null,
    forecast: ForecastPvDayResponse | null,
    isToday: boolean,
  ): void {
    const d = theoretical.date;
    if (isToday) {
      if (forecast) {
        this.metLabel.set(
          `${d} — today: clear-sky theoretical, Open-Meteo forecast (components), and FoxESS measured pvPower`,
        );
      } else {
        this.metLabel.set(
          `${d} — today: clear-sky theoretical vs FoxESS (weather forecast unavailable)`,
        );
      }
    } else if (actual) {
      this.metLabel.set(`${d} — clear-sky theoretical vs FoxESS measured pvPower`);
    } else {
      this.metLabel.set(`${d} — theoretical only (FoxESS failed)`);
    }
  }

  private applyChart(
    theoretical: PvCurveResponse,
    actual: PvCurveResponse | null,
    forecast: ForecastPvDayResponse | null,
  ): void {
    const x = theoretical.points.map((p) => p.time);
    const traces: unknown[] = [
      {
        x,
        y: theoretical.points.map((p) => p.power_w ?? 0),
        name: 'Theoretical max (clear sky)',
        type: 'scatter',
        mode: 'lines',
        line: { color: '#0ea5e9', width: 2, dash: 'dash' },
      },
    ];
    if (forecast) {
      const fp = forecast.forecast_points;
      const xFc =
        fp.length === theoretical.points.length ? x : fp.map((p) => p.time);
      traces.push({
        x: xFc,
        y: fp.map((p) => p.power_w ?? 0),
        name: 'Forecast (Open-Meteo, components)',
        type: 'scatter',
        mode: 'lines',
        line: { color: '#d97706', width: 2 },
      });
    }
    if (actual) {
      traces.push({
        x,
        y: actual.points.map((p) => p.power_w),
        name: 'Actual (FoxESS)',
        type: 'scatter',
        mode: 'lines',
        line: { color: '#15803d', width: 2 },
        connectgaps: false,
      });
    }
    const peak = this.peakPoint(theoretical.points);
    if (peak) {
      traces.push({
        x: [peak.time],
        y: [peak.power_w],
        name: 'Theoretical peak',
        type: 'scatter',
        mode: 'markers+text',
        text: [`${peak.time} — ${(peak.power_w / 1000).toFixed(2)} kW`],
        textposition: 'top center',
        marker: {
          size: 11,
          color: '#dc2626',
          symbol: 'star',
          line: { color: '#7f1d1d', width: 1 },
        },
        hovertemplate:
          '%{x}<br>%{y:.0f} W<extra>Theoretical peak</extra>',
        showlegend: true,
      });
    }
    this.graphData.set(traces);
    const title =
      forecast && actual
        ? 'PV power: theoretical, forecast, and FoxESS'
        : forecast
          ? 'PV power: theoretical and weather forecast (today)'
          : actual
            ? 'PV power: theoretical vs FoxESS actual'
            : 'PV power: theoretical (clear sky)';
    this.graphLayout.set({
      title: { text: title },
      xaxis: { title: { text: 'Time (HH:MM)' } },
      yaxis: { title: { text: 'Power (W)' } },
      margin: { l: 60, r: 20, t: 50, b: 50 },
      autosize: true,
      legend: { orientation: 'h', y: -0.15 },
    });

    if (theoretical.points.length >= 2) {
      const th = integrateEnergyKwh(theoretical.points);
      const parts = [
        `Theoretical: ${formatKwh(th.kwh)}${th.partial ? ' (partial)' : ''}`,
      ];
      if (forecast && forecast.forecast_points.length >= 2) {
        const fc = integrateEnergyKwh(forecast.forecast_points);
        parts.push(`Forecast: ${formatKwh(fc.kwh)}${fc.partial ? ' (partial)' : ''}`);
      }
      if (actual) {
        const ac = integrateEnergyKwh(actual.points);
        parts.push(`Actual: ${formatKwh(ac.kwh)}${ac.partial ? ' (partial)' : ''}`);
      }
      this.dailyTotalsLabel.set(parts.join('   ·   '));
    } else {
      this.dailyTotalsLabel.set(null);
    }
  }

  private peakPoint(points: PvCurvePoint[]): { time: string; power_w: number } | null {
    let best: { time: string; power_w: number } | null = null;
    for (const p of points) {
      const v = p.power_w;
      if (v == null) {
        continue;
      }
      if (!best || v > best.power_w) {
        best = { time: p.time, power_w: v };
      }
    }
    return best;
  }
}
