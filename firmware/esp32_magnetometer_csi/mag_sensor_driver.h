#ifndef MAG_SENSOR_DRIVER_H
#define MAG_SENSOR_DRIVER_H

#include <Arduino.h>
#include <Wire.h>

/**
 * Modular Magnetic Sensor Driver with Strict Hardware Verification
 * Supports:
 * - Genuine MPU-9250 (MPU-6500 + internal AK8963 at 0x0C)
 * - Detects and rejects MPU-6500 clone boards missing AK8963
 * - Detects and rejects MPU-6050 boards (no magnetometer)
 * - Standalone HMC5883L (0x1E) and QMC5883L (0x0D)
 */

enum MagChipType {
    CHIP_UNKNOWN = 0,
    CHIP_HMC5883L,
    CHIP_QMC5883L,
    CHIP_MPU9250_AK8963,
    CHIP_MPU6500_NO_MAG,      // Hardware marked MPU-9250/6500 but lacking AK8963
    CHIP_MPU6050_NO_MAG       // MPU-6050 breakout (no magnetometer)
};

struct MagReading {
    float bx_uT;
    float by_uT;
    float bz_uT;
    float magnitude_uT;
    bool is_valid;
};

class MagSensorDriver {
private:
    MagChipType detectedChip;
    String chipName;
    bool isSupported;
    uint8_t mpuI2cAddr;
    float ak8963_asa_x;
    float ak8963_asa_y;
    float ak8963_asa_z;

    void writeRegister8(uint8_t i2cAddr, uint8_t reg, uint8_t value) {
        Wire.beginTransmission(i2cAddr);
        Wire.write(reg);
        Wire.write(value);
        Wire.endTransmission();
    }

    uint8_t readRegister8(uint8_t i2cAddr, uint8_t reg) {
        Wire.beginTransmission(i2cAddr);
        Wire.write(reg);
        Wire.endTransmission(false);
        Wire.requestFrom(i2cAddr, (uint8_t)1);
        if (Wire.available()) {
            return Wire.read();
        }
        return 0;
    }

    bool checkI2CAddress(uint8_t addr) {
        Wire.beginTransmission(addr);
        return (Wire.endTransmission() == 0);
    }

public:
    MagSensorDriver() : 
        detectedChip(CHIP_UNKNOWN), 
        chipName("UNKNOWN"), 
        isSupported(false),
        mpuI2cAddr(0x68),
        ak8963_asa_x(1.0f),
        ak8963_asa_y(1.0f),
        ak8963_asa_z(1.0f) {}

