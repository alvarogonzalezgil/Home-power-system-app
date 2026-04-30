import { Routes } from '@angular/router';
import { Forecast } from './features/forecast/forecast';
import { PvDashboard } from './features/pv-dashboard/pv-dashboard';
import { Settings } from './features/settings/settings';

export const routes: Routes = [
  { path: '', component: PvDashboard },
  { path: 'forecast', component: Forecast },
  { path: 'settings', component: Settings },
  { path: '**', redirectTo: '' },
];
