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

def test_fusion_mode_radar_only():
    engine = SensorFusionEngine(stale_threshold_sec=2.0)
    now = time.time()
    radar = RadarTelemetry(
        target_count=1,
        targets=[
            RadarTarget(target_id=1, x_mm=100, y_mm=2500, x_m=0.1, y_m=2.5, distance_m=2.5, speed_cms=30, speed_ms=0.3, resolution_mm=100)
        ]
    )
    # Rx1 and Rx2 offline/stale
    state = engine.evaluate(
        radar=radar, wifi_radar=None, wifi_mag=None, mag=None, mtc=None,
        radar_updated_at=now, wifi_updated_at=0.0, mag_updated_at=0.0, now_ts=now
    )
    assert state.presence_state == "MOVING_TARGET"
    assert len(state.radar_evidence) > 0
    assert "stale or offline" in state.conflicting_sensors[0].lower() or "offline" in state.conflicting_sensors[0].lower()

def test_fusion_mode_rx1_only():
    engine = SensorFusionEngine(stale_threshold_sec=2.0)
    now = time.time()
    wifi1 = WiFiMetrics(
        receiver_id="rx1", rssi_dbm=-42, csi_available=True, feature_format="SUBCA_AMP_VAR",
        csi_packet_rate=100, csi_amplitude_variance=3.8, motion_heuristic="ACTIVE"
    )
    state = engine.evaluate(
        radar=None, wifi_radar=wifi1, wifi_mag=None, mag=None, mtc=None,
        radar_updated_at=0.0, wifi_updated_at=now, mag_updated_at=0.0, now_ts=now
    )
    assert state.presence_state == "WIFI_RF_ACTIVITY_ONLY"
    assert any("Rx1" in e for e in state.rx1_evidence)
    assert state.confidence_score is not None

def test_fusion_mode_rx2_only():
    engine = SensorFusionEngine(stale_threshold_sec=2.0)
    now = time.time()
    wifi2 = WiFiMetrics(
        receiver_id="rx2", rssi_dbm=-50, csi_available=False, feature_format="RAW_RSSI_ONLY",
        csi_packet_rate=100, csi_amplitude_variance=2.2, motion_heuristic="SUBTLE"
    )
    state = engine.evaluate(
        radar=None, wifi_radar=None, wifi_mag=wifi2, mag=None, mtc=None,
        radar_updated_at=0.0, wifi_updated_at=now, mag_updated_at=0.0, now_ts=now
    )
    assert state.presence_state == "WIFI_RF_ACTIVITY_ONLY"
    assert any("Rx2" in e for e in state.rx2_evidence)

def test_fusion_mode_radar_plus_one_receiver():
    engine = SensorFusionEngine(stale_threshold_sec=2.0)
    now = time.time()
    radar = RadarTelemetry(
        target_count=1,
        targets=[
            RadarTarget(target_id=1, x_mm=200, y_mm=2200, x_m=0.2, y_m=2.2, distance_m=2.21, speed_cms=10, speed_ms=0.1, resolution_mm=100)
        ]
    )
    wifi1 = WiFiMetrics(
        receiver_id="rx1", rssi_dbm=-44, csi_available=True, feature_format="SUBCA_AMP_VAR",
        csi_packet_rate=100, csi_amplitude_variance=1.9, motion_heuristic="SUBTLE"
    )
    state = engine.evaluate(
        radar=radar, wifi_radar=wifi1, wifi_mag=None, mag=None, mtc=None,
        radar_updated_at=now, wifi_updated_at=now, mag_updated_at=0.0, now_ts=now
    )
    assert state.presence_state in ["MOVING_TARGET", "STATIONARY_PRESENCE"]
    assert len(state.radar_evidence) > 0
    assert len(state.rx1_evidence) > 0

def test_fusion_mode_radar_plus_both_receivers():
    engine = SensorFusionEngine(stale_threshold_sec=2.0)
    now = time.time()
    radar = RadarTelemetry(
        target_count=1,
        targets=[
            RadarTarget(target_id=1, x_mm=-300, y_mm=3000, x_m=-0.3, y_m=3.0, distance_m=3.01, speed_cms=25, speed_ms=0.25, resolution_mm=100)
        ]
    )
    wifi1 = WiFiMetrics(receiver_id="rx1", rssi_dbm=-45, csi_available=True, feature_format="SUBCA_AMP_VAR", csi_packet_rate=100, csi_amplitude_variance=2.8, motion_heuristic="ACTIVE")
    wifi2 = WiFiMetrics(receiver_id="rx2", rssi_dbm=-48, csi_available=False, feature_format="RAW_RSSI_ONLY", csi_packet_rate=100, csi_amplitude_variance=1.5, motion_heuristic="SUBTLE")
    
    state = engine.evaluate(
        radar=radar, wifi_radar=wifi1, wifi_mag=wifi2, mag=None, mtc=None,
        radar_updated_at=now, wifi_updated_at=now, mag_updated_at=0.0, now_ts=now
    )
    assert state.presence_state == "MOVING_TARGET"
    assert len(state.radar_evidence) > 0
    assert len(state.rx1_evidence) > 0
    assert len(state.rx2_evidence) > 0

