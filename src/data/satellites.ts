import { Satellite } from '@/types/satellite';

/**
 * GSAT-30 is the only asset with a live RF + detector chain on this Windows deployment.
 * Other entries are retained for future site-specific integration (e.g. one Raspberry Pi per row).
 */
export const initialSatellites: Satellite[] = [
  { id: '1', name: 'GSAT-30', band: 'C-Band', status: 'online', elevation: 45.2, azimuth: 183.7, latitude: 0.05, longitude: 83.0, state: 'Andhra Pradesh', country: 'India', groundStation: 'Hassan', piIpAddress: '127.0.0.1 (local chain)', inchargeName: 'Dr. Ananya Sharma', facingPosition: 'South-East', hardwareSpecs: 'Ku/C-band transponders, 3.4kW Solar', signalHealth: 94, cnRatio: 18.5, ebNo: 12.3, launchDate: '2020-01-17' },
  { id: '2', name: 'INSAT-4B', band: 'Ku-Band', status: 'offline', elevation: 52.1, azimuth: 176.3, latitude: 0.02, longitude: 93.5, state: 'Karnataka', country: 'India', groundStation: 'Bengaluru', piIpAddress: '—', inchargeName: '—', facingPosition: 'South', hardwareSpecs: '—', signalHealth: 0, cnRatio: 0, ebNo: 0, launchDate: '2007-03-12' },
  { id: '3', name: 'RISAT-2BR1', band: 'X-Band', status: 'offline', elevation: 38.9, azimuth: 192.1, latitude: 37.0, longitude: 76.0, state: 'Sriharikota', country: 'India', groundStation: 'SDSC-SHAR', piIpAddress: '—', inchargeName: '—', facingPosition: 'Nadir', hardwareSpecs: '—', signalHealth: 0, cnRatio: 0, ebNo: 0, launchDate: '2019-12-11' },
  { id: '4', name: 'Chandrayaan-3', band: 'S-Band', status: 'offline', elevation: 62.4, azimuth: 210.5, latitude: -69.37, longitude: 32.35, state: 'Lunar South Pole', country: 'Moon', groundStation: 'IDSN Byalalu', piIpAddress: '—', inchargeName: '—', facingPosition: 'Lunar Surface', hardwareSpecs: '—', signalHealth: 0, cnRatio: 0, ebNo: 0, launchDate: '2023-07-14' },
  { id: '5', name: 'Aditya-L1', band: 'S-Band', status: 'offline', elevation: 71.8, azimuth: 155.3, latitude: 0.0, longitude: 0.0, state: 'L1 Lagrange', country: 'Solar Orbit', groundStation: 'IDSN Byalalu', piIpAddress: '—', inchargeName: '—', facingPosition: 'Sun-facing', hardwareSpecs: '—', signalHealth: 0, cnRatio: 0, ebNo: 0, launchDate: '2023-09-02' },
];
