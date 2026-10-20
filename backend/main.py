"""
NewVision Backend — FastAPI Application.
Provides:
- Real-time WebSockets (/ws/telemetry) at 20 Hz
- High-throughput UDP ingestion (port 5005)
- REST API (/api/health, /api/telemetry, /api/mode, /api/session/*)
- Tactical Web Dashboard serving
"""

import asyncio
import os
import time
import json
import logging
from contextlib import asynccontextmanager
from typing import Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from backend.config import settings
from backend.schemas import SystemConsolidatedState
from backend.services.simulator import demo_simulator
from backend.services.udp_receiver import live_hardware_manager, UDPIngestionProtocol
from backend.services.telemetry_buffer import telemetry_buffer
from backend.models.mtc1_loader import mtc1_service

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("newvision.api")

# System operational mode
SYSTEM_STATE = {
    "is_demo_mode": True,  # Default to demo mode for immediate testing without hardware
    "active_websockets": set()
}

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Start UDP ingestion server
    loop = asyncio.get_running_loop()
    transport = None
    try:
        transport, _ = await loop.create_datagram_endpoint(
            lambda: UDPIngestionProtocol(on_packet_callback=live_hardware_manager.handle_packet),
            local_addr=(settings.HOST, settings.UDP_PORT)
        )
        logger.info(f"UDP listener bound to {settings.HOST}:{settings.UDP_PORT}")
    except Exception as e:
        logger.warning(f"Could not bind UDP listener on port {settings.UDP_PORT}: {e}")

    # Start background WebSocket broadcaster task
    broadcast_task = asyncio.create_task(telemetry_broadcaster_task())
    
    yield
    
    # Shutdown
    broadcast_task.cancel()
    if transport:
        transport.close()
    logger.info("NewVision backend shutdown complete.")

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Background Telemetry Streamer ──────────────────────────────────────────

async def telemetry_broadcaster_task():
    """Broadcasts consolidated telemetry to WebSocket clients at 20 Hz."""
    interval = 1.0 / settings.WS_PUSH_RATE_HZ
    while True:
        try:
            if SYSTEM_STATE["is_demo_mode"]:
                state = demo_simulator.generate_tick()
            else:
                state = live_hardware_manager.current_state
                state.is_demo_mode = False

            # Always push to telemetry buffer for charts & recording
            telemetry_buffer.push(state)

            # Broadcast to active WebSockets
            active_ws: Set[WebSocket] = SYSTEM_STATE["active_websockets"]
            if active_ws:
                payload = state.model_dump_json()
                disconnected = set()
                for ws in active_ws:
                    try:
                        await ws.send_text(payload)
                    except Exception:
                        disconnected.add(ws)
                active_ws.difference_update(disconnected)

            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in telemetry broadcaster: {e}")
            await asyncio.sleep(interval)

# ── REST Endpoints ─────────────────────────────────────────────────────────

@app.get("/api/health")
def api_health():
    return {
        "project": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "mode": "DEMO / SIMULATED" if SYSTEM_STATE["is_demo_mode"] else "LIVE HARDWARE",
        "is_demo_mode": SYSTEM_STATE["is_demo_mode"],
        "mtc1_loaded": mtc1_service.is_loaded,
        "mtc1_classes": list(mtc1_service.model_stats.get("classes", [])),
        "udp_port": settings.UDP_PORT,
        "buffer_size": len(telemetry_buffer.history),
        "is_recording": telemetry_buffer.is_recording
    }

@app.get("/api/telemetry")
def api_get_telemetry():
    if SYSTEM_STATE["is_demo_mode"]:
        state = demo_simulator.generate_tick()
    else:
        state = live_hardware_manager.current_state
        state.is_demo_mode = False
    return state.model_dump()

@app.post("/api/mode/toggle")
def api_toggle_mode():
    SYSTEM_STATE["is_demo_mode"] = not SYSTEM_STATE["is_demo_mode"]
    mode_str = "DEMO / SIMULATED" if SYSTEM_STATE["is_demo_mode"] else "LIVE HARDWARE"
    logger.info(f"System mode switched to: {mode_str}")
    return {
        "success": True, 
        "is_demo_mode": SYSTEM_STATE["is_demo_mode"], 
        "mode_label": mode_str
    }

@app.post("/api/simulator/object")
def api_set_simulator_object(payload: dict):
    obj = payload.get("object_type", "handgun")
    demo_simulator.set_object_type(obj)
    return {"success": True, "simulated_object": demo_simulator.simulated_object_mode}

@app.post("/api/magnetometer/calibrate")
def api_calibrate_mag():
    if SYSTEM_STATE["is_demo_mode"]:
        demo_simulator.base_bx = 22.4
        demo_simulator.base_by = 14.8
        demo_simulator.base_bz = 41.2
        return {"success": True, "message": "Demo magnetometer zeroed to baseline."}
    else:
        live_hardware_manager.calibrate_magnetometer(num_samples=50)
        return {"success": True, "message": "Live magnetometer baseline calibration started (50 samples)."}

