import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { PlotlyModule } from 'angular-plotly.js';
import { OptimizationService } from '../../core/api/optimization.service';
import {
  OptimizationDayResponseModel,
  OptimizationHalfHourRow,
} from '../../core/models/optimization.model';

function todayIsoLocal(): string {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

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

function formatPp(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) {
    return '—';
  }
  return `${v.toFixed(2)}p`;
}

@Component({
  selector: 'app-optimization',
  imports: [CommonModule, FormsModule, PlotlyModule],
  templateUrl: './optimization.html',
  styleUrl: './optimization.scss',
})
export class Optimization implements OnInit {
  private readonly api = inject(OptimizationService);

  readonly minIso = signal(todayIsoLocal());
  readonly maxIso = signal(shiftDateIso(todayIsoLocal(), 6));
  readonly dateIso = signal(todayIsoLocal());
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);
  readonly payload = signal<OptimizationDayResponseModel | null>(null);

  readonly graphData = signal<unknown[]>([]);
  readonly graphLayout = signal<Record<string, unknown>>({});

  readonly canPrev = computed(
    () => this.dateIso() > this.minIso() && !this.loading(),
  );
  readonly canNext = computed(
    () => this.dateIso() < this.maxIso() && !this.loading(),
  );

  readonly tickerLine = computed(() => {
    const res = this.payload();
    if (!res?.half_hours?.length) {
      return null;
    }
    const now = Date.now();
    const row = this.findHalfHourRow(res.half_hours, now);
    if (!row) {
      return `Selected day ${res.date} — no half-hour slot matches “now” (pick today to see live slot).`;
    }
    return (
      `Now slot ${row.label_hhmm}: import ${formatPp(row.import_p_per_kwh)} · export ` +
      `${formatPp(row.export_p_per_kwh)} · forecast PV ~${row.pv_kw != null ? `${row.pv_kw.toFixed(2)} kW` : '—'}`
    );
  });

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

  estimatesSummary(e: OptimizationDayResponseModel['estimates']): string {
    const parts = [
      `Clipped PV (forecast): ${e.clipped_pv_energy_kwh.toFixed(2)} kWh${
        e.clipped_energy_partial_forecast ? ' (partial intervals)' : ''
      }`,
      `Usable above min SOC: ${e.usable_battery_energy_kwh.toFixed(2)} kWh`,
      `SoC ceiling hint (advisory): ~${e.target_soc_headroom_pct_hint.toFixed(0)}%`,
    ];
    if (e.overnight_import_avg_p_per_kwh != null) {
      parts.push(`Overnight import avg: ${formatPp(e.overnight_import_avg_p_per_kwh)}`);
    }
    if (e.peak_export_avg_p_per_kwh != null) {
      parts.push(`Peak export avg: ${formatPp(e.peak_export_avg_p_per_kwh)}`);
    }
    if (e.theoretical_arbitrage_spread_pp != null) {
      parts.push(`Spread (peak exp − overnight imp): ${e.theoretical_arbitrage_spread_pp.toFixed(2)}p`);
    }
    if (e.clipped_value_vs_grid_import_pence != null) {
      parts.push(
        `Illustrative clipped value vs day import: ${e.clipped_value_vs_grid_import_pence.toFixed(1)}p`,
      );
    }
    return parts.join('   ·   ');
  }

  private load(): void {
    const iso = this.dateIso();
    if (iso < this.minIso() || iso > this.maxIso()) {
      return;
    }

    this.loading.set(true);
    this.error.set(null);

    this.api.getToday(iso).subscribe({
      next: (res) => {
        this.loading.set(false);
        this.payload.set(res);
        this.applyChart(res);
      },
      error: (e: unknown) => {
        this.loading.set(false);
        this.payload.set(null);
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

  private findHalfHourRow(
    rows: OptimizationHalfHourRow[],
    epochMs: number,
  ): OptimizationHalfHourRow | null {
    const halfMs = 30 * 60 * 1000;
    for (const row of rows) {
      const t0 = Date.parse(row.interval_start_iso);
      if (!Number.isFinite(t0)) {
        continue;
      }
      const t1 = t0 + halfMs;
      if (epochMs >= t0 && epochMs < t1) {
        return row;
      }
    }
    return null;
  }

  private applyChart(res: OptimizationDayResponseModel): void {
    const x = res.half_hours.map((r) => r.label_hhmm);

    const traces: unknown[] = [
      {
        x,
        y: res.half_hours.map((r) =>
          r.import_p_per_kwh == null ? null : r.import_p_per_kwh,
        ),
        name: 'Import (p/kWh)',
        type: 'scatter',
        mode: 'lines',
        line: { color: '#b45309', width: 2 },
        connectgaps: false,
        yaxis: 'y',
      },
      {
        x,
        y: res.half_hours.map((r) =>
          r.export_p_per_kwh == null ? null : r.export_p_per_kwh,
        ),
        name: 'Export (p/kWh)',
        type: 'scatter',
        mode: 'lines',
        line: { color: '#047857', width: 2, dash: 'dot' },
        connectgaps: false,
        yaxis: 'y',
      },
      {
        x,
        y: res.half_hours.map((r) =>
          r.pv_kw == null ? null : r.pv_kw,
        ),
        name: 'Forecast PV (kW)',
        type: 'scatter',
        mode: 'lines',
        line: { color: '#0369a1', width: 2 },
        connectgaps: false,
        yaxis: 'y2',
      },
    ];

    this.graphData.set(traces);
    this.graphLayout.set({
      title: { text: 'Octopus half-hour rates vs forecast PV' },
      xaxis: { title: { text: 'Local interval start (HH:MM)' } },
      yaxis: {
        title: { text: 'Standing rate (p/kWh inc VAT)' },
        rangemode: 'tozero',
        side: 'left',
      },
      yaxis2: {
        title: { text: 'PV (kW)' },
        overlaying: 'y',
        side: 'right',
        rangemode: 'tozero',
        showgrid: false,
      },
      margin: { l: 60, r: 60, t: 50, b: 50 },
      autosize: true,
      legend: { orientation: 'h', y: -0.22 },
      hovermode: 'x unified',
    });
  }
}
