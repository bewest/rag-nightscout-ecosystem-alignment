# 📋 CGMENCODE: Engineering & Research Roadmap

This document outlines the roadmap for moving from a prototype toolbox to a production-grade physiological modeling system.

**Last Updated**: 2026-04 (after physics→ML bridge, sweep training, and UVA/Padova validation)

---

## Phase 1: Data Acquisition (Scaling the Dataset) — ✅ DONE

*Goal: Move from ~1,000 vectors to 10,000+ vectors.*

- [x] **SIM-* → cgmencode bridge** (`sim_adapter.py`): Converts physics simulation output to 8-feature training vectors. Handles both SIM-* and TV-* conformance formats.
- [x] **Latin Hypercube parameter sweep** (`generate_training_data.py`): Generates diverse patient profiles (ISF 15–80, CR 5–20, basal 0.3–3.0, weight 45–110, DIA 4–8) via LHS sampling.
- [x] **Patient parameter CLI** (`in-silico-bridge.js`): Added `--isf`, `--cr`, `--basal-rate`, `--weight`, `--dia`, `--patient`, `--id-prefix`, `--output-dir` flags.
- [x] **Multi-engine support**: Both cgmsim and UVA/Padova engines produce training data via `--engine` flag.
- [x] **Scaled to 50 patients**: 3,500 cgmsim vectors + 2,400 UVA/Padova vectors generated.
- [ ] **Real patient data**: `real_data_adapter.py` built and tested with synthetic trace. **Blocked on OhioT1DM dataset download from PhysioNet** (credentialed access required).
- [ ] ~~Automate Nightscout History Ingestion~~: Deferred — physics sweep provides sufficient volume for current R&D.

---

## Phase 2: Systematic Model Evaluation — ✅ DONE

*Goal: Benchmark the performance of each architecture.*

- [x] **Unified training CLI** (`train.py`): Supports all 4 architectures with `--model {ae,vae,conditioned,diffusion}`.
- [x] **Evaluation metrics** (`evaluate.py`): MAE/RMSE in mg/dL (denormalized), persistence baseline comparison.
- [x] **KL annealing for VAE**: Ramps β from 0→0.01 over 30% warmup. Prevents collapse but doesn't fix architectural mismatch.
- [x] **Cross-engine comparison**: Trained on both cgmsim (simplified) and UVA/Padova (realistic) — results show models learn genuine physiology.
- [ ] **CRPS**: Not yet implemented for Diffusion model (diffusion itself is a toy — CRPS would be meaningless on current implementation).
- [ ] **K-fold cross-validation**: Not yet implemented. Current evaluation uses 80/20 train/val split.

---

## Phase 3: Conditioned Transformer & Dosing — 🔜 NEXT

*Goal: Prove the "digital twin" can learn physics, then beat it.*

- [x] **Basic Conditioned Transformer training**: Works, achieves 3.47 MAE on UVA/Padova.
- [ ] **Dose comparison visualization**: Compare predicted trajectories for 2U vs 5U bolus on same history.
- [ ] **Hyperparameter tuning**: Val loss oscillates — needs learning rate schedule or gradient clipping.
- [ ] **Scale to 200+ patients**: Current 50-patient sweep may under-represent action space diversity.
- [ ] **Residual training (§8.2)**: Train on `actual − UVA_predicted` instead of raw glucose. Requires real data.

---

## Phase 4: Safety & Integration — 🔮 FUTURE

- [ ] **Safety scorecard**: Flag proposals if >5% of probability cloud enters hypo range (<70 mg/dL).
- [ ] **Conditional VAE redesign**: Current VAE's 32D bottleneck is fundamentally mismatched for trajectory forecasting. Needs per-timestep conditioning or hierarchical latent structure.
- [ ] **Fix Diffusion model**: Current forward process is `x + noise`, not proper DDPM β-schedule. Uncertainty estimates are meaningless.
- [ ] **Swift/CoreML integration**: Export trained models for mobile inference.

---

## Known Issues

| Issue | Status | Notes |
|-------|--------|-------|
| VAE 42.78 MAE (worse than persistence) | Known | 32D latent bottleneck too narrow. Needs architectural redesign. |
| Diffusion is toy implementation | Known | Forward process not proper DDPM. Uncertainty meaningless. |
| cgmsim sweep hangs on extreme params | Workaround | Some ISF/CR combos cause edge cases. Use UVA/Padova for production training. |
| `encoder.py` fixture paths hardcoded | Known | Legacy paths (`fixtures/algorithm-replays`). Use `sim_adapter.py` or `generate_training_data.py` instead. |
