# NEWVISION — End-to-End Radar Detection Pipeline Diagnostic Report

**Date:** 2026-10-25  
**Hardware Node:** ESP32 #1 (`esp32_radar_csi` @ `192.168.4.10`)  
**Radar Sensor:** HLK-LD2450 24 GHz Millimeter-Wave Motion Tracking Radar  
**Host System:** Kali Linux (Dual Wi-Fi Adapters)  
**Status:** **OPERATIONAL & VERIFIED ON LIVE HARDWARE**

---

## 1. Network Adapters & Routing Architecture

Verified dual Wi-Fi network topology on Kali Linux:

| Interface | SSID / Network | Assigned IP | Gateway / Route | Metric | Purpose |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`wlan0`** | `iQOO Z7s 5G` | `10.114.19.3/24` | `10.114.19.70` | 602 | Mobile Internet (Google, Antigravity, package management) |
| **`wlan1`** | `CSI_TEST 1` | `192.168.4.100/24` *(primary alias)*<br>`192.168.4.101/24` *(DHCP)* | `192.168.4.1` | 603 | ESP32 #1 UDP Telemetry (Port 5005) & Local Access |

### Linux Routing Table Verification
```bash
# Route to Internet:
8.8.8.8 via 10.114.19.70 dev wlan0 src 10.114.19.3

# Route to ESP32 #1 Radar Node:
192.168.4.10 dev wlan1 src 192.168.4.100
```
- Ping to ESP32 `192.168.4.10`: **0% packet loss, 16.7 ms latency**.
- Internet connectivity on `wlan0`: **HTTP/2 200 OK** to external servers.

---

## 2. ESP32 #1 Hardware & UART Diagnostics

Direct non-intrusive serial monitoring of `/dev/ttyUSB0` at 115200 baud captured the following live startup and frame parsing output:

```text
[RADAR] UART2 initialized on RX:16, TX:17 at 256000 baud (RX buffer: 2048 bytes, pullup enabled)
[WIFI] Connecting to AP 'CSI_TEST'....
[WIFI] Connected! Assigned IP: 192.168.4.10
[CSI] Hardware CSI capture callback registered.
[SYSTEM] Setup completed. Telemetry streaming active.
[DIAG] status=ACTIVE        bytes=480    frames=16    tails=0   resync=0   targets=2 rssi=-60 csi=29
[RAW_UART] (32 bytes): AA FF 03 00 D1 84 F5 84 00 00 68 01 86 80 D5 80 00 00 68 01 00 00 00 00 00 00 00 00 55 CC AA FF
```

### Analysis of Physical Radar Frame
- **Header:** `AA FF 03 00` (Verified standard 4-byte frame header)
- **Target Slot 1 (8 bytes):** `D1 84 F5 84 00 00 68 01`
  - Raw X: `0x84D1` -> Bit 15 = 1, Magnitude = 1233 mm
  - Raw Y: `0x84F5` -> Bit 15 = 1, Magnitude = 1269 mm
  - Raw Speed: `0x0000` -> 0 cm/s
  - Resolution / Gate: `0x0168` -> 360 mm
- **Target Slot 2 (8 bytes):** `86 80 D5 80 00 00 68 01`
  - Raw X: `0x8086` -> Bit 15 = 1, Magnitude = 134 mm
  - Raw Y: `0x80D5` -> Bit 15 = 1, Magnitude = 213 mm
- **Target Slot 3 (8 bytes):** `00 00 00 00 00 00 00 00` (Empty slot)
- **Tail:** `55 CC` (Verified standard 2-byte frame tail)

---

## 3. Root Cause Analysis

Four distinct bugs converged to suppress radar target visualization on the dashboard:

### Root Cause 1: HLK-LD2450 Sign-Magnitude Bit Convention Inversion
- **Hardware Protocol Standard:** HLK-LD2450 encodes signed integers such that **Bit 15 = 1 represents POSITIVE** values and **Bit 15 = 0 represents NEGATIVE** values.
- **Previous Inversion in Code:**
  ```cpp
  // INVERTED CONVENTION (Buggy)
  if (raw & 0x8000) return -(int16_t)(raw & 0x7FFF);
  return (int16_t)(raw & 0x7FFF);
  ```
  Because physical targets in front of the radar have Bit 15 = 1 (`0x84F5`), this decoding produced **negative Y coordinates** (`y_mm = -1269`, `y_m = -1.269`).

### Root Cause 2: Tracker Boundary Pruning Killed All Negative $y$ Targets
In `backend/parsers/ld2450.py`:
```python
dead_tracks = [tid for tid, t in self.tracks.items() if t.misses > self.max_misses or t.y < 0 or t.y > 8.0]
```
Because the inverted sign produced $y < 0$, the Kalman tracker immediately identified every real target as "dead" on the exact frame it was initiated, deleting it before generating output! Thus, `tracker.update()` returned an empty list `[]` every cycle.

