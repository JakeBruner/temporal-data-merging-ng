// conflict-resolution.component.ts
import { Component, Input, Output, EventEmitter } from '@angular/core';
import { DatePipe } from '@angular/common';
import { type TimelineEntry } from '../date-range.model';
import { CommonModule } from '@angular/common';

@Component({
  standalone: true,
  selector: 'app-conflict-resolution',
  templateUrl: './conflict-resolution.component.html',
  styleUrls: ['./conflict-resolution.component.scss'],
  imports: [CommonModule],
  providers: [DatePipe]
})
export class ConflictResolutionComponent {
  @Input() conflictingEntries: TimelineEntry[] = [];
  @Output() resolveConflict = new EventEmitter<{ entry: TimelineEntry, action: 'merge-incoming' | 'merge-outgoing' }>();

  resolveAction(entry: TimelineEntry, action: 'merge-incoming' | 'merge-outgoing') {
    this.resolveConflict.emit({ entry, action });
  }
}