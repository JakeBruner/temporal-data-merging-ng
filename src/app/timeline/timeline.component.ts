// timeline.component.ts
import { Component, OnInit, ViewChild, ElementRef, AfterViewInit, HostListener } from '@angular/core';
import { TimelineService } from './timeline.service';
import { DateRange, TimelineEntry } from './date-range.model';
import { EntryFormComponent } from './entry-form/entry-form.component';
import { ConflictResolutionComponent } from './conflict-resolution/conflict-resolution.component';
import { CommonModule } from '@angular/common';

@Component({
  standalone: true,
  selector: 'app-timeline',
  templateUrl: './timeline.component.html',
  styleUrls: ['./timeline.component.scss'],
  imports: [CommonModule, EntryFormComponent, ConflictResolutionComponent]
})
export class TimelineComponent implements OnInit, AfterViewInit {
  @ViewChild('timelineContainer') timelineContainer!: ElementRef;

  timelineData: TimelineEntry[] = [];
  conflictingEntries: TimelineEntry[] = [];
  currentEntry: TimelineEntry | null = null;
  hoveredEntry: TimelineEntry | null = null;
  timelineStart: Date = new Date();
  timelineEnd: Date = new Date();
  containerWidth: number = 0;
  totalDays: number = 0;
  timelineWidth: number = 0;
  tickMarks: { position: string, label: string }[] = [];
  pixelsPerDay: number = 10; // Default value, will be adjusted

  constructor(private timelineService: TimelineService) {}

  ngOnInit() {
    this.loadTimelineData();
  }

  ngAfterViewInit() {
    this.updateContainerWidth();
    this.setupHorizontalScroll();
  }

  @HostListener('window:resize')
  onResize() {
    this.updateContainerWidth();
  }

  setupHorizontalScroll() {
    const container = this.timelineContainer.nativeElement;
    container.addEventListener('wheel', (e: WheelEvent) => {
      if (e.deltaY !== 0) {
        e.preventDefault();
        container.scrollLeft += e.deltaY;
      }
    });
  }

  updateContainerWidth() {
    this.containerWidth = this.timelineContainer.nativeElement.offsetWidth;
    this.calculateTimelineWidth();
    this.calculatePositionsAndWidths();
    this.generateTickMarks();
  }

  loadTimelineData() {
    this.timelineService.getTimelineData().subscribe(data => {
      this.timelineData = data;
      this.updateTimelineRange();
      this.checkConflicts();
      this.calculateTimelineWidth();
      this.calculatePositionsAndWidths();
      this.generateTickMarks();
    });
  }

  updateTimelineRange() {
    this.timelineStart = new Date(Math.min(...this.timelineData.map(entry => entry.dateRange.start.getTime())));
    this.timelineEnd = new Date(Math.max(...this.timelineData.map(entry => entry.dateRange.end.getTime())));
    this.totalDays = (this.timelineEnd.getTime() - this.timelineStart.getTime()) / (1000 * 60 * 60 * 24);
  }

  calculateTimelineWidth() {
    // Auto-zoom logic
    const minWidth = this.containerWidth;
    const maxWidth = this.containerWidth * 2; // Limit max width to 3 times the container width
    const idealPixelsPerDay = 20; // Adjust this value to change the default zoom level

    this.pixelsPerDay = Math.min(idealPixelsPerDay, maxWidth / this.totalDays);
    this.timelineWidth = Math.max(minWidth, this.totalDays * this.pixelsPerDay);
  }

  calculatePositionsAndWidths() {
    if (this.timelineWidth === 0 || this.totalDays === 0) return;

    this.timelineData.forEach(entry => {
      entry.position = this.getEntryPosition(entry);
      entry.width = this.getEntryWidth(entry);
    });

    this.conflictingEntries.forEach(entry => {
      entry.position = this.getEntryPosition(entry);
      entry.width = this.getEntryWidth(entry);
    });

    if (this.currentEntry) {
      this.currentEntry.position = this.getEntryPosition(this.currentEntry);
      this.currentEntry.width = this.getEntryWidth(this.currentEntry);
    }
  }

  getEntryPosition(entry: TimelineEntry): string {
    const daysFromStart = (entry.dateRange.start.getTime() - this.timelineStart.getTime()) / (1000 * 60 * 60 * 24);
    const position = daysFromStart * this.pixelsPerDay;
    return `${position}px`;
  }

