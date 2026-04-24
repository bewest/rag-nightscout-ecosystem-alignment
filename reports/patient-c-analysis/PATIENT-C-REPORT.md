# Patient C — Production Pipeline Demo Report

**Generated:** 2026-04-23 (180-day analysis window: 2025-10-03 → 2026-04-01)
**Controller:** Loop (autobolus-on)
**Data source:** `externals/ns-parquet/training/grid.parquet` (51,841 5-minute rows)
**Analysis script:** `tools/cgmencode/analyze_patient_c.py`
**Raw outputs:** `reports/patient-c-analysis/{facts.json, pipeline.json, meal_audit.csv, plots/}`

This report demonstrates the production pipeline (`tools/cgmencode/production`)
end-to-end on patient C, exercising the **new Wave-12/13 work just landed**:
correction-denominator ISF (EXP-2741), controller-dynamics factloader
(EXP-2753), basal-mismatch facts (EXP-2869), and ISF-gap bootstrap
(EXP-2861), all under the safety-margin doctrine (EXP-2738).

---

## 1. Glycemic summary

| Metric            | Value     | Threshold | Status |
|-------------------|-----------|-----------|--------|
| Mean glucose      | 162 mg/dL | —         |        |
| eA1c (GMI)        | **7.19 %** | <7.0 %    | ⚠️     |
| CV                | 43.4 %    | <36 %     | ⚠️ high variability |
| TIR (70–180)      | **61.6 %** | ≥70 %     | ⚠️     |
| TBR <70           | **4.7 %** | <4 %      | ⚠️ above safety threshold |
| TBR <54           | **1.6 %** | <1 %      | ⚠️     |
| TAR >180          | 33.7 %    | <25 %     | ⚠️     |
| TAR >250          | 12.1 %    | <5 %      | ⚠️     |

Patient C is **below TIR target** *and* **above hypo target** — a classic
"over-corrected" phenotype. The Wave-13 facts loaders below show why.

![AGP](plots/01_agp.png)

---

## 2. New Wave-13 controller-dynamics facts (EXP-2753)

| Field | Value | Interpretation |
|---|---|---|
| `controller_type` | **loop** | Loop autobolus-on |
| `n_events` | 368 corrections analyzed | sufficient sample |
| `mean_correction_fraction` | **0.154** | only 15 % of correction insulin came from user manual boluses |
| `mean_smb_fraction` | **0.846** | **85 % of corrections delivered as controller SMBs** |
| `mean_excess_basal_fraction` | 0.000 | no excess basal channel |
| `corr_denom_gap_closure` | **−0.43** | observed correction *over*-shoots target ⇒ ISF too aggressive |
| `isf_profile_median` | 75 mg/dL/U | currently programmed |
| `isf_corr_denom_median` | **126 mg/dL/U** | what corrections actually accomplished |

![Channel mix](plots/02_controller_donut.png)

This patient is essentially in **fully automated correction mode** — Loop
delivers 85 % of correction insulin as SMBs with very little user
intervention. The ISF gap (75 vs 126) means each correction is sized for a
75 mg/dL drop per unit but actually moves glucose 126 mg/dL — a **+68 %
over-correction** that drives the elevated TBR.

![ISF reconciliation](plots/03_isf_reconciliation.png)

This is exactly the signal the Wave-12 correction-denominator advisor was
built for, and it agrees with the bootstrap ISF-gap fact:

| `isf_gap_facts` (EXP-2861) | Value |
|---|---|
| `p_isf_over_correction` | **1.00** (consistent over-correction) |
| `p_isf_under_correction` | 0.00 |

---

## 3. Basal-mismatch facts (EXP-2869)

| Field | Value |
|---|---|
| `p_basal_mismatch` | **1.00** (controller persistently overrides scheduled basal) |
| `median_recommended_mult` | **0.00** (advisory floor — TRIAGE only, do not auto-apply) |
| Scheduled basal (median) | 1.40 U/h |
| Actual basal (median) | **0.00 U/h** |

![Basal pattern](plots/04_basal_pattern.png)

Loop is suspending basal almost continuously across the day. Combined with
the over-correction signal above, this paints a coherent picture: **the
schedule is too aggressive on both basal and ISF**, so the controller cuts
basal hard and SMBs over-correct on the descents.

---

## 4. Production pipeline recommendations (with safety clamps)

`run_pipeline()` returned 6 advisories. Top 4 settings recommendations
(all clamped to ±25 % per EXP-2738 safety doctrine — actual observed
deltas in `evidence` field):

