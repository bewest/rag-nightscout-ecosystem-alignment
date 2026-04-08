# Autotune & UAM Characterization Report

**Date**: 2026-04-08
**Patients analyzed**: 10 (a–k, excluding j)
**Total glucose readings**: 511951
**Total hours of data**: 42663

## Executive Summary

This report characterizes two key inference capabilities across AID systems:
**Autotune** (parameter optimization) and **UAM** (unannounced meal detection).
We compare oref0's heuristic algorithms (used identically by oref0, AAPS, and Trio)
with physics-based ML approaches (cgmencode pipeline) on 10 patients
with ~180 days of continuous data each.

### Key Findings

1. **UAM Detection**: Physics-based ML achieves mean F1=0.513
   vs oref0's mean F1=0.344 — ML wins.
2. **Unannounced meals** account for 68% of all glucose rise events —
   both approaches struggle with this fundamental ambiguity.
3. **Effective ISF is 1.4× profile ISF** — AID loop compensation
   masks inadequate settings, limiting what autotune can discover.
4. **Loop runs at scheduled basal only 0–5% of the time** — the loop itself IS
   the dominant controller, not the settings.

---

## 1. UAM (Unannounced Meal) Detection

### 1.1 Algorithm Comparison

| System | Method | Key Mechanism |
|--------|--------|---------------|
| **oref0/AAPS/Trio** | Heuristic state machine | IOB > 2×basal AND deviation > 0 |
| **Loop** | Missed Meal Detection + IRC | Retrospective PID on 180-min window |
| **cgmencode (Physics)** | Residual burst detection | 2σ threshold on supply-demand residual |

**Note**: oref0, AAPS, and Trio use algorithmically identical UAM detection.
Loop's approach is fundamentally different (retrospective vs forward-looking).

### 1.2 Per-Patient Results

| Patient | Events | Unann. | oref0 F1 | Physics F1 | oref0 Prec | Physics Prec | oref0 Rec | Physics Rec |
|---------|--------|--------|----------|------------|------------|--------------|-----------|-------------|
| a | 1938 | 1475 | 0.564 | 0.564 | 0.426 | 0.655 | 0.835 | 0.495 |
| b | 1772 | 278 | 0.211 | 0.261 | 0.648 | 0.618 | 0.126 | 0.165 |
| c | 1875 | 1455 | 0.467 | 0.587 | 0.481 | 0.744 | 0.453 | 0.485 |
| d | 1287 | 959 | 0.315 | 0.535 | 0.239 | 0.599 | 0.461 | 0.484 |
| e | 1521 | 1171 | 0.366 | 0.532 | 0.297 | 0.505 | 0.478 | 0.561 |
| f | 1516 | 1128 | 0.387 | 0.685 | 0.325 | 0.749 | 0.479 | 0.631 |
| g | 1783 | 997 | 0.323 | 0.596 | 0.238 | 0.709 | 0.502 | 0.515 |
| h | 713 | 470 | 0.372 | 0.418 | 0.375 | 0.289 | 0.368 | 0.753 |
| i | 1660 | 1516 | 0.318 | 0.485 | 0.283 | 0.445 | 0.361 | 0.533 |
| k | 485 | 467 | 0.122 | 0.464 | 0.072 | 0.359 | 0.413 | 0.655 |

### 1.3 Aggregate Statistics

| Metric | oref0 UAM | Physics ML |
|--------|-----------|------------|
| **Mean F1** | 0.344 ± 0.116 | 0.513 ± 0.110 |
| **Mean Precision** | 0.338 ± 0.149 | 0.567 ± 0.153 |
| **Mean Recall** | 0.448 ± 0.165 | 0.528 ± 0.147 |
| **Total Unannounced Events** | 9916 | 9916 |
| **Unannounced Rate** | 68.2% | 68.2% |

### 1.4 How Each Approach Works

**oref0 UAM** operates as a binary state machine:
- Enters UAM state when `IOB > 2×basal_rate` AND glucose is rising faster than insulin explains
- Persists in UAM while deviation remains positive
- Exits when deviation goes negative
- Excludes UAM periods from autosens sensitivity calculation
- **Strength**: Simple, deterministic, safety-focused
- **Weakness**: IOB threshold is arbitrary; can't distinguish UAM from dawn phenomenon

