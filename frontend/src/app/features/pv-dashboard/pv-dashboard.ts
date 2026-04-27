import { HttpErrorResponse } from '@angular/common/http';
import { CommonModule } from '@angular/common';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { PlotlyModule } from 'angular-plotly.js';
import { PvService } from '../../core/api/pv.service';
import { PvCurveResponse } from '../../core/models/pv-curve.model';

const MONTHS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12];

function daysInMonth(m: number): number {
  const t = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  return t[m - 1];
}

@Component({
  selector: 'app-pv-dashboard',
  imports: [CommonModule, FormsModule, PlotlyModule],
  templateUrl: './pv-dashboard.html',
  styleUrl: './pv-dashboard.scss',
})
export class PvDashboard implements OnInit {
  private readonly pv = inject(PvService);

  readonly month = signal(7);
  readonly day = signal(1);
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);
  readonly metLabel = signal<string | null>(null);

  /** Plotly data traces */
  readonly graphData = signal<unknown[]>([]);
  readonly graphLayout = signal<Record<string, unknown>>({});
  readonly monthOptions = MONTHS;

  readonly maxDay = computed(() => daysInMonth(this.month()));

  ngOnInit(): void {
    this.load();
  }

  onMonth(m: string | number): void {
    const n = Number(m);
    this.month.set(n);
    this.clampDay();
    this.load();
  }

  onDay(d: string | number): void {
    const n = Math.floor(Number(d));
    if (Number.isNaN(n) || n < 1) {
      return;
    }
    this.day.set(Math.min(n, this.maxDay()));
    this.load();
  }

  private clampDay(): void {
    const max = this.maxDay();
    if (this.day() > max) {
      this.day.set(max);
    }
  }

  private load(): void {
    this.loading.set(true);
    this.error.set(null);
    this.pv.getDay(this.month(), this.day()).subscribe({
      next: (res: PvCurveResponse) => {
        this.loading.set(false);
        this.metLabel.set(
          `Clear-sky model — ${res.date} (day-of-year from 2025 reference)`,
        );
        const x = res.points.map((p) => p.time);
        const y = res.points.map((p) => p.power_w);
        this.graphData.set([
          {
            x,
            y,
            type: 'scatter',
            mode: 'lines',
            name: 'PV (W)',
            line: { color: '#0ea5e9', width: 2 },
          },
        ]);
        this.graphLayout.set({
          title: { text: 'Theoretical max PV power (clear sky)' },
          xaxis: { title: { text: 'Time (HH:MM)' } },
          yaxis: { title: { text: 'Power (W)' } },
          margin: { l: 60, r: 20, t: 50, b: 50 },
          autosize: true,
        });
      },
      error: (e: unknown) => {
        this.loading.set(false);
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
        this.graphData.set([]);
        this.graphLayout.set({});
      },
    });
  }
}
