import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { PvCurveResponse } from '../models/pv-curve.model';

@Injectable({ providedIn: 'root' })
export class PvService {
  private readonly http = inject(HttpClient);
  private readonly base = environment.apiBase;

  getDay(month: number, day: number): Observable<PvCurveResponse> {
    const params = new HttpParams()
      .set('month', String(month))
      .set('day', String(day));
    return this.http.get<PvCurveResponse>(`${this.base}/api/pv/day`, { params });
  }
}
