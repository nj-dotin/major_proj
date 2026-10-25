/**
 * NewVision GPIO16 Hardware Isolation Diagnostic
 * 
 * Purpose:
 * Tests the electrical state of ESP32 GPIO16 as a standard digital INPUT_PULLUP.
 * 
 * Constraints:
 * - UART2 is NOT initialized.
 * - No hardware interrupts or ISRs.
 * - No Wi-Fi, CSI, or parser code.
 * - Reads and prints the pin logic level once per second.
 */

#include <Arduino.h>

#define TARGET_PIN 16

void setup() {
    Serial.begin(115200);
    delay(1000);

    Serial.println("\n=======================================================");
    Serial.println("  NEWVISION — ESP32 GPIO16 DIGITAL INPUT_PULLUP TEST   ");
    Serial.println("=======================================================");

    // Configure GPIO16 strictly as a digital input with internal pull-up
    pinMode(TARGET_PIN, INPUT_PULLUP);

    Serial.printf("[SETUP] GPIO%d configured as INPUT_PULLUP.\n", TARGET_PIN);
    Serial.println("[SETUP] Reading pin level once per second.\n");
}

void loop() {
    static unsigned long lastCheck = 0;
    static uint32_t sampleIndex = 0;

    unsigned long now = millis();
    if (now - lastCheck >= 1000) {
        lastCheck = now;
        sampleIndex++;

        int pinState = digitalRead(TARGET_PIN);

        Serial.printf("[SAMPLE #%04lu | uptime: %6.1fs] GPIO%d Level: %s (%d)\n",
                      sampleIndex, now / 1000.0, TARGET_PIN,
                      (pinState == HIGH) ? "HIGH" : "LOW ", pinState);
    }
}
