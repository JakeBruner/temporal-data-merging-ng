// date-range.model.ts
export class DateRange {
  constructor(public start: Date, public end: Date) {}

  intersects(other: DateRange): boolean {
    return this.start < other.end && other.start < this.end;
  }

  intersection(other: DateRange): DateRange | null {
    const start = new Date(Math.max(this.start.getTime(), other.start.getTime()));
    const end = new Date(Math.min(this.end.getTime(), other.end.getTime()));
    return start < end ? new DateRange(start, end) : null;
  }
}

export interface TimelineEntry {
  id: number;
  position?: string;
  width?: string;
  expectedLoss: number;
  dateRange: DateRange;
}