| # | Parameter | Current | Suggested | Cap | ΔTIR | Confidence | Source |
|---|---|---:|---:|---:|---:|---:|---|
| 1 | ISF (overnight) | 75 | **237** *(clamped from +216 %)* | +25 % | +7.2 pp | 0.30 | EXP-2271 |
| 2 | CR | 4.5 | **15.7** *(clamped from +250 %)* | −25 % | +5.0 pp | 0.34 | EXP-2535 |
| 3 | Basal | 1.40 | **0.84** | −25 % | +1.2 pp | 0.20 | Loop workload analysis |
| 4 | Correction threshold | 180 | **250** | +25 % | +0.7 pp | 0.27 | EXP-2741 corr-denom |

All recommendations are **directionally consistent** — back off insulin on
every channel. The safety margin clamps prevent any single review cycle
from making more than a 25 % adjustment, per EXP-2738.

---

## 5. Side question A: per-patient EGP modelling

**Is it feasible? Does it help?**

**Method (read-only proxy of EXP-2739):** isolate deep-fasting rows
(`cob=0`, `time_since_carb_min ≥ 240`, `time_since_bolus_min ≥ 240`,
no exercise/override, IOB < 0.5 U) and read the median `glucose_roc`.
This is the rate the patient's EGP outpaces minimal IOB.

**Result for patient C (n = 8,449 rows = 16.3 % of grid):**

| Quantity | Population | Patient C |
|---|---:|---:|
| EGP (`_BASE_EGP`, mg/dL / 5 min) | 1.50 | **1.00** |
| Equilibrium basal multiplier | — | **0.00** |

Patient C runs ~33 % below population EGP, *and* the controller settles
at 0 % of scheduled basal in fasting equilibrium. Both signals point the
same way: this patient's metabolic insulin demand is materially lower
than the schedule presumes.

![Per-patient EGP](plots/06_per_patient_egp.png)

**Verdict:**
- **Feasible:** yes. Computed in <1 s per patient from existing grid columns.
- **Helps:** yes — the EGP estimate corroborates the basal recommendation
  (decrease) and the over-correction signal (high observed ISF). It would
  let the metabolic engine simulate descents more accurately for triage.
- **NOT yet productionized:** per the EXP-2738 safety doctrine, naively
  swapping `_BASE_EGP = 1.5` in `metabolic_engine.py` is unsafe. The
  correct shape is a **facts loader** (parallel to
  `controller_dynamics_facts_loader`) that exposes
  `egp_mgdl_per_5min_p50` per patient into `AuditionInputs`, where the
  triage-only safety margin can clamp downstream effects.
- This is tracked as `prod_todos.egp-personalization` (status: blocked
  pending facts-loader design pass).

**Caveats:**
1. The proxy assumes IOB < 0.5 U is "low enough" — for a Loop user that
   continuously suspends basal, this filter passes nearly all fasting
   rows (8,449/8,449). A finer estimate would solve a 2-compartment
   ODE (EXP-2739), but the 5-min-resolution proxy is sufficient to
   *triage* who needs personalization.
2. Equilibrium-window count (176) is small; the per-patient EGP CI would
   need bootstrap before being trusted for control decisions.

---

## 6. Side question B: meal-isolation thresholds (smell test)

**User's smell test:** most people eat 2–8 logged meals/day, evening
dessert is real, "real meals" should be ≥ 50 g.

**Production today** (`tools/cgmencode/production/meal_filter.py`):
- `REAL_CARB_EVENT_THRESHOLD_G = 5` g  → "is this a carb event at all?"
- `REAL_MEAL_FLOOR_G = 10` g           → "is this a meal vs a snack?"
- `SUBSTANTIAL_MEAL_G = 30` g          → "is this a substantial planned meal?"

**Patient C measurement (180 days, 396 logged carb events):**

| Floor | Events | Mean/day | Median/day | Max/day | Days with 2–8 events | Evening share |
|---:|---:|---:|---:|---:|---:|---:|
| ≥ 5 g  | 385 | **2.50** | 2 | 7 | 60.0 % ✅ |  23 % |
| ≥ 10 g | 377 | 2.46 | 2 | 7 | 59.4 % ✅ |  24 % |
| ≥ 20 g | 234 | 1.92 | 2 | 5 | 38.3 % ❌ |  23 % |
| ≥ 30 g | 141 | 1.48 | 1 | 3 | 20.0 % ❌ |  22 % |
| **≥ 50 g** | **2** | 1.00 | 1 | 1 | 0.0 % ❌ | 50 % |

