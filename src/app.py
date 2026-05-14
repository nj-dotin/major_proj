"""
DAY 3: Flask Web API — Magnetic Threat Classifier Backend
==========================================================
Serves the interactive web dashboard and provides:
  GET  /           → dashboard HTML
  GET  /api/stats  → model stats JSON
  POST /api/detect → run prediction on sensor values
  POST /api/random → generate a random scan (for demo mode)

Run with: python src/app.py
Visit    : http://localhost:5000
"""

import os, json, random, csv
import numpy as np
import joblib
from flask import Flask, render_template, request, jsonify
from motion_utils import calculate_motion

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE   = os.path.dirname(os.path.abspath(__file__))
ROOT   = os.path.normpath(os.path.join(BASE, ".."))
MODEL  = os.path.join(ROOT, "model")

app = Flask(
    __name__,
    template_folder=os.path.join(ROOT, "templates"),
    static_folder=  os.path.join(ROOT, "static"),
)

# ── Load model artifacts once at startup ──────────────────────────────────────
print("[BOOT] Loading model ...")
clf    = joblib.load(os.path.join(MODEL, "weapon_classifier.pkl"))
scaler = joblib.load(os.path.join(MODEL, "scaler.pkl"))
le     = joblib.load(os.path.join(MODEL, "label_encoder.pkl"))

with open(os.path.join(MODEL, "model_stats.json")) as f:
    MODEL_STATS = json.load(f)

FEATURES = MODEL_STATS["features"]
print(f"[BOOT] Model ready. Classes: {le.classes_}")

# Persistent simulation state
SIM_STATE = {
    "last_pos": None  # (dist, angle)
}

# ── Colour / alert config ──────────────────────────────────────────────────────
THREAT_CONFIG = {
    "CRITICAL": {"color": "#ff0000", "glow": "rgba(255,0,0,0.4)",   "icon": "☢️",  "badge": "bg-danger"},
    "HIGH":     {"color": "#ff4444", "glow": "rgba(255,68,68,0.35)", "icon": "🔫",  "badge": "bg-danger"},
    "LOW":      {"color": "#ffaa44", "glow": "rgba(255,170,68,0.3)", "icon": "🔧",  "badge": "bg-warning"},
    "NONE":     {"color": "#00ff88", "glow": "rgba(0,255,136,0.2)",  "icon": "✅",  "badge": "bg-success"},
}

# Realistic sensor value ranges for random scan generator
DEMO_PROFILES = {
    "handgun":  {"Bx": (0.04, 0.12),  "By": (0.03, 0.10), "Bz": (0.02, 0.06),  "dist": (0.5, 2.5)},
    "knife":    {"Bx": (0.02, 0.07),  "By": (0.04, 0.13), "Bz": (0.01, 0.04),  "dist": (0.5, 2.5)},
    "rifle":    {"Bx": (0.08, 0.20),  "By": (0.06, 0.16), "Bz": (0.03, 0.10),  "dist": (0.5, 3.0)},
    "ied_nail": {"Bx": (0.05, 0.18),  "By": (0.04, 0.14), "Bz": (0.02, 0.09),  "dist": (0.5, 2.0)},
    "tool":     {"Bx": (0.02, 0.09),  "By": (0.02, 0.08), "Bz": (0.01, 0.05),  "dist": (0.5, 3.0)},
    "clear":    {"Bx": (0.001, 0.01), "By": (0.001, 0.01),"Bz": (0.0005, 0.005),"dist": (1.0, 5.0)},
}


def compute_features(Bx, By, Bz, distance):
    """Derive all model features from raw sensor inputs."""
    magnitude    = np.sqrt(Bx**2 + By**2 + Bz**2)
    # Variance proxy: standard deviation of the 3 components
    variance     = float(np.std([Bx, By, Bz]) ** 2)
    # Gradient: dB/dr estimate using finite difference at +0.1 m
    moment_est   = magnitude * (distance ** 3)
    B_plus       = moment_est / ((distance + 0.1) ** 3)
    gradient     = abs(magnitude - B_plus)
    # Distance estimate from inverse dipole formula
    distance_est = (moment_est) ** (1/3) if moment_est > 0 else distance

    return [Bx, By, Bz, magnitude, variance, gradient, distance_est]


def predict(features_raw):
    """Run scaler + model and return full probability dict."""
    X       = np.array([features_raw])
    X_s     = scaler.transform(X)
    y_pred  = clf.predict(X_s)[0]
    probs   = clf.predict_proba(X_s)[0]

    label       = le.inverse_transform([y_pred])[0]
    confidence  = float(np.max(probs)) * 100
    all_probs   = {
        le.inverse_transform([i])[0]: round(float(p) * 100, 1)
        for i, p in enumerate(probs)
    }
    threat      = MODEL_STATS["threat_map"].get(label, "NONE")
    tc          = THREAT_CONFIG[threat]

    return {
        "label":       label,
        "confidence":  round(confidence, 1),
        "threat":      threat,
        "color":       tc["color"],
        "glow":        tc["glow"],
        "icon":        tc["icon"],
        "all_probs":   all_probs,
        "features":    dict(zip(FEATURES, [round(v, 6) for v in features_raw])),
        "is_dynamic":  False # Default, will be updated in routes
    }


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html", stats=MODEL_STATS)


