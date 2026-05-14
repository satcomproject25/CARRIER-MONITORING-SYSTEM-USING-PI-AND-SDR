# Your Setup Summary — Campus Network Deployment

## Quick Overview

**Your Configuration:**
- 🔧 **Raspberry Pi:** GNU Radio + Backend (both on same Pi)
- 💻 **Computer 2:** Frontend only
- 🌐 **Network:** Campus LAN (no internet)

**Why this works:**
- Backend and GNU Radio on same Pi → use localhost (fast, no network config)
- Frontend on Computer 2 → connects to Pi's API over LAN

---

## What Changed in the Code

### ✅ Backend API Now Accessible from Network

**Before:**
```python
app.run(host="127.0.0.1", port=8766)  # Localhost only
```

**After:**
```python
bind_host = os.environ.get("SCIPY_API_HOST", "0.0.0.0")
app.run(host=bind_host, port=8766)  # Network accessible
```

**Result:** Computer 2 can now reach `http://10.x.x.20:8766/api/snapshot`

---

## Setup Steps (Simplified)

### On Raspberry Pi (10.x.x.20)

```bash
# Terminal 1: Start GNU Radio
python3 backend/sdr_scipy.py

# Terminal 2: Start Backend
export SCIPY_HEADLESS=1
python backend/Interference.py
```

**That's it!** No ZMQ configuration needed (uses localhost by default).

### On Computer 2 (10.x.x.100)

```bash
# Create Frontend1/.env
echo "VITE_API_URL=http://10.x.x.20:8766" > Frontend1/.env

# Start frontend
cd Frontend1
npm run dev
```

**Open browser:** `http://localhost:5173`

---

## Testing

### Test 1: From Raspberry Pi (verify backend works)
```bash
curl http://localhost:8766/api/health
# Expected: {"status":"ok","headless":true,"port":8766}
```

### Test 2: From Computer 2 (verify network access)
```bash
curl http://10.x.x.20:8766/api/health
# Expected: {"status":"ok","headless":true,"port":8766}
```

### Test 3: Open frontend
```
http://localhost:5173
```
Should show live spectrum!

---

## Firewall (If Needed)

```bash
# On Raspberry Pi
sudo ufw allow from 10.x.x.0/24 to any port 8766
```

---

## Troubleshooting

### Frontend shows "API connection failed"

**Fix:**
```bash
# On Computer 2, verify .env
cat Frontend1/.env
# Should show: VITE_API_URL=http://10.x.x.20:8766

# Test API manually
curl http://10.x.x.20:8766/api/health
```

### "Connection refused" from Computer 2

**Fix:**
```bash
# On Raspberry Pi, check backend is running
ps aux | grep Interference.py

# Check it's binding to 0.0.0.0 (not 127.0.0.1)
netstat -tuln | grep 8766
# Should show: tcp 0.0.0.0:8766 LISTEN
```

---

## Files You Need

### On Raspberry Pi
- ✅ `backend/` folder (all files)
- ✅ GNU Radio flowgraph (`sdr_scipy.grc` / `sdr_scipy.py`)
- ✅ Python dependencies installed

### On Computer 2
- ✅ `Frontend1/` folder (all files)
- ✅ Node.js installed
- ✅ `Frontend1/.env` with Pi's IP

---

## Environment Variables Reference

### Raspberry Pi (Optional)

```bash
# Headless mode (no GUI)
export SCIPY_HEADLESS=1

# API bind address (default: 0.0.0.0)
export SCIPY_API_HOST=0.0.0.0

# API port (default: 8766)
export SCIPY_SNAPSHOT_PORT=8766

# Active antenna
export SCIPY_ACTIVE_ANTENNA=gsat-30
```

### Computer 2 (Required)

```bash
# Frontend1/.env
VITE_API_URL=http://10.x.x.20:8766  # Replace with your Pi's IP
```

---

## Full Documentation

- 📘 **CAMPUS_DEPLOYMENT_GUIDE.md** — Complete step-by-step guide
- 📘 **backend/DISTRIBUTED_DEPLOYMENT.md** — Technical details
- 📘 **ZMQ_REFACTOR_SUMMARY.md** — What changed in the code

---

## Quick Start Script

Save as `start_system.sh` on Raspberry Pi:

```bash
#!/bin/bash
# Start SDR System on Raspberry Pi

cd /path/to/your/project

# Start GNU Radio
python3 backend/sdr_scipy.py > /tmp/gnuradio.log 2>&1 &
echo "GNU Radio started"
sleep 5

# Start Backend
export SCIPY_HEADLESS=1
python backend/Interference.py > /tmp/backend.log 2>&1 &
echo "Backend started"

echo "System ready at http://$(hostname -I | awk '{print $1}'):8766"
```

---

## Summary

✅ **Your setup is SIMPLE:**
1. Pi runs GNU Radio + Backend (localhost ZMQ, no config)
2. Computer 2 runs Frontend (points to Pi's IP)
3. Everything communicates over campus LAN

✅ **No internet needed**
✅ **No complex ZMQ configuration**
✅ **Just works!**

**Next step:** Follow **CAMPUS_DEPLOYMENT_GUIDE.md** for detailed instructions.
