import { CommonModule } from '@angular/common';
import { Component, EventEmitter, Output } from '@angular/core';
import { FormsModule } from '@angular/forms';

@Component({
  selector: 'app-response-picker',
  standalone: true,
  imports: [FormsModule, CommonModule],
  templateUrl: './response-picker.component.html',
  styleUrl: './response-picker.component.css'
})
export class ResponsePickerComponent {
  searchText = '';
  optionsVisible = false;
  selectedIndex = -1;
  filteredOptions: Option[] = []; // This should be populated with actual data
  @Output() optionSelected = new EventEmitter<Option>();

  constructor() {
    // pass these in @Input directive
    this.filteredOptions = [
      { requestName: 'Option 1', requestId: '1', requestDate: '2021-01-01', requestKey: 'key1', selected: false },
      { requestName: 'Option 2', requestId: '2', requestDate: '2021-01-02', requestKey: 'key2', selected: false },
      { requestName: 'Option 3', requestId: '3', requestDate: '2021-01-03', requestKey: 'key3', selected: false },


    ];
  }

  filterOptions() {
    // Placeholder for filtering logic, assuming options include 'name' property
    this.filteredOptions = this.filteredOptions.filter(option =>
      option.requestName.toLowerCase().includes(this.searchText.toLowerCase())
    );
  }

  toggleOptionsVisibility() {
    this.optionsVisible = !this.optionsVisible;
  }

  setActive(index: number) {
    this.selectedIndex = index;
  }

  selectOption(option: any) {
    this.filteredOptions.forEach(opt => opt.selected = false); // Reset selection
    option.selected = true;
    this.optionSelected.emit(option); // Emit selected option to parent
    this.searchText = option.name; // Update input field
    this.optionsVisible = false; // Close dropdown
  }
}

export interface Option {
  requestName: string;
  requestId: string;
  requestDate: string;
  requestKey: string;
  selected: boolean;
}