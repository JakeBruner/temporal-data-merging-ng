import { Component } from '@angular/core';

@Component({
  selector: 'app-right-drawer',
  templateUrl: './right-drawer.component.html',
  styleUrls: ['./right-drawer.component.css']
})
export class RightDrawerComponent {
  isOpen = true
  tickers: string[] = [];
  fields: string[] = [];

  toggleDrawer() {
    this.isOpen = !this.isOpen;
  }

  addTicker() {
    this.tickers.push('');
  }

  removeTicker(index: number) {
    this.tickers.splice(index, 1);
  }

  addField() {
    this.fields.push('');
  }

  removeField(index: number) {
    this.fields.splice(index, 1);
  }

  submitData() {
    console.log('Submitting:', this.tickers, this.fields);
    // Add your API service call here
  }
}