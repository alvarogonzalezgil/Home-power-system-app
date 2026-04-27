import { Routes } from '@angular/router';
import { PvDashboard } from './features/pv-dashboard/pv-dashboard';
import { Settings } from './features/settings/settings';

export const routes: Routes = [
  { path: '', component: PvDashboard },
  { path: 'settings', component: Settings },
  { path: '**', redirectTo: '' },
];
