"""
Spatial and Network Calibration Management Service.
Handles loading and saving of anchor coordinates, coordinate frames, and offset calibration.
"""

import json
import os
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("newvision.calibration")

CONFIG_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "config"))
CALIBRATION_FILE = os.path.join(CONFIG_DIR, "spatial_calibration.json")

class CalibrationService:
    def __init__(self, filepath: str = CALIBRATION_FILE):
        self.filepath = filepath
        self.config = self.load_calibration()

    def load_calibration(self) -> Dict[str, Any]:
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    logger.info(f"Loaded spatial calibration from {self.filepath}")
                    return data
            except Exception as e:
                logger.error(f"Error reading spatial calibration: {e}")
        
        # Default fallback
        return {
            "coordinate_frame": {
                "type": "Cartesian Right-Handed Metric",
                "origin": "LD2450 Radar Phase Center (0,0)",
                "units": "meters"
            },
            "anchors": {
                "radar": {"x": 0.0, "y": 0.0, "z": 0.0, "label": "LD2450 Radar", "type": "RADAR"},
                "tx": {"x": 0.0, "y": 4.0, "z": 0.8, "label": "NodeMCU AP Tx", "type": "TX"},
                "rx1": {"x": -1.5, "y": 2.5, "z": 0.8, "label": "Rx1 (ESP32 #1)", "type": "RX1"},
                "rx2": {"x": 1.5, "y": 2.5, "z": 0.8, "label": "Rx2 (ESP32 #2)", "type": "RX2"}
            }
        }

    def save_calibration(self, new_data: Dict[str, Any]) -> bool:
        try:
            self.config.update(new_data)
            os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2)
            logger.info(f"Saved updated spatial calibration to {self.filepath}")
            return True
        except Exception as e:
            logger.error(f"Failed to save spatial calibration: {e}")
            return False

    def get_anchors(self) -> Dict[str, Any]:
        return self.config.get("anchors", {})

    def update_anchors(self, anchor_updates: Dict[str, Any]) -> bool:
        if "anchors" not in self.config:
            self.config["anchors"] = {}
        for key, val in anchor_updates.items():
            if key in self.config["anchors"]:
                self.config["anchors"][key].update(val)
            else:
                self.config["anchors"][key] = val
        return self.save_calibration(self.config)

calibration_service = CalibrationService()