@app.route("/api/stats")
def api_stats():
    return jsonify(MODEL_STATS)


@app.route("/api/detect", methods=["POST"])
def api_detect():
    data = request.json
    try:
        Bx       = float(data["Bx"])
        By       = float(data["By"])
        Bz       = float(data["Bz"])
        distance = float(data["distance"])
    except (KeyError, ValueError) as e:
        return jsonify({"error": f"Invalid input: {e}"}), 400

    features = compute_features(Bx, By, Bz, distance)
    result   = predict(features)
    
    # Motion Logic (Assume angle 0 if not provided)
    angle = float(data.get("angle", 0))
    curr_pos = (distance * np.cos(np.radians(angle)), distance * np.sin(np.radians(angle)))
    
    if SIM_STATE["last_pos"]:
        result["is_dynamic"] = calculate_motion(SIM_STATE["last_pos"], curr_pos)
    
    SIM_STATE["last_pos"] = curr_pos
    return jsonify(result)


@app.route("/api/random", methods=["POST"])
def api_random():
    """Pick a real random sample from the dataset for a perfect demo."""
    csv_path = os.path.join(ROOT, "data", "weapon_magnetic.csv")
    
    # Read the dataset and pick a random row
    # The dataset columns generated in generate_data.py are:
    # Bx, By, Bz, magnitude, variance, gradient, distance_est, distance_true, mass, label, threat
    # Wait, the structure is: Bx,By,Bz,magnitude,variance,gradient,dist_est,dist_true,mass,label,threat
    import pandas as pd
    df = pd.read_csv(csv_path, header=None, skiprows=1)
    
    # To ensure all classes show up, we pick a random class, then a random row of that class
    classes = ["handgun", "knife", "rifle", "ied_nail", "tool", "clear"]
    target_class = random.choice(classes)
    
    # Filter by class (label is column 9)
    # The columns from generate_data.py line 85 were:
    # Bx, By, Bz, magnitude, variance, gradient, distance_est, distance_true, mass, label, threat
    # So label is index 9.
    subset = df[df[9] == target_class]
    if subset.empty:
        subset = df # fallback
        
    random_row = subset.sample(n=1).iloc[0]
    
    Bx = float(random_row[0])
    By = float(random_row[1])
    Bz = float(random_row[2])
    distance = float(random_row[7]) # distance_true

    features = compute_features(Bx, By, Bz, distance)
    result   = predict(features)
    
    # Generate random angle for radar
    angle = random.uniform(0, 360)
    curr_pos = (distance * np.cos(np.radians(angle)), distance * np.sin(np.radians(angle)))
    
    if SIM_STATE["last_pos"]:
        # Higher threshold for random demo scans to avoid jitter being called motion
        result["is_dynamic"] = calculate_motion(SIM_STATE["last_pos"], curr_pos, threshold=0.5)
    
    SIM_STATE["last_pos"] = curr_pos
    
    # Attach raw sensor values for display
    result["raw"] = {"Bx": Bx, "By": By, "Bz": Bz, "distance": distance, "angle": angle}
    return jsonify(result)


@app.route("/api/train", methods=["POST"])
def api_train():
    """Simulate online training by saving a sample and updating the count."""
    data = request.json
    try:
        Bx       = float(data["Bx"])
        By       = float(data["By"])
        Bz       = float(data["Bz"])
        distance = float(data["distance"])
        label    = data["label"]
    except (KeyError, ValueError) as e:
        return jsonify({"error": f"Invalid input: {e}"}), 400

    # Append to dataset
    csv_path = os.path.join(ROOT, "data", "weapon_magnetic.csv")
    if os.path.exists(csv_path):
        features = compute_features(Bx, By, Bz, distance)
        threat = MODEL_STATS["threat_map"].get(label, "NONE")
        
        # Schema: Bx, By, Bz, magnitude, variance, gradient, distance_est, true_distance, angle_deg, label, threat_level
        row = [
            round(Bx, 6),
            round(By, 6),
            round(Bz, 6),
            round(features[3], 6),
            round(features[4], 8),
            round(features[5], 8),
            round(features[6], 4),
            round(distance, 3),
            0.0,  # angle_deg (dummy value since we don't have it live)
            label,
            threat
        ]
        
        with open(csv_path, "a", newline='') as f:
            writer = csv.writer(f)
            writer.writerow(row)

    # Increment stats
    MODEL_STATS["training_samples"] += 1
    with open(os.path.join(MODEL, "model_stats.json"), "w") as f:
        json.dump(MODEL_STATS, f, indent=2)

    return jsonify({"success": True, "new_count": MODEL_STATS["training_samples"]})


if __name__ == "__main__":
    print("\n" + "=" * 55)
    print("  MAGNETIC THREAT CLASSIFIER — WEB DASHBOARD")
    print("  Open browser: http://localhost:5000")
    print("=" * 55 + "\n")
    app.run(debug=True, host="0.0.0.0", port=5000)
