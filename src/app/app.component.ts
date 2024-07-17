import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Item } from './item';
import { Option, ResponsePickerComponent } from './response-picker/response-picker.component';

type FilterOptions = 'all' | 'active' | 'completed';

import { JsonToCsvService } from './jsonto-csv.service';
import { TimelineComponent } from './timeline/timeline.component';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, TimelineComponent],
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.css'],
})
export class AppComponent {
  
}
