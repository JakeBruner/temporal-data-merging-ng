import { Injectable } from '@angular/core';

@Injectable({
  providedIn: 'root'
})
export class JsonToCsvService {

  constructor() { }

  public convertToCSV(jsonData: any[], headerList: string[]): string {
    const array = typeof jsonData !== 'object' ? JSON.parse(jsonData) : jsonData;
    let str = '';
    
    // Generate the CSV header
    let header = headerList.join(',');
    str += header + '\r\n';

    // Generate CSV content
    for (let i = 0; i < array.length; i++) {
      let line = '';
      for (let index in headerList) {
        if (line != '') line += ',';
        
        let data = array[i][headerList[index]];
        line += '"' + (data ? data.toString().replace(/"/g, '""') : '') + '"';
      }

      str += line + '\r\n';
    }

    return str;
  }
}
