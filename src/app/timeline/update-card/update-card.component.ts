import { Component, Input, Output, OnInit, EventEmitter  } from '@angular/core';
import { TimelineEntry, DateRange } from '../date-range.model';
import { CommonModule, DatePipe } from '@angular/common';


@Component({
  selector: 'app-update-card',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './update-card.component.html',
  providers: [DatePipe]
})
export class UpdateCardComponent implements OnInit {

  @Output() undo = new EventEmitter<{ id: number, action: "create" | "update" | "delete" }>();

  undoAction(id: number, action: "create" | "update" | "delete") {
    console.log("undoAction", id, action);
    this.undo.emit({id, action });
  }

diffPosArr = ["start", "end"] as const;

@Input() changeType!: "update" | "delete" | "create";

@Input() entry!: TimelineEntry;
@Input() originalEntry?: TimelineEntry;

diffedRange: "start" | "end" | "both" | null = null;
diff: {original: string, modified: string}[] | null = null;

id: number;



getEntryColor(entry: TimelineEntry, lightness = 50, alpha = 0.9): string {
  const hue = (entry.id * 137.508) % 360;
  return `hsla(${hue}, 50%, ${lightness}%, ${alpha})`;
}

getDiffedRange(): "start" | "end" | "both" | null {
  if (!this.originalEntry) return null;
  if (this.changeType !== "update") return null;
  if (this.originalEntry.dateRange.start.getTime() !== this.entry.dateRange.start.getTime() && this.originalEntry.dateRange.end.getTime() !== this.entry.dateRange.end.getTime()) return "both";
  if (this.originalEntry.dateRange.start.getTime() !== this.entry.dateRange.start.getTime()) return "start";
  if (this.originalEntry.dateRange.end.getTime() !== this.entry.dateRange.end.getTime()) return "end";
  return null;
}
/* tuple is original date -> new date */
getDiff(): {original: string, modified: string}[]  | null { 
  if (this.changeType !== "update") return null;
  if (!this.originalEntry) return null;

  if ( this.diffedRange === "start" ) {
    return [{original: this.originalEntry.dateRange.start.toLocaleDateString(), modified: this.entry.dateRange.start.toLocaleDateString()}];
  }
  if (this.diffedRange === "end") {
    return [{original: this.originalEntry.dateRange.end.toLocaleDateString(), modified: this.entry.dateRange.end.toLocaleDateString()}];
  }

  if (this.diffedRange === "both") {
    return [{original: this.originalEntry.dateRange.start.toLocaleDateString(), modified: this.entry.dateRange.start.toLocaleDateString()},
            {original: this.originalEntry.dateRange.end.toLocaleDateString(), modified: this.entry.dateRange.end.toLocaleDateString()}];
  }

  return null;
}

ngOnInit(): void {
    this.diffedRange = this.getDiffedRange();
    this.diff = this.getDiff();
    
    const element = document.getElementById(this.id.toString());
    if (!element) return;
    element.setAttribute('style', 'background-color: #f4f3bc;');
    setTimeout(() => element.removeAttribute('style'), 700);

}

constructor() {
  this.id = 10000* Math.random();

}

}
