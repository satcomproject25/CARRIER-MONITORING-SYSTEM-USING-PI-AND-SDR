# SCIPY-CMS — Full System Architecture
> Last updated: auto-generated from codebase audit
> Covers: backend signal chain, frontend rendering pipeline, all API connections,
>         FFT flow, smoothing, detection, and inter-process communication.

---

## TABLE OF CONTENTS

1. Project Overview
2. Complete Folder Structure
3. Backend File Responsibilities
4. Frontend File Responsibilities
5. Inter-Process Communication (ZMQ + HTTP)
6. Full Signal Pipeline — Step by Step
7. Frontend Signal Pipeline — FFT to Plot
8. API Endpoint Reference
9. Data Flow Diagram (ASCII)
10. Configuration Parameters Cross-Reference

---

## 1. PROJECT OVERVIEW

This system is a real-time satellite RF interference detection and monitoring platform.

Hardware:  HackRF SDR dongle  →  GNU Radio  →  Python detector  →  React web UI
Protocol:  ZMQ (IQ samples)  →  HTTP REST polling (400 ms)  →  Canvas rendering

Two operating modes:
  LIVE (GSAT-30 only)   — real IQ from HackRF, detection in Python, frontend renders results
  SIMULATION (others)   — synthetic PSD generated in browser, detection runs in browser JS
---

## 2. COMPLETE FOLDER STRUCTURE

```
SCIPY-CMS/                          ← project root
│
├── ARCHITECTURE.md                 ← THIS FILE
├── .gitignore
│
├── backend/                        ← Python signal processing + API servers
│   ├── Interference.py             ← CORE: FFT, detection, snapshot API (port 8766)
│   ├── orchestrator.py             ← HTTP control plane for frontend (port 8780)
│   ├── config_manager.py           ← Authorized frequency store + web UI (port 5580)
│   ├── sdr_scipy.py                ← GNU Radio flowgraph: HackRF → ZMQ publisher
│   ├── sdr_scipy.grc               ← GNU Radio Companion source for sdr_scipy.py
│   ├── sdr_scipy_epy_block_0.py    ← GRC embedded block: XML-RPC control receiver
│   ├── sdr_scipy_epy_block_1.py    ← GRC embedded block: metadata publisher (ZMQ 5556)
│   ├── sdr_scipy_epy_block_1_0.py  ← GRC embedded block: carrier publisher (ZMQ 5557)
│   ├── frequency_server.py         ← Legacy standalone freq config server (port 5000)
│   ├── detection_confidence.py     ← ConfidenceEngine: per-detection scoring helper
│   ├── cuc_detector.py             ← Carrier-under-carrier curvature detector helper
│   ├── authorized_freqs.json       ← Persisted per-antenna authorized frequency lists
│   ├── requirements-cms.txt        ← Python dependencies
│   │
│   ├── (INTF_CUC_CURV_SIGMA        ← Tuning constant export file (read by detector)
│   ├── (INTF_VARIANCE_SIGMA        ← Tuning constant export file
│   ├── INTF_BUMP_THRESHOLD_DB      ← Tuning constant export file
│   ├── detect_threshold            ← Runtime state export (last computed threshold)
│   ├── l_limit                     ← Runtime state export
│   ├── PSD                         ← Runtime state export (last PSD snapshot binary)
│   ├── 0                           ← Runtime state export
│   │
│   ├── texts/                      ← Documentation / design notes (not runtime)
│   │   ├── Code explain.docx
│   │   ├── Input.docx
│   │   ├── interference detection.pdf
│   │   ├── lag issue corrected.docx
│   │   ├── Libraries+ code.docx
│   │   ├── plot_simple.txt.txt
│   │   └── Transition.docx
│   │
│   └── duplicate gui_plots/        ← Archived earlier GUI versions (not runtime)
│       ├── gui_plotscipy.py
│       ├── gui_plot_working.py.txt
│       ├── inter.py
│       └── interference.py
│
└── Frontend1/                      ← React + Vite web application
    ├── index.html                  ← HTML entry point
    ├── package.json                ← npm dependencies and scripts
    ├── vite.config.ts              ← Vite config: dev proxy /api → localhost:8780
    ├── tailwind.config.ts          ← Tailwind CSS config
    ├── components.json             ← shadcn/ui component registry
    ├── eslint.config.js
    ├── postcss.config.js
    ├── playwright.config.ts        ← E2E test config
    ├── playwright-fixture.ts
    │
    └── src/
        ├── main.tsx                ← React DOM entry point
        ├── App.tsx                 ← Router: / → Index, * → NotFound
        ├── App.css / index.css     ← Global styles + Tailwind base
        ├── vite-env.d.ts
        │
        ├── pages/
        │   ├── Index.tsx           ← Root page: auth gate → dashboard or monitor
        │   └── NotFound.tsx        ← 404 page
        │
        ├── store/
        │   └── appStore.ts         ← Zustand global state: auth, satellites, monitor target
        │
        ├── types/
        │   └── satellite.ts        ← TypeScript interfaces: Satellite, SignalData, AuthState
        │
        ├── data/
        │   └── satellites.ts       ← Static satellite list (GSAT-30 is the live asset)
        │
        ├── lib/
        │   ├── cmsApi.ts           ← HTTP client: all fetch() calls to backend REST API
        │   ├── dspEngine.ts        ← JS DSP: simulation PSD gen + detection pipeline
        │   ├── exportData.ts       ← XLSX export of signal log data
        │   └── utils.ts            ← Tailwind class merge utility (cn)
        │
        ├── hooks/
        │   ├── use-mobile.tsx      ← Responsive breakpoint hook
        │   └── use-toast.ts        ← Toast notification hook
        │
        ├── components/
        │   ├── NavLink.tsx         ← Styled navigation link
        │   │
        │   ├── auth/
        │   │   ├── LoginPage.tsx   ← Login form (email + password)
        │   │   └── SignupModal.tsx ← Multi-step signup modal
        │   │
        │   ├── dashboard/
        │   │   ├── DashboardHeader.tsx   ← Top bar: logo, user menu, logout
        │   │   ├── SatelliteGrid.tsx     ← Grid of SatelliteCard components
        │   │   ├── SatelliteCard.tsx     ← Per-satellite card: status, metrics, Monitor button
        │   │   ├── AddSatelliteModal.tsx ← Form to add a new satellite entry
        │   │   └── DetailPanel.tsx       ← Slide-in panel: full satellite details
        │   │
        │   ├── monitoring/
        │   │   ├── SignalMonitor.tsx     ← MAIN ORCHESTRATOR: state, polling, data flow
        │   │   ├── SpectrumAnalyzer.tsx  ← Canvas renderer: FFT plot + overlays
        │   │   ├── SpectrumControls.tsx  ← Control panel: toggles + smoothing slider
        │   │   ├── SpectrumChart.tsx     ← Recharts time-series: power + C/N over time
        │   │   ├── DetectionLog.tsx      ← Scrollable detection event log
        │   │   ├── MetricsGrid.tsx       ← KPI cards: noise, C/N, Eb/No, health
        │   │   └── RadarView.tsx         ← Satellite position radar display
        │   │
        │   └── ui/                      ← shadcn/ui primitives (button, slider, switch, etc.)
        │       └── [50+ component files]
        │
        └── test/
            ├── example.test.ts     ← Vitest example test
            └── setup.ts            ← Vitest setup
```
---

## 3. BACKEND FILE RESPONSIBILITIES

### backend/sdr_scipy.py
GNU Radio flowgraph. The hardware entry point.
- Opens HackRF via SoapySDR driver (driver=hackrf)
- Tunes to CENTER_FREQ = 70 MHz, sample rate = 20 MHz, gain = 20.6 dB
- Streams raw complex IQ samples (fc32 / complex64) continuously
- Publishes IQ stream via ZMQ PUB socket on tcp://127.0.0.1:5555
- Also feeds GNU Radio internal waterfall + frequency sink (desktop display)
- Exposes XML-RPC server on port 8080 for runtime parameter changes (freq, rate, fft)
- Connections inside flowgraph:
    soapy_source_0 → zeromq_pub_sink_0   (IQ to ZMQ port 5555)
    soapy_source_0 → qtgui_freq_sink     (internal spectrum display)
    soapy_source_0 → qtgui_waterfall_sink (internal waterfall display)

### backend/sdr_scipy_epy_block_0.py
GNU Radio embedded Python block — Control Receiver.
- Listens on a GRC message port for JSON control commands
- Handles: set center freq, set sample rate, set FFT size
- Calls tb.set_center_freq(), tb.set_sample_rate(), tb.set_fft_size()

### backend/sdr_scipy_epy_block_1.py
GNU Radio embedded Python block — Metadata Publisher.
- Publishes SDR metadata (sample rate, FFT size, center freq) as JSON
- Sends on ZMQ port 5556 so Interference.py can sync its parameters

### backend/sdr_scipy_epy_block_1_0.py
GNU Radio embedded Python block — Carrier Publisher.
- Publishes detected carrier info (freq, bw, power) as JSON
- Sends on ZMQ port 5557 so Interference.py can receive carrier hints

### backend/Interference.py  ← THE CORE PROCESSING ENGINE
Receives IQ from ZMQ, runs the full detection pipeline, exposes results via HTTP.

Responsibilities:
  1. ZMQ subscriber on tcp://127.0.0.1:5555 — receives raw IQ frames
  2. ZMQ subscriber on tcp://127.0.0.1:5556 — receives metadata updates
  3. ZMQ subscriber on tcp://127.0.0.1:5557 — receives carrier hints
  4. DataFetcher thread — polls all three ZMQ sockets, stores latest frames
  5. update() function — called every 33ms (headless) or by Qt timer (desktop):
       a. FFT computation
       b. Smoothing (optional exponential averaging)
       c. Carrier detection (morphological + hysteresis + adaptive threshold)
       d. Interference detection (bump + variance + curvature + edge + gap)
       e. Valley/split detection
       f. Unauthorized carrier detection
       g. Temporal stability tracking (debounce + confidence scoring)
       h. Snapshot JSON assembly
  6. Flask HTTP server on port 8766 — exposes:
       GET /api/health    → {"status":"ok","headless":true}
       GET /api/snapshot  → full detection result JSON
  7. In desktop mode: matplotlib GUI with sliders, checkboxes, markers

