"""
Asynchronous UDP Telemetry Ingestion Service.
Listens on UDP port 5005 (configurable) for incoming packets from:
- NodeMCU ESP8266 traffic generator
- ESP32 #1 Radar + CSI node
- ESP32 #2 Magnetometer + CSI node

Parses both JSON telemetry and raw LD2450 binary frames.
Updates live system consolidated state and feeds the telemetry buffer.
"""

import asyncio
import json
import logging
import time
from typing import Optional, Callable
from backend.config import settings
from backend.schemas import (
    SystemConsolidatedState, 
    DeviceDiagnostics, 
    RadarTelemetry, 
    WiFiMetrics, 
    MagnetometerTelemetry
)
from backend.parsers.ld2450 import LD2450StreamParser
from backend.parsers.magnetometer import MagnetometerProcessor
from backend.parsers.csi import CSIProcessor
from backend.models.mtc1_loader import mtc1_service
from backend.fusion.engine import fusion_engine
from backend.services.telemetry_buffer import telemetry_buffer

logger = logging.getLogger("newvision.udp")

class UDPIngestionProtocol(asyncio.DatagramProtocol):
    def __init__(self, on_packet_callback: Callable[[dict], None]):
        self.on_packet_callback = on_packet_callback
        self.transport = None
        self.radar_parser = LD2450StreamParser()

    def connection_made(self, transport):
        self.transport = transport
        logger.info(f"UDP Ingestion Server active on port {settings.UDP_PORT}")

    def datagram_received(self, data: bytes, addr):
        try:
            # 1. Try parsing as JSON
            try:
                text = data.decode("utf-8")
                payload = json.loads(text)
                payload["_source_ip"] = addr[0]
                self.on_packet_callback(payload)
                return
            except (UnicodeDecodeError, json.JSONDecodeError):
                pass

            # 2. Try parsing as raw LD2450 binary packet (30 bytes)
            if len(data) >= 30 and data.startswith(bytes([0xAA, 0xFF, 0x03, 0x00])):
                frames = self.radar_parser.feed(data)
                for f in frames:
                    payload = {
                        "device_id": "esp32_radar_csi",
                        "role": "radar_csi",
                        "_source_ip": addr[0],
                        "radar": f.model_dump()
                    }
                    self.on_packet_callback(payload)
                return

            logger.warning(f"Unrecognized UDP packet ({len(data)} bytes) from {addr}")
        except Exception as e:
            logger.error(f"Error handling UDP datagram from {addr}: {e}")

