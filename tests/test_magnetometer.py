"""
Tests for Magnetometer telemetry processing, baseline calibration, and chip validation.
"""

import pytest
from backend.parsers.magnetometer import MagnetometerProcessor

def test_magnetometer_baseline_zeroing():
    processor = MagnetometerProcessor()
    assert processor.is_calibrated is False
    
    # Process uncalibrated
    t1 = processor.process(bx=22.0, by=15.0, bz=40.0)
    assert t1.calibration_status == "UNCALIBRATED"
    assert t1.delta_magnitude == 0.0

    # Calibrate with 10 samples
    processor.start_calibration(num_samples=10)
    for _ in range(10):
        processor.process(bx=20.0, by=10.0, bz=40.0)

    assert processor.is_calibrated is True
    assert processor.baseline_bx == 20.0
    assert processor.baseline_by == 10.0
    assert processor.baseline_bz == 40.0

    # Test baseline deviation with anomaly (+3 uT in Bx, +4 uT in By)
    # Deviation = sqrt(3^2 + 4^2) = 5.0 uT
    t_anomaly = processor.process(bx=23.0, by=14.0, bz=40.0)
    assert t_anomaly.calibration_status == "CALIBRATED"
    assert t_anomaly.delta_magnitude == pytest.approx(5.0, 0.05)

def test_mpu6050_incompatibility_detection():
    processor = MagnetometerProcessor()
    res = processor.process(bx=10.0, by=10.0, bz=10.0, sensor_chip="MPU6050_NO_MAG")
    assert res.is_supported is False
    assert res.calibration_status == "INCOMPATIBLE"
    assert res.magnitude == 0.0

def test_mpu6500_clone_rejection():
    # Board marked MPU-9250/6500 but physically lacking AK8963
    processor = MagnetometerProcessor()
    res = processor.process(bx=12.0, by=8.0, bz=35.0, sensor_chip="MPU6500_NO_MAG")
    assert res.is_supported is False
    assert res.calibration_status == "INCOMPATIBLE"

def test_genuine_mpu9250_acceptance():
    # Genuine MPU-9250 with AK8963 verified
    processor = MagnetometerProcessor()
    res = processor.process(bx=21.0, by=14.0, bz=42.0, sensor_chip="MPU9250_AK8963")
    assert res.is_supported is True
    assert res.magnitude > 0
    assert res.calibration_status == "UNCALIBRATED"

