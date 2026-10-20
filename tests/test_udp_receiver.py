"""
Unit tests for LiveHardwareStateManager and UDP telemetry ingestion.
Validates:
1. Sequence number progression, duplicate sequence detection, out-of-order handling.
2. Clock offset calculation between host epoch and device uptime.
3. Multi-node diagnostic states.
4. Radar target tracking integration through LD2450Tracker.
"""

import pytest
import time
from backend.services.udp_receiver import LiveHardwareStateManager
from backend.schemas import RadarTarget

def test_sequence_and_clock_tracking():
    manager = LiveHardwareStateManager()
    t0 = 1000.0
    
    # 1. First packet from nodemcu_ap (seq=1, uptime=10000ms)
    stats = manager._update_sequence_and_clock("nodemcu_ap", seq=1, uptime_ms=10000, now_ts=t0)
    assert stats["last_seq"] == 1
    assert stats["duplicates"] == 0
    assert stats["out_of_order"] == 0
    # host_ms = 1000.0 * 1000 = 1,000,000; offset = 1,000,000 - 10,000 = 990,000.0
    assert stats["clock_offset_ms"] == 990000.0

    # 2. Normal sequential packet (seq=2)
    stats = manager._update_sequence_and_clock("nodemcu_ap", seq=2, uptime_ms=10100, now_ts=t0 + 0.1)
    assert stats["last_seq"] == 2
    assert stats["duplicates"] == 0
    assert stats["out_of_order"] == 0

    # 3. Duplicate packet (seq=2 repeated)
    stats = manager._update_sequence_and_clock("nodemcu_ap", seq=2, uptime_ms=10100, now_ts=t0 + 0.105)
    assert stats["last_seq"] == 2
    assert stats["duplicates"] == 1
    assert stats["out_of_order"] == 0

    # 4. Out-of-order packet (seq=1 arrives late)
    stats = manager._update_sequence_and_clock("nodemcu_ap", seq=1, uptime_ms=10000, now_ts=t0 + 0.11)
    assert stats["duplicates"] == 1
    assert stats["out_of_order"] == 1

def test_handle_packet_diagnostics():
    manager = LiveHardwareStateManager()
    
    packet_ap = {
        "device_id": "nodemcu_ap",
        "fw_ver": "1.2.0",
        "uptime_ms": 25000,
        "seq": 105,
        "free_heap": 41200,
        "packet_rate_hz": 99.2,
        "_source_ip": "192.168.4.1"
    }
    
    manager.handle_packet(packet_ap)
    assert manager.current_state.node_ap is not None
    assert manager.current_state.node_ap.device_id == "nodemcu_ap"
    assert manager.current_state.node_ap.seq == 105
    assert manager.current_state.node_ap.ip_address == "192.168.4.1"
    assert manager.current_state.node_ap.clock_offset_ms is not None

def test_radar_packet_tracker_integration():
    manager = LiveHardwareStateManager()
    
    # Send packet with a radar target
    packet_radar = {
        "device_id": "esp32_radar_csi",
        "fw_ver": "1.0.0",
        "uptime_ms": 5000,
        "seq": 1,
        "free_heap": 178000,
        "_source_ip": "192.168.4.10",
        "targets": [
            {
                "target_id": 1,
                "x_mm": 500,
                "y_mm": 2000,
                "x_m": 0.5,
                "y_m": 2.0,
                "distance_m": 2.061,
                "speed_cms": 30,
                "speed_ms": 0.3,
                "resolution_mm": 150,
                "is_valid": True
            }
        ]
    }
    
    manager.handle_packet(packet_radar)
    assert manager.current_state.radar is not None
    assert manager.current_state.radar.target_count == 1
    target = manager.current_state.radar.targets[0]
    assert target.is_valid is True
    assert round(target.x_m, 1) == 0.5
    assert round(target.y_m, 1) == 2.0
    assert len(manager.current_state.radar.track_history) >= 1
