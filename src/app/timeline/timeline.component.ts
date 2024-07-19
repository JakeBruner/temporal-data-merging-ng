// timeline.component.ts
import { Component, OnInit, ViewChild, ElementRef, AfterViewInit, HostListener } from '@angular/core';
import { ConflictingEntry, DateRange, TimelineEntry } from './date-range.model';
import { EntryFormComponent } from './entry-form/entry-form.component';
import { ConflictResolutionComponent } from './conflict-resolution/conflict-resolution.component';
import { CommonModule, Time } from '@angular/common';

@Component({
  standalone: true,
  selector: 'app-timeline',
  templateUrl: './timeline.component.html',
  styleUrls: ['./timeline.component.scss'],
  imports: [CommonModule, EntryFormComponent, ConflictResolutionComponent]
})
export class TimelineComponent implements OnInit, AfterViewInit {
  @ViewChild('timelineContainer') timelineContainer!: ElementRef<HTMLDivElement>;

  unmodifiedTimelineData: TimelineEntry[] = [];
  timelineData: TimelineEntry[] = [];
  conflictingEntries: ConflictingEntry[] = [];
  currentEntry: TimelineEntry | null = null;
  hoveredEntry: TimelineEntry | null = null;
  timelineStart: Date = new Date();
  timelineEnd: Date = new Date();
  containerWidth: number = 0;
  totalDays: number = 0;
  timelineWidth: number = 0;
  majorTickMarks: { position: number, label: string }[] = [];
  minorTickMarks: string[] = [];
  pixelsPerDay: number = 10; // Default value, will be adjusted

  numberOfMajorTicks = 5;

  constructor() {}

  ngOnInit() {
    this.loadTimelineData();
  }

  ngAfterViewInit() {
    this.updateContainerWidth();
    this.setupHorizontalScroll();
    this.scrollToMiddle();
  }

  @HostListener('window:resize')
  onResize() {
    this.updateContainerWidth();
  }

  setupHorizontalScroll() {
    const container = this.timelineContainer.nativeElement;
    const options = { passive: true };
    container.addEventListener('wheel', (e: WheelEvent) => {
      if (e.deltaY !== 0) {
      container.scrollLeft += e.deltaY;
      }
    }, options);
  }

  updateContainerWidth() {
    this.containerWidth = this.timelineContainer.nativeElement.offsetWidth;
    this.calculateTimelineWidth();
    this.calculatePositionsAndWidths();
    this.generateTickMarks();
  }

  scrollToMiddle() {
    const e = this.timelineContainer.nativeElement
    e.scrollLeft = (this.timelineWidth - this.containerWidth) / 2;
  }

  loadTimelineData() {
    console.log('Loading timeline data...')
    // make api call given table and params passed by parent component
      const data = [
        { id: 1, expectedLoss: 1.3, dateRange: new DateRange (new Date(2020, 5, 7), new Date(2020, 7, 5)) },
        { id: 2, expectedLoss: 2.5, dateRange: new DateRange (new Date(2021, 6, 15), new Date(2022, 5, 10)) },
        { id: 3, expectedLoss: 0.8, dateRange: new DateRange (new Date(2021, 7, 20), new Date(2022, 6, 15)) },
        { id: 4, expectedLoss: 1.2, dateRange: new DateRange (new Date(2022, 5, 10), new Date(2023, 4, 30))}
      ];

      this.unmodifiedTimelineData = data;
      this.timelineData = data;


      console.log("updating timeline range")
      this.updateTimelineRange();
      console.log("calculating timeline width")
      this.calculateTimelineWidth();
      console.log("calculating positions and widths")
      this.calculatePositionsAndWidths();
      console.log("generating tick marks")
      this.generateTickMarks();
      console.log("populating conflicts")
      this.populateConflicts();

      console.log("load function done")
      
  }

