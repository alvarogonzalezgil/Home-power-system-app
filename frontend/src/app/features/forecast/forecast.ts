import { HttpErrorResponse } from '@angular/common/http';
import { CommonModule } from '@angular/common';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { PlotlyModule } from 'angular-plotly.js';
import { ForecastService } from '../../core/api/forecast.service';
import {
  ForecastPvDayResponse,
  ForecastPvModel,
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
  selector: 'app-forecast',
  imports: [CommonModule, FormsModule, PlotlyModule],
  templateUrl: './forecast.html',
  styleUrl: './forecast.scss',
})
export class Forecast implements OnInit {
  private readonly forecastApi = inject(ForecastService);

  readonly minIso = signal(todayIsoLocal());
  readonly maxIso = signal(shiftDateIso(todayIsoLocal(), 6));

  /** YYYY-MM-DD within [today, today+6] */
  readonly dateIso = signal(todayIsoLocal());
  readonly model = signal<ForecastPvModel>('components');
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);
  readonly metLabel = signal<string | null>(null);

  readonly graphData = signal<unknown[]>([]);
  readonly graphLayout = signal<Record<string, unknown>>({});

  readonly canPrev = computed(
    () => this.dateIso() > this.minIso() && !this.loading(),
  );
  readonly canNext = computed(
    () => this.dateIso() < this.maxIso() && !this.loading(),
  );

  ngOnInit(): void {
    this.load();
  }

  onDateIso(value: string): void {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) {
      return;
    }
    if (value < this.minIso() || value > this.maxIso()) {
      this.error.set(`Pick a date between ${this.minIso()} and ${this.maxIso()}.`);
      return;
    }
    this.dateIso.set(value);
    this.load();
  }

  shiftDay(deltaDays: number): void {
    const next = shiftDateIso(this.dateIso(), deltaDays);
    this.onDateIso(next);
  }

  onModel(value: ForecastPvModel): void {
    this.model.set(value);
    this.load();
  }

  private load(): void {
    const iso = this.dateIso();
    if (iso < this.minIso() || iso > this.maxIso()) {
      return;
    }

    this.loading.set(true);
    this.error.set(null);

    this.forecastApi.getDay(iso, this.model()).subscribe({
      next: (res: ForecastPvDayResponse) => {
        this.loading.set(false);
        const modelLabel =
          res.model === 'cloud_derate'
            ? 'cloud-cover derate on clear-sky'
            : 'irradiance components + temp derate';
        this.metLabel.set(`${res.date} — forecast (${modelLabel}) vs clear-sky reference`);
        this.applyChart(res);
      },
      error: (e: unknown) => {
        this.loading.set(false);
        this.graphData.set([]);
        this.graphLayout.set({});
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

  private applyChart(res: ForecastPvDayResponse): void {
    const x = res.forecast_points.map((p) => p.time);
    const traces: unknown[] = [
      {
        x,
        y: res.forecast_points.map((p) => p.power_w ?? 0),
        name: 'Forecast (weather)',
        type: 'scatter',
        mode: 'lines',
        line: { color: '#15803d', width: 2 },
      },
      {
        x,
        y: res.clear_sky_points.map((p) => p.power_w ?? 0),
        name: 'Clear-sky reference',
        type: 'scatter',
        mode: 'lines',
        line: { color: '#0ea5e9', width: 2, dash: 'dash' },
      },
    ];
    this.graphData.set(traces);
    this.graphLayout.set({
      title: { text: 'PV power forecast vs clear sky' },
      xaxis: { title: { text: 'Time (HH:MM)' } },
      yaxis: { title: { text: 'Power (W)' } },
      margin: { l: 60, r: 20, t: 50, b: 50 },
      autosize: true,
      legend: { orientation: 'h', y: -0.15 },
    });
  }
}
