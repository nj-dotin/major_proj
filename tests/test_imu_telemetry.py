"""
Unit and integration tests for MPU-6500 IMU telemetry ingestion,
validation, Pydantic schema serialization, and error recovery.
"""

import pytest
import math
import time
import json
from backend.schemas import IMUTelemetry, SystemConsolidatedState, TelemetryPacket, DeviceDiagnostics
from backend.services.udp_receiver import LiveHardwareStateManager

def test_imu_telemetry_schema_defaults():
    imu = IMUTelemetry()
    assert imu.sensor_chip == "UNKNOWN"
    assert imu.is_available is False
    assert imu.is_valid is False
    assert imu.status == "UNAVAILABLE"
    assert imu.ax is None
    assert imu.ay is None
    assert imu.az is None
    assert imu.gx is None
    assert imu.gy is None
    assert imu.gz is None
    assert imu.total_accel_g is None
    assert imu.total_gyro_dps is None

def test_imu_telemetry_serialization():
    imu = IMUTelemetry(
        sensor_chip="MPU6500",
        is_available=True,
        is_valid=True,
        status="ONLINE",
        ax=0.0123,
        ay=-0.0456,
        az=0.9854,
        gx=0.15,
        gy=-0.35,
        gz=0.05,
        total_accel_g=0.9865,
        total_gyro_dps=0.384,
        sample_seq=42,
        device_timestamp_ms=123456,
        last_update_ts=time.time()
    )
    json_str = imu.model_dump_json()
    data = json.loads(json_str)
    assert data["sensor_chip"] == "MPU6500"
    assert data["is_available"] is True
    assert data["is_valid"] is True
    assert data["ax"] == pytest.approx(0.0123, 0.0001)
    assert data["az"] == pytest.approx(0.9854, 0.0001)
    assert data["gx"] == pytest.approx(0.15, 0.01)

    # State serialization
    state = SystemConsolidatedState(imu=imu)
    state_json = state.model_dump_json()
    assert "MPU6500" in state_json
    reconstructed = SystemConsolidatedState.model_validate_json(state_json)
    assert reconstructed.imu.is_available is True
    assert reconstructed.imu.az == pytest.approx(0.9854, 0.0001)

def test_udp_receiver_valid_nested_imu():
    mgr = LiveHardwareStateManager()
    payload = {
        "device_id": "esp32_mag_csi",
        "fw_ver": "1.0.0",
        "uptime_ms": 10000,
        "seq": 105,
        "free_heap": 220000,
        "rssi": -55,
        "chip": "MPU6500_NO_MAG",
        "supported": False,
        "bx": 0.0,
        "by": 0.0,
        "bz": 0.0,
        "imu": {
            "sensor": "MPU6500",
            "available": True,
            "valid": True,
            "ax": 0.021,
            "ay": -0.015,
            "az": 0.998,
            "gx": 1.2,
            "gy": -0.8,
            "gz": 0.3,
            "sample_seq": 105,
            "timestamp_ms": 10000
        }
    }
    mgr.handle_packet(payload)
    imu = mgr.current_state.imu
    assert imu.sensor_chip == "MPU6500"
    assert imu.is_available is True
    assert imu.is_valid is True
    assert imu.status == "ONLINE"
    assert imu.ax == pytest.approx(0.021, 0.001)
    assert imu.az == pytest.approx(0.998, 0.001)
    assert imu.gx == pytest.approx(1.2, 0.01)
    assert imu.total_accel_g == pytest.approx(math.sqrt(0.021**2 + (-0.015)**2 + 0.998**2), 0.01)

def test_udp_receiver_valid_flat_root_imu():
    mgr = LiveHardwareStateManager()
    payload = {
        "device_id": "esp32_mag_csi",
        "fw_ver": "1.0.0",
        "uptime_ms": 20000,
        "seq": 200,
        "imu_sensor": "MPU6500",
        "imu_available": True,
        "imu_valid": True,
        "ax": -0.05,
        "ay": 0.02,
        "az": 1.01,
        "gx": -2.5,
        "gy": 0.0,
        "gz": 1.1
    }
    mgr.handle_packet(payload)
    imu = mgr.current_state.imu
    assert imu.sensor_chip == "MPU6500"
    assert imu.is_available is True
    assert imu.is_valid is True
    assert imu.status == "ONLINE"
    assert imu.ax == pytest.approx(-0.05, 0.001)
    assert imu.gx == pytest.approx(-2.5, 0.01)

def test_udp_receiver_absent_imu_fields():
    mgr = LiveHardwareStateManager()
    # Packet from older firmware without any IMU fields
    payload = {
        "device_id": "esp32_mag_csi",
        "fw_ver": "1.0.0",
        "uptime_ms": 5000,
        "seq": 50,
        "chip": "MPU6500_NO_MAG",
        "supported": False,
        "bx": 0.0,
        "by": 0.0,
        "bz": 0.0
    }
    mgr.handle_packet(payload)
    imu = mgr.current_state.imu
    # Must NOT fabricate zeros or report available
    assert imu.is_available is False
    assert imu.is_valid is False
    assert imu.status == "UNAVAILABLE"
    assert imu.ax is None
    assert imu.az is None

def test_udp_receiver_malformed_and_out_of_bounds_imu():
    mgr = LiveHardwareStateManager()
    # Packet with NaN, string garbage, and out-of-range 99999g
    payload = {
        "device_id": "esp32_mag_csi",
        "seq": 60,
        "imu": {
            "sensor": "MPU6500",
            "available": True,
            "valid": True,
            "ax": "not-a-number",
            "ay": float("nan"),
            "az": 99999.0, # Exceeds ±16g physical bound
            "gx": float("inf"),
            "gy": None,
            "gz": -50000.0
        }
    }
    # Must handle gracefully without crashing
    mgr.handle_packet(payload)
    imu = mgr.current_state.imu
    assert imu.is_available is True
    assert imu.is_valid is False
    assert imu.status == "UNAVAILABLE"
    assert imu.ax is None

def test_udp_receiver_corrupt_payload_recovery():
    mgr = LiveHardwareStateManager()
    # Invalid types for fields
    payload = {
        "device_id": "esp32_mag_csi",
        "imu": "corrupt_string_not_dict"
    }
    mgr.handle_packet(payload)
    assert mgr.current_state.imu.is_valid is False
