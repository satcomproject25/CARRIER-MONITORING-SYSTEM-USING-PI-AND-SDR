# Campus Network Deployment Guide
## Raspberry Pi (GNU Radio + Backend) + Computer 2 (Frontend)

This guide is for deploying the SDR system on a **campus network without internet access**.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│  Campus Network (No Internet) — 10.x.x.x subnet                 │
│                                                                  │
│  ┌────────────────────────────┐    ┌───────────────────────┐   │
│  │  Raspberry Pi              │    │  Computer 2           │   │
│  │  IP: 10.x.x.20             │    │  IP: 10.x.x.100       │   │
│  │  (e.g., 10.10.50.20)       │    │  (e.g., 10.10.50.100) │   │
│  │                            │    │                       │   │
│  │  ┌──────────────────────┐  │    │  ┌─────────────────┐ │   │
│  │  │ GNU Radio            │  │    │  │ React Frontend  │ │   │
│  │  │ - RTL-SDR/HackRF     │  │    │  │ - Browser UI    │ │   │
│  │  │ - ZMQ PUB localhost  │  │    │  │ - Port 5173     │ │   │
│  │  └──────────┬───────────┘  │    │  └────────▲────────┘ │   │
│  │             │ IQ samples    │    │           │ HTTP     │   │
│  │             ▼               │    │           │          │   │
│  │  ┌──────────────────────┐  │    │           │          │   │
│  │  │ Backend              │  │    │           │          │   │
│  │  │ - Interference.py    │  │    │           │          │   │
│  │  │ - Detection Pipeline │  │    │           │          │   │
│  │  │ - Flask API :8766    │──┼────┼───────────┘          │   │
│  │  └──────────────────────┘  │    │                       │   │
│  └────────────────────────────┘    └───────────────────────┘   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Prerequisites

### Raspberry Pi
- ✅ Raspberry Pi 4/5 (4GB+ RAM recommended)
- ✅ SDR hardware (RTL-SDR, HackRF, LimeSDR, etc.)
- ✅ Campus network connection (LAN cable)
- ✅ Python 3.11+, GNU Radio 3.10+
- ✅ Project files copied to Pi

### Computer 2
- ✅ Campus network connection (LAN cable or WiFi)
- ✅ Node.js 18+ (for frontend)
- ✅ Modern browser (Chrome, Firefox, Edge)
- ✅ Frontend files copied to computer

### Network
- ✅ Both devices on same subnet (e.g., 10.10.50.x)
- ✅ Can ping each other
- ✅ Firewall allows ports 8766 (API) and 5173 (frontend)

---

## Step 1: Raspberry Pi Setup

### 1.1 Find Raspberry Pi IP Address

```bash
# On Raspberry Pi
hostname -I
# Example output: 10.10.50.20
```

**Write down this IP!** You'll need it for Computer 2.

### 1.2 Install Dependencies

```bash
# On Raspberry Pi
cd /path/to/your/project

# Install Python dependencies
pip3 install -r backend/requirements-cms.txt

# Verify GNU Radio installed
gnuradio-config-info --version
```

### 1.3 Configure GNU Radio (Default Localhost)

**No changes needed!** The default configuration works:

```bash
# Verify sdr_scipy.grc has these ZMQ addresses:
# - IQ stream:      tcp://127.0.0.1:5555
# - Metadata:       tcp://127.0.0.1:5556
# - Carrier hints:  tcp://127.0.0.1:5557

# If you modified them, regenerate:
grcc backend/sdr_scipy.grc
```

### 1.4 Configure Firewall (Allow Computer 2 Access)

```bash
# On Raspberry Pi
# Allow Computer 2 to access Flask API
sudo ufw allow from 10.10.50.0/24 to any port 8766 comment "Backend API"

# Or if you know Computer 2's exact IP:
sudo ufw allow from 10.10.50.100 to any port 8766

# Check firewall status
sudo ufw status
```

### 1.5 Start GNU Radio

```bash
# On Raspberry Pi — Terminal 1
cd /path/to/your/project/backend
python3 sdr_scipy.py
```

