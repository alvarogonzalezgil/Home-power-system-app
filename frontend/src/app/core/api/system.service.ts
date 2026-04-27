import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { SystemConfig } from '../models/system-config.model';

@Injectable({ providedIn: 'root' })
export class SystemService {
  private readonly http = inject(HttpClient);
  private readonly base = environment.apiBase;

  getConfig(): Observable<SystemConfig> {
    return this.http.get<SystemConfig>(`${this.base}/api/system/config`);
  }

  putConfig(config: SystemConfig): Observable<SystemConfig> {
    return this.http.put<SystemConfig>(`${this.base}/api/system/config`, config);
  }
}
