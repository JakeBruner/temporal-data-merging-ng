# Porting into Company Code
Currently this uses hardcoded example data in timeline.component.ts's loadTimelineData(). This codebase should be imported inside a wrapper component (to slide over on `tables` with ineffective/effective) that passes down the data given the identifying data sufficent to know that two entries correspond to the "same" piece of data (e.g., one bond's el), likely with a new angular service and a new APIController on the backend providing these hooks. This component passes three "changes" arrays, corresponding to updates, deletions, and creations. These should be hooked into a form submit / (onclick) action that provides this to the API Controller in C#. Currently, the data types don't keep all the context of the entry itself. This can be handled in a number of ways: 1) make the original table entry, serialized in json, a key of the data type. Like:
```ts
interface Entry {
  id: number;
  expectedLoss: number;
  dateRange: DateRange;
  tableEntry: {[key: string]: string | number | Date | boolean};
}
```
Or otherwise, the types can be kept slim like it is currently, and on pushing staged changes, use the id column to relink the changes here with the actual database types in C# using where clauses. Though, this hinders the ability to add new entries from here directly. To that point, if that functionality is desired and it's implemented similar to the `Entry` interface above, you can use my code for `<input />` tags within a `*ngFor="let (k,v) of entry.tableEntry"` directive and either `[ngModel]` or `(onChange)` hook with a method, e.g., `updateRowField(id: number, entryField: string, newValue: string | number | Date | boolean)` that mutates the data[].

## Importing Styles
For the styles, I used [TailwindCSS](https://tailwindcss.com/) to speed up development. While I highly(!) reccomend it, it probably doesn't make sense to create a dependency on it in WebApp. Most efficently, you can build the app then grab the generated tailwind css file, which only includes classes I used here, and import that as the stylesheet of the page and components. 

To do so, run `ng build` then navigate to the `dist/temporal-data-merging-ng` directory and look for the `styles-[...].css` file. This is the stylesheet for the entire app. Bring it to the codebase and point to it in the `@Component` or `@Module` decorators for each `*.component.ts` file.

Otherwise, it's possible to use a tailwindcss CDN, except this has a large bundle size and negates the benefits that these utility classes bring. 

## Note
On another note, it's entirely possible that this functionality contains issues that need to be smoothed over. Including some finniky things like the rendering of the timeline. I didn't have bandwidth to comb through these, since I started on other projects. Feel free to reach out if you need any clarification. Most of this 'drawing' and 'sizing' logic is contained in: ```this.updateTimelineRange();
    this.calculateTimelineWidth();
    this.calculatePositionsAndWidths();
    this.generateTickMarks();
    this.populateConflicts();```

Also, since ids are autoincremented by SQL, I needed a way to track new entries added. I made new entries have a negative id between [-100,-1). This is bad. Maybe just decrement from the lowest negative id, or -1 otherwise? Obviously, this field should be stripped when pushing updates to the SQL.

On a performance note, this is well-optimized on modern angular, but it's possible performance issues could come from the earlier code target or the outdated angular version. 

In general, it's important the parent component forgo rendering this in the DOM at all when its not in use. E.g., a `*ngIf` directive.


## Development server

Run `ng serve` for a dev server. Navigate to `http://localhost:4200/`. The application will automatically reload if you change any of the source files.

## Build

Run `ng build` to build the project. The build artifacts will be stored in the `dist/` directory.
