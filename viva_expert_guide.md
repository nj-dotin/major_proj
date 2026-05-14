# MTC-S1: The Definitive Project Guide (Minute to Big)
**Project Title:** Multi-Modal Through-Wall Detection Simulation (MTC-1)
**Scope:** Phase 1 (Magnetic & Kinetic AI Classification)

---

## 1. Project Timeline & Key Milestones (The "Big Picture")

| Stage | Focus | Key Achievement |
| :--- | :--- | :--- |
| **Stage 1: Tactical Core** | Data & ML Pipeline | Built the Magnetic Dipole Simulator and trained the Random Forest. |
| **Stage 2: Interface Evolution** | UX/UI Refinement | Developed the tactical dashboard and pivoted to a high-contrast academic style. |
| **Stage 3: Behavioral Intelligence**| Motion Analysis | Implemented TDD-based kinetic detection to separate static noise from mobile threats. |

---

## 2. From "Minute" Code to "Big" Architecture

### 🔬 The Minute Details (Inside the Code)
1.  **Normalization (`scaler.pkl`):** The raw magnetic flux can range from $0.001$ to $0.2$. The ML model doesn't like large number ranges, so we used a **StandardScaler** to normalize all inputs to a mean of $0$ and unit variance. This ensures that a "small knife" and a "large rifle" are compared on a mathematically fair ground.
2.  **The Ensemble Jigsaw:** We used **200 Decision Trees**. Each tree looks at a "minute" split, such as: `IF magnitude > 0.05 AND gradient < 0.01 THEN object = tool`. By combining 200 of these tiny rules, we get a "Big" accurate prediction.
3.  **The Canvas Buffer:** The Radar isn't just a video. It's a **Dynamic 2D Canvas**. Every frame (16.7ms), the code clears the screen and redraws the "Minute" sweep lines and anomaly halos to create a smooth 60fps simulation.
4.  **CSV Row Integrity:** Every time you click "Train", the system appends a row with precisely **11 columns**. Even one missing comma would break the training pipeline.

### 🏢 The Big Architecture (System Level)
1.  **The Nervous System (Flask):** The `src/app.py` acts as the router. It listens for "Minute" HTTP requests from the browser, runs them through the "Big" ML model, and sends back a JSON payload containing the threat level.
2.  **Multi-Modal Vision:** While Phase 1 is Magnetic, the "Big" vision is sensor fusion. We have built the infrastructure so that when the **UWB Radar** hardware is added in Phase 2, it can simply "Inject" its data into the same dashboard.
3.  **Edge Intelligence:** This isn't just a website. It is designed to be **Cloud-Independent**. The `.pkl` files can be loaded onto an NVIDIA Jetson or a high-end Raspberry Pi, making it a portable "Big" security tool.

---

## 3. Technical Architecture (The Math)

### A. The Data Generation Engine (`src/generate_data.py`)
We don't use arbitrary random numbers. We use a **Physical Proxy Model**:
*   **Dipole Equations:** We calculate the field $B$ using the **Biot-Savart** derivative for dipoles: $\vec{B}(\mathbf{r}) = \frac{\mu_0}{4\pi} \left[ \frac{3\mathbf{\hat{r}}(\mathbf{m}\cdot\mathbf{\hat{r}}) - \mathbf{m}}{r^3} \right]$.
*   **Mass & Moment Scaling:** Each object class (Handgun vs. IED) has a specific magnetic moment $m$ based on typical ferrous content (e.g., steel alloy vs. iron nails).

### B. Feature Engineering (Derived Invariants)
The model calculates "Derived Invariants" that are distance-independent:
1.  **Magnitude ($\sqrt{\sum B_i^2}$):** The total magnetic pressure.
2.  **Variance:** Detects the "signature complexity" (IEDs with mixed scrap metal have erratic variance).
3.  **Gradient ($\Delta B/\Delta r$):** Helps determine if the anomaly is a point source (weapon) or a large field (structural beam).

---

## 4. The Kinetic Intelligence Upgrade (Motion Detection)

We implemented a **Temporal Tracking Layer** using Test-Driven Development (TDD).
*   **Static Anomaly:** A constant magnetic reading in one spot (e.g., rebar in the wall).
*   **Dynamic Threat:** A reading that moves spatially between scans (e.g., a person walking with a weapon).
*   **The Logic:** $dist = \sqrt{(x_2-x_1)^2 + (y_2-y_1)^2}$. If $dist > 0.5m$, the system flags **DYNAMIC**.

---

## 5. Comprehensive Viva Q&A

**Q: How do you handle "Magnetic Drift"?**
*A: We implemented a **Reset/Clear** function that recalibrates the baseline. In Phase 2, we will use a hardware-based 'Zeroing' algorithm to subtract the Earth's ambient magnetic field automatically.*

**Q: Why choose Random Forest over Deep Learning?**
*A: For Phase 1, we prioritized **interpretability and edge-device compatibility**. A Random Forest allows us to see exactly which features (like Magnitude or Distance Est) were dominant. It also requires 100x less power than a Neural Network.*

**Q: What is the 'Clear' class?**
*A: It represents the **Benign Structural Environment**. It simulates low-level magnetic distortions from rebar or electrical pipes. By training the AI on what is 'Safe', we reduce false alarms.*

**Q: How does the .pkl file work?**
*A: It is a **Serialized Python Object**. Instead of recalculating the 200 trees every time, we save the "state" of the trained brain. This allows for instantaneous "Stochastic Inference" in the dashboard.*

---

## 6. Summary of Built Files

*   `src/app.py`: The **Nervous System** (Flask Backend).
*   `src/generate_data.py`: The **Physical World** (Simulator).
*   `src/train_model.py`: The **Education** (Model Training).
*   `src/motion_utils.py`: The **Kinetic Eye** (Velocity Tracking).
*   `templates/index.html`: The **Operator Interface** (Dashboard).
*   `data/weapon_magnetic.csv`: The **Memory** (Dataset).
*   `model/*.pkl`: The **Intelligence** (Serialized Model).

---
**Status:** Phase 1 Feature Complete. Ready for Review.
