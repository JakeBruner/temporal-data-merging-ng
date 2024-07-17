// entry-form.component.ts
import { Component, Output, EventEmitter } from '@angular/core';
import { type TimelineEntry, DateRange } from '../date-range.model';
import { FormsModule } from '@angular/forms';

@Component({
  standalone: true,
  selector: 'app-entry-form',
  templateUrl: './entry-form.component.html',
  styleUrls: ['./entry-form.component.scss'],
  imports: [FormsModule]
})
export class EntryFormComponent {
  @Output() newEntry = new EventEmitter<TimelineEntry>();

  entry: TimelineEntry = {
    id: 0,
    expectedLoss: 1.3,
    dateRange: new DateRange(new Date(2021,5, 7), new Date(2022, 4 , 5))
  };

  submitEntry() {
    this.newEntry.emit(this.entry);
    this.resetForm();
  }

  resetForm() {
    this.entry = {
      id: 0,
      expectedLoss: 0,
      dateRange: new DateRange(new Date(), new Date())
    };
  }
}