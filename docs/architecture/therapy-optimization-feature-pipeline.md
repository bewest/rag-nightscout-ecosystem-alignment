# Feature Pipeline: From Fingerprinting to Therapy Optimization

**Status**: Architecture proposal  
**Related**: [Simulation Validation Architecture](simulation-validation-architecture.md)  
**Date**: 2026-03-29

This document describes how the data ingestion and statistical fingerprinting
pipeline — originally designed to calibrate CGM simulators — naturally produces
therapy optimization recommendations as a fourth deliverable. This capability
works for any person with CGM + insulin + carb data, regardless of which dosing
algorithm they use.

For the simulation calibration context, see §3 and §5 of the
[Simulation Validation Architecture](simulation-validation-architecture.md).

---

## 1. Overview: From Fingerprinting to Therapy Optimization

### 1.1 The Core Insight

The data ingestion and statistical fingerprinting pipeline (§3, §5) does not merely
calibrate simulators. **The same analysis that fingerprints a data stream also
identifies therapy optimization opportunities.** This creates a fourth deliverable
from the same infrastructure:

```
                     Data Ingestion Pipeline
                            │
          ┌─────────────────┼─────────────────┐
          │                 │                 │
          ▼                 ▼                 ▼
  (A) Statistical    (B) Scenario       (C) Edge Case
      Fingerprints       Library            Catalog
      ───────────        ───────            ───────
      Calibrate          Test               Test
      simulator          common life        safety
          │                 │                 │
          └────────┬────────┘                 │
                   │                          │
                   ▼                          │
          (D) Therapy Assessment              │
              ─────────────────               │
              Identify individual             │
              optimization                    │
              opportunities                   │
                   │                          │
                   └────────────┬─────────────┘
                                ▼
                   algorithm_score.py + individual reports
```

**Deliverable D emerges naturally** because the fingerprint engine computes exactly
the signals that autotune uses to detect therapy mismatches — just organized
differently:

| Fingerprint Computation | Autotune Equivalent | What It Reveals |
|------------------------|--------------------|--------------------|
| Overnight BG mean deviation from target | Basal period deviations | Basal rate too high/low |
| Post-meal BG peak amplitude vs carbs entered | CR data category | Carb ratio mismatch |
| Post-correction BG trajectory slope | ISF data category | ISF wrong for corrections |
| BG coefficient of variation by time-of-day | Hourly deviation sums | Circadian pattern mismatch |
| TIR% in 70-180 range | Aggregate deviation score | Overall settings quality |
| Spectral power at 24h cycle | Dawn phenomenon signature | Basal schedule missing circadian shape |
| Post-meal duration to return to baseline | DIA/absorption timing | DIA or carb absorption model wrong |

### 1.2 How Data Ingestion Creates All Four Deliverables

When a new data stream enters the pipeline (from any source — Nightscout, Tidepool,
GluPredKit parser, CSV upload), the ingestion process runs the following stages:

