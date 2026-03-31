# 📋 CGMENCODE: Engineering & Research Roadmap

This document outlines the next steps for moving from a "Toolbox" to a production-grade physiological modeling system.

---

## Phase 1: Data Acquisition (Scaling the Dataset)
*Goal: Move from ~1,000 vectors to 100,000+ vectors.*

- [ ] **Automate Nightscout History Ingestion**: Use `scripts/capture-ns-history.sh` to pull multi-year datasets from consented research accounts.
- [ ] **Clean Window Extraction**: Refine `tools/iob-clean-windows/extract_fixtures.py` to identify "high-quality" segments where data is continuous and site changes are documented.
- [ ] **Data Augmentation**: Implement "physiological jitter" (randomly shifting carb absorption times or insulin onset in the simulator) to help the model generalize beyond the limited fixture set.
- [ ] **Metadata Labeling**: Add labels for "Exercise," "Stress," or "Illness" if available in the NS `treatments` notes to allow for conditioned phenotyping in the VAE.

---

## Phase 2: Systematic Model Evaluation
*Goal: Benchmark the performance of each architecture in the Toolbox.*

- [ ] **Metric Standardization**:
    - **MAE/MSE**: For the Pattern Recognizer and Digital Twin.
    - **KL Divergence**: For the VAE latent space distribution.
    - **CRPS (Continuous Ranked Probability Score)**: Specifically for the **Diffusion** model to evaluate the quality of its "probability clouds."
- [ ] **Cross-Validation**: Implement K-fold validation across different "Patient IDs" to ensure the model isn't just learning one person's physiology.
- [ ] **Baseline Comparison**: Compare model accuracy against the canonical **Loop Algorithm** (Oref0/Oref1) predictions found in the `loopPredicted` fields of our fixtures.

---

## Phase 3: Actionable Dosing & Integration
*Goal: Use the models to evaluate or suggest real-world insulin doses.*

- [ ] **The "Counselor" Loop**:
    1. Receive a proposed dose from an external algorithm (e.g., T1PalAID or Loop).
    2. Feed the current history + the proposed dose into the **Action-Conditioned Predictor**.
    3. Run the **Diffusion** model 50 times to generate a "Cloud of Futures."
- [ ] **Safety Scorecard**:
    - Develop a "Safety Evaluator" that flags a proposal if >5% of the Diffusion cloud enters the hypoglycemic range (<70 mg/dL).
- [ ] **Proposal Optimization**:
    - Use the **Digital Twin** to "sweep" a range of doses (e.g., 0.0U to 5.0U) and identify the dose that maximizes time-in-range (TIR) according to the model.
- [ ] **Swift Integration**: Explore using `CoreML` or a Python microservice to allow the T1Pal Mobile app to query the "Digital Twin" for real-time safety checks.

---

## Phase 4: Human-in-the-Loop
- [ ] **Visual Debugger**: Build a small dashboard (using Matplotlib or Streamlit) that shows the Nightscout maintainers the "Cloud of Possibilities" the AI sees for a given fixture.
- [ ] **Failure Analysis**: Specifically evaluate where the models fail (e.g., during unannounced meals) and use those failures to drive "Hard Case" data collection.
