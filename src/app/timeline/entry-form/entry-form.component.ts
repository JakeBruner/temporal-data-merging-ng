// entry-form.component.ts
import { Component, Output, EventEmitter } from '@angular/core';
import { type TimelineEntry, DateRange } from '../date-range.model';
import { FormsModule } from '@angular/forms';
import { CommonModule } from '@angular/common';

@Component({
  standalone: true,
  selector: 'app-entry-form',
  templateUrl: './entry-form.component.html',
  styles: `
  @keyframes tilt-n-move-shaking {
    0% { transform: translate(0, 0) rotate(0deg); }
    25% { transform: translate(5px, 5px) rotate(5deg); }
    50% { transform: translate(0, 0) rotate(0eg); }
    75% { transform: translate(-5px, 5px) rotate(-5deg); }
    100% { transform: translate(0, 0) rotate(0deg); }
  }
  
  .strong-tilt-move-shake {
    animation: tilt-n-move-shaking 0.15s infinite;
  }
  `,
  imports: [FormsModule, CommonModule]
})
export class EntryFormComponent {
  @Output() newEntry = new EventEmitter<TimelineEntry>();

  error: { message: string } | null = null;

  entry: TimelineEntry = {
    // 1/1000 chance of causing a bug... hah...
    id: -1*Math.floor(Math.random()* 1000),
    expectedLoss: 1.3,
    dateRange: new DateRange(new Date(2021,5, 7), new Date(2022, 4 , 5))
  };

  submitEntry() {
    if (this.entry.expectedLoss <= 0) {
      this.showError('Expected loss must be greater than 0');
      return;
    }
    if (this.entry.dateRange.start > this.entry.dateRange.end) {
      this.showError('Start date must be before end date');
      return;
    }
    this.newEntry.emit(this.entry);
    this.resetForm();
  }

  showError(message: string) {
    this.error = { message };
    const btn = document.getElementById('btn-for-animate');
    if (btn) {
      btn.classList.add('strong-tilt-move-shake');
      setTimeout(() => {
        btn.classList.remove('strong-tilt-move-shake');
      }, 1000);
    }
    setTimeout(() => {
      this.error = null;
    }, 5000);
  }

  resetForm() {
    this.entry = {
      id: -1*Math.floor(Math.random()* 1000),
      expectedLoss: 0,
      dateRange: new DateRange(new Date(), new Date())
    };
  }
}