```
Raw Data Stream (CGM + insulin + carbs, any source)
        │
        ▼
┌────────────────────────────┐
│ Stage 1: NORMALIZE         │   GluPredKit parser → 5-min DataFrame
│                            │   [date, id, CGM, insulin, carbs, basal, bolus]
│ Any of 12 parsers:         │
│ nightscout.py, tidepool.py │
│ ohio_t1dm.py, IOBP2.py... │
└────────────┬───────────────┘
             │
             ▼
┌────────────────────────────┐
│ Stage 2: CATEGORIZE        │   Autotune-prep logic: classify each reading
│                            │
│ For each 5-min window:     │   → Basal period (fasting, overnight, no IOB)
│   - Compute IOB, COB       │   → Meal period (carbs entered, COB > 0)
│   - Check for carb entry   │   → Correction period (IOB >> basal rate)
│   - Detect unannounced     │   → UAM period (unexplained rise)
│     meal (UAM)             │   → Exercise (HR up, BG dropping, low IOB)
│                            │   → Confounder flag (cyclic, illness, etc.)
└────────────┬───────────────┘
             │
             ▼
┌────────────────────────────┐
│ Stage 3: COMPUTE           │
│                            │
│ Per-subject, per-window:   │   (A) Fingerprint: distribution, temporal, treatment,
│                            │       event-dynamic statistics (Tiers 1-4, §3.2)
│   Aggregate across all     │
│   categorized windows      │   (B) Scenario labels: meal-rise, hypo-recovery,
│                            │       dawn-phenomenon, exercise, missed-bolus,
│                            │       stacking, etc. with severity + frequency
│                            │
│                            │   (C) Edge case flags: BG < 40, BG > 400,
│                            │       >2h CGM gap, impossible deltas, etc.
│                            │
│                            │   (D) Therapy signals: per-hour basal deviation,
│                            │       per-meal CR effectiveness, correction ISF
│                            │       effectiveness, DIA fit quality
└────────────┬───────────────┘
             │
             ▼
┌────────────────────────────┐
│ Stage 4: ASSESS            │
│                            │
│ Compare individual         │   Population comparison:
│ fingerprint against        │   - "Your overnight CV is 2× population median"
│ population norms           │   - "Your post-meal peak is 95th percentile"
│                            │
│ Compute therapy            │   Mismatch detection:
│ mismatch estimates         │   - "Basal appears 25% low between 3-7 AM"
│                            │   - "CR appears 30% wrong for dinner meals"
│                            │   - "ISF corrections overshoot by 20%"
│                            │
│ Identify active            │   Confounder detection:
│ confounders                │   - "~7 day ISF cycle detected (hormonal?)"
│                            │   - "Consistent 4-8 AM drift (dawn phenomenon)"
│                            │   - "Absorption degrades on days 3-4 of site"
└────────────┬───────────────┘
             │
             ▼
        Four Outputs:
        (A) fingerprint.json     → calibrate simulator
        (B) scenario_library/    → test algorithm prediction
        (C) edge_cases/          → test safety boundaries
        (D) therapy_report.json  → actionable optimization recommendations
```

### 1.3 Reverse Mismatch Detection: The Mathematical Foundation

Autotune (oref0, AAPS, Trio) and the fingerprint engine perform the same fundamental
computation — **measuring the gap between what therapy settings predicted and what
actually happened** — but from different starting points:

**Forward (Simulation Mismatch, §4.3):**
```
Known mismatch parameters → Simulate BG trajectory → Measure glycemic variability
```

**Reverse (Data Ingestion → Therapy Assessment):**
```
Observed BG trajectory → Measure deviations from expected → Infer mismatch parameters
```

The key equations (from oref0 autotune, `externals/oref0/lib/autotune/index.js`):

```
Basal mismatch:
  deviation_per_hour = Σ(actual_BG - target_BG) during basal periods
  basal_adjustment = 0.2 × deviation_per_hour / ISF
  → Positive deviation = BG rising = basal too low
  → Negative deviation = BG falling = basal too high

CR mismatch:
  CR_measured = carbs_entered / (insulin_used + correction_needed)
  CR_error = CR_measured / CR_configured
  → Ratio > 1.0: patient needs MORE insulin per carb (CR too high)
  → Ratio < 1.0: patient needs LESS insulin per carb (CR too low)

ISF mismatch:
  ISF_measured = BG_change / correction_insulin_dose
  ISF_error = ISF_measured / ISF_configured
  → Ratio > 1.0: corrections overshoot (ISF too low = patient more sensitive)
  → Ratio < 1.0: corrections undershoot (ISF too high = patient more resistant)
```

The fingerprint engine adds population-level context that autotune lacks:

| Signal | Autotune (Individual) | Fingerprint + Assessment |
|--------|----------------------|--------------------------|
| Basal drift | Adjusts basal ±20% | Compares to population overnight CV; flags if 2× median |
| CR error | Adjusts CR ±20% | Identifies meal-type-specific CR patterns (pizza vs fruit) |
| ISF error | Adjusts ISF ±20% | Detects circadian ISF variation, cyclic hormonal patterns |
| DIA fit | Tests ±2h candidates | Compares IOB decay curve against empirical absorption data |
| Sensitivity ratio | 24h autosens multiplier | Detects multi-day trends (illness, cycle, weight change) |
| TDD trend | 24h vs 7–14d ratio | Correlates with confounder catalog (what's CAUSING the shift) |

### 1.4 What This Enables: Therapy Assessment Without Algorithm Adoption

The critical architectural insight: **a person does not need to use our dosing
algorithm to benefit from the fingerprint pipeline.** They only need data:

| Data Source | What They Need | What They Get |
|-------------|---------------|---------------|
| Nightscout instance | CGM + treatments (any pump/algorithm) | Full therapy assessment report |
| Tidepool export | CSV with CGM + insulin + carbs | Settings mismatch analysis |
| GluPredKit-compatible dataset | Any of 12 supported formats | Population-contextualized fingerprint |
| Raw CGM + manual insulin log | 5-min CGM + bolus/basal timestamps | Basal + ISF + CR mismatch estimates |

The output is a **therapy assessment report**, not an algorithm change:

```json
{
  "subject_id": "patient-123",
  "data_window": { "start": "2026-03-01", "end": "2026-03-15", "days": 14 },
  "fingerprint": {
    "tier1_glucose": { "mean": 162, "sd": 58, "cv": 35.8, "tir_70_180": 61.2 },
    "tier2_temporal": { "overnight_cv": 28.3, "daytime_cv": 41.2, "dawn_rise": 32 },
    "tier3_treatment": { "tdi": 42.5, "basal_bolus_ratio": 0.55, "meals_per_day": 3.2 },
    "population_percentiles": {
      "cv": "p72 (higher variability than 72% of T1D population)",
      "tir": "p38 (lower TIR than 62% of population)",
      "overnight_cv": "p85 (significantly worse overnight control)"
    }
  },
  "therapy_signals": {
    "basal_assessment": {
      "overall": "Basal appears 22% low between 3-7 AM (dawn phenomenon)",
      "hourly_adjustments": [
        { "hour": 3, "current": 0.8, "suggested_direction": "increase", "magnitude": "+18%" },
        { "hour": 4, "current": 0.8, "suggested_direction": "increase", "magnitude": "+25%" },
        { "hour": 5, "current": 0.8, "suggested_direction": "increase", "magnitude": "+22%" },
        { "hour": 6, "current": 1.0, "suggested_direction": "increase", "magnitude": "+15%" }
      ],
      "confidence": "high (14 overnight periods analyzed, consistent pattern)"
    },
    "cr_assessment": {
      "overall": "CR appears approximately correct on average, but varies by meal",
      "by_meal_window": [
        { "window": "breakfast (6-10 AM)", "effective_cr": 8.2, "configured_cr": 10, "error": "-18%" },
        { "window": "lunch (11-14)", "effective_cr": 10.5, "configured_cr": 10, "error": "+5%" },
        { "window": "dinner (17-21)", "effective_cr": 7.1, "configured_cr": 10, "error": "-29%" }
      ],
      "confidence": "moderate (42 meals analyzed, dinner pattern strongest)"
    },
    "isf_assessment": {
      "overall": "ISF appears correct for daytime, but 30% too high overnight",
      "daytime_effective_isf": 42,
      "overnight_effective_isf": 28,
      "configured_isf": 40,
      "confidence": "moderate (18 correction events analyzed)"
    },
    "confounders_detected": [
      {
        "type": "dawn_phenomenon",
        "confidence": "high",
        "pattern": "BG rises 25-40 mg/dL between 3-7 AM on 12 of 14 nights",
        "recommendation": "Increase basal 3-7 AM or enable autotune/dynamic basal"
      },
      {
        "type": "possible_hormonal_cycle",
        "confidence": "low",
        "pattern": "ISF dropped ~25% for days 8-12 of data window then recovered",
        "recommendation": "Monitor over 2-3 months to confirm cyclic pattern"
      },
      {
        "type": "site_degradation",
        "confidence": "moderate",
        "pattern": "Post-meal peaks 20% higher on day 3-4 after site change events",
        "recommendation": "Consider changing sites every 2-3 days instead of 3-4"
      }
    ]
  },
  "scenarios_observed": {
    "total_hours_analyzed": 336,
    "scenario_distribution": {
      "stable_basal": { "hours": 142, "pct": 42 },
      "meal_response": { "count": 45, "avg_peak": 62, "median_duration_min": 135 },
      "hypo_event": { "count": 8, "avg_nadir": 58, "avg_duration_min": 22 },
      "dawn_phenomenon": { "count": 12, "avg_rise": 33 },
      "missed_bolus": { "count": 3 },
      "exercise_related": { "count": 0, "note": "no HR/exercise data available" }
    }
  }
}
```

### 1.5 Data Requirements for Therapy Assessment

The same minimum data windows from §3.2.3 (fingerprint extraction) apply, but with
practical guidance for individual assessment:

| Assessment Level | Data Needed | What You Get | Confidence |
|-----------------|-------------|-------------|------------|
| **Quick screen** | 3 days CGM + insulin | Basal drift direction, gross CR/ISF error | Low — may catch transient confounder |
| **Standard assessment** | 7–14 days CGM + insulin + carbs | Hourly basal profile, meal-window CR, ISF, DIA fit | Moderate — captures weekly pattern |
| **Full assessment** | 28–60 days | Above + cyclic confounders (hormonal), seasonal drift, population percentiles | High — captures monthly variation |
| **Longitudinal tracking** | 90+ days rolling | Trend analysis: are settings improving? New confounders appearing? | Very high — detects slow drift |

**Minimum viable data per assessment:**
- CGM readings: 5-minute interval, ≥80% coverage (per FDA/NICE guidance)
- Insulin: basal rates + bolus timestamps + amounts (from pump or manual log)
- Carbs: meal entries with gram estimates (even rough — ±30% is useful)
- Profile: current ISF, CR, basal schedule, DIA (what the person's pump thinks)

**Enriching optional data:**
- Heart rate / steps → exercise detection
- Site change timestamps → absorption degradation analysis
- Temp targets / overrides → intentional behavioral signals
- Self-reported: illness, menstrual cycle, alcohol, stress → confounder correlation

### 1.6 Population Context: Why Fingerprinting Matters Beyond Individual Tuning

Autotune running on a single patient's data tells that patient how to adjust their
settings. The fingerprint engine, running across 1,000+ subjects from research datasets,
adds something autotune cannot: **population context**.

```
Individual autotune:     "Your basal should be 1.2 U/hr at 4 AM"
Fingerprint + autotune:  "Your basal should be 1.2 U/hr at 4 AM.
                          Your overnight variability is in the 85th percentile.
                          68% of patients with similar TDI and dawn phenomenon
                          use 1.1–1.4 U/hr in this window. Your adjustment
                          is consistent with population norms."
```

This population context provides:

1. **Sanity checking** — if autotune suggests ISF=200 but population p99 is 120,
   something is wrong with the data, not the patient
2. **Confidence calibration** — how much of this patient's variance is explained by
   known factors vs unexplained?
3. **Confounder hypothesis generation** — "patients with similar fingerprints and
   unexplained overnight CV this high tend to have undiagnosed dawn phenomenon or
   hormonal cycling"
4. **Therapy benchmark** — "your TIR is p38; patients with similar TDI and management
   complexity who run autotune/dynamic ISF achieve p55-p65 TIR"

### 1.7 Relationship to Algorithm Validation (Closing the Loop)

Deliverable D feeds back into algorithm validation:

```
Therapy Assessment (D)
        │
        ├──→ Parameterize two-layer mismatch model (§4.3)
        │    "We now know the DISTRIBUTION of real mismatches"
        │    "We can simulate realistic therapy-settings-vs-reality gaps"
        │
        ├──→ Calibrate confounder models
        │    "We know 68% of patients have dawn phenomenon with this magnitude"
        │    "We know hormonal cycling affects ~50% with this ISF shift range"
        │
        ├──→ Weight scenario library by real prevalence
        │    "Missed bolus: 3×/month. Site degradation: noticeable on 30% of days"
        │
        └──→ Define safety boundaries from population data
             "No real patient ever had ISF > 150 — flag as data error"
             "Population p99 for post-meal peak is 280 mg/dL — edge case above this"
```

This creates a **virtuous cycle**: more data ingested → better therapy assessments →
more accurate mismatch parameterization → more realistic simulation → better algorithm
validation → better dosing → better outcomes → more data.

---