**Expected output:**
```
gr-osmosdr 0.2.0.0 (0.2.0) gnuradio 3.10.1.1
built-in source types: file osmosdr fcd rtl rtl_tcp uhd hackrf bladerf rfspace airspy airspyhf soapy redpitaya freesrp
Using device #0 Realtek RTL2838UHIDIR SN: 00000001
[INFO] Opening Generic RTL2838UHIDIR SN: 00000001
Found Rafael Micro R820T tuner
```

**Leave this running!**

### 1.6 Start Backend

```bash
# On Raspberry Pi — Terminal 2 (or new SSH session)
cd /path/to/your/project

# Enable headless mode (no GUI)
export SCIPY_HEADLESS=1

# Optional: Set active antenna
export SCIPY_ACTIVE_ANTENNA=gsat-30

# Start backend
python backend/Interference.py
```

**Expected output:**
```
[ZMQ] Deployment mode: LOCAL
[ZMQ] IQ stream endpoint:      tcp://127.0.0.1:5555
[ZMQ] Metadata stream endpoint: tcp://127.0.0.1:5556
[ZMQ] Carrier hints endpoint:   tcp://127.0.0.1:5557
[ZMQ] Local mode active — expecting GNU Radio on localhost
[ZMQ] IQ stream connected to tcp://127.0.0.1:5555
[ZMQ] Carrier hints connected to tcp://127.0.0.1:5557
[ZMQ] Metadata stream connected to tcp://127.0.0.1:5556
[INFO] DataFetcher thread started.
[INFO] Headless detection service (no matplotlib/Qt windows)
[INFO] Snapshot API http://0.0.0.0:8766/api/snapshot
```

**Key line:** `Snapshot API http://0.0.0.0:8766` — means API is accessible from network!

### 1.7 Test Backend API (from Raspberry Pi)

```bash
# On Raspberry Pi — Terminal 3
curl http://localhost:8766/api/health
```

**Expected output:**
```json
{"status":"ok","headless":true,"port":8766}
```

✅ **Raspberry Pi setup complete!**

---

## Step 2: Computer 2 Setup

### 2.1 Find Computer 2 IP Address

```bash
# On Computer 2 (Linux/Mac)
hostname -I

# On Computer 2 (Windows)
ipconfig
```

### 2.2 Test Network Connectivity to Raspberry Pi

```bash
# On Computer 2
# Replace 10.10.50.20 with your Raspberry Pi's IP
ping 10.10.50.20
```

**Expected:** Successful ping responses

```bash
# Test API connectivity
curl http://10.10.50.20:8766/api/health
```

**Expected output:**
```json
{"status":"ok","headless":true,"port":8766}
```

✅ If this works, you're ready for frontend!

❌ If this fails, check:
- Firewall on Raspberry Pi (Step 1.4)
- Both devices on same network
- Raspberry Pi backend is running

### 2.3 Configure Frontend

```bash
# On Computer 2
cd /path/to/your/project/Frontend1

# Install dependencies (first time only)
npm install
```

**Edit frontend configuration to point to Raspberry Pi:**

Create or edit `Frontend1/.env`:

```bash
# Frontend1/.env
VITE_API_URL=http://10.10.50.20:8766
```

**Replace `10.10.50.20` with your Raspberry Pi's actual IP!**

### 2.4 Start Frontend

```bash
# On Computer 2
cd Frontend1
npm run dev
```

**Expected output:**
```
  VITE v5.x.x  ready in xxx ms

  ➜  Local:   http://localhost:5173/
  ➜  Network: http://10.10.50.100:5173/
  ➜  press h + enter to show help
```

### 2.5 Open Browser

On Computer 2, open browser and navigate to:

```
http://localhost:5173
```

**You should see:**
- Real-time spectrum display
- Carrier detections
- Interference alerts
- Live logs

✅ **Complete system operational!**

---

## Troubleshooting

### Issue 1: Frontend shows "API connection failed"

**Symptoms:**
- Frontend loads but shows no data
- Browser console shows network errors

**Solutions:**

1. **Verify API URL in frontend:**
   ```bash
   # Check Frontend1/.env
   cat Frontend1/.env
   # Should show: VITE_API_URL=http://10.10.50.20:8766
   ```

2. **Test API from Computer 2:**
   ```bash
   curl http://10.10.50.20:8766/api/snapshot
   ```

