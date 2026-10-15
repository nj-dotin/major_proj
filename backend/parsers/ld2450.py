"""
HLK-LD2450 24 GHz Radar Protocol Parser
Decodes standard UART target tracking frames:
Header: 0xAA 0xFF 0x03 0x00 (4 bytes)
Target 1..3: 8 bytes each (24 bytes)
Tail:   0x55 0xCC (2 bytes)
Total Frame Length: 30 bytes
"""

import math
from typing import List, Tuple, Optional
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

class LD2450StreamParser:
    """
    Stream parser that extracts and decodes frames from continuous UART byte buffers.
    """
    def __init__(self):
        self.buffer = bytearray()
        self.error_count = 0
        
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
                
                targets: List[RadarTarget] = []
                # 3 targets at offset 4, 12, 20
                for i in range(3):
                    offset = 4 + (i * 8)
                    t_bytes = frame_data[offset : offset + 8]
                    target = parse_ld2450_target(target_id=i + 1, raw_bytes=t_bytes)
                    if target:
                        targets.append(target)
                        
                telemetry = RadarTelemetry(
                    target_count=len(targets),
                    targets=targets,
                    raw_frame_hex=frame_data.hex(),
                    parser_errors=self.error_count,
                    sensor_status="ACTIVE" if len(targets) > 0 else "NO_TARGETS"
                )
                telemetry_frames.append(telemetry)
            else:
                # Bad tail, skip one byte and re-sync
                self.error_count += 1
                self.buffer = self.buffer[1:]
                
        return telemetry_frames
