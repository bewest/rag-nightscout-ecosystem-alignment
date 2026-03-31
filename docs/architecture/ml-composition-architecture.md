# ML Composition Architecture

## Purpose

This document defines the architecture for composing physics simulation with machine learning to enable anticipatory diabetes management. It focuses on **why** the system is structured in layers, **what** design decisions constrain the approach, and **how** the layers connect.

For technique details: `docs/60-research/ml-technique-catalog.md`
For gap tracking: `traceability/ml-gaps.md`
For implementation: `tools/cgmencode/README.md`
For open questions: `docs/OPEN-QUESTIONS.md` (OQ-032 through OQ-035)

---

## 1. The 4-Layer Architecture

### 1.1 Vision

Shift diabetes management from reactive, moment-to-moment intervention into **anticipatory, context-aware support** that works alongside existing controllers (Loop, oref0). The system should:

- **Detect** short-term events (meals, exercise) — minutes to hours
- **Recognize** medium-term patterns (daily routines) — hours to a day
- **Identify** long-term physiological drift (ISF/CR changes) — days to weeks
- **Recommend** overrides before the user has to think about them

### 1.2 Layer Stack

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 4: DECISION & POLICY                                  │
│  "When should we suggest an override? What type? How early?" │
├─────────────────────────────────────────────────────────────┤
│  Layer 3: LEARNED DYNAMICS (cgmencode)                       │
│  "What will glucose do if we take action A?"                 │
├─────────────────────────────────────────────────────────────┤
│  Layer 2: CALIBRATION & RESIDUAL                             │
│  "How far is physics from reality? What's missing?"          │
├─────────────────────────────────────────────────────────────┤
│  Layer 1: PHYSICS SIMULATION (aid-autoresearch)              │
│  "Given insulin + carbs + parameters, what BG trajectory?"   │
└─────────────────────────────────────────────────────────────┘
```

**Key principle**: Physics provides causal grounding that pure ML cannot. ML provides speed, personalization, and uncertainty that physics alone cannot. Calibration connects them. Decisions consume them all.

### 1.3 Current Status

| Layer | Status | Evidence |
|-------|--------|----------|
| **L1 Physics** | ✅ Working | UVA/Padova + cgmsim engines, sensor noise, 50-patient sweep |
| **L1→L3 Residual** | ✅ **Validated** | Physics→ML residual: 0.28 MAE (8.2× better than raw ML). EXP-005. |
| **L2 Calibration** | ❌ Not built | Fingerprinting designed, not coded. §2.1 residual approach bypasses it. |
| **L3 Dynamics** | ✅ Working | See `docs/60-research/ml-experiment-log.md` for benchmarks |
| **L4 Decision** | ❌ Not started | Needs override event labels (OQ-032) |

---

## 2. Design Decisions

### 2.1 Physics backbone, ML residual

The UVA/Padova model encodes 60+ years of metabolic research. A pure ML model would need millions of patient-hours to learn what the ODEs already know. The correct composition:

```
BG_predicted = UVA_Padova(insulin, carbs, θ_patient) + ML_residual(context, history)
               └── Causal, interpretable, zero-shot ──┘  └── Behavioral, personalized ──┘
```

**Implication**: cgmencode models should be trained to predict the *residual* (actual − physics), not raw glucose. This dramatically reduces what the neural network must learn.

**Current status**: ✅ **Validated in EXP-005.** Residual AE (0.28 MAE) is 8.2× better than raw AE (2.31 MAE) on identical architecture. Even a simple IOB/COB forward-integration physics model (no full ODE) captures enough dynamics to beat persistence by 27%. The ML residual correction captures sensor noise, exercise, and model mismatch. See `docs/60-research/ml-experiment-log.md` EXP-005 for full results. Implementation: `tools/cgmencode/physics_model.py`.

### 2.2 Sim-to-real transfer

Pre-train on unlimited UVA/Padova synthetic data → fine-tune on real patient data. Standard pattern from robotics. Physics provides the curriculum; real data provides calibration.

**Implication**: cgmencode training always starts with synthetic data. Real data is a fine-tuning step, not a prerequisite for development. This unblocks all Layer 3 work.

**Current status**: Step 1 (synthetic pre-training) validated. Step 2 (real data training from scratch) validated — AE achieves 6.11 MAE on 85-day Nightscout data. Step 3 (sim→real transfer learning comparison) not yet run.

### 2.3 Start with trees, not transformers (for decisions)

For Layer 4 event classification, gradient-boosted trees on tabular features will likely match or beat deep learning on small labeled datasets.

**Rationale**:
- Fast iteration (minutes, not hours)
- Interpretable feature importances
- Strong baseline that deep models must beat to justify complexity
- Works with hundreds of examples, not millions

### 2.4 Safety floor, not safety ceiling

The policy layer must guarantee **never worse than "do nothing"** but need not be optimal.

**Safety architecture**:
```
Candidate Override → Physics guard (UVA/Padova: will this cause hypo?)
                   → Uncertainty guard (P(hypo) < threshold?)
                   → Controller agreement (does Loop/oref0 concur?)
                   → Human approval (notify with confidence, await accept/reject)
