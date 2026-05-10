# MTC-1 | Magnetic Threat Classifier

Phase 1 Proof of Concept for a Multi-Modal Through-Wall Detection System.
This project uses magnetic anomaly detection and machine learning to classify hidden threats behind walls.

## Project Architecture

1. **Synthetic Data Generation**: Uses the physical Magnetic Dipole Model to generate realistic sensor readings for different objects based on mass and distance.
2. **Machine Learning Classifier**: A Random Forest model trained on 4,800 synthetic samples to classify objects into 6 categories (handgun, knife, rifle, ied_nail, tool, clear) with ~96.5% accuracy.
3. **Web Dashboard**: A Flask-based API running a tactical, industrial-dark themed web interface that visualizes incoming sensor data, model confidence, and a 2D simulated magnetic field heatmap.

## Setup & Running

1. **Install Dependencies**:
   ```bash
   pip install flask pandas scikit-learn matplotlib
   ```

2. **Generate Data & Train Model** (Optional, already done):
   ```bash
   python src/generate_data.py
   python src/train_model.py
   ```
   *Training output and graphs are saved in the `report/` folder.*

3. **Run the Dashboard**:
   ```bash
   python src/app.py
   ```

4. **View**: Open `http://localhost:5000` in your browser. Click "Random Scan" to simulate real-time sensor data detection.

## Engineering Standards

This project adheres to **Test-Driven Development (TDD)** principles at the API level (simulating endpoint behavior before finalizing the ML logic) and **Frontend Design** best practices. 

**UI Aesthetic**: "Industrial Utilitarian + Tactical Dark". 
* Avoids generic components.
* Uses raw data readouts, monospaced fonts (`JetBrains Mono`), and a CRT-inspired scanline effect.
* Functional emphasis: A live radar sweep visualization maps the magnetic field in 2D space.