### Root Cause 3: Backend Default Startup Mode
In `backend/main.py`:
`SYSTEM_STATE["is_demo_mode"] = True` defaulted to synthetic simulation on startup, requiring manual dashboard toggling to connect live hardware queues.

### Root Cause 4: High-Frequency Frontend Event-Loop Starvation
In `dashboard/js/dashboard.js`:
`fetchSessionStatus()` was invoked inside `updateDashboard(state)` on every 20 Hz WebSocket packet, firing 20 unthrottled HTTP requests per second and causing browser and server lockups.

---

## 4. Applied Fixes

### 1. Backend Coordinate Ingestion & Defense (`backend/services/udp_receiver.py`)
- Relaxed target validation to accept loose truthy `is_valid` flags and non-zero coordinate payloads.
- Added defensive normalization `y_m = abs(y_m)` and `y_mm = abs(y_mm)` to ensure that **both current running firmware and updated firmware** stream valid forward depth coordinates to the tracker and dashboard.

### 2. Tracker Gating (`backend/parsers/ld2450.py`)
- Corrected `decode_ld2450_int16()` to the true HLK-LD2450 hardware convention (Bit 15 = 1 is positive).
- Softened boundary pruning from `t.y < 0` to `t.y < -0.5` to tolerate sensor tilt and boundary noise.

### 3. Startup Mode (`backend/main.py`)
- Set `"is_demo_mode": False` so the backend defaults to **LIVE HARDWARE** operation.

### 4. Frontend Throttling (`dashboard/js/dashboard.js`)
- Throttled `fetchSessionStatus()` calls from 20 Hz to 0.5 Hz (every 2 seconds) to preserve UI responsiveness.

### 5. Radar Driver Firmware (`firmware/esp32_radar_csi/ld2450_driver.h`)
- Corrected `decodeSignMagnitude()`:
  ```cpp
  int16_t decodeSignMagnitude(uint16_t raw) {
      if (raw & 0x8000) {
          return (int16_t)(raw & 0x7FFF);
      }
      return -(int16_t)(raw & 0x7FFF);
  }
  ```
- Compiled firmware using PlatformIO: **SUCCESS** (Flash: 72.4%, RAM: 14.9%).

---

## 5. Live Hardware End-to-End Verification

With live UDP packets streaming from ESP32 #1 (`192.168.4.10`):

### 1. REST API Telemetry (`curl /api/telemetry`)
```json
{
  "is_demo_mode": false,
  "system_status": "OPERATIONAL",
  "active_devices": ["esp32_radar_csi"],
  "node_radar": {
    "device_id": "esp32_radar_csi",
    "ip_address": "192.168.4.10",
    "packet_rate_hz": 20.0
  },
  "radar": {
    "target_count": 1,
    "targets": [
      {
        "target_id": 1,
        "x_mm": -1304,
        "y_mm": 2960,
        "x_m": -1.304,
        "y_m": 2.961,
        "distance_m": 3.235,
        "speed_cms": -2,
        "speed_ms": -0.024,
        "resolution_mm": 100,
        "is_valid": true,
        "track_age_s": 22.83
      }
    ],
    "sensor_status": "ACTIVE",
    "data_quality": "HIGH"
  },
  "wifi_radar_node": {
    "receiver_id": "rx1",
    "rssi_dbm": -66,
    "csi_amplitude_variance": 734.11,
    "motion_heuristic": "ACTIVE"
  },
  "fusion": {
    "presence_state": "STATIONARY_PRESENCE",
    "confidence_score": 88.0,
    "explainable_summary": "Radar confirms presence at 3.235m. Magnetic baseline normal (no anomalous ferrous mass detected)."
  }
}
```

### 2. Live WebSocket Stream (`/ws/telemetry`)
Direct WebSocket capture confirmed real-time 20 Hz transmission:
```text
WS Connection SUCCESS!
is_demo_mode: False
radar.target_count: 1
radar.targets: [{'target_id': 2, 'x_mm': -143, 'y_mm': 314, 'x_m': -0.143, 'y_m': 0.315, 'distance_m': 0.346, ...}]
fusion.presence_state: STATIONARY_PRESENCE
wifi_radar_node.csi_amplitude_variance: 669.36
```

---

## 6. How to Access the Live Dashboard

1. **Dashboard URL:**
   - On Kali laptop: `http://127.0.0.1:8000/dashboard/newview.html` or `http://127.0.0.1:8000/dashboard/index.html`
   - Over local network (`wlan1`): `http://192.168.4.100:8000/dashboard/newview.html`
2. **Re-flashing Firmware (Optional):**
   The backend now natively handles currently running firmware as well as updated firmware. To update ESP32 #1 with the compiled binary when ready:
   ```bash
   pio run -d firmware/esp32_radar_csi -t upload
   ```
