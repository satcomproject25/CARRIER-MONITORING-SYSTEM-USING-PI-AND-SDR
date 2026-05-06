/**
 * CMS backend (Python orchestrator + headless Interference.py) API client.
 * Proxied via Vite to http://127.0.0.1:8780 in development.
 */

import type { DetectionResult, CarrierDetection, InterferenceDetection } from '@/lib/dspEngine';

export type CmsSnapshot = {
  ts?: number;
  error?: string;
  antenna_id?: string;
  hw_center_mhz?: number;
  display_center_mhz?: number;
  sample_rate_mhz?: number;
  fft_size?: number;
  noise_db?: number;
  detect_threshold_db?: number;
  threshold_compat_db?: number;
  freq_mhz?: number[];
  psd_db?: number[];
  carriers?: Array<{
    f_center_mhz: number;
    f_start_mhz: number;
    f_stop_mhz: number;
    bw_khz: number;
    is_auth: boolean;
    is_valley_sub: boolean;
  }>;
  unauthorized?: Array<{
    f_center_mhz: number;
    f_start_mhz: number;
    f_stop_mhz: number;
    bw_khz: number;
    excess_db: number;
    trigger: string;
  }>;
  interference?: Array<{
    center_mhz: number;
    start_mhz?: number;
    end_mhz?: number;
    strength_db: number;
    method?: string;
    classification?: string;
    confidence?: number;
    track_id?: number;
    parent_carrier_id?: number;
  }>;
  gap_interference?: Array<{
    center_mhz: number;
    start_mhz?: number;
    end_mhz?: number;
    strength_db: number;
    method?: string;
    confidence?: number;
  }>;
  stable_carriers?: Array<Record<string, unknown>>;
  unauth_count?: number;
  logs?: Array<{ msg: string; color?: string }>;
};

export type AuthorizedFrequency = {
  center: number;
  bandwidth: number;
  label?: string;
};

export async function cmsStartMonitor(startSdr = true, antennaId = 'gsat-30'): Promise<Response> {
  return fetch('/api/monitor/start', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ start_sdr: startSdr, sdr_settle_s: 2.0, antenna_id: antennaId }),
  });
}

export async function cmsStopMonitor(stopSdr = true): Promise<Response> {
  return fetch('/api/monitor/stop', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ stop_sdr: stopSdr }),
  });
}

export async function cmsFetchSnapshot(): Promise<CmsSnapshot> {
  const r = await fetch('/api/snapshot');
  const j = (await r.json()) as CmsSnapshot;
  if (!r.ok) j.error = j.error ?? `HTTP ${r.status}`;
  return j;
}

export async function cmsSetSmoothing(smoothEnabled: boolean, smoothAlpha: number): Promise<void> {
  await fetch('/api/set_smoothing', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ smooth_enabled: smoothEnabled, smooth_alpha: smoothAlpha }),
  }).catch(() => undefined); // best-effort; don't crash the UI if backend is down
}

export async function cmsHealth(): Promise<{
  status: string;
  sdr_running: boolean;
  detector_running: boolean;
}> {
  const r = await fetch('/api/health');
  return r.json() as Promise<{
    status: string;
    sdr_running: boolean;
    detector_running: boolean;
  }>;
}

export async function cmsGetAuthorizedFrequencies(antennaId: string): Promise<AuthorizedFrequency[]> {
  const r = await fetch(`/api/frequencies?antenna_id=${encodeURIComponent(antennaId)}`);
  const j = (await r.json()) as { frequencies?: AuthorizedFrequency[] };
  return j.frequencies ?? [];
}

export async function cmsAddAuthorizedFrequency(
  antennaId: string,
  centerHz: number,
  bandwidthHz: number,
  label: string,
): Promise<void> {
  await fetch('/api/frequencies', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      antenna_id: antennaId,
      center: centerHz,
      bandwidth: bandwidthHz,
      label,
    }),
  });
}

export async function cmsDeleteAuthorizedFrequency(antennaId: string, index: number): Promise<void> {
  await fetch(`/api/frequencies/${index}?antenna_id=${encodeURIComponent(antennaId)}`, {
    method: 'DELETE',
  });
}

/** Map backend snapshot → canvas + DSP types used by SpectrumAnalyzer. */
export function snapshotToDetectionResult(
  snap: CmsSnapshot,
  maxHold: Float64Array | null,
  minHold: Float64Array | null,
): DetectionResult | null {
  const f = snap.freq_mhz;
  const p = snap.psd_db;
  if (!f?.length || !p?.length || f.length !== p.length) return null;

  const freqAxis = Float64Array.from(f, (mhz) => mhz * 1e6);
  const psd = Float64Array.from(p);

  const carriers: CarrierDetection[] = [];

  for (const c of snap.carriers ?? []) {
    const startFreq = c.f_start_mhz * 1e6;
    const endFreq = c.f_stop_mhz * 1e6;
    const centerFreq = c.f_center_mhz * 1e6;
    const bandwidth = endFreq - startFreq;
    const startBin = Math.max(0, f.findIndex((x) => x >= c.f_start_mhz) || 0);
    const endBin = Math.min(f.length - 1, f.findIndex((x) => x >= c.f_stop_mhz) || f.length - 1);
    let peakPower = snap.noise_db ?? -100;
    for (let b = startBin; b <= endBin; b++) peakPower = Math.max(peakPower, p[b] ?? peakPower);
    const totalPower = peakPower + 10 * Math.log10(Math.max(endBin - startBin + 1, 1));
    carriers.push({
      startBin,
      endBin,
      startFreq,
      endFreq,
      centerFreq,
      bandwidth,
      peakPower,
      totalPower,
      cnRatio: Math.max(0, peakPower - (snap.noise_db ?? 0)),
      isAuthorized: c.is_auth,
    });
  }

  const interferences: InterferenceDetection[] = [];
  const half = 100e3;
  for (const x of snap.interference ?? []) {
    const cf = x.center_mhz * 1e6;
    // Use actual span from backend if available, otherwise fallback to ±100 kHz
    const startFreq = x.start_mhz ? x.start_mhz * 1e6 : cf - half;
    const endFreq = x.end_mhz ? x.end_mhz * 1e6 : cf + half;
    interferences.push({
      startFreq,
      endFreq,
      peakFreq: cf,
      strengthDb: x.strength_db,
      method: x.method ?? 'stable',
      isGap: false,
      parentCarrierId: x.parent_carrier_id ?? undefined,
    });
  }
  for (const g of snap.gap_interference ?? []) {
    const cf = g.center_mhz * 1e6;
    const startFreq = g.start_mhz ? g.start_mhz * 1e6 : cf - half;
    const endFreq = g.end_mhz ? g.end_mhz * 1e6 : cf + half;
    interferences.push({
      startFreq,
      endFreq,
      peakFreq: cf,
      strengthDb: g.strength_db,
      method: g.method ?? 'gap',
      isGap: true,
    });
  }

  return {
    psd,
    freqAxis,
    noiseFloor: snap.noise_db ?? 0,
    detectThreshold: snap.detect_threshold_db ?? 0,
    carriers,
    interferences,
    maxHold,
    minHold,
  };
}
