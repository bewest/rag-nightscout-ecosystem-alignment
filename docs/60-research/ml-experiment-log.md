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
| **Real (85-day Nightscout)** | Transformer AE | **6.11** | **8.09** | **↓67.9%** | 2026-03-31 |
| Real (85-day Nightscout) | Conditioned | 26.14 | 32.27 | ↑37.5% ❌ | 2026-03-31 |
| UVA/Padova (50 patients) | Transformer AE | 2.12 | 3.94 | ↓55% | 2026-03-31 |
| UVA/Padova (50 patients) | Conditioned | 3.47 | 5.49 | ↓27% | 2026-03-31 |
| cgmsim (50 patients) | Transformer AE | 4.64 | 6.89 | ↓88% | 2026-03-31 |
| cgmsim (50 patients) | Conditioned | 4.67 | 7.83 | ↓87% | 2026-03-31 |
| Any | VAE (32D latent) | 42.78 | 57.57 | ❌ broken | 2026-03-31 |

### Key Findings

1. **Real data is ~3× harder than synthetic** (6.11 vs 2.12 MAE) — expected: sensor noise, meal variability, exercise, compression artifacts
2. **Transformer AE is the clear winner** — simple, small (68K params), trains fast, generalizes well
3. **Conditioned Transformer overfits on real data** — val loss oscillates; needs dropout, weight decay, LR scheduling
4. **VAE architectural mismatch** — 32D bottleneck loses too much sequence info for trajectory forecasting
5. **Diffusion model is a toy** — forward process is `x + noise`, not proper DDPM β-schedule

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

## Planned Experiments

### EXP-003: Sim-to-Real Transfer Learning (pending)

**Hypothesis**: Pre-training on UVA/Padova synthetic data → fine-tuning on Nightscout real data will produce lower MAE than training from scratch (6.11 baseline).

**Blocked on**: `--pretrained` flag in train.py

### EXP-004: Conditioned Transformer Regularization (pending)

**Hypothesis**: Adding dropout (0.1-0.3), weight decay (1e-4), and ReduceLROnPlateau will fix the oscillating val loss and bring Conditioned below persistence baseline.

**Blocked on**: LR scheduling + early stopping in train.py

### EXP-005: Physics-ML Residual Training (pending)

**Hypothesis**: Training on `actual_glucose - UVA_predicted` instead of raw glucose will dramatically reduce MAE, since the physics model captures the bulk of the dynamics.

**Blocked on**: Pairing Nightscout timestamps with UVA/Padova sim runs on same inputs

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
