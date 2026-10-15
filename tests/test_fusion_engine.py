"""
Tests for Multimodal Sensor Fusion Engine.
"""

import pytest
import time
from backend.fusion.engine import SensorFusionEngine
from backend.schemas import (
    RadarTelemetry, 
    RadarTarget, 
    WiFiMetrics, 
    MagnetometerTelemetry, 
    MTCInference
)

def test_fusion_all_offline():
    engine = SensorFusionEngine(stale_threshold_sec=2.0)
    now = time.time()
    # Age 10 seconds -> stale
    state = engine.evaluate(
        radar=None,
        wifi_radar=None,
        wifi_mag=None,
        mag=None,
        mtc=None,
        radar_updated_at=now - 10.0,
        wifi_updated_at=now - 10.0,
        mag_updated_at=now - 10.0,
        now_ts=now
    )
    assert state.presence_state == "OFFLINE"
    assert "offline" in state.explainable_summary.lower()

def test_fusion_radar_target_with_magnetic_anomaly():
    engine = SensorFusionEngine(stale_threshold_sec=2.0)
    now = time.time()
    
    radar = RadarTelemetry(
        target_count=1,
        targets=[
            RadarTarget(
                target_id=1, x_mm=200, y_mm=1800, x_m=0.2, y_m=1.8,
                distance_m=1.81, speed_cms=40, speed_ms=0.4, resolution_mm=100
            )
        ]
    )
    
    wifi = WiFiMetrics(
        rssi_dbm=-45, csi_packet_count=1000, csi_packet_rate=100,
        csi_amplitude_variance=3.5, motion_heuristic="ACTIVE"
    )
    
    mag = MagnetometerTelemetry(
        sensor_chip="HMC5883L", is_supported=True,
        bx=25.0, by=18.0, bz=42.0, magnitude=52.0,
        baseline_bx=20.0, baseline_by=15.0, baseline_bz=40.0,
        delta_magnitude=5.8, calibration_status="CALIBRATED"
    )
    
    mtc = MTCInference(
        status="READY", predicted_class="handgun",
        confidence_percent=92.0, threat_level="HIGH"
    )

    state = engine.evaluate(
        radar=radar,
        wifi_radar=wifi,
        wifi_mag=wifi,
        mag=mag,
        mtc=mtc,
        radar_updated_at=now,
        wifi_updated_at=now,
        mag_updated_at=now,
        now_ts=now
    )

    assert state.presence_state == "MOVING_TARGET"
    assert state.threat_state in ["ELEVATED_FERROUS", "HIGH"]
    assert "Multi-modal confirmation" in state.explainable_summary
    assert len(state.supporting_sensors) >= 2

def test_fusion_radar_target_without_magnetic_anomaly():
    engine = SensorFusionEngine(stale_threshold_sec=2.0)
    now = time.time()
    
    radar = RadarTelemetry(
        target_count=1,
        targets=[
            RadarTarget(
                target_id=1, x_mm=0, y_mm=2000, x_m=0.0, y_m=2.0,
                distance_m=2.0, speed_cms=0, speed_ms=0.0, resolution_mm=100
            )
        ]
    )
    
    mag = MagnetometerTelemetry(
        sensor_chip="HMC5883L", is_supported=True,
        bx=20.1, by=15.0, bz=40.0, magnitude=47.1,
        baseline_bx=20.0, baseline_by=15.0, baseline_bz=40.0,
        delta_magnitude=0.1, calibration_status="CALIBRATED"
    )

    state = engine.evaluate(
        radar=radar,
        wifi_radar=None,
        wifi_mag=None,
        mag=mag,
        mtc=None,
        radar_updated_at=now,
        wifi_updated_at=0,
        mag_updated_at=now,
        now_ts=now
    )

    assert state.presence_state == "STATIONARY_PRESENCE"
    assert state.threat_state == "NONE"
    assert "Magnetic baseline normal" in state.explainable_summary
