import { HttpErrorResponse } from '@angular/common/http';
import { CommonModule } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { PlotlyModule } from 'angular-plotly.js';
import { PvService } from '../../core/api/pv.service';
import { FoxessService } from '../../core/api/foxess.service';
import { formatKwh, integrateEnergyKwh } from '../../core/util/energy';
import {
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

  /** YYYY-MM-DD */
  readonly dateIso = signal(todayIsoLocal());
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);
  readonly foxessBanner = signal<string | null>(null);
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

    this.pv.getDay(year, month, day).subscribe({
      next: (theoretical: PvCurveResponse) => {
        this.foxess.getDay(iso).subscribe({
          next: (actual: PvCurveResponse) => {
            this.loading.set(false);
            this.metLabel.set(
              `${theoretical.date} — clear-sky theoretical vs FoxESS measured pvPower`,
            );
            this.applyChart(theoretical, actual);
          },
          error: (e: unknown) => {
            this.loading.set(false);
            const msg = this.detailFromHttp(e);
            this.foxessBanner.set(
              `Actual (FoxESS) unavailable — ${msg}. Showing theoretical curve only.`,
            );
            this.metLabel.set(
              `${theoretical.date} — theoretical only (FoxESS failed)`,
            );
            this.applyChart(theoretical, null);
          },
        });
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
        return 'could not reach API (status 0 — restart `ng serve` after updating env; ensure backend is on 8010)';
      }
      const d = e.error;
      if (d && typeof d === 'object' && 'detail' in d) {
        return String((d as { detail: string }).detail);
      }
      return e.message;
    }
    return String(e);
  }

  private applyChart(
    theoretical: PvCurveResponse,
    actual: PvCurveResponse | null,
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
    this.graphLayout.set({
      title: { text: 'PV power: theoretical vs FoxESS actual' },
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