**Physics-based ML** uses supply-demand decomposition:
- Computes expected glucose change from insulin absorption + known carb absorption
- Residual = actual change - expected change
- Detects positive residual bursts exceeding 2σ (adaptive threshold)
- **Strength**: Accounts for known physiological effects; quantifies uncertainty
- **Weakness**: Requires accurate PK model; ground truth is still ambiguous

**Loop's Missed Meal Detection** (different paradigm):
- Does NOT do real-time UAM detection
- Retrospectively identifies unexplained glucose rises
- Uses Integral Retrospective Correction (IRC) — a PID controller on prediction errors
- **Strength**: Handles all unmodeled effects, not just meals
- **Weakness**: Purely reactive; no predictive capability

### 1.5 Practical Implications

- **For AID dosing**: oref0's approach is appropriate — conservative, safety-focused,
  and designed for real-time insulin adjustment. The IOB threshold prevents false UAM
  during low-insulin periods.
- **For alerting/notification**: Physics ML approach is better suited — probabilistic
  output allows tunable sensitivity, and the residual-based method is more specific.
- **For clinical analysis**: Neither approach provides true meal prediction. Both are
  reactive (detecting meals as they happen, not before). The 7.5-min average lead time
  from previous ML experiments is at the detection ceiling.

---

## 2. Autotune (Parameter Optimization)

### 2.1 Algorithm Comparison

| System | Available? | Method | Adjustment Rate |
|--------|-----------|--------|----------------|
| **oref0** | ✅ | 3-bucket categorization + 20% blend | Conservative (≤20%/iteration) |
| **AAPS** | ✅ | 1:1 Kotlin port of oref0 | Identical |
| **Trio** | ✅ | Embedded oref0 JS (identical) | Identical |
| **Loop** | ❌ | None — settings are manual | N/A |
| **cgmencode** | ⚠️ Research | Physics forward model + ML | Retrospective analysis |

### 2.2 Autotune Basal Recommendations

oref0's autotune recommends basal adjustments based on fasting glucose deviations.
The algorithm:
1. Identifies fasting periods (no carbs, COB ≈ 0)
2. Computes deviation = actual ΔBG - expected BGI (from insulin)
3. Adjusts basal for 3 hours prior to observed deviation (accounts for insulin lag)
4. Applies only 20% of the calculated change (conservative)
5. Caps at ±20% of pump basal

See **Figure 3** for per-patient basal profile recommendations.

### 2.3 Fasting Deviation Patterns

See **Figure 4** for the hour × patient deviation heatmap.

**Dawn Phenomenon**: 3/10 patients show elevated
fasting deviations during 4–8am vs midnight–4am, consistent with the universal
dawn phenomenon finding (71.3±18.7 mg/dL amplitude) from previous research.
Patients: b, d, h.

**Deviation Magnitude**: Hourly deviations vary widely across patients (0–21 U/hr range), with median values typically 3–6 U/hr. The large range reflects inter-patient variability in basal needs, dawn phenomenon intensity, and AID loop compensation behavior.

### 2.4 Effective ISF vs Profile ISF

| Patient | Profile ISF (mg/dL) | Effective ISF (mg/dL) | Ratio | Interpretation |
|---------|--------------------|-----------------------|-------|----------------|
| a | 48.6 | 45.8 | 0.94× | Adequate |
| b | 90.0 | 76.5 | 0.85× | Adequate |
| c | 72.0 | 95.6 | 1.33× | Adequate |
| d | 40.0 | 87.3 | 2.18× | Profile too aggressive |
| e | 33.0 | 73.3 | 2.22× | Profile too aggressive |
| f | 21.0 | 24.2 | 1.15× | Adequate |
| g | 70.0 | 103.1 | 1.47× | Adequate |
| h | 92.0 | 64.9 | 0.71× | Adequate |
| i | 55.0 | 101.5 | 1.84× | Profile too aggressive |
| k | 25.0 | 23.3 | 0.93× | Adequate |

**Mean effective/profile ISF ratio: 1.36×**

This confirms the key finding from cgmencode research: AID systems compensate for
inaccurate settings by adjusting temp basal rates. When ISF is set too low
(insulin is actually more effective than settings indicate), the loop suspends
basal more often. When ISF is too high, the loop increases basal.

### 2.5 What Autotune Can and Cannot Discover

**Can discover**:
- Circadian basal rate patterns (dawn phenomenon → increase morning basal)
- Gross ISF miscalibration (>30% off)
- CR drift if sufficient meal data exists

