# NewVision — Multimodal Wi-Fi Sensing, Radar Tracking & MTC-1

**NewVision** is a local-first, cross-platform engineering prototype for through-wall multimodal sensing, human tracking, and magnetic anomaly detection. It operates on both **macOS** and **Linux (including Kali Linux)**.

---

## 1. System Architecture

```
                    ┌──────────────────────────────────────────────┐
                    │          NodeMCU ESP8266 Access Point        │
                    │   SSID: CSI_TEST  |  Ch: 6  | 192.168.4.1   │
                    │  Predictable UDP Traffic Generation (~100Hz) │
                    └──────────────────────┬───────────────────────┘
                                           │ Wi-Fi Packets (CSI Source)
                    ┌──────────────────────┴───────────────────────┐
                    ▼                                              ▼
┌───────────────────────────────────────┐      ┌───────────────────────────────────────┐
│     ESP32 Node #1: Radar + CSI        │      │    ESP32 Node #2: Mag + CSI + MTC-1   │
│  - HLK-LD2450 24GHz mmWave Radar      │      │  - HMC5883L / QMC5883L / MPU-9250     │
│  - Non-blocking CSI Callback & Queue  │      │  - Non-blocking CSI Callback & Queue  │
│  - 256k Baud UART2 (GPIO 16/17)       │      │  - I2C (GPIO 21/22) @ 400kHz          │
│  - Target Extraction (X, Y, Speed)    │      │  - Baseline Zeroing & Anomaly (Bx,By,Bz)│
└───────────────────┬───────────────────┘      └───────────────────┬───────────────────┘
                    │ UDP Telemetry (Port 5005)                    │ UDP Telemetry (Port 5005)
                    └──────────────────────┬───────────────────────┘
                                           │
                                           ▼
                    ┌──────────────────────────────────────────────┐
                    │          NewVision FastAPI Backend           │
                    │  - Async UDP Ingestion Server (Port 5005)    │
                    │  - Telemetry Buffer & CSV/JSON Recorder      │
                    │  - MTC-1 Scikit-Learn Model Pipeline         │
                    │  - Explainable Multimodal Sensor Fusion      │
                    │  - Real-time WebSockets @ 20 Hz (/ws)        │
                    └──────────────────────┬───────────────────────┘
                                           │ WebSockets & REST API
                                           ▼
                    ┌──────────────────────────────────────────────┐
                    │       Tactical 2D Operator Dashboard         │
                    │  - 2D Canvas Radar Sweep & Velocity Vectors  │
                    │  - Dual-Node Wi-Fi RSSI & CSI Waveforms      │
                    │  - 3-Axis Magnetic Waveform & ΔB Gauge       │
                    │  - Transparent Multi-Sensor Fusion Matrix    │
                    │  - Demo Simulator vs Live Hardware Toggle    │
                    └──────────────────────────────────────────────┘
```

---

## 2. Hardware Roles & Connection Diagrams

### NodeMCU ESP8266 — Wi-Fi Traffic Source
- **Role:** Generates regular, unfragmented Wi-Fi traffic so ESP32 receiver nodes can measure CSI and RSSI distortions caused by physical movement.
- **Power:** Micro-USB 5V / 1A.
- **Wiring:** No external sensors attached.

### ESP32 #1 — Radar Tracking and Wi-Fi Sensing
- **MCU:** Classic ESP32-WROOM-32
- **Radar Module:** HLK-LD2450 24 GHz Millimeter-Wave Radar

| ESP32-WROOM Pin | HLK-LD2450 Radar Pin | Function | Notes |
| :--- | :--- | :--- | :--- |
| **5V / VIN** | **VCC** | Power Input | Requires 5V supply (>200mA peak) |
| **GND** | **GND** | Ground | Common ground |
| **GPIO 16 (RX2)** | **TX** | Radar Data Out | Receives 256,000 baud binary frames |
| **GPIO 17 (TX2)** | **RX** | Radar Config In| Module command interface |

