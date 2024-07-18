// conflict-resolution.component.ts
import { Component, Input, Output, EventEmitter } from '@angular/core';
import { DatePipe } from '@angular/common';
import { ConflictingEntry, type TimelineEntry } from '../date-range.model';
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
  @Input() conflictingEntries: ConflictingEntry[] = [];
  @Output() resolveConflict = new EventEmitter<{ conflictEntry: ConflictingEntry, action: 'merge-incoming' | 'merge-outgoing' }>();

  resolveAction(conflictEntry: ConflictingEntry, action: 'merge-incoming' | 'merge-outgoing') {
    this.resolveConflict.emit({conflictEntry, action });
  }
}