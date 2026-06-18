# CMS-SATCOM — Carrier Monitoring System
## Complete User Manual & Production Blueprint

**Version:** 1.0 | **Organisation:** ISRO | **System:** SDR-based Satellite Carrier Monitoring

---

## TABLE OF CONTENTS

1. [Hardware Requirements](#1-hardware-requirements)
2. [Software Requirements](#2-software-requirements)
3. [Project Architecture Overview](#3-project-architecture-overview)
4. [File Reference — Backend](#4-file-reference--backend)
5. [File Reference — Frontend](#5-file-reference--frontend)
6. [Raspberry Pi Setup](#6-raspberry-pi-setup)
7. [Software Installation on Pi](#7-software-installation-on-pi)
8. [Connecting to Wi-Fi and Cloning the Repository](#8-connecting-to-wi-fi-and-cloning-the-repository)
9. [SSD Setup and Mounting](#9-ssd-setup-and-mounting)
10. [Running the System](#10-running-the-system)
11. [Remote Dashboard Setup](#11-remote-dashboard-setup)
12. [Multi-Antenna Production Deployment](#12-multi-antenna-production-deployment)
13. [Troubleshooting](#13-troubleshooting)

---

## 1. HARDWARE REQUIREMENTS

### Per Antenna Station (Edge Node)

| Component | Specification | Notes |
|---|---|---|
| **Raspberry Pi** | Pi 5 (recommended) or Pi 4 (4GB/8GB) | Pi 5 preferred for continuous 24/7 operation |
| **Software Defined Radio** | HackRF One or RTL-SDR v3 | HackRF recommended for wider frequency range |
| **External SSD** | 256 GB, shock-resistant | Samsung T7 Shield or WD My Passport recommended |
| **MicroSD Card** | 64 GB, Class 10 / A2 rated | Samsung Endurance Pro or SanDisk Endurance |
| **SATA-to-USB Cable** | USB 3.0, if SSD is SATA type | Use quality adapter (Ugreen/Inateck) |
| **Power Supply** | Official Pi 5 PSU (5V/5A USB-C) | Do NOT use phone chargers |
| **Cooling Fan** | Active cooling case or official Pi fan | Mandatory for 24/7 continuous operation |
| **Monitor** | Any HDMI monitor or TV | For initial setup only |
| **Keyboard + Mouse** | USB or Bluetooth | For initial setup only |
| **Micro HDMI to HDMI cable** | Male Micro-HDMI → Female HDMI | Pi uses Micro-HDMI, not standard HDMI |

### Remote Dashboard Machine (Central Laptop/PC)

| Component | Specification |
|---|---|
| **OS** | Windows 10/11, macOS, or Ubuntu |
| **RAM** | 8 GB minimum |
| **Network** | Same LAN as the Pi(s), or VPN |
| **Browser** | Chrome or Edge (latest) |

---

## 2. SOFTWARE REQUIREMENTS

### Raspberry Pi (Edge Node)

| Software | Version | Purpose | Install Command |
|---|---|---|---|
| **Raspberry Pi OS** | Bookworm 64-bit (latest) | Operating system | Via Pi Imager |
| **Python** | 3.11+ | Backend runtime | Pre-installed on Pi OS |
| **GNU Radio** | 3.10.x | SDR signal processing flowgraph | `sudo apt install gnuradio` |
| **Flask** | 3.0+ | REST API server | `pip install flask>=3.0` |
| **NumPy** | 1.26+ | FFT and signal math | `pip install numpy>=1.26` |
| **SciPy** | 1.11+ | Signal processing (windows, peaks) | `pip install scipy>=1.11` |
| **Matplotlib** | 3.8+ | Spectrum plot (headless mode) | `pip install matplotlib>=3.8` |
| **PyZMQ** | 25.0+ | ZMQ transport between GNU Radio and detector | `pip install pyzmq>=25.0` |
| **openpyxl** | 3.1+ | Excel log file writing | `pip install openpyxl>=3.1` |
| **Git** | Latest | Clone repository | `sudo apt install git` |
| **Node.js** | 20 LTS | Frontend dev server (dashboard machine only) | Via nvm |
| **Bun** | Latest | Fast JS package manager (optional) | Via install script |

### Dashboard Machine (Remote Laptop/PC)

| Software | Version | Purpose |
|---|---|---|
| **Node.js** | 20 LTS | Run the Vite dev server |
| **npm** | 10+ | Package manager |
| **Git** | Latest | Clone repository |
| **VS Code** | Latest | Code editor (optional but recommended) |
| **Chrome/Edge** | Latest | View the dashboard |

---

## 3. PROJECT ARCHITECTURE OVERVIEW

```
┌─────────────────────────────────────────────────────────────────┐
│                    RASPBERRY PI (Edge Node)                      │
│                                                                  │
│  SDR Hardware (HackRF/RTL-SDR)                                  │
│       │ IQ samples (USB)                                         │
│       ▼                                                          │
│  sdr_scipy.py  (GNU Radio flowgraph)                            │
│       │ ZMQ PUB tcp://127.0.0.1:5555  (IQ stream)              │
│       │ ZMQ PUB tcp://127.0.0.1:5557  (carrier hints)          │
│       ▼                                                          │
│  Interference.py  (headless detector)                           │
│       │ FFT → PSD → carrier detection → interference detection  │
│       │ Writes logs → /mnt/ssd/interference_logs/               │
│       │ REST API  tcp://0.0.0.0:8766                            │
│       ▼                                                          │
│  orchestrator.py  (control plane)                               │
│       │ Starts/stops sdr_scipy.py and Interference.py           │
│       │ Proxies all API calls                                    │
│       │ REST API  tcp://0.0.0.0:8780  ◄── Frontend connects here│
│       ▼                                                          │
│  config_manager.py  (frequency authorization)                   │
│       │ Stores authorized IF frequencies per antenna            │
│       │ REST API  tcp://0.0.0.0:5580                            │
│       ▼                                                          │
│  External SSD  /mnt/ssd/interference_logs/                      │
│       GSAT-30/GSAT-30_2026-05-22.xlsx  (full day log)          │
└─────────────────────────────────────────────────────────────────┘
                              │
                    LAN / Wi-Fi Network
                              │
┌─────────────────────────────────────────────────────────────────┐
│              DASHBOARD MACHINE (Laptop/PC)                       │
│                                                                  │
│  npm run dev  →  Vite dev server  :8080                         │
│       │                                                          │
│  Browser  →  http://localhost:8080  (local)                     │
│           →  http://<laptop-ip>:8080  (other clients on LAN)   │
│                                                                  │
│  API calls proxied:  /api  →  Pi IP:8780/api                   │
└─────────────────────────────────────────────────────────────────┘
```

**Data flow summary:**
1. SDR hardware captures RF → GNU Radio converts to IQ samples → ZMQ stream
2. `Interference.py` receives IQ, computes FFT/PSD, detects carriers and interference
3. Results stored in memory + written to SSD Excel files
4. `orchestrator.py` exposes a single REST API that the frontend calls
5. Frontend polls every 150ms, renders spectrum, logs, and metrics in the browser

---

## 4. FILE REFERENCE — BACKEND

All backend files are in the `backend/` folder.

---

### `sdr_scipy.py` — GNU Radio Flowgraph
**Runs on:** Raspberry Pi
**Responsibility:** The main GNU Radio signal acquisition script. Connects to the SDR hardware (HackRF/RTL-SDR via SoapySDR), captures IQ samples at 20 MHz sample rate centered at 70 MHz, and publishes the raw complex IQ stream over ZMQ PUB socket on port 5555. Also runs a Qt waterfall and frequency sink for local visual monitoring. An XML-RPC server on port 8080 allows remote tuning of center frequency and sample rate.

**Key parameters inside the file:**
- `samp_rate = 20e6` — 20 MHz sample rate
- `freq = 70e6` — center frequency (70 MHz)
- `fft_size = 2048` — FFT size
- `set_gain(0, 20.6)` — SDR hardware gain

---

### `sdr_scipy.grc` — GNU Radio Companion File
**Runs on:** Raspberry Pi
**Responsibility:** The graphical flowgraph source file for GNU Radio Companion (GRC). This is the design file that generates `sdr_scipy.py`. Open this in GNU Radio Companion to visually edit the flowgraph. Do not edit `sdr_scipy.py` directly if you plan to use GRC.

---

### `sdr_scipy_epy_block_0.py` — Control Receiver Block
**Runs on:** Raspberry Pi (embedded in GNU Radio)
**Responsibility:** A custom GNU Radio embedded Python block that receives JSON control messages over ZMQ. Allows the orchestrator to remotely change center frequency, sample rate, and FFT size while the flowgraph is running.

---

### `sdr_scipy_epy_block_1.py` / `sdr_scipy_epy_block_1_0.py` — Carrier Detector Block
**Runs on:** Raspberry Pi (embedded in GNU Radio)
**Responsibility:** A custom GNU Radio block that receives the PSD (power spectral density) from the FFT sink, detects carrier clusters above a noise threshold, and publishes carrier metadata (frequency, bandwidth, power) over ZMQ PUB on port 5557. This provides a fast carrier hint to `Interference.py`.

---

### `Interference.py` — Main Detector (CRITICAL FILE)
**Runs on:** Raspberry Pi
**Responsibility:** The core signal processing and detection engine. This is the most important file in the project. It:
- Subscribes to the ZMQ IQ stream from GNU Radio (port 5555)
- Computes FFT → PSD with Hann window, normalized to dBFS
- Applies EMA temporal smoothing (α=0.85 by default)
- Detects carriers using morphological open/close + adaptive threshold
- Detects interference inside carriers (bump, variance, curvature, gap, level-shift detectors)
- Detects valley splits between sub-carriers
- Checks each carrier against the authorized frequency list
- Writes detection logs to the SSD Excel file (one file per antenna per day)
- Exposes a REST API on port 8766 with endpoints: `/api/snapshot`, `/api/health`, `/api/set_smoothing`, `/api/logs_full`, `/api/export_logs`
- In headless mode (`SCIPY_HEADLESS=1`): runs without any GUI window, suitable for 24/7 service

**Key tunable parameters at the top of the file:**
- `MORPH_CLOSE_BINS = 9` — gap bridging in carrier mask
- `VALLEY_DEPTH_DB = 6.0` — minimum dip to split a carrier
- `INTF_MERGE_GAP_HZ = 50e3` — max gap to merge two interference hits
- `smooth_alpha = 0.85` — EMA smoothing strength
- `LOG_THROTTLE_SEC = 0.5` — log entry interval (2 logs/second)
- `_WARMUP_FRAMES = 60` — frames to skip before detection starts (EMA convergence)
- `LOG_SSD_PATH` — read from `.env`, path to SSD log folder

---

### `orchestrator.py` — Control Plane API
**Runs on:** Raspberry Pi
**Responsibility:** The single entry point that the frontend talks to. It:
- Starts and stops `sdr_scipy.py` and `Interference.py` as subprocesses
- Proxies all API calls from the frontend to the correct backend service
- Loads `.env` file automatically for environment variables
- Exposes REST API on port 8780 (accessible from the network)

**Endpoints it exposes:**
- `POST /api/monitor/start` — start SDR + detector
- `POST /api/monitor/stop` — stop SDR + detector
- `GET /api/snapshot` — proxy to detector snapshot
- `GET /api/health` — system health check
- `POST /api/set_smoothing` — adjust EMA smoothing
- `GET /api/frequencies` — get authorized frequencies
- `POST /api/frequencies` — add authorized frequency
- `DELETE /api/frequencies/<idx>` — remove authorized frequency
- `GET /api/logs_full` — full in-memory log buffer
- `GET /api/export_logs` — download Excel log file

---

### `config_manager.py` — Authorized Frequency Manager
**Runs on:** Raspberry Pi
**Responsibility:** Manages the per-antenna authorized IF frequency list. Stores data in `authorized_freqs.json`. Exposes a web UI on port 5580 and a REST API. The `is_authorized()` method checks if a detected carrier's center frequency is within ±1 MHz of any authorized entry — bandwidth is not used for this check.

---

### `authorized_freqs.json` — Frequency Authorization Database
**Runs on:** Raspberry Pi (file on disk)
**Responsibility:** JSON file storing the authorized IF frequencies per antenna. Automatically reloaded when changed on disk. Format:
```json
{
  "gsat-30": [
    { "center": 70000000.0, "bandwidth": 2000000.0, "label": "MOX-SHAR" }
  ]
}
```

---

### `detection_confidence.py` — Confidence Engine
**Runs on:** Raspberry Pi
**Responsibility:** Tracks detection confidence scores over time for each interference hit. Uses a rolling vote buffer to reduce false positives — a detection must appear consistently across multiple frames before being logged. Prevents single-frame noise spikes from generating log entries.

---

### `.env` — Environment Configuration
**Runs on:** Raspberry Pi
**Responsibility:** Environment variable configuration file. Key variables:
```
LOG_SSD_PATH=/mnt/ssd/interference_logs
SCIPY_SNAPSHOT_PORT=8766
SCIPY_ORCHESTRATOR_PORT=8780
SCIPY_HEADLESS=1
```

---

### `requirements-cms.txt` — Python Dependencies
**Responsibility:** Lists all Python packages needed. Install with:
```bash
pip install -r requirements-cms.txt
```

---

## 5. FILE REFERENCE — FRONTEND

All frontend files are in the `Frontend1/` folder. The frontend is a React + TypeScript + Vite application.

---

### Entry Points

**`index.html`** — HTML entry point. Sets the browser tab title to "CMS-SATCOM" and the ISRO logo as favicon.

**`src/main.tsx`** — React application bootstrap. Mounts the root React component into the DOM.

**`src/App.tsx`** — Root component. Sets up React Router with two routes: `/` (main app) and `*` (404 page). Wraps everything in the Toaster notification provider.

**`src/App.css` / `src/index.css`** — Global styles. Dark theme, glass-card effects, custom scrollbar, animation utilities.

**`vite.config.ts`** — Vite build configuration. Sets dev server port to 8080, configures the `/api` proxy to forward to `http://127.0.0.1:8780` (the orchestrator).

---

### Pages

**`src/pages/Index.tsx`** — Main page. Checks authentication state. If not logged in, shows `LoginPage`. If logged in and monitoring a satellite, shows `SignalMonitor`. Otherwise shows the fleet dashboard (`SatelliteGrid` + `DashboardHeader`).

**`src/pages/NotFound.tsx`** — 404 error page.

---

### Auth Components (`src/components/auth/`)

**`LoginPage.tsx`** — Login screen with ISRO logo, email/password fields, and "Secure Login" button. Validates credentials against the app store. Also contains the signup link.

**`SignupModal.tsx`** — Multi-step registration modal. Collects name, email, mobile, organisation ID. Stores user profile in the app store.

---

### Dashboard Components (`src/components/dashboard/`)

**`DashboardHeader.tsx`** — Top navigation bar on the fleet view. Shows ISRO logo, system title "CMS-SATCOM", user info, and logout button.

**`SatelliteGrid.tsx`** — The fleet view grid. Displays all configured antenna/satellite cards. Handles health checks by pinging each Pi's `/api/health` endpoint. Shows online/offline status.

**`SatelliteCard.tsx`** — Individual antenna card in the fleet grid. Shows name, band, status indicator, signal health, C/N ratio, Eb/No, and a "Monitor" button to enter live monitoring.

**`DetailPanel.tsx`** — Side panel showing full details of a selected satellite (coordinates, ground station, hardware specs, in-charge name, etc.).

**`AddSatelliteModal.tsx`** — Modal form to add a new antenna/satellite entry. Fields include name, band, Pi IP address, ground station, coordinates, etc.

**`EditSatelliteModal.tsx`** — Same as Add but pre-filled for editing an existing entry.

**`SettingsPanel.tsx`** — Settings panel (theme, preferences).

---

### Monitoring Components (`src/components/monitoring/`)

**`SignalMonitor.tsx`** — THE MAIN MONITORING SCREEN. This is the most complex component. It:
- Connects to the Pi's API using the satellite's IP address
- Polls `/api/snapshot` every 150ms for live PSD + detection data
- Calls `/api/logs_full` once on mount to restore full log history
- Manages smoothing state (enabled=true, α=0.85 by default)
- Renders the spectrum analyzer, detection log, metrics grid, and controls
- Contains the Authorized Frequency Manager with manual entry AND Excel import
- Handles Excel import: reads Tx Station, Rx Station, central freq columns → adds as authorized frequencies with label "TX-RX"
- Contains the Export XLSX button for downloading detection logs

**`SpectrumAnalyzer.tsx`** — Canvas-based real-time FFT spectrum renderer. Draws:
- Grid lines, frequency axis (MHz), power axis (dBFS, -140 to +10)
- Live PSD as cyan line with gradient fill
- Green spans for authorized carriers, red spans for unauthorized
- Red interference overlays with individual labels per hit
- Orange edge lines on all carriers
- Noise floor (purple dashed) and detection threshold (yellow dashed) lines
- Mouse crosshair with frequency/power readout

**`SpectrumControls.tsx`** — Right-side control panel. Toggles for Interference, Max Hold, Min Hold, Smooth. Smooth α slider (0–1). Reset Hold button. Config display (FFT size, sample rate, etc.).

**`DetectionLog.tsx`** — Scrollable real-time detection log panel. Shows timestamped carrier and interference events. Buttons: Auto-scroll ON/OFF, Export XLSX (downloads today's log), Clear.

**`MetricsGrid.tsx`** — Top metrics bar showing Signal Health %, C/N ratio (dB), Eb/No (dB), and Interference status (CLEAR / DETECTED).

**`SpectrumChart.tsx`** — Recharts time-series line chart showing power and C/N ratio over time.

**`RadarView.tsx`** — Radar/polar plot showing satellite position (elevation/azimuth).

---

### Library Files (`src/lib/`)

**`cmsApi.ts`** — All API communication with the backend. Functions:
- `setApiTarget(ip)` — switch which Pi to talk to
- `cmsStartMonitor()` / `cmsStopMonitor()` — start/stop detector
- `cmsFetchSnapshot()` — get latest PSD + detection data
- `cmsSetSmoothing(enabled, alpha)` — update smoothing parameters
- `cmsGetFullLogs()` — fetch full in-memory log history
- `cmsExportLogs(antenna, date)` — download Excel log file
- `snapshotToDetectionResult()` — convert snapshot JSON to canvas data types

**`dspEngine.ts`** — Frontend signal processing for simulation mode. Contains `DSP_CONFIG` (FFT size, sample rate, Y-axis range -140 to +10 dB), carrier detection, interference detection, and PSD generation for demo/simulation when no Pi is connected.

**`exportData.ts`** — Exports signal metrics data to Excel using the `xlsx` library. Used by the "Export XLSX" button in the header.

**`healthCheck.ts`** — Utility to ping a Pi's `/api/health` endpoint and return online/offline status. Used by `SatelliteGrid` to show live status indicators.

**`utils.ts`** — Tailwind CSS class merging utility (`cn()`).

---

### Store (`src/store/`)

**`appStore.ts`** — Global application state using Zustand with localStorage persistence. Stores: authentication state, satellite list, selected/monitoring satellite, modal visibility. Satellite list is saved to `localStorage` so it persists across browser refreshes.

---

### Types (`src/types/`)

**`satellite.ts`** — TypeScript interfaces: `Satellite` (all antenna fields including Pi IP), `SignalData` (metrics snapshot), `AuthState`, `UserProfile`.

---

### Data (`src/data/`)

**`satellites.ts`** — Default satellite list loaded on first run. Contains GSAT-30, INSAT-4B, RISAT-2BR1, Chandrayaan-3, Aditya-L1 as initial entries. Edit this file to change the default fleet.

---

### Hooks (`src/hooks/`)

**`useAutoStartBackend.ts`** — Automatically calls `cmsStartMonitor` for the first online satellite when the dashboard loads.

**`useSatelliteMetrics.ts`** — Polling hook for satellite metrics.

**`use-mobile.tsx`** — Detects mobile screen size for responsive layout.

**`use-toast.ts`** — Toast notification hook.

---

### UI Components (`src/components/ui/`)
Pre-built Radix UI + Tailwind components (button, card, slider, switch, dialog, table, etc.). These are standard shadcn/ui components — do not modify unless you need to change the design system.

---

## 6. RASPBERRY PI SETUP

### Step 1 — Download Raspberry Pi Imager

Go to the official Raspberry Pi website:
```
https://www.raspberrypi.com/software/
```
Download the Raspberry Pi Imager for your OS (Windows/macOS/Linux). Install it normally.

---

### Step 2 — Flash the MicroSD Card

1. Insert your 64 GB MicroSD card into your laptop/PC using a card reader.
2. Open **Raspberry Pi Imager**.
3. Click **"Choose Device"** → Select **Raspberry Pi 5** (or Pi 4 if using Pi 4).
4. Click **"Choose OS"** → Select:
   - **Raspberry Pi OS (64-bit)** → **Raspberry Pi OS Bookworm (64-bit)**
   - Do NOT choose Lite — you need the full desktop for GNU Radio
5. Click **"Choose Storage"** → Select your MicroSD card.
6. Click the **gear icon (⚙)** or **"Edit Settings"** before flashing:

**In the settings panel, configure:**
```
Hostname:     cms-pi-01          (or cms-pi-02 for second unit, etc.)
Username:     pi
Password:     [choose a strong password]
Wi-Fi SSID:   [your network name]
Wi-Fi Password: [your Wi-Fi password]
Country:      IN
Timezone:     Asia/Kolkata
Enable SSH:   YES (Use password authentication)
```

7. Click **Save** → Click **Yes** to apply settings → Click **Yes** to confirm flashing.
8. Wait for flashing and verification to complete (~5–10 minutes).
9. Remove the MicroSD card safely.

---

### Step 3 — First Boot

1. Insert the MicroSD card into the Raspberry Pi.
2. Connect the Micro-HDMI cable from Pi to your monitor/TV.
3. Connect keyboard and mouse via USB.
4. Connect the power supply last — Pi boots automatically.
5. Wait for the desktop to appear (~60–90 seconds on first boot).
6. The Pi will automatically connect to your Wi-Fi using the credentials you set.

---

### Step 4 — Find the Pi's IP Address

On the Pi terminal (or via SSH):
```bash
hostname -I
```
Note the IP address (e.g., `192.168.1.45`). You will need this for the dashboard.

Alternatively, check your router's admin panel for connected devices named `cms-pi-01`.

---

### Step 5 — Enable Raspberry Pi Connect (Optional — Remote Access)

Raspberry Pi Connect allows browser-based remote desktop access without needing to be on the same network.

```bash
sudo apt update
sudo apt install rpi-connect
rpi-connect on
```

Then visit `https://connect.raspberrypi.com` and sign in with your Raspberry Pi account to access the Pi remotely from anywhere.

---

## 7. SOFTWARE INSTALLATION ON PI

Open a terminal on the Pi (or SSH into it from your laptop):
```bash
ssh pi@192.168.1.45
```

### Step 1 — Update the System
```bash
sudo apt update && sudo apt upgrade -y
```

### Step 2 — Install GNU Radio
```bash
sudo apt install gnuradio -y
```
Verify:
```bash
gnuradio-companion --version
```

### Step 3 — Install SoapySDR and HackRF Support
```bash
sudo apt install soapysdr-tools libsoapysdr-dev soapysdr-module-all -y
sudo apt install hackrf -y
```
Test SDR detection (plug in HackRF first):
```bash
SoapySDRUtil --find
```
You should see your HackRF listed.

### Step 4 — Install Python Dependencies
```bash
pip install flask>=3.0 numpy>=1.26 scipy>=1.11 matplotlib>=3.8 pyzmq>=25.0 openpyxl>=3.1
```
Or using the requirements file after cloning:
```bash
pip install -r ~/cms/backend/requirements-cms.txt
```

### Step 5 — Install VS Code (Optional but Recommended)
```bash
sudo apt install code -y
```
Or download the ARM64 `.deb` from `https://code.visualstudio.com/download` and install:
```bash
sudo dpkg -i code_*.deb
```

### Step 6 — Install Node.js (Only needed on Dashboard machine, not Pi)
On the **dashboard laptop/PC** (not the Pi):
```bash
# Using nvm (recommended)
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
source ~/.bashrc
nvm install 20
nvm use 20
node --version   # should show v20.x.x
```

On Windows, download the Node.js 20 LTS installer from `https://nodejs.org`.

---

## 8. CONNECTING TO WI-FI AND CLONING THE REPOSITORY

### Connect Pi to Wi-Fi (if not already connected via Imager settings)
```bash
sudo nmtui
```
Select "Activate a connection" → choose your Wi-Fi → enter password.

Or via command line:
```bash
sudo nmcli dev wifi connect "YOUR_WIFI_NAME" password "YOUR_WIFI_PASSWORD"
```

Verify connection:
```bash
ping google.com -c 4
```

### Install Git
```bash
sudo apt install git -y
```

### Clone the Repository

On the **Raspberry Pi**:
```bash
cd ~
git clone https://github.com/satcomproject25/CARRIER-MONITORING-SYSTEM-USING-PI-AND-SDR cms
cd cms
```

On the **Dashboard laptop/PC**:
```bash
git clone https://github.com/satcomproject25/CARRIER-MONITORING-SYSTEM-USING-PI-AND-SDR cms
cd cms
```

### Configure the .env File on Pi
```bash
cd ~/cms/backend
cp .env.example .env
nano .env
```

Edit the file to set your SSD path:
```
LOG_SSD_PATH=/mnt/ssd/interference_logs
SCIPY_SNAPSHOT_PORT=8766
SCIPY_ORCHESTRATOR_PORT=8780
SCIPY_CONFIG_PORT=5580
```
Save with `Ctrl+O`, exit with `Ctrl+X`.

---

## 9. SSD SETUP AND MOUNTING

### Step 1 — Connect the SSD
Plug the SSD into the **USB 3.0 port** (blue port) on the Pi.

### Step 2 — Find the SSD Device
```bash
lsblk
```
Look for a disk like `/dev/sda` with your SSD's size. If it shows `0B`, see the troubleshooting section.

### Step 3 — Format the SSD (First Time Only)
```bash
# Create a partition
sudo fdisk /dev/sda
# Press: n → p → 1 → Enter → Enter → w

# Format as ext4
sudo mkfs.ext4 /dev/sda1
```

### Step 4 — Mount the SSD
```bash
sudo mkdir -p /mnt/ssd
sudo mount /dev/sda1 /mnt/ssd
sudo chown -R pi:pi /mnt/ssd
```

### Step 5 — Auto-Mount on Boot
```bash
# Get UUID
sudo blkid /dev/sda1
# Copy the UUID value (e.g., a1b2c3d4-e5f6-...)

# Edit fstab
sudo nano /etc/fstab
```
Add this line at the bottom (replace UUID with yours):
```
UUID=a1b2c3d4-e5f6-xxxx  /mnt/ssd  ext4  defaults,nofail  0  2
```
Test:
```bash
sudo mount -a
df -h /mnt/ssd
```
You should see the SSD listed with available space.

### Step 6 — Fix Power Issues (if SSD shows 0B)
```bash
sudo nano /boot/firmware/config.txt
```
Add at the bottom:
```
usb_max_current_enable=1
```
Save and reboot:
```bash
sudo reboot
```

---

## 10. RUNNING THE SYSTEM

### What Runs Where

| Process | Machine | Command | Port |
|---|---|---|---|
| `orchestrator.py` | Raspberry Pi | `python orchestrator.py` | 8780 |
| `sdr_scipy.py` | Started by orchestrator | automatic | 5555, 5557 |
| `Interference.py` | Started by orchestrator | automatic | 8766 |
| `config_manager.py` | Started by Interference.py | automatic | 5580 |
| `npm run dev` | Dashboard laptop/PC | `npm run dev` | 8080 |

---

### On the Raspberry Pi — Start the Backend

Open a terminal on the Pi:
```bash
cd ~/cms/backend
python orchestrator.py
```

You will see:
```
[orchestrator] http://127.0.0.1:8780
  POST /api/monitor/start   — headless SDR + Interference.py
  POST /api/monitor/stop
  GET  /api/snapshot        — proxy to detector
```

**Keep this terminal open.** The orchestrator must keep running.

The frontend will automatically call `/api/monitor/start` when you click "Monitor" on any satellite card, which starts `sdr_scipy.py` and `Interference.py` as subprocesses.

---

### On the Dashboard Laptop/PC — Start the Frontend

Open a terminal:
```bash
cd ~/cms/Frontend1
npm install        # first time only
npm run dev
```

You will see:
```
  VITE v5.x.x  ready in xxx ms
  ➜  Local:   http://localhost:8080/
  ➜  Network: http://192.168.1.50:8080/
```

Open Chrome/Edge and go to `http://localhost:8080`.

---

### First-Time Login

Default credentials (change after first login):
```
Email:    admin@isro.gov.in
Password: admin123
```

---

### Adding Your Pi to the Dashboard

1. Log in to the dashboard.
2. On the Fleet view, click **"Add Satellite"**.
3. Fill in:
   - **Name:** GSAT-30 (or your antenna name)
   - **Pi IP Address:** `192.168.1.45` (your Pi's IP)
   - **Band:** C-Band
   - Other fields as appropriate
4. Click **Save**.
5. The card will appear in the fleet. Click **Monitor** to start live monitoring.

---

### Adding Authorized Frequencies

**Method 1 — Manual:**
In the monitor view, scroll to "Authorized Frequency Manager":
- Enter Center MHz (e.g., `70`)
- Enter Label (e.g., `MOX-SHAR`)
- Click **Add CF**

**Method 2 — Excel Import:**
Prepare an Excel file with columns:
```
Tx Station | Rx Station | central freq | data rate
MOX        | SHAR       | 70 mhz       | 11kbps
```
Click **Choose Excel File** and select your file. All rows are imported automatically.

---

## 11. REMOTE DASHBOARD SETUP

### Accessing from Other Laptops on the Same Network

Once `npm run dev` is running on the dashboard machine, any laptop on the same Wi-Fi can access the dashboard:

```
http://192.168.1.50:8080
```
(Replace `192.168.1.50` with the dashboard machine's IP address.)

Find the dashboard machine's IP:
- **Windows:** `ipconfig` in Command Prompt → look for IPv4 Address
- **Linux/Mac:** `hostname -I`

### Multiple Users Simultaneously

Multiple users can open the dashboard URL at the same time. Each browser session is independent. All users see the same live data from the Pi.

### Production Deployment (No Dev Server)

For a permanent installation without running `npm run dev`, build the frontend:
```bash
cd ~/cms/Frontend1
npm run build
```
This creates a `dist/` folder. Serve it with any static file server:
```bash
# Using Python (simple)
cd dist
python3 -m http.server 8080

# Using nginx (production)
sudo apt install nginx
sudo cp -r dist/* /var/www/html/
```

For nginx, also configure a reverse proxy so `/api` calls reach the Pi orchestrator.

---

## 12. MULTI-ANTENNA PRODUCTION DEPLOYMENT

This section describes how to deploy the system for multiple antennas, each with its own Raspberry Pi, SDR, and SSD.

### Architecture for 2 Antennas (Example: GSAT-30 + GSAT-20)

```
Pi 1 (IP: 192.168.1.45)          Pi 2 (IP: 192.168.1.46)
  SDR → sdr_scipy.py               SDR → sdr_scipy.py
  Interference.py (GSAT-30)        Interference.py (GSAT-20)
  orchestrator.py :8780            orchestrator.py :8780
  SSD → /mnt/ssd/GSAT-30/         SSD → /mnt/ssd/GSAT-20/

         │                                  │
         └──────────── LAN ─────────────────┘
                          │
              Dashboard Laptop :8080
              (one frontend serves both)
```

### Steps to Add a Second Pi

**On Pi 2 — same setup as Pi 1:**
```bash
cd ~/cms/backend
cp .env.example .env
nano .env
# Set LOG_SSD_PATH=/mnt/ssd/interference_logs
python orchestrator.py
```

**On the Dashboard — add the second antenna:**
1. Click **Add Satellite**
2. Name: `GSAT-20`
3. Pi IP Address: `192.168.1.46`
4. Click Save

Now clicking **Monitor** on GSAT-30 connects to Pi 1, and clicking **Monitor** on GSAT-20 connects to Pi 2. Each Pi runs independently — switching antennas in the dashboard does NOT stop the other Pi's logging.

### Key Rule — Logging is Always Independent

Each Pi logs continuously to its own SSD regardless of whether anyone is viewing the dashboard. The frontend is purely a viewer — it never controls when logging starts or stops. Logging begins the moment `orchestrator.py` starts the detector and continues until the Pi is shut down.

### Downloading Logs Per Antenna

When you are on the GSAT-30 monitor screen → click **Export XLSX** → downloads GSAT-30 logs from Pi 1.
When you are on the GSAT-20 monitor screen → click **Export XLSX** → downloads GSAT-20 logs from Pi 2.

Each download is completely independent.

### Running as a System Service (Auto-start on Boot)

To make the orchestrator start automatically when the Pi boots:

```bash
sudo nano /etc/systemd/system/cms-orchestrator.service
```

Paste:
```ini
[Unit]
Description=CMS-SATCOM Orchestrator
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/cms/backend
ExecStart=/usr/bin/python3 /home/pi/cms/backend/orchestrator.py
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable cms-orchestrator
sudo systemctl start cms-orchestrator
sudo systemctl status cms-orchestrator
```

Check logs:
```bash
journalctl -u cms-orchestrator -f
```

Now the orchestrator starts automatically on every boot, even after a power cut.

---

## 13. TROUBLESHOOTING

### SSD Shows 0B Size
**Cause:** Pi USB port cannot supply enough power to the SSD.
**Fix:**
```bash
sudo nano /boot/firmware/config.txt
# Add at bottom:
usb_max_current_enable=1
sudo reboot
```
If still 0B, use a powered USB hub between the Pi and SSD.

---

### "Export failed: HTTP Error 500" on Dashboard
**Cause:** `openpyxl` not installed in the Python environment running `Interference.py`.
**Fix:**
```bash
pip install openpyxl==3.1.5
# Then restart orchestrator
```

---

### "File wasn't available on site" on Export
**Cause:** Old process running before code update.
**Fix:** Restart the orchestrator:
```bash
# Press Ctrl+C in the orchestrator terminal, then:
python orchestrator.py
```

---

### Dashboard Shows "SCANNING..." and Never Loads
**Cause:** The detector is in the EMA warmup period (first 60 frames, ~1.2 seconds). This is normal.
**Fix:** Wait 2–3 seconds after clicking Monitor. The spectrum will appear automatically.

---

### Carrier Showing as UNAUTH When It Should Be AUTH
**Cause:** The authorized frequency list does not have an entry within ±1 MHz of the carrier's center.
**Fix:** Add the carrier's IF frequency to the Authorized Frequency Manager, or import your frequency plan Excel file.

---

### Two Carriers Detected Instead of One Continuous Carrier
**Cause:** The carrier has a shallow dip in the middle triggering valley detection.
**Fix:** Already tuned — `VALLEY_DEPTH_DB = 6.0` requires a 6 dB dip to split. If still happening, increase further in `Interference.py`:
```python
VALLEY_DEPTH_DB = 8.0
```

---

### GNU Radio Not Finding SDR Hardware
**Cause:** HackRF not detected by SoapySDR.
**Fix:**
```bash
# Check USB connection
lsusb | grep HackRF
# Should show: "Great Scott Gadgets HackRF One"

# Test SoapySDR
SoapySDRUtil --find
# Should show driver=hackrf

# If not found, reinstall:
sudo apt install hackrf soapysdr-module-all -y
sudo hackrf_info
```

---

### Pi Overheating (Throttling)
**Symptom:** System slows down, detection becomes irregular.
**Fix:**
```bash
# Check temperature
vcgencmd measure_temp
# If above 80°C, add cooling

# Check throttling
vcgencmd get_throttled
# 0x0 = no throttling (good)
```
Install the official Pi active cooler or a heatsink+fan case.

---

### Cannot Access Dashboard from Other Laptops
**Cause:** Firewall blocking port 8080 on the dashboard machine.
**Fix (Windows):**
```
Windows Defender Firewall → Advanced Settings →
Inbound Rules → New Rule → Port → TCP 8080 → Allow
```
**Fix (Linux):**
```bash
sudo ufw allow 8080
```

---

### Logs Not Being Written to SSD
**Cause:** `LOG_SSD_PATH` not set, or SSD not mounted.
**Fix:**
```bash
# Check SSD is mounted
df -h /mnt/ssd

# Check .env file
cat ~/cms/backend/.env
# Should contain: LOG_SSD_PATH=/mnt/ssd/interference_logs

# Check log folder exists
ls /mnt/ssd/interference_logs/
```

---

### Frontend Shows Wrong Frequency Range
**Cause:** The `DSP_CONFIG` in `dspEngine.ts` has hardcoded center frequency.
**Fix:** The spectrum analyzer now reads the actual frequency axis from the backend snapshot automatically. If it still looks wrong, check that `Interference.py` is running and the snapshot contains valid `freq_mhz` data.

---

---

## QUICK REFERENCE — STARTUP CHECKLIST

### Every Time You Start the System

**On Raspberry Pi:**
```bash
# 1. Verify SSD is mounted
df -h /mnt/ssd

# 2. Connect SDR via USB

# 3. Start the backend
cd ~/cms/backend
python orchestrator.py
```

**On Dashboard Laptop:**
```bash
# 4. Start the frontend
cd ~/cms/Frontend1
npm run dev

# 5. Open browser
# http://localhost:8080
```

**In the Browser:**
```
6. Log in
7. Click "Monitor" on your antenna card
8. Wait 2-3 seconds for spectrum to appear
9. Verify: "Detector streaming • <Pi IP>" shown in green
```

---

## QUICK REFERENCE — PORT SUMMARY

| Port | Service | Accessible From |
|---|---|---|
| `8780` | Orchestrator REST API | Dashboard machine (LAN) |
| `8766` | Interference.py snapshot API | Localhost on Pi only |
| `5580` | Config Manager (freq auth) | Localhost on Pi only |
| `5555` | ZMQ IQ stream (GNU Radio → Detector) | Localhost on Pi only |
| `5557` | ZMQ carrier hints | Localhost on Pi only |
| `8080` | Frontend Vite dev server | All machines on LAN |

---

## QUICK REFERENCE — KEY TUNING PARAMETERS

All in `backend/Interference.py`:

| Parameter | Default | Effect |
|---|---|---|
| `smooth_alpha` | `0.85` | EMA smoothing strength (0=raw, 1=max smooth) |
| `LOG_THROTTLE_SEC` | `0.5` | Seconds between log entries (0.5 = 2/sec) |
| `VALLEY_DEPTH_DB` | `6.0` | Min dip depth to split a carrier into two |
| `MORPH_CLOSE_BINS` | `9` | Max gap (bins) to bridge inside a carrier |
| `ADAPTIVE_MERGE_BW_FACTOR` | `0.8` | How aggressively to merge adjacent spans |
| `INTF_MERGE_GAP_HZ` | `50e3` | Max gap to merge two interference hits |
| `INTF_BUMP_THRESHOLD_DB` | `3` | Min bump height to flag as interference |
| `_WARMUP_FRAMES` | `60` | Frames to skip at startup (EMA convergence) |
| `Y_MIN` / `Y_MAX` | `-140` / `10` | PSD display range (dBFS) |

---

## REPOSITORY

```
https://github.com/satcomproject25/CARRIER-MONITORING-SYSTEM-USING-PI-AND-SDR
```

---

*CMS-SATCOM User Manual — ISRO Carrier Monitoring System*
*Document generated: 2026*
