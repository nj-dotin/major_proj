"""
Tests for NewVision FastAPI endpoints, session management, and demo mode toggle.
"""

import pytest
from starlette.testclient import TestClient
from backend.main import app

client = TestClient(app)

def test_health_endpoint():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["project"] == "NewVision"
    assert "mtc1_loaded" in data
    assert "is_demo_mode" in data

def test_telemetry_endpoint():
    response = client.get("/api/telemetry")
    assert response.status_code == 200
    data = response.json()
    assert "radar" in data
    assert "magnetometer" in data
    assert "mtc" in data
    assert "fusion" in data

def test_mode_toggle():
    # Get current mode
    r1 = client.get("/api/health").json()
    init_mode = r1["is_demo_mode"]

    # Toggle
    r2 = client.post("/api/mode/toggle")
    assert r2.status_code == 200
    assert r2.json()["is_demo_mode"] != init_mode

    # Toggle back
    r3 = client.post("/api/mode/toggle")
    assert r3.status_code == 200
    assert r3.json()["is_demo_mode"] == init_mode

def test_session_lifecycle_and_export():
    # Check status initially
    r_stat = client.get("/api/session/status")
    assert r_stat.status_code == 200
    assert "recording" in r_stat.json()

    # Start session
    r_start = client.post("/api/session/start")
    assert r_start.status_code == 200
    assert r_start.json()["status"] == "RECORDING_STARTED"

    # Status during recording
    r_stat2 = client.get("/api/session/status")
    assert r_stat2.status_code == 200
    assert r_stat2.json()["recording"] is True

    # Fetch telemetry to populate session
    client.get("/api/telemetry")
    client.get("/api/telemetry")

    # Stop session
    r_stop = client.post("/api/session/stop")
    assert r_stop.status_code == 200
    assert r_stop.json()["status"] == "RECORDING_STOPPED"


    # Export JSON
    r_json = client.get("/api/session/export/json")
    assert r_json.status_code == 200
    assert isinstance(r_json.json(), list)

    # Export CSV
    r_csv = client.get("/api/session/export/csv")
    assert r_csv.status_code == 200
    assert "timestamp" in r_csv.text

def test_simulator_object_endpoint():
    r = client.post("/api/simulator/object", json={"object_type": "rifle"})
    assert r.status_code == 200
    assert r.json()["simulated_object"] == "rifle"

def test_magnetometer_calibrate_endpoint():
    r = client.post("/api/magnetometer/calibrate")
    assert r.status_code == 200
    assert r.json()["success"] is True

def test_dashboard_html_served():
    response = client.get("/")
    assert response.status_code == 200
    assert "NEWVISION" in response.text
    assert "radarCanvas" in response.text

def test_newview_html_served():
    response = client.get("/newview")
    assert response.status_code == 200
    assert "NEWVIEW" in response.text
    assert "spatialCanvas" in response.text
    assert "2D PLAN" in response.text
    assert "3D ORBIT" in response.text

def test_spatial_calibration_endpoints():
    # GET spatial calibration
    r_get = client.get("/api/calibration/spatial")
    assert r_get.status_code == 200
    data = r_get.json()
    assert "rx1_position" in data
    assert "radar_position" in data

    # POST spatial calibration update
    new_cfg = {
        "rx1_position": {"x": -2.0, "y": 3.0},
        "tx_position": {"x": 0.0, "y": 5.0}
    }
    r_post = client.post("/api/calibration/spatial", json=new_cfg)
    assert r_post.status_code == 200
    assert r_post.json()["success"] is True

