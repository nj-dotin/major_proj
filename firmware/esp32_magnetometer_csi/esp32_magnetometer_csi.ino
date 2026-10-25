/**
 * NewVision Firmware: ESP32 #2 Magnetometer Sensing & Wi-Fi CSI
 * 
 * Hardware:
 * - ESP32-WROOM
 * - Magnetometer Module on I2C (SDA: GPIO 21, SCL: GPIO 22)
 *   Supports HMC5883L, QMC5883L, MPU-9250 (AK8963).
 *   Explicitly warns and halts if MPU-6050 (no mag) is detected!
 * 
 * Responsibilities:
 * - Connects to NodeMCU AP "CSI_TEST" (Static IP: 192.168.4.20)
 * - Captures Wi-Fi CSI outside callback via FreeRTOS queue
 * - Measures 3-axis magnetic flux (Bx, By, Bz in microTesla)
 * - Streams structured telemetry to backend laptop over UDP (Port 5005)
 */

#include <WiFi.h>
#include <WiFiUdp.h>
#include "esp_wifi.h"
#include "mag_sensor_driver.h"

// ── Configuration ────────────────────────────────────────────────────────────
const char* AP_SSID         = "CSI_TEST";
const char* AP_PASSWORD     = "csi_sensing_pass";
const IPAddress LOCAL_IP(192, 168, 4, 20);
const IPAddress GATEWAY(192, 168, 4, 1);
const IPAddress SUBNET(255, 255, 255, 0);

const IPAddress BACKEND_IP(192, 168, 4, 100);
const uint16_t  BACKEND_UDP_PORT = 5005;

#define I2C_SDA_PIN 21
#define I2C_SCL_PIN 22

// ── CSI Queue & Metrics ──────────────────────────────────────────────────────
#define CSI_SAMPLE_COUNT 16
struct CSIMetadata {
    int8_t rssi;
    uint32_t timestamp;
    uint16_t subcarrier_count;
    uint8_t amplitudes[CSI_SAMPLE_COUNT];
};

QueueHandle_t csiQueue;
volatile uint32_t csiPacketCount = 0;
int lastRssi = -50;
uint8_t latestSubcarriers[CSI_SAMPLE_COUNT] = {0};
bool hasSubcarrierData = false;

void IRAM_ATTR wifi_csi_rx_callback(void* ctx, wifi_csi_info_t* data) {
    if (!data || !data->buf || data->len < 32) return;
    csiPacketCount = csiPacketCount + 1;

    CSIMetadata meta;
    meta.rssi = data->rx_ctrl.rssi;
    meta.timestamp = millis();
    meta.subcarrier_count = data->len;

    // Subcarrier magnitude sampling across packet bandwidth
    int total_sc = data->len / 2;
    int step = total_sc / CSI_SAMPLE_COUNT;
    if (step < 1) step = 1;

    for (int i = 0; i < CSI_SAMPLE_COUNT; i++) {
        int idx = i * step * 2;
        if (idx + 1 < data->len) {
            int8_t im = data->buf[idx];
            int8_t re = data->buf[idx + 1];
            int aim = (im < 0) ? -im : im;
            int are = (re < 0) ? -re : re;
            int amp = (aim > are) ? (aim + (are >> 1)) : (are + (aim >> 1));
            meta.amplitudes[i] = (uint8_t)(amp > 255 ? 255 : amp);
        } else {
            meta.amplitudes[i] = 0;
        }
    }

    BaseType_t xHigherPriorityTaskWoken = pdFALSE;
    xQueueSendFromISR(csiQueue, &meta, &xHigherPriorityTaskWoken);
    if (xHigherPriorityTaskWoken) {
        portYIELD_FROM_ISR();
    }
}

// ── Globals ──────────────────────────────────────────────────────────────────
WiFiUDP udp;
MagSensorDriver magDriver;
unsigned long lastTelemetrySent = 0;
unsigned long seqNum = 0;
const unsigned long TELEMETRY_INTERVAL_MS = 50; // 20 Hz telemetry

