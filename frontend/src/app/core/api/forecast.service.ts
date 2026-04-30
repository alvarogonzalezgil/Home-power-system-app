import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import {
  ForecastPvDayResponse,
  ForecastPvModel,
} from '../models/pv-curve.model';

@Injectable({ providedIn: 'root' })
export class ForecastService {
  private readonly http = inject(HttpClient);
  private readonly base = environment.apiBase;

  getDay(dateIso: string, model: ForecastPvModel): Observable<ForecastPvDayResponse> {
    const params = new HttpParams().set('date', dateIso).set('model', model);
    return this.http.get<ForecastPvDayResponse>(
      `${this.base}/api/forecast/pv/day`,
      { params },
    );
  }
}
