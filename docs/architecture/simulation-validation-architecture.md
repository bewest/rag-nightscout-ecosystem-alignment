# Simulation Validation Architecture

> How to ensure simulated CGM and treatment data reflects actual human experience,
> and how to use validated simulations for autonomous dosing algorithm improvement.

**Trace**: REQ-060, ALG-VERIFY-007, ALG-VERIFY-008, ALG-SCORE-001

---

## 1. Problem Statement

Simulated glucose and treatment data is essential for:

1. **Exhaustive algorithm testing** — real datasets are small and sparse
2. **Edge-case coverage** — rare but dangerous scenarios (DKA, site failures, compression lows)
3. **Autonomous algorithm improvement** — the autoresearch loop (`program.md`) needs
   unlimited scenario generation to explore the parameter space

But simulation is only useful if it's **calibrated against reality**. We've already observed
the core failure mode: **algorithm rankings reverse on synthetic vs real data**. Persistence
wins on cgmsim-lib's simplified engine (narrow 89–140 mg/dL range, MAE 2.3) while oref0
wins on real TV-* vectors (real variability, MAE 14.6). Any autonomous loop that optimizes
against uncalibrated simulation will converge on algorithms that are good at predicting
*simulations*, not *humans*.

---

## 2. Current Simulation Infrastructure

### 2.1 Engines

| Engine | Location | Model Type | Fidelity | Speed |
|--------|----------|------------|----------|-------|
| **cgmsim-lib CGMSIM** | `externals/cgmsim-lib/src/CGMSIMsimulator.ts` | Pharmacokinetic (ISF-based exponential decay) | Medium | Fast |
| **cgmsim-lib UVA/Padova** | `externals/cgmsim-lib/src/UVAsimulator.ts` | ODE physiological (8-equation T1DMS) | High | Moderate |
| **cgmsim-lib sensor models** | `externals/cgmsim-lib/src/lt1/core/sensors/` | CGM noise (Breton2008, Facchinetti2014, Vettoretti2018) | Configurable | — |
| **GluPredKit UVA/Padova** | `externals/GluPredKit/glupredkit/models/uva_padova.py` | ReplayBG identification + ODE replay | High | Slow |
| **GluPredKit Loop** | `externals/GluPredKit/glupredkit/models/loop.py` | PyLoopKit prediction engine | Algorithm-level | Moderate |

### 2.2 Integration Tools

| Tool | Location | Purpose |
|------|----------|---------|
| `in-silico-bridge.js` | `tools/aid-autoresearch/` | Generates SIM-* vectors via cgmsim-lib (7 scenarios × 3 patients) |
| `score-in-silico.js` | `tools/aid-autoresearch/` | Scores algorithms against SIM-* ground truth |
| `glupredkit_oref0_model.py` | `tools/aid-autoresearch/` | Wraps oref0 as GluPredKit BaseModel |
| `glupredkit_loop_model.py` | `tools/aid-autoresearch/` | Wraps Loop as GluPredKit BaseModel |
| `algorithm_score.py` | `tools/aid-autoresearch/` | Composite 6-metric scoring (in-silico = 10% weight) |

### 2.3 Generated Artifacts

- **35 SIM-* vectors** in `conformance/in-silico/vectors/`
- **~20 TV-*-synthetic vectors** in `conformance/t1pal/vectors/oref0-endtoend/`
- **GluPredKit example data**: `externals/GluPredKit/example_data/synthetic_data.csv` (6000 rows)

### 2.4 Known Limitation: Ranking Reversal

The simplified CGMSIM engine produces BG in 89–140 mg/dL — far narrower than real T1D
variability (SD 50–65 mg/dL, range frequently 40–350+). This causes:

- Persistence (just predict current BG) to score best on synthetic data
- Algorithms that handle variability well (oref0) to score best on real data
- Any composite score mixing uncalibrated synthetic + real data to produce misleading rankings

---

## 3. Validation Methodology

### 3.1 Three-Layer Validation

