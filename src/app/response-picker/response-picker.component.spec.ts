import { ComponentFixture, TestBed } from '@angular/core/testing';

import { ResponsePickerComponent } from './response-picker.component';

describe('ResponsePickerComponent', () => {
  let component: ResponsePickerComponent;
  let fixture: ComponentFixture<ResponsePickerComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ResponsePickerComponent]
    })
    .compileComponents();
    
    fixture = TestBed.createComponent(ResponsePickerComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
