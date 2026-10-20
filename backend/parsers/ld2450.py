"""
HLK-LD2450 24 GHz Radar Protocol Parser
Decodes standard UART target tracking frames:
Header: 0xAA 0xFF 0x03 0x00 (4 bytes)
Target 1..3: 8 bytes each (24 bytes)
Tail:   0x55 0xCC (2 bytes)
Total Frame Length: 30 bytes
"""

import math
from typing import List, Tuple, Optional, Dict
from backend.schemas import RadarTarget, RadarTelemetry

FRAME_HEADER = bytes([0xAA, 0xFF, 0x03, 0x00])
FRAME_TAIL = bytes([0x55, 0xCC])
FRAME_LENGTH = 30

def decode_ld2450_int16(raw_val: int) -> int:
    """
    Decodes LD2450 sign-magnitude 16-bit integer.
    Per HLK-LD2450 manual:
    Bit 15 is sign bit (1 = negative, 0 = positive), bits 0-14 are magnitude.
    """
    if raw_val & 0x8000:
        return -(raw_val & 0x7FFF)
    return raw_val & 0x7FFF

def parse_ld2450_target(target_id: int, raw_bytes: bytes) -> Optional[RadarTarget]:
    """
    Parses an 8-byte target block from the LD2450 frame:
    Bytes 0-1: X coordinate (mm)
    Bytes 2-3: Y coordinate (mm)
    Bytes 4-5: Speed (cm/s)
    Bytes 6-7: Distance resolution (mm)
    """
    if len(raw_bytes) < 8:
        return None
        
    raw_x = raw_bytes[0] | (raw_bytes[1] << 8)
    raw_y = raw_bytes[2] | (raw_bytes[3] << 8)
    raw_speed = raw_bytes[4] | (raw_bytes[5] << 8)
    raw_res = raw_bytes[6] | (raw_bytes[7] << 8)
    
    x_mm = decode_ld2450_int16(raw_x)
    y_mm = decode_ld2450_int16(raw_y)
    speed_cms = decode_ld2450_int16(raw_speed)
    resolution_mm = raw_res
    
    # Check if target is empty / inactive
    # In LD2450, an inactive target slot has 0 for coordinates and resolution
    if x_mm == 0 and y_mm == 0 and speed_cms == 0 and resolution_mm == 0:
        return None
        
    x_m = round(x_mm / 1000.0, 3)
    y_m = round(y_mm / 1000.0, 3)
    speed_ms = round(speed_cms / 100.0, 3)
    distance_m = round(math.sqrt(x_m**2 + y_m**2), 3)
    
    return RadarTarget(
        target_id=target_id,
        x_mm=x_mm,
        y_mm=y_mm,
        x_m=x_m,
        y_m=y_m,
        distance_m=distance_m,
        speed_cms=speed_cms,
        speed_ms=speed_ms,
        resolution_mm=resolution_mm,
        is_valid=True
    )

class TrackedObject:
    """
    Internal state for a tracked radar target with an Alpha-Beta filter.
    State: [x, y, vx, vy] in meters and m/s.
    """
    def __init__(self, track_id: int, x: float, y: float, vx: float = 0.0, vy: float = 0.0):
        self.track_id = track_id
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.hits = 1
        self.misses = 0
        self.state = "CONFIRMED" if self.hits >= 2 else "TENTATIVE"
        self.history: List[dict] = []
        self.append_history()

    def predict(self, dt: float = 0.05):
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.misses += 1

    def update(self, meas_x: float, meas_y: float, speed_ms: float, dt: float = 0.05, alpha: float = 0.7, beta: float = 0.4):
        residual_x = meas_x - self.x
        residual_y = meas_y - self.y

        self.x += alpha * residual_x
        self.y += alpha * residual_y

        if dt > 0:
            self.vx += (beta / dt) * residual_x
            self.vy += (beta / dt) * residual_y

        self.hits += 1
        self.misses = 0
        if self.hits >= 2:
            self.state = "CONFIRMED"
        self.append_history()

    def append_history(self):
        self.history.append({
            "x": round(self.x, 3),
            "y": round(self.y, 3),
            "speed": round(math.hypot(self.vx, self.vy), 3)
        })
        if len(self.history) > 60:
            self.history.pop(0)

