"""
Deterministic Demo Simulator for NewVision.
Simulates all three hardware nodes:
1. NodeMCU AP (Traffic generation, sequence counters, uptime)
2. ESP32 #1 Radar + CSI (LD2450 target coordinates, speed, Wi-Fi RSSI)
3. ESP32 #2 Magnetometer + CSI (Geomagnetic baseline + dipole perturbation)

Feeds the exact same unified schema as real hardware, with:
- Explicit 'is_simulated = True' tagging
- Realistic target trajectory & velocity
- Dipole physics for magnetic anomaly
- Real execution of the MTC-1 model pipeline on simulated data
"""

import math
import time
from typing import Optional
from backend.schemas import (
    SystemConsolidatedState,
    DeviceDiagnostics,
    RadarTelemetry,
    RadarTarget,
    WiFiMetrics,
    MagnetometerTelemetry,
    MTCInference
)
from backend.models.mtc1_loader import mtc1_service
from backend.fusion.engine import fusion_engine

class DemoSimulator:
    def __init__(self):
        self.is_running = True
        self.start_time = time.time()
        self.seq_nodemcu = 0
        self.seq_esp32_radar = 0
        self.seq_esp32_mag = 0
        
        # Calibration baseline for simulated magnetometer
        self.base_bx = 22.4
        self.base_by = 14.8
        self.base_bz = 41.2
        
        # Object being simulated: 'handgun', 'tool', or 'clear'
        self.simulated_object_mode = "handgun"
        self.moment_map = {
            "handgun": 0.52,
            "knife": 0.28,
            "rifle": 0.85,
            "tool": 0.38,
            "clear": 0.02
        }

    def set_object_type(self, obj_type: str):
        if obj_type in self.moment_map:
            self.simulated_object_mode = obj_type

    def generate_tick(self, now: Optional[float] = None) -> SystemConsolidatedState:
        t = (now or time.time()) - self.start_time
        
        self.seq_nodemcu += 1
        self.seq_esp32_radar += 1
        self.seq_esp32_mag += 1

        # 1. NodeMCU Diagnostics
        node_ap = DeviceDiagnostics(
            device_id="nodemcu_ap",
            role="traffic_ap",
            firmware_version="1.0.0-demo",
            uptime_ms=int(t * 1000),
            seq=self.seq_nodemcu,
            free_heap=42150,
            wifi_connected=True,
            ip_address="192.168.4.1",
            packet_rate_hz=98.5
        )

        # 2. ESP32 #1 Radar + CSI Simulation
        # Target walking in forward direction and swaying laterally
        # Y oscillates between 1.0m and 3.8m
        y_m = round(2.4 + 1.4 * math.sin(0.4 * t), 3)
        # Lateral X oscillates between -0.8m and +0.8m
        x_m = round(0.8 * math.sin(0.25 * t), 3)
        # Velocity is derivative of position: dy/dt = 1.4 * 0.4 * cos(0.4 * t)
        speed_ms = round(1.4 * 0.4 * math.cos(0.4 * t), 3)
        speed_cms = int(speed_ms * 100)
        
        dist_m = round(math.sqrt(x_m**2 + y_m**2), 3)
        
        target = RadarTarget(
            target_id=1,
            x_mm=int(x_m * 1000),
            y_mm=int(y_m * 1000),
            x_m=x_m,
            y_m=y_m,
            distance_m=dist_m,
            speed_cms=speed_cms,
            speed_ms=speed_ms,
            resolution_mm=150,
            is_valid=True
        )
        
        radar_telemetry = RadarTelemetry(
            target_count=1,
            targets=[target],
            sensor_status="ACTIVE",
            parser_errors=0
        )
        
        node_radar = DeviceDiagnostics(
            device_id="esp32_radar_csi",
            role="radar_csi",
            firmware_version="1.0.0-demo",
            uptime_ms=int(t * 1000),
            seq=self.seq_esp32_radar,
            free_heap=184320,
            wifi_connected=True,
            ip_address="192.168.4.10",
            packet_rate_hz=20.0
        )

        # Wi-Fi CSI for Radar Node: variance rises when target is moving faster
        motion_factor = abs(speed_ms)
        csi_var_r = round(0.5 + 4.5 * motion_factor + 0.2 * math.sin(3.0 * t), 3)
        wifi_radar = WiFiMetrics(
            rssi_dbm=int(-46 + 4 * math.sin(0.2 * t)),
            csi_packet_count=self.seq_esp32_radar * 5,
            csi_packet_rate=100.0,
            csi_amplitude_variance=csi_var_r,
            motion_heuristic="ACTIVE" if csi_var_r > 2.0 else "SUBTLE",
            is_model_inferred=False
        )

        # 3. ESP32 #2 Magnetometer + CSI Simulation
        # Dipole perturbation from target: B_anomaly ∝ m / r^3
        m = self.moment_map.get(self.simulated_object_mode, 0.4)
        # Perturbation in uT (Earth is ~50 uT; near target ~0.5m might produce 5-15 uT disturbance)
        pert = (m * 15.0) / (dist_m ** 3)
        pert_x = round(pert * math.cos(0.5 * t), 3)
        pert_y = round(pert * math.sin(0.5 * t), 3)
        pert_z = round(pert * 0.4, 3)

        current_bx = round(self.base_bx + pert_x, 3)
        current_by = round(self.base_by + pert_y, 3)
        current_bz = round(self.base_bz + pert_z, 3)
        magnitude = round(math.sqrt(current_bx**2 + current_by**2 + current_bz**2), 3)
        delta_mag = round(math.sqrt(pert_x**2 + pert_y**2 + pert_z**2), 3)

        mag_telemetry = MagnetometerTelemetry(
            sensor_chip="HMC5883L (SIMULATED)",
            is_supported=True,
            bx=current_bx,
            by=current_by,
            bz=current_bz,
            magnitude=magnitude,
            baseline_bx=self.base_bx,
            baseline_by=self.base_by,
            baseline_bz=self.base_bz,
            delta_magnitude=delta_mag,
            unit="uT",
            calibration_status="CALIBRATED"
        )

        node_mag = DeviceDiagnostics(
            device_id="esp32_mag_csi",
            role="magnetometer_csi",
            firmware_version="1.0.0-demo",
            uptime_ms=int(t * 1000),
            seq=self.seq_esp32_mag,
            free_heap=192100,
            wifi_connected=True,
            ip_address="192.168.4.20",
            packet_rate_hz=20.0
        )

        wifi_mag = WiFiMetrics(
            rssi_dbm=int(-48 + 3 * math.cos(0.3 * t)),
            csi_packet_count=self.seq_esp32_mag * 5,
            csi_packet_rate=100.0,
            csi_amplitude_variance=round(0.4 + 3.0 * motion_factor, 3),
            motion_heuristic="ACTIVE" if motion_factor > 0.3 else "QUIET",
            is_model_inferred=False
        )

        # 4. MTC-1 Inference on Simulated Features
        # Pass simulated magnetic anomaly & target distance into real MTC-1 model pipeline
        mtc_result = mtc1_service.predict(
            bx=pert_x,
            by=pert_y,
            bz=pert_z,
            distance=dist_m,
            is_calibrated=True,
            sensor_supported=True
        )

        # 5. Fusion Evaluation
        now_ts = now or time.time()
        fusion_result = fusion_engine.evaluate(
            radar=radar_telemetry,
            wifi_radar=wifi_radar,
            wifi_mag=wifi_mag,
            mag=mag_telemetry,
            mtc=mtc_result,
            radar_updated_at=now_ts,
            wifi_updated_at=now_ts,
            mag_updated_at=now_ts,
            now_ts=now_ts
        )

        return SystemConsolidatedState(
            timestamp=now_ts,
            is_demo_mode=True,
            system_status="OPERATIONAL",
            active_devices=["nodemcu_ap", "esp32_radar_csi", "esp32_mag_csi"],
            node_ap=node_ap,
            node_radar=node_radar,
            node_mag=node_mag,
            radar=radar_telemetry,
            wifi_radar_node=wifi_radar,
            wifi_mag_node=wifi_mag,
            magnetometer=mag_telemetry,
            mtc=mtc_result,
            fusion=fusion_result
        )

demo_simulator = DemoSimulator()
