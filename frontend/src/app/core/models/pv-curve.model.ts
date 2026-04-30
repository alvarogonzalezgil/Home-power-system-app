export interface PvCurvePoint {
  time: string;
  power_w: number | null;
}

export interface PvCurveResponse {
  date: string;
  points: PvCurvePoint[];
}

export type ForecastPvModel = 'components' | 'cloud_derate';

export interface ForecastPvDayResponse {
  date: string;
  model: ForecastPvModel;
  forecast_points: PvCurvePoint[];
  clear_sky_points: PvCurvePoint[];
}
