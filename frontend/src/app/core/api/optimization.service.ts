import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { OptimizationDayResponseModel } from '../models/optimization.model';

@Injectable({ providedIn: 'root' })
export class OptimizationService {
  private readonly http = inject(HttpClient);
  private readonly base = environment.apiBase;

  getToday(dateIso: string): Observable<OptimizationDayResponseModel> {
    const params = new HttpParams().set('date', dateIso);
    return this.http.get<OptimizationDayResponseModel>(
      `${this.base}/api/optimization/today`,
      { params },
    );
  }
}