### ESP32 #2 — Magnetometer, MTC-1 & Wi-Fi Sensing
- **MCU:** Classic ESP32-WROOM-32
- **Sensor:** HMC5883L / QMC5883L / MPU-9250 3-Axis Magnetometer

| ESP32-WROOM Pin | Sensor Module Pin | Function | Notes |
| :--- | :--- | :--- | :--- |
| **3V3** | **VCC** | 3.3V Power | Clean 3.3V power |
| **GND** | **GND** | Ground | Common ground |
| **GPIO 21** | **SDA** | I2C Data | 400 kHz Fast-Mode I2C |
| **GPIO 22** | **SCL** | I2C Clock | 400 kHz Fast-Mode I2C |

> [!WARNING]
> **CRITICAL HARDWARE VERIFICATION: MPU-9250 vs MPU-6050**
> The **MPU-6050 has NO integrated magnetometer** (only 3-axis gyro + 3-axis accel).
> The firmware includes auto-detection: if WHO_AM_I returns `0x68` without an internal AK8963 magnetometer, it reports `MPU6050_NO_MAG` as **INCOMPATIBLE**.
> Always use genuine **HMC5883L** (`0x1E`), **QMC5883L** (`0x0D`), or **MPU-9250** (`0x68` + `0x0C`).

---

## 3. Network Architecture & IP Configuration

All nodes and the laptop communicate over the dedicated subnet `192.168.4.0/24`:

| Device | Role | IP Address | MAC / Interface | Ports Used |
| :--- | :--- | :--- | :--- | :--- |
| **NodeMCU ESP8266** | SoftAP Gateway | `192.168.4.1` | AP `CSI_TEST` | UDP 4210 (Traffic) |
| **Laptop (Host)** | Dashboard & Backend | `192.168.4.2` | Wi-Fi Station | UDP 5005 (Ingest), HTTP 8000 |
| **ESP32 #1** | Radar + CSI | `192.168.4.10` | Wi-Fi Station | UDP 5005 (Telemetry) |
| **ESP32 #2** | Magnetometer + CSI | `192.168.4.20` | Wi-Fi Station | UDP 5005 (Telemetry) |

### Setting Up Laptop Network
When testing with physical hardware:
1. Connect your laptop to the Wi-Fi network `CSI_TEST` (Password: `csi_sensing_pass`).
2. Verify or assign your laptop IP to `192.168.4.2` (or adjust `NEWVISION_LAPTOP_IP` in `.env`).

---

## 4. Software Installation & Setup

### Prerequisites
- Python 3.11+
- `uv` (recommended) or standard `pip`

```bash
# 1. Clone or enter the repository
cd /path/to/major_proj

# 2. Create virtual environment and install dependencies
uv venv --python 3.11 .venv
source .venv/bin/activate
uv pip install -r requirements.txt
# (or: pip install fastapi uvicorn websockets pydantic scikit-learn pandas matplotlib httpx pytest)
```

---

## 5. Running the Application

### A. Demo Mode (No Hardware Required)
Test all features, radar sweeps, Wi-Fi waveforms, magnetic baseline deviations, and MTC-1 inference immediately on your Mac or Linux laptop:

```bash
# Activate virtual environment
source .venv/bin/activate

# Run NewVision backend server
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

Open your browser to:
👉 **`http://localhost:8000`**

- The dashboard starts in **`DEMO / SIMULATED DATA`** mode.
- Use the **Simulate Object** dropdown in the header to simulate different threat signatures (`Handgun`, `Knife`, `Rifle`, `Tool`, `Clear`).
- Click **Zero Magnetometer** to recalibrate baseline.
- Click **Record Session** to capture live data, then **Export CSV** or **Export JSON**.

### B. Live Hardware Mode
When ready to connect real ESP32 / NodeMCU hardware:
1. Flash the firmware onto the three boards (see Section 6).
2. Connect your laptop to `CSI_TEST` Wi-Fi AP.
3. Start the backend:
   ```bash
   python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
   ```
