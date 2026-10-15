# NodeMCU ESP8266 — Wi-Fi Traffic Source

## Role in NewVision Architecture
The NodeMCU ESP8266 acts as the master Wi-Fi Access Point (AP) and predictable traffic generator. Both ESP32 receiver nodes connect to this AP, collecting Channel State Information (CSI) and Received Signal Strength Indication (RSSI) as packets pass through the physical sensing environment.

## Key Specifications
- **SoftAP SSID:** `CSI_TEST`
- **SoftAP IP:** `192.168.4.1`
- **Wi-Fi Channel:** 6 (fixed channel essential for repeatable CSI)
- **Traffic Port:** UDP `4210`
- **Packet Rate:** Configurable, default ~10ms interval (100 Hz)
- **Modes Supported:**
  - Round-robin unicast to both ESP32 receivers (`192.168.4.10` and `192.168.4.20`)
  - Subnet broadcast (`192.168.4.255`)
- **Telemetry Port:** UDP `5005` directed to laptop backend (`192.168.4.2`)

## Hardware Wiring
No external sensors are attached to the NodeMCU. Its role is dedicated solely to Wi-Fi traffic generation.
- Power: Micro-USB 5V / 1A.

## Flashing Instructions

### Using PlatformIO (macOS / Linux):
```bash
cd firmware/nodemcu_ap
pio run -t upload
pio device monitor -b 115200
```

### Using Arduino IDE:
1. Install **ESP8266 Boards** via Boards Manager.
2. Select Board: `NodeMCU 1.0 (ESP-12E Module)`.
3. Select CPU Frequency: `80 MHz` or `160 MHz`.
4. Select Port and click **Upload**.
