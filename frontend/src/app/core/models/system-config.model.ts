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
}
