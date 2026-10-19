"""
Wi-Fi CSI (Channel State Information) & RSSI Telemetry Processor.
Computes subcarrier amplitude statistics and heuristic motion indicators.
Important: CSI metrics are transparent heuristics, not a validated human location classifier.
"""

from typing import List, Optional
import math
from backend.schemas import WiFiMetrics

class CSIProcessor:
    def __init__(self):
        self.packet_count = 0
        self.last_timestamp = 0.0
        self.packet_rate = 0.0
        self.amplitude_history: List[float] = []
        self.max_history = 30
        
    def process(self, 
                rssi_dbm: Optional[int], 
                csi_packet_count: int, 
                subcarrier_amplitudes: Optional[List[float]] = None,
                now_ts: float = 0.0,
                receiver_id: str = "rx1") -> WiFiMetrics:
        """
        Processes CSI and RSSI data.
        """
        self.packet_count = csi_packet_count
        
        # Calculate subcarrier variance if subcarriers provided
        variance: Optional[float] = None
        has_csi = False
        format_str = "RAW_RSSI_ONLY"

        if subcarrier_amplitudes and len(subcarrier_amplitudes) > 1:
            has_csi = True
            format_str = f"SUBCA_AMP_VAR ({len(subcarrier_amplitudes)} SC)"
            mean_amp = sum(subcarrier_amplitudes) / len(subcarrier_amplitudes)
            variance = sum((a - mean_amp) ** 2 for a in subcarrier_amplitudes) / len(subcarrier_amplitudes)
            variance = round(variance, 4)
            self.amplitude_history.append(variance)
            if len(self.amplitude_history) > self.max_history:
                self.amplitude_history.pop(0)

        # Activity heuristic from variance
        motion_heuristic = "QUIET"
        if variance is not None:
            if variance > 4.0:
                motion_heuristic = "ACTIVE"
            elif variance > 1.2:
                motion_heuristic = "SUBTLE"
            else:
                motion_heuristic = "QUIET"
                
        return WiFiMetrics(
            receiver_id=receiver_id,
            rssi_dbm=rssi_dbm,
            raw_rssi=rssi_dbm,
            csi_available=has_csi,
            feature_format=format_str,
            csi_packet_count=csi_packet_count,
            csi_packet_rate=self.packet_rate,
            csi_amplitude_variance=variance,
            derived_variance=variance,
            packet_loss_pct=0.0,
            timestamp_quality="GOOD" if now_ts > 0 else "STALE",
            connection_status="CONNECTED" if rssi_dbm is not None else "OFFLINE",
            motion_heuristic=motion_heuristic,
            is_model_inferred=False # Explicitly unvalidated
        )
