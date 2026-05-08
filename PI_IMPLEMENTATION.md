# RASPBERRY PI IMPLEMENTATION GUIDE
## Real-Time Satellite RF Interference Detection System

> **Project:** SCIPY-CMS — Satellite Communication Monitoring System  
> **Target Hardware:** Raspberry Pi 4/5 (4GB+ RAM recommended)  
> **Last Updated:** May 7, 2026

---

## TABLE OF CONTENTS

1. [System Architecture Overview](#1-system-architecture-overview)
2. [Hardware Requirements](#2-hardware-requirements)
3. [File Distribution Strategy](#3-file-distribution-strategy)
4. [Raspberry Pi Setup - Step by Step](#4-raspberry-pi-setup---step-by-step)
5. [Central Dashboard Setup](#5-central-dashboard-setup)
6. [Network Configuration & IP Management](#6-network-configuration--ip-management)
7. [Antenna Connection & Switching](#7-antenna-connection--switching)
8. [Starting the System](#8-starting-the-system)
9. [Troubleshooting](#9-troubleshooting)
10. [Maintenance & Monitoring](#10-maintenance--monitoring)

---

## 1. SYSTEM ARCHITECTURE OVERVIEW

### Deployment Model

```
┌─────────────────────────────────────────────────────────────┐
│                    CENTRAL DASHBOARD                         │
│  (Your Main Computer / Server)                              │
│  - React Frontend (Vite Dev Server or Production Build)     │
│  - Web Browser Access                                        │
│  - Connects to Remote Raspberry Pi via HTTP                 │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ HTTP/REST API
                              │ (Port 8780)
                              ▼
┌─────────────────────────────────────────────────────────────┐
│              RASPBERRY PI (Field Unit)                       │
│  Location: Near Antenna/SDR Hardware                        │
│                                                              │
│  ┌────────────────────────────────────────────────────┐    │
│  │  HackRF SDR → GNU Radio → Python Detector          │    │
│  │  (sdr_scipy.py → Interference.py → orchestrator.py)│    │
│  └────────────────────────────────────────────────────┘    │
│                                                              │
│  Storage:                                                    │
│  - MicroSD Card: Raspberry Pi OS + Software                 │
│  - SSD: Data collection, logs, PSD snapshots                │
└─────────────────────────────────────────────────────────────┘
```

### Communication Flow

1. **Frontend Dashboard** (Central) → HTTP requests → **Raspberry Pi** (Field)
2. **Raspberry Pi** processes RF signals from HackRF SDR
3. **Raspberry Pi** sends detection results back via HTTP REST API
4. **Frontend** polls every 400ms for real-time updates

---

## 2. HARDWARE REQUIREMENTS

### Raspberry Pi Unit (Per Antenna)

| Component | Specification | Purpose |
|-----------|--------------|---------|
| **Raspberry Pi** | Pi 4 (4GB+) or Pi 5 | Main processing unit |
| **MicroSD Card** | 32GB+ (Class 10/U3) | OS installation |
| **SSD** | 128GB+ USB 3.0 SSD | Data storage & processing |
| **HackRF SDR** | HackRF One | RF signal capture |
| **LAN Cable** | Cat5e/Cat6 | Network connection |
| **Power Supply** | Official Pi PSU (5V 3A) | Stable power |
| **Cooling** | Heatsink + Fan | Thermal management |
| **Case** | Protective enclosure | Physical protection |

### Central Dashboard System

| Component | Specification |
|-----------|--------------|
| **Computer** | Windows/Linux/Mac with 8GB+ RAM |
| **Network** | Same LAN as Raspberry Pi units |
| **Browser** | Chrome/Firefox/Edge (latest) |

---

## 3. FILE DISTRIBUTION STRATEGY

### 🔴 FILES FOR RASPBERRY PI (Field Unit)

**Deploy these to Raspberry Pi:**

```
backend/
├── sdr_scipy.py                    # GNU Radio flowgraph (HackRF interface)
├── sdr_scipy.grc                   # GNU Radio Companion source
├── sdr_scipy_epy_block_0.py        # GRC embedded block (control)
├── sdr_scipy_epy_block_1.py        # GRC embedded block (metadata)
├── sdr_scipy_epy_block_1_0.py      # GRC embedded block (carrier)
├── Interference.py                 # CORE: FFT + Detection engine
├── orchestrator.py                 # HTTP control plane (port 8780)
├── config_manager.py               # Authorized frequency manager
├── detection_confidence.py         # Confidence scoring helper
├── cuc_detector.py                 # Carrier-under-carrier detector
├── authorized_freqs.json           # Frequency configuration
└── requirements-cms.txt            # Python dependencies
```

**Storage locations on Pi:**
- **MicroSD Card:** `/home/pi/scipy-cms/backend/` (all Python files)
- **SSD:** `/mnt/ssd/scipy-data/` (logs, PSD snapshots, runtime state)

### 🟢 FILES FOR CENTRAL DASHBOARD

**Keep these on your main computer:**

```
Frontend1/
├── src/                            # React source code
├── public/                         # Static assets
├── package.json                    # Node dependencies
├── vite.config.ts                  # Vite configuration
├── index.html                      # Entry point
└── [all other frontend files]
```

### ⚪ SHARED DOCUMENTATION (Optional)

```
ARCHITECTURE.md                     # System documentation
PI_IMPLEMENTATION.md                # This file
```

---

## 4. RASPBERRY PI SETUP - STEP BY STEP

### Step 1: Install Raspberry Pi OS

**On your main computer:**

1. Download **Raspberry Pi Imager**: https://www.raspberrypi.com/software/
2. Insert MicroSD card into your computer
3. Open Raspberry Pi Imager
4. Choose:
   - **OS:** Raspberry Pi OS (64-bit) - Recommended
   - **Storage:** Your MicroSD card
5. Click **Settings** (gear icon):
   - Set hostname: `scipy-pi-1` (or unique name per antenna)
   - Enable SSH (password authentication)
   - Set username: `pi`
   - Set password: [your secure password]
   - Configure WiFi (optional, LAN recommended)
   - Set locale/timezone
6. Click **Write** and wait for completion
7. Insert MicroSD into Raspberry Pi and power on

### Step 2: Initial Pi Configuration

**Connect to Pi via SSH:**

```bash
# From your main computer
ssh pi@scipy-pi-1.local
# Or use IP address: ssh pi@192.168.1.XXX
```

**Update system:**

```bash
sudo apt update
sudo apt upgrade -y
sudo reboot
```

### Step 3: Mount SSD for Data Storage

**After reboot, reconnect via SSH:**

```bash
# Connect SSD to USB 3.0 port (blue port on Pi 4)

# Identify SSD device
lsblk
# Look for your SSD (usually /dev/sda)

# Format SSD (⚠️ WARNING: This erases all data on SSD)
sudo mkfs.ext4 /dev/sda

# Create mount point
sudo mkdir -p /mnt/ssd

# Get UUID of SSD
sudo blkid /dev/sda
# Copy the UUID value

# Add to fstab for auto-mount on boot
sudo nano /etc/fstab
# Add this line (replace UUID with your actual UUID):
UUID=your-uuid-here /mnt/ssd ext4 defaults,nofail 0 2

# Mount SSD
sudo mount -a

# Create data directory
sudo mkdir -p /mnt/ssd/scipy-data
sudo chown pi:pi /mnt/ssd/scipy-data

# Verify mount
df -h | grep ssd
```

### Step 4: Install Python Dependencies

```bash
# Install Python 3 and pip
sudo apt install -y python3 python3-pip python3-venv

# Install system dependencies
sudo apt install -y \
    libzmq3-dev \
    libatlas-base-dev \
    libopenblas-dev \
    libhdf5-dev \
    python3-pyqt5 \
    python3-matplotlib \
    python3-numpy \
    python3-scipy
```

### Step 5: Install GNU Radio

**GNU Radio is required for HackRF SDR interface:**

```bash
# Install GNU Radio from repository
sudo apt install -y gnuradio

# Install SoapySDR for HackRF support
sudo apt install -y \
    soapysdr-tools \
    soapysdr-module-hackrf \
    hackrf \
    libhackrf-dev

# Verify GNU Radio installation
gnuradio-config-info --version
# Should show version 3.10.x or higher

# Test HackRF detection
hackrf_info
# Should detect your HackRF device
```

### Step 6: Create Project Directory

```bash
# Create project structure
mkdir -p /home/pi/scipy-cms/backend
cd /home/pi/scipy-cms

# Link data directory to SSD
ln -s /mnt/ssd/scipy-data data
```

### Step 7: Transfer Backend Files to Pi

**On your main computer (from project root):**

```bash
# Using SCP to transfer files
scp backend/*.py pi@scipy-pi-1.local:/home/pi/scipy-cms/backend/
scp backend/*.grc pi@scipy-pi-1.local:/home/pi/scipy-cms/backend/
scp backend/requirements-cms.txt pi@scipy-pi-1.local:/home/pi/scipy-cms/backend/
scp backend/authorized_freqs.json pi@scipy-pi-1.local:/home/pi/scipy-cms/backend/

# Or use rsync for entire backend folder
rsync -avz --exclude='__pycache__' --exclude='*.pyc' \
    backend/ pi@scipy-pi-1.local:/home/pi/scipy-cms/backend/
```

### Step 8: Install Python Requirements on Pi

**Back on Raspberry Pi SSH session:**

```bash
cd /home/pi/scipy-cms/backend

# Create virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate

# Install Python packages
pip install --upgrade pip
pip install -r requirements-cms.txt

# Verify installations
python3 -c "import flask, numpy, scipy, zmq; print('All imports OK')"
```

### Step 9: Configure Firewall (Optional but Recommended)

```bash
# Install UFW firewall
sudo apt install -y ufw

# Allow SSH
sudo ufw allow 22/tcp

# Allow orchestrator port (main API)
sudo ufw allow 8780/tcp

# Allow config manager web UI
sudo ufw allow 5580/tcp

# Enable firewall
sudo ufw enable
sudo ufw status
```

### Step 10: Create Systemd Service for Auto-Start

**Create service file:**

```bash
sudo nano /etc/systemd/system/scipy-cms.service
```

**Add this content:**

```ini
[Unit]
Description=SCIPY-CMS Interference Detection Service
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/scipy-cms/backend
Environment="SCIPY_HEADLESS=1"
Environment="SCIPY_ACTIVE_ANTENNA=gsat-30"
Environment="SCIPY_SNAPSHOT_PORT=8766"
Environment="SCIPY_ORCHESTRATOR_PORT=8780"
Environment="SCIPY_CONFIG_PORT=5580"
Environment="SCIPY_DATA_DIR=/mnt/ssd/scipy-data"
ExecStart=/home/pi/scipy-cms/backend/venv/bin/python3 /home/pi/scipy-cms/backend/orchestrator.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Enable and start service:**

```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable service to start on boot
sudo systemctl enable scipy-cms.service

# Start service now
sudo systemctl start scipy-cms.service

# Check status
sudo systemctl status scipy-cms.service

# View logs
sudo journalctl -u scipy-cms.service -f
```

---

## 5. CENTRAL DASHBOARD SETUP

### Step 1: Install Node.js

**On your main computer:**

**Windows:**
- Download from: https://nodejs.org/ (LTS version)
- Run installer and follow prompts

**Linux/Mac:**
```bash
# Using nvm (recommended)
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.0/install.sh | bash
nvm install --lts
nvm use --lts
```

### Step 2: Install Frontend Dependencies

```bash
# Navigate to frontend directory
cd Frontend1

# Install dependencies
npm install

# Verify installation
npm list --depth=0
```

### Step 3: Configure Frontend for Remote Pi

**Edit `Frontend1/vite.config.ts`:**

```typescript
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";
import path from "path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    host: true,
    port: 5173,
    proxy: {
      "/api": {
        target: "http://192.168.1.100:8780",  // ← CHANGE THIS to your Pi's IP
        changeOrigin: true,
        secure: false,
      },
    },
  },
});
```

**Update satellite data with Pi IP:**

Edit `Frontend1/src/data/satellites.ts`:

```typescript
export const satellites: Satellite[] = [
  {
    id: 1,
    name: "GSAT-30",
    // ... other fields ...
    piIpAddress: "192.168.1.100",  // ← Your Raspberry Pi IP address
    // ... rest of config ...
  },
  // ... other satellites ...
];
```

### Step 4: Run Development Server

```bash
cd Frontend1
npm run dev
```

**Access dashboard:**
- Open browser: `http://localhost:5173`
- Login with your credentials
- Click "Monitor" on GSAT-30 satellite card

### Step 5: Production Build (Optional)

**For production deployment:**

```bash
cd Frontend1
npm run build

# Serve with a static server
npm install -g serve
serve -s dist -p 3000
```

---

## 6. NETWORK CONFIGURATION & IP MANAGEMENT

### Finding Raspberry Pi IP Address

**Method 1: From Pi directly (if you have monitor/keyboard):**
```bash
hostname -I
```

**Method 2: From your router's admin panel:**
- Look for device named `scipy-pi-1`

**Method 3: Network scan from main computer:**
```bash
# Linux/Mac
arp -a | grep scipy

# Windows PowerShell
arp -a | Select-String "scipy"

# Or use nmap
nmap -sn 192.168.1.0/24
```

### Setting Static IP (Recommended)

**On Raspberry Pi:**

```bash
# Edit dhcpcd configuration
sudo nano /etc/dhcpcd.conf

# Add at the end (adjust to your network):
interface eth0
static ip_address=192.168.1.100/24
static routers=192.168.1.1
static domain_name_servers=192.168.1.1 8.8.8.8

# Save and reboot
sudo reboot
```

### IP Configuration Files

**File:** `Frontend1/src/data/satellites.ts`
- **Purpose:** Stores Pi IP for each satellite
- **Location:** Frontend codebase
- **How to change:** Edit the `piIpAddress` field

**File:** `Frontend1/vite.config.ts`
- **Purpose:** Development proxy configuration
- **Location:** Frontend root
- **How to change:** Update `proxy.target` URL

**File:** `backend/orchestrator.py`
- **Purpose:** Backend listens on all interfaces (0.0.0.0)
- **No change needed** - automatically accepts connections from any IP

### Connecting Multiple Raspberry Pis

**For multiple antennas:**

1. **Each Pi gets unique:**
   - Hostname: `scipy-pi-1`, `scipy-pi-2`, etc.
   - Static IP: `192.168.1.100`, `192.168.1.101`, etc.
   - Antenna ID: `gsat-30`, `intelsat-28`, etc.

2. **Update `satellites.ts`:**
```typescript
export const satellites: Satellite[] = [
  {
    id: 1,
    name: "GSAT-30",
    piIpAddress: "192.168.1.100",  // Pi #1
    // ...
  },
  {
    id: 2,
    name: "INTELSAT-28",
    piIpAddress: "192.168.1.101",  // Pi #2
    // ...
  },
];
```

---

## 7. ANTENNA CONNECTION & SWITCHING

### Physical Connection

```
Antenna → Coax Cable → HackRF SDR → USB 3.0 → Raspberry Pi
```

**Connection checklist:**
1. Connect antenna to HackRF's SMA connector
2. Connect HackRF to Pi's USB 3.0 port (blue port)
3. Verify detection: `hackrf_info` (should show device)

### Antenna Configuration in Software

**File responsible:** `backend/config_manager.py`

**Configuration storage:** `backend/authorized_freqs.json`

**Structure:**
```json
{
  "gsat-30": [
    {
      "center": 70000000,
      "bandwidth": 500000,
      "label": "Downlink Channel 1"
    }
  ],
  "intelsat-28": [
    {
      "center": 72000000,
      "bandwidth": 1000000,
      "label": "Transponder A"
    }
  ]
}
```

### Switching Between Antennas

**Method 1: Via Frontend Dashboard**

1. Stop current monitoring session
2. Navigate to dashboard
3. Click "Monitor" on different satellite
4. Frontend automatically connects to that satellite's Pi IP

**Method 2: Via Environment Variable**

```bash
# On Raspberry Pi, change active antenna
sudo systemctl stop scipy-cms

# Edit service file
sudo nano /etc/systemd/system/scipy-cms.service

# Change this line:
Environment="SCIPY_ACTIVE_ANTENNA=intelsat-28"

# Restart
sudo systemctl daemon-reload
sudo systemctl start scipy-cms
```

**Method 3: Via API Call**

```bash
# Change active antenna without restart
curl -X POST http://192.168.1.100:5580/api/active-antenna \
  -H "Content-Type: application/json" \
  -d '{"antenna_id": "intelsat-28"}'
```

### Managing Authorized Frequencies

**Web UI (Recommended):**
- Open: `http://192.168.1.100:5580`
- Select antenna from dropdown
- Add/remove frequencies
- Changes save automatically to `authorized_freqs.json`

**Manual editing:**
```bash
# On Raspberry Pi
nano /home/pi/scipy-cms/backend/authorized_freqs.json

# Edit JSON, then restart
sudo systemctl restart scipy-cms
```

### Changing Center Frequency

**File:** `backend/Interference.py`

**Current setting:**
```python
HW_CENTER_FREQ = 70e6  # 70 MHz
```

**To change:**
1. Edit `Interference.py` on Pi
2. Change `HW_CENTER_FREQ` value
3. Restart service: `sudo systemctl restart scipy-cms`

**Or via GNU Radio:**
```bash
# If sdr_scipy.py is running standalone
# Use XML-RPC to change frequency dynamically
# (Advanced - requires XML-RPC client)
```

---

## 8. STARTING THE SYSTEM

### Complete Startup Sequence

**1. Power on Raspberry Pi**
```bash
# Service starts automatically if enabled
# Check status:
sudo systemctl status scipy-cms
```

**2. Verify backend is running**
```bash
# Check orchestrator
curl http://localhost:8780/api/health

# Expected response:
# {"status":"ok","sdr_running":false,"detector_running":false}
```

**3. Start frontend dashboard (on main computer)**
```bash
cd Frontend1
npm run dev
```

**4. Access dashboard**
- Browser: `http://localhost:5173`
- Login
- Click "Monitor" on satellite

**5. Backend auto-starts SDR + Detector**
- Frontend sends: `POST /api/monitor/start`
- Orchestrator starts: `sdr_scipy.py` → `Interference.py`
- Data flows: HackRF → GNU Radio → ZMQ → Detector → HTTP → Frontend

### Manual Start (for testing)

**On Raspberry Pi:**

```bash
cd /home/pi/scipy-cms/backend
source venv/bin/activate

# Terminal 1: Start orchestrator
python3 orchestrator.py

# Terminal 2: Start config manager (if not auto-started)
python3 config_manager.py

# Terminal 3: Manual SDR start (optional)
python3 sdr_scipy.py

# Terminal 4: Manual detector start (optional)
SCIPY_HEADLESS=1 python3 Interference.py
```

### Stopping the System

**From frontend:**
- Click "Stop Monitoring" button
- Sends: `POST /api/monitor/stop`

**From Pi:**
```bash
# Stop service
sudo systemctl stop scipy-cms

# Or kill processes manually
pkill -f orchestrator.py
pkill -f sdr_scipy.py
pkill -f Interference.py
```

---

## 9. TROUBLESHOOTING

### Issue: Cannot connect to Raspberry Pi

**Symptoms:** Frontend shows "Connection failed" or timeout

**Solutions:**
1. Verify Pi is powered on: `ping 192.168.1.100`
2. Check service status: `sudo systemctl status scipy-cms`
3. Check firewall: `sudo ufw status`
4. Verify IP in `vite.config.ts` matches Pi's actual IP
5. Check logs: `sudo journalctl -u scipy-cms -n 50`

### Issue: HackRF not detected

**Symptoms:** `hackrf_info` shows "No HackRF boards found"

**Solutions:**
1. Check USB connection (use USB 3.0 port)
2. Check USB power: `lsusb` (should show HackRF device)
3. Install drivers: `sudo apt install hackrf libhackrf-dev`
4. Check permissions: `sudo usermod -a -G plugdev pi`
5. Reboot Pi

### Issue: No spectrum data in frontend

**Symptoms:** Dashboard shows flat line or "No data"

**Solutions:**
1. Check if SDR is running: `ps aux | grep sdr_scipy`
2. Check ZMQ ports: `netstat -tulpn | grep 555`
3. Verify antenna is connected
4. Check detector logs: `sudo journalctl -u scipy-cms -f`
5. Restart monitoring from frontend

### Issue: High CPU usage / Pi overheating

**Solutions:**
1. Install cooling fan
2. Reduce FFT size in `Interference.py`: `FFT_SIZE = 1024`
3. Increase polling interval in frontend
4. Use Pi 5 for better performance
5. Monitor temperature: `vcgencmd measure_temp`

### Issue: SSD not mounting

**Solutions:**
1. Check connection: `lsblk`
2. Verify fstab entry: `cat /etc/fstab`
3. Manual mount: `sudo mount /dev/sda /mnt/ssd`
4. Check filesystem: `sudo fsck /dev/sda`
5. Reformat if needed: `sudo mkfs.ext4 /dev/sda`

### Issue: Port conflicts

**Symptoms:** "Address already in use" errors

**Solutions:**
```bash
# Find process using port 8780
sudo lsof -i :8780

# Kill process
sudo kill -9 <PID>

# Or change port in orchestrator.py
```

---

## 10. MAINTENANCE & MONITORING

### Regular Maintenance Tasks

**Daily:**
- Check dashboard for anomalies
- Verify data is being collected

**Weekly:**
- Check disk space: `df -h`
- Review logs: `sudo journalctl -u scipy-cms --since "1 week ago"`
- Verify SSD health: `sudo smartctl -a /dev/sda`

**Monthly:**
- Update system: `sudo apt update && sudo apt upgrade`
- Clean old logs: `sudo journalctl --vacuum-time=30d`
- Backup configuration files
- Check temperature trends

### Monitoring Commands

```bash
# System status
sudo systemctl status scipy-cms

# Live logs
sudo journalctl -u scipy-cms -f

# Resource usage
htop

# Network connections
sudo netstat -tulpn | grep python

# Disk usage
du -sh /mnt/ssd/scipy-data/*

# Temperature
vcgencmd measure_temp
```

### Backup Strategy

**Configuration files to backup:**
```bash
# Create backup
tar -czf scipy-backup-$(date +%Y%m%d).tar.gz \
  /home/pi/scipy-cms/backend/*.py \
  /home/pi/scipy-cms/backend/authorized_freqs.json \
  /etc/systemd/system/scipy-cms.service

# Copy to main computer
scp scipy-backup-*.tar.gz user@main-computer:/backups/
```

### Log Management

**View logs:**
```bash
# Service logs
sudo journalctl -u scipy-cms -n 100

# Python errors
grep -i error /var/log/syslog

# Custom log location (if configured)
tail -f /mnt/ssd/scipy-data/detection.log
```

**Rotate logs:**
```bash
# Configure logrotate
sudo nano /etc/logrotate.d/scipy-cms

# Add:
/mnt/ssd/scipy-data/*.log {
    daily
    rotate 7
    compress
    missingok
    notifempty
}
```

### Performance Optimization

**For better performance:**

1. **Overclock Pi (carefully):**
```bash
sudo nano /boot/config.txt
# Add:
over_voltage=2
arm_freq=1800
```

2. **Disable unnecessary services:**
```bash
sudo systemctl disable bluetooth
sudo systemctl disable avahi-daemon
```

3. **Use RAM disk for temporary data:**
```bash
sudo mkdir /mnt/ramdisk
sudo mount -t tmpfs -o size=512M tmpfs /mnt/ramdisk
```

---

## QUICK REFERENCE

### Essential Commands

| Task | Command |
|------|---------|
| Check service status | `sudo systemctl status scipy-cms` |
| Restart service | `sudo systemctl restart scipy-cms` |
| View live logs | `sudo journalctl -u scipy-cms -f` |
| Check Pi IP | `hostname -I` |
| Test HackRF | `hackrf_info` |
| Check disk space | `df -h` |
| Monitor CPU/RAM | `htop` |
| Test API | `curl http://localhost:8780/api/health` |

### Port Reference

| Port | Service | Purpose |
|------|---------|---------|
| 8780 | Orchestrator | Main API endpoint (frontend connects here) |
| 8766 | Interference.py | Snapshot API (internal) |
| 5580 | Config Manager | Frequency management web UI |
| 5555 | ZMQ | IQ data stream (internal) |
| 5556 | ZMQ | Metadata stream (internal) |
| 5557 | ZMQ | Carrier hints (internal) |
| 8080 | XML-RPC | GNU Radio control (internal) |

### File Locations

| Item | Location |
|------|----------|
| Backend code | `/home/pi/scipy-cms/backend/` |
| Data storage | `/mnt/ssd/scipy-data/` |
| Service file | `/etc/systemd/system/scipy-cms.service` |
| Config file | `/home/pi/scipy-cms/backend/authorized_freqs.json` |
| Logs | `sudo journalctl -u scipy-cms` |

---

## SUPPORT & NEXT STEPS

### Testing Checklist

- [ ] Raspberry Pi boots successfully
- [ ] SSD mounts automatically
- [ ] HackRF detected (`hackrf_info`)
- [ ] Service starts on boot
- [ ] API responds (`curl http://PI_IP:8780/api/health`)
- [ ] Frontend connects to Pi
- [ ] Spectrum data displays in dashboard
- [ ] Detection logs appear
- [ ] Authorized frequencies load correctly

### Additional Resources

- **GNU Radio Documentation:** https://wiki.gnuradio.org/
- **HackRF Documentation:** https://hackrf.readthedocs.io/
- **Raspberry Pi Documentation:** https://www.raspberrypi.com/documentation/
- **Flask API Documentation:** https://flask.palletsprojects.com/

### Contact & Support

For issues specific to this implementation, refer to:
- `ARCHITECTURE.md` - System design details
- Backend code comments - Implementation specifics
- Frontend code - UI/UX behavior

---

**END OF IMPLEMENTATION GUIDE**

*This guide provides a complete deployment strategy for the SCIPY-CMS interference detection system on Raspberry Pi hardware. Follow each step carefully and verify functionality at each stage.*
