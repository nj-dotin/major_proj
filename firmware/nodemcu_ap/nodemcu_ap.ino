/**
 * NewVision Firmware: NodeMCU ESP8266 Wi-Fi Traffic Source
 * 
 * Responsibilities:
 * - Creates SoftAP "CSI_TEST" on Channel 6 (192.168.4.1)
 * - Generates regular, non-blocking UDP traffic (~10 ms interval)
 * - Transmits to both ESP32 receivers (unicast round-robin or subnet broadcast)
 * - Exposes packet counters and diagnostic telemetry
 * - Avoids blocking loops
 */

#include <ESP8266WiFi.h>
#include <WiFiUdp.h>

// ── Configurable Parameters ──────────────────────────────────────────────────
const char* AP_SSID        = "CSI_TEST";
const char* AP_PASSWORD    = "csi_sensing_pass";
const int   AP_CHANNEL     = 6;
const IPAddress AP_LOCAL_IP(192, 168, 4, 1);
const IPAddress AP_GATEWAY(192, 168, 4, 1);
const IPAddress AP_SUBNET(255, 255, 255, 0);

// Receiver Destinations
const IPAddress ESP32_RADAR_IP(192, 168, 4, 10);
const IPAddress ESP32_MAG_IP(192, 168, 4, 20);
const IPAddress BROADCAST_IP(192, 168, 4, 255);
const IPAddress BACKEND_LAPTOP_IP(192, 168, 4, 2);

const uint16_t  CSI_TRAFFIC_PORT  = 4210;
const uint16_t  BACKEND_UDP_PORT  = 5005;

// Packet Generation Rate (default ~10ms = 100 Hz)
const unsigned long PACKET_INTERVAL_MS = 10;
const unsigned long TELEMETRY_INTERVAL_MS = 1000;

// Mode: 0 = Broadcast to subnet, 1 = Unicast round-robin to both ESP32s
const int TRAFFIC_MODE = 1;

// ── Globals ──────────────────────────────────────────────────────────────────
WiFiUDP udp;
unsigned long lastPacketTime = 0;
unsigned long lastTelemetryTime = 0;
unsigned long packetSeq = 0;
unsigned long packetsSentTotal = 0;
int destinationToggle = 0;

void setup() {
  Serial.begin(115200);
  delay(500);

  Serial.println();
  Serial.println("==================================================");
  Serial.println("  NEWVISION — NODEMCU ESP8266 AP TRAFFIC SOURCE   ");
  Serial.println("==================================================");

  // Configure SoftAP
  WiFi.mode(WIFI_AP);
  WiFi.softAPConfig(AP_LOCAL_IP, AP_GATEWAY, AP_SUBNET);
  bool apSuccess = WiFi.softAP(AP_SSID, AP_PASSWORD, AP_CHANNEL, false, 8);

  if (apSuccess) {
    Serial.printf("[AP] SSID: %s | Ch: %d | IP: %s\n", 
                  AP_SSID, AP_CHANNEL, WiFi.softAPIP().toString().c_str());
  } else {
    Serial.println("[AP] ERROR: Failed to start SoftAP!");
  }

  udp.begin(CSI_TRAFFIC_PORT);
  Serial.printf("[UDP] Listening on port: %d\n", CSI_TRAFFIC_PORT);
}

void loop() {
  unsigned long now = millis();

  // 1. High-rate non-blocking CSI Sensing Traffic Generation
  if (now - lastPacketTime >= PACKET_INTERVAL_MS) {
    lastPacketTime = now;
    packetSeq++;
    packetsSentTotal++;

    // Prepare packet payload (contains sequence number and timestamp)
    char csiPayload[48];
    snprintf(csiPayload, sizeof(csiPayload), "CSI_PKT:%lu:%lu", packetSeq, now);

    if (TRAFFIC_MODE == 0) {
      // Broadcast mode
      udp.beginPacket(BROADCAST_IP, CSI_TRAFFIC_PORT);
      udp.write((const uint8_t*)csiPayload, strlen(csiPayload));
      udp.endPacket();
    } else {
      // Unicast round-robin mode: alternates packets to each receiver
      IPAddress dest = (destinationToggle == 0) ? ESP32_RADAR_IP : ESP32_MAG_IP;
      destinationToggle = 1 - destinationToggle;

      udp.beginPacket(dest, CSI_TRAFFIC_PORT);
      udp.write((const uint8_t*)csiPayload, strlen(csiPayload));
      udp.endPacket();
    }
  }

  // 2. Periodic NodeMCU Health & Diagnostics Telemetry (1 Hz)
  if (now - lastTelemetryTime >= TELEMETRY_INTERVAL_MS) {
    lastTelemetryTime = now;

    int stationsConnected = WiFi.softAPgetStationNum();
    uint32_t freeHeap = ESP.getFreeHeap();
    float pps = packetsSentTotal / (now / 1000.0f);

    // Send diagnostic JSON to backend laptop
    char diagJson[192];
    snprintf(diagJson, sizeof(diagJson),
      "{\"device_id\":\"nodemcu_ap\",\"fw_ver\":\"1.0.0\",\"uptime_ms\":%lu,\"seq\":%lu,"
      "\"free_heap\":%u,\"stations\":%d,\"packet_rate_hz\":%.1f}",
      now, packetSeq, freeHeap, stationsConnected, pps
    );

    udp.beginPacket(BACKEND_LAPTOP_IP, BACKEND_UDP_PORT);
    udp.write((const uint8_t*)diagJson, strlen(diagJson));
    udp.endPacket();

    Serial.printf("[DIAG] Stations: %d | Sent: %lu pkts (%.1f pps) | FreeHeap: %u B\n", 
                  stationsConnected, packetsSentTotal, pps, freeHeap);
  }

  // Non-blocking yield for ESP8266 background Wi-Fi stack
  yield();
}
