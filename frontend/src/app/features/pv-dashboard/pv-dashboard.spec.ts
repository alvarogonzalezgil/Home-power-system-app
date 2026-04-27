import { ComponentFixture, TestBed } from '@angular/core/testing';

import { PvDashboard } from './pv-dashboard';

describe('PvDashboard', () => {
  let component: PvDashboard;
  let fixture: ComponentFixture<PvDashboard>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [PvDashboard]
    })
    .compileComponents();

    fixture = TestBed.createComponent(PvDashboard);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
