"""
In-memory bounded telemetry ring-buffer and session recorder.
Supports high-throughput real-time streaming, CSV/JSON session export.
"""

import time
import csv
import io
import json
from collections import deque
from typing import List, Dict, Any, Optional
from backend.schemas import SystemConsolidatedState, TelemetryPacket

class TelemetryBufferService:
    def __init__(self, max_size: int = 1000):
        self.max_size = max_size
        self.history: deque = deque(maxlen=max_size)
        self.is_recording = False
        self.recording_started_at: Optional[float] = None
        self.recorded_sessions: List[Dict[str, Any]] = []

    def push(self, state: SystemConsolidatedState):
        self.history.append(state)
        if self.is_recording:
            self.recorded_sessions.append(state.model_dump())

    def get_recent(self, count: int = 100) -> List[Dict[str, Any]]:
        items = list(self.history)[-count:]
        return [item.model_dump() for item in items]

    def start_recording(self):
        self.is_recording = True
        self.recording_started_at = time.time()
        self.recorded_sessions = []
        return {"status": "RECORDING_STARTED", "timestamp": self.recording_started_at}

    def stop_recording(self):
        self.is_recording = False
        duration = round(time.time() - (self.recording_started_at or time.time()), 2)
        count = len(self.recorded_sessions)
        return {
            "status": "RECORDING_STOPPED", 
            "duration_sec": duration, 
            "sample_count": count
        }

    def clear_session(self):
        self.recorded_sessions = []
        self.history.clear()
        return {"status": "CLEARED"}

    def export_json(self) -> str:
        return json.dumps(self.recorded_sessions, indent=2)

    def export_csv(self) -> str:
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Header
        headers = [
            "timestamp", "is_demo_mode", "presence_state", "threat_state",
            "radar_target_count", "closest_target_dist_m", "target_speed_ms",
            "radar_rssi_dbm", "mag_rssi_dbm", "csi_variance",
            "mag_bx", "mag_by", "mag_bz", "mag_magnitude", "mag_delta",
            "mtc_status", "mtc_predicted_class", "mtc_confidence"
        ]
        writer.writerow(headers)

        for s in self.recorded_sessions:
            fusion = s.get("fusion", {})
            radar = s.get("radar", {})
            targets = radar.get("targets", [])
            t0 = targets[0] if targets else {}
            
            wifi_r = s.get("wifi_radar_node") or {}
            wifi_m = s.get("wifi_mag_node") or {}
            mag = s.get("magnetometer") or {}
            mtc = s.get("mtc") or {}
            
            row = [
                s.get("timestamp"),
                s.get("is_demo_mode"),
                fusion.get("presence_state"),
                fusion.get("threat_state"),
                radar.get("target_count", 0),
                t0.get("distance_m", ""),
                t0.get("speed_ms", ""),
                wifi_r.get("rssi_dbm", ""),
                wifi_m.get("rssi_dbm", ""),
                wifi_r.get("csi_amplitude_variance", ""),
                mag.get("bx", ""),
                mag.get("by", ""),
                mag.get("bz", ""),
                mag.get("magnitude", ""),
                mag.get("delta_magnitude", ""),
                mtc.get("status", ""),
                mtc.get("predicted_class", ""),
                mtc.get("confidence_percent", "")
            ]
            writer.writerow(row)

        return output.getvalue()

telemetry_buffer = TelemetryBufferService()
