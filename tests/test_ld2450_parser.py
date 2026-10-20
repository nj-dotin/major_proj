"""
Tests for HLK-LD2450 24 GHz Radar UART binary frame parser.
"""

import pytest
from backend.parsers.ld2450 import LD2450StreamParser, decode_ld2450_int16, parse_ld2450_target

def test_decode_ld2450_sign_magnitude():
    # Bit 15 is 0 -> positive
    assert decode_ld2450_int16(0x01F4) == 500
    # Bit 15 is 1 -> negative (0x8000 | 500 = 0x81F4)
    assert decode_ld2450_int16(0x81F4) == -500
    # Zero
    assert decode_ld2450_int16(0x0000) == 0

def test_parse_single_target():
    # Target 1: X = -800 mm (0x8320), Y = 2400 mm (0x0960), Speed = -60 cm/s (0x803C), Res = 100 mm (0x0064)
    target_bytes = bytes([
        0x20, 0x83, # X = -800
        0x60, 0x09, # Y = 2400
        0x3C, 0x80, # Speed = -60
        0x64, 0x00  # Res = 100
    ])
    target = parse_ld2450_target(target_id=1, raw_bytes=target_bytes)
    assert target is not None
    assert target.x_mm == -800
    assert target.y_mm == 2400
    assert target.x_m == -0.8
    assert target.y_m == 2.4
    assert target.speed_cms == -60
    assert target.speed_ms == -0.6
    assert target.distance_m == pytest.approx(2.53, 0.01)

def test_stream_parser_valid_frame():
    parser = LD2450StreamParser()
    # Build complete 30-byte frame
    # Header: AA FF 03 00
    header = bytes([0xAA, 0xFF, 0x03, 0x00])
    # Target 1: X=500mm, Y=1500mm, Speed=20cm/s, Res=100
    t1 = bytes([0xF4, 0x01, 0xDC, 0x05, 0x14, 0x00, 0x64, 0x00])
    # Target 2 & 3: empty
    t2 = bytes([0x00] * 8)
    t3 = bytes([0x00] * 8)
    # Tail: 55 CC
    tail = bytes([0x55, 0xCC])
    
    frame = header + t1 + t2 + t3 + tail
    assert len(frame) == 30
    
    telemetry = parser.feed(frame)
    assert len(telemetry) == 1
    assert telemetry[0].target_count == 1
    assert telemetry[0].targets[0].x_mm == 500
    assert telemetry[0].targets[0].y_mm == 1500

def test_stream_parser_fragmented_and_garbage():
    parser = LD2450StreamParser()
    garbage = bytes([0x12, 0x34, 0x56])
    header = bytes([0xAA, 0xFF, 0x03, 0x00])
    t1 = bytes([0xF4, 0x01, 0xDC, 0x05, 0x14, 0x00, 0x64, 0x00])
    t_empty = bytes([0x00] * 16)
    tail = bytes([0x55, 0xCC])
    full_frame = header + t1 + t_empty + tail

    # Feed in two separate chunks
    chunk1 = garbage + full_frame[:15]
    chunk2 = full_frame[15:]

    res1 = parser.feed(chunk1)
    assert len(res1) == 0

    res2 = parser.feed(chunk2)
    assert len(res2) == 1
    assert res2[0].target_count == 1

def test_tracker_continuity_and_coasting():
    from backend.parsers.ld2450 import LD2450Tracker
    from backend.schemas import RadarTarget
    
    tracker = LD2450Tracker(max_misses=3, max_distance_gate=1.0, dt=0.05)
    
    # Frame 1: Target detected at X=0.5m, Y=2.0m, moving +0.2 m/s
    t1 = RadarTarget(target_id=1, x_mm=500, y_mm=2000, x_m=0.5, y_m=2.0, distance_m=2.06, speed_cms=20, speed_ms=0.2, resolution_mm=100)
    out1 = tracker.update([t1])
    assert len(out1) == 1
    assert out1[0].target_id == 1
    assert out1[0].x_m == pytest.approx(0.5, 0.05)
    
    # Frame 2: Target moves to X=0.51m, Y=2.01m
    t2 = RadarTarget(target_id=1, x_mm=510, y_mm=2010, x_m=0.51, y_m=2.01, distance_m=2.07, speed_cms=20, speed_ms=0.2, resolution_mm=100)
    out2 = tracker.update([t2])
    assert len(out2) == 1
    assert out2[0].target_id == 1
    
    # Frame 3: Dropout! No radar measurement (e.g. multipath cancellation)
    out3 = tracker.update([])
    assert len(out3) == 1  # Still coasting!
    assert out3[0].target_id == 1  # Track ID preserved
    
    # Frame 4: Target reappears at X=0.53m, Y=2.03m
    t4 = RadarTarget(target_id=1, x_mm=530, y_mm=2030, x_m=0.53, y_m=2.03, distance_m=2.09, speed_cms=20, speed_ms=0.2, resolution_mm=100)
    out4 = tracker.update([t4])
    assert len(out4) == 1
    assert out4[0].target_id == 1  # Re-associated without ID jumping!
    
    # 4 consecutive misses -> track dropped
    tracker.update([])
    tracker.update([])
    tracker.update([])
    out_lost = tracker.update([])
    assert len(out_lost) == 0

def test_stream_parser_malformed_frames():
    parser = LD2450StreamParser(enable_tracking_filter=False)
    # Header correct, but tail corrupted
    bad_frame = bytes([0xAA, 0xFF, 0x03, 0x00]) + bytes([0x00]*24) + bytes([0x12, 0x34])
    res = parser.feed(bad_frame)
    assert len(res) == 0
    assert parser.error_count > 0