  getEntryWidth(entry: TimelineEntry): string {
    const entryDays = (entry.dateRange.end.getTime() - entry.dateRange.start.getTime()) / (1000 * 60 * 60 * 24);
    const width = entryDays * this.pixelsPerDay;
    return `${width}px`;
  }

  generateTickMarks() {
    this.tickMarks = [];
    
    // Add start and end tick marks
    this.tickMarks.push(
      { position: '0px', label: this.formatDate(this.timelineStart) },
      { position: `${this.timelineWidth}px`, label: this.formatDate(this.timelineEnd) }
    );

    // Add intermediate tick marks
    const intervalDays = Math.ceil(this.totalDays / 5); // Divide timeline into 5 parts
    for (let i = 1; i < 5; i++) {
      const date = new Date(this.timelineStart.getTime() + intervalDays * i * 24 * 60 * 60 * 1000);
      const position = `${intervalDays * i * this.pixelsPerDay}px`;
      this.tickMarks.push({ position, label: this.formatDate(date) });
    }
  }

  formatDate(date: Date): string {
    return date.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
  }

  setCurrentEntry(entry: TimelineEntry) {
    this.currentEntry = entry;
    this.checkConflicts();
    this.calculatePositionsAndWidths();
  }

  setHoveredEntry(entry: TimelineEntry | null) {
    this.hoveredEntry = entry;
  }

  getEntryColor(entry: TimelineEntry): string {
    const hue = (entry.id * 137.508) % 360;
    return `hsla(${hue}, 50%, 50%, 0.90)`;
  }

  getTooltipPosition(entry: TimelineEntry): { left: string, top: string } {
    return { left: entry.position!, top: '60px' };
  }

  checkConflicts() {
    this.conflictingEntries = [];
    for (let i = 0; i < this.timelineData.length; i++) {
      for (let j = i + 1; j < this.timelineData.length; j++) {
        if (this.timelineData[i].dateRange.intersects(this.timelineData[j].dateRange)) {
          this.conflictingEntries.push(this.timelineData[i], this.timelineData[j]);
        }
      }
    }
  }

  addNewEntry(entry: TimelineEntry) {
    this.timelineService.addEntry(entry).subscribe(() => {
      this.loadTimelineData();
    });
  }

  resolveConflict(entry: TimelineEntry, action: 'merge-incoming' | 'merge-outgoing') {
    const conflictingEntry = this.conflictingEntries.find(e => e.dateRange.intersects(entry.dateRange) && e !== entry);
    if (!conflictingEntry) return;

    const intersection = entry.dateRange.intersection(conflictingEntry.dateRange);
    if (!intersection) return;

    if (action === 'merge-incoming') {
      this.mergeEntries(entry, conflictingEntry, intersection);
    } else {
      this.mergeEntries(conflictingEntry, entry, intersection);
    }

    this.timelineService.updateEntries(this.timelineData).subscribe(() => {
      this.loadTimelineData();
    });
  }

  private mergeEntries(target: TimelineEntry, source: TimelineEntry, intersection: DateRange) {
    // Split the target entry if necessary
    if (target.dateRange.start < intersection.start) {
      this.timelineData.push({
        ...target,
        id: Date.now(), // Generate a new ID
        dateRange: new DateRange(target.dateRange.start, intersection.start)
      });
    }
    if (target.dateRange.end > intersection.end) {
      this.timelineData.push({
        ...target,
        id: Date.now() + 1, // Generate a new ID
        dateRange: new DateRange(intersection.end, target.dateRange.end)
      });
    }

    // Update the target entry with the intersection
    target.dateRange = intersection;
    target.expectedLoss = source.expectedLoss;

    // Remove the source entry
    const sourceIndex = this.timelineData.findIndex(e => e.id === source.id);
    if (sourceIndex !== -1) {
      this.timelineData.splice(sourceIndex, 1);
    }
  }

  selectedEntry: TimelineEntry | null = null;

  showEntryDetails(entry: TimelineEntry) {
    this.selectedEntry = entry;
  }

  hideEntryDetails() {
    this.selectedEntry = null;
  }

}