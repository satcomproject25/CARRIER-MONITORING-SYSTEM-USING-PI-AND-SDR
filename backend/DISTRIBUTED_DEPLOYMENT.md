# Distributed SDR Deployment Guide

## Overview

The Interference.py ZMQ transport layer now supports distributed deployment across multiple hosts:
- **Raspberry Pi** running GNU Radio + SDR hardware
- **Backend server** running detection/processing pipeline
- **Remote frontend** accessing via web API

All hardcoded `tcp://127.0.0.1:*` endpoints have been replaced with environment-driven configuration.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Raspberry Pi (ARM64)                                           │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  GNU Radio Flowgraph (sdr_scipy.py)                      │  │
│  │  - SoapySDR Source (RTL-SDR / HackRF / LimeSDR)          │  │
│  │  - ZMQ PUB Sink (BIND mode)                              │  │
│  │    • IQ stream:      tcp://0.0.0.0:5555                  │  │
│  │    • Metadata:       tcp://0.0.0.0:5556                  │  │
│  │    • Carrier hints:  tcp://0.0.0.0:5557                  │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                            │
                            │ LAN/WiFi (ZMQ over TCP)
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  Backend Server (x86_64 / ARM64)                                │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Interference.py (Detection Pipeline)                    │  │
│  │  - ZMQ SUB Client (CONNECT mode)                         │  │
│  │    • IQ stream:      tcp://192.168.1.20:5555             │  │
│  │    • Metadata:       tcp://192.168.1.20:5556             │  │
│  │    • Carrier hints:  tcp://192.168.1.20:5557             │  │
│  │  - FFT + Adaptive Detection                              │  │
│  │  - Interference Classification                           │  │
│  │  - Flask Snapshot API (port 8766)                        │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                            │
                            │ HTTP/WebSocket
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  Remote Frontend (Browser)                                      │
│  - React Dashboard                                              │
│  - Real-time spectrum visualization                             │
│  - Carrier/interference logs                                    │
└─────────────────────────────────────────────────────────────────┘
```

---

## Environment Variables

### Deployment Mode

| Variable       | Default | Description                                    |
|----------------|---------|------------------------------------------------|
| `LOCAL_MODE`   | `true`  | Forces localhost endpoints (single-machine)    |
| `REMOTE_MODE`  | `false` | Enables distributed mode (multi-host)          |

### ZMQ Endpoints

| Variable                 | Default                  | Description                          |
|--------------------------|--------------------------|--------------------------------------|
| `SCIPY_ZMQ_IQ_ADDR`      | `tcp://127.0.0.1:5555`   | IQ stream endpoint (GNU Radio PUB)   |
| `SCIPY_ZMQ_META_ADDR`    | `tcp://127.0.0.1:5556`   | Metadata stream endpoint             |
| `SCIPY_ZMQ_CARRIER_ADDR` | `tcp://127.0.0.1:5557`   | Carrier hints endpoint (optional)    |

---

## Deployment Scenarios

### Scenario 1: Local Development (Single Machine)

**Use case:** Testing on laptop/desktop with SDR attached locally.

**Configuration:**
```bash
# No environment variables needed — defaults to localhost
python backend/Interference.py
```

**GNU Radio configuration:**
- ZMQ PUB Sink address: `tcp://127.0.0.1:5555` (default)

---

### Scenario 2: Distributed Deployment (Raspberry Pi + Backend Server)

**Use case:** Production deployment with Raspberry Pi at antenna site, backend server in data center.

#### Raspberry Pi Setup (192.168.1.20)

1. **Edit GNU Radio flowgraph** (`sdr_scipy.grc`):
   - ZMQ PUB Sink address: `tcp://0.0.0.0:5555` (bind to all interfaces)
   - Regenerate Python: `grcc sdr_scipy.grc`

2. **Start GNU Radio:**
   ```bash
   python3 sdr_scipy.py
   ```

3. **Verify binding:**
   ```bash
   netstat -tuln | grep 5555
   # Should show: tcp 0.0.0.0:5555 LISTEN
   ```

