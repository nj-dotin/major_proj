# ESP32 #1 — Radar Tracking and Wi-Fi Sensing

## Hardware Setup
- **MCU:** Classic ESP32-WROOM-32
- **Radar Module:** HLK-LD2450 24 GHz Millimeter-Wave Motion Tracking Radar

## Pin Connections
| ESP32 Pin | LD2450 Pin | Function | Notes |
| :--- | :--- | :--- | :--- |
| **5V / VIN** | **VCC** | Power | LD2450 requires 5V supply (>200mA) |
| **GND** | **GND** | Ground | Common system ground |
| **GPIO 16 (RX2)**| **TX** | Radar Data | Receives 256,000 baud UART stream |
| **GPIO 17 (TX2)**| **RX** | Radar Config | Optional command interface |

## Protocol Details
- Standard LD2450 UART frame: 30 bytes at 256,000 bps
- Header: `0xAA 0xFF 0x03 0x00`
- 3 target slots (8 bytes each): lateral X (mm), longitudinal distance Y (mm), radial speed (cm/s), resolution gate
- Tail: `0x55 0xCC`

## Wi-Fi CSI Handling
- Connects to `CSI_TEST` AP (`192.168.4.10`).
- CSI receive callback pushes packet descriptors to a dedicated FreeRTOS Queue.
- Processing occurs safely outside the Wi-Fi interrupt context to maintain sub-millisecond execution.

## Flashing Instructions
```bash
cd firmware/esp32_radar_csi
pio run -t upload
pio device monitor -b 115200
```