void setup() {
    Serial.begin(115200);
    delay(500);

    Serial.println("\n==================================================");
    Serial.println("  NEWVISION — ESP32 #2 MAGNETOMETER & CSI NODE    ");
    Serial.println("==================================================");

    // Initialize Magnetometer I2C
    bool sensorOk = magDriver.init(I2C_SDA_PIN, I2C_SCL_PIN);
    Serial.printf("[SENSOR] Detected Chip: %s | Supported: %s | Init: %s\n",
                  magDriver.getChipName().c_str(),
                  magDriver.getIsSupported() ? "YES" : "NO (INCOMPATIBLE)",
                  sensorOk ? "SUCCESS" : "WARNING");

    // Initialize CSI Queue
    csiQueue = xQueueCreate(32, sizeof(CSIMetadata));

    // Connect to Wi-Fi SoftAP
    WiFi.mode(WIFI_STA);
    WiFi.config(LOCAL_IP, GATEWAY, SUBNET);
    WiFi.begin(AP_SSID, AP_PASSWORD);

    Serial.printf("[WIFI] Connecting to AP '%s'...", AP_SSID);
    int retries = 0;
    while (WiFi.status() != WL_CONNECTED && retries < 20) {
        delay(500);
        Serial.print(".");
        retries++;
    }

    if (WiFi.status() == WL_CONNECTED) {
        Serial.printf("\n[WIFI] Connected! Assigned IP: %s\n", WiFi.localIP().toString().c_str());

        // Configure CSI
        wifi_csi_config_t csi_config = {
            .lltf_en = true,
            .htltf_en = true,
            .stbc_htltf2_en = true,
            .ltf_merge_en = true,
            .channel_filter_en = true,
            .manu_scale = false,
            .shift = false
        };
        esp_wifi_set_csi_config(&csi_config);
        esp_wifi_set_csi_rx_cb(wifi_csi_rx_callback, NULL);
        esp_wifi_set_csi(true);
        Serial.println("[CSI] Hardware CSI capture callback registered.");
    } else {
        Serial.println("\n[WIFI] Warning: AP not found. Running in standalone mode.");
    }

    udp.begin(LOCAL_IP, 5005);
}

void loop() {
    // 1. Drain CSI Queue
    CSIMetadata csiData;
    while (xQueueReceive(csiQueue, &csiData, 0) == pdTRUE) {
        lastRssi = csiData.rssi;
        for (int i = 0; i < CSI_SAMPLE_COUNT; i++) {
            latestSubcarriers[i] = csiData.amplitudes[i];
        }
        hasSubcarrierData = true;
    }

    // 2. Dispatch Telemetry at 20 Hz
    unsigned long now = millis();
    if (now - lastTelemetrySent >= TELEMETRY_INTERVAL_MS) {
        lastTelemetrySent = now;
        seqNum++;

        MagReading mag = magDriver.read();

        // Format subcarrier amplitudes string
        char scJson[160];
        if (hasSubcarrierData) {
            int scLen = snprintf(scJson, sizeof(scJson),
                "[%u,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u]",
                latestSubcarriers[0], latestSubcarriers[1], latestSubcarriers[2], latestSubcarriers[3],
                latestSubcarriers[4], latestSubcarriers[5], latestSubcarriers[6], latestSubcarriers[7],
                latestSubcarriers[8], latestSubcarriers[9], latestSubcarriers[10], latestSubcarriers[11],
                latestSubcarriers[12], latestSubcarriers[13], latestSubcarriers[14], latestSubcarriers[15]
            );
            if (scLen <= 0 || scLen >= (int)sizeof(scJson)) {
                snprintf(scJson, sizeof(scJson), "[]");
            }
        } else {
            snprintf(scJson, sizeof(scJson), "[]");
        }

        char jsonPacket[512];
        int ret = snprintf(jsonPacket, sizeof(jsonPacket),
            "{\"device_id\":\"esp32_mag_csi\",\"fw_ver\":\"1.0.0\",\"uptime_ms\":%lu,\"seq\":%lu,"
            "\"free_heap\":%u,\"rssi\":%d,\"csi_count\":%lu,\"subcarriers\":%s,\"packet_rate_hz\":20.0,"
            "\"chip\":\"%s\",\"supported\":%s,\"bx\":%.2f,\"by\":%.2f,\"bz\":%.2f,\"unit\":\"uT\"}",
            now, seqNum, (unsigned)ESP.getFreeHeap(), lastRssi, csiPacketCount, scJson,
            magDriver.getChipName().c_str(),
            magDriver.getIsSupported() ? "true" : "false",
            mag.bx_uT, mag.by_uT, mag.bz_uT
        );

        if (ret > 0 && ret < (int)sizeof(jsonPacket)) {
            udp.beginPacket(BACKEND_IP, BACKEND_UDP_PORT);
            udp.write((const uint8_t*)jsonPacket, ret);
            udp.endPacket();
        }
    }
}
