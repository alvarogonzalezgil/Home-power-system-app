import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { PvCurveResponse } from '../models/pv-curve.model';

@Injectable({ providedIn: 'root' })
export class FoxessService {
  private readonly http = inject(HttpClient);
  private readonly base = environment.apiBase;

  getDay(dateIso: string): Observable<PvCurveResponse> {
    const params = new HttpParams().set('date', dateIso);
    return this.http.get<PvCurveResponse>(`${this.base}/api/foxess/pv/day`, {
      params,
    });
  }
}