```
┌─────────────────────────────────────────────────────────────┐
│  LAYER 1: Statistical Distribution Matching                 │
│  "Does the simulator produce data that looks like real T1D?"│
│                                                             │
│  Compare population-level statistics:                       │
│  • BG mean, SD, CV, MAGE                                   │
│  • Time-in-range buckets (< 54, 54-70, 70-180, > 180, >250)│
│  • Meal response amplitude and shape                        │
│  • Overnight stability patterns                             │
│  • Insulin delivery patterns (TDI, basal:bolus ratio)       │
│                                                             │
│  Acceptance: KL divergence < threshold per metric           │
└────────────────────────────┬────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────┐
│  LAYER 2: Scenario Realism Calibration                      │
│  "Do individual scenarios match real-world patterns?"       │
│                                                             │
│  Compare specific dynamics:                                 │
│  • Post-meal peak timing (real: 45-90 min)                  │
│  • Post-meal peak amplitude (real: 40-120 mg/dL rise)       │
│  • Hypo nadir and recovery trajectory                       │
│  • Dawn phenomenon ramp rate                                │
│  • Exercise-induced BG changes                              │
│                                                             │
│  Acceptance: DTW distance < threshold per scenario type     │
└────────────────────────────┬────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────┐
│  LAYER 3: Edge Case / Adversarial Scenarios                 │
│  "Can we stress-test beyond normal human experience?"       │
│                                                             │
│  Not validated against real data — intentionally extreme:   │
│  • Stuck sensor, compression lows, sensor gaps              │
│  • Pump site failure (phantom IOB)                          │
│  • Extreme carb loads, double bolus                         │
│  • Rapid glucose crash (> 5 mg/dL/min)                      │
│  • Stale data (no readings for 30+ min)                     │
│                                                             │
│  Acceptance: Algorithm safety invariants hold               │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 Reference Datasets for Calibration

GluPredKit already has parsers for all of these:

| Dataset | Parser | Subjects | Duration | Strengths |
|---------|--------|----------|----------|-----------|
| **OhioT1DM** (2018/2020) | `parsers/ohio_t1dm.py` | 12 | 8 weeks each | CGM + insulin + meals + exercise + self-reported life events |
| **Tidepool-JDRF** | `parsers/tidepool_dataset.py` | Large | Months | Real pump data at scale |
| **Shanghai T1DM** | `parsers/shanghai_t1dm.py` | ~100 | Variable | Different demographic, MDI + pump mix |
| **BRIST1D** | `parsers/brist1d.py` | — | — | UK cohort |
| **T1DEXI** | `parsers/t1dexi.py` | — | — | Exercise-focused study |
| **Nightscout** | `parsers/nightscout.py` | 1+ | Unlimited | Your own data, Loop/AAPS/Trio device data |
| **Tidepool API** | `parsers/tidepool.py` | 1+ | Unlimited | Live data via Tidepool platform |
| **Apple Health** | `parsers/apple_health.py` | 1 | Unlimited | iPhone health export |

### 3.3 Statistical Fingerprint Targets

Based on published T1D population data (ADA Standards of Care, ATTD consensus):

| Metric | Well-Controlled T1D | Average T1D | Poorly Controlled |
|--------|---------------------|-------------|-------------------|
| Mean BG (mg/dL) | 130–145 | 154 (A1C ~7%) | 180–220 |
| BG SD (mg/dL) | 35–45 | 50–65 | 70–90 |
| CV (%) | 25–33 | 33–40 | 40–55 |
| TIR 70–180 | > 70% | 50–70% | < 50% |
| TBR < 70 | < 4% | 4–10% | variable |
| TBR < 54 | < 1% | 1–3% | variable |
| TAR > 180 | < 25% | 25–45% | > 50% |
| MAGE (mg/dL) | 60–80 | 80–120 | 120–160 |

The current cgmsim-lib CGMSIM engine produces data resembling the "well-controlled" column
at best — it lacks the variability to represent average or poorly-controlled T1D.

---

## 4. Gaps in Current Simulation

### 4.1 Physiological Noise Missing from CGMSIM Engine

| Factor | Real World | Current Simulation | Impact |
|--------|------------|--------------------|--------|
| CGM sensor noise | ±15–20% MARD | Clean signal (none) | Algorithms overtrained on perfect data |
| Carb estimation error | ±30–50% systematic bias | Exact carbs specified | Underestimates real meal response variance |
| Meal timing jitter | ±15–30 min from intended | Exact timestamp | Missing bolus-meal mismatch scenarios |
| Missed/late bolus | ~20% of meals in real data | All boluses given | Missing most common real-world failure |
| Compression lows | Common during sleep | Not modeled | False hypo signals not tested |
| Sensor dropout/warmup | Hours of missing data | Continuous signal | Missing data handling untested |
| Multi-day ISF drift | Illness, cycle, stress | Fixed ISF per run | Autosens/dynamic-ISF not exercised |
| Insulin absorption variability | ±20–30% per injection | Deterministic decay | IOB model precision overstated |

### 4.2 Available but Not Integrated

cgmsim-lib's `lt1/core/sensors/` directory contains CGM noise models
(Breton2008, Facchinetti2014, Vettoretti2018/2019) that are used by the UVA/Padova
simulator but **not by the CGMSIM engine** that `in-silico-bridge.js` uses. The
UVA/Padova engine with these sensor models would produce significantly more realistic
output, but integration requires:

1. State persistence between 5-minute ticks (UVA needs `lastState`)
2. ODE solver initialization with steady-state finder
3. Treatment format conversion to UVA's input schema

### 4.3 Scenario Coverage Gaps

Current 7 scenarios in `in-silico-bridge.js`:

```
✅ meal-rise          (adequate bolus)
✅ meal-underbolus    (50% bolus)
✅ fasting-flat       (stable basal)
✅ hypo-recovery      (BG 65 + carb correction)
✅ dawn-phenomenon    (cortisol rise)
✅ exercise           (post-meal exercise)
✅ multi-meal         (breakfast + lunch + snack)
```

Missing scenarios needed for realistic coverage:

```
❌ missed-bolus       (meal with no bolus — extremely common)
❌ double-bolus       (accidental re-dose)
❌ site-change        (insulin absorption disruption)
❌ sensor-warmup      (2-hour CGM gap after new sensor)
❌ compression-low    (false low during sleep)
❌ illness            (rising ISF, elevated BG for hours)
❌ alcohol-evening    (delayed hypo risk next morning)
❌ high-fat-meal      (extended carb absorption, 4-6 hr tail)
❌ stacking           (multiple corrections → hypo)
❌ rebound-high       (overtreatment of low → spike)
❌ exercise-delayed   (hypo 6-12 hrs after exercise)
❌ adrenaline-spike   (stress/competition → transient high)
```

---

## 5. Calibration Pipeline Architecture

### 5.1 Fingerprint Extraction

```
Real Dataset (OhioT1DM, Nightscout, Tidepool)
       │
       ▼