#### Backend Server Setup (192.168.1.100)

1. **Set environment variables:**
   ```bash
   export REMOTE_MODE="true"
   export SCIPY_ZMQ_IQ_ADDR="tcp://192.168.1.20:5555"
   export SCIPY_ZMQ_META_ADDR="tcp://192.168.1.20:5556"
   export SCIPY_ZMQ_CARRIER_ADDR="tcp://192.168.1.20:5557"
   ```

2. **Start detection pipeline:**
   ```bash
   export SCIPY_HEADLESS=1  # Headless mode for server deployment
   python backend/Interference.py
   ```

3. **Verify connection:**
   - Check startup logs for `[ZMQ] Deployment mode: REMOTE`
   - Confirm endpoints: `[ZMQ] IQ stream endpoint: tcp://192.168.1.20:5555`

---

### Scenario 3: Docker Deployment

**Use case:** Containerized backend service connecting to remote GNU Radio.

**Dockerfile:**
```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY backend/ /app/backend/
RUN pip install -r backend/requirements-cms.txt

ENV SCIPY_HEADLESS=1
ENV REMOTE_MODE=true
ENV SCIPY_ZMQ_IQ_ADDR=tcp://192.168.1.20:5555
ENV SCIPY_ZMQ_META_ADDR=tcp://192.168.1.20:5556
ENV SCIPY_ZMQ_CARRIER_ADDR=tcp://192.168.1.20:5557

CMD ["python", "backend/Interference.py"]
```

**Run:**
```bash
docker build -t sdr-backend .
docker run -p 8766:8766 sdr-backend
```

---

### Scenario 4: Multi-Site Deployment (Multiple SDRs)

**Use case:** Multiple Raspberry Pi SDRs at different antenna sites, centralized backend.

**Configuration:**
```bash
# Backend server connects to multiple SDR instances via orchestrator
# Each SDR runs on different ports or IPs

# SDR Site A (192.168.1.20:5555)
export SCIPY_ZMQ_IQ_ADDR="tcp://192.168.1.20:5555"

# SDR Site B (192.168.1.21:5555)
# Run separate Interference.py instance with different port
export SCIPY_SNAPSHOT_PORT=8767
export SCIPY_ZMQ_IQ_ADDR="tcp://192.168.1.21:5555"
```

---

## Resilient Features

### Automatic Reconnection

The DataFetcher thread includes automatic reconnection logic:

- **Timeout handling:** 100ms poll timeout prevents blocking
- **Error tracking:** Counts consecutive errors (max 10 before reconnect)
- **Rate limiting:** Reconnect attempts limited to once per 5 seconds
- **Socket recreation:** Closes stale sockets and creates new connections

### Non-Blocking Receive

All ZMQ receive operations use `zmq.NOBLOCK` flag:
- Prevents pipeline stalls on network interruption
- Allows graceful degradation (continues with last known data)

### Diagnostic Logging

Startup logs show active configuration:
```
[ZMQ] Deployment mode: REMOTE
[ZMQ] IQ stream endpoint:      tcp://192.168.1.20:5555
[ZMQ] Metadata stream endpoint: tcp://192.168.1.20:5556
[ZMQ] Carrier hints endpoint:   tcp://192.168.1.20:5557
[ZMQ] Remote mode active — expecting GNU Radio on remote host
[ZMQ] IQ stream connected to tcp://192.168.1.20:5555
[ZMQ] Carrier hints connected to tcp://192.168.1.20:5557
[ZMQ] Metadata stream connected to tcp://192.168.1.20:5556
```

Runtime reconnection logs:
```
[ZMQ] 10 consecutive errors — triggering reconnect
[ZMQ] Network interruption detected — attempting reconnect...
[ZMQ] Reconnecting IQ stream to tcp://192.168.1.20:5555...
[ZMQ] IQ stream connected to tcp://192.168.1.20:5555
[ZMQ] Reconnection successful
```

