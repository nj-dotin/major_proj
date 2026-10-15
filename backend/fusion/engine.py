"""
Multimodal Sensor Fusion Engine for NewVision.
Transparent, explainable fusion combining:
- HLK-LD2450 24 GHz Radar Target Tracking
- Wi-Fi CSI/RSSI Activity Sensing
- 3-Axis Magnetometer Anomaly Detection & Baseline Drift
- MTC-1 Classification Evidence

Adheres strictly to honest sensing:
- Distinguishes motion from stationary presence
- Discloses sensor freshness and staleness
- Flags missing or contradictory evidence
- Does not manufacture fake confidence metrics
"""

import time
from typing import Optional, List, Dict, Any
from backend.schemas import (
    FusionState, 
    RadarTelemetry, 
    WiFiMetrics, 
    MagnetometerTelemetry, 
    MTCInference
)

class SensorFusionEngine:
    def __init__(self, stale_threshold_sec: float = 3.0):
        self.stale_threshold_sec = stale_threshold_sec
        self.last_radar_time = 0.0
        self.last_wifi_time = 0.0
        self.last_mag_time = 0.0

    def evaluate(self,
                 radar: Optional[RadarTelemetry],
                 wifi_radar: Optional[WiFiMetrics],
                 wifi_mag: Optional[WiFiMetrics],
                 mag: Optional[MagnetometerTelemetry],
                 mtc: Optional[MTCInference],
                 radar_updated_at: float,
                 wifi_updated_at: float,
                 mag_updated_at: float,
                 now_ts: Optional[float] = None) -> FusionState:
        now = now_ts or time.time()
        
        # Calculate freshness
        age_radar = round(now - radar_updated_at, 2) if radar_updated_at > 0 else 999.0
        age_wifi = round(now - wifi_updated_at, 2) if wifi_updated_at > 0 else 999.0
        age_mag = round(now - mag_updated_at, 2) if mag_updated_at > 0 else 999.0
        
        freshness = {
            "radar_sec": age_radar,
            "wifi_sec": age_wifi,
            "mag_sec": age_mag
        }

        radar_active = (radar is not None) and (age_radar < self.stale_threshold_sec)
        wifi_active = (age_wifi < self.stale_threshold_sec)
        mag_active = (mag is not None) and (age_mag < self.stale_threshold_sec) and mag.is_supported

        supporting: List[str] = []
        contradicting: List[str] = []
        
        presence_state = "CLEAR"
        threat_state = "NONE"
        summary_parts: List[str] = []
        
        target_count = 0
        closest_distance: Optional[float] = None
        top_speed: Optional[float] = None

        # 1. Evaluate Radar Tracking
        radar_detected_targets = False
        if radar_active and radar and radar.targets:
            target_count = len(radar.targets)
            valid_targets = [t for t in radar.targets if t.is_valid]
            if valid_targets:
                radar_detected_targets = True
                closest_target = min(valid_targets, key=lambda t: t.distance_m)
                closest_distance = closest_target.distance_m
                top_speed = closest_target.speed_ms
                
                if abs(closest_target.speed_ms) > 0.15:
                    presence_state = "MOVING_TARGET"
                    supporting.append(f"Radar tracking {target_count} moving target(s) (closest: {closest_distance}m at {top_speed}m/s)")
                else:
                    presence_state = "STATIONARY_PRESENCE"
                    supporting.append(f"Radar tracking {target_count} stationary target(s) at {closest_distance}m")
            else:
                contradicting.append("Radar active with 0 valid targets")
        elif not radar_active:
            contradicting.append("Radar stream stale or disconnected")

        # 2. Evaluate Wi-Fi Sensing Evidence
        wifi_activity_noted = False
        if wifi_active:
            metrics = wifi_radar or wifi_mag
            if metrics:
                if metrics.motion_heuristic == "ACTIVE":
                    wifi_activity_noted = True
                    supporting.append(f"Wi-Fi CSI subcarrier variance elevated (heuristic: ACTIVE, var: {metrics.csi_amplitude_variance})")
                elif metrics.motion_heuristic == "SUBTLE":
                    wifi_activity_noted = True
                    supporting.append(f"Wi-Fi CSI reports subtle channel fluctuation")
                else:
                    if radar_detected_targets and presence_state == "MOVING_TARGET":
                        contradicting.append("Wi-Fi CSI variance is quiet while radar tracks motion")
                    else:
                        supporting.append("Wi-Fi channel state baseline quiet")
        else:
            contradicting.append("Wi-Fi telemetry stale or offline")

        # 3. Evaluate Magnetometer Evidence & Threat
        significant_mag_deviation = False
        if mag_active and mag:
            if mag.calibration_status == "CALIBRATED":
                # Significant disturbance threshold (typically > 3.0 uT above background)
                if mag.delta_magnitude > 3.0:
                    significant_mag_deviation = True
                    supporting.append(f"Magnetic disturbance detected: +{mag.delta_magnitude} uT above calibrated baseline")
                    if threat_state == "NONE":
                        threat_state = "ELEVATED_FERROUS"
                else:
                    supporting.append(f"Magnetic field stable (deviation: {mag.delta_magnitude} uT within normal range)")
            elif mag.calibration_status == "UNCALIBRATED":
                contradicting.append("Magnetometer not yet calibrated to ambient baseline")
            elif mag.calibration_status == "INCOMPATIBLE":
                contradicting.append("Magnetometer hardware incompatible (MPU-6050 lacks magnetic sensor)")
        else:
            contradicting.append("Magnetometer stream stale or unsupported")

        # 4. Integrate MTC-1 ML Model Evidence
        if mtc and mtc.status == "READY":
            supporting.append(f"MTC-1 Model: predicted '{mtc.predicted_class}' ({mtc.confidence_percent}%) [Threat: {mtc.threat_level}]")
            if mtc.threat_level in ["HIGH", "CRITICAL"] and significant_mag_deviation:
                threat_state = mtc.threat_level
        elif mtc and mtc.status == "AWAITING_RANGE":
            contradicting.append("MTC-1 model awaiting target range measurement for dipole evaluation")

        # 5. Formulate Transparent Synthesis
        if not radar_active and not wifi_active and not mag_active:
            presence_state = "OFFLINE"
            threat_state = "UNKNOWN"
            explainable_summary = "All sensor streams are offline or stale. No valid telemetry."
        elif radar_detected_targets and significant_mag_deviation:
            explainable_summary = f"Multi-modal confirmation: Target detected at {closest_distance}m correlated with +{mag.delta_magnitude} uT magnetic disturbance."
        elif radar_detected_targets:
            explainable_summary = f"Radar confirms presence at {closest_distance}m. Magnetic baseline normal (no anomalous ferrous mass detected)."
        elif wifi_activity_noted and not radar_detected_targets:
            presence_state = "WIFI_RF_ACTIVITY_ONLY"
            explainable_summary = "Wi-Fi channel disturbance observed without confirmed radar target. Possible peripheral movement or multipath interference."
        elif significant_mag_deviation and not radar_detected_targets:
            explainable_summary = f"Magnetic disturbance (+{mag.delta_magnitude} uT) without radar target. Possible static structural metal or equipment activation."
        else:
            explainable_summary = "Ambient baseline quiet. No human targets or significant magnetic anomalies detected."

        return FusionState(
            presence_state=presence_state,
            threat_state=threat_state,
            explainable_summary=explainable_summary,
            supporting_sensors=supporting,
            conflicting_sensors=contradicting,
            freshness=freshness,
            tracked_target_count=target_count,
            closest_target_distance_m=closest_distance,
            estimated_motion_speed_ms=top_speed,
            fusion_timestamp=now
        )

fusion_engine = SensorFusionEngine()