3. **Check CORS (should be enabled by default):**
   - Backend already has CORS headers in `_run_headless_snapshot_api()`
   - If still blocked, check browser console for CORS errors

4. **Restart frontend after changing .env:**
   ```bash
   # Stop frontend (Ctrl+C)
   # Start again
   npm run dev
   ```

---

### Issue 2: "Connection refused" when testing API

**Symptoms:**
```bash
curl http://10.10.50.20:8766/api/health
# curl: (7) Failed to connect to 10.10.50.20 port 8766: Connection refused
```

**Solutions:**

1. **Verify backend is running on Raspberry Pi:**
   ```bash
   # On Raspberry Pi
   ps aux | grep Interference.py
   ```

2. **Check backend is binding to 0.0.0.0 (not 127.0.0.1):**
   ```bash
   # On Raspberry Pi
   netstat -tuln | grep 8766
   # Should show: tcp 0.0.0.0:8766 LISTEN
   # NOT: tcp 127.0.0.1:8766 LISTEN
   ```

3. **If showing 127.0.0.1, force bind to 0.0.0.0:**
   ```bash
   # On Raspberry Pi
   export SCIPY_API_HOST="0.0.0.0"
   python backend/Interference.py
   ```

4. **Check firewall:**
   ```bash
   # On Raspberry Pi
   sudo ufw status
   # Should show: 8766 ALLOW from 10.10.50.0/24
   ```

---

### Issue 3: No spectrum data / frozen display

**Symptoms:**
- Frontend loads but spectrum is flat/frozen
- No carrier detections

**Solutions:**

1. **Verify GNU Radio is running:**
   ```bash
   # On Raspberry Pi
   ps aux | grep sdr_scipy
   ```

2. **Check ZMQ connection in backend logs:**
   ```bash
   # On Raspberry Pi
   # Look for these lines in backend output:
   [ZMQ] IQ stream connected to tcp://127.0.0.1:5555
   ```

3. **Test ZMQ manually:**
   ```bash
   # On Raspberry Pi
   python backend/test_zmq_connection.py
   ```

4. **Restart both GNU Radio and Backend:**
   ```bash
   # Stop both (Ctrl+C)
   # Start GNU Radio first
   python3 backend/sdr_scipy.py
   # Then start backend
   python backend/Interference.py
   ```

---

### Issue 4: Campus network blocks ports

**Symptoms:**
- Can ping Raspberry Pi but can't access port 8766
- Firewall rules are correct

**Solutions:**

1. **Try different port:**
   ```bash
   # On Raspberry Pi
   export SCIPY_SNAPSHOT_PORT=8080  # Common allowed port
   python backend/Interference.py
   
   # Update frontend .env
   VITE_API_URL=http://10.10.50.20:8080
   ```

2. **Check campus network policy:**
   - Contact IT department
   - Ask which ports are allowed
   - Common allowed: 80, 443, 8080, 8000

3. **Use SSH tunnel (if SSH allowed):**
   ```bash
   # On Computer 2
   ssh -L 8766:localhost:8766 pi@10.10.50.20
   
   # Then use localhost in frontend:
   VITE_API_URL=http://localhost:8766
   ```

---

## Performance Optimization

### For Raspberry Pi 4 (4GB RAM)

```bash
# Reduce FFT size for lower CPU usage
# Edit backend/Interference.py
FFT_SIZE = 1024  # Instead of 2048

# Disable some detectors if needed
INTF_ENABLED = False
VALLEY_ENABLED = False
```

### For Raspberry Pi 5 (8GB RAM)

Default settings should work fine. No optimization needed.

---

## Startup Scripts

### Raspberry Pi Auto-Start Script

Save as `/home/pi/start_sdr.sh`:

```bash
#!/bin/bash
# SDR System Startup Script for Raspberry Pi

PROJECT_DIR="/home/pi/sdr-project"  # Change to your path

# Start GNU Radio in background
cd $PROJECT_DIR/backend
python3 sdr_scipy.py > /tmp/gnuradio.log 2>&1 &
GNURADIO_PID=$!

echo "GNU Radio started (PID: $GNURADIO_PID)"
sleep 5  # Wait for GNU Radio to initialize

# Start Backend
export SCIPY_HEADLESS=1
export SCIPY_ACTIVE_ANTENNA=gsat-30
python backend/Interference.py > /tmp/backend.log 2>&1 &
BACKEND_PID=$!

echo "Backend started (PID: $BACKEND_PID)"
echo "System ready!"
echo "Access API at: http://$(hostname -I | awk '{print $1}'):8766"
echo ""
echo "To stop:"
echo "  kill $GNURADIO_PID $BACKEND_PID"
```

