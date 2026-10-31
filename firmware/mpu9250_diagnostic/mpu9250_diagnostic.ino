
#include <Arduino.h>
#include <Wire.h>

#define MPU_ADDR       0x68
#define WHO_AM_I_REG   0x75
#define PWR_MGMT_1     0x6B
#define ACCEL_CONFIG   0x1C
#define GYRO_CONFIG    0x1B
#define ACCEL_XOUT_H   0x3B

bool writeRegister(uint8_t reg, uint8_t value) {
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(reg);
  Wire.write(value);
  return Wire.endTransmission() == 0;
}

bool readRegisters(uint8_t reg, uint8_t *data, uint8_t len) {
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(reg);

  if (Wire.endTransmission(false) != 0) {
    return false;
  }

  uint8_t received = Wire.requestFrom(MPU_ADDR, len);
  if (received != len) {
    while (Wire.available()) Wire.read();
    return false;
  }

  for (uint8_t i = 0; i < len; i++) {
    data[i] = Wire.read();
  }

  return true;
}

int16_t toInt16(uint8_t highByte, uint8_t lowByte) {
  return (int16_t)((uint16_t)highByte << 8 | lowByte);
}

void setup() {
  Serial.begin(115200);
  delay(1000);

  Wire.begin(21, 22, 100000);
  Wire.setTimeOut(100);

  Serial.println("\n==================================");
  Serial.println(" NEWVISION MPU-6500 DIAGNOSTIC");
  Serial.println("==================================");

  uint8_t identity = 0;

  if (!readRegisters(WHO_AM_I_REG, &identity, 1)) {
    Serial.println("[ERROR] Cannot read WHO_AM_I.");
    Serial.println("Check wiring and I2C address.");
    return;
  }

  Serial.printf("[INFO] I2C address: 0x%02X\n", MPU_ADDR);
  Serial.printf("[INFO] WHO_AM_I: 0x%02X\n", identity);

  if (identity != 0x70) {
    Serial.println("[WARNING] Identity differs from expected MPU-6500.");
  }

  // Wake the sensor.
  if (!writeRegister(PWR_MGMT_1, 0x00)) {
    Serial.println("[ERROR] Failed to wake sensor.");
    return;
  }

  delay(100);

  // Configure accelerometer: +/- 2 g.
  writeRegister(ACCEL_CONFIG, 0x00);

  // Configure gyroscope: +/- 250 degrees/second.
  writeRegister(GYRO_CONFIG, 0x00);

  Serial.println("[INFO] Sensor initialized.");
  Serial.println("[INFO] Keep still, then move/rotate the board.");
  Serial.println("AX(g), AY(g), AZ(g) | GX, GY, GZ(deg/s)");
  Serial.println("----------------------------------------------");
}

void loop() {
  uint8_t data[14];

  if (!readRegisters(ACCEL_XOUT_H, data, 14)) {
    Serial.println("[ERROR] Failed to read sensor data.");
    delay(500);
    return;
  }

  int16_t axRaw = toInt16(data[0], data[1]);
  int16_t ayRaw = toInt16(data[2], data[3]);
  int16_t azRaw = toInt16(data[4], data[5]);

  int16_t gxRaw = toInt16(data[8], data[9]);
  int16_t gyRaw = toInt16(data[10], data[11]);
  int16_t gzRaw = toInt16(data[12], data[13]);

  // Default ranges: +/- 2 g and +/- 250 degrees/second.
  float ax = axRaw / 16384.0f;
  float ay = ayRaw / 16384.0f;
  float az = azRaw / 16384.0f;

  float gx = gxRaw / 131.0f;
  float gy = gyRaw / 131.0f;
  float gz = gzRaw / 131.0f;

  Serial.printf(
    "A: %7.3f %7.3f %7.3f g | "
    "G: %7.2f %7.2f %7.2f deg/s\n",
    ax, ay, az, gx, gy, gz
  );

  delay(200);
}
