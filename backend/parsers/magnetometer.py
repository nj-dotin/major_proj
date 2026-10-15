"""
Magnetometer telemetry processor and baseline calibrator.
Handles unit normalization (microTesla uT), ambient geomagnetic field zeroing,
and hardware compatibility verification (MPU-9250 vs MPU-6050).
"""

import math
from typing import Optional, List
from backend.schemas import MagnetometerTelemetry

class MagnetometerProcessor:
    def __init__(self):
        self.baseline_bx = 0.0
        self.baseline_by = 0.0
        self.baseline_bz = 0.0
        self.is_calibrated = False
        self.calibration_samples: List[tuple] = []
        self.calibrating = False
        self.target_calibration_samples = 50
        
    def start_calibration(self, num_samples: int = 50):
        """Starts collecting samples to determine the ambient baseline."""
        self.calibrating = True
        self.is_calibrated = False
        self.calibration_samples = []
        self.target_calibration_samples = num_samples

    def set_manual_baseline(self, bx: float, by: float, bz: float):
        """Manually sets the reference ambient magnetic vector."""
        self.baseline_bx = bx
        self.baseline_by = by
        self.baseline_bz = bz
        self.is_calibrated = True
        self.calibrating = False

    def process(self, 
                bx: float, 
                by: float, 
                bz: float, 
                sensor_chip: str = "HMC5883L", 
                unit: str = "uT") -> MagnetometerTelemetry:
        """
        Processes raw magnetic vector, updates calibration if active,
        and computes baseline deviation.
        """
        # Verification check: MPU-6050 and standalone MPU-6500 have NO magnetometer!
        is_incompatible = (
            ("6050" in sensor_chip and "9250" not in sensor_chip) or
            ("6500" in sensor_chip and "9250" not in sensor_chip) or
            ("NO_MAG" in sensor_chip) or
            ("NOT_FOUND" in sensor_chip)
        )
        if is_incompatible:
            return MagnetometerTelemetry(
                sensor_chip=sensor_chip,
                is_supported=False,
                bx=0.0,
                by=0.0,
                bz=0.0,
                magnitude=0.0,
                delta_magnitude=0.0,
                unit=unit,
                calibration_status="INCOMPATIBLE"
            )

        magnitude = round(math.sqrt(bx**2 + by**2 + bz**2), 3)

        # Handle ongoing calibration
        if self.calibrating:
            self.calibration_samples.append((bx, by, bz))
            if len(self.calibration_samples) >= self.target_calibration_samples:
                avg_bx = sum(s[0] for s in self.calibration_samples) / len(self.calibration_samples)
                avg_by = sum(s[1] for s in self.calibration_samples) / len(self.calibration_samples)
                avg_bz = sum(s[2] for s in self.calibration_samples) / len(self.calibration_samples)
                self.baseline_bx = round(avg_bx, 3)
                self.baseline_by = round(avg_by, 3)
                self.baseline_bz = round(avg_bz, 3)
                self.is_calibrated = True
                self.calibrating = False

        status = "CALIBRATING" if self.calibrating else ("CALIBRATED" if self.is_calibrated else "UNCALIBRATED")

        # Compute deviation from baseline
        if self.is_calibrated:
            dx = bx - self.baseline_bx
            dy = by - self.baseline_by
            dz = bz - self.baseline_bz
            delta_mag = round(math.sqrt(dx**2 + dy**2 + dz**2), 3)
        else:
            delta_mag = 0.0

        return MagnetometerTelemetry(
            sensor_chip=sensor_chip,
            is_supported=True,
            bx=round(bx, 3),
            by=round(by, 3),
            bz=round(bz, 3),
            magnitude=magnitude,
            baseline_bx=self.baseline_bx,
            baseline_by=self.baseline_by,
            baseline_bz=self.baseline_bz,
            delta_magnitude=delta_mag,
            unit=unit,
            calibration_status=status
        )