class LD2450Tracker:
    """
    Track continuity filter for LD2450 radar.
    Maintains persistent target IDs, smooths noisy coordinate jitter with an alpha-beta filter,
    and coasts tracks over brief signal dropouts (up to max_misses frames).
    """
    def __init__(self, max_misses: int = 5, max_distance_gate: float = 1.2, dt: float = 0.05):
        self.tracks: Dict[int, TrackedObject] = {}
        self.next_track_id = 1
        self.max_misses = max_misses
        self.max_distance_gate = max_distance_gate
        self.dt = dt

    def update(self, raw_targets: List[RadarTarget]) -> List[RadarTarget]:
        # 1. Prediction step for existing tracks
        for track in self.tracks.values():
            track.predict(self.dt)

        unmatched_detections = list(raw_targets)
        matched_track_ids = set()

        # 2. Association step (Greedy Nearest Neighbor)
        for track_id, track in list(self.tracks.items()):
            best_det_idx = -1
            best_dist = float('inf')

            for idx, det in enumerate(unmatched_detections):
                d = math.hypot(track.x - det.x_m, track.y - det.y_m)
                if d < best_dist and d <= self.max_distance_gate:
                    best_dist = d
                    best_det_idx = idx

            if best_det_idx != -1:
                det = unmatched_detections.pop(best_det_idx)
                track.update(det.x_m, det.y_m, det.speed_ms, self.dt)
                matched_track_ids.add(track_id)

        # 3. Initiation step for unmatched detections
        for det in unmatched_detections:
            new_id = self.next_track_id
            self.next_track_id += 1
            if self.next_track_id > 999:
                self.next_track_id = 1
            self.tracks[new_id] = TrackedObject(
                track_id=new_id,
                x=det.x_m,
                y=det.y_m,
                vx=0.0,
                vy=det.speed_ms
            )

        # 4. Pruning step for lost tracks
        dead_tracks = [tid for tid, t in self.tracks.items() if t.misses > self.max_misses or t.y < 0 or t.y > 8.0]
        for tid in dead_tracks:
            del self.tracks[tid]

        # 5. Output confirmed/coasting targets
        output_targets: List[RadarTarget] = []
        for tid, track in self.tracks.items():
            if track.misses <= self.max_misses:
                dist_m = round(math.hypot(track.x, track.y), 3)
                v_total = round(math.hypot(track.vx, track.vy), 3)
                output_targets.append(RadarTarget(
                    target_id=track.track_id,
                    x_mm=int(track.x * 1000),
                    y_mm=int(track.y * 1000),
                    x_m=round(track.x, 3),
                    y_m=round(track.y, 3),
                    distance_m=dist_m,
                    speed_cms=int(track.vy * 100),
                    speed_ms=round(track.vy, 3),
                    resolution_mm=100,
                    is_valid=True
                ))

        return output_targets

class LD2450StreamParser:
    """
    Stream parser that extracts and decodes frames from continuous UART byte buffers,
    with an integrated tracking continuity filter.
    """
    def __init__(self, enable_tracking_filter: bool = True):
        self.buffer = bytearray()
        self.error_count = 0
        self.enable_tracking_filter = enable_tracking_filter
        self.tracker = LD2450Tracker() if enable_tracking_filter else None
        
    def feed(self, data: bytes) -> List[RadarTelemetry]:
        self.buffer.extend(data)
        telemetry_frames: List[RadarTelemetry] = []
        
        while len(self.buffer) >= FRAME_LENGTH:
            # Find header
            header_idx = self.buffer.find(FRAME_HEADER)
            if header_idx == -1:
                # Keep last 3 bytes in case header spans across chunks
                self.buffer = self.buffer[-3:]
                break
                
            if header_idx > 0:
                # Discard garbage before header
                self.buffer = self.buffer[header_idx:]
                
            if len(self.buffer) < FRAME_LENGTH:
                break
                
            # Check tail
            if self.buffer[FRAME_LENGTH - 2 : FRAME_LENGTH] == FRAME_TAIL:
                frame_data = bytes(self.buffer[:FRAME_LENGTH])
                self.buffer = self.buffer[FRAME_LENGTH:]
                
                raw_targets: List[RadarTarget] = []
                # 3 targets at offset 4, 12, 20
                for i in range(3):
                    offset = 4 + (i * 8)
                    t_bytes = frame_data[offset : offset + 8]
                    target = parse_ld2450_target(target_id=i + 1, raw_bytes=t_bytes)
                    if target:
                        raw_targets.append(target)
                        
                # Filter targets using tracker if enabled
                if self.tracker is not None:
                    tracked_targets = self.tracker.update(raw_targets)
                else:
                    tracked_targets = raw_targets
                
                # Check data quality based on parser errors and target coordinates
                data_quality = "HIGH QUALITY"
                if self.error_count > 5:
                    data_quality = "DEGRADED (SERIAL NOISE)"
                elif len(tracked_targets) == 0:
                    data_quality = "CLEAR (NO TARGETS)"

                # Assemble track history
                history_list: List[dict] = []
                if self.tracker is not None:
                    for t in self.tracker.tracks.values():
                        history_list.extend(t.history[-20:])

                telemetry = RadarTelemetry(
                    target_count=len(tracked_targets),
                    targets=tracked_targets,
                    raw_frame_hex=frame_data.hex(),
                    parser_errors=self.error_count,
                    sensor_status="ACTIVE" if len(tracked_targets) > 0 else "NO_TARGETS",
                    data_quality=data_quality,
                    track_history=history_list
                )
                telemetry_frames.append(telemetry)
            else:
                # Bad tail, skip one byte and re-sync
                self.error_count += 1
                self.buffer = self.buffer[1:]
                
        return telemetry_frames

