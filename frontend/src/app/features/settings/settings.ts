import { CommonModule } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router } from '@angular/router';
import { HttpErrorResponse } from '@angular/common/http';
import { SystemService } from '../../core/api/system.service';
import { SystemConfig } from '../../core/models/system-config.model';

@Component({
  selector: 'app-settings',
  imports: [CommonModule, ReactiveFormsModule],
  templateUrl: './settings.html',
  styleUrl: './settings.scss',
})
export class Settings implements OnInit {
  private readonly fb = inject(FormBuilder);
  private readonly system = inject(SystemService);
  private readonly router = inject(Router);

  /** Browser local offset from UTC in hours (same convention as `timezone_offset_h`). */
  readonly browserUtcOffsetH = -new Date().getTimezoneOffset() / 60;

  readonly saving = signal(false);
  readonly loadError = signal<string | null>(null);
  readonly saveMessage = signal<string | null>(null);

  readonly form = this.fb.group({
    latitude: [0, [Validators.required]],
    longitude: [0, [Validators.required]],
    tilt_deg: [0, [Validators.required, Validators.min(0), Validators.max(90)]],
    azimuth_deg: [0, [Validators.required, Validators.min(0), Validators.max(360)]],
    panel_count: [1, [Validators.required, Validators.min(1), Validators.max(10000)]],
    panel_width_m: [0, [Validators.required, Validators.min(0.01)]],
    panel_height_m: [0, [Validators.required, Validators.min(0.01)]],
    panel_efficiency: [0, [Validators.required, Validators.min(0.0001), Validators.max(1)]],
    timezone_offset_h: [
      this.browserUtcOffsetH,
      [Validators.min(-12), Validators.max(12)],
    ],
    sample_minutes: [5, [Validators.required, Validators.min(1), Validators.max(60)]],
    inverter_sn: [''],
    foxess_power_unit: ['kW' as 'kW' | 'W'],
    octopus_region: [
      'K',
      [
        Validators.required,
        Validators.pattern(/^[ABCDEFGHJKLMNP]$/i),
      ],
    ],
    octopus_import_product: [
      'FLUX-IMPORT-23-02-14',
      [Validators.required, Validators.minLength(3)],
    ],
    octopus_export_product: [
      'FLUX-EXPORT-23-02-14',
      [Validators.required, Validators.minLength(3)],
    ],
    inverter_capacity_kw: [5, [Validators.required, Validators.min(0.1)]],
    battery_capacity_kwh: [5.2, [Validators.required, Validators.min(0.1)]],
    battery_min_soc_pct: [
      10,
      [Validators.required, Validators.min(0), Validators.max(95)],
    ],
    battery_round_trip_efficiency: [
      0.88,
      [Validators.required, Validators.min(0.05), Validators.max(1)],
    ],
  });

  ngOnInit(): void {
    this.system.getConfig().subscribe({
      next: (c) => {
        this.form.patchValue({
          ...c,
          inverter_sn: c.inverter_sn ?? '',
          foxess_power_unit: c.foxess_power_unit ?? 'kW',
          octopus_region: c.octopus_region ?? 'K',
          octopus_import_product:
            c.octopus_import_product ?? 'FLUX-IMPORT-23-02-14',
          octopus_export_product:
            c.octopus_export_product ?? 'FLUX-EXPORT-23-02-14',
          inverter_capacity_kw: c.inverter_capacity_kw ?? 5,
          battery_capacity_kwh: c.battery_capacity_kwh ?? 5.2,
          battery_min_soc_pct: c.battery_min_soc_pct ?? 10,
          battery_round_trip_efficiency: c.battery_round_trip_efficiency ?? 0.88,
        });
        this.loadError.set(null);
      },
      error: (e) => {
        this.loadError.set(this.httpErr(e, 'Failed to load settings'));
      },
    });
  }

  useDetectedTimezone(): void {
    this.form.patchValue({ timezone_offset_h: this.browserUtcOffsetH });
  }

  submit(): void {
    this.saveMessage.set(null);
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    const raw = this.form.getRawValue();
    const payload = {
      ...raw,
      inverter_sn: raw.inverter_sn?.trim() ? raw.inverter_sn.trim() : null,
      foxess_power_unit: (raw.foxess_power_unit ?? 'kW') as 'kW' | 'W',
      octopus_region: (raw.octopus_region ?? 'K').trim().toUpperCase(),
      octopus_import_product: (raw.octopus_import_product ?? '').trim(),
      octopus_export_product: (raw.octopus_export_product ?? '').trim(),
    } as SystemConfig;
    this.saving.set(true);
    this.system.putConfig(payload).subscribe({
      next: () => {
        this.saving.set(false);
        this.saveMessage.set('Saved. Returning to dashboard…');
        this.router.navigate(['/']);
      },
      error: (e) => {
        this.saving.set(false);
        this.saveMessage.set(this.httpErr(e, 'Save failed'));
      },
    });
  }

  private httpErr(e: unknown, fallback: string): string {
    if (e instanceof HttpErrorResponse) {
      const d = e.error;
      if (d && typeof d === 'object' && 'detail' in d) {
        return String((d as { detail: string }).detail);
      }
      return e.message || fallback;
    }
    return fallback;
  }
}
