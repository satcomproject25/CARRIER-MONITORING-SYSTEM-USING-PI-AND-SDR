# Campus Network Access Guide

## Accessing Dashboard from Other Systems (No Internet Required)

Your current setup already supports campus network access! Here's how to use it.

---

## Current Configuration Status

✅ **Vite dev server** is configured with `host: "::"` (allows external connections)  
✅ **Port 8080** is used for the dashboard  
✅ **No internet required** - works on local campus network  
✅ **No hosting needed** - runs directly from your development machine  

---

## Step-by-Step Setup

### Step 1: Find Your System's IP Address

**On Windows:**
```bash
ipconfig
```
Look for "IPv4 Address" under your active network adapter (Ethernet or Wi-Fi)

**Example output:**
```
Ethernet adapter Ethernet:
   IPv4 Address. . . . . . . . . . . : 192.168.1.100
```

**On Linux/Mac:**
```bash
ip addr show
# or
ifconfig
```

### Step 2: Start the Development Server

In your project directory:
```bash
cd Frontend1
npm run dev
```

**Expected output:**
```
VITE v5.x.x  ready in xxx ms

➜  Local:   http://localhost:8080/
➜  Network: http://192.168.1.100:8080/
➜  Network: http://[fe80::xxxx]:8080/
```

The "Network" URL is what you'll use from other systems!

### Step 3: Access from Other Systems

On any other computer/laptop on the same campus network:

1. Open a web browser (Chrome, Firefox, Edge, etc.)
2. Enter the URL: `http://YOUR_IP:8080`
3. Example: `http://192.168.1.100:8080`

**That's it!** The dashboard should load.

---

## Firewall Configuration (If Connection Fails)

If other systems can't connect, you may need to allow port 8080 through Windows Firewall:

### Windows Firewall - Allow Port 8080

**Method 1: Using Windows Defender Firewall GUI**
1. Open "Windows Defender Firewall with Advanced Security"
2. Click "Inbound Rules" → "New Rule"
3. Select "Port" → Next
4. Select "TCP" → Specific local ports: `8080` → Next
5. Select "Allow the connection" → Next
6. Check all profiles (Domain, Private, Public) → Next
7. Name: "Vite Dev Server" → Finish

**Method 2: Using Command Line (Run as Administrator)**
```powershell
netsh advfirewall firewall add rule name="Vite Dev Server" dir=in action=allow protocol=TCP localport=8080
```

---

## Testing Connection

### From the Same System (Local Test)
```bash
# Should work
http://localhost:8080
http://127.0.0.1:8080
```

### From Another System (Network Test)
```bash
# Replace with your actual IP
http://192.168.1.100:8080
```

### Verify Port is Listening
On your development system:
```bash
netstat -an | findstr :8080
```

Should show:
```
TCP    0.0.0.0:8080           0.0.0.0:0              LISTENING
TCP    [::]:8080              [::]:0                 LISTENING
```

---

## Common Issues & Solutions

### Issue 1: "Connection Refused" or "Can't Reach This Page"

**Cause**: Firewall blocking port 8080

**Solution**: 
1. Add firewall rule (see above)
2. Temporarily disable firewall to test
3. Check if dev server is running (`npm run dev`)

### Issue 2: "Network URL Not Showing"

**Cause**: Vite config issue

**Solution**: Verify `vite.config.ts` has:
```typescript
server: {
  host: "::",  // ← This allows external access
  port: 8080,
}
```

### Issue 3: Dashboard Loads but Can't Connect to Raspberry Pi

**Cause**: Pi IP address not accessible from other system

**Solution**: 
- Ensure Raspberry Pi is on same campus network
- Use Pi's campus network IP (not 127.0.0.1)
- Update satellite Pi IP in dashboard to use network IP

### Issue 4: Different Subnet

**Cause**: Systems on different network segments

**Solution**:
- Check both systems are on same subnet (e.g., 192.168.1.x)
- Contact campus IT if routing is needed between subnets
- Use VPN if campus network requires it

---

## Production Deployment (Optional)

If you want a permanent setup without running `npm run dev`:

