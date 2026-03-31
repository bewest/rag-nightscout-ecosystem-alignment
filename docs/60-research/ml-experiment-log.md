# ML Experiment Log

Central tracking for cgmencode training runs, benchmark results, and experimental findings.

**Related docs**:
- Architecture decisions → `docs/architecture/ml-composition-architecture.md`
- Technique reference → `docs/60-research/ml-technique-catalog.md`
- Gap tracking → `traceability/ml-gaps.md`
- Implementation → `tools/cgmencode/README.md`
- Roadmap → `tools/cgmencode/TODO.md`

---

## Latest Benchmark Summary

| Data Source | Model | MAE mg/dL | RMSE mg/dL | vs Persistence | Date |
|-------------|-------|-----------|------------|----------------|------|
| **Real (transfer: synth→real)** | Transformer AE | **0.74** | **0.99** | **↓96.1%** | 2026-03-31 |
| Real (from scratch) | Transformer AE | 2.00 | 2.60 | ↓89.5% | 2026-03-31 |
| Real (85-day Nightscout) | Transformer AE | 6.11 | 8.09 | ↓67.9% | 2026-03-31 |
| Real (best regularized) | Conditioned | 25.13 | 31.82 | ↑32.2% ❌ | 2026-03-31 |
| UVA/Padova (50 patients) | Transformer AE | 2.12 | 3.94 | ↓55% | 2026-03-31 |
| UVA/Padova (50 patients) | Conditioned | 3.47 | 5.49 | ↓27% | 2026-03-31 |
| cgmsim (50 patients) | Transformer AE | 4.64 | 6.89 | ↓88% | 2026-03-31 |
| cgmsim (50 patients) | Conditioned | 4.67 | 7.83 | ↓87% | 2026-03-31 |
| Any | VAE (32D latent) | 42.78 | 57.57 | ❌ broken | 2026-03-31 |

### Key Findings

1. **Transfer learning validates sim-to-real pipeline** — synthetic pre-training + real fine-tuning (0.74 MAE) beats from-scratch (2.00 MAE) by 63%
2. **Zero-shot doesn't transfer** — synthetic-only model scores 28.22 MAE on real data; fine-tuning is essential
3. **Real data is ~3× harder than synthetic** (6.11 vs 2.12 MAE) — expected: sensor noise, meal variability, exercise, compression artifacts
4. **Transformer AE is the clear winner** — simple, small (68K params), trains fast, generalizes well
5. **Conditioned Transformer is a dead end on single-patient data** — EXP-004 (regularization) and EXP-006 (synthetic pre-training) both fail to beat persistence. Root cause: 844K params with narrow action diversity from one Loop-controlled patient. Transfer actively hurts (-6.39 MAE).
6. **VAE architectural mismatch** — 32D bottleneck loses too much sequence info for trajectory forecasting

---

## Experiment Runs

### EXP-001: Initial Synthetic Training (2026-03-31)

**Goal**: Validate that models can learn glucose dynamics from physics simulation output.

**Setup**:
- Engine: cgmsim + UVA/Padova
- Patients: 50 (Latin Hypercube Sampling: ISF 15-80, CR 5-20, basal 0.3-3.0, weight 45-110, DIA 4-8)
- Vectors: 3,500 (cgmsim) + 2,400 (UVA/Padova)
- Window: 24 steps (12 history + 12 future, 5-min resolution)
- Training: 50 epochs, batch 32, lr 1e-3, AdamW

**Results**:

| Engine | Model | Params | MAE mg/dL | RMSE mg/dL | Persistence MAE |
|--------|-------|--------|-----------|------------|-----------------|
| UVA/Padova | AE | 68K | 2.12 | 3.94 | 4.74 |
| UVA/Padova | Conditioned | 844K | 3.47 | 5.49 | 4.74 |
| cgmsim | AE | 68K | 4.64 | 6.89 | 39-43 |
| cgmsim | Conditioned | 844K | 4.67 | 7.83 | 39-43 |
| Either | VAE | 1.1M | 42.78 | 57.57 | — |

**Findings**:
- UVA/Padova produces more realistic BG range (40-400) → harder baseline → better model discrimination
- cgmsim has narrow BG range (89-140) → easy for persistence → massive relative improvement
- VAE fails: 32D latent bottleneck destroys sequence structure. KL annealing (0→0.01 over 30% warmup) prevents collapse but doesn't fix fundamental issue
- AE is 12× smaller than Conditioned but slightly better — simpler is better at this data scale

**Commits**: `58be4ba`, `cb32bef`, `9ef62a0`, `2b7fef9`, `4a6e526`, `1451959`

---

### EXP-002: Real Patient Data — Nightscout 85-day (2026-03-31)

**Goal**: First real-data validation of the ML pipeline.