---

## Network Requirements

### Firewall Rules

**Raspberry Pi (GNU Radio host):**
```bash
# Allow incoming ZMQ connections
sudo ufw allow 5555/tcp comment "ZMQ IQ stream"
sudo ufw allow 5556/tcp comment "ZMQ metadata"
sudo ufw allow 5557/tcp comment "ZMQ carrier hints"
```

**Backend Server:**
```bash
# Allow incoming HTTP API connections
sudo ufw allow 8766/tcp comment "Snapshot API"
sudo ufw allow 5580/tcp comment "Config Manager API"
```

### Bandwidth Estimation

| Stream          | Data Rate                          | Bandwidth (20 MHz SR, 2048 FFT) |
|-----------------|------------------------------------|---------------------------------|
| IQ stream       | `SR × 8 bytes/sample`              | ~160 Mbps                       |
| Metadata        | ~100 bytes/update (infrequent)     | < 1 kbps                        |
| Carrier hints   | ~500 bytes/update (30 Hz)          | ~120 kbps                       |

**Recommendation:** Gigabit Ethernet or 5 GHz WiFi for IQ streaming.

---

## Troubleshooting

### Issue: "Connection refused" on startup

**Cause:** GNU Radio not running or not binding to correct interface.

**Solution:**
1. Verify GNU Radio is running: `ps aux | grep sdr_scipy`
2. Check binding: `netstat -tuln | grep 5555`
3. Ensure GNU Radio ZMQ address is `tcp://0.0.0.0:5555` (not `127.0.0.1`)

---

### Issue: "10 consecutive errors — triggering reconnect"

**Cause:** Network interruption or GNU Radio crash.

**Solution:**
1. Check network connectivity: `ping 192.168.1.20`
2. Restart GNU Radio on Raspberry Pi
3. Check firewall rules on both hosts

---

### Issue: Stale data / frozen spectrum

**Cause:** ZMQ CONFLATE not working (old messages queued).

**Solution:**
- Already handled by `sock.setsockopt(zmq.CONFLATE, 1)` in code
- Verify GNU Radio is publishing at expected rate (30 Hz)

---

### Issue: High latency / delayed updates

**Cause:** Network congestion or insufficient bandwidth.

**Solution:**
1. Reduce FFT size: `FFT_SIZE = 1024` (halves bandwidth)
2. Use wired Ethernet instead of WiFi
3. Enable QoS on router (prioritize ports 5555-5557)

---

## Testing Distributed Deployment

### 1. Test Local Mode (Baseline)

```bash
# Start GNU Radio locally
python backend/sdr_scipy.py

# Start Interference.py (default LOCAL_MODE)
python backend/Interference.py
```

**Expected output:**
```
[ZMQ] Deployment mode: LOCAL
[ZMQ] IQ stream endpoint:      tcp://127.0.0.1:5555
[ZMQ] Local mode active — expecting GNU Radio on localhost
```

---

### 2. Test Remote Mode (Distributed)

**On Raspberry Pi:**
```bash
# Edit sdr_scipy.grc: set ZMQ address to tcp://0.0.0.0:5555
grcc sdr_scipy.grc
python3 sdr_scipy.py
```

**On Backend Server:**
```bash
export REMOTE_MODE=true
export SCIPY_ZMQ_IQ_ADDR="tcp://192.168.1.20:5555"
export SCIPY_ZMQ_META_ADDR="tcp://192.168.1.20:5556"
export SCIPY_ZMQ_CARRIER_ADDR="tcp://192.168.1.20:5557"
export SCIPY_HEADLESS=1

python backend/Interference.py
```

**Expected output:**
```
[ZMQ] Deployment mode: REMOTE
[ZMQ] IQ stream endpoint:      tcp://192.168.1.20:5555
[ZMQ] Remote mode active — expecting GNU Radio on remote host
[ZMQ] IQ stream connected to tcp://192.168.1.20:5555
```

---

### 3. Test Reconnection (Resilience)

