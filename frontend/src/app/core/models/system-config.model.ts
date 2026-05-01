export interface SystemConfig {
  latitude: number;
  longitude: number;
  tilt_deg: number;
  azimuth_deg: number;
  panel_count: number;
  panel_width_m: number;
  panel_height_m: number;
  panel_efficiency: number;
  timezone_offset_h: number;
  sample_minutes: number;
  inverter_sn?: string | null;
  foxess_power_unit?: 'kW' | 'W';
  /** GB region letter (A–H, J–N, P) for Octopus tariff codes */
  octopus_region?: string;
  octopus_import_product?: string;
  octopus_export_product?: string;
  inverter_capacity_kw?: number;
  battery_capacity_kwh?: number;
  battery_min_soc_pct?: number;
  battery_round_trip_efficiency?: number;
}
