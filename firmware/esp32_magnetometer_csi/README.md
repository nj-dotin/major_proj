# ESP32 #2 — Magnetometer and Wi-Fi Sensing

## Hardware Setup
- **MCU:** Classic ESP32-WROOM-32
- **Sensor:** Magnetometer module (HMC5883L, QMC5883L, or MPU-9250 with internal AK8963).

### CRITICAL HARDWARE VERIFICATION: MPU-9250 vs MPU-6050
> **IMPORTANT:** Check the exact chip marking with a magnifying glass or microscope before testing!
> The **MPU-6050** contains only a 3-axis accelerometer and 3-axis gyroscope. **It has NO integrated magnetometer.**
> If an MPU-6050 is connected, the firmware automatically detects WHO_AM_I = 0x68 and reports `MPU6050_NO_MAG` with `supported: false`. The NewVision backend will explicitly mark the sensor as `INCOMPATIBLE` rather than reporting dummy magnetic fields.
> For magnetic threat classification, use a genuine **HMC5883L** (0x1E), **QMC5883L** (0x0D), or **MPU-9250** (0x68 + 0x0C).

## Pin Connections
| ESP32 Pin | Sensor Module Pin | Function |
| :--- | :--- | :--- |
| **3V3** | **VCC** | 3.3V Power |
| **GND** | **GND** | Ground |
| **GPIO 21** | **SDA** | I2C Data line (with 4.7kΩ pull-up) |
| **GPIO 22** | **SCL** | I2C Clock line (with 4.7kΩ pull-up) |

## Flashing Instructions
```bash
cd firmware/esp32_magnetometer_csi
pio run -t upload
pio device monitor -b 115200
```
