"""
Tests for MTC-1 model loading, feature calculation, and inference integrity.
"""

import pytest
from backend.models.mtc1_loader import mtc1_service

def test_mtc1_model_loaded():
    assert mtc1_service.is_loaded is True
    assert len(mtc1_service.model_stats.get("classes", [])) == 6

def test_mtc1_uncalibrated_guardrail():
    # If uncalibrated, model should refuse to classify weapons
    res = mtc1_service.predict(
        bx=0.1, by=0.1, bz=0.05, distance=1.5, is_calibrated=False
    )
    assert res.status == "UNCALIBRATED"
    assert res.threat_level == "NONE"

def test_mtc1_awaiting_range_guardrail():
    # If target distance is None, dipole features cannot be computed
    res = mtc1_service.predict(
        bx=0.1, by=0.1, bz=0.05, distance=None, is_calibrated=True
    )
    assert res.status == "AWAITING_RANGE"
    assert res.threat_level == "NONE"

def test_mtc1_sensor_incompatible_guardrail():
    res = mtc1_service.predict(
        bx=0.0, by=0.0, bz=0.0, distance=1.5, is_calibrated=True, sensor_supported=False
    )
    assert res.status == "SENSOR_INCOMPATIBLE"

def test_mtc1_valid_inference():
    # Pass realistic dipole readings with distance 1.5m
    res = mtc1_service.predict(
        bx=0.08, by=0.06, bz=0.03, distance=1.5, is_calibrated=True, sensor_supported=True
    )
    assert res.status == "READY"
    assert res.predicted_class in mtc1_service.model_stats["classes"]
    assert res.confidence_percent is not None
    assert res.confidence_percent > 0
    assert len(res.all_probabilities) == 6
    assert res.is_validated_hardware_model is False