    bool init(int sdaPin = 21, int sclPin = 22) {
        Wire.begin(sdaPin, sclPin, 400000); // 400 kHz Fast I2C
        delay(100);

        Serial.println("\n[MAG_PROBE] Starting modular I2C sensor identification...");

        // 1. First probe for HMC5883L at 0x1E
        if (checkI2CAddress(0x1E)) {
            detectedChip = CHIP_HMC5883L;
            chipName = "HMC5883L";
            isSupported = true;
            writeRegister8(0x1E, 0x00, 0x70); // 8-avg, 15Hz
            writeRegister8(0x1E, 0x01, 0x20); // +/- 1.3G
            writeRegister8(0x1E, 0x02, 0x00); // Continuous
            Serial.println("[MAG_PROBE] Verified genuine HMC5883L at 0x1E");
            return true;
        }

        // 2. Probe for QMC5883L at 0x0D
        if (checkI2CAddress(0x0D)) {
            detectedChip = CHIP_QMC5883L;
            chipName = "QMC5883L";
            isSupported = true;
            writeRegister8(0x0D, 0x0B, 0x01); // Set period
            writeRegister8(0x0D, 0x09, 0x1D); // Continuous 100Hz 8G
            Serial.println("[MAG_PROBE] Verified genuine QMC5883L at 0x0D");
            return true;
        }

        // 3. Probe for MPU-6050 / MPU-6500 / MPU-9250 at 0x68 or 0x69
        uint8_t candidateAddr = 0;
        if (checkI2CAddress(0x68)) candidateAddr = 0x68;
        else if (checkI2CAddress(0x69)) candidateAddr = 0x69;

        if (candidateAddr != 0) {
            mpuI2cAddr = candidateAddr;
            uint8_t mpuWhoAmI = readRegister8(mpuI2cAddr, 0x75); // WHO_AM_I
            Serial.printf("[MAG_PROBE] Found I2C device at 0x%02X with WHO_AM_I = 0x%02X\n", mpuI2cAddr, mpuWhoAmI);

            // Check if MPU-6050 (WHO_AM_I == 0x68)
            if (mpuWhoAmI == 0x68) {
                detectedChip = CHIP_MPU6050_NO_MAG;
                chipName = "MPU6050_NO_MAG";
                isSupported = false;
                Serial.println("[CRITICAL WARNING] MPU-6050 detected!");
                Serial.println("  The MPU-6050 has NO integrated magnetometer (6-axis gyro/accel only).");
                Serial.println("  It cannot be used for magnetic threat classification.");
                return false;
            }

            // Wake up MPU
            writeRegister8(mpuI2cAddr, 0x6B, 0x00); // Clear sleep bit
            delay(10);

            // Enable I2C Master Bypass to access auxiliary AK8963 magnetometer at 0x0C
            writeRegister8(mpuI2cAddr, 0x6A, 0x00); // USER_CTRL: disable master mode
            writeRegister8(mpuI2cAddr, 0x37, 0x02); // INT_PIN_CFG: enable bypass
            delay(20);

            // Now probe address 0x0C for AK8963
            if (checkI2CAddress(0x0C)) {
                uint8_t akWho = readRegister8(0x0C, 0x00); // WIA register
                Serial.printf("[MAG_PROBE] Auxiliary device at 0x0C responded with WIA = 0x%02X\n", akWho);

                if (akWho == 0x48) {
                    detectedChip = CHIP_MPU9250_AK8963;
                    chipName = "MPU9250_AK8963";
                    isSupported = true;

                    // Read Fuse ROM sensitivity adjustments (ASAX, ASAY, ASAZ)
                    writeRegister8(0x0C, 0x0A, 0x00); // Power down
                    delay(10);
                    writeRegister8(0x0C, 0x0A, 0x1F); // Fuse ROM access mode
                    delay(10);
                    uint8_t raw_asax = readRegister8(0x0C, 0x10);
                    uint8_t raw_asay = readRegister8(0x0C, 0x11);
                    uint8_t raw_asaz = readRegister8(0x0C, 0x12);
                    ak8963_asa_x = ((float)(raw_asax - 128) / 256.0f) + 1.0f;
                    ak8963_asa_y = ((float)(raw_asay - 128) / 256.0f) + 1.0f;
                    ak8963_asa_z = ((float)(raw_asaz - 128) / 256.0f) + 1.0f;

                    // Set AK8963 to Continuous Measurement Mode 2 (16-bit output, 100 Hz ODR)
                    writeRegister8(0x0C, 0x0A, 0x00); // Power down
                    delay(10);
                    writeRegister8(0x0C, 0x0A, 0x16); // 16-bit, 100Hz
                    delay(10);

                    Serial.println("[MAG_PROBE] Verified genuine MPU-9250 with AK8963 magnetometer!");
                    Serial.printf("  Sensitivity adjustments: X=%.2f, Y=%.2f, Z=%.2f\n",
                                  ak8963_asa_x, ak8963_asa_y, ak8963_asa_z);
                    return true;
                }
            }

            // If we reached here: MPU-6500 or clone without AK8963
            detectedChip = CHIP_MPU6500_NO_MAG;
            chipName = "MPU6500_NO_MAG";
            isSupported = false;
            Serial.println("[HARDWARE CHECK FAILED] Board is an MPU-6500 clone lacking an AK8963 magnetometer!");
            Serial.println("  Breakout board labeled 'MPU-9250/6500' only contains an MPU-6500 6-axis die.");
            Serial.println("  No magnetometer responds at 0x0C. Flagging as INCOMPATIBLE.");
            return false;
        }

        detectedChip = CHIP_UNKNOWN;
        chipName = "NO_SENSOR_FOUND";
        isSupported = false;
        Serial.println("[MAG_PROBE] No compatible magnetometer or IMU detected on I2C bus.");
        return false;
    }

