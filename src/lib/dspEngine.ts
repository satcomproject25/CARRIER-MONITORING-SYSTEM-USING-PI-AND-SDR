// DSP Engine - Ported from Interference.py
// Simulates FFT spectrum with carrier detection, interference detection,
// noise floor estimation, and valley/gap detection

// =====================================================
// CONFIG (matching Python constants)
// =====================================================
export const DSP_CONFIG = {
  FFT_SIZE: 2048,
  HW_SAMPLE_RATE: 20e6,
  DISPLAY_BW: 20e6,
  CENTER_FREQ: 70e6,
  Y_MIN: -70,
  Y_MAX: 80,

  // Noise floor
  NF_PERCENTILE: 15.0,
  NF_ROLLING_WINDOW_DIV: 8,

  // Carrier detection
  CARRIER_K_SIGMA: 3.5,
  MORPH_OPEN_BINS: 3,
  MORPH_CLOSE_BINS: 5,
  ADAPTIVE_MERGE_BW_FACTOR: 0.5,
  MIN_CARRIER_BW_HZ: 5 * (20e6 / 2048),
  SMOOTH_BW_HZ: 5 * (20e6 / 2048),
  THRESHOLD_RATIO: 0.35,

  // Interference detection — must match backend Interference.py exactly
  INTF_BUMP_THRESHOLD_DB: 2,
  INTF_MIN_BUMP_BINS: 1.0,       // backend: INTF_MIN_BUMP_BINS = 1.0
  INTF_ENVELOPE_ORDER: 9,        // backend: INTF_ENVELOPE_ORDER = 9
  INTF_VARIANCE_WINDOW: 7,
  INTF_VARIANCE_SIGMA: 2.5,
  INTF_CUC_CURV_SIGMA: 3.5,
  INTF_MERGE_GAP_HZ: 200e3,

  // Gap detection — must match backend exactly
  GAP_DEPTH_DB: 2.5,
  GAP_MIN_BINS: 3,               // backend: GAP_MIN_BINS = 3 (was wrongly 32)

  // Valley detection
  VALLEY_DEPTH_DB: 3.0,
  VALLEY_MIN_WIDTH_HZ: 10e3,

  // Hysteresis
  CARRIER_HIGH_THRESH_OFFSET: 4.0,
};

export interface CarrierDetection {
  startBin: number;
  endBin: number;
  startFreq: number;
  endFreq: number;
  centerFreq: number;
  bandwidth: number;
  peakPower: number;
  totalPower: number;
  cnRatio: number;
  isAuthorized: boolean;
}

export interface InterferenceDetection {
  startFreq: number;
  endFreq: number;
  peakFreq: number;
  strengthDb: number;
  method: string;
  isGap: boolean;
  parentCarrierId?: number;
}

export interface DetectionResult {
  psd: Float64Array;
  freqAxis: Float64Array;
  noiseFloor: number;
  detectThreshold: number;
  carriers: CarrierDetection[];
  interferences: InterferenceDetection[];
  maxHold: Float64Array | null;
  minHold: Float64Array | null;
}

export interface LogEntry {
  time: string;
  message: string;
  color: string;
  type: 'carrier' | 'interference' | 'gap' | 'info' | 'warning';
}

// =====================================================
// SIMULATED SPECTRUM GENERATION
// =====================================================

interface SimulatedCarrier {
  centerFreqMHz: number;
  bandwidthKHz: number;
  powerDb: number;
  hasInterference: boolean;
  intfOffsetKHz: number;
  intfPowerDb: number;
  intfWidthKHz: number;
}

const SIMULATED_CARRIERS: SimulatedCarrier[] = [
  { centerFreqMHz: 62, bandwidthKHz: 800, powerDb: 35, hasInterference: false, intfOffsetKHz: 0, intfPowerDb: 0, intfWidthKHz: 0 },
  { centerFreqMHz: 65, bandwidthKHz: 1200, powerDb: 40, hasInterference: true, intfOffsetKHz: 200, intfPowerDb: 8, intfWidthKHz: 100 },
  { centerFreqMHz: 68.5, bandwidthKHz: 600, powerDb: 30, hasInterference: false, intfOffsetKHz: 0, intfPowerDb: 0, intfWidthKHz: 0 },
  { centerFreqMHz: 72, bandwidthKHz: 1500, powerDb: 45, hasInterference: true, intfOffsetKHz: -400, intfPowerDb: 12, intfWidthKHz: 150 },
  { centerFreqMHz: 76, bandwidthKHz: 500, powerDb: 25, hasInterference: false, intfOffsetKHz: 0, intfPowerDb: 0, intfWidthKHz: 0 },
  { centerFreqMHz: 78.5, bandwidthKHz: 900, powerDb: 38, hasInterference: true, intfOffsetKHz: 100, intfPowerDb: 6, intfWidthKHz: 80 },
];

