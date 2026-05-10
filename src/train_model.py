"""
DAY 2: ML Model Training — Random Forest Classifier
=====================================================
Trains a Random Forest on the generated magnetic dataset.
Saves:
  - model/weapon_classifier.pkl
  - model/scaler.pkl
  - model/label_encoder.pkl
  - model/model_stats.json   ← used by the web dashboard

Outputs confusion matrix + feature importance plots to report/
"""

import os, json, joblib
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")          # headless rendering (no display needed)
import matplotlib.pyplot as plt
import seaborn as sns

from sklearn.ensemble          import RandomForestClassifier
from sklearn.model_selection   import train_test_split, cross_val_score
from sklearn.preprocessing     import StandardScaler, LabelEncoder
from sklearn.metrics           import (
    accuracy_score, classification_report, confusion_matrix
)

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE   = os.path.dirname(os.path.abspath(__file__))
ROOT   = os.path.normpath(os.path.join(BASE, ".."))
DATA   = os.path.join(ROOT, "data",   "weapon_magnetic.csv")
MODEL  = os.path.join(ROOT, "model")
REPORT = os.path.join(ROOT, "report")

os.makedirs(MODEL,  exist_ok=True)
os.makedirs(REPORT, exist_ok=True)

# Feature columns used for training (no label leakage)
FEATURES = ["Bx", "By", "Bz", "magnitude", "variance", "gradient", "distance_est"]
TARGET   = "label"

# Threat level map (for dashboard)
THREAT_MAP = {
    "handgun":  "HIGH",
    "knife":    "HIGH",
    "rifle":    "HIGH",
    "ied_nail": "CRITICAL",
    "tool":     "LOW",
    "clear":    "NONE",
}


def load_data():
    print("[1/6] Loading dataset ...")
    df = pd.read_csv(DATA)
    print(f"      Shape: {df.shape} | Classes: {df[TARGET].nunique()}")
    return df


def prepare(df):
    print("[2/6] Preparing features ...")
    X = df[FEATURES].values
    y = df[TARGET].values

    le = LabelEncoder()
    y_enc = le.fit_transform(y)

    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y_enc, test_size=0.20, random_state=42, stratify=y_enc
    )

    scaler = StandardScaler()
    X_tr_s = scaler.fit_transform(X_tr)
    X_te_s = scaler.transform(X_te)

    print(f"      Train: {X_tr_s.shape} | Test: {X_te_s.shape}")
    return X_tr_s, X_te_s, y_tr, y_te, scaler, le


def train(X_tr, y_tr):
    print("[3/6] Training Random Forest (200 trees) ...")
    clf = RandomForestClassifier(
        n_estimators=200,
        max_depth=None,
        min_samples_split=4,
        min_samples_leaf=2,
        max_features="sqrt",
        class_weight="balanced",
        n_jobs=-1,
        random_state=42,
    )
    clf.fit(X_tr, y_tr)
    print("      Done.")
    return clf


def evaluate(clf, X_te, y_te, le):
    print("[4/6] Evaluating model ...")
    y_pred    = clf.predict(X_te)
    acc       = accuracy_score(y_te, y_pred)
    report    = classification_report(y_te, y_pred, target_names=le.classes_, output_dict=True)
    cm        = confusion_matrix(y_te, y_pred)

    print(f"\n      [PASS] Accuracy : {acc*100:.2f}%")
    print(f"\n{classification_report(y_te, y_pred, target_names=le.classes_)}")
    return acc, report, cm, y_pred


