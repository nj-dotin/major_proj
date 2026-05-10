"""
DAY 1: Synthetic Magnetic Anomaly Dataset Generator
====================================================
Generates realistic magnetic field signatures for 6 object classes
based on the magnetic dipole model: B ∝ m / r³

Classes:
  - handgun  : compact ferrous mass, medium moment
  - knife    : elongated thin ferrous, asymmetric signature
  - rifle    : large ferrous mass, high moment
  - ied_nail : irregular nail clusters, high variance
  - tool     : hammer/wrench, moderate symmetric dipole
  - clear    : no weapon (background/structural steel noise)

Output: data/weapon_magnetic.csv  (4800 samples, 800 per class)
"""

import numpy as np
import pandas as pd
import os

# ── Reproducibility ────────────────────────────────────────────────────────────
np.random.seed(42)

# ── Physical parameters per class ─────────────────────────────────────────────
# magnetic_moment (Am²) — controls field strength
# moment_spread   (%)   — manufacturing variation
# shape_anisotropy       — how asymmetric the object is (1=sphere, >1=elongated)
# noise_level            — environmental + sensor noise multiplier

OBJECT_PROFILES = {
    "handgun": {
        "magnetic_moment": 0.52,
        "moment_spread":   0.10,
        "shape_anisotropy": 1.2,
        "noise_level":      0.04,
        "threat_level":     "HIGH",
    },
    "knife": {
        "magnetic_moment": 0.28,
        "moment_spread":   0.08,
        "shape_anisotropy": 2.5,   # very elongated
        "noise_level":      0.05,
        "threat_level":     "HIGH",
    },
    "rifle": {
        "magnetic_moment": 0.85,
        "moment_spread":   0.12,
        "shape_anisotropy": 1.8,
        "noise_level":      0.03,
        "threat_level":     "HIGH",
    },
    "ied_nail": {
        "magnetic_moment": 0.61,
        "moment_spread":   0.25,   # high variance — nail clusters are irregular
        "shape_anisotropy": 1.1,
        "noise_level":      0.09,
        "threat_level":     "CRITICAL",
    },
    "tool": {
        "magnetic_moment": 0.38,
        "moment_spread":   0.11,
        "shape_anisotropy": 1.4,
        "noise_level":      0.04,
        "threat_level":     "LOW",
    },
    "clear": {
        "magnetic_moment": 0.04,   # just background / structural steel
        "moment_spread":   0.50,
        "shape_anisotropy": 1.0,
        "noise_level":      0.06,
        "threat_level":     "NONE",
    },
}

SAMPLES_PER_CLASS = 800
DISTANCE_RANGE    = (0.3, 5.0)   # meters — sensor to object
ANGLE_RANGE       = (0, 360)     # degrees — object orientation


def generate_sample(profile: dict, distance: float, angle_deg: float) -> dict:
    """
    Generate one magnetic measurement from a single object.

    Uses simplified magnetic dipole model:
        B_total ≈ (µ₀ / 4π) * (2m / r³)  [along dipole axis]

    We compute Bx, By, Bz components + derived features.
    """
    m     = profile["magnetic_moment"]
    spread = profile["moment_spread"]
    aniso  = profile["shape_anisotropy"]
    noise  = profile["noise_level"]

    # Actual moment with manufacturing variation
    actual_moment = m * np.random.normal(1.0, spread)
    actual_moment = max(actual_moment, 1e-4)

    # Dipole field magnitude: B ∝ m / r³
    B_base = actual_moment / (distance ** 3)

    # Project onto axes using angle (simulates sensor orientation)
    angle_rad = np.radians(angle_deg)
    Bx = B_base * np.cos(angle_rad) * aniso
    By = B_base * np.sin(angle_rad)
    Bz = B_base * 0.5 / aniso   # depth component inversely affected by anisotropy

    # Add sensor + environmental noise
    sigma = noise * B_base
    Bx += np.random.normal(0, sigma)
    By += np.random.normal(0, sigma)
    Bz += np.random.normal(0, sigma * 0.7)

    # Derived features (what real processing would compute)
    magnitude   = np.sqrt(Bx**2 + By**2 + Bz**2)
    variance    = (sigma ** 2) * profile["moment_spread"]   # proxy for signal instability
    gradient    = abs(B_base - (actual_moment / ((distance + 0.1) ** 3)))  # dB/dr
    distance_est = (actual_moment / max(magnitude, 1e-6)) ** (1/3)         # inverse dipole estimate

    return {
        "Bx":           round(Bx, 6),
        "By":           round(By, 6),
        "Bz":           round(Bz, 6),
        "magnitude":    round(magnitude, 6),
        "variance":     round(variance, 8),
        "gradient":     round(gradient, 8),
        "distance_est": round(distance_est, 4),
        "true_distance": round(distance, 3),
        "angle_deg":    round(angle_deg, 1),
    }


def generate_dataset() -> pd.DataFrame:
    records = []
    for label, profile in OBJECT_PROFILES.items():
        print(f"  Generating {SAMPLES_PER_CLASS} samples for: {label} ...")
        for _ in range(SAMPLES_PER_CLASS):
            distance  = np.random.uniform(*DISTANCE_RANGE)
            angle_deg = np.random.uniform(*ANGLE_RANGE)
            sample    = generate_sample(profile, distance, angle_deg)
            sample["label"]        = label
            sample["threat_level"] = profile["threat_level"]
            records.append(sample)

    df = pd.DataFrame(records)
    # Shuffle
    df = df.sample(frac=1, random_state=42).reset_index(drop=True)
    return df


if __name__ == "__main__":
    print("=" * 60)
    print("  MAGNETIC ANOMALY DATASET GENERATOR")
    print("  Magnetic Dipole Model  |  6 Classes  |  4800 samples")
    print("=" * 60)

    df = generate_dataset()

    out_path = os.path.join(os.path.dirname(__file__), "..", "data", "weapon_magnetic.csv")
    out_path = os.path.normpath(out_path)
    df.to_csv(out_path, index=False)

    print(f"\n[OK] Dataset saved -> {out_path}")
    print(f"   Shape     : {df.shape}")
    print(f"   Columns   : {list(df.columns)}")
    print(f"\n   Class distribution:")
    print(df["label"].value_counts().to_string())
    print(f"\n   Feature statistics:")
    print(df[["Bx","By","Bz","magnitude","variance","gradient"]].describe().round(4))
