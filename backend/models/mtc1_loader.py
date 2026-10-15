"""
MTC-1 (Magnetic Threat Classifier) Model Service.
Safely wraps the pre-trained Random Forest model and scaler.
Enforces honest evaluation: Requires calibrated baseline and target range,
and clearly indicates that this is a synthetic proof-of-concept model.
"""

import os
import json
import logging
from typing import Optional, Dict, Any
import numpy as np
import joblib
from backend.config import settings
from backend.schemas import MTCInference

logger = logging.getLogger("newvision.mtc1")

class MTC1ClassifierService:
    def __init__(self, model_dir: Optional[str] = None):
        self.model_dir = model_dir or settings.MODEL_DIR
        self.is_loaded = False
        self.clf = None
        self.scaler = None
        self.le = None
        self.model_stats = {}
        self.load_error: Optional[str] = None
        
        self.load_artifacts()

    def load_artifacts(self):
        try:
            clf_path = os.path.join(self.model_dir, "weapon_classifier.pkl")
            scaler_path = os.path.join(self.model_dir, "scaler.pkl")
            le_path = os.path.join(self.model_dir, "label_encoder.pkl")
            stats_path = os.path.join(self.model_dir, "model_stats.json")

            if not all(os.path.exists(p) for p in [clf_path, scaler_path, le_path, stats_path]):
                self.load_error = "One or more model artifact files missing."
                logger.warning(self.load_error)
                return

            self.clf = joblib.load(clf_path)
            self.scaler = joblib.load(scaler_path)
            self.le = joblib.load(le_path)
            
            with open(stats_path, "r") as f:
                self.model_stats = json.load(f)

            self.is_loaded = True
            logger.info("MTC-1 model artifacts loaded successfully.")
        except Exception as e:
            self.load_error = f"Failed to load model: {str(e)}"
            logger.error(self.load_error)
            self.is_loaded = False

    def compute_dipole_features(self, bx: float, by: float, bz: float, distance: float) -> list:
        """
        Original MTC-1 dipole feature engineering:
        [Bx, By, Bz, magnitude, variance, gradient, distance_est]
        """
        magnitude = np.sqrt(bx**2 + by**2 + bz**2)
        variance = float(np.std([bx, by, bz]) ** 2)
        
        # Dipole moment estimate m ≈ B * r^3
        moment_est = magnitude * (distance ** 3)
        # Gradient dB/dr evaluated with step 0.1m
        b_plus = moment_est / ((distance + 0.1) ** 3) if distance > 0 else 0
        gradient = abs(magnitude - b_plus)
        distance_est = (moment_est) ** (1/3) if moment_est > 0 else distance
        
        return [bx, by, bz, magnitude, variance, gradient, distance_est]

    def predict(self, 
                bx: float, 
                by: float, 
                bz: float, 
                distance: Optional[float] = None, 
                is_calibrated: bool = False,
                sensor_supported: bool = True) -> MTCInference:
        """
        Executes prediction with strict guardrails against false confidence.
        """
        if not sensor_supported:
            return MTCInference(
                status="SENSOR_INCOMPATIBLE",
                threat_level="NONE",
                threat_color="#888888",
                explanation="Sensor hardware lacks a magnetometer (e.g. MPU-6050)."
            )

        if not self.is_loaded:
            return MTCInference(
                status="UNAVAILABLE",
                threat_level="NONE",
                threat_color="#888888",
                explanation=self.load_error or "Model artifacts could not be loaded."
            )

        if not is_calibrated:
            return MTCInference(
                status="UNCALIBRATED",
                threat_level="NONE",
                threat_color="#ffaa44",
                explanation="Magnetometer requires baseline calibration before threat classification."
            )

        if distance is None or distance <= 0:
            return MTCInference(
                status="AWAITING_RANGE",
                threat_level="NONE",
                threat_color="#00e5ff",
                explanation="Dipole gradient calculation requires target range (from Radar or calibrated standoff distance)."
            )

        # Scale down uT (Earth is ~50 uT) to the ~0.01 - 0.2 units expected by MTC-1 training data
        # In generate_data.py, dipole field values were generated around 0.001 - 0.2
        # Let's normalize appropriately if inputs are raw microTesla
        scale_factor = 0.005 if max(abs(bx), abs(by), abs(bz)) > 1.0 else 1.0
        norm_bx = bx * scale_factor
        norm_by = by * scale_factor
        norm_bz = bz * scale_factor

        features = self.compute_dipole_features(norm_bx, norm_by, norm_bz, distance)
        
        try:
            x_arr = np.array([features])
            x_scaled = self.scaler.transform(x_arr)
            y_pred = self.clf.predict(x_scaled)[0]
            probs = self.clf.predict_proba(x_scaled)[0]

            label = self.le.inverse_transform([y_pred])[0]
            confidence = float(np.max(probs)) * 100.0
            
            all_probs = {
                self.le.inverse_transform([i])[0]: round(float(p) * 100.0, 1)
                for i, p in enumerate(probs)
            }
            
            threat_map = self.model_stats.get("threat_map", {})
            threat = threat_map.get(label, "NONE")
            
            color_map = {
                "CRITICAL": "#ff0000",
                "HIGH": "#ff4444",
                "LOW": "#ffaa44",
                "NONE": "#00ff88"
            }
            
            feature_names = self.model_stats.get("features", [
                "Bx", "By", "Bz", "magnitude", "variance", "gradient", "distance_est"
            ])
            derived_dict = {k: round(v, 6) for k, v in zip(feature_names, features)}

            return MTCInference(
                status="READY",
                is_validated_hardware_model=False, # Honestly labeled
                predicted_class=label,
                confidence_percent=round(confidence, 1),
                threat_level=threat,
                threat_color=color_map.get(threat, "#00ff88"),
                all_probabilities=all_probs,
                derived_features=derived_dict,
                distance_source=f"Target range: {round(distance, 2)}m",
                explanation=f"Classified as {label} ({round(confidence, 1)}% confidence, experimental model)."
            )
        except Exception as e:
            return MTCInference(
                status="INFERENCE_ERROR",
                threat_level="NONE",
                threat_color="#ff4444",
                explanation=f"Error during feature scaling or model prediction: {str(e)}"
            )

mtc1_service = MTC1ClassifierService()
