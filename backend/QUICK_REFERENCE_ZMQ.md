# ZMQ Distributed Deployment — Quick Reference

## Environment Variables

```bash
# Deployment Mode
export LOCAL_MODE=true          # Use localhost (default)
export REMOTE_MODE=true         # Use remote endpoints

# ZMQ Endpoints
export SCIPY_ZMQ_IQ_ADDR="tcp://192.168.1.20:5555"
export SCIPY_ZMQ_META_ADDR="tcp://192.168.1.20:5556"
export SCIPY_ZMQ_CARRIER_ADDR="tcp://192.168.1.20:5557"

# Optional
export SCIPY_HEADLESS=1         # Headless mode (no GUI)
export SCIPY_SNAPSHOT_PORT=8766 # API port
```

## Quick Start

### Local (Single Machine)
```bash
python backend/Interference.py
```

### Remote (Distributed)
```bash
export REMOTE_MODE=true
export SCIPY_ZMQ_IQ_ADDR="tcp://192.168.1.20:5555"
export SCIPY_HEADLESS=1
python backend/Interference.py
```

## Test Connection
```bash
python backend/test_zmq_connection.py
```

## GNU Radio Configuration

**Edit `sdr_scipy.grc`:**
- ZMQ PUB Sink address: `tcp://0.0.0.0:5555` (bind to all interfaces)
- Regenerate: `grcc sdr_scipy.grc`

## Firewall Rules

**Raspberry Pi:**
```bash
sudo ufw allow 5555/tcp
sudo ufw allow 5556/tcp
sudo ufw allow 5557/tcp
```

**Backend Server:**
```bash
sudo ufw allow 8766/tcp
```

## Troubleshooting

```bash
# Check GNU Radio running
ps aux | grep sdr_scipy

# Check ZMQ binding
netstat -tuln | grep 5555

# Test network
ping 192.168.1.20

# View logs
python backend/Interference.py 2>&1 | grep ZMQ
```

## Expected Logs

**Success:**
```
[ZMQ] Deployment mode: REMOTE
[ZMQ] IQ stream connected to tcp://192.168.1.20:5555
```

**Reconnecting:**
```
[ZMQ] 10 consecutive errors — triggering reconnect
[ZMQ] Reconnection successful
```

## Full Documentation

- `backend/DISTRIBUTED_DEPLOYMENT.md` — Complete guide
- `ZMQ_REFACTOR_SUMMARY.md` — Technical details