let frameCount = 0;

export function generateSimulatedPSD(): { psd: Float64Array; freqAxis: Float64Array } {
  const { FFT_SIZE, HW_SAMPLE_RATE, CENTER_FREQ } = DSP_CONFIG;
  const df = HW_SAMPLE_RATE / FFT_SIZE;
  frameCount++;

  const freqAxis = new Float64Array(FFT_SIZE);
  const psd = new Float64Array(FFT_SIZE);

  // Build frequency axis
  for (let i = 0; i < FFT_SIZE; i++) {
    freqAxis[i] = (i - FFT_SIZE / 2) * df + CENTER_FREQ;
  }

  // Base noise floor with slight variation
  const noiseBase = -45 + Math.sin(frameCount * 0.01) * 2;
  for (let i = 0; i < FFT_SIZE; i++) {
    psd[i] = noiseBase + (Math.random() - 0.5) * 6;
  }

  // Add carriers
  for (const carrier of SIMULATED_CARRIERS) {
    const cf = carrier.centerFreqMHz * 1e6;
    const bw = carrier.bandwidthKHz * 1e3;
    const drift = Math.sin(frameCount * 0.02 + carrier.centerFreqMHz) * 0.5;

    for (let i = 0; i < FFT_SIZE; i++) {
      const f = freqAxis[i];
      const dist = Math.abs(f - cf) / (bw / 2);
      if (dist < 1.0) {
        // Raised cosine shape
        const shape = 0.5 * (1 + Math.cos(Math.PI * dist));
        psd[i] = Math.max(psd[i], noiseBase + carrier.powerDb * shape + drift + (Math.random() - 0.5) * 2);
      } else if (dist < 1.3) {
        // Shoulder rolloff
        const rolloff = Math.exp(-(dist - 1.0) * 10);
        psd[i] = Math.max(psd[i], noiseBase + carrier.powerDb * 0.3 * rolloff + (Math.random() - 0.5) * 2);
      }
    }

    // Add interference spikes
    if (carrier.hasInterference) {
      const intfFreq = cf + carrier.intfOffsetKHz * 1e3;
      const intfBw = carrier.intfWidthKHz * 1e3;
      // Interference flickers in and out
      const intfActive = Math.sin(frameCount * 0.05 + carrier.centerFreqMHz * 0.1) > -0.3;
      if (intfActive) {
        for (let i = 0; i < FFT_SIZE; i++) {
          const f = freqAxis[i];
          const dist = Math.abs(f - intfFreq) / (intfBw / 2);
          if (dist < 1.0) {
            const shape = Math.exp(-dist * dist * 2);
            psd[i] += carrier.intfPowerDb * shape + (Math.random() - 0.5) * 1.5;
          }
        }
      }
    }
  }

  return { psd, freqAxis };
}

// =====================================================
// NOISE FLOOR ESTIMATION (Adaptive rolling percentile)
// =====================================================

function percentile(arr: Float64Array | number[], p: number): number {
  const sorted = Array.from(arr).sort((a, b) => a - b);
  const idx = (p / 100) * (sorted.length - 1);
  const lo = Math.floor(idx);
  const hi = Math.ceil(idx);
  if (lo === hi) return sorted[lo];
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (idx - lo);
}

export function estimateNoiseFloor(psd: Float64Array): number {
  const { NF_PERCENTILE, NF_ROLLING_WINDOW_DIV } = DSP_CONFIG;
  const n = psd.length;
  const windowSize = Math.max(32, Math.floor(n / NF_ROLLING_WINDOW_DIV));
  const step = Math.max(1, Math.floor(windowSize / 4));
  const floors: number[] = [];

  for (let i = 0; i <= n - windowSize; i += step) {
    const window = psd.slice(i, i + windowSize);
    floors.push(percentile(window, NF_PERCENTILE));
  }

  if (floors.length === 0) return percentile(psd, NF_PERCENTILE);
  floors.sort((a, b) => a - b);
  return floors[Math.floor(floors.length / 2)];
}

