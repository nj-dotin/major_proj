"""
Wi-Fi CSI (Channel State Information) & RSSI Telemetry Processor.
Computes subcarrier amplitude statistics and heuristic motion indicators.
Important: CSI metrics are transparent heuristics, not a validated human location classifier.
"""

from typing import List, Optional
import math
from backend.schemas import WiFiMetrics

class CSIProcessor:
    def __init__(self, receiver_id: str = "rx1"):
        self.receiver_id = receiver_id
        self.packet_count = 0
        self.last_timestamp = 0.0
        self.packet_rate = 0.0
        self.amplitude_history: List[float] = []
        self.rssi_history: List[int] = []
        self.max_history = 30
        
    def process(self, 
                rssi_dbm: Optional[int], 
                csi_packet_count: int, 
                subcarrier_amplitudes: Optional[List[float]] = None,
                now_ts: float = 0.0,
                receiver_id: Optional[str] = None) -> WiFiMetrics:
        """
        Processes CSI and RSSI data with dynamic packet rate calculation,
        subcarrier amplitude variance, and rolling RSSI variance heuristics.
        """
        rx_id = receiver_id or self.receiver_id

        # Update dynamic packet rate
        if now_ts > 0 and self.last_timestamp > 0:
            dt = now_ts - self.last_timestamp
            if dt >= 0.1:
                delta_pkts = csi_packet_count - self.packet_count
                if delta_pkts >= 0:
                    self.packet_rate = round(delta_pkts / dt, 1)
                self.packet_count = csi_packet_count
                self.last_timestamp = now_ts
        elif now_ts > 0:
            self.last_timestamp = now_ts
            self.packet_count = csi_packet_count
        else:
            self.packet_count = csi_packet_count

        # Maintain rolling RSSI history
        if rssi_dbm is not None:
            self.rssi_history.append(rssi_dbm)
            if len(self.rssi_history) > self.max_history:
                self.rssi_history.pop(0)

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

        # Derived rolling signal variance (from subcarriers, or rolling RSSI if subcarriers unavailable)
        derived_variance: Optional[float] = None
        if variance is not None:
            derived_variance = variance
        elif len(self.rssi_history) >= 3:
            mean_rssi = sum(self.rssi_history) / len(self.rssi_history)
            derived_variance = round(sum((r - mean_rssi) ** 2 for r in self.rssi_history) / len(self.rssi_history), 3)

        # Activity heuristic from subcarrier or RSSI variance
        motion_heuristic = "QUIET"
        if variance is not None:
            if variance > 4.0:
                motion_heuristic = "ACTIVE"
            elif variance > 1.2:
                motion_heuristic = "SUBTLE"
            else:
                motion_heuristic = "QUIET"
        elif derived_variance is not None:
            if derived_variance > 3.0:
                motion_heuristic = "ACTIVE"
            elif derived_variance > 0.8:
                motion_heuristic = "SUBTLE"
            else:
                motion_heuristic = "QUIET"
                
        return WiFiMetrics(
            receiver_id=rx_id,
            rssi_dbm=rssi_dbm,
            raw_rssi=rssi_dbm,
            csi_available=has_csi,
            feature_format=format_str,
            csi_packet_count=csi_packet_count,
            csi_packet_rate=self.packet_rate,
            csi_amplitude_variance=variance,
            derived_variance=derived_variance,
            packet_loss_pct=0.0,
            timestamp_quality="GOOD" if now_ts > 0 else "STALE",
            connection_status="CONNECTED" if rssi_dbm is not None else "OFFLINE",
            motion_heuristic=motion_heuristic,
            is_model_inferred=False  # Explicitly unvalidated
        )