  updateTimelineRange() {
    this.timelineStart = new Date(Math.min(...this.timelineData.map(entry => entry.dateRange.start.getTime())));
    this.timelineEnd = new Date(Math.max(...this.timelineData.map(entry => entry.dateRange.end.getTime())));
    this.totalDays = (this.timelineEnd.getTime() - this.timelineStart.getTime()) / (1000 * 60 * 60 * 24);
    // get number of divisions as roughly half the number of months between start and end date
    this.numberOfMajorTicks = Math.ceil(this.totalDays / 60);
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
      entry.position = this.getEntryPosition(entry.dateRange);
      entry.width = this.getEntryWidth(entry.dateRange);
    });
    this.conflictingEntries.forEach(conflict => {
      conflict.position = this.getEntryPosition(conflict.intersection);
      conflict.width = this.getEntryWidth(conflict.intersection
      );  
    });
  }

  getEntryPosition(range: DateRange): string {
    const daysFromStart = (range.start.getTime() - this.timelineStart.getTime()) / (1000 * 60 * 60 * 24);
    const position = daysFromStart * this.pixelsPerDay;
    return `${position}px`;
  }

  getEntryWidth(range: DateRange): string {
    const entryDays = (range.end.getTime() - range.start.getTime()) / (1000 * 60 * 60 * 24);
    const width = entryDays * this.pixelsPerDay;
    return `${width}px`;
  }




  generateTickMarks() {
    this.majorTickMarks = [];
    
    // Add start and end tick marks
    this.majorTickMarks.push(
      { position: 0, label: this.formatDate(this.timelineStart) },
      { position: this.timelineWidth, label: this.formatDate(this.timelineEnd) }
    );

    // Add intermediate tick marks
    const intervalDays = Math.ceil(this.totalDays / this.numberOfMajorTicks); 
    for (let i = 1; i < this.numberOfMajorTicks; i++) {
      const date = new Date(this.timelineStart.getTime() + intervalDays * i * 24 * 60 * 60 * 1000);
      const position = intervalDays * i * this.pixelsPerDay;
      this.majorTickMarks.push({ position, label: this.formatDate(date) });
    }
  }

  formatDate(date: Date): string {
    return date.toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric"});
  }

  setCurrentEntry(entry: TimelineEntry) {
    this.currentEntry = entry;
    this.populateConflicts();
    this.calculatePositionsAndWidths();
  }



  // duplicated in conflict-resolution.component.ts
  getEntryColor(entry: TimelineEntry, lightness = 50, alpha = 0.9): string {
    const hue = (entry.id * 137.508) % 360;
    return `hsla(${hue}, 50%, ${lightness}%, ${alpha})`;
  }

  populateConflicts() {
    this.conflictingEntries = [];
    for (let i = 0; i < this.timelineData.length; i++) {
      for (let j = i + 1; j < this.timelineData.length; j++) {
        if (this.timelineData[i].dateRange.intersects(this.timelineData[j].dateRange)) {
          const intersection = this.timelineData[i].dateRange.intersection(this.timelineData[j].dateRange)!;
          this.conflictingEntries.push({ entry1: this.timelineData[i], entry2: this.timelineData[j], intersection});
        }
      }
    }
  }

  addNewEntry(entry: TimelineEntry) {
    this.timelineData.push(entry);
    // handle diffs later
    this.calculatePositionsAndWidths();
    this.populateConflicts(); 
  }

  resolveConflict(conflictEntry: ConflictingEntry, action: 'merge-incoming' | 'merge-outgoing') {
    // merge-incoming: newer entry (2) overwrites
    if (action === 'merge-incoming') {

        conflictEntry.entry1.dateRange.end = conflictEntry.intersection.start;
        console.log("option2")

    } else {

        conflictEntry.entry2.dateRange.start = conflictEntry.intersection.end;

    }
    this.calculatePositionsAndWidths();
    this.populateConflicts(); 
  }

    
  // }

  // private mergeEntries(target: TimelineEntry, source: TimelineEntry, intersection: DateRange) {
  //   // merge entries by calculating the intersection, and then updating the target entry's either start or end date to the intersection's start or end date

  //   if (target.dateRange.start.getTime() === intersection.start.getTime()) {
  //     target.dateRange.end = intersection.end;
  //   } else {
  //     target.dateRange.start = intersection.start;
  //   }

  //   console.log('Merged entries:', target, source);
  //   console.log('Target was updated from intersection:', intersection);

  //   //trigger re-render
  //   this.calculatePositionsAndWidths();
  //   this.populateConflicts();

  // }


  log(message: any) {
    console.log(message);
  }

}