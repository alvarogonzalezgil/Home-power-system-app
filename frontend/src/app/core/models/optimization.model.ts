/** Response from GET /api/optimization/today */
export interface OptimizationHalfHourRow {
  interval_start_iso: string;
  label_hhmm: string;
  import_p_per_kwh: number | null;
  export_p_per_kwh: number | null;
  import_band?: string | null;
  export_band?: string | null;
  pv_kw: number | null;
}

export interface OptimizationRecommendationRow {
  title: string;
  detail: string;
}

export interface OptimizationEstimatesRow {
  clipped_pv_energy_kwh: number;
  clipped_energy_partial_forecast: boolean;
  usable_battery_energy_kwh: number;
  target_soc_headroom_pct_hint: number;
  overnight_import_avg_p_per_kwh: number | null;
  peak_export_avg_p_per_kwh: number | null;
  theoretical_arbitrage_spread_pp: number | null;
  clipped_value_vs_grid_import_pence: number | null;
}

export interface OptimizationDayResponseModel {
  date: string;
  tariff_code_import: string;
  tariff_code_export: string;
  half_hours: OptimizationHalfHourRow[];
  recommendations: OptimizationRecommendationRow[];
  estimates: OptimizationEstimatesRow;
}