### backend/orchestrator.py
Single HTTP control plane that the frontend talks to. Acts as a process manager and proxy.
- Starts/stops sdr_scipy.py and Interference.py as subprocesses
- Sets environment variables: SCIPY_HEADLESS=1, SCIPY_ACTIVE_ANTENNA, SCIPY_SNAPSHOT_PORT
- Proxies GET /api/snapshot → Interference.py:8766/api/snapshot
- Proxies /api/frequencies/* → config_manager.py:5580/api/frequencies/*
- Runs Flask on port 8780
- All frontend HTTP calls go to port 8780 (via Vite dev proxy)

### backend/config_manager.py
Authorized frequency store with per-antenna isolation.
- Loads/saves authorized_freqs.json (dict keyed by antenna_id)
- AuthorizedFrequencyManager class: add(), remove(), is_authorized(), get_all()
- Starts embedded Flask web server on port 5580:
    GET  /api/frequencies?antenna_id=X  → list frequencies for antenna
    POST /api/frequencies               → add frequency {center, bandwidth, label}
    DELETE /api/frequencies/<idx>       → remove by index
    GET  /                              → HTML management UI
- is_authorized(freq_hz) checks if freq falls within any [center ± bandwidth/2] range
- Used by Interference.py to classify carriers as authorized or unauthorized

### backend/detection_confidence.py
ConfidenceEngine helper class.
- Augments interference detections with a confidence score (0.0–1.0)
- Called once per carrier per frame: augment(psd_raw, display_psd, carrier_span, ...)
- Scores based on: SNR above noise, spectral consistency, temporal persistence
- Results attached to each interference hit before snapshot assembly

### backend/cuc_detector.py
Carrier-Under-Carrier (CUC) curvature detector helper.
- Detects a second carrier hidden underneath a dominant carrier
- Uses second-derivative (curvature) of the smoothed PSD segment
- Called from within detect_interference_in_carrier() in Interference.py

### backend/authorized_freqs.json
Persistent storage for authorized frequency lists.
Format: { "gsat-30": [ {"center": 70000000, "bandwidth": 500000, "label": "..."}, ... ] }
One key per antenna_id. Written by config_manager.py on every add/remove.

### backend/frequency_server.py
Legacy standalone frequency config server (port 5000). Not used in the current
orchestrator-based deployment. Kept for backward compatibility with older frontends.
Endpoints: GET /api/config, POST /api/add, POST /api/delete
---

## 4. FRONTEND FILE RESPONSIBILITIES

### Frontend1/src/main.tsx
React DOM entry point. Mounts <App /> into #root div in index.html.

### Frontend1/src/App.tsx
Sets up React Query client, React Router, and global UI providers (Toaster, Tooltip).
Routes: "/" → Index.tsx, "*" → NotFound.tsx

### Frontend1/src/pages/Index.tsx
Root page controller. Reads Zustand store and decides what to render:
  - Not authenticated → <LoginPage />
  - monitoringSatellite is set → <SignalMonitor />
  - Otherwise → Dashboard (DashboardHeader + SatelliteGrid + modals)

### Frontend1/src/store/appStore.ts
Zustand global state store. Single source of truth for:
  - auth: { isAuthenticated, user }
  - satellites: Satellite[]  (loaded from data/satellites.ts)
  - selectedSatellite: Satellite | null
  - monitoringSatellite: Satellite | null  ← set when user clicks "Monitor"
  - showAddModal, showDetailPanel: boolean
Actions: login, logout, addSatellite, selectSatellite, setMonitoringSatellite

### Frontend1/src/types/satellite.ts
TypeScript interfaces:
  Satellite     — full satellite record (id, name, band, status, coords, specs, metrics)
  SignalData    — time-series data point (time, frequency, power, noise, cnRatio, ebNo, signalHealth)
  AuthState     — { isAuthenticated, user }
  UserProfile   — { name, email, mobile, orgId, verified }

### Frontend1/src/data/satellites.ts
Static array of 5 satellite records. GSAT-30 (id=1) is the only live asset.
piIpAddress for GSAT-30 is "127.0.0.1 (local chain)" — signals local backend.
Other satellites have piIpAddress="—" meaning simulation mode only.

### Frontend1/src/lib/cmsApi.ts
All HTTP communication with the backend. No WebSocket — pure REST polling.
Functions:
  cmsStartMonitor(startSdr, antennaId)     POST /api/monitor/start
  cmsStopMonitor(stopSdr)                  POST /api/monitor/stop
  cmsHealth()                              GET  /api/health
  cmsFetchSnapshot()                       GET  /api/snapshot  ← called every 400ms
  cmsGetAuthorizedFrequencies(antennaId)   GET  /api/frequencies?antenna_id=X
  cmsAddAuthorizedFrequency(...)           POST /api/frequencies
  cmsDeleteAuthorizedFrequency(id, idx)    DELETE /api/frequencies/<idx>
  snapshotToDetectionResult(snap, max, min) ← converts CmsSnapshot → DetectionResult
    - Converts freq_mhz[] → Float64Array (Hz)
    - Converts psd_db[] → Float64Array
    - Maps carriers[] → CarrierDetection[]
    - Maps interference[] + gap_interference[] → InterferenceDetection[]
    - Attaches maxHold / minHold arrays
    - DOES NOT re-run any detection — pure data mapping

### Frontend1/src/lib/dspEngine.ts
JavaScript DSP engine. Used ONLY in simulation mode (non-GSAT-30 satellites).
In live mode this file is NOT called for detection — only its CONFIG constants are used.

Functions:
  generateSimulatedPSD()         Generates synthetic FFT spectrum with 6 carriers + noise
  estimateNoiseFloor(psd)        Rolling 15th-percentile noise floor (matches backend)
  smoothPSD(psd, taps)           Box-filter smoothing (moving average)
  detectCarriers(...)            Full carrier detection pipeline (matches backend logic)
  detectInterference(...)        Bump + variance interference detection
  updateMaxHold / updateMinHold  Element-wise max/min across frames
  runDetectionPipeline(...)      Orchestrates all of the above for one simulation frame

DSP_CONFIG constants — must match backend Interference.py exactly:
  FFT_SIZE: 2048, HW_SAMPLE_RATE: 20e6, CENTER_FREQ: 70e6
  NF_PERCENTILE: 15.0, CARRIER_K_SIGMA: 3.5
  MORPH_OPEN_BINS: 3, MORPH_CLOSE_BINS: 5
  INTF_BUMP_THRESHOLD_DB: 2, INTF_MIN_BUMP_BINS: 1.0
  INTF_ENVELOPE_ORDER: 9, GAP_MIN_BINS: 3
  CARRIER_HIGH_THRESH_OFFSET: 4.0

### Frontend1/src/lib/exportData.ts
Exports signal log data to XLSX using the xlsx library.
Called when user clicks "Export XLSX" button in SignalMonitor.
Writes: time, frequency, power, noise, C/N, Eb/No, signal health columns.

### Frontend1/src/lib/utils.ts
Single utility: cn(...classes) — merges Tailwind class names using clsx + tailwind-merge.

### Frontend1/src/components/monitoring/SignalMonitor.tsx
THE MAIN ORCHESTRATOR COMPONENT. Manages all state and data flow for the monitor view.

State managed:
  piConnected: boolean           — backend health status
  detectionResult: DetectionResult | null  — latest processed frame
  logs: LogEntry[]               — detection event log
  anomalyDetected: boolean       — true if any interference or unauth carrier
  enableIntf, enableMaxHold, enableMinHold: boolean  — display toggles
  smoothEnabled: boolean         — temporal smoothing toggle
  smoothAlpha: number (0–1)      — smoothing strength
  latestMetrics: SignalData      — for MetricsGrid and SpectrumChart
  authorizedList: AuthorizedFrequency[]  — for the freq manager table

Refs (persist across renders without triggering re-render):
  maxHoldRef: Float64Array | null   — running max-hold PSD
  minHoldRef: Float64Array | null   — running min-hold PSD
  psdAvgRef: Float64Array | null    — running EMA buffer for smoothing
  intervalRef: ReturnType<setInterval>  — polling interval handle
  frameCountRef: number             — frame counter for log throttling

Live mode behavior (isLiveBackend = sat.name === "GSAT-30"):
  - On mount: calls cmsStartMonitor() to start SDR + detector subprocesses
  - On unmount: calls cmsStopMonitor()
  - Polls every 400ms: cmsHealth() + cmsFetchSnapshot() in parallel
  - Applies temporal EMA smoothing to received PSD (if smoothEnabled)
  - Updates maxHold / minHold buffers
  - Calls snapshotToDetectionResult() to build DetectionResult
  - Sets detectionResult state → triggers SpectrumAnalyzer re-render

Simulation mode behavior:
  - Runs processFrameSimulated() every 100ms via setInterval
  - Calls runDetectionPipeline() from dspEngine.ts
  - Full detection runs in browser JS

### Frontend1/src/components/monitoring/SpectrumAnalyzer.tsx
Canvas-based FFT spectrum renderer. Receives DetectionResult, draws everything.
No detection logic — pure visualization.

What it draws (in order):
  1. Background fill (dark navy)
  2. Horizontal grid lines every 10 dB (Y_MIN=-70 to Y_MAX=80)
  3. Vertical grid lines every 2 MHz
  4. Axis labels (Frequency MHz, Power dB)
  5. Title text
  6. Carrier highlight spans (green=authorized, red=unauthorized)
     - Orange vertical edge lines at carrier boundaries
     - Label badge showing bandwidth in kHz
  7. Interference highlight spans (red, semi-transparent)
     - Label badge showing "INTF X.XdB"
  8. Noise floor line (purple dashed)
  9. Detection threshold line (yellow dashed)
  10. Max Hold line (green, 0.8px) — if enableMaxHold
  11. Min Hold line (red, 0.5px) — if enableMinHold
  12. Live PSD gradient fill (cyan, semi-transparent)
  13. Live PSD stroke line (cyan, 1.2px)
  14. Mouse crosshair + frequency/power readout tooltip

Uses ResizeObserver to adapt canvas to container size.
Coordinate mapping:
  freqToX(freq_hz) = margin.left + ((freq_mhz - fMin) / (fMax - fMin)) * plotW
  powerToY(power_db) = margin.top + ((Y_MAX - power) / (Y_MAX - Y_MIN)) * plotH

### Frontend1/src/components/monitoring/SpectrumControls.tsx
Control panel sidebar. Passes all state up via props (no local state).
Controls:
  - Interference toggle (Switch)
  - Max Hold toggle (Switch)
  - Min Hold toggle (Switch)
  - Smooth toggle (Switch)
  - Smooth alpha slider (0–100 mapped to 0.0–1.0) — visible only when Smooth is ON
  - Reset Hold button
  - Config display: FFT size, sample rate, center freq, carrier k·σ

### Frontend1/src/components/monitoring/SpectrumChart.tsx
Recharts-based time-series chart. Shows power and noise floor over time.
Secondary chart shows C/N ratio and Eb/No.
Receives SignalData[] array from SignalMonitor.

### Frontend1/src/components/monitoring/DetectionLog.tsx
Scrollable log panel. Receives LogEntry[] array.
Each entry has: time, message, color (hex), type (carrier/interference/gap/info).
In live mode: log entries come directly from backend (snap.logs[]).
In simulation mode: log entries are generated by SignalMonitor from detection results.
Auto-scrolls to bottom. Has a Clear button.

### Frontend1/src/components/monitoring/MetricsGrid.tsx
Four KPI cards: Noise Floor, C/N Ratio, Eb/No, Signal Health.
Receives SignalData and anomaly flag. Shows warning colors when anomaly=true.

### Frontend1/src/components/monitoring/RadarView.tsx
Circular radar display showing satellite azimuth/elevation position.
Purely visual — reads from the Satellite object, no backend connection.

### Frontend1/src/components/dashboard/SatelliteCard.tsx
Per-satellite card in the fleet grid.
"Monitor" button calls setMonitoringSatellite(sat) in Zustand store.
This triggers Index.tsx to render <SignalMonitor /> instead of the dashboard.

---

## 5. INTER-PROCESS COMMUNICATION (ZMQ + HTTP)

### ZMQ Sockets (backend-internal only, never touched by frontend)

  Publisher:  sdr_scipy.py
  Subscriber: Interference.py

  Port 5555  ZMQ PUB/SUB  — Raw IQ samples (complex64 binary stream)
             sdr_scipy.py publishes every GNU Radio buffer (~2048 samples)
             Interference.py subscribes with CONFLATE=1 (always gets latest frame)

  Port 5556  ZMQ PUB/SUB  — SDR metadata (JSON)
             sdr_scipy_epy_block_1.py publishes: {rate, fft, cf}
             Interference.py subscribes to sync FFT_SIZE, HW_SAMPLE_RATE, HW_CENTER_FREQ

  Port 5557  ZMQ PUB/SUB  — Carrier hints (JSON)
             sdr_scipy_epy_block_1_0.py publishes: [{id, freq, bw, power}, ...]
             Interference.py subscribes for optional carrier cross-reference

  Port 8080  XML-RPC server inside sdr_scipy.py
             Allows runtime changes: set_freq(), set_samp_rate(), set_fft_size()
             Not used by frontend directly

### HTTP REST (frontend ↔ backend)

  All frontend HTTP calls go to the Vite dev proxy at /api/*
  Vite proxies them to http://127.0.0.1:8780 (orchestrator.py)

  Frontend → Orchestrator (port 8780):
    POST /api/monitor/start    Start SDR + Interference.py subprocesses
    POST /api/monitor/stop     Stop both subprocesses
    GET  /api/health           Check if detector is running + has PSD data
    GET  /api/snapshot         Get latest FFT + detection results (polled 400ms)
    GET  /api/frequencies      List authorized frequencies for an antenna
    POST /api/frequencies      Add an authorized frequency
    DELETE /api/frequencies/N  Remove authorized frequency by index

  Orchestrator → Interference.py (port 8766):
    GET /api/snapshot          Proxy — orchestrator forwards to detector
    GET /api/health            Proxy — orchestrator forwards to detector

  Orchestrator → Config Manager (port 5580):
    GET  /api/frequencies      Proxy — orchestrator forwards to config_manager
    POST /api/frequencies      Proxy
    DELETE /api/frequencies/N  Proxy

  Config Manager web UI (port 5580):
    GET /                      HTML management page (standalone, not used by React frontend)

### No WebSocket
  There is NO WebSocket in this system.
  The frontend polls GET /api/snapshot every 400ms using setInterval + fetch().
  This is a deliberate design choice: simple, stateless, no reconnect logic needed.
---

## 6. FULL SIGNAL PIPELINE — STEP BY STEP (LIVE MODE)

This is the exact sequence every ~33ms when GSAT-30 is being monitored.

### STAGE 1 — Hardware Capture (sdr_scipy.py)
  HackRF antenna receives RF at 70 MHz center, 20 MHz bandwidth
  SoapySDR driver converts to complex baseband IQ samples (float32 I + float32 Q)
  GNU Radio streams 2048 complex samples per buffer
  zeromq_pub_sink publishes raw bytes to tcp://127.0.0.1:5555

### STAGE 2 — IQ Reception (Interference.py — DataFetcher thread)
  ZMQ SUB socket receives binary frame from port 5555
  np.frombuffer(data, dtype=np.complex64) → iq array of 2048 complex samples
  Stored in _latest_iq (protected by _state_lock)
  ZMQ CONFLATE=1 ensures only the newest frame is kept (no queue buildup)

### STAGE 3 — FFT Computation (Interference.py — update() function)
  iq_buffer[:] = iq[:FFT_SIZE]                    copy 2048 samples
  windowed = iq_buffer * window                    apply Hann window (reduces spectral leakage)
  spectrum = np.fft.fftshift(np.fft.fft(windowed)) compute 2048-point FFT, shift DC to center
  psd = 20 * log10(|spectrum| + 1e-12)             convert to dB (power spectral density)
  Result: psd array of 2048 float values, range typically -70 to +80 dB
  Frequency axis: freq_axis = arange(-1024, 1024) * df + 70e6
                  df = 20e6 / 2048 = 9765.625 Hz per bin

### STAGE 4 — Smoothing (Interference.py — update() function)
  Two independent smoothing layers:

  Layer A — Exponential temporal averaging (user-controlled via Smooth slider):
    if smooth_enabled and smooth_alpha > 0:
        alpha = 1 - (1 - smooth_alpha)^2          quadratic scaling for perceptual linearity
        psd_avg = alpha * psd_avg + (1-alpha) * psd  EMA: blend old average with new frame
        display_psd = psd_avg
    else:
        display_psd = psd                          raw FFT output

  Layer B — Fast Attack / Slow Decay (optional, FAST_AD_ENABLED=False by default):
    rising bins use FAST_AD_ATTACK_ALPHA=0.7 (fast response to signal rise)
    falling bins use FAST_AD_DECAY_ALPHA=0.15 (slow decay, persistence effect)
    Applied on top of Layer A result

  display_psd is what gets sent to the frontend and drawn on the canvas.

### STAGE 5 — Detection Smoothing (Interference.py — separate from display)
  smooth_taps = max(3, round(SMOOTH_BW_HZ / df)) | 1   = 5 bins (odd)
  psd_s = convolve(display_psd, ones(5)/5, mode='same')  box-filter moving average
  psd_s is used ONLY for detection — never sent to frontend
  This separates the detection input from the display output

### STAGE 6 — Noise Floor Estimation (Interference.py)
  estimate_noise_floor_adaptive(psd_s):
    window_size = FFT_SIZE // 8 = 256 bins
    step = 64 bins
    For each sliding window: compute 15th percentile of that window
    Return median of all window floors
  Result: noise (single float, e.g. -45.2 dB)
  This is robust to wide carriers — a carrier cannot dominate all windows

### STAGE 7 — Detection Threshold (Interference.py)
  noise_sigma = std(psd_s[psd_s < noise + 10])   sigma of noise-only bins
  noise_sigma = max(noise_sigma, 0.3)             floor to prevent collapse
  detect_threshold = noise + max(2.5, 3.5 * noise_sigma)
  threshold (compat) = noise + 0.35 * (peak - noise)   kept for legacy reference

### STAGE 8 — Carrier Detection (Interference.py)
  Step 1: Binary mask
    above = psd_s > detect_threshold              True where signal exceeds threshold

  Step 2: Morphological opening (removes isolated noise spikes)
    Erode with 3-bin kernel: bin is True only if all 3 neighbors are True
    Dilate with 3-bin kernel: restore surviving regions
    Effect: single-bin spikes are removed, real carriers survive

  Step 3: Morphological closing (bridges tiny intra-carrier notches)
    Dilate with 5-bin kernel, then erode with 5-bin kernel
    Effect: gaps of <5 bins inside a carrier are filled

  Step 4: Hysteresis gate (removes flat-noise false carriers)
    high_threshold = detect_threshold + 4.0 dB
    Any connected region in 'above' that has NO bin above high_threshold → removed
    Effect: only regions with a genuine signal peak survive

  Step 5: Extract spans
    Find rising/falling edges of 'above' mask
    Filter: span must be >= MIN_CARRIER_BW_HZ / df = 5 bins wide

  Step 6: Adaptive merging
    If gap between two spans < 0.5 * min(bw1, bw2) → merge into one span

  Step 7: Isolated spike detection
    find_peaks on psd_s for peaks > noise + 10 dB, prominence > 7 dB
    Walk left/right from each peak to noise + 3.5 dB to find edges
    Add as additional spans if not already covered

  Step 8: Per-span quality gate
    Peak of span must exceed span's 10th-percentile floor by >= 2.5 dB
    Rejects flat elevated noise regions

### STAGE 9 — Valley / Carrier Split Detection (Interference.py)
  For each carrier span wider than 10 bins:
    Find peaks within the span using find_peaks()
    For each pair of adjacent peaks, find the valley between them
    If valley depth >= VALLEY_DEPTH_DB (3.0 dB) and width >= 10 kHz:
      Split the carrier at the valley boundary
      Record valley for brown overlay drawing
  Result: raw_spans may be split into sub-spans (each treated as independent carrier)

### STAGE 10 — Authorization Check (Interference.py)
  For each carrier span:
    span_center_hz = midpoint of span
    is_auth = config_mgr.is_authorized(span_center_hz)
    Checks if center falls within any [cf - bw/2, cf + bw/2] in authorized_freqs.json
  Unauthorized carriers flagged for red highlight + unauth persistence filter

### STAGE 11 — Interference Detection (Interference.py)
  For each carrier span, run detect_interference_in_carrier(display_psd[r:f], freq[r:f]):

  Method 1 — Spectral Bump:
    Compute rolling median envelope (window = INTF_ENVELOPE_ORDER = 9 bins)
    residual = psd_segment - envelope
    bump_threshold = max(2.0 dB, 1.5 * local_sigma)
    Regions where residual > bump_threshold → interference hit

  Method 2 — Local Variance Anomaly:
    Compute local variance in sliding window of 7 bins
    median_variance = median of all local variances
    Regions where local_var > 2.5 * median_variance → interference hit

  Method 3 — Carrier-Under-Carrier (Curvature):
    Smooth segment with 5-bin box filter
    Compute second derivative (d2/dx2)
    Regions where curvature > 3.5 * median_curvature → hidden carrier bump

  Method 4 — Edge Interference:
    Check left 20% and right 20% of carrier for elevated residual
    Detects partial-overlap interference at carrier edges

  Method 5 — Sub-band Variance:
    Divide carrier into 4 equal sub-bands
    Flag sub-bands with variance > 2.5 * median sub-band variance

  Method 6 — Intra-carrier Gap:
    Find peaks within carrier, look for valleys between them
    If valley depth > GAP_DEPTH_DB (2.5 dB) and width >= GAP_MIN_BINS (3) → gap hit

  All hits merged if within INTF_MERGE_GAP_HZ (200 kHz) of each other
  Gap hits kept separate from non-gap hits

### STAGE 12 — Temporal Stability Tracking (Interference.py)
  DetectionTracker class (one instance per category: intf, gap, valley, carrier):
    Each detection bucketed by frequency (50 kHz buckets)
    Must appear in >= STABILITY_DEBOUNCE_ON (3) consecutive frames to be confirmed
    Disappears after >= STABILITY_DEBOUNCE_OFF (5) consecutive absent frames
    Confidence score = 0.65 * persistence_ratio + 0.35 * strength_stability
    Only detections with confidence >= 0.6 are included in snapshot output
  Effect: eliminates single-frame false positives and flickering detections

### STAGE 13 — Snapshot Assembly (Interference.py)
  Assembled once per update() call, stored in _latest_snapshot (thread-safe):
  {
    "ts":                  unix timestamp
    "antenna_id":          "gsat-30"
    "hw_center_mhz":       70.0
    "display_center_mhz":  70.0
    "sample_rate_mhz":     20.0
    "fft_size":            2048
    "noise_db":            float  (estimated noise floor)
    "detect_threshold_db": float  (adaptive threshold)
    "threshold_compat_db": float  (legacy threshold)
    "freq_mhz":            [2048 floats]  (frequency axis in MHz)
    "psd_db":              [2048 floats]  (display_psd — post-smoothing)
    "carriers":            [{f_center_mhz, f_start_mhz, f_stop_mhz, bw_khz, is_auth, is_valley_sub}]
    "unauthorized":        [{f_center_mhz, f_start_mhz, f_stop_mhz, bw_khz, excess_db, trigger}]
    "interference":        [{center_mhz, strength_db, method, classification, confidence, track_id, parent_carrier_id}]
    "gap_interference":    [{center_mhz, strength_db, method, confidence, track_id, parent_carrier_id}]
    "stable_carriers":     [{center_mhz, strength_db, confidence, track_id}]
    "unauth_count":        int
    "logs":                [{msg, color}]  (last 400 log lines)
  }

### STAGE 14 — HTTP Delivery (orchestrator.py → frontend)
  Frontend calls GET /api/snapshot every 400ms
  orchestrator.py proxies to http://127.0.0.1:8766/api/snapshot
  Interference.py Flask server returns _latest_snapshot as JSON
  Response size: ~50–80 KB per frame (2048 floats + detection arrays)
---

## 7. FRONTEND SIGNAL PIPELINE — FFT RECEIVED TO PLOT DRAWN

This is what happens inside the browser every 400ms for GSAT-30 live mode.

### STEP 1 — Poll Trigger (SignalMonitor.tsx — useEffect interval)
  setInterval fires every 400ms
  Calls: Promise.all([cmsHealth(), cmsFetchSnapshot()])
  Both are fetch() calls to /api/* (proxied by Vite to port 8780)

### STEP 2 — Health Check (cmsApi.ts — cmsHealth)
  GET /api/health
  Response: { status, sdr_running, detector_running }
  If detector_running=false OR psd_db is empty → setPiConnected(false), return early
  If ok → setPiConnected(true)

### STEP 3 — Snapshot Fetch (cmsApi.ts — cmsFetchSnapshot)
  GET /api/snapshot
  Response: CmsSnapshot JSON (see Stage 13 above)
  Key fields used:
    snap.psd_db[]        — 2048 floats, the display PSD from backend
    snap.freq_mhz[]      — 2048 floats, frequency axis
    snap.noise_db        — noise floor scalar
    snap.detect_threshold_db — detection threshold scalar
    snap.carriers[]      — carrier detection results
    snap.interference[]  — interference detection results
    snap.gap_interference[] — gap detection results
    snap.logs[]          — log lines for DetectionLog

### STEP 4 — Frontend Smoothing (SignalMonitor.tsx — tick() function)
  NOTE: The backend already sends display_psd (post-smoothing).
  The frontend smoothing is an ADDITIONAL temporal layer across poll frames (400ms cadence).
  It does NOT re-smooth the per-FFT-frame smoothing — it averages across HTTP responses.

  let psd = Float64Array.from(snap.psd_db)   convert JSON array to typed array

  if (smoothEnabled && smoothAlpha > 0):
    if psdAvgRef is null or wrong length:
      psdAvgRef = psd.slice()                initialize buffer on first frame
    else:
      alpha = 1 - (1 - smoothAlpha)^2        same quadratic formula as backend
      for each bin i:
        smoothed[i] = alpha * psdAvgRef[i] + (1 - alpha) * psd[i]
      psdAvgRef = smoothed
    psd = psdAvgRef                          use smoothed version for display
  else:
    psdAvgRef = null                         reset buffer when smoothing disabled

  Result: psd is now the display-ready PSD array (smoothed or raw)

### STEP 5 — Max/Min Hold Update (SignalMonitor.tsx)
  if (enableMaxHold):
    for each bin: maxHoldRef[i] = max(maxHoldRef[i], psd[i])
  else:
    maxHoldRef = null

  if (enableMinHold):
    for each bin: minHoldRef[i] = min(minHoldRef[i], psd[i])
  else:
    minHoldRef = null

### STEP 6 — Detection Result Assembly (cmsApi.ts — snapshotToDetectionResult)
  NO detection is re-run here. This is pure data mapping.

  freqAxis = Float64Array.from(snap.freq_mhz, mhz => mhz * 1e6)
  psd = the (possibly smoothed) Float64Array from Step 4

  carriers = snap.carriers.map(c => {
    startFreq = c.f_start_mhz * 1e6
    endFreq   = c.f_stop_mhz  * 1e6
    centerFreq = c.f_center_mhz * 1e6
    bandwidth  = endFreq - startFreq
    startBin   = findIndex(freq_mhz >= c.f_start_mhz)
    endBin     = findIndex(freq_mhz >= c.f_stop_mhz)
    peakPower  = max(psd[startBin..endBin])
    totalPower = 10 * log10(sum(10^(psd[bins]/10)))
    cnRatio    = peakPower - snap.noise_db
    isAuthorized = c.is_auth
  })

  interferences = [
    ...snap.interference.map(x => {
      center = x.center_mhz * 1e6
      startFreq = center - 100kHz, endFreq = center + 100kHz
      strengthDb = x.strength_db, method = x.method, isGap = false
    }),
    ...snap.gap_interference.map(g => { ..., isGap = true })
  ]

  Returns: DetectionResult {
    psd, freqAxis, noiseFloor, detectThreshold,
    carriers, interferences, maxHold, minHold
  }

### STEP 7 — State Update (SignalMonitor.tsx)
  setDetectionResult(dr)     triggers SpectrumAnalyzer re-render
  setAnomalyDetected(...)    true if interference.length > 0 or unauth_count > 0
  setLatestMetrics({...})    updates MetricsGrid + SpectrumChart
  setLogs(snap.logs)         updates DetectionLog

### STEP 8 — Canvas Render (SpectrumAnalyzer.tsx — useEffect on data)
  Triggered by detectionResult state change.
  canvas.width = container width (from ResizeObserver)
  canvas.height = container height

  Coordinate system:
    plotW = canvas.width - 55 (left margin) - 20 (right margin)
    plotH = canvas.height - 30 (top) - 40 (bottom)
    freqToX(f) = 55 + ((f/1e6 - 60) / 20) * plotW   [60–80 MHz maps to full width]
    powerToY(p) = 30 + ((80 - p) / 150) * plotH      [80 dB top, -70 dB bottom]

  Draw sequence (each step uses ctx.beginPath / ctx.stroke / ctx.fill):
    1. ctx.fillRect(full canvas, dark navy)
    2. Grid lines: horizontal every 10 dB, vertical every 2 MHz
    3. Axis labels and title
    4. For each carrier in data.carriers:
         ctx.fillRect(x1..x2, green or red, alpha=0.2)
         ctx.moveTo/lineTo orange edge lines
         ctx.fillText bandwidth label badge
    5. For each interference in data.interferences:
         ctx.fillRect(x1..x2, red, alpha=0.35)
         ctx.fillText "INTF X.XdB" badge
    6. Noise floor: ctx.setLineDash([4,4]), purple dashed line at powerToY(noiseFloor)
    7. Threshold: ctx.setLineDash([2,3]), yellow dashed line at powerToY(detectThreshold)
    8. Max Hold: if enableMaxHold, iterate data.maxHold[], green line
    9. Min Hold: if enableMinHold, iterate data.minHold[], red line
    10. PSD fill: ctx.createLinearGradient (cyan top → transparent bottom)
          moveTo bottom-left, lineTo each (x, powerToY(psd[i])), lineTo bottom-right
          ctx.fill with gradient
    11. PSD stroke: iterate psd[], ctx.lineTo each point, ctx.stroke cyan 1.2px
    12. Mouse crosshair: if mousePos, draw dashed cross + readout box

### STEP 9 — Log Update (DetectionLog.tsx)
  Receives logs[] array from SignalMonitor state
  In live mode: logs come from snap.logs[] (backend-generated, color-coded)
  Renders each entry as colored text line
  Auto-scrolls to bottom on new entries

### STEP 10 — Metrics Update (MetricsGrid.tsx)
  Receives latestMetrics: SignalData from SignalMonitor
  Displays: noise floor, C/N ratio, Eb/No, signal health percentage
  Colors turn warning-red when anomalyDetected=true
---

## 8. API ENDPOINT REFERENCE

### Orchestrator — port 8780 (frontend entry point via Vite proxy)

  GET  /api/health
    Response: { status, sdr_running, detector_running, snapshot_port }
    Used by: SignalMonitor.tsx every 400ms to set piConnected state

  POST /api/monitor/start
    Body: { start_sdr: bool, sdr_settle_s: float, antenna_id: string }
    Response: { status, antenna_id, sdr_pid, detector_pid }
    Used by: SignalMonitor.tsx on mount (when isLiveBackend=true)
    Effect: spawns sdr_scipy.py (if start_sdr=true) then Interference.py

  POST /api/monitor/stop
    Body: { stop_sdr: bool }
    Response: { status: "stopped" }
    Used by: SignalMonitor.tsx on unmount
    Effect: terminates Interference.py (and sdr_scipy.py if stop_sdr=true)

  GET  /api/snapshot
    Response: CmsSnapshot JSON (see Stage 13 for full schema)
    Used by: SignalMonitor.tsx every 400ms
    Proxied to: http://127.0.0.1:8766/api/snapshot

  GET  /api/frequencies?antenna_id=gsat-30
    Response: { antenna_id, frequencies: [{center, bandwidth, label}] }
    Used by: SignalMonitor.tsx on mount + after add/delete
    Proxied to: http://127.0.0.1:5580/api/frequencies

  POST /api/frequencies
    Body: { antenna_id, center (Hz), bandwidth (Hz), label }
    Response: { status: "ok", antenna_id }
    Used by: SignalMonitor.tsx "Add CF" button
    Proxied to: http://127.0.0.1:5580/api/frequencies

  DELETE /api/frequencies/<idx>?antenna_id=gsat-30
    Response: { status: "ok", antenna_id }
    Used by: SignalMonitor.tsx "Delete" button in freq table
    Proxied to: http://127.0.0.1:5580/api/frequencies/<idx>

### Interference.py — port 8766 (internal, not directly accessed by frontend)

  GET /api/health
    Response: { status: "ok", headless: true, port: 8766 }

  GET /api/snapshot
    Response: full _latest_snapshot dict as JSON
    Thread-safe read via _snapshot_lock

### Config Manager — port 5580 (internal, proxied by orchestrator)

  GET  /api/frequencies?antenna_id=X   list frequencies
  POST /api/frequencies                add frequency
  DELETE /api/frequencies/<idx>        remove by index
  PUT  /api/frequencies/<idx>          update by index
  GET  /api/active-antenna             get current active antenna
  POST /api/active-antenna             set active antenna
  GET  /                               HTML management web UI

### Legacy Frequency Server — port 5000 (not used in current deployment)

  GET  /api/config    { centers_mhz, tolerance_mhz }
  POST /api/add       { freq_mhz }
  POST /api/delete    { freq_mhz }

---

## 9. DATA FLOW DIAGRAM (ASCII)

```
HARDWARE
  [HackRF SDR]
       |
       | RF signal (70 MHz center, 20 MHz BW)
       v
  [sdr_scipy.py — GNU Radio]
       |
       | complex64 IQ samples (2048 per buffer)
       | ZMQ PUB tcp://127.0.0.1:5555
       |
       | JSON metadata {rate, fft, cf}
       | ZMQ PUB tcp://127.0.0.1:5556
       |
       | JSON carrier hints [{id, freq, bw, power}]
       | ZMQ PUB tcp://127.0.0.1:5557
       |
       v
  [Interference.py — DataFetcher thread]
       |
       | _latest_iq, _latest_meta, _latest_carriers
       | (protected by _state_lock)
       v
  [Interference.py — update() — every 33ms]
       |
       |-- FFT (Hann window, 2048-point, fftshift)
       |-- psd = 20*log10(|spectrum|)
       |
       |-- Smoothing Layer A (EMA, user-controlled)
       |   psd_avg = alpha*psd_avg + (1-alpha)*psd
       |   display_psd = psd_avg (or raw psd)
       |
       |-- Smoothing Layer B (Fast A/D, optional)
       |   display_psd = fast_attack/slow_decay(display_psd)
       |
       |-- Detection smoothing (box filter, 5 bins)
       |   psd_s = convolve(display_psd, ones(5)/5)
       |
       |-- Noise floor (rolling 15th-percentile)
       |   noise = median(percentile(windows, 15))
       |
       |-- Adaptive threshold
       |   detect_threshold = noise + max(2.5, 3.5*sigma)
       |
       |-- Carrier detection (on psd_s)
       |   binary mask → morph open → morph close
       |   → hysteresis gate → span extraction
       |   → adaptive merge → spike detection
       |   → quality gate → valley split
       |
       |-- Authorization check (vs authorized_freqs.json)
       |
       |-- Interference detection (on display_psd segments)
       |   bump + variance + curvature + edge + subband + gap
       |
       |-- Temporal stability tracking (debounce + confidence)
       |
       |-- Snapshot assembly → _latest_snapshot
       |
       v
  [Interference.py — Flask HTTP :8766]
       |
       | GET /api/snapshot → JSON (~50-80 KB)
       v
  [orchestrator.py — Flask HTTP :8780]
       |
       | GET /api/snapshot (proxy)
       | GET /api/health
       | POST /api/monitor/start|stop
       | GET|POST|DELETE /api/frequencies (proxy to :5580)
       v
  [Vite Dev Proxy — /api/* → localhost:8780]
       v
  [Browser — SignalMonitor.tsx — every 400ms]
       |
       |-- fetch /api/health + /api/snapshot (parallel)
       |
       |-- Frontend smoothing (optional EMA across poll frames)
       |   psd = alpha*psdAvg + (1-alpha)*snap.psd_db
       |
       |-- Max/Min hold update
       |
       |-- snapshotToDetectionResult()
       |   (pure mapping, NO re-detection)
       |
       |-- setDetectionResult(dr)
       |
       v
  [SpectrumAnalyzer.tsx — Canvas 2D]
       |
       |-- Draw grid, labels, title
       |-- Draw carrier spans (green/red)
       |-- Draw interference spans (red)
       |-- Draw noise floor + threshold lines
       |-- Draw max/min hold lines
       |-- Draw PSD gradient fill + stroke
       |-- Draw mouse crosshair
       v
  [Browser screen — real-time FFT display]

PARALLEL FLOWS:
  [DetectionLog.tsx]   ← snap.logs[] (backend log lines, color-coded)
  [MetricsGrid.tsx]    ← latestMetrics (noise, C/N, Eb/No, health)
  [SpectrumChart.tsx]  ← SignalData[] time series
  [RadarView.tsx]      ← Satellite object (static, no backend)

CONFIG FLOW:
  [Browser — Freq Manager table]
       |
       | POST /api/frequencies (add)
       | DELETE /api/frequencies/N (remove)
       v
  [orchestrator.py] → proxy → [config_manager.py :5580]
       |
       | writes authorized_freqs.json
       v
  [Interference.py — config_mgr.is_authorized()]
       (reads on every carrier detection, no restart needed)
```

---

## 10. CONFIGURATION PARAMETERS CROSS-REFERENCE

All values must match between backend/Interference.py and Frontend1/src/lib/dspEngine.ts

  Parameter                  Backend value    Frontend DSP_CONFIG    Notes
  ─────────────────────────────────────────────────────────────────────────────
  FFT_SIZE                   2048             2048                   bins per frame
  HW_SAMPLE_RATE             20e6 Hz          20e6                   20 MHz bandwidth
  HW_CENTER_FREQ             70e6 Hz          CENTER_FREQ: 70e6      center frequency
  DISPLAY_BW                 20e6 Hz          DISPLAY_BW: 20e6       displayed range
  Y_MIN                      -70 dB           Y_MIN: -70             plot floor
  Y_MAX                      80 dB            Y_MAX: 80              plot ceiling
  NF_PERCENTILE              15.0             15.0                   noise floor percentile
  NF_ROLLING_WINDOW_DIV      8                8                      window = FFT/8 = 256
  CARRIER_K_SIGMA            3.5              3.5                    threshold = noise + k*sigma
  MORPH_OPEN_BINS            3                3                      spike removal kernel
  MORPH_CLOSE_BINS           5                5                      gap fill kernel
  ADAPTIVE_MERGE_BW_FACTOR   0.5              0.5                    carrier merge threshold
  MIN_CARRIER_BW_HZ          5*df = 48.8 kHz  5*(20e6/2048)          min carrier width
  SMOOTH_BW_HZ               5*df = 48.8 kHz  5*(20e6/2048)          detection smooth width
  CARRIER_HIGH_THRESH_OFFSET 4.0 dB           4.0                    hysteresis high gate
  INTF_BUMP_THRESHOLD_DB     2.0 dB           2                      min bump above envelope
  INTF_MIN_BUMP_BINS         1.0              1.0                    min bump width in bins
  INTF_ENVELOPE_ORDER        9                9                      median envelope half-width
  INTF_VARIANCE_WINDOW       7                7                      variance sliding window
  INTF_VARIANCE_SIGMA        2.5              2.5                    variance anomaly threshold
  INTF_CUC_CURV_SIGMA        3.5              3.5                    curvature anomaly threshold
  INTF_MERGE_GAP_HZ          200e3 Hz         200e3                  merge nearby intf hits
  GAP_DEPTH_DB               2.5 dB           2.5                    min gap depth
  GAP_MIN_BINS               3                3                      min gap width in bins
  VALLEY_DEPTH_DB            3.0 dB           3.0                    min valley depth
  VALLEY_MIN_WIDTH_HZ        10e3 Hz          10e3                   min valley width
  THRESHOLD_RATIO            0.35             0.35                   legacy compat threshold

  Smoothing alpha formula (both backend and frontend):
    alpha = 1 - (1 - smooth_alpha)^2
    slider 0.0 → alpha=0.0 (no smoothing, raw FFT)
    slider 0.5 → alpha=0.75 (moderate smoothing)
    slider 1.0 → alpha=1.0 (maximum persistence, frozen display)

  Polling interval:
    Live mode:       400ms (setInterval in SignalMonitor.tsx)
    Simulation mode: 100ms (setInterval in SignalMonitor.tsx)
    Backend update:  33ms  (time.sleep(0.033) in headless loop)

  Port assignments:
    5555  ZMQ IQ stream (sdr_scipy → Interference)
    5556  ZMQ metadata (sdr_scipy → Interference)
    5557  ZMQ carrier hints (sdr_scipy → Interference)
    5580  Config Manager HTTP (internal)
    5000  Legacy frequency server (unused)
    8080  XML-RPC SDR control (sdr_scipy)
    8766  Interference.py snapshot API (internal)
    8780  Orchestrator HTTP (frontend entry point)
    5173  Vite dev server (browser)