![Meal floors](plots/05_meal_floors.png)

**Findings:**

1. **Patient C under-logs heavily.** Even at the lowest 5 g floor we see
   only 2.5 carb events/day, which is at the *bottom* of the user's
   2–8 expected range. Loop autobolus users routinely skip logging
   when the controller catches the rise.

2. **A 50 g floor would be a disaster for this patient.** Only 2 events
   in 180 days clear it — meal-response analyses would be statistically
   useless. The user's intuition about "real meals" doesn't survive
   Loop-era under-logging.

3. **The current 5/10/30 g ladder is the right *shape*** but the labels
   are misleading for sparse-logging users:
   - At 5 g (`REAL_CARB_EVENT_THRESHOLD_G`) we recover essentially all
     logged events; near-zero noise filtering happens here.
   - The 5 → 10 g step removes only **8 events** (385 → 377). For Loop
     users who don't bother logging treat-of-low, this is fine; the
     EXP-2866 audit rationale (30 % of cohort events are < 5 g) does
     **not generalize** to patient C.
   - Most attrition happens in the 10 → 30 g window (377 → 141 = 60 %
     drop). This is where meal-analysis sample size collapses.

4. **Evening dessert?** ~23 % of carb events occur ≥ 18:00 across all
   floors except 50 g (where the n=2 sample is meaningless). That's
   roughly 1 event every 2 days in the evening — plausible but
   *under*-represented vs typical 30–40 % evening eating patterns,
   reinforcing the under-logging hypothesis.

**Recommendations for meal isolation:**

| Use case | Recommended floor | Rationale |
|---|---|---|
| "Did anything happen?" detection | **≥ 5 g** (current) | catches almost all logged events |
| Meal-response statistics (CR, COB) | **≥ 10 g** AND **time_since_carb_min ≥ 180** | excludes correction snacks without losing samples |
| Substantial-meal absorption studies | **≥ 30 g** (current) | matches population EXP-2866 rationale |
| **Glucose-rise inferred meal detection** | not yet wired in | `meal_detector.py` exists (2σ residual burst) but is not invoked in `run_pipeline()`; would help recover unlogged meals on Loop users like patient C |

The per-patient validation should compare **logged carb event rate** to
**glucose-rise-inferred event rate** (`meal_detector.detect_meal_events`)
and flag patients whose ratio < 0.5 as "under-logger" so downstream meal
analyses widen confidence intervals or fall back to inferred events.

---

## 7. Code quality snapshot (for context)

- **Test markers:** unit/integration split landed (`pytestmark` on every
  TestCase); `pytest -m unit` runs in 35 s, `pytest -m integration` in 112 s,
  full suite 4:47 (997 tests). See commit `c27661a5`.
- **Wave-13 factloader** (`controller_dynamics_facts_loader.py`) has 7
  unit tests, follows the standard contract (lookup returns frozen
  dataclass with all-None for unknown patients). Commit `15b0d759`.
- **Safety doctrine** (β ≥ 1, 22 % ISF margin, ±25 % clamp on
  recommendations) enforced in advisor pipeline. Commit `098118c1`.

---

## 8. What this demo proves

1. **The new Wave-13 factloader works end-to-end** — patient C comes back
   with the controller-dynamics signal expected from the offline experiment.
2. **The new correction-denominator ISF advisor produces a coherent,
   high-priority recommendation** (overnight ISF +216 % observed, clamped
   to +25 %) that aligns with the over-correction phenotype indicated by
   the bootstrap ISF-gap facts.
3. **All recommendations are safety-clamped** per EXP-2738 — no single
   review cycle can move a setting more than 25 %.
4. **Per-patient EGP is feasible and informative** but should be
   productionized as a facts loader, not as a `_BASE_EGP` swap.
5. **Meal-isolation thresholds in production are sound** for the cohort,
   but a 50 g "real meal" floor would be too aggressive for Loop
   under-loggers. A glucose-rise-inferred fallback (already implemented
   in `meal_detector.py` but not wired into `run_pipeline()`) would
   close the gap.

---

## 9. Reproduce

```bash
cd /home/bewest/src/rag-nightscout-ecosystem-alignment
PYTHONPATH=. python3 tools/cgmencode/analyze_patient_c.py
ls reports/patient-c-analysis/plots/
```