class LiveHardwareStateManager:
    """
    Maintains the live aggregated multi-node state from hardware packets.
    """
    def __init__(self):
        self.mag_processor = MagnetometerProcessor()
        self.csi_processor_radar = CSIProcessor()
        self.csi_processor_mag = CSIProcessor()
        
        self.current_state = SystemConsolidatedState(is_demo_mode=False)
        self.last_update_radar = 0.0
        self.last_update_mag = 0.0
        self.last_update_ap = 0.0
        self.last_update_wifi = 0.0
        
    def calibrate_magnetometer(self, num_samples: int = 50):
        self.mag_processor.start_calibration(num_samples)

    def handle_packet(self, payload: dict):
        now = time.time()
        dev_id = payload.get("device_id", "unknown")
        src_ip = payload.get("_source_ip")
        
        if dev_id == "nodemcu_ap":
            self.last_update_ap = now
            self.current_state.node_ap = DeviceDiagnostics(
                device_id="nodemcu_ap",
                role="traffic_ap",
                firmware_version=payload.get("fw_ver", "1.0.0"),
                uptime_ms=payload.get("uptime_ms", 0),
                seq=payload.get("seq", 0),
                free_heap=payload.get("free_heap"),
                wifi_connected=True,
                ip_address=src_ip,
                packet_rate_hz=payload.get("packet_rate_hz", 0.0)
            )
            
        elif dev_id == "esp32_radar_csi":
            self.last_update_radar = now
            self.last_update_wifi = now
            
            self.current_state.node_radar = DeviceDiagnostics(
                device_id="esp32_radar_csi",
                role="radar_csi",
                firmware_version=payload.get("fw_ver", "1.0.0"),
                uptime_ms=payload.get("uptime_ms", 0),
                seq=payload.get("seq", 0),
                free_heap=payload.get("free_heap"),
                wifi_connected=True,
                ip_address=src_ip,
                parser_errors=payload.get("errors", 0),
                packet_rate_hz=payload.get("packet_rate_hz", 0.0)
            )
            
            # Radar targets
            if "radar" in payload:
                self.current_state.radar = RadarTelemetry(**payload["radar"])
            elif "targets" in payload:
                self.current_state.radar = RadarTelemetry(
                    target_count=len(payload["targets"]),
                    targets=payload["targets"],
                    sensor_status="ACTIVE"
                )

            # Wi-Fi / CSI
            rssi = payload.get("rssi")
            csi_count = payload.get("csi_count", 0)
            subcarriers = payload.get("subcarriers")
            self.current_state.wifi_radar_node = self.csi_processor_radar.process(
                rssi_dbm=rssi,
                csi_packet_count=csi_count,
                subcarrier_amplitudes=subcarriers,
                now_ts=now
            )
            
        elif dev_id == "esp32_mag_csi":
            self.last_update_mag = now
            self.last_update_wifi = now
            
            self.current_state.node_mag = DeviceDiagnostics(
                device_id="esp32_mag_csi",
                role="magnetometer_csi",
                firmware_version=payload.get("fw_ver", "1.0.0"),
                uptime_ms=payload.get("uptime_ms", 0),
                seq=payload.get("seq", 0),
                free_heap=payload.get("free_heap"),
                wifi_connected=True,
                ip_address=src_ip,
                packet_rate_hz=payload.get("packet_rate_hz", 0.0)
            )
            
            # Magnetometer
            bx = float(payload.get("bx", 0.0))
            by = float(payload.get("by", 0.0))
            bz = float(payload.get("bz", 0.0))
            chip = payload.get("chip", "HMC5883L")
            unit = payload.get("unit", "uT")
            
            self.current_state.magnetometer = self.mag_processor.process(
                bx=bx, by=by, bz=bz, sensor_chip=chip, unit=unit
            )
            
            # Wi-Fi / CSI
            rssi = payload.get("rssi")
            csi_count = payload.get("csi_count", 0)
            self.current_state.wifi_mag_node = self.csi_processor_mag.process(
                rssi_dbm=rssi,
                csi_packet_count=csi_count,
                now_ts=now
            )

        # Update active devices list
        active = []
        if (now - self.last_update_ap) < 3.0 and self.current_state.node_ap:
            active.append("nodemcu_ap")
        if (now - self.last_update_radar) < 3.0 and self.current_state.node_radar:
            active.append("esp32_radar_csi")
        if (now - self.last_update_mag) < 3.0 and self.current_state.node_mag:
            active.append("esp32_mag_csi")
        self.current_state.active_devices = active

        # Compute range for MTC-1 from radar if available
        closest_range: Optional[float] = None
        if self.current_state.radar and self.current_state.radar.targets:
            valid_targets = [t for t in self.current_state.radar.targets if t.is_valid]
            if valid_targets:
                closest_range = min(valid_targets, key=lambda t: t.distance_m).distance_m

        # Run MTC-1
        mag = self.current_state.magnetometer
        self.current_state.mtc = mtc1_service.predict(
            bx=mag.bx - mag.baseline_bx,
            by=mag.by - mag.baseline_by,
            bz=mag.bz - mag.baseline_bz,
            distance=closest_range,
            is_calibrated=self.mag_processor.is_calibrated,
            sensor_supported=mag.is_supported
        )

        # Run Fusion
        self.current_state.fusion = fusion_engine.evaluate(
            radar=self.current_state.radar,
            wifi_radar=self.current_state.wifi_radar_node,
            wifi_mag=self.current_state.wifi_mag_node,
            mag=self.current_state.magnetometer,
            mtc=self.current_state.mtc,
            radar_updated_at=self.last_update_radar,
            wifi_updated_at=self.last_update_wifi,
            mag_updated_at=self.last_update_mag,
            now_ts=now
        )
        
        self.current_state.timestamp = now
        telemetry_buffer.push(self.current_state)

live_hardware_manager = LiveHardwareStateManager()
