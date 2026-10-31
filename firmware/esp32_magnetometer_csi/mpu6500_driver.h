#ifndef MPU6500_DRIVER_H
#define MPU6500_DRIVER_H

#include <Arduino.h>
#include <Wire.h>

/**
 * Robust Hardware Driver for MPU-6500 6-Axis IMU (Accelerometer + Gyroscope)
 * Reuses existing I2C bus initialized by ESP32 #2.
 * 
 * Hardware Specs:
 * - Address: 0x68 (or 0x69)
 * - WHO_AM_I register (0x75): expects 0x70 for genuine MPU-6500
 * - Accelerometer: ±2 g (16384 LSB/g)
 * - Gyroscope: ±250 °/s (131 LSB/(°/s))
 * - Read burst: 14 bytes starting at 0x3B (ACCEL_XOUT_H)
 */

#define MPU6500_DEFAULT_ADDR 0x68
#define MPU6500_REG_XG_OFFS_TC 0x00
#define MPU6500_REG_GYRO_CONFIG 0x1B
#define MPU6500_REG_ACCEL_CONFIG 0x1C
#define MPU6500_REG_ACCEL_XOUT_H 0x3B
#define MPU6500_REG_PWR_MGMT_1 0x6B
#define MPU6500_REG_WHO_AM_I 0x75

#define MPU6500_EXPECTED_WHO_AM_I 0x70

struct IMUReading {
    float ax;          // In g (±2 g range)
    float ay;          // In g (±2 g range)
    float az;          // In g (±2 g range)
    float gx;          // In deg/s (±250 °/s range)
    float gy;          // In deg/s (±250 °/s range)
    float gz;          // In deg/s (±250 °/s range)
    bool is_valid;     // True only if successfully read and decoded
    uint32_t sample_seq;
    uint32_t timestamp_ms;
};

class MPU6500Driver {
private:
    uint8_t i2c_addr;
    bool is_available;
    uint8_t who_am_i;
    uint32_t sample_seq;
    uint32_t error_count;

    bool writeReg(uint8_t reg, uint8_t value) {
        Wire.beginTransmission(i2c_addr);
        Wire.write(reg);
        Wire.write(value);
        return (Wire.endTransmission() == 0);
    }

    bool readRegs(uint8_t start_reg, uint8_t *buffer, uint8_t length) {
        Wire.beginTransmission(i2c_addr);
        Wire.write(start_reg);
        if (Wire.endTransmission(false) != 0) {
            return false;
        }

        uint8_t received = Wire.requestFrom(i2c_addr, length);
        if (received != length) {
            while (Wire.available()) Wire.read();
            return false;
        }

        for (uint8_t i = 0; i < length; i++) {
            buffer[i] = Wire.read();
        }
        return true;
    }

    inline int16_t toInt16(uint8_t h, uint8_t l) {
        return (int16_t)(((uint16_t)h << 8) | l);
    }

public:
    MPU6500Driver() :
        i2c_addr(MPU6500_DEFAULT_ADDR),
        is_available(false),
        who_am_i(0),
        sample_seq(0),
        error_count(0) {}

    /**
     * Initialize MPU-6500 on existing I2C bus.
     * Checks WHO_AM_I identity and configures ±2g and ±250 deg/s.
     */
    bool init(uint8_t addr = MPU6500_DEFAULT_ADDR) {
        i2c_addr = addr;
        is_available = false;

        // 1. Check WHO_AM_I
        uint8_t id = 0;
        if (!readRegs(MPU6500_REG_WHO_AM_I, &id, 1)) {
            Serial.printf("[IMU_PROBE] MPU-6500 not responding at 0x%02X\n", i2c_addr);
            return false;
        }

        who_am_i = id;
        Serial.printf("[IMU_PROBE] MPU-6500 I2C 0x%02X responded with WHO_AM_I = 0x%02X\n", i2c_addr, who_am_i);

        if (who_am_i != MPU6500_EXPECTED_WHO_AM_I) {
            Serial.printf("[IMU_PROBE] WARNING: WHO_AM_I 0x%02X differs from expected 0x%02X (MPU-6500)\n",
                          who_am_i, MPU6500_EXPECTED_WHO_AM_I);
            // We still proceed if it's an MPU-6050/6500 derivative (e.g. 0x68, 0x71, 0x73) but note it
            if (who_am_i != 0x68 && who_am_i != 0x71 && who_am_i != 0x73) {
                return false;
            }
        }

        // 2. Wake sensor (clear sleep bit in PWR_MGMT_1)
        if (!writeReg(MPU6500_REG_PWR_MGMT_1, 0x00)) {
            Serial.println("[IMU_PROBE] ERROR: Failed to wake MPU-6500 from sleep.");
            return false;
        }
        delay(50);

        // 3. Configure Accelerometer to ±2 g (ACCEL_CONFIG = 0x00)
        // Sensitivity: 16384 LSB/g
        if (!writeReg(MPU6500_REG_ACCEL_CONFIG, 0x00)) {
            Serial.println("[IMU_PROBE] ERROR: Failed to configure ACCEL_CONFIG.");
            return false;
        }

        // 4. Configure Gyroscope to ±250 °/s (GYRO_CONFIG = 0x00)
        // Sensitivity: 131 LSB/(°/s)
        if (!writeReg(MPU6500_REG_GYRO_CONFIG, 0x00)) {
            Serial.println("[IMU_PROBE] ERROR: Failed to configure GYRO_CONFIG.");
            return false;
        }

        is_available = true;
        Serial.println("[IMU_PROBE] MPU-6500 IMU successfully initialized (±2 g, ±250 °/s).");
        return true;
    }

    /**
     * Read 6-axis raw registers and convert to standard units:
     * ax, ay, az in g (raw / 16384.0f)
     * gx, gy, gz in deg/s (raw / 131.0f)
     */
    IMUReading read() {
        IMUReading r = {0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, false, 0, 0};
        if (!is_available) {
            return r;
        }

        uint8_t data[14];
        if (!readRegs(MPU6500_REG_ACCEL_XOUT_H, data, 14)) {
            error_count++;
            return r; // is_valid remains false
        }

        int16_t axRaw = toInt16(data[0], data[1]);
        int16_t ayRaw = toInt16(data[2], data[3]);
        int16_t azRaw = toInt16(data[4], data[5]);
        // bytes 6-7 are temperature
        int16_t gxRaw = toInt16(data[8], data[9]);
        int16_t gyRaw = toInt16(data[10], data[11]);
        int16_t gzRaw = toInt16(data[12], data[13]);

        r.ax = (float)axRaw / 16384.0f;
        r.ay = (float)ayRaw / 16384.0f;
        r.az = (float)azRaw / 16384.0f;

        r.gx = (float)gxRaw / 131.0f;
        r.gy = (float)gyRaw / 131.0f;
        r.gz = (float)gzRaw / 131.0f;

        sample_seq++;
        r.sample_seq = sample_seq;
        r.timestamp_ms = millis();
        r.is_valid = true;

        return r;
    }

    bool isAvailable() const { return is_available; }
    uint8_t getWhoAmI() const { return who_am_i; }
    const char* getSensorName() const { return "MPU6500"; }
    uint32_t getErrorCount() const { return error_count; }
};

#endif // MPU6500_DRIVER_H