**Simulate network interruption:**
```bash
# On Raspberry Pi: stop GNU Radio
pkill -f sdr_scipy.py

# Backend should log:
# [ZMQ ERROR] IQ stream receive error: ...
# [ZMQ] 10 consecutive errors — triggering reconnect

# Restart GNU Radio
python3 sdr_scipy.py

# Backend should log:
# [ZMQ] Reconnection successful
```

---

## Migration Checklist

- [x] Replace hardcoded `tcp://127.0.0.1:5555` with `ZMQ_ADDR`
- [x] Replace hardcoded `tcp://127.0.0.1:5556` with `ZMQ_META_ADDR`
- [x] Replace hardcoded `tcp://127.0.0.1:5557` with `ZMQ_CARRIER_ADDR`
- [x] Add environment variable support (`SCIPY_ZMQ_*_ADDR`)
- [x] Add `LOCAL_MODE` / `REMOTE_MODE` flags
- [x] Implement `initialize_zmq_socket()` helper
- [x] Implement `reconnect_socket()` helper
- [x] Implement `log_zmq_configuration()` diagnostics
- [x] Add automatic reconnection in `DataFetcher`
- [x] Add non-blocking receive with `zmq.NOBLOCK`
- [x] Add error tracking and rate-limited reconnect
- [x] Add startup diagnostic logging
- [x] Preserve all DSP/detection logic (no changes)
- [x] Maintain backward compatibility (localhost default)

---

## Compatibility

### Preserved Components (Unchanged)

- ✅ FFT processing pipeline
- ✅ Adaptive thresholding algorithms
- ✅ Carrier detection logic
- ✅ Interference detection (bump/variance/curvature/level-shift)
- ✅ Valley detection and carrier splitting
- ✅ Gap detection
- ✅ Persistence tracking
- ✅ Confidence scoring
- ✅ Authorization checking
- ✅ Matplotlib visualization
- ✅ Qt GUI (desktop mode)
- ✅ Flask snapshot API (headless mode)
- ✅ All detection parameters and thresholds

### Modified Components (Transport Only)

- 🔧 ZMQ socket initialization (now uses helper functions)
- 🔧 ZMQ endpoint configuration (now environment-driven)
- 🔧 DataFetcher thread (now includes reconnection logic)

---

## Performance Impact

**Latency:** +2-5ms (network RTT) compared to localhost deployment  
**Throughput:** No change (ZMQ handles backpressure via CONFLATE)  
**CPU:** No change (same DSP algorithms)  
**Memory:** +~10 MB (ZMQ buffers for network transport)

---

## Security Considerations

### Network Exposure

- ZMQ has no built-in authentication or encryption
- Use VPN or SSH tunnel for untrusted networks
- Restrict firewall rules to known backend IPs

### Example: SSH Tunnel

**On Backend Server:**
```bash
# Forward remote ZMQ ports through SSH tunnel
ssh -L 5555:localhost:5555 \
    -L 5556:localhost:5556 \
    -L 5557:localhost:5557 \
    pi@192.168.1.20

# Use localhost endpoints (tunnel handles remote connection)
export SCIPY_ZMQ_IQ_ADDR="tcp://127.0.0.1:5555"
python backend/Interference.py
```

---

## Future Enhancements

- [ ] ZMQ CURVE encryption support
- [ ] Multi-SDR aggregation (frequency stitching)
- [ ] Dynamic endpoint discovery (mDNS/Zeroconf)
- [ ] WebSocket transport option (browser-native)
- [ ] Compression for IQ stream (reduce bandwidth)

---

## Support

For issues or questions:
1. Check logs for `[ZMQ]` and `[ZMQ ERROR]` messages
2. Verify network connectivity and firewall rules
3. Test with `zmq_proxy` utility for debugging
4. Review GNU Radio ZMQ block configuration

---

**Last Updated:** 2026-05-13  
**Version:** 1.0.0  
**Compatibility:** Python 3.11+, ZMQ 4.3+, GNU Radio 3.10+