```

### 2.5 Three time horizons require different techniques

| Horizon | Window | Examples | Primary Technique |
|---------|--------|----------|-------------------|
| Immediate | min → 2h | Meal detection, hypo prediction | Sequence classification |
| Daily | 2h → 24h | Sleep transition, routine prediction | Pattern matching + context |
| Longitudinal | days → weeks | ISF/CR drift, illness, hormones | State-space / Bayesian filtering |

**Implication**: No single model covers all three. The architecture must compose short-term sequence models with long-term state trackers.

---

## 3. Data Flow

```
Real Patient Data ─────────────────┐
(Nightscout, CGM, Pump)            │
                                   ▼
                          ┌─── Layer 2: Calibration ──────────┐
                          │  Fingerprint → distance metrics   │
                          │  → optimize UVA/Padova params     │
                          └───────────┬───────────────────────┘
                                      │ calibrated params
                                      ▼
                          ┌─── Layer 1: Physics Engine ───────┐
                          │  UVA/Padova + sensor noise        │
                          │  → SIM-*.json vectors             │
                          └───────────┬───────────────────────┘
                                      │ synthetic training data
                    ┌─────────────────┼──────────────────┐
                    ▼                 ▼                   ▼
            Algorithm          cgmencode             Decision Model
            Validation         Training              Training
            (oref0/Loop)       (AE, Conditioned)     (XGBoost, TCN)
                    └─────────────────┼──────────────────┘
                                      ▼
                          ┌─── Layers 3+4: Inference ─────────┐
                          │  Encode history → predict events  │
                          │  → evaluate overrides → recommend │
                          │  → physics safety guard           │
                          └───────────┬───────────────────────┘
                                      ▼
                               User-facing output
                          ("Meal likely in ~30min.
                           Suggest 'Eating Soon'?")
                                      │
                                      ▼ accept/reject feedback
                               Retrain all layers
```

---

## 4. Integration Points

| Bridge | From → To | Status |
|--------|-----------|--------|
| Physics → ML training | SIM-*.json → sim_adapter.py → cgmencode | ✅ Working |
| **Physics → ML residual** | **physics_model.py → residual windows → AE** | **✅ Validated (EXP-005)** |
| Calibrated params → physics | Fingerprinting → UVA/Padova θ | ❌ Not built |
| ML residual → physics improvement | cgmencode identifies blind spots | ❌ Research |
| Algorithm decisions → decision model labels | Cross-validated oref0/Loop output → training labels | ❌ Not wired |
| Override events → decision model | Nightscout treatments → labeled events | ❌ Needs OQ-032 |

---

## 5. What This Architecture Does NOT Cover

- **cgmencode implementation details** → `tools/cgmencode/README.md`, `SCHEMA.md`
- **Individual technique descriptions** → `docs/60-research/ml-technique-catalog.md`
- **Gap tracking and status** → `traceability/ml-gaps.md`
- **Physics engine internals** → `docs/architecture/simulation-validation-architecture.md`
- **Algorithm cross-validation** → `docs/architecture/cross-validation-harness.md`
- **Roadmap and backlog** → `LIVE-BACKLOG.md`
- **Open questions** → `docs/OPEN-QUESTIONS.md` (OQ-032–035)
