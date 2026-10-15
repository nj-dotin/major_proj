"""
Versioned Telemetry & API Schemas for NewVision.
Handles ingestion from ESP32 nodes, validation, and dashboard streaming.
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
import time

class DeviceDiagnostics(BaseModel):
    device_id: str = Field(..., description="Unique device ID, e.g. 'esp32_radar_csi' or 'esp32_mag_csi'")
    role: str = Field(..., description="Role: 'radar_csi', 'magnetometer_csi', 'traffic_ap'")
    firmware_version: str = Field(default="1.0.0")
    uptime_ms: int = Field(default=0)
    seq: int = Field(default=0, description="Monotonically increasing sequence number")
    free_heap: Optional[int] = None
    wifi_connected: bool = True
    ip_address: Optional[str] = None
    parser_errors: int = 0
    packet_rate_hz: float = 0.0

class WiFiMetrics(BaseModel):
    rssi_dbm: Optional[int] = Field(default=None, description="Wi-Fi RSSI in dBm")
    csi_packet_count: int = Field(default=0, description="Total CSI frames captured")
    csi_packet_rate: float = Field(default=0.0, description="CSI packets/sec")
    csi_amplitude_variance: Optional[float] = Field(
        default=None, 
        description="Variance across subcarrier amplitudes (motion metric)"
    )
    motion_heuristic: str = Field(
        default="QUIET", 
        description="Wi-Fi motion heuristic: QUIET, SUBTLE, ACTIVE. Not a validated coordinate detector."
    )
    is_model_inferred: bool = Field(
        default=False,
        description="Always False until a validated CSI classifier is deployed"
    )

class RadarTarget(BaseModel):
    target_id: int = Field(..., description="Target slot (1, 2, or 3)")
    x_mm: int = Field(..., description="Lateral position in mm (-3000 to +3000)")
    y_mm: int = Field(..., description="Distance in mm (0 to 6000)")
    x_m: float = Field(..., description="Lateral position in meters")
    y_m: float = Field(..., description="Distance in meters")
    distance_m: float = Field(..., description="Euclidean distance in meters")
    speed_cms: int = Field(..., description="Radial speed in cm/s (positive=away, negative=approaching)")
    speed_ms: float = Field(..., description="Speed in m/s")
    resolution_mm: int = Field(default=0, description="Distance resolution/gate")
    is_valid: bool = True

class RadarTelemetry(BaseModel):
    target_count: int = Field(default=0, description="Number of detected targets (0-3)")
    targets: List[RadarTarget] = Field(default_factory=list)
    raw_frame_hex: Optional[str] = None
    parser_errors: int = 0
    sensor_status: str = Field(default="ACTIVE", description="ACTIVE, NO_DATA, DISCONNECTED")

class MagnetometerTelemetry(BaseModel):
    sensor_chip: str = Field(default="UNKNOWN", description="HMC5883L, QMC5883L, MPU9250, MPU6050_NO_MAG, SIMULATED")
    is_supported: bool = Field(default=True, description="False if sensor lacks magnetometer like MPU-6050")
    bx: float = Field(default=0.0, description="X component in microTesla (uT)")
    by: float = Field(default=0.0, description="Y component in microTesla (uT)")
    bz: float = Field(default=0.0, description="Z component in microTesla (uT)")
    magnitude: float = Field(default=0.0, description="Total field magnitude in uT")
    baseline_bx: float = 0.0
    baseline_by: float = 0.0
    baseline_bz: float = 0.0
    delta_magnitude: float = Field(default=0.0, description="Deviation from calibrated baseline in uT")
    unit: str = "uT"
    calibration_status: str = Field(default="UNCALIBRATED", description="UNCALIBRATED, CALIBRATED, INCOMPATIBLE")

class MTCInference(BaseModel):
    status: str = Field(
        default="AWAITING_RANGE", 
        description="READY, AWAITING_RANGE, UNCALIBRATED, UNAVAILABLE, SENSOR_INCOMPATIBLE"
    )
    is_validated_hardware_model: bool = Field(
        default=False,
        description="Always False for current synthetic MTC-1 model on live hardware"
    )
    predicted_class: Optional[str] = None
    confidence_percent: Optional[float] = None
    threat_level: str = "NONE"
    threat_color: str = "#00ff88"
    all_probabilities: Dict[str, float] = Field(default_factory=dict)
    derived_features: Dict[str, float] = Field(default_factory=dict)
    distance_source: str = Field(
        default="RADAR_OR_STANDOFF",
        description="Source of distance feature needed for dipole gradient computation"
    )
    explanation: str = "Model requires calibrated baseline and range estimate."

class FusionState(BaseModel):
    presence_state: str = Field(
        default="CLEAR", 
        description="CLEAR, STATIONARY_PRESENCE, MOVING_TARGET, ANOMALY_UNDER_INVESTIGATION"
    )
    threat_state: str = Field(
        default="NONE",
        description="NONE, ELEVATED_FERROUS, UNKNOWN_ANOMALY, DEMO_SIMULATED"
    )
    explainable_summary: str = "All sensor streams within ambient baseline."
    supporting_sensors: List[str] = Field(default_factory=list)
    conflicting_sensors: List[str] = Field(default_factory=list)
    freshness: Dict[str, float] = Field(default_factory=dict, description="Age in seconds for each sensor stream")
    tracked_target_count: int = 0
    closest_target_distance_m: Optional[float] = None
    estimated_motion_speed_ms: Optional[float] = None
    fusion_timestamp: float = Field(default_factory=time.time)

class TelemetryPacket(BaseModel):
    version: str = "1.0"
    timestamp: float = Field(default_factory=time.time)
    is_simulated: bool = Field(default=False, description="Explicitly True for simulated demo data")
    device: DeviceDiagnostics
    wifi: Optional[WiFiMetrics] = None
    radar: Optional[RadarTelemetry] = None
    magnetometer: Optional[MagnetometerTelemetry] = None
    mtc: Optional[MTCInference] = None

class SystemConsolidatedState(BaseModel):
    timestamp: float = Field(default_factory=time.time)
    is_demo_mode: bool = False
    system_status: str = "OPERATIONAL" # OPERATIONAL, DEGRADED, OFFLINE
    active_devices: List[str] = Field(default_factory=list)
    node_ap: Optional[DeviceDiagnostics] = None
    node_radar: Optional[DeviceDiagnostics] = None
    node_mag: Optional[DeviceDiagnostics] = None
    radar: RadarTelemetry = Field(default_factory=RadarTelemetry)
    wifi_radar_node: Optional[WiFiMetrics] = None
    wifi_mag_node: Optional[WiFiMetrics] = None
    magnetometer: MagnetometerTelemetry = Field(default_factory=MagnetometerTelemetry)
    mtc: MTCInference = Field(default_factory=MTCInference)
    fusion: FusionState = Field(default_factory=FusionState)