### Option 1: Build and Serve Locally

```bash
# Build the production version
cd Frontend1
npm run build

# Serve using a simple HTTP server
npx serve -s dist -l 8080
```

### Option 2: Use Nginx (More Robust)

1. Install Nginx on your system
2. Build the frontend: `npm run build`
3. Configure Nginx to serve `Frontend1/dist`
4. Access via `http://YOUR_IP:80`

### Option 3: Docker Container (Advanced)

Create `Dockerfile` in Frontend1:
```dockerfile
FROM node:18-alpine
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build
RUN npm install -g serve
EXPOSE 8080
CMD ["serve", "-s", "dist", "-l", "8080"]
```

Build and run:
```bash
docker build -t satellite-dashboard .
docker run -p 8080:8080 satellite-dashboard
```

---

## Multi-User Scenario

### Scenario: 5 Users Accessing Dashboard

**Setup:**
- Your system: `192.168.1.100` (runs `npm run dev`)
- User 1: `192.168.1.101` (opens `http://192.168.1.100:8080`)
- User 2: `192.168.1.102` (opens `http://192.168.1.100:8080`)
- User 3: `192.168.1.103` (opens `http://192.168.1.100:8080`)
- User 4: `192.168.1.104` (opens `http://192.168.1.100:8080`)

**All users see the same dashboard interface.**

**Note**: Each user's browser maintains its own state (localStorage), so:
- Satellite edits are local to each user
- To share configuration, use Export/Import feature
- For true multi-user sync, you'd need a backend database (future enhancement)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    Campus Network                        │
│                    (No Internet)                         │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ┌──────────────────┐         ┌──────────────────┐     │
│  │  Your System     │         │  Raspberry Pi 1  │     │
│  │  192.168.1.100   │◄────────┤  192.168.1.50    │     │
│  │                  │         │  (GSAT-30)       │     │
│  │  npm run dev     │         └──────────────────┘     │
│  │  Port: 8080      │                                   │
│  └────────┬─────────┘         ┌──────────────────┐     │
│           │                   │  Raspberry Pi 2  │     │
│           │                   │  192.168.1.51    │     │
│           └───────────────────┤  (INSAT-4B)      │     │
│                               └──────────────────┘     │
│                                                          │
│  ┌──────────────────┐         ┌──────────────────┐     │
│  │  User Laptop 1   │         │  User Laptop 2   │     │
│  │  192.168.1.101   │         │  192.168.1.102   │     │
│  │                  │         │                  │     │
│  │  Browser:        │         │  Browser:        │     │
│  │  192.168.1.100   │         │  192.168.1.100   │     │
│  │  :8080           │         │  :8080           │     │
│  └──────────────────┘         └──────────────────┘     │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

---

## Security Considerations

### Campus Network Only
✅ Dashboard is only accessible within campus network  
✅ No internet exposure  
✅ Firewall protects from external access  

### Recommendations
- Keep dev server running only when needed
- Use strong passwords if you add authentication later
- Monitor who has access to campus network
- Consider HTTPS if handling sensitive data (requires SSL certificate)

---

## Quick Reference

| Task | Command/URL |
|------|-------------|
| Find your IP | `ipconfig` (Windows) or `ip addr` (Linux) |
| Start dashboard | `cd Frontend1 && npm run dev` |
| Access locally | `http://localhost:8080` |
| Access from network | `http://YOUR_IP:8080` |
| Check port listening | `netstat -an \| findstr :8080` |
| Allow firewall | `netsh advfirewall firewall add rule...` |

---

## Next Steps

1. ✅ Find your system's IP address
2. ✅ Start `npm run dev` in Frontend1
3. ✅ Note the "Network" URL from Vite output
4. ✅ Add firewall rule if needed
5. ✅ Test from another system on campus network
6. ✅ Share the URL with your team

---

**Status**: ✅ Ready to use - no code changes needed!  
**Network**: Campus network only (no internet required)  
**Hosting**: Not needed - runs from your development machine  
**Access**: Any browser on campus network can access `http://YOUR_IP:8080`
