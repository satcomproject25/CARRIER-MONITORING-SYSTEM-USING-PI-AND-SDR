# Quick Start Guide

## 🚀 Edit Satellite & Change IP in 30 Seconds

### Step 1: Open Edit Modal
Click the **⚙️ Settings icon** on any satellite card

### Step 2: Change IP Address
Go to **"Basic Info"** tab → Edit **"Raspberry Pi IP Address"** field

### Step 3: Save
Click **"Save Changes"** button

### Step 4: Monitor
Click **"Monitor"** button on the satellite card

**Done!** The system now connects to the new Raspberry Pi and displays live data.

---

## 📝 Quick Edit Checklist

- [ ] Click Settings icon (⚙️)
- [ ] Edit Pi IP Address (e.g., `192.168.1.100`)
- [ ] Edit other fields as needed
- [ ] Click "Save Changes"
- [ ] See success toast ✅
- [ ] Click "Monitor"
- [ ] Live data appears 📡

---

## 🔧 Common IP Configurations

| Scenario | IP Address | Notes |
|----------|------------|-------|
| Local testing | `127.0.0.1` | Uses Vite proxy |
| Simulation mode | `—` | No real hardware |
| Remote Pi #1 | `192.168.1.100` | Direct connection |
| Remote Pi #2 | `192.168.1.101` | Direct connection |
| Remote Pi #3 | `192.168.1.102` | Direct connection |

---

## 🎯 Three Ways to Edit

### 1. Settings Icon (Fastest)
```
Satellite Card → ⚙️ Icon → Edit Modal
```

### 2. Detail Panel
```
Satellite Card → Details Button → Edit Button → Edit Modal
```

### 3. From Monitoring
```
Stop Monitoring → Dashboard → Settings Icon → Edit Modal
```

---

## ✅ What You Can Edit

### Basic Info
- Satellite Name
- Frequency Band
- Status (Online/Offline)
- **Pi IP Address** ⭐
- Person In-Charge
- Launch Date

### Location
- Ground Station
- State, Country
- Facing Position
- Lat/Long
- Elevation, Azimuth

### Technical
- Hardware Specs
- Signal Health
- C/N Ratio
- Eb/No

---

## 🔄 Switching Between Antennas

```
1. Monitor GSAT-30 (IP: 192.168.1.100)
   ↓
2. Stop Monitoring
   ↓
3. Go to Dashboard
   ↓
4. Monitor INTELSAT-28 (IP: 192.168.1.101)
   ↓
5. System automatically switches to new Pi
```

---

## 🐛 Quick Troubleshooting

### Can't connect after changing IP?

**Check:**
1. Ping the IP: `ping 192.168.1.XXX`
2. Test API: `curl http://192.168.1.XXX:8780/api/health`
3. Verify Pi is running: `ssh pi@192.168.1.XXX`
4. Check firewall: Port 8780 must be open

### Changes not saving?

**Verify:**
- All required fields filled (Name, IP)
- IP format is valid (xxx.xxx.xxx.xxx)
- Success toast appeared
- Refresh page if needed

---

## 📚 Full Documentation

- **PI_IMPLEMENTATION.md** - Raspberry Pi setup (complete guide)
- **SATELLITE_EDIT_GUIDE.md** - Edit feature details
- **IMPLEMENTATION_SUMMARY.md** - Technical overview
- **ARCHITECTURE.md** - System architecture

---

## 💡 Pro Tips

1. **Use static IPs** for Raspberry Pis (avoid DHCP changes)
2. **Test connection** before monitoring (curl health endpoint)
3. **Document your IPs** (keep a list of which Pi is which)
4. **Edit in batches** (configure all satellites before monitoring)
5. **Backup configs** (export satellite data periodically)

---

## 🎉 You're Ready!

The system is now fully flexible for multi-antenna deployments. Edit any detail, change IPs on the fly, and monitor multiple Raspberry Pis seamlessly!

**Happy Monitoring! 📡**
