"""
Tests for NewVision Telemetry Schemas and Pydantic validation.
"""

import pytest
from backend.schemas import (
    RadarTarget, 
    RadarTelemetry, 
    WiFiMetrics, 
    MagnetometerTelemetry, 
    MTCInference, 
    FusionState,
    DeviceDiagnostics,
    SystemConsolidatedState
)

def test_radar_target_schema():
    target = RadarTarget(
        target_id=1,
        x_mm=-1200,
        y_mm=2500,
        x_m=-1.2,
        y_m=2.5,
        distance_m=2.773,
        speed_cms=-45,
        speed_ms=-0.45,
        resolution_mm=150,
        is_valid=True
    )
    assert target.x_mm == -1200
    assert target.distance_m == 2.773
    assert target.speed_ms == -0.45

def test_magnetometer_schema_defaults():
    mag = MagnetometerTelemetry(
        sensor_chip="HMC5883L",
        bx=20.5,
        by=12.2,
        bz=40.0,
        magnitude=46.57
    )
    assert mag.is_supported is True
    assert mag.calibration_status == "UNCALIBRATED"
    assert mag.unit == "uT"

def test_mtc_inference_schema():
    mtc = MTCInference(
        status="READY",
        predicted_class="handgun",
        confidence_percent=91.4,
        threat_level="HIGH",
        threat_color="#ff4444"
    )
    assert mtc.status == "READY"
    assert mtc.threat_level == "HIGH"
    assert mtc.is_validated_hardware_model is False

def test_fusion_state_schema():
    fusion = FusionState(
        presence_state="MOVING_TARGET",
        threat_state="ELEVATED_FERROUS",
        supporting_sensors=["Radar target at 2.5m", "Magnetic disturbance +4.2 uT"]
    )
    assert fusion.presence_state == "MOVING_TARGET"
    assert len(fusion.supporting_sensors) == 2

def test_system_consolidated_state():
    state = SystemConsolidatedState(
        is_demo_mode=True,
        system_status="OPERATIONAL",
        active_devices=["nodemcu_ap", "esp32_radar_csi"]
    )
    assert state.is_demo_mode is True
    assert "nodemcu_ap" in state.active_devices
