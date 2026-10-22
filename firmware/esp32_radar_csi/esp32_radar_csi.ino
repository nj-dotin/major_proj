/**
 * NewVision Firmware: ESP32 #1 Radar Tracking & Wi-Fi CSI Sensing
 * 
 * Hardware:
 * - ESP32-WROOM
 * - HLK-LD2450 24 GHz Millimeter-Wave Radar on UART2 (RX2: GPIO 16, TX2: GPIO 17, Baud: 256,000)
 * 
 * Responsibilities:
 * - Connects to NodeMCU AP "CSI_TEST"
 * - Collects Wi-Fi CSI with non-blocking FreeRTOS queue
 * - Parses HLK-LD2450 target coordinates, speed, and status with bounds-safe framing
 * - Streams structured telemetry to backend laptop over UDP (Port 5005)
 */

#include <WiFi.h>
#include <WiFiUdp.h>
#include "esp_wifi.h"
#include "ld2450_driver.h"

// ── Configuration ────────────────────────────────────────────────────────────
const char* AP_SSID         = "CSI_TEST";
const char* AP_PASSWORD     = "csi_sensing_pass";
const IPAddress LOCAL_IP(192, 168, 4, 10);
const IPAddress GATEWAY(192, 168, 4, 1);
const IPAddress SUBNET(255, 255, 255, 0);

const IPAddress BACKEND_IP(192, 168, 4, 2);
const uint16_t  BACKEND_UDP_PORT = 5005;

// UART2 for LD2450 Radar
#define RADAR_RX_PIN 16
#define RADAR_TX_PIN 17
#define RADAR_BAUD   256000

// ── CSI Queue & Metrics ──────────────────────────────────────────────────────
struct CSIMetadata {
    int8_t rssi;
    uint32_t timestamp;
    uint8_t subcarrier_count;
};

QueueHandle_t csiQueue;
volatile uint32_t csiPacketCount = 0;
int lastRssi = -50;

// CSI Receive Callback (Must remain extremely fast and non-blocking!)
void IRAM_ATTR wifi_csi_rx_callback(void* ctx, wifi_csi_info_t* data) {
    if (!data || !data->buf) return;
    csiPacketCount++;

    CSIMetadata meta;
    meta.rssi = data->rx_ctrl.rssi;
    meta.timestamp = millis();
    meta.subcarrier_count = data->len;

    BaseType_t xHigherPriorityTaskWoken = pdFALSE;
    xQueueSendFromISR(csiQueue, &meta, &xHigherPriorityTaskWoken);
    if (xHigherPriorityTaskWoken) {
        portYIELD_FROM_ISR();
    }
}

// ── Globals ──────────────────────────────────────────────────────────────────
WiFiUDP udp;
LD2450Driver radarDriver;
LD2450Frame latestRadarFrame;
unsigned long lastTelemetrySent = 0;
unsigned long seqNum = 0;
const unsigned long TELEMETRY_INTERVAL_MS = 50; // 20 Hz telemetry

