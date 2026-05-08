import { useState, useEffect, useCallback, useRef } from 'react';
import { ArrowLeft, Download, Wifi, WifiOff, Activity } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useAppStore } from '@/store/appStore';
import { SpectrumAnalyzer } from './SpectrumAnalyzer';
import { DetectionLog } from './DetectionLog';
import { SpectrumControls } from './SpectrumControls';
import { MetricsGrid } from './MetricsGrid';
import { runDetectionPipeline, DetectionResult, LogEntry } from '@/lib/dspEngine';
import {
  cmsAddAuthorizedFrequency,
  cmsDeleteAuthorizedFrequency,
  cmsGetAuthorizedFrequencies,
  cmsStartMonitor,
  cmsStopMonitor,
  cmsFetchSnapshot,
  cmsHealth,
  cmsSetSmoothing,
  snapshotToDetectionResult,
  setApiTarget,
} from '@/lib/cmsApi';
import { exportSignalData } from '@/lib/exportData';
import { SignalData } from '@/types/satellite';

export const SignalMonitor = () => {
  const { monitoringSatellite: sat, setMonitoringSatellite } = useAppStore();
  
  // Determine if this is a live backend (has valid Pi IP) or simulation mode
  const hasValidIp = sat?.piIpAddress && sat.piIpAddress !== '—' && !sat.piIpAddress.includes('(');
  const isLiveBackend = hasValidIp;

  const [piConnected, setPiConnected] = useState(false);
  const [detectionResult, setDetectionResult] = useState<DetectionResult | null>(null);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [anomalyDetected, setAnomalyDetected] = useState(false);

  const [enableIntf, setEnableIntf] = useState(true);
  const [enableMaxHold, setEnableMaxHold] = useState(false);
  const [enableMinHold, setEnableMinHold] = useState(false);
  const [smoothEnabled, setSmoothEnabled] = useState(false);
  const [smoothAlpha, setSmoothAlpha] = useState(0.0);

  const maxHoldRef = useRef<Float64Array | null>(null);
  const minHoldRef = useRef<Float64Array | null>(null);
  const psdAvgRef = useRef<Float64Array | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval>>();
  const frameCountRef = useRef(0);

  const [latestMetrics, setLatestMetrics] = useState<SignalData | undefined>();
  const [authorizedList, setAuthorizedList] = useState<Array<{ center: number; bandwidth: number; label?: string }>>([]);
  const [cfMHz, setCfMHz] = useState('');
  const [bwKHz, setBwKHz] = useState('500');
  const [authLabel, setAuthLabel] = useState('');
  const [authBusy, setAuthBusy] = useState(false);

  const antennaId = (sat?.name || 'gsat-30').trim().toLowerCase().replace(/\s+/g, '-');

  useEffect(() => {
    if (!isLiveBackend || !sat) return;
    
    // Set the API target to the satellite's Pi IP address
    setApiTarget(sat.piIpAddress);
    
    void cmsStartMonitor(true, antennaId).catch(() => undefined);
    return () => {
      void cmsStopMonitor(true);
      maxHoldRef.current = null;
      minHoldRef.current = null;
      // Reset API target when unmounting
      setApiTarget(null);
    };
  }, [isLiveBackend, sat, antennaId]);

  const refreshAuthorized = useCallback(async () => {
    if (!sat) return;
    try {
      const rows = await cmsGetAuthorizedFrequencies(antennaId);
      setAuthorizedList(rows);
    } catch {
      setAuthorizedList([]);
    }
  }, [sat, antennaId]);

  useEffect(() => {
    void refreshAuthorized();
  }, [refreshAuthorized]);

  // Sync smoothing controls to backend so detection is affected, not just visuals
  useEffect(() => {
    if (!isLiveBackend) return;
    void cmsSetSmoothing(smoothEnabled, smoothAlpha);
  }, [isLiveBackend, smoothEnabled, smoothAlpha]);

  const processFrameSimulated = useCallback(() => {
    if (!sat || isLiveBackend) return;
    frameCountRef.current++;

    const result = runDetectionPipeline(
      enableIntf,
      false,
      enableMaxHold,
      enableMinHold,
      maxHoldRef.current,
      minHoldRef.current,
      smoothEnabled,
      smoothAlpha,
      psdAvgRef.current,
    );

    maxHoldRef.current = result.maxHold;
    minHoldRef.current = result.minHold;
    psdAvgRef.current = result.psdAvg;

    setDetectionResult(result);

    const hasInterference = result.interferences.length > 0;
    setAnomalyDetected(hasInterference);

    const avgHealth = hasInterference ? 55 + Math.random() * 20 : 85 + Math.random() * 10;
    setLatestMetrics({
      time: new Date().toLocaleTimeString(),
      frequency: 70e6,
      power: result.noiseFloor + 30,
      noise: result.noiseFloor,
      cnRatio: result.carriers.length > 0 ? result.carriers[0].cnRatio : 0,
      ebNo: result.carriers.length > 0 ? result.carriers[0].cnRatio * 0.7 : 0,
      signalHealth: avgHealth,
    });

    if (frameCountRef.current % 5 === 0) {
      const d = new Date();
      const now = d.toLocaleTimeString('en-US', { hour12: false }) + '.' + Math.floor(d.getMilliseconds() / 100);
      const newLogs: LogEntry[] = [];

      for (let i = 0; i < result.carriers.length; i++) {
        const c = result.carriers[i];
        const carrierPower = c.peakPower - 3; // Approximate total power from peak
        const ebNo = c.cnRatio * 0.7; // Eb/No calculation
        const freqStart = c.centerFreq - (c.bandwidth / 2);
        const freqStop = c.centerFreq + (c.bandwidth / 2);
        
        newLogs.push({
          time: now,
          message: `Carrier ${i + 1} [AUTH]  |  Freq: ${(c.centerFreq / 1e6).toFixed(3)} MHz  |  Pwr: ${carrierPower.toFixed(1)} dB  |  BW: ${(c.bandwidth / 1e3).toFixed(1)} kHz  |  Peak: ${c.peakPower.toFixed(1)} dB  |  Noise: ${result.noiseFloor.toFixed(1)} dB  |  Range: ${(freqStart / 1e6).toFixed(3)}-${(freqStop / 1e6).toFixed(3)} MHz  |  C/N: ${c.cnRatio.toFixed(2)} dB  |  Eb/No: ${ebNo.toFixed(2)} dB`,
          color: ['#4ec9b0', '#6abf69', '#98e898', '#00ff7f', '#b2fab4'][i % 5],
          type: 'carrier',
        });
      }

      for (const intf of result.interferences) {
        const intfBw = (intf.endFreq - intf.startFreq) / 1e3;
        newLogs.push({
          time: now,
          message: `  └─ INTERFERENCE [${intf.method.toUpperCase()}]  |  Center: ${(intf.peakFreq / 1e6).toFixed(4)} MHz  |  BW: ${intfBw.toFixed(1)} kHz  |  Strength: +${intf.strengthDb.toFixed(1)} dB  |  Range: ${(intf.startFreq / 1e6).toFixed(4)}-${(intf.endFreq / 1e6).toFixed(4)} MHz`,
          color: '#ff6b6b',
          type: 'interference',
        });
      }

      if (result.carriers.length === 0) {
        const cnRatio = Math.max(0, result.detectThreshold - result.noiseFloor);
        newLogs.push({
          time: now,
          message: `No carriers detected  |  Noise: ${result.noiseFloor.toFixed(1)} dB  |  Threshold: ${result.detectThreshold.toFixed(1)} dB  |  C/N: ${cnRatio.toFixed(2)} dB  |  Center: ${(70).toFixed(1)} MHz  |  BW: ${(20).toFixed(1)} MHz`,
          color: '#808080',
          type: 'info',
        });
      }

      setLogs((prev) => [...prev.slice(-200), ...newLogs]);
    }
  }, [sat, isLiveBackend, enableIntf, enableMaxHold, enableMinHold, smoothEnabled, smoothAlpha]);

  useEffect(() => {
    if (!sat || isLiveBackend) return;
    const t = setTimeout(() => setPiConnected(true), 1500);
    return () => clearTimeout(t);
  }, [sat, isLiveBackend]);

  useEffect(() => {
    if (!sat || isLiveBackend) return;
    intervalRef.current = setInterval(processFrameSimulated, 100);
    return () => clearInterval(intervalRef.current);
  }, [sat, isLiveBackend, processFrameSimulated]);

  useEffect(() => {
    if (!sat || !isLiveBackend) return;

    const tick = async () => {
      try {
        const [health, snap] = await Promise.all([cmsHealth(), cmsFetchSnapshot()]);
        const hasPsd = !!(snap.psd_db?.length && snap.freq_mhz?.length);
        const ok = health.detector_running && hasPsd && !snap.error;
        setPiConnected(ok);

        if (!hasPsd || snap.error) {
          setDetectionResult(null);
          return;
        }

        let psd = Float64Array.from(snap.psd_db!);

        // Smoothing is handled entirely by the backend (Interference.py).
        // The snapshot already contains the smoothed PSD — render it directly.

        if (enableMaxHold) {
          if (!maxHoldRef.current || maxHoldRef.current.length !== psd.length) {
            maxHoldRef.current = psd.slice();
          } else {
            for (let i = 0; i < psd.length; i++) {
              maxHoldRef.current[i] = Math.max(maxHoldRef.current[i]!, psd[i]!);
            }
          }
        } else {
          maxHoldRef.current = null;
        }

        if (enableMinHold) {
          if (!minHoldRef.current || minHoldRef.current.length !== psd.length) {
            minHoldRef.current = psd.slice();
          } else {
            for (let i = 0; i < psd.length; i++) {
              minHoldRef.current[i] = Math.min(minHoldRef.current[i]!, psd[i]!);
            }
          }
        } else {
          minHoldRef.current = null;
        }

        // Build a patched snapshot with the (possibly smoothed) PSD for rendering
        const patchedSnap = { ...snap, psd_db: Array.from(psd) };
        const dr = snapshotToDetectionResult(patchedSnap, maxHoldRef.current, minHoldRef.current);
        setDetectionResult(dr);

        const intfN = snap.interference?.length ?? 0;
        const unauthN = snap.unauth_count ?? 0;
        const hasAnomaly = intfN > 0 || unauthN > 0;
        setAnomalyDetected(hasAnomaly);

        const cn0 =
          snap.carriers && snap.carriers.length > 0
            ? Math.max(0, (snap.detect_threshold_db ?? 0) - (snap.noise_db ?? 0))
            : 0;
        setLatestMetrics({
          time: new Date().toLocaleTimeString(),
          frequency: (snap.hw_center_mhz ?? 70) * 1e6,
          power: (snap.noise_db ?? 0) + 28,
          noise: snap.noise_db ?? 0,
          cnRatio: cn0,
          ebNo: cn0 * 0.7,
          signalHealth: hasAnomaly ? 52 : 90,
        });

        const tail = snap.logs ?? [];
        setLogs(
          tail.slice(-400).map((l) => ({
            time: '',
            message: l.msg,
            color: l.color ?? '#d4d4d4',
            type: 'info' as const,
          })),
        );
      } catch {
        setPiConnected(false);
      }
    };

    void tick();
    intervalRef.current = setInterval(() => void tick(), 400);
    return () => clearInterval(intervalRef.current);
  }, [sat, isLiveBackend, enableMaxHold, enableMinHold, smoothEnabled, smoothAlpha]);

  const handleResetHold = useCallback(() => {
    maxHoldRef.current = null;
    minHoldRef.current = null;
  }, []);

  if (!sat) return null;

  return (
    <div className="min-h-screen bg-background">
      <div className="glass-panel rounded-none border-x-0 border-t-0 sticky top-0 z-30">
        <div className="flex items-center justify-between px-6 py-3">
          <div className="flex items-center gap-4">
            <Button variant="ghost" size="sm" onClick={() => setMonitoringSatellite(null)} className="text-muted-foreground">
              <ArrowLeft className="w-4 h-4 mr-1" /> Fleet
            </Button>
            <div className="h-6 w-px bg-border/30" />
            <div>
              <div className="flex items-center gap-2">
                <Activity className="w-4 h-4 text-primary" />
                <h1 className="font-bold text-sm">{sat.name}</h1>
                <span className="text-[10px] font-mono text-muted-foreground bg-secondary/50 px-2 py-0.5 rounded">{sat.band}</span>
              </div>
              <p className="text-[10px] font-mono text-muted-foreground">
                INTERFERENCE DETECTION • {isLiveBackend ? 'LIVE BACKEND (Python)' : 'SIMULATION'}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div
              className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-mono ${
                piConnected ? 'bg-success/10 text-success border border-success/30' : 'bg-warning/10 text-warning border border-warning/30'
              }`}
            >
              {piConnected ? <Wifi className="w-3 h-3" /> : <WifiOff className="w-3 h-3 animate-pulse" />}
              {piConnected
                ? isLiveBackend
                  ? `Detector streaming • ${sat.piIpAddress}`
                  : `Pi Connected • ${sat.piIpAddress}`
                : isLiveBackend
                  ? 'Starting detector / waiting for spectrum…'
                  : 'Connecting to Pi...'}
            </div>
            {anomalyDetected && (
              <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-destructive/10 text-destructive border border-destructive/30 text-xs font-mono animate-pulse">
                {'\u26a0'} INTERFERENCE DETECTED
              </div>
            )}
            <Button
              size="sm"
              variant="outline"
              onClick={() => {
                const signalData: SignalData[] = latestMetrics ? [latestMetrics] : [];
                exportSignalData(signalData, sat.name);
              }}
              className="border-border/40 text-xs"
            >
              <Download className="w-3 h-3 mr-1.5" /> Export XLSX
            </Button>
          </div>
        </div>
      </div>

      <div className="p-6 space-y-4">
        <MetricsGrid data={latestMetrics} anomaly={anomalyDetected} connected={piConnected} />

        <div className="grid grid-cols-1 xl:grid-cols-12 gap-4">
          <div className="xl:col-span-9" style={{ minHeight: 450 }}>
            <SpectrumAnalyzer data={detectionResult} enableMaxHold={enableMaxHold} enableMinHold={enableMinHold} />
          </div>

          <div className="xl:col-span-3 space-y-4">
            {isLiveBackend && (
              <p className="text-[10px] text-muted-foreground leading-relaxed px-1">
                Live mode: smoothing is applied in the backend before detection. Max/Min hold are applied in the browser as additional visual layers on the streamed PSD.
              </p>
            )}
            <SpectrumControls
              enableIntf={enableIntf}
              setEnableIntf={setEnableIntf}
              enableMaxHold={enableMaxHold}
              setEnableMaxHold={setEnableMaxHold}
              enableMinHold={enableMinHold}
              setEnableMinHold={setEnableMinHold}
              smoothEnabled={smoothEnabled}
              setSmoothEnabled={setSmoothEnabled}
              smoothAlpha={smoothAlpha}
              setSmoothAlpha={setSmoothAlpha}
              onResetHold={handleResetHold}
            />
          </div>
        </div>

        <div style={{ height: 280 }}>
          <DetectionLog logs={logs} onClear={() => setLogs([])} />
        </div>

        <div className="glass-card p-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold">Authorized Frequency Manager</h3>
            <span className="text-[10px] font-mono text-muted-foreground">
              Antenna: {antennaId}
            </span>
          </div>
          <p className="text-[11px] text-muted-foreground mb-3">
            Per-antenna authorization list. Values tuned for this antenna are isolated from others.
          </p>
          <div className="grid grid-cols-1 md:grid-cols-5 gap-2 mb-3">
            <input
              className="bg-secondary/30 border border-border/40 rounded-md px-2 py-2 text-xs font-mono"
              placeholder="Center MHz (e.g. 70)"
              value={cfMHz}
              onChange={(e) => setCfMHz(e.target.value)}
            />
            <input
              className="bg-secondary/30 border border-border/40 rounded-md px-2 py-2 text-xs font-mono"
              placeholder="BW kHz (e.g. 500)"
              value={bwKHz}
              onChange={(e) => setBwKHz(e.target.value)}
            />
            <input
              className="bg-secondary/30 border border-border/40 rounded-md px-2 py-2 text-xs font-mono md:col-span-2"
              placeholder="Label (optional)"
              value={authLabel}
              onChange={(e) => setAuthLabel(e.target.value)}
            />
            <Button
              size="sm"
              disabled={authBusy}
              onClick={async () => {
                const c = Number(cfMHz);
                const b = Number(bwKHz);
                if (!Number.isFinite(c) || !Number.isFinite(b)) return;
                setAuthBusy(true);
                try {
                  await cmsAddAuthorizedFrequency(antennaId, c * 1e6, b * 1e3, authLabel.trim());
                  setCfMHz('');
                  setAuthLabel('');
                  await refreshAuthorized();
                } finally {
                  setAuthBusy(false);
                }
              }}
            >
              Add CF
            </Button>
          </div>
          <div className="max-h-48 overflow-auto border border-border/30 rounded-md">
            <table className="w-full text-xs font-mono">
              <thead className="bg-secondary/30 text-muted-foreground">
                <tr>
                  <th className="text-left px-2 py-2">#</th>
                  <th className="text-left px-2 py-2">Label</th>
                  <th className="text-left px-2 py-2">Center</th>
                  <th className="text-left px-2 py-2">BW</th>
                  <th className="text-left px-2 py-2">Range</th>
                  <th className="text-left px-2 py-2">Action</th>
                </tr>
              </thead>
              <tbody>
                {authorizedList.length === 0 ? (
                  <tr>
                    <td className="px-2 py-3 text-muted-foreground" colSpan={6}>
                      No authorized frequencies configured for this antenna.
                    </td>
                  </tr>
                ) : (
                  authorizedList.map((f, i) => {
                    const lo = f.center / 1e6 - f.bandwidth / 2e6;
                    const hi = f.center / 1e6 + f.bandwidth / 2e6;
                    return (
                      <tr key={`${f.center}-${i}`} className="border-t border-border/20">
                        <td className="px-2 py-2">{i + 1}</td>
                        <td className="px-2 py-2">{f.label || '—'}</td>
                        <td className="px-2 py-2">{(f.center / 1e6).toFixed(3)} MHz</td>
                        <td className="px-2 py-2">{(f.bandwidth / 1e3).toFixed(1)} kHz</td>
                        <td className="px-2 py-2">{lo.toFixed(3)}-{hi.toFixed(3)} MHz</td>
                        <td className="px-2 py-2">
                          <Button
                            size="sm"
                            variant="destructive"
                            className="h-7 text-[10px]"
                            onClick={async () => {
                              setAuthBusy(true);
                              try {
                                await cmsDeleteAuthorizedFrequency(antennaId, i);
                                await refreshAuthorized();
                              } finally {
                                setAuthBusy(false);
                              }
                            }}
                          >
                            Delete
                          </Button>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
};