**Cannot discover**:
- True effective ISF masked by AID compensation (the 1.4× discrepancy)
- Real-time sensitivity changes (autosens handles this, not autotune)
- Exercise effects on sensitivity
- Meal composition effects (protein/fat vs carbs)

**oref0's autotune limitation**: Because the algorithm uses a 20% blend
(80% current + 20% recommended), convergence to correct settings takes
many iterations. With ±20% caps, extreme miscalibration takes 5+ daily
runs to correct. This is by design (safety), but means:
- **Conservative ≈ slow**: 5–10 iterations to converge to correct basal
- **Stability ≈ inertia**: Settings resist change even when change is needed

---

## 3. Cross-System Characterization

### 3.1 Approach Taxonomy

| Dimension | oref0/AAPS/Trio | Loop | cgmencode ML |
|-----------|----------------|------|--------------|
| **Philosophy** | Rule-based + percentile statistics | Model-based prediction + PID | Physics decomposition + ML |
| **UAM** | Forward state machine | Retrospective correction | Residual burst detection |
| **Autotune** | Conservative iterative adjustment | None (manual only) | Counterfactual simulation |
| **Safety** | Built-in caps (±20%, min/max) | Built-in guardrails | No inherent safety limits |
| **Transparency** | Fully deterministic | Model-dependent | Black-box for ML components |
| **Data needs** | 24h minimum | Continuous | Days to weeks (training) |
| **Adaptation speed** | Hours (autosens), days (autotune) | Minutes (IRC) | Offline (batch) |

### 3.2 Practical Use Case Recommendations

| Use Case | Best Approach | Why |
|----------|---------------|-----|
| **Real-time insulin dosing** | oref0/Loop | Safety-critical → need conservative, deterministic |
| **Meal detection for alerts** | Physics ML | Probabilistic output → tunable sensitivity |
| **Settings optimization** | oref0 autotune + ML validation | Autotune for safety; ML to verify convergence |
| **Clinical review** | cgmencode | Retrospective analysis, counterfactual reasoning |
| **Patient onboarding** | oref0 autotune | Proven, incremental, safe starting point |
| **Research/phenotyping** | cgmencode | Rich feature set, cross-patient comparison |

---

## 4. Visualizations

| Figure | Description | File |
|--------|-------------|------|
| Fig 1 | UAM Detection Performance (F1/Precision/Recall) | `fig1_uam_performance.png` |
| Fig 2 | UAM Event Counts and Detection Rates | `fig2_uam_events.png` |
| Fig 3 | Autotune Basal Profile Recommendations | `fig3_autotune_basal.png` |
| Fig 4 | Fasting Deviation Heatmap (Hour × Patient) | `fig4_deviation_heatmap.png` |
| Fig 5 | Profile vs Effective ISF Comparison | `fig5_isf_comparison.png` |
| Fig 6 | Algorithm Characterization Summary | `fig6_algorithm_summary.png` |

---

## 5. Methodology Notes

### Data
- **Source**: Nightscout continuous monitoring data (CGM + insulin + carbs)
- **Patients**: 10 (labeled a–k, excluding j for limited treatments)
- **Duration**: ~180 days per patient
- **CGM**: Dexcom G6/G7, 5-minute intervals
- **AID System**: Loop (all patients)

### UAM Evaluation
- **Ground truth**: Glucose rise events >30 mg/dL over 60 minutes
- **Announced**: Carb entry within ±30 min of event
- **Unannounced**: No carb entry near event
- **oref0 UAM**: Simulated using oref0's state machine (IOB > 2×basal + deviation > 0)
- **Physics ML**: Residual burst detection (2σ adaptive threshold)

### Autotune Evaluation
- **Fasting periods**: No carbs for ≥3 hours
- **Deviations**: Actual glucose change - expected change from insulin (BGI)
- **BGI calculation**: Approximated from IOB changes and ISF
- **Autotune simulation**: oref0's 20% blend, ±20% cap, 3-hour retroactive adjustment
- **Effective ISF**: Measured from correction bolus outcomes during non-meal periods

### Limitations
- Loop's actual UAM behavior cannot be directly observed (missed meal detection
  is internal; we see its effects through temp basal adjustments)
- BGI approximation from IOB differences is less accurate than oref0's activity-based
  calculation (which requires the full IOB curve)
- Autotune simulation runs one iteration (not the multi-day iterative process)
- Profile ISF may be in mmol/L units; conversion factor applied but may vary