Make executable and run:
```bash
chmod +x /home/pi/start_sdr.sh
./start_sdr.sh
```

### Computer 2 Startup Script

Save as `start_frontend.sh`:

```bash
#!/bin/bash
# Frontend Startup Script for Computer 2

RASPBERRY_PI_IP="10.10.50.20"  # Change to your Pi's IP

# Test connectivity
echo "Testing connection to Raspberry Pi..."
if ! curl -s http://$RASPBERRY_PI_IP:8766/api/health > /dev/null; then
    echo "ERROR: Cannot reach Raspberry Pi at $RASPBERRY_PI_IP:8766"
    echo "Check:"
    echo "  1. Raspberry Pi is powered on"
    echo "  2. Backend is running on Pi"
    echo "  3. Network connection"
    exit 1
fi

echo "✓ Connection successful!"

# Update .env
cd Frontend1
echo "VITE_API_URL=http://$RASPBERRY_PI_IP:8766" > .env

# Start frontend
npm run dev
```

Make executable and run:
```bash
chmod +x start_frontend.sh
./start_frontend.sh
```

---

## System Status Check

### Quick Health Check Script

Save as `check_system.sh`:

```bash
#!/bin/bash
# System Health Check

RASPBERRY_PI_IP="10.10.50.20"  # Change to your Pi's IP

echo "=== SDR System Health Check ==="
echo ""

# Test network
echo "[1/4] Testing network connectivity..."
if ping -c 1 $RASPBERRY_PI_IP > /dev/null 2>&1; then
    echo "✓ Network OK"
else
    echo "✗ Cannot reach Raspberry Pi"
    exit 1
fi

# Test API
echo "[2/4] Testing Backend API..."
if curl -s http://$RASPBERRY_PI_IP:8766/api/health | grep -q "ok"; then
    echo "✓ Backend API OK"
else
    echo "✗ Backend API not responding"
    exit 1
fi

# Test data
echo "[3/4] Testing data stream..."
if curl -s http://$RASPBERRY_PI_IP:8766/api/snapshot | grep -q "freq_mhz"; then
    echo "✓ Data stream OK"
else
    echo "✗ No data from backend"
    exit 1
fi

# Test frontend
echo "[4/4] Testing frontend..."
if curl -s http://localhost:5173 > /dev/null 2>&1; then
    echo "✓ Frontend OK"
else
    echo "⚠ Frontend not running (start with: npm run dev)"
fi

echo ""
echo "=== System Status: OPERATIONAL ==="
echo "Access frontend at: http://localhost:5173"
```

---

## Summary

### ✅ What You Have Now

1. **Raspberry Pi** running:
   - GNU Radio (SDR data acquisition)
   - Backend (detection pipeline + API)
   - Accessible at `http://10.10.50.20:8766`

2. **Computer 2** running:
   - Frontend (React dashboard)
   - Accessible at `http://localhost:5173`

3. **Communication:**
   - GNU Radio → Backend: localhost ZMQ (fast, no network)
   - Backend → Frontend: LAN HTTP (campus network)

### 🎯 Key Points

- ✅ No internet required (all on campus network)
- ✅ Backend uses default localhost ZMQ (no configuration needed)
- ✅ Frontend connects to Pi's IP over LAN
- ✅ Automatic reconnection if network hiccups
- ✅ All detection algorithms preserved

### 📝 Remember

- **Raspberry Pi IP:** Write it down and use in frontend .env
- **Firewall:** Allow port 8766 on Raspberry Pi
- **Start order:** GNU Radio first, then Backend, then Frontend
- **Testing:** Use `check_system.sh` to verify everything works

---

**Need help?** Check logs:
- GNU Radio: `/tmp/gnuradio.log`
- Backend: `/tmp/backend.log`
- Frontend: Browser console (F12)
