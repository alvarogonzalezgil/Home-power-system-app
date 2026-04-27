export interface PvCurvePoint {
  time: string;
  power_w: number;
}

export interface PvCurveResponse {
  date: string;
  points: PvCurvePoint[];
}