@app.post("/api/telemetry/ingest")
def api_ingest_telemetry(packet: dict):
    """HTTP fallback for hardware nodes unable to use UDP."""
    packet["_source_ip"] = "http_ingest"
    live_hardware_manager.handle_packet(packet)
    return {"success": True}

# ── Session Management Endpoints ───────────────────────────────────────────

@app.get("/api/session/status")
def api_session_status():
    duration = 0.0
    if telemetry_buffer.is_recording and telemetry_buffer.recording_started_at:
        duration = round(time.time() - telemetry_buffer.recording_started_at, 2)
    return {
        "recording": telemetry_buffer.is_recording,
        "sample_count": len(telemetry_buffer.recorded_sessions),
        "duration_sec": duration,
        "buffer_size": len(telemetry_buffer.history)
    }

@app.post("/api/session/start")
def api_session_start():
    res = telemetry_buffer.start_recording()
    return res

@app.post("/api/session/stop")
def api_session_stop():
    res = telemetry_buffer.stop_recording()
    return res

@app.post("/api/session/clear")
def api_session_clear():
    res = telemetry_buffer.clear_session()
    return res

@app.get("/api/session/export/json")
def api_session_export_json():
    data = telemetry_buffer.export_json()
    return JSONResponse(
        content=json.loads(data),
        headers={"Content-Disposition": "attachment; filename=newvision_session.json"}
    )

@app.get("/api/session/export/csv")
def api_session_export_csv():
    csv_text = telemetry_buffer.export_csv()
    return PlainTextResponse(
        csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=newvision_session.csv"}
    )

# ── WebSocket Stream ───────────────────────────────────────────────────────

@app.websocket("/ws/telemetry")
async def websocket_telemetry_endpoint(websocket: WebSocket):
    await websocket.accept()
    SYSTEM_STATE["active_websockets"].add(websocket)
    logger.info(f"WebSocket client connected. Total clients: {len(SYSTEM_STATE['active_websockets'])}")
    try:
        while True:
            # Handle client commands if sent
            data = await websocket.receive_text()
            try:
                cmd = json.loads(data)
                if cmd.get("action") == "toggle_mode":
                    SYSTEM_STATE["is_demo_mode"] = not SYSTEM_STATE["is_demo_mode"]
                elif cmd.get("action") == "calibrate_mag":
                    api_calibrate_mag()
            except Exception:
                pass
    except WebSocketDisconnect:
        pass
    finally:
        SYSTEM_STATE["active_websockets"].discard(websocket)
        logger.info(f"WebSocket client disconnected. Total clients: {len(SYSTEM_STATE['active_websockets'])}")

# ── Spatial Calibration Endpoints ──────────────────────────────────────────

from backend.services.calibration import calibration_service

@app.get("/api/calibration/spatial")
def api_get_spatial_calibration():
    state = live_hardware_manager.current_state if not SYSTEM_STATE["is_demo_mode"] else demo_simulator.generate_tick()
    anchors = calibration_service.get_anchors()
    return {
        "rx1_position": anchors.get("rx1", state.rx1_position),
        "rx2_position": anchors.get("rx2", state.rx2_position),
        "tx_position": anchors.get("tx", state.tx_position),
        "radar_position": anchors.get("radar", state.radar_position),
        "coordinate_frame": calibration_service.config.get("coordinate_frame")
    }

@app.post("/api/calibration/spatial")
def api_update_spatial_calibration(config: dict):
    updates = {}
    if "rx1_position" in config:
        live_hardware_manager.current_state.rx1_position = config["rx1_position"]
        updates["rx1"] = config["rx1_position"]
    if "rx2_position" in config:
        live_hardware_manager.current_state.rx2_position = config["rx2_position"]
        updates["rx2"] = config["rx2_position"]
    if "tx_position" in config:
        live_hardware_manager.current_state.tx_position = config["tx_position"]
        updates["tx"] = config["tx_position"]
    if "radar_position" in config:
        live_hardware_manager.current_state.radar_position = config["radar_position"]
        updates["radar"] = config["radar_position"]
        
    if updates:
        calibration_service.update_anchors(updates)
        
    return {"success": True, "message": "Spatial calibration updated and saved"}


# ── Dashboard UI Serving ───────────────────────────────────────────────────

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DASHBOARD_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "dashboard"))

if os.path.exists(DASHBOARD_DIR):
    app.mount("/static", StaticFiles(directory=DASHBOARD_DIR), name="static")

@app.get("/", response_class=HTMLResponse)
def get_dashboard():
    index_file = os.path.join(DASHBOARD_DIR, "index.html")
    if os.path.exists(index_file):
        with open(index_file, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>NewVision Dashboard Loading...</h1>"

@app.get("/newview", response_class=HTMLResponse)
def get_newview():
    newview_file = os.path.join(DASHBOARD_DIR, "newview.html")
    if os.path.exists(newview_file):
        with open(newview_file, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>NewView Spatial Workspace Loading...</h1>"

