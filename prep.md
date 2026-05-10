# Phase 1 Viva & Presentation Prep Guide
**Project:** Multi Model Object Detection and Classification Using Magnetic and Radar Sensors
**Team:** Niranjith M, Kavya B B, Nikitha S, Prajwal M
**Guide:** Dr. Kusuma G S

---

## 1. What We Built For Phase 1 (The MTC-1 System)
For Phase 1, our primary objective was to master the **Magnetic Anomaly Detection** and **Machine Learning** portions of the project. We built the **Magnetic Threat Classifier (MTC-1)**, a complete software-to-machine-learning pipeline.

### What is the MTC-1 Dashboard?
It is a tactical, military-grade web dashboard built using HTML, CSS, JavaScript, and a Python (Flask) backend. It simulates a real-world operator's interface. 
*   **Sensor Input (Left):** Simulates raw $B_x$, $B_y$, and $B_z$ readings from an HMC-5883L magnetometer.
*   **Radar Sweep (Center):** A 2D visualization that maps the spatial location of the detected anomaly based on the magnetic vector and distance.
*   **Classification Output (Right):** Shows the exact probability for all 6 object classes (Handgun, Rifle, Knife, IED, Tool, Clear).
*   **Live ML Feedback:** Allows an operator to manually correct the model and append the new data directly to the training dataset, incrementing the sample count in real-time.

### The Machine Learning Model
We trained a **Random Forest Classifier** with 200 estimators.
*   **Dataset:** We mathematically simulated 4,800 sensor readings using the Magnetic Dipole Equation, adding real-world noise.
*   **Feature Engineering:** Instead of just feeding raw X/Y/Z data to the AI, we calculated the **Magnitude**, **Variance**, **Gradient**, and **Spatial Position**. This feature engineering is why our model achieves **96.56% Accuracy**.

---

## 2. PPT Slide Content (Presentation Outline)

**Slide 1: Title & Team**
*   **Title:** Multi Model Object Detection and Classification Using Magnetic and Radar Sensors
*   **Team:** Niranjith M, Kavya B B, Nikitha S, Prajwal M | **Guide:** Dr. Kusuma G S

**Slide 2: Problem Statement**
*   Police and rescue teams lack affordable, portable through-wall detection.
*   Current systems are expensive, bulky, and only detect *presence*, not the *threat level* (e.g., weapon vs. tool).

**Slide 3: Project Objectives & Phase 1 Scope**
*   **Overall Goal:** Fuse magnetic anomaly detection (for ferrous weapons) with radar sensing (for human presence).
*   **Phase 1 Goal:** Develop the Magnetic Machine Learning Classifier and the Operator Dashboard.

**Slide 4: Phase 1 Methodology (The ML Pipeline)**
*   **Data Generation:** Used magnetic dipole physics to simulate realistic HMC-5883L sensor data.
*   **Feature Engineering:** Calculated Magnitude, Variance, and Gradient.
*   **Model:** Random Forest Classifier (200 trees). Chosen for its high accuracy (96.5%) and ability to run on low-power edge devices (like ESP32/Raspberry Pi).

**Slide 5: Live Dashboard Overview**
*   *(Insert a screenshot of the dark UI dashboard here)*
*   Highlight the real-time radar sweep, the class probabilities, and the Live ML Feedback Loop.

**Slide 6: Project Roadmap (Phase 2)**
*   **Hardware:** Integrate physical HMC-5883L magnetometers and DWM3000 UWB radar.
*   **Sensor Fusion:** Implement Kalman filtering to merge radar motion tracking with our magnetic weapon classification.
*   **Deployment:** Port the Random Forest model to the microcontroller.

---

## 3. Q&A Cheat Sheet (Professor Questions & Answers)

**Q: Where is the Radar you mentioned in your title?**
**A:** "Our ultimate objective is a sensor fusion system. For Phase 1 (Proof of Concept), we focused entirely on perfecting the Magnetic Anomaly Detection and the ML classification pipeline. Radar hardware integration and Kalman filtering are explicitly scheduled for Phase 2."

**Q: Is this a real application or just a UI mockup?**
**A:** "This is a fully functioning full-stack application. The UI communicates via REST API to a Python backend. The backend loads a real serialized Machine Learning model (`.pkl` file) trained on 4,800 samples, processes the payload, and returns real inferences in milliseconds."

**Q: Why does the system detect 'Tools'?**
**A:** "A major problem with standard metal detectors is false positives—they beep for everything. Our system's goal is *classification*. We trained it on a 'Tool' class (like a wrench) so the AI learns to differentiate between harmless structural/work objects and actual threats like guns or knives."

**Q: How exactly does the Random Forest work?**
**A:** "We used 200 'Decision Trees'. One tree might look at the data and say, *'The Magnitude is very high, so it is a Handgun.'* Another tree might say, *'The Variance is low, so it is a Tool.'* The sensor data is passed through all 200 trees, and they all 'vote'. This is why our dashboard shows exact probability percentages (e.g., 75% sure it's an IED)."

**Q: Why are your left panel inputs only Bx, By, Bz? Where is Magnitude?**
**A:** "In the real world, a magnetometer sensor only measures the magnetic field in 3 physical directions (X, Y, Z). Magnitude is a *derived feature* calculated using the physics formula: `√(Bx² + By² + Bz²)`. We placed Magnitude in the 'Derived Features' list to show we understand the difference between raw hardware data and software-calculated features."

**Q: What is the 'ML Live Feedback' section on the dashboard?**
**A:** "Real-world deployment requires continuous learning. We built a Human-in-the-Loop system. If the model encounters a new type of weapon or makes an error, the operator can correct the classification live on the dashboard. The system instantly saves that sensor profile back into our dataset to be retrained on. You can watch the training sample count tick up live."

---

## 4. The Elevator Pitch
"Current through-wall detection systems cost thousands of dollars and only tell you if a person is in the room. They don't tell you if that person is holding a hammer or a handgun. We are building a low-cost, portable fusion of radar and magnetic sensing. For Phase 1, we have successfully built and trained the magnetic machine learning classifier—achieving 96.5% accuracy—and wrapped it in a deployment-ready, real-time tactical dashboard with live feedback learning."