┌──────────────────────┐
│ Statistical           │
│ Fingerprint Extractor │
│                       │
│ • BG distribution     │    Output: fingerprint.json
│ • Time-in-range       │    {
│ • Meal response shape │      "bg_mean": 154,
│ • Overnight pattern   │      "bg_sd": 58,
│ • Insulin delivery    │      "cv": 37.7,
│ • Glycemic variability│      "tir_70_180": 0.62,
│ • Hypo frequency      │      "meal_peak_mg": 72,
│ • Carb:bolus patterns │      "meal_peak_min": 68,
│                       │      ...
└──────────────────────┘    }
```

### 5.2 Simulation Calibration Loop

```
fingerprint.json (target)
       │
       ▼
┌──────────────────────────────────────────────────────┐
│ Calibration Controller                                │
│                                                       │
│ 1. Generate N hours of synthetic data                 │
│    (in-silico-bridge.js with current patient params)  │
│                                                       │
│ 2. Extract synthetic fingerprint                      │
│                                                       │
│ 3. Compute distance metrics:                          │
│    • Wasserstein distance on BG distribution           │
│    • Absolute error on TIR buckets                    │
│    • DTW on meal response shape template              │
│    • KL divergence on glycemic variability            │
│                                                       │
│ 4. If distance > threshold:                           │
│    • Adjust patient profiles (ISF, CR, noise params)  │
│    • Enable/tune CGM noise model                      │
│    • Add meal timing jitter, carb estimation error    │
│    • Re-run from step 1                               │
│                                                       │
│ 5. If distance < threshold:                           │
│    • Lock calibrated patient profiles                 │
│    • Generate conformance vectors                     │
│    • Proceed to algorithm scoring                     │
└──────────────────────────────────────────────────────┘
```

### 5.3 Integration with Autoresearch Loop

```
┌─────────────────────────────────────────────────────────────┐
│                  AUTONOMOUS ALGORITHM LOOP                   │
│                  (program.md experiment cycle)               │
│                                                              │
│  Data Sources (weighted by calibration confidence):          │
│                                                              │
│  ┌─────────────────────┐  ┌──────────────────────┐          │
│  │ Real TV-* Vectors   │  │ Calibrated SIM-*     │          │
│  │ (phone captures)    │  │ (validated synthetic) │          │
│  │                     │  │                       │          │
│  │ Weight: ~35%        │  │ Weight: ~25%          │          │
│  │ Vectors: ~85        │  │ Vectors: unlimited    │          │
│  │ Fidelity: ground    │  │ Fidelity: calibrated  │          │
│  │           truth     │  │           against real │          │
│  └────────┬────────────┘  └────────┬─────────────┘          │
│           │                        │                         │
│  ┌────────▼────────────┐  ┌────────▼─────────────┐          │
│  │ Safety Boundary     │  │ Adversarial Edge     │          │
│  │ Vectors             │  │ Cases                │          │
│  │                     │  │                       │          │
│  │ Weight: HARD GATE   │  │ Weight: ~15%          │          │
│  │ Vectors: 12+        │  │ Vectors: 50+          │          │
│  │ ANY fail → score 0  │  │ Intentionally extreme │          │
│  └────────┬────────────┘  └────────┬─────────────┘          │
│           │                        │                         │
│           └──────────┬─────────────┘                         │
│                      ▼                                       │
│           algorithm_score.py                                 │
│           (composite: 0.0 – 1.0)                             │
│                      │                                       │
│                      ▼                                       │
│           KEEP (improved + safe)                             │
│           DISCARD (regressed or unsafe)                      │
│                      │                                       │
│                      ▼                                       │
│           param-mutation-engine.js                           │
│           (propose next change)                              │
│                      │                                       │
│                      └────────── LOOP FOREVER                │
└─────────────────────────────────────────────────────────────┘
```

---

## 6. Clinical Evaluation Metrics

GluPredKit provides standard clinical metrics that should be integrated into scoring:

| Metric | Module | Use |
|--------|--------|-----|
| **Clarke Error Grid** | `metrics/clarke_error_grid.py` | % in zones A+B (clinical accuracy) |
| **Parkes Error Grid** | `metrics/parkes_error_grid.py` | Modern replacement for Clarke |
| **Glycemia Detection** | `metrics/glycemia_detection.py` | Sensitivity/specificity for hypo/hyper events |
| **MCC Hypo** | `metrics/mcc_hypo.py` | Matthews correlation for hypoglycemia detection |
| **MCC Hyper** | `metrics/mcc_hyper.py` | Matthews correlation for hyperglycemia detection |
| **gRMSE** | `metrics/grmse.py` | Glucose-specific RMSE (penalizes hypo errors more) |
| **Temporal Gain** | `metrics/temporal_gain.py` | How much earlier does prediction detect events? |
| **MAE / RMSE / ME** | `metrics/mae.py`, etc. | Standard prediction error metrics |

These are the metrics regulators (FDA, NICE) use for evaluating CGM and prediction accuracy.
Incorporating them into `algorithm_score.py` would strengthen the clinical validity of the
autonomous improvement loop.

---

## 7. Recommended Scoring Weight Rebalance

### Current Weights (`algorithm_score.py`)

```
20%  decision agreement (rate divergence from e2e vectors)
20%  prediction trajectory MAE (captured vs reconstructed)
20%  strict conformance pass rate (e2e vectors)
15%  trajectory direction agreement
10%  robustness (xval + in-silico)        ← synthetic under-weighted
 5%  simplicity bonus