4. On the dashboard header, click **`Mode: SIMULATED`** to switch to **`📡 Mode: LIVE HARDWARE`**.
5. The dashboard now displays live millimeter-wave radar pings, real magnetometer I2C readings, and real Wi-Fi RSSI.

---

## 6. Firmware Build & Flash Instructions

Each board has a dedicated configuration inside `firmware/`:

### 1. NodeMCU AP (`firmware/nodemcu_ap`)
```bash
cd firmware/nodemcu_ap
pio run -t upload
pio device monitor -b 115200
```

### 2. ESP32 Radar + CSI (`firmware/esp32_radar_csi`)
```bash
cd firmware/esp32_radar_csi
pio run -t upload
pio device monitor -b 115200
```

### 3. ESP32 Magnetometer + CSI (`firmware/esp32_magnetometer_csi`)
```bash
cd firmware/esp32_magnetometer_csi
pio run -t upload
pio device monitor -b 115200
```

---

## 7. REST & WebSocket API Reference

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/api/health` | `GET` | System operational state, MTC-1 model status, buffer size |
| `/api/telemetry` | `GET` | Snapshot of current consolidated multi-modal telemetry |
| `/api/mode/toggle` | `POST` | Toggle between `DEMO / SIMULATED` and `LIVE HARDWARE` |
| `/api/simulator/object` | `POST` | Change demo threat object (`handgun`, `knife`, `rifle`, etc.) |
| `/api/magnetometer/calibrate` | `POST` | Trigger zeroing / baseline calibration |
| `/api/session/start` | `POST` | Begin recording telemetry buffer |
| `/api/session/stop` | `POST` | Stop recording and return statistics |
| `/api/session/export/json` | `GET` | Download recorded session as JSON file |
| `/api/session/export/csv` | `GET` | Download recorded session as CSV file |
| `/api/telemetry/ingest` | `POST` | HTTP ingestion fallback for microcontrollers |
| `/ws/telemetry` | `WS` | 20 Hz real-time WebSocket push stream |

---

## 8. Preserved MTC-1 Legacy Application

The original Phase 1 Flask MTC-1 implementation is preserved 100% intact:
```bash
# Run legacy Flask app
python src/app.py
# Open: http://localhost:5000
```

---

## 9. Current Limitations & Honest Sensing Disclosures

1. **Radar vs CSI Coordinates:** Only the HLK-LD2450 millimeter-wave radar provides genuine Cartesian coordinates $(X, Y)$ and radial velocity. Wi-Fi CSI subcarrier amplitude variance is a motion/activity heuristic and cannot localize humans without calibrated spatial anchors.
2. **Synthetic MTC-1 Model:** The Random Forest classifier was trained on synthetic dipole equations with Gaussian noise. On live hardware, it is labeled `EXPERIMENTAL SYNTHETIC MODEL — NOT VALIDATED ON LIVE WEAPONS`.
3. **Range Dependency:** Dipole gradient $\Delta B / \Delta r$ requires knowing distance $r$. In NewVision, this distance is dynamically supplied by the LD2450 radar range measurement. If no range is available, the system reports `AWAITING_RANGE`.
4. **CSI Baseline Accuracy:** In prior held-out window testing, raw CSI classification reached only 38.88% accuracy. NewVision does not claim validated CSI human identification.

---

## 10. Automated Tests

Run the comprehensive test suite (29 tests):
```bash
.venv/bin/pytest tests/ -v
```
Tests cover:
- Pydantic Telemetry Schemas
- LD2450 30-byte UART binary decoding & sign-magnitude arithmetic
- Magnetometer zeroing & MPU-6050 incompatibility detection
- MTC-1 inference wrapper and safety guardrails
- Multimodal Sensor Fusion logic under partial and stale stream conditions
- FastAPI REST endpoints, WebSocket streaming, and CSV/JSON export