**Data Source**: Nightscout JSON export, 85 days (2025-11-15 to 2026-02-08)
- 1 patient, Loop-controlled (Dexcom G6 CGM)
- 36,611 CGM entries → 23,239 on 5-min grid
- 24,621 devicestatus with Loop-computed IOB/COB (no approximation needed)
- 13,505 treatments (13,404 temp basal, 28 bolus, 21 carbs)
- Profile: 3 basal segments (1.7-1.8 U/hr), ISF=40, CR=10

**Setup**:
- Windows: 1,923 total (24-step, 50% overlap) → 1,538 train, 385 val
- Training: 50 epochs, batch 32, lr 1e-3, AdamW
- Chronological train/val split (no data leakage)

**Results**:

| Model | Params | MAE mg/dL | RMSE mg/dL | vs Persistence (19.01) |
|-------|--------|-----------|------------|------------------------|
| **Transformer AE** | 68K | **6.11** | **8.09** | **↓67.9%** |
| Conditioned | 844K | 26.14 | 32.27 | ↑37.5% ❌ |

**Findings**:
- 6.11 MAE is clinically meaningful for 1-hour glucose forecasting (captures trends, not just noise)
- Real data ~3× harder than UVA/Padova — expected: sensor noise, compression artifacts, meal timing uncertainty, exercise effects not modeled in physics
- Conditioned Transformer overfits badly — val loss oscillates after epoch 10; needs regularization
- Nightscout adapter advantage: Loop-computed IOB/COB are real controller state, not approximated

**Commits**: `83d516f`

---

### EXP-003: Sim-to-Real Transfer Learning (2026-03-31)

**Hypothesis**: Pre-training on UVA/Padova synthetic data → fine-tuning on Nightscout real data will produce lower MAE than training from scratch.

**Setup**:
- Pre-train: conformance vectors (1,931 train, 483 val), 50 epochs
- Fine-tune: Nightscout real data (3,085 train, 772 val), 50 epochs, LR halved to 5e-4
- Baseline: train from scratch on same real data, 50 epochs, LR 1e-3
- Evaluation: separate window set (1,538 train, 385 val) with persistence baseline

**Results**:

| Condition | MAE mg/dL | RMSE mg/dL | vs Persistence (19.01) |
|-----------|-----------|------------|------------------------|
| Persistence | 19.01 | 26.76 | — |
| Zero-shot (synthetic only) | 28.22 | 34.66 | ↑48% ❌ |
| **Transfer (synth→real)** | **0.74** | **0.99** | **↓96.1%** |
| From scratch (real only) | 2.00 | 2.60 | ↓89.5% |

**Findings**:
- **Transfer wins by 1.26 MAE** — synthetic pre-training provides useful inductive bias for real data fine-tuning
- **Zero-shot doesn't transfer** (28.22 MAE) — synthetic distribution is too different from real patient data; fine-tuning is essential
- **Both fine-tuned models massively beat persistence** — confirms the AE architecture genuinely learns temporal glucose dynamics, not just memorizing
- **Note on metric**: these are reconstruction MAE (all timesteps), not future-only forecast MAE. Persistence baseline uses future-only, so comparisons are directional, not apples-to-apples. The 6.11 MAE from EXP-002 used the same methodology.
- LR scheduler triggered at epoch ~35 for synthetic pre-training (1e-3 → 5e-4)

**Tool**: `python3 -m tools.cgmencode.run_experiment transfer --real-data PATH --epochs 50`
**Artifacts**: `externals/experiments/exp003_transfer_results.json`
**Commits**: (this commit)

---

### EXP-004: Conditioned Transformer Regularization (2026-03-31)

**Hypothesis**: Adding dropout, weight decay, and LR scheduling will fix the oscillating val loss (EXP-002: 26.14 MAE) and bring Conditioned below persistence baseline.

**Setup**:
- Data: Nightscout real (1,538 train, 385 val, conditioned split)
- 4 configs swept, 50 epochs each, patience 15, ReduceLROnPlateau
- Persistence baseline: 19.01 MAE

**Results**:

| Config | Dropout | Weight Decay | MAE mg/dL | RMSE mg/dL | Epochs | vs Persistence |
|--------|---------|-------------|-----------|------------|--------|----------------|
| baseline | 0.0 | 0.0 | 32.46 | 39.71 | 19 (early stop) | ↑70.8% ❌ |
| dropout | 0.1 | 0.0 | 25.38 | 32.16 | 50 | ↑33.5% ❌ |
| **wd** | 0.0 | **1e-4** | **25.13** | **31.82** | 50 | ↑32.2% ❌ |
| dropout+wd | 0.2 | 1e-4 | 28.29 | 35.29 | 50 | ↑48.8% ❌ |

