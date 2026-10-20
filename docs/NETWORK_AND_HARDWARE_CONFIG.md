# NewVision / NewView: Hardware Architecture & Network Configuration Guide

This document specifies the exact physical setup, radio modes, network configuration, and telemetry format for the **NewVision / NewView** multimodal sensing platform.

---

## 1. Intended Physical Hardware Architecture

| Device | Microcontroller / Board | Primary Sensors / Modules | Role in Platform | Interface & Bus |
| :--- | :--- | :--- | :--- | :--- |
| **NodeMCU AP** | NodeMCU v2 / ESP8266 (ESP-12E) | None (Internal Wi-Fi Radio) | Controlled 100 Hz Wi-Fi Traffic Source & SoftAP | Wi-Fi 802.11b/g/n (Ch 6) |
| **Receiver 1 (ESP32 #1)** | DOIT ESP32-WROOM-32 | HLK-LD2450 24 GHz FMCW Radar | Radar Target Tracking + Wi-Fi CSI Capture | UART2 (`RX2: GPIO 16`, `TX2: GPIO 17`, 256 kBaud) |
| **Receiver 2 (ESP32 #2)** | DOIT ESP32-WROOM-32 | MPU-9250 / AK8963 Magnetometer | 3-Axis Magnetic Anomaly + Wi-Fi RSSI Capture | I2C (`SDA: GPIO 21`, `SCL: GPIO 22`, 400 kHz) |
| **Host Workstation** | Laptop (Kali Linux or macOS) | FastAPI + WebSocket Broadcaster | Telemetry Ingestion, Calibration, Fusion & NewView UI | UDP `5005`, HTTP `8000`, WS `8000` |

> [!IMPORTANT]
> **Separation of Roles**: The HLK-LD2450 radar and NodeMCU traffic source are physically separate devices. The radar is attached directly to ESP32 #1 to prevent UART interference with Wi-Fi AP beacon generation.

---

## 2. Network Plan & Conflict-Free Addressing

All devices communicate over a dedicated **192.168.4.0/24** private Wi-Fi subnet created by the NodeMCU SoftAP.

### IP Allocation Table

| Device | Assigned IP | Gateway IP | Port(s) | Traffic Mode | Notes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **NodeMCU AP** | `192.168.4.1` | `192.168.4.1` | `4210` (UDP traffic) | SoftAP Mode | Broadcast beacon & unicast probe frames |
| **Host Workstation (Laptop)** | `192.168.4.2` | `192.168.4.1` | `5005` (UDP RX), `8000` (HTTP/WS) | Wi-Fi Station | Host machine running backend and NewView |
| **Receiver 1 (Radar Node)** | `192.168.4.10` | `192.168.4.1` | `5005` (UDP TX) | Wi-Fi Station + Promiscuous CSI | Fixed static IP; transmits radar frames |
| **Receiver 2 (Mag Node)** | `192.168.4.20` | `192.168.4.1` | `5005` (UDP TX) | Wi-Fi Station | Fixed static IP; transmits magnetic flux |

### Wireless Access Point Parameters
- **SSID:** `CSI_TEST`
- **Default Password:** `csi_sensing_pass` (Overridable via `.env` / `NEWVISION_AP_PASSWORD`)
- **Channel:** `6` (2.437 GHz, non-overlapping channel with standard AP spacing)
- **Security:** WPA2-PSK

> [!NOTE]
> The previous conflict where both the host laptop and Receiver 1 were assigned `192.168.4.2` is resolved. The laptop is strictly `192.168.4.2`, Receiver 1 is `192.168.4.10`, and Receiver 2 is `192.168.4.20`.

---

## 3. Wi-Fi Sensing & Radio Mode Realities

### Receiver 1 (ESP32 #1): Radar + Wi-Fi CSI
- Operates in Wi-Fi Station mode with active promiscuous packet monitoring for CSI collection (`esp_wifi_set_csi_rx_cb`).
- Captures raw 64-subcarrier OFDM channel frequency response for packet traffic transmitted by NodeMCU AP.
- Computes subcarrier amplitude variance as a channel disturbance metric:
  $$\sigma_{CSI}^2 = \frac{1}{N} \sum_{k=1}^N (|H_k| - \mu_{|H|})^2$$
- **Honest Sensing Disclosure:** Subcarrier variance indicates RF multipath perturbation caused by moving objects. It does **not** provide direct 3D human coordinates without multi-antenna beamforming arrays and calibrated spatial anchors.

### Receiver 2 (ESP32 #2): Magnetometer + RSSI
- Operates in Wi-Fi Station mode.
- Extracts per-packet RSSI (dBm) and computes rolling RSSI variance.
- Explicitly flagged as `RAW_RSSI_ONLY` (not full CSI) to prevent deceptive claims of subcarrier phase/amplitude capability when operating without raw CSI callbacks.

---

## 4. HLK-LD2450 Radar Specifications & Frame Format

The HLK-LD2450 millimeter-wave sensor operates at 24.00 – 24.25 GHz with a 30-byte UART target tracking frame at 256,000 baud:

```
[0xAA 0xFF 0x03 0x00] [Target 1: 8 bytes] [Target 2: 8 bytes] [Target 3: 8 bytes] [0x55 0xCC]
```

Each 8-byte target payload contains:
1. `Bytes 0-1`: X coordinate in millimeters (sign-magnitude 16-bit integer, bit 15 = sign, bits 0-14 = magnitude).
2. `Bytes 2-3`: Y coordinate in millimeters (sign-magnitude 16-bit integer).
3. `Bytes 4-5`: Radial speed in cm/s (sign-magnitude 16-bit integer; positive = moving away, negative = approaching).
4. `Bytes 6-7`: Distance resolution in millimeters.

### Tracking Filter & Coasting
NewVision implements an **Alpha-Beta Tracking Filter (`LD2450Tracker`)**:
- Position smoothing factor: $\alpha = 0.7$
- Velocity estimation factor: $\beta = 0.4$
- Association: Nearest-neighbor gating ($d_{gate} \le 1.2\text{ m}$)
- Coasting: Maintains track persistence across up to 5 consecutive missed frames ($\approx 250\text{ ms}$) to prevent target ID flickering.

---

## 5. Host Telemetry Protocol & Clock Synchronization

All nodes transmit structured JSON datagrams to the laptop's UDP port `5005`:

```json
{
  "device_id": "esp32_radar_csi",
  "role": "radar_csi",
  "fw_ver": "1.0.0",
  "seq": 14205,
  "uptime_ms": 354890,
  "free_heap": 184520,
  "errors": 0,
  "packet_rate_hz": 20.0,
  "rssi": -46,
  "csi_count": 8920,
  "radar": {
    "target_count": 1,
    "targets": [
      {
        "target_id": 1,
        "x_mm": 450,
        "y_mm": 2300,
        "x_m": 0.45,
        "y_m": 2.3,
        "distance_m": 2.34,
        "speed_cms": 32,
        "speed_ms": 0.32,
        "resolution_mm": 100,
        "is_valid": true
      }
    ]
  }
}
```

### Clock Skew Compensation
Because ESP32 microcontrollers lack battery-backed real-time clocks, NewVision computes clock offsets on receipt:
$$\Delta t_{offset} = t_{host\_mono} - \frac{t_{device\_uptime\_ms}}{1000}$$
Observations within a $\pm 100\text{ ms}$ window are aligned for multimodal fusion.

---

## 6. Firmware Flashing & Verification

### NodeMCU AP (ESP8266)
```bash
cd firmware/nodemcu_ap
pio run -t upload
pio device monitor -b 115200
```

### Receiver 1 (ESP32 Radar)
```bash
cd firmware/esp32_radar_csi
pio run -t upload
pio device monitor -b 115200
```

### Receiver 2 (ESP32 Magnetometer)
```bash
cd firmware/esp32_magnetometer_csi
pio run -t upload
pio device monitor -b 115200
```