// =====================================================
// SMOOTHING
// =====================================================

export function smoothPSD(psd: Float64Array, taps: number): Float64Array {
  const n = psd.length;
  const result = new Float64Array(n);
  const half = Math.floor(taps / 2);

  for (let i = 0; i < n; i++) {
    let sum = 0;
    let count = 0;
    for (let j = Math.max(0, i - half); j <= Math.min(n - 1, i + half); j++) {
      sum += psd[j];
      count++;
    }
    result[i] = sum / count;
  }

  return result;
}

// =====================================================
// CARRIER DETECTION
// =====================================================

export function detectCarriers(
  psdSmoothed: Float64Array,
  freqAxis: Float64Array,
  noiseFloor: number,
  displayPsd: Float64Array
): CarrierDetection[] {
  const { FFT_SIZE, HW_SAMPLE_RATE, CARRIER_K_SIGMA, MORPH_OPEN_BINS, MORPH_CLOSE_BINS,
    MIN_CARRIER_BW_HZ, CARRIER_HIGH_THRESH_OFFSET, ADAPTIVE_MERGE_BW_FACTOR } = DSP_CONFIG;
  const df = HW_SAMPLE_RATE / FFT_SIZE;
  const n = psdSmoothed.length;

  // Noise sigma from noise-like bins
  let noiseBins: number[] = [];
  for (let i = 0; i < n; i++) {
    if (psdSmoothed[i] < noiseFloor + 10) noiseBins.push(psdSmoothed[i]);
  }
  let noiseSigma = 1.0;
  if (noiseBins.length > 4) {
    const mean = noiseBins.reduce((a, b) => a + b, 0) / noiseBins.length;
    noiseSigma = Math.sqrt(noiseBins.reduce((a, b) => a + (b - mean) ** 2, 0) / noiseBins.length);
    noiseSigma = Math.max(noiseSigma, 0.3);
  }

  const detectThreshold = noiseFloor + Math.max(2.5, CARRIER_K_SIGMA * noiseSigma);

  // Binary mask
  let above = new Uint8Array(n);
  for (let i = 0; i < n; i++) {
    above[i] = psdSmoothed[i] > detectThreshold ? 1 : 0;
  }

  // Morphological opening (erode then dilate)
  if (MORPH_OPEN_BINS > 1) {
    const h = Math.floor(MORPH_OPEN_BINS / 2);
    const eroded = new Uint8Array(n);
    for (let i = 0; i < n; i++) {
      let allTrue = true;
      for (let k = -h; k <= h; k++) {
        const idx = (i + k + n) % n;
        if (!above[idx]) { allTrue = false; break; }
      }
      eroded[i] = allTrue ? 1 : 0;
    }
    const dilated = new Uint8Array(n);
    for (let i = 0; i < n; i++) {
      for (let k = -h; k <= h; k++) {
        const idx = (i + k + n) % n;
        if (eroded[idx]) { dilated[i] = 1; break; }
      }
    }
    above = dilated;
  }

  // Morphological closing (dilate then erode)
  if (MORPH_CLOSE_BINS > 1) {
    const h = Math.floor(MORPH_CLOSE_BINS / 2);
    const dilated = new Uint8Array(n);
    for (let i = 0; i < n; i++) {
      for (let k = -h; k <= h; k++) {
        const idx = (i + k + n) % n;
        if (above[idx]) { dilated[i] = 1; break; }
      }
    }
    const eroded = new Uint8Array(n);
    for (let i = 0; i < n; i++) {
      let allTrue = true;
      for (let k = -h; k <= h; k++) {
        const idx = (i + k + n) % n;
        if (!dilated[idx]) { allTrue = false; break; }
      }
      eroded[i] = allTrue ? 1 : 0;
    }
    above = eroded;
  }

  // Hysteresis: require a high-threshold core
  const highThreshold = detectThreshold + CARRIER_HIGH_THRESH_OFFSET;
  {
    const rises: number[] = [];
    const falls: number[] = [];
    for (let i = 1; i < n; i++) {
      if (above[i] && !above[i - 1]) rises.push(i);
      if (!above[i] && above[i - 1]) falls.push(i);
    }
    if (above[0]) rises.unshift(0);
    if (above[n - 1]) falls.push(n);

    for (let k = 0; k < Math.min(rises.length, falls.length); k++) {
      let hasHigh = false;
      for (let i = rises[k]; i < falls[k]; i++) {
        if (psdSmoothed[i] > highThreshold) { hasHigh = true; break; }
      }
      if (!hasHigh) {
        for (let i = rises[k]; i < falls[k]; i++) above[i] = 0;
      }
    }
  }

  // Extract spans
  const rises: number[] = [];
  const falls: number[] = [];
  for (let i = 1; i < n; i++) {
    if (above[i] && !above[i - 1]) rises.push(i);
    if (!above[i] && above[i - 1]) falls.push(i);
  }
  if (above[0]) rises.unshift(0);
  if (above[n - 1]) falls.push(n - 1);

  const minBins = Math.max(2, Math.round(MIN_CARRIER_BW_HZ / df));
  let rawSpans: [number, number][] = [];
  for (let k = 0; k < Math.min(rises.length, falls.length); k++) {
    if (falls[k] - rises[k] >= minBins) {
      rawSpans.push([rises[k], falls[k]]);
    }
  }

  // Adaptive merging
  if (rawSpans.length > 1) {
    const merged: [number, number][] = [[...rawSpans[0]]];
    for (let i = 1; i < rawSpans.length; i++) {
      const [r1, f1] = merged[merged.length - 1];
      const [r2, f2] = rawSpans[i];
      const bw1 = (f1 - r1) * df;
      const bw2 = (f2 - r2) * df;
      const gap = Math.max(0, freqAxis[r2] - freqAxis[f1]);
      const mergeThr = Math.max(MIN_CARRIER_BW_HZ, ADAPTIVE_MERGE_BW_FACTOR * Math.min(bw1, bw2));
      if (gap < mergeThr) {
        merged[merged.length - 1][1] = f2;
      } else {
        merged.push([r2, f2]);
      }
    }
    rawSpans = merged;
  }

  // Build carrier results
  const carriers: CarrierDetection[] = [];
  for (const [r, f] of rawSpans) {
    const startFreq = freqAxis[r];
    const endFreq = freqAxis[Math.min(f, n - 1)];
    const centerFreq = (startFreq + endFreq) / 2;
    const bandwidth = endFreq - startFreq;

    let peakPower = -Infinity;
    let totalLinear = 0;
    for (let i = r; i <= Math.min(f, n - 1); i++) {
      peakPower = Math.max(peakPower, displayPsd[i]);
      totalLinear += Math.pow(10, displayPsd[i] / 10);
    }
    const totalPower = 10 * Math.log10(totalLinear + 1e-12);
    const bins = f - r + 1;
    const noiseLinear = Math.pow(10, noiseFloor / 10) * bins;
    const cnRatio = totalPower - 10 * Math.log10(noiseLinear + 1e-12);

    carriers.push({
      startBin: r,
      endBin: f,
      startFreq,
      endFreq,
      centerFreq,
      bandwidth,
      peakPower,
      totalPower,
      cnRatio,
      isAuthorized: true, // In simulation, all are authorized
    });
  }

  return carriers;
}

// =====================================================
// INTERFERENCE DETECTION (intra-carrier)
// =====================================================

export function detectInterference(
  psd: Float64Array,
  freqAxis: Float64Array,
  carriers: CarrierDetection[]
): InterferenceDetection[] {
  const { INTF_BUMP_THRESHOLD_DB, INTF_MIN_BUMP_BINS, INTF_ENVELOPE_ORDER,
    INTF_VARIANCE_WINDOW, INTF_VARIANCE_SIGMA, NF_PERCENTILE } = DSP_CONFIG;

  const results: InterferenceDetection[] = [];

  carriers.forEach((carrier, carrierIdx) => {
    const r = carrier.startBin;
    const f = carrier.endBin;
    const n = f - r + 1;
    if (n < 6) return;

    const segment = psd.slice(r, r + n);
    const freqSeg = freqAxis.slice(r, r + n);

    // Local statistics
    const localFloor = percentile(segment, NF_PERCENTILE);
    const belowFloor: number[] = [];
    for (let i = 0; i < n; i++) {
      if (segment[i] < localFloor + 8) belowFloor.push(segment[i]);
    }
    let localSigma = 0.5;
    if (belowFloor.length > 2) {
      const mean = belowFloor.reduce((a, b) => a + b, 0) / belowFloor.length;
      localSigma = Math.sqrt(belowFloor.reduce((a, b) => a + (b - mean) ** 2, 0) / belowFloor.length);
      localSigma = Math.max(localSigma, 0.5);
    }
    const bumpThr = Math.max(INTF_BUMP_THRESHOLD_DB, 1.5 * localSigma);

    // 1. Spectral bump detector
    const half = Math.min(INTF_ENVELOPE_ORDER, Math.floor(n / 2));
    if (half >= 1) {
      const envelope = new Float64Array(n);
      for (let i = 0; i < n; i++) {
        const vals: number[] = [];
        for (let j = Math.max(0, i - half); j <= Math.min(n - 1, i + half); j++) {
          vals.push(segment[j]);
        }
        vals.sort((a, b) => a - b);
        envelope[i] = vals[Math.floor(vals.length / 2)];
      }

      const residual = new Float64Array(n);
      for (let i = 0; i < n; i++) residual[i] = segment[i] - envelope[i];

      // Find bump regions
      let inBump = false;
      let bumpStart = 0;
      for (let i = 0; i <= n; i++) {
        const isBump = i < n && residual[i] > bumpThr;
        if (isBump && !inBump) { bumpStart = i; inBump = true; }
        if (!isBump && inBump) {
          if (i - bumpStart >= INTF_MIN_BUMP_BINS) {
            let peakIdx = bumpStart;
            for (let j = bumpStart; j < i; j++) {
              if (segment[j] > segment[peakIdx]) peakIdx = j;
            }
            results.push({
              startFreq: freqSeg[bumpStart],
              endFreq: freqSeg[Math.min(i, n - 1)],
              peakFreq: freqSeg[peakIdx],
              strengthDb: residual[peakIdx],
              method: 'bump',
              isGap: false,
              parentCarrierId: carrierIdx,
            });
          }
          inBump = false;
        }
      }
    }

    // 2. Local variance anomaly
    const w = Math.min(INTF_VARIANCE_WINDOW, Math.floor(n / 3));
    if (w >= 3) {
      const localVar = new Float64Array(n);
      for (let i = 0; i < n; i++) {
        const start = Math.max(0, i - w);
        const end = Math.min(n, i + w + 1);
        const vals = Array.from(segment.slice(start, end));
        const mean = vals.reduce((a, b) => a + b, 0) / vals.length;
        localVar[i] = vals.reduce((a, b) => a + (b - mean) ** 2, 0) / vals.length;
      }
      const medianVar = percentile(localVar, 50) + 1e-6;

      let inAnom = false;
      let anomStart = 0;
      for (let i = 0; i <= n; i++) {
        const isAnom = i < n && localVar[i] > INTF_VARIANCE_SIGMA * medianVar;
        if (isAnom && !inAnom) { anomStart = i; inAnom = true; }
        if (!isAnom && inAnom) {
          if (i - anomStart >= INTF_MIN_BUMP_BINS) {
            let peakIdx = anomStart;
            for (let j = anomStart; j < i; j++) {
              if (segment[j] > segment[peakIdx]) peakIdx = j;
            }
            const median = percentile(segment, 50);
            const strength = segment[peakIdx] - median;
            if (strength >= Math.max(2.0, localSigma)) {
              results.push({
                startFreq: freqSeg[anomStart],
                endFreq: freqSeg[Math.min(i, n - 1)],
                peakFreq: freqSeg[peakIdx],
                strengthDb: strength,
                method: 'variance',
                isGap: false,
                parentCarrierId: carrierIdx,
              });
            }
          }
          inAnom = false;
        }
      }
    }
  });

  // Merge overlapping results
  if (results.length <= 1) return results;
  results.sort((a, b) => a.startFreq - b.startFreq);
  const merged: InterferenceDetection[] = [{ ...results[0] }];
  for (let i = 1; i < results.length; i++) {
    const prev = merged[merged.length - 1];
    if (results[i].startFreq - prev.endFreq <= DSP_CONFIG.INTF_MERGE_GAP_HZ) {
      prev.endFreq = Math.max(prev.endFreq, results[i].endFreq);
      if (results[i].strengthDb > prev.strengthDb) {
        prev.peakFreq = results[i].peakFreq;
        prev.strengthDb = results[i].strengthDb;
      }
      if (!prev.method.includes(results[i].method)) {
        prev.method += '+' + results[i].method;
      }
    } else {
      merged.push({ ...results[i] });
    }
  }

  return merged;
}