void setup() {
    Serial.begin(115200);
    delay(500);

    Serial.println("\n==================================================");
    Serial.println("  NEWVISION — ESP32 #1 RADAR & CSI SENSING NODE   ");
    Serial.println("==================================================");

    // Initialize latestRadarFrame explicitly so uninitialized memory cannot appear as targets
    latestRadarFrame.clear();

    // Initialize Radar UART2
    Serial2.begin(RADAR_BAUD, SERIAL_8N1, RADAR_RX_PIN, RADAR_TX_PIN);
    Serial.printf("[RADAR] UART2 initialized on RX:%d, TX:%d at %d baud\n", 
                  RADAR_RX_PIN, RADAR_TX_PIN, RADAR_BAUD);

    // Initialize CSI Queue (Capacity 32 frames)
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
    // 1. Ingest Radar UART bytes
    while (Serial2.available()) {
        uint8_t b = Serial2.read();
        radarDriver.readByte(b, &latestRadarFrame);
    }

    // 2. Drain CSI Queue outside interrupt
    CSIMetadata csiData;
    while (xQueueReceive(csiQueue, &csiData, 0) == pdTRUE) {
        lastRssi = csiData.rssi;
    }

    // 3. Dispatch Telemetry to Backend at 20 Hz
    unsigned long now = millis();
    if (now - lastTelemetrySent >= TELEMETRY_INTERVAL_MS) {
        lastTelemetrySent = now;
        seqNum++;

        // Formulate target JSON array with bounded buffer and snprintf checks
        char targetsJson[512];
        int targetsLen = 0;
        targetsJson[0] = '[';
        targetsJson[1] = '\0';
        targetsLen = 1;

        int validCount = 0;
        for (int i = 0; i < LD2450_MAX_TARGETS; i++) {
            if (latestRadarFrame.targets[i].is_valid) {
                LD2450TargetData& t = latestRadarFrame.targets[i];
                float xm = t.x_mm / 1000.0f;
                float ym = t.y_mm / 1000.0f;
                float dist = sqrt(xm * xm + ym * ym);
                float speed = t.speed_cms / 100.0f;

                char tBuf[160];
                int n = snprintf(tBuf, sizeof(tBuf),
                    "%s{\"target_id\":%d,\"x_mm\":%d,\"y_mm\":%d,\"x_m\":%.3f,\"y_m\":%.3f,"
                    "\"distance_m\":%.3f,\"speed_cms\":%d,\"speed_ms\":%.3f,\"resolution_mm\":%u,\"is_valid\":true}",
                    (validCount > 0) ? "," : "",
                    i + 1, t.x_mm, t.y_mm, xm, ym, dist, t.speed_cms, speed, t.resolution_mm
                );

                if (n > 0 && n < (int)sizeof(tBuf) && (targetsLen + n + 2) < (int)sizeof(targetsJson)) {
                    memcpy(targetsJson + targetsLen, tBuf, n);
                    targetsLen += n;
                    targetsJson[targetsLen] = '\0';
                    validCount++;
                }
            }
        }
        targetsJson[targetsLen++] = ']';
        targetsJson[targetsLen] = '\0';

        // Retrieve diagnostic counters from radar driver
        uint32_t totalBytes   = radarDriver.getTotalBytes();
        uint32_t validFrames  = radarDriver.getValidFrames();
        uint32_t invalidTails = radarDriver.getInvalidTails();
        uint32_t headerResync = radarDriver.getHeaderResyncs();
        uint32_t errorsTotal  = radarDriver.getErrors();

        // Distinguish UART connection, valid frame reception, and target detection
        // Do NOT report healthy/ACTIVE merely because Wi-Fi is transmitting
        const char* sensorStatus = "DISCONNECTED";
        if (validFrames > 0) {
            sensorStatus = (validCount > 0) ? "ACTIVE" : "NO_TARGETS";
        } else if (totalBytes > 0) {
            sensorStatus = "SYNCING";
        }

        bool uartActive      = (totalBytes > 0);
        bool framesHealthy   = (validFrames > 0);
        bool targetsDetected = (validCount > 0);

        // Build telemetry packet safely with 1024-byte capacity and strict truncation check
        static char jsonPacket[1024];
        int ret = snprintf(jsonPacket, sizeof(jsonPacket),
            "{\"device_id\":\"esp32_radar_csi\",\"fw_ver\":\"1.0.0\",\"uptime_ms\":%lu,\"seq\":%lu,"
            "\"free_heap\":%u,\"rssi\":%d,\"csi_count\":%lu,\"errors\":%lu,\"packet_rate_hz\":20.0,"
            "\"radar\":{\"target_count\":%d,\"targets\":%s,\"parser_errors\":%lu,\"sensor_status\":\"%s\"},"
            "\"radar_diagnostics\":{\"total_bytes\":%lu,\"valid_frames\":%lu,\"invalid_tails\":%lu,"
            "\"header_resyncs\":%lu,\"uart_active\":%s,\"frames_healthy\":%s,\"targets_detected\":%s,\"radar_status\":\"%s\"}}",
            now, seqNum, (unsigned)ESP.getFreeHeap(), lastRssi, csiPacketCount, errorsTotal,
            validCount, targetsJson, errorsTotal, sensorStatus,
            totalBytes, validFrames, invalidTails, headerResync,
            uartActive ? "true" : "false",
            framesHealthy ? "true" : "false",
            targetsDetected ? "true" : "false",
            sensorStatus
        );

        // Strict verification: only transmit complete valid JSON
        if (ret > 0 && ret < (int)sizeof(jsonPacket)) {
            udp.beginPacket(BACKEND_IP, BACKEND_UDP_PORT);
            udp.write((const uint8_t*)jsonPacket, ret);
            udp.endPacket();
        } else {
            Serial.printf("[WARN] Telemetry packet truncated (ret=%d, cap=%u)\n", ret, (unsigned)sizeof(jsonPacket));
        }
    }
}
