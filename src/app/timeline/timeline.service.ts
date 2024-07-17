// timeline.service.ts
import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { TimelineEntry, DateRange } from './date-range.model';

@Injectable({
  providedIn: 'root'
})
export class TimelineService {
  private apiUrl = 'api/timeline'; // Replace with your actual API endpoint

  // constructor(private http: HttpClient) {}

  getTimelineData(): Observable<TimelineEntry[]> {
    // return this.http.get<TimelineEntry[]>(this.apiUrl);
    console.log('Getting timeline data')
    return new Observable<TimelineEntry[]>(observer => {
      observer.next([
        { id: 1, expectedLoss: 1.3, dateRange: new DateRange (new Date(2020, 5, 7), new Date(2020, 7, 5)) },
        { id: 2, expectedLoss: 2.5, dateRange: new DateRange (new Date(2021, 6, 15), new Date(2022, 5, 10)) },
        { id: 3, expectedLoss: 0.8, dateRange: new DateRange (new Date(2021, 7, 20), new Date(2022, 6, 15)) },
        { id: 4, expectedLoss: 1.2, dateRange: new DateRange (new Date(2022, 5, 10), new Date(2023, 4, 30))}
      ]);
      observer.complete();
    });
  }

  addEntry(entry: TimelineEntry): Observable<TimelineEntry> {
    // return this.http.post<TimelineEntry>(this.apiUrl, entry);
    console.log('Adding entry:', entry);
    return new Observable<TimelineEntry>(observer => {
      observer.next(entry);
      observer.complete();
    });

  }

  updateEntry(entry: TimelineEntry): Observable<TimelineEntry> {
    // return this.http.put<TimelineEntry>(`${this.apiUrl}/${entry.id}`, entry);
    console.log('Updating entry:', entry);
    return new Observable<TimelineEntry>(observer => {
      observer.next(entry);
      observer.complete();
    });
  }
  updateEntries(entries: TimelineEntry[]): Observable<TimelineEntry[]> {
    // return this.http.put<TimelineEntry[]>(this.apiUrl, entries);
    console.log('Updating entries:', entries);
    return new Observable<TimelineEntry[]>(observer => {
      observer.next(entries);
      observer.complete();
    });
  }
}