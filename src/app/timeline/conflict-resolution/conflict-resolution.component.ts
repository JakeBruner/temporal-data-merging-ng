// conflict-resolution.component.ts
import { Component, Input, Output, EventEmitter } from '@angular/core';
import { DatePipe } from '@angular/common';
import { ConflictingEntry, type TimelineEntry } from '../date-range.model';
import { CommonModule } from '@angular/common';

@Component({
  standalone: true,
  selector: 'app-conflict-resolution',
  templateUrl: './conflict-resolution.component.html',
  imports: [CommonModule],
  providers: [DatePipe]
})
export class ConflictResolutionComponent {
  @Input() conflictingEntries: ConflictingEntry[] = [];
  @Output() resolveConflict = new EventEmitter<{ conflictEntry: ConflictingEntry, action: 'merge-incoming' | 'merge-outgoing' }>();

  resolveAction(conflictEntry: ConflictingEntry, action: 'merge-incoming' | 'merge-outgoing') {
    this.resolveConflict.emit({conflictEntry, action });
  }

  getEntryColor(entry: TimelineEntry, lightness = 50, alpha = 0.9): string {
    const hue = (entry.id * 137.508) % 360;
    return `hsla(${hue}, 50%, ${lightness}%, ${alpha})`;
  }

  scrollToOnTimeline(entry: ConflictingEntry) {
    const timelineElement = document.getElementById('timeline');
    if (!timelineElement || !entry.position) return;

    timelineElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
    timelineElement.scrollLeft = +entry.position.replace("px","") - 70;

  }
}