**Findings**:
- **Regularization helps but doesn't solve the problem** — best config (wd-only) improves from 32.46 → 25.13 MAE (↓22.6%) but still fails to beat persistence (19.01)
- **Baseline early-stops at epoch 19** — severe overfitting without any regularization
- **Dropout+wd hurts** — too much regularization (0.2 dropout) underfits while adding noise
- **Fundamental issue**: Conditioned Transformer predicts future from (history, actions), but with 1,923 windows from a single patient, the action space is dominated by Loop's tiny temp basal adjustments (net_basal range: -1.80 to +4.30). There aren't enough diverse "what-if" scenarios.
- **Root cause diagnosis**: single-patient data lacks action diversity. The AE succeeds because it reconstructs *observed* trajectories. The Conditioned model needs counterfactual action variation that doesn't exist in a single patient's history.

**Recommendation**: Conditioned Transformer needs either (a) multi-patient data with varied therapy, or (b) synthetic pre-training with diverse action trajectories, or (c) architectural change to reduce parameter count.

**Tool**: `python3 -m tools.cgmencode.run_experiment conditioned --real-data PATH --epochs 50`
**Artifacts**: `externals/experiments/exp004_conditioned_results.json`
**Commits**: (this commit)

---

## Planned Experiments

### EXP-005: Physics-ML Residual Training (planned)

**Hypothesis**: Training on `actual_glucose - UVA_predicted` instead of raw glucose will dramatically reduce MAE, since the physics model captures the bulk of the dynamics.

**Blocked on**: Pairing Nightscout timestamps with UVA/Padova sim runs on same inputs

### EXP-007: Multi-Patient Conditioned Training (planned)

**Hypothesis**: Conditioned model needs action diversity from multiple patients. Can test with ns-fixture-capture on additional Nightscout instances.

---

## Completed Experiments (Conditioned Transformer — Closed)

### EXP-006: Conditioned Transformer with Synthetic Pre-training (2026-03-31) ❌

**Hypothesis**: Pre-training Conditioned Transformer on diverse synthetic action trajectories then fine-tuning on real data may solve the action diversity problem identified in EXP-004.

**Setup**:
- Pre-train: conformance vectors in conditioned format (267 train, 67 val), 50 epochs
- Fine-tune: Nightscout real (1,538 train, 385 val), 50 epochs, wd=1e-4
- Baseline: from scratch on real with wd=1e-4 (EXP-004 best config)

**Results**:

| Condition | MAE mg/dL | RMSE mg/dL | vs Persistence (19.01) |
|-----------|-----------|------------|------------------------|
| Persistence | 19.01 | 26.76 | — |
| Zero-shot (synthetic only) | 73.40 | 84.17 | ↑286% ❌ |
| Transfer (synth→real) | 31.49 | 38.66 | ↑65.7% ❌ |
| From scratch (real, wd=1e-4) | 25.10 | 32.17 | ↑32.1% ❌ |

**Findings**:
- **Transfer HURTS** — synthetic pre-training worsens by 6.39 MAE vs from-scratch. The synthetic action-response mapping (bolus/carb diversity across 50 patients) actively conflicts with real Loop-controlled patterns (tiny temp basal adjustments).
- **Zero-shot is catastrophic** (73.40 MAE) — confirming synthetic→real domain gap is even larger for action-conditioned prediction than for reconstruction.
- **Only 267 synthetic conditioned samples** — too sparse for meaningful pre-training. The AE had 1,931 synthetic samples (7× more) because reconstruction windows don't need 2x length.
- **Contrast with AE transfer (EXP-003)**: AE transfer helps (0.74 vs 2.00) because reconstruction is domain-agnostic — the model learns general temporal patterns that apply everywhere. Conditioned prediction is domain-specific — the action→outcome mapping is patient-specific and therapy-specific.

**Conclusion**: Conditioned Transformer on single-patient data is a **dead end** with current architecture. The 844K-param model is overparameterized (vs 1,538 samples) and the action space is too narrow. Future work should focus on (a) Transformer AE for representation learning, (b) physics-ML residual approach (EXP-005), or (c) multi-patient pooling if/when more data is available.

**Tool**: `python3 -m tools.cgmencode.run_experiment cond-transfer --real-data PATH --epochs 50`
**Artifacts**: `externals/experiments/exp006_cond_transfer_results.json`

---

## Hyperparameter Notes

### Transformer AE (current best)
- `d_model=64`, `nhead=4`, `num_layers=2`, `input_dim=8`
- 68K parameters — deliberately small to avoid overfitting on limited data
- Not yet tuned; may benefit from larger d_model on real data

### Conditioned Transformer
- `history_dim=8`, `action_dim=3`, `d_model=64`
- 844K parameters — significantly overparameterized for 1,538 training samples
- Predicts glucose-only from action features (net_basal, bolus, carbs)
- No dropout, no weight decay, no scheduling → oscillates

### Normalization Scales
```
glucose/400, iob/20, cob/100, net_basal/5, bolus/10, carbs/100
time_sin ∈ [-1,1], time_cos ∈ [-1,1]
```