// =====================================================
// MAX/MIN HOLD
// =====================================================

export function updateMaxHold(current: Float64Array | null, psd: Float64Array): Float64Array {
  if (!current || current.length !== psd.length) {
    return new Float64Array(psd);
  }
  const result = new Float64Array(psd.length);
  for (let i = 0; i < psd.length; i++) {
    result[i] = Math.max(current[i], psd[i]);
  }
  return result;
}

export function updateMinHold(current: Float64Array | null, psd: Float64Array): Float64Array {
  if (!current || current.length !== psd.length) {
    return new Float64Array(psd);
  }
  const result = new Float64Array(psd.length);
  for (let i = 0; i < psd.length; i++) {
    result[i] = Math.min(current[i], psd[i]);
  }
  return result;
}

// =====================================================
// FULL PIPELINE
// =====================================================

export function runDetectionPipeline(
  enableIntf: boolean,
  enableGap: boolean,
  enableMaxHold: boolean,
  enableMinHold: boolean,
  maxHoldData: Float64Array | null,
  minHoldData: Float64Array | null,
  smoothEnabled: boolean,
  smoothAlpha: number,
  psdAvg: Float64Array | null,
): DetectionResult & { psdAvg: Float64Array; maxHold: Float64Array | null; minHold: Float64Array | null } {
  const { psd, freqAxis } = generateSimulatedPSD();
  const { SMOOTH_BW_HZ, HW_SAMPLE_RATE, FFT_SIZE } = DSP_CONFIG;
  const df = HW_SAMPLE_RATE / FFT_SIZE;

  // Smoothing
  let displayPsd = psd;
  let newPsdAvg = psdAvg;
  if (smoothEnabled && smoothAlpha > 0) {
    if (!newPsdAvg || newPsdAvg.length !== psd.length) {
      newPsdAvg = new Float64Array(psd);
    } else {
      const alpha = 1 - (1 - smoothAlpha) ** 2;
      const result = new Float64Array(psd.length);
      for (let i = 0; i < psd.length; i++) {
        result[i] = alpha * newPsdAvg[i] + (1 - alpha) * psd[i];
      }
      newPsdAvg = result;
    }
    displayPsd = newPsdAvg;
  } else {
    newPsdAvg = new Float64Array(psd);
  }

  // Smooth for detection
  const smoothTaps = Math.max(3, Math.round(SMOOTH_BW_HZ / df)) | 1;
  const psdSmoothed = smoothPSD(displayPsd, smoothTaps);

  // Noise floor
  const noiseFloor = estimateNoiseFloor(psdSmoothed);

  // Noise sigma for detection threshold
  let noiseBins: number[] = [];
  for (let i = 0; i < psdSmoothed.length; i++) {
    if (psdSmoothed[i] < noiseFloor + 10) noiseBins.push(psdSmoothed[i]);
  }
  let noiseSigma = 1.0;
  if (noiseBins.length > 4) {
    const mean = noiseBins.reduce((a, b) => a + b, 0) / noiseBins.length;
    noiseSigma = Math.sqrt(noiseBins.reduce((a, b) => a + (b - mean) ** 2, 0) / noiseBins.length);
    noiseSigma = Math.max(noiseSigma, 0.3);
  }
  const detectThreshold = noiseFloor + Math.max(2.5, DSP_CONFIG.CARRIER_K_SIGMA * noiseSigma);

  // Carrier detection
  const carriers = detectCarriers(psdSmoothed, freqAxis, noiseFloor, displayPsd);

  // Interference detection
  let interferences: InterferenceDetection[] = [];
  if (enableIntf) {
    interferences = detectInterference(displayPsd, freqAxis, carriers);
  }

  // Max/Min hold
  const newMaxHold = enableMaxHold ? updateMaxHold(maxHoldData, displayPsd) : null;
  const newMinHold = enableMinHold ? updateMinHold(minHoldData, displayPsd) : null;

  return {
    psd: displayPsd,
    freqAxis,
    noiseFloor,
    detectThreshold,
    carriers,
    interferences,
    maxHold: newMaxHold,
    minHold: newMinHold,
    psdAvg: newPsdAvg,
  };
}