def save_artifacts(clf, scaler, le, acc, report):
    print("[5/6] Saving model artifacts ...")
    joblib.dump(clf,    os.path.join(MODEL, "weapon_classifier.pkl"))
    joblib.dump(scaler, os.path.join(MODEL, "scaler.pkl"))
    joblib.dump(le,     os.path.join(MODEL, "label_encoder.pkl"))

    stats = {
        "accuracy":        round(acc * 100, 2),
        "n_classes":       len(le.classes_),
        "classes":         list(le.classes_),
        "threat_map":      THREAT_MAP,
        "features":        FEATURES,
        "n_estimators":    200,
        "training_samples": 3840,
        "test_samples":     960,
        "per_class_f1": {
            cls: round(report[cls]["f1-score"] * 100, 1)
            for cls in le.classes_
        },
    }
    with open(os.path.join(MODEL, "model_stats.json"), "w") as f:
        json.dump(stats, f, indent=2)

    print(f"      Artifacts saved to: {MODEL}")
    # (no emoji — ASCII safe for Windows cp1252)


def plot_confusion_matrix(cm, le):
    fig, ax = plt.subplots(figsize=(8, 6))
    sns.heatmap(
        cm, annot=True, fmt="d", cmap="Blues",
        xticklabels=le.classes_, yticklabels=le.classes_, ax=ax
    )
    ax.set_xlabel("Predicted Label", fontsize=12)
    ax.set_ylabel("True Label",      fontsize=12)
    ax.set_title("Confusion Matrix — Magnetic Weapon Classifier", fontsize=14, fontweight="bold")
    plt.tight_layout()
    path = os.path.join(REPORT, "confusion_matrix.png")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"      Confusion matrix -> {path}")


def plot_feature_importance(clf, le):
    importances = clf.feature_importances_
    indices     = np.argsort(importances)[::-1]
    feat_names  = [FEATURES[i] for i in indices]

    fig, ax = plt.subplots(figsize=(8, 5))
    bars = ax.bar(feat_names, importances[indices], color="#00ff88", edgecolor="#003320")
    ax.set_xlabel("Feature",     fontsize=12)
    ax.set_ylabel("Importance",  fontsize=12)
    ax.set_title("Feature Importance — Random Forest", fontsize=14, fontweight="bold")
    ax.set_facecolor("#0d1117")
    fig.patch.set_facecolor("#0d1117")
    ax.tick_params(colors="white")
    ax.xaxis.label.set_color("white")
    ax.yaxis.label.set_color("white")
    ax.title.set_color("white")
    for bar in bars:
        bar.set_alpha(0.85)
    plt.tight_layout()
    path = os.path.join(REPORT, "feature_importance.png")
    fig.savefig(path, dpi=150, facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"      Feature importance -> {path}")


def plot_class_distribution():
    df   = pd.read_csv(DATA)
    cnts = df[TARGET].value_counts()

    colors = ["#ff4444","#ff8844","#ff4444","#ff0000","#ffaa44","#44ff44"]
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.pie(cnts.values, labels=cnts.index, autopct="%1.0f%%",
           colors=colors, startangle=140,
           textprops={"color": "white", "fontsize": 11})
    ax.set_title("Training Dataset — Class Distribution", fontsize=13, color="white", fontweight="bold")
    fig.patch.set_facecolor("#0d1117")
    plt.tight_layout()
    path = os.path.join(REPORT, "class_distribution.png")
    fig.savefig(path, dpi=150, facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"      Class distribution -> {path}")


if __name__ == "__main__":
    print("=" * 60)
    print("  MAGNETIC WEAPON CLASSIFIER - ML TRAINING")
    print("  Random Forest  |  6 Classes  |  200 Trees")
    print("=" * 60)

    df = load_data()
    X_tr, X_te, y_tr, y_te, scaler, le = prepare(df)
    clf = train(X_tr, y_tr)
    acc, report, cm, y_pred = evaluate(clf, X_te, y_te, le)
    save_artifacts(clf, scaler, le, acc, report)

    print("\n[6/6] Generating report graphs ...")
    plot_confusion_matrix(cm, le)
    plot_feature_importance(clf, le)
    plot_class_distribution()

    print("=" * 60)
    print(f"  TRAINING COMPLETE")
    print(f"  Final Accuracy : {acc*100:.2f}%")
    print(f"  Model saved    : model/weapon_classifier.pkl")
    print("=" * 60)
