import * as XLSX from 'xlsx';
import { SignalData } from '@/types/satellite';

export const exportSignalData = (data: SignalData[], satelliteName: string) => {
  const wsData = [
    ['ISRO CMS - Signal Log Report'],
    [`Satellite: ${satelliteName}`],
    [`Generated: ${new Date().toLocaleString()}`],
    [],
    ['Time', 'Frequency (MHz)', 'Power (dBm)', 'Noise (dBm)', 'C/N Ratio (dB)', 'Eb/No (dB)', 'Signal Health (%)'],
    ...data.map(d => [d.time, d.frequency.toFixed(1), d.power.toFixed(2), d.noise.toFixed(2), d.cnRatio.toFixed(2), d.ebNo.toFixed(2), d.signalHealth.toFixed(1)]),
  ];

  const wb = XLSX.utils.book_new();
  const ws = XLSX.utils.aoa_to_sheet(wsData);

  // Column widths
  ws['!cols'] = [{ wch: 14 }, { wch: 16 }, { wch: 14 }, { wch: 14 }, { wch: 16 }, { wch: 14 }, { wch: 18 }];

  XLSX.utils.book_append_sheet(wb, ws, 'Signal Log');
  XLSX.writeFile(wb, `${satelliteName}_signal_log_${Date.now()}.xlsx`);
};
