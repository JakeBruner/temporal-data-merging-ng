import { TestBed } from '@angular/core/testing';

import { JSONToCSVService } from './jsonto-csv.service';

describe('JSONToCSVService', () => {
  let service: JSONToCSVService;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    service = TestBed.inject(JSONToCSVService);
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });
});
