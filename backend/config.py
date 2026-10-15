"""
NewVision System Configuration
Local-first, cross-platform configuration for macOS and Linux.
Configurable via environment variables or .env file.
"""

import os
from pydantic import BaseModel

class Settings(BaseModel):
    # System Info
    PROJECT_NAME: str = "NewVision"
    VERSION: str = "1.0.0"
    API_PREFIX: str = "/api"
    
    # Network Ingestion
    HOST: str = os.getenv("NEWVISION_HOST", "0.0.0.0")
    HTTP_PORT: int = int(os.getenv("NEWVISION_HTTP_PORT", "8000"))
    UDP_PORT: int = int(os.getenv("NEWVISION_UDP_PORT", "5005"))
    
    # Buffer & Streaming
    MAX_BUFFER_SIZE: int = int(os.getenv("NEWVISION_BUFFER_SIZE", "1000"))
    WS_PUSH_RATE_HZ: float = float(os.getenv("NEWVISION_PUSH_HZ", "20.0"))
    STALE_THRESHOLD_SEC: float = float(os.getenv("NEWVISION_STALE_SEC", "3.0"))
    
    # Model Artifacts Path
    MODEL_DIR: str = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "model")
    )
    
    # Wi-Fi AP Defaults
    AP_SSID: str = "CSI_TEST"
    AP_CHANNEL: int = 6
    AP_GATEWAY_IP: str = "192.168.4.1"

settings = Settings()
