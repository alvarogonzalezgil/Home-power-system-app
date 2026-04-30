export interface PvCurvePoint {
  time: string;
  power_w: number | null;
}

export interface PvCurveResponse {
  date: string;
  points: PvCurvePoint[];
}