```

### Proposed Weights (after simulation calibration)

```
25%  decision agreement on real TV-* vectors
20%  prediction trajectory MAE on real TV-* vectors
15%  calibrated synthetic scenario pass rate     ← promoted from 10%
15%  clinical metrics (Clarke/Parkes zone A+B %)  ← NEW
10%  adversarial edge case survival rate          ← NEW
10%  trajectory direction agreement
 5%  simplicity bonus
───
HARD GATE: safety boundary vectors (any fail → score 0.0)
```

---

## 8. Key Architectural Decisions

### Why Two Simulation Engines?

| | CGMSIM (simplified) | UVA/Padova (ODE) |
|---|---|---|
| **Use for** | Fast scenario sweep, parameter exploration | Calibration-grade validation vectors |
| **Speed** | ~1 ms per 5-min tick | ~10–50 ms per 5-min tick |
| **Noise** | Must add externally | Built-in sensor models |
| **State** | Stateless (recalculates from history) | Stateful (13-variable ODE state) |
| **Limitation** | Narrow BG range without noise | Requires initialization, slower |

**Strategy**: Use CGMSIM for the fast inner loop of autoresearch (thousands of parameter
sweeps), use UVA/Padova for the calibration validation layer (confirm that results hold
on higher-fidelity simulation).

### Why Real Data Is Irreplaceable

Simulation cannot capture:

- **Behavioral patterns** — real people forget boluses in predictable ways
- **Device-specific artifacts** — Dexcom G7 vs Libre 3 noise profiles differ
- **Multi-day dynamics** — illness progression, hormonal cycles, travel
- **Psychosocial factors** — alarm fatigue, diabetes distress, override decisions

Real TV-* vectors from phone captures must always carry the highest scoring weight.
Simulation expands coverage; it doesn't replace ground truth.

---

## 9. Source File Reference

| File | Lines | Purpose |
|------|-------|---------|
| `externals/cgmsim-lib/src/CGMSIMsimulator.ts` | ~100 | Simplified simulator entry point |
| `externals/cgmsim-lib/src/UVAsimulator.ts` | ~100 | UVA/Padova simulator entry point |
| `externals/cgmsim-lib/src/sgv.ts` | ~60 | Core glucose calculation |
| `externals/cgmsim-lib/src/liver.ts` | ~60 | Hepatic glucose production model |
| `externals/cgmsim-lib/src/lt1/core/models/UvaPadova_T1DMS.ts` | ~300 | FDA T1DMS ODE model |
| `externals/cgmsim-lib/src/lt1/core/sensors/Breton2008.ts` | — | CGM noise model |
| `externals/GluPredKit/glupredkit/models/uva_padova.py` | ~120 | ReplayBG-based UVA/Padova |
| `externals/GluPredKit/glupredkit/models/loop.py` | ~80 | PyLoopKit prediction wrapper |
| `externals/GluPredKit/glupredkit/parsers/ohio_t1dm.py` | ~170 | OhioT1DM real data parser |
| `externals/GluPredKit/glupredkit/parsers/nightscout.py` | ~540 | Nightscout API data parser |
| `externals/GluPredKit/glupredkit/parsers/tidepool_dataset.py` | — | Tidepool dataset parser |
| `externals/GluPredKit/glupredkit/metrics/` | 15 files | Clinical evaluation metrics |
| `tools/aid-autoresearch/in-silico-bridge.js` | ~550 | Scenario generation via cgmsim-lib |
| `tools/aid-autoresearch/score-in-silico.js` | ~250 | Algorithm scoring against SIM-* vectors |
| `tools/aid-autoresearch/algorithm_score.py` | ~330 | Composite 6-metric scoring |
| `tools/aid-autoresearch/glupredkit_oref0_model.py` | ~390 | oref0→GluPredKit wrapper |
| `tools/aid-autoresearch/glupredkit_loop_model.py` | — | Loop→GluPredKit wrapper |
| `tools/aid-autoresearch/program.md` | ~70 | Autoresearch loop specification |
| `conformance/in-silico/vectors/` | 35 files | Generated SIM-* conformance vectors |

---

## 10. Related Requirements and Gaps

| ID | Description |
|----|-------------|
| REQ-060 | Algorithm validation infrastructure |
| ALG-VERIFY-007 | In-silico bridge generates synthetic scenarios |
| ALG-VERIFY-008 | In-silico scoring against synthetic ground truth |
| ALG-SCORE-001 | Composite algorithm scoring pipeline |
| GAP-ALG-010 | *Proposed*: cgmsim-lib CGMSIM engine produces unrealistically narrow BG range |
| GAP-ALG-011 | *Proposed*: No CGM sensor noise in CGMSIM-engine-generated vectors |
| GAP-ALG-012 | *Proposed*: No meal timing/estimation error in synthetic scenarios |
| GAP-ALG-013 | *Proposed*: No statistical calibration pipeline (real → synthetic fingerprint matching) |
| GAP-ALG-014 | *Proposed*: Clinical metrics (Clarke/Parkes) not integrated into algorithm_score.py |
| GAP-ALG-015 | *Proposed*: Missing 12+ common real-world scenarios (missed bolus, site change, etc.) |
