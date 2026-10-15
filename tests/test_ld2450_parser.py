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