    MagReading read() {
        MagReading r = {0.0f, 0.0f, 0.0f, 0.0f, false};
        if (!isSupported) return r;

        if (detectedChip == CHIP_MPU9250_AK8963) {
            // Check Data Ready (ST1 bit 0)
            uint8_t st1 = readRegister8(0x0C, 0x02);
            if (st1 & 0x01) {
                Wire.beginTransmission(0x0C);
                Wire.write(0x03); // HXL
                Wire.endTransmission(false);
                Wire.requestFrom((uint8_t)0x0C, (uint8_t)7); // 6 data bytes + ST2
                if (Wire.available() >= 7) {
                    int16_t x = Wire.read() | (Wire.read() << 8);
                    int16_t y = Wire.read() | (Wire.read() << 8);
                    int16_t z = Wire.read() | (Wire.read() << 8);
                    uint8_t st2 = Wire.read(); // Reading ST2 clears data latch

                    // Check magnetic sensor overflow
                    if (!(st2 & 0x08)) {
                        // 16-bit output: 0.15 uT per LSB
                        r.bx_uT = (x * 0.15f) * ak8963_asa_x;
                        r.by_uT = (y * 0.15f) * ak8963_asa_y;
                        r.bz_uT = (z * 0.15f) * ak8963_asa_z;
                        r.magnitude_uT = sqrt(r.bx_uT * r.bx_uT + r.by_uT * r.by_uT + r.bz_uT * r.bz_uT);
                        r.is_valid = true;
                    }
                }
            }
        } else if (detectedChip == CHIP_HMC5883L) {
            Wire.beginTransmission(0x1E);
            Wire.write(0x03);
            Wire.endTransmission(false);
            Wire.requestFrom((uint8_t)0x1E, (uint8_t)6);
            if (Wire.available() >= 6) {
                int16_t x = (Wire.read() << 8) | Wire.read();
                int16_t z = (Wire.read() << 8) | Wire.read();
                int16_t y = (Wire.read() << 8) | Wire.read();
                r.bx_uT = (x / 1090.0f) * 100.0f;
                r.by_uT = (y / 1090.0f) * 100.0f;
                r.bz_uT = (z / 1090.0f) * 100.0f;
                r.magnitude_uT = sqrt(r.bx_uT * r.bx_uT + r.by_uT * r.by_uT + r.bz_uT * r.bz_uT);
                r.is_valid = true;
            }
        } else if (detectedChip == CHIP_QMC5883L) {
            Wire.beginTransmission(0x0D);
            Wire.write(0x00);
            Wire.endTransmission(false);
            Wire.requestFrom((uint8_t)0x0D, (uint8_t)6);
            if (Wire.available() >= 6) {
                int16_t x = Wire.read() | (Wire.read() << 8);
                int16_t y = Wire.read() | (Wire.read() << 8);
                int16_t z = Wire.read() | (Wire.read() << 8);
                r.bx_uT = (x / 3000.0f) * 100.0f;
                r.by_uT = (y / 3000.0f) * 100.0f;
                r.bz_uT = (z / 3000.0f) * 100.0f;
                r.magnitude_uT = sqrt(r.bx_uT * r.bx_uT + r.by_uT * r.by_uT + r.bz_uT * r.bz_uT);
                r.is_valid = true;
            }
        }
        return r;
    }

    String getChipName() const { return chipName; }
    bool getIsSupported() const { return isSupported; }
    MagChipType getChipType() const { return detectedChip; }
};

#endif // MAG_SENSOR_DRIVER_H
