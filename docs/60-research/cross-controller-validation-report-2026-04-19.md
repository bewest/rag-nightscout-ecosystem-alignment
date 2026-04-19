# EXP-2671: Cross-Controller Data Fidelity Validation Report

**Date**: 2026-04-19  
**Dataset**: 31 patients × 1,293,810 grid rows (Loop=9, Trio=13, OpenAPS=8, unknown=1)  
**Figures**: `visualizations/cross-controller-validation/fig[1-8]_*.png`  
**Results**: `externals/experiments/exp-2671_cross_controller_validation.json`

---

## Executive Summary

Before scaling ISF/correction experiments to the expanded multi-controller dataset,
we validated that the ns2parquet pipeline produces semantically comparable fields
across Loop, Trio, and OpenAPS. **Core fields (glucose, IOB, bolus, carbs,
actual\_basal\_rate, scheduled\_isf) are safe for cross-system analysis.** Three
issues require mitigation before autoresearch proceeds.

### Verdict

| Category | Status | Action |
|----------|--------|--------|
| Core fields (glucose, iob, cob, bolus, carbs, net\_basal) | ✅ PASS | Safe for cross-system use |
| Basal rate fields (actual, scheduled, net) | ✅ PASS | Derived from treatments with % handling |
| Correction event detection | ✅ PASS | Comparable rates across controllers |
| Enacted rate (devicestatus) | ⚠️ FAIL | odc-96254963 percent-encoded; exclude or fix |
| IOB decay semantics | ⚠️ CAUTION | AID-contaminated; not raw insulin kinetics |
| Controller-specific fields | ℹ️ KNOWN | sensitivity\_ratio, eventual\_bg: Loop=0% by design |
| Flagged patients | ⚠️ 8 of 31 | Exclude or qualify per experiment |

---

## Panel-by-Panel Findings

### Panel 1: Core Field Distributions

| Field | Loop | Trio | OpenAPS | Interpretation |
|-------|------|------|---------|----------------|
| Glucose (mg/dL) | 148 ± wide | 131 ± tight | 141 ± wide | Real population difference; Trio cohort trends lower |
| IOB (U) | 1.8 (p50=0.74) | 1.1 (p50=0.06) | 0.8 (p50=0.0) | **Trio/OpenAPS IOB median ≈0**: controller reports IOB=0 most of the time |
| COB (g) | 3.2 | 7.4 | 4.5 | Trio patients log more carbs (see Panel 8) |
| Bolus size | 0.55 U | 0.54 U | 0.71 U | Comparable; OpenAPS slightly larger (fewer SMBs) |
| Net Basal | −0.56 | −0.67 | −0.39 | All controllers reduce below scheduled rate — expected |
| Scheduled ISF | 51 | 76 | 76 | Loop patients have lower ISF (more insulin-sensitive settings) |

**Key insight**: The IOB median near zero for Trio/OpenAPS means IOB is reported
as 0.0 when the controller isn't looping, which is ~40-50% of the time.
This is semantically different from Loop, where IOB reflects continuous
insulin-activity accounting. Experiments using IOB should be aware that the zero
mass differs by controller.

### Panel 2: Glycemic Outcomes (TIR / TBR)

- TIR ranges 55-95% across all patients — realistic clinical variation
- **No controller-type clustering**: Loop, Trio, OpenAPS all span the full range
- Several short-span OpenAPS patients (<30 days) — TIR estimates unreliable
- TBR 1-13% — some patients run aggressive settings (TBR>4% safety limit)

**Conclusion**: Glycemic outcomes vary by patient, not by controller type. This
is reassuring — controller type doesn't systematically bias glucose distributions
in ways that would confound cross-system analysis.

### Panel 3: Correction Event Detection Equivalence

| Controller | Events | Rate (corr/day) | Median Pre-BG | Median Dose |
|------------|--------|-----------------|---------------|-------------|
| Loop | 6,876 | ~4.3/day | ~210 mg/dL | ~1.1 U |
| Trio | 7,600 | ~4.1/day | ~170 mg/dL | ~0.9 U |
| OpenAPS | 1,168 | ~1.0/day | ~190 mg/dL | ~0.9 U |

**Key findings**:
- Loop and Trio detection rates are comparable (~4/day) — **detector is not biased
  by SMB frequency**
- OpenAPS detection rate is lower (1/day) because:
  - 4 of 8 odc patients have <30 days of data
  - OpenAPS patients use fewer manual correction boluses (rely more on temp basal)
- Trio corrections happen at lower glucose (170 vs 210) — real behavioral
  difference (Trio users correct more proactively)
- Dose distributions are comparable across controllers

**Conclusion**: Correction detector works equivalently. OpenAPS low rate is
real (behavioral), not a pipeline artifact.

### Panel 4: IOB Decay Curves — ⚠️ IMPORTANT FINDING

| Controller | IOB @ 3h | IOB @ 5h | N events | Expected |
|------------|----------|----------|----------|----------|
| Loop | 1.11× | 0.79× | 282 | ~0.22× |
| Trio | 0.96× | 1.16× | 95 | ~0.22× |
| OpenAPS | 0.74× | 0.58× | 83 | ~0.22× |

**None of the controllers show the expected exponential decay.** This is NOT a
bug — it reveals a fundamental property of AID systems:

1. **Loop**: IOB initially INCREASES (to 1.3× at ~30min) because the controller
   sees the correction bolus, recognizes high glucose, and adds more insulin
   (temp basals or additional SMBs). Decays slowly after ~2h.

2. **Trio**: IOB stays flat ~1.0× for 3+ hours, then oscillates upward. Trio's
   aggressive SMB strategy keeps firing micro-boluses that replenish IOB as fast
   as it decays. The "isolated bolus" is never truly isolated.

3. **OpenAPS**: Most reasonable decay (0.74× at 3h), because these odc patients
   use fewer SMBs. But still above the theoretical curve due to temp basal
   contributions.

**Implication for experiments**: The `iob` column reflects **total system IOB**
(bolus + basal + SMB), not pharmacokinetic decay of a single bolus. This is
correct data — it just means:
- IOB-based isolation windows must account for controller-added insulin
- "Isolated correction" is a spectrum, not binary
- The 6h prior-bolus isolation (EXP-2666) partially addresses this
- Cross-controller IOB comparisons need the controller context

**This validates the existing experimental approach**: EXP-2663–2666 use
glucose drop and bolus dose (not IOB) for ISF extraction, sidestepping
the IOB contamination issue. The experiments are sound.

### Panel 5: Enacted Rate vs Actual Basal — Bug Confirmed

- **Loop**: Clean y=x relationship ✅
- **Trio**: Clean y=x relationship ✅ (12 patients, one high outlier at 8 U/h)
- **OpenAPS**: **odc-96254963 has percent-encoded enacted\_rate** (red cluster
  at 50-150 while actual\_basal is 1-2 U/h) ⚠️

The bug is **isolated to `loop_enacted_rate`** for one patient. The `actual_basal_rate`
and `net_basal` fields (derived from treatments) are correct because the pipeline
already handles percent-based temp basals at line 464-476 of grid.py.

**Remediation**: Either:
1. Fix in `grid.py` devicestatus processing (detect enacted.rate > 10× scheduled → divide by 100)
2. Or exclude odc-96254963 from analyses using `loop_enacted_rate`

Experiments using only `actual_basal_rate` (EXP-2667, 2668) are unaffected.

### Panel 6: Field Coverage Heatmap

Three clear coverage tiers:

**Tier 1 — Universal (100% all controllers)**:
glucose, iob, cob, net\_basal, bolus, bolus\_smb, carbs, scheduled\_isf,
scheduled\_cr, actual\_basal\_rate, scheduled\_basal\_rate

**Tier 2 — Majority (60-96%)**:
glucose\_roc, glucose\_accel, loop\_predicted\_30/60/min,
loop\_enacted\_rate, loop\_enacted\_bolus

**Tier 3 — Controller-specific**:
- `sensitivity_ratio`: Loop=0%, Trio=57%, OpenAPS=31%
- `eventual_bg`: Loop=0%, Trio=57%, OpenAPS=51%
- `insulin_req`: Loop=0%, Trio=57%, OpenAPS=47%

Loop does not emit these fields (they come from oref0's `suggested` object).
This is a schema difference, not a pipeline bug. Loop's equivalent is the
`loop.predicted.values` array, which feeds `loop_predicted_30/60`.

**For cross-system experiments**: Use Tier 1 fields only. Tier 3 fields
enable controller-specific analyses (e.g., sensitivity\_ratio for DynISF
validation) but cannot be compared across Loop vs Trio.

### Panel 7: 48h Glucose Traces

- **Loop (patient d)**: Rich data — continuous glucose, frequent boluses,
  IOB 2-8U, smooth traces. Textbook AID operation.
- **Trio (patient b)**: Similar richness — IOB 2-16U(!), more volatile glucose.
  Higher IOB reflects more aggressive SMB dosing.
- **OpenAPS (odc-86025410)**: **IOB scale is −0.04 to +0.04 U** — essentially
  zero throughout. This patient has very low insulin requirements OR the IOB
  field is not being populated correctly from the OpenDataCommons export.

**Follow-up needed**: Investigate whether odc-86025410's near-zero IOB reflects
real low requirements or a data extraction issue specific to OpenDataCommons
format.

### Panel 8: Per-Patient Metrics

Key patterns:
- **Boluses/Day**: Loop 3-78/day, Trio 30-70/day, OpenAPS 2-65/day.
  Wide range within each controller type.
- **SMBs/Day**: Loop patients (a, c-i) all have 55-75 SMBs/day.
  Most Trio patients: 25-70/day. Most OpenAPS: near zero except
  odc-74077367 (30/day) and odc-96254963 (28/day).
- **Mean IOB**: Loop 1-3.5U, Trio 0.2-2.3U, OpenAPS 0.2-2U.
- **Carbs/Day**: Most patients 2-8/day. **odc-49141524 = 35/day** — suspicious
  (likely auto-logged carbs or duplicate entries).

**Flagged patients**:

| Patient | Controller | Issue | Recommendation |
|---------|-----------|-------|----------------|
| j | unknown | Zero IOB, COB, enacted rate | **EXCLUDE** from all analyses |
| h | loop | Low glucose coverage (<50% non-null) | Qualify: exclude from glucose-dependent analyses |
| odc-84181797 | openaps | IOB mostly zero, low glucose coverage | Qualify: 139 days of data but poor field coverage |
| odc-39819048 | openaps | 10 days of data | Qualify: short-span only |
| odc-49141524 | openaps | 8 days, 35 carbs/day | Qualify: short-span, investigate carb anomaly |
| odc-58680324 | openaps | 10 days | Qualify: short-span only |
| odc-61403732 | openaps | 10 days | Qualify: short-span only |
| ns-c422538aa12a | trio | IOB~0, few boluses | Investigate: possibly sensor-only user |

---

## Cross-System Qualification for Autoresearch

### Safe Patient Pool (Qualified for Cross-System Experiments)

After excluding flagged patients:

| Controller | Qualified Patients | Total Days |
|------------|-------------------|------------|
| Loop | 8 (a, c, d, e, f, g, i, k) | ~1,170 |
| Trio | 12 (b, ns-* except c422) | ~1,800 |
| OpenAPS | 3 (odc-74077367, odc-86025410, odc-96254963*) | ~750 |
| **Total** | **23 patients** | **~3,720 days** |

*odc-96254963: exclude from enacted\_rate analyses but safe for glucose/bolus/ISF

### Columns Safe for Cross-System Analysis

```
glucose, iob, cob, net_basal, bolus, bolus_smb, carbs,
scheduled_isf, scheduled_cr, actual_basal_rate, scheduled_basal_rate,
glucose_roc, glucose_accel, time, patient_id
```

### Columns Requiring Controller-Aware Handling

```
sensitivity_ratio     → Trio/OpenAPS only (use for DynISF validation)
eventual_bg           → Trio/OpenAPS only (≈Loop predicted at long horizon)
loop_enacted_rate     → Exclude odc-96254963 or fix percent encoding
loop_predicted_30/60  → Available for all but different source (single curve vs best-of-4)
```

---

## Issues to Fix Before Autoresearch

### P0 — Must Fix

1. **Patient exclusion list**: Codify {j} as permanent exclusion.
   Qualify {h} for low glucose coverage (<50% non-null).
   Qualify {odc-84181797} for IOB mostly zero + low glucose coverage.
   Add short-span qualifier for {odc-39819048, odc-49141524, odc-58680324,
   odc-61403732}. Investigate ns-c422538aa12a.

2. **Enacted rate percent-encoding**: Fix for odc-96254963 in grid.py
   devicestatus normalization (detect rate > 10 × scheduled\_basal → likely
   percentage → convert).

### P1 — Should Fix

3. **IOB semantics documentation**: Document that IOB = total system IOB
   including controller-added insulin. Not pharmacokinetic single-bolus decay.

4. **odc-86025410 IOB investigation**: Verify whether near-zero IOB is real
   (very low requirements) or data extraction issue.

5. **odc-49141524 carb anomaly**: 35 carb entries/day — investigate source.

### P2 — Nice to Have

6. **Loop eventual\_bg equivalent**: Consider computing eventual\_bg for Loop
   from predicted\_values (last element of prediction array).

7. **Unified sensitivity\_ratio**: For Loop, compute from autosens or ISF
   schedule to enable cross-controller autosens comparison.

---

## Implications for Prior Experiments

| Experiment | Uses | Cross-System Safe? |
|-----------|------|-------------------|
| EXP-2663 (Dose-dep ISF) | glucose, bolus, carbs | ✅ Yes |
| EXP-2664 (Circadian ISF) | glucose, bolus, carbs, time | ✅ Yes |
| EXP-2665 (Nyquist) | glucose, bolus, carbs, time | ✅ Yes |
| EXP-2666 (Isolation) | glucose, bolus, carbs, time | ✅ Yes |
| EXP-2667 (SC ceiling) | glucose, iob, bolus, actual\_basal | ✅ Yes |
| EXP-2668 (Controller ISF) | glucose, iob, bolus\_smb, actual\_basal | ✅ Yes |
| EXP-2669 (Wall resolution) | glucose, iob, bolus, glucose\_roc | ✅ Yes |

**All recent experiments use only safe columns.** Results are valid for
cross-system scaling.

---

## Next Steps: Autoprepare → Autoresearch Transition

### Phase 1: Autoprepare ✅ COMPLETE
- [x] Run EXP-2671 cross-controller validation (8 panels, all findings documented)
- [x] Fix P0 enacted rate percent-encoding (grid.py auto-detects & converts)
- [x] Codify patient exclusion list (2 permanent, 4 short-span, 1 investigate)

### Phase 2: Qualification Gate ✅ PASSED (EXP-2672)

EXP-2672 ran the autoprepare qualification gate on 22 qualified patients across
3 controller types. All 4 gates passed:

| Gate | Criterion | Result |
|------|-----------|--------|
| G1 | Demand-ISF dose-independence (|r| < 0.3) in ≥2 controllers | ✅ Loop=−0.19, Trio=−0.20, OpenAPS=−0.08 |
| G2 | ≥15 correction events per patient | ✅ Min=37 |
| G3 | No new data quality anomalies | ✅ None |
| G4 | ISF range plausible (10-200 mg/dL/U) | ✅ [10.7, 67.5] |

**Key insight**: G1 validates EXP-2663's finding that demand-phase ISF (0-2h
drop/dose) is dose-INDEPENDENT — this holds across all 3 controller types.
The original r=−0.56 from EXP-2640 used apparent ISF (total drop), which is
inflated by AID compensation per EXP-2651.

**Qualified pool**: 22 patients (Loop=8, Trio=11, OpenAPS=3)  
**Manifest**: `externals/experiments/autoprepare-qualified.json`  
**Figures**: `visualizations/autoprepare-gate/fig[1-4]_*.png`

### Phase 3: Autoresearch — Results (EXP-2673 through EXP-2675) 🔬

#### EXP-2673: Circadian ISF Replication + Sensitivity Ratio Validation

**Part A — Circadian ISF** (22 patients, 562 events, 2h isolation):
- Pooled Mann-Whitney p=0.18: **NO circadian signal** (confirms EXP-2665)
- Per-controller: Loop p=0.59, Trio p=0.07 (marginal), OpenAPS p=0.46
- 6h isolation too strict for SMB controllers — 2h validated by EXP-2663

**Part B — Sensitivity Ratio** (6 patients with SR coverage + events):
- Cross-patient SR vs demand ISF: r=0.59 (promising but n=6, p=0.22)
- Effective ISF (scheduled/SR) vs demand ISF: r=0.70 (p=0.12)
- Effective/demand ISF ratio: 1.4-5.2× (confirms EXP-2651 inflation)

#### EXP-2674: DynISF Formula × Demand ISF

**Headline finding**: DynISF formula type predicts ISF inflation magnitude:

| Formula | Patients | Median Inflation | Range |
|---------|----------|-----------------|-------|
| Sigmoid | 6 | 6.6× | 2.6-38.3× |
| Log | 5 | 2.5× | 1.5-4.7× |

- Sigmoid formula creates more aggressive AID compensation → higher inflation
- Event-level SR is NOT predictive of per-correction ISF (pooled r=0.055)
- 994 correction events across 12 Trio patients

#### EXP-2675: Cross-Controller ISF Portability

**Key result**: Patient physiology explains **81.9%** of demand ISF variance:

| Metric | Loop | Trio | OpenAPS |
|--------|------|------|---------|
| Patients | 8 | 11 | 3 |
| Events | 311 | 318 | 239 |
| Median ISF | 7.3 | 4.7 | 32.5 |
| Median CV | 2.32 | 5.41 | 1.67 |

- Controller type: 18.1% (eta²=0.181) — moderate, not dominant
- ISF distributions differ (Kruskal-Wallis p<0.001) — OpenAPS higher ISF
- Profile ISF predicts demand ISF: r=0.456 (moderate)
- Trio has highest variability (CV=5.41) due to aggressive SMBs

### Phase 4: Methodology Revision (EXP-2677-2679)

#### EXP-2677: AID Compensation Artifact — The 57% Negative ISF Problem

**Critical finding**: 57% of "correction" events show NEGATIVE demand ISF (glucose rises
after bolus). This affects ALL controllers:

| Controller | N events | % Negative ISF | Median BG (neg) | Median BG (pos) |
|------------|----------|----------------|-----------------|-----------------|
| Loop | 597 | 55% | ~106 | ~160 |
| Trio | 318 | 60% | ~108 | ~155 |
| OpenAPS | 239 | 52% | ~110 | ~158 |

**Root cause**: Boluses at in-range glucose (median BG=106 for negative ISF events) are
misclassified meals, not corrections. The BG rises because the person was eating, not
because insulin is ineffective.

**BG Floor Effect**:
| Floor | % Negative ISF |
|-------|----------------|
| None | 57% |
| ≥120 mg/dL | 39% |
| ≥150 mg/dL | 31% |
| ≥160 mg/dL | 27% |
| ≥180 mg/dL | 23% |

**METHODOLOGY REQUIREMENT**: All future ISF extraction MUST include BG ≥ 150-180 mg/dL floor
to exclude misclassified meal boluses. Earlier experiments (EXP-2673-2675) that used no floor
have inflated variance and potentially incorrect conclusions.

#### EXP-2678: BG Floor Sensitivity Analysis

Replicated 3 key analyses from EXP-2673-2675 at BG floors [0, 120, 150, 180]:

1. **Circadian ISF**: p drops from 0.18 (no floor) to 0.0009 (BG≥180). The signal was
   HIDDEN by meal noise, not absent.

2. **Variance decomposition**: Patient >> controller at ALL floors. Robust finding.

3. **DynISF inflation**: Drops from 6.6× (no floor) to 1.4-1.8× (BG≥180). Sigmoid and log
   formulas converge with cleaner data.

#### EXP-2679: Circadian ISF Deep Dive (BG≥180)

**Overall**: Kruskal-Wallis p=0.000894 — confirmed circadian signal with BG≥180 filter.
Peak ISF at 2PM UTC (31.7 mg/dL/U), trough at midnight (2.0 mg/dL/U).

**By controller**:
| Controller | N (BG≥180) | Kruskal-Wallis p | Interpretation |
|------------|-----------|------------------|----------------|
| Loop | 597 | 7e-06 | **Strong circadian signal** |
| Trio | 57 | 0.40 | Inconclusive (severely underpowered) |
| OpenAPS | 402 | 0.40 | **No signal** (adequately powered) |

**Dawn phenomenon**: NOT significant (p=0.95). Dawn ISF=17.0 vs non-dawn=15.6.

**Interpretation**: The circadian signal is LOOP-SPECIFIC. Since OpenAPS has adequate power
(n=402) and shows no signal, this likely reflects Loop controller behavior patterns (temp
basal strategies that vary by time of day) rather than pure physiology. However, cannot rule
out genuine physiology in the Loop patient population without timezone normalization.

---

## EXP-2676: Cross-Controller PK Model Comparison

**Date**: 2026-04-19  
**Figures**: `visualizations/pk-model-comparison/fig[1-6]_*.png`  
**Results**: `externals/experiments/exp-2676_pk_model_comparison.json`

### Headline Finding

**All 4 AID systems (Loop, oref0, AAPS, Trio) use mathematically identical exponential
PK formulas**, sourced from the same LoopKit reference (GitHub issue #388). The differences
are only in default parameters:

| System | Default DIA | Default Peak | Model Options |
|--------|-------------|--------------|---------------|
| Loop | 360 min (6h) | 75 min (rapid) | Exponential + Walsh |
| oref0 | 180 min (3h) | 75 min (rapid) | Exponential + Bilinear |
| AAPS | Profile-based | 75/55/45 min | Exponential only |
| Trio | 600 min (10h) | 75 min (rapid) | Exponential + Bilinear (= oref0) |

**Shared exponential formula** (all systems):
```
τ = peak × (1 - peak/DIA) / (1 - 2×peak/DIA)
a = 2×τ/DIA
S = 1 / (1 - a + (1 + a)×exp(-DIA/τ))
IOB(t) = 1 - S×(1-a)×((t²/(τ×DIA×(1-a)) - t/τ - 1)×exp(-t/τ) + 1)
```

### Panel Results

#### Panel 2: IOB Decomposition (bolus\_iob + basal\_iob = total IOB)

| Controller | N | MAE (U) | r |
|------------|---|---------|---|
| Loop | 42,900 | 0.0003 | 1.000000 |
| Trio | 439,347 | 0.0002 | 1.000000 |
| OpenAPS | 0 | — | — (no bolus\_iob data) |

**Verdict**: Perfect decomposition where data available. IOB is exactly the sum of components.

#### Panel 3: Empirical IOB Decay

**Critical finding**: All curve fits hit the upper bounds (DIA=720m, peak=150m) for BOTH
total IOB AND bolus\_iob component. This means empirical IOB does NOT follow single-bolus
pharmacokinetic decay in AID systems, because:

1. **Total IOB**: Controller keeps adding insulin (SMBs, temp basals), so IOB never truly decays
2. **Bolus IOB**: Even the "bolus component" reflects ALL boluses (including new SMBs delivered after the index bolus), not just the isolated bolus's decay

This is a fundamental methodological finding: **you cannot extract PK parameters from observed
IOB in closed-loop AID data**. The PK model equivalence must be verified by source code analysis
(which we have done) rather than empirical curve fitting.

#### Panel 4: Insulin Activity vs IOB

| Controller | N | r(IOB, activity) | Median Activity |
|------------|---|-------------------|-----------------|
| Loop | 42,900 | 0.844 | 0.0075 |
| Trio | 439,347 | 0.856 | 0.0104 |
| OpenAPS | — | — | No activity data |

Strong positive correlation, consistent with activity being the derivative of IOB.
Trio has higher median activity (more aggressive dosing → higher insulin action rate).

#### Panel 5: IOB-Based BG Prediction at t+30 min

`pred_iob_30` is a **glucose prediction** (mg/dL), NOT an insulin prediction. It represents
the controller's prediction of where BG will be in 30 minutes considering only IOB effects.

| Controller | N | MAE (mg/dL) | RMSE | r |
|------------|---|-------------|------|---|
| OpenAPS | 3,000 | 13.9 | 20.6 | 0.844 |
| Trio | 3,000 | 22.8 | 33.1 | 0.559 |
| Loop | 3,000 | 29.1 | 40.4 | 0.825 |

OpenAPS has the best IOB-based BG prediction. This likely reflects less aggressive dosing
(fewer perturbations → more predictable trajectory). Loop's strong r but higher MAE suggests
systematic bias in the IOB-only prediction channel.

#### Panel 6: IOB Semantics

| Controller | Median IOB | P90 IOB | Max IOB | % Negative |
|------------|-----------|---------|---------|------------|
| Loop | 0.69 U | 4.85 U | varies | 15.5% |
| Trio | 0.00 U | 3.58 U | varies | 9.2% |
| OpenAPS | 0.08 U | 3.39 U | varies | 13.4% |

**Key differences in IOB semantics**:
- **Loop** carries the highest baseline IOB (median 0.69U) — runs relatively higher temp basals
- **Trio** has median IOB = 0.0U — oscillates between zero-basal and SMB bursts (bang-bang control)
- **OpenAPS** has low median (0.08U) — conservative dosing
- **15.5% of Loop data has negative IOB** — basal suspended below scheduled rate

### Implications for Cross-System Research

1. **PK model is portable**: The formula is the same. Cross-system ISF/dosing comparisons
   are valid because all systems compute IOB/activity identically (given same DIA/peak).

2. **DIA settings matter enormously**: Trio's 10h default vs oref0's 3h default creates
   3.3× different IOB tail lengths. When comparing IOB across systems, normalize by DIA.

3. **Total IOB is NOT pharmacokinetic**: It's a closed-loop aggregate. Don't try to extract
   PK parameters from IOB time series — the controller's continuous dosing masks the true
   insulin kinetics.

4. **pred\_iob\_30 is a BG prediction**: Future analyses should use this as a glucose prediction
   channel, comparable to `loop_predicted_30` (which is also in mg/dL).

5. **IOB semantics differ by controller strategy**: The "meaning" of IOB=2U differs — in Loop
   it's steady state, in Trio it's a transient spike from an SMB burst.

---

---

## Phase 5: The Insulin Irrelevance Discovery (EXP-2680-2683)

### EXP-2680: Definitive Demand ISF Characterization

Applied all methodology corrections (BG≥180, 2h isolation) to 22 patients:
- 7986 events total, 1226 at BG≥180 (73-88% positive ISF vs 36-43% without floor)
- **Trio severely underpowered**: only 66 events at BG≥180 (tight control)
- ISF differs across controllers (Kruskal-Wallis p<0.0001)
- **REVISION**: Demand ISF IS dose-dependent (r=-0.418) — contradicts EXP-2663

### EXP-2681: BG Drop Direct Modeling

Investigated the dose-dependence — **it's a ratio artifact**:
- BG drop is ~74 mg/dL **regardless of dose** (Loop=78@4U, OpenAPS=71@1U, Trio=64@1.4U)
- Dose R²=0.015, BG₀ R²=0.141, IOB R²=0.001, Full model R²=0.146
- ISF = drop/dose creates artificial 1/dose dependence from a near-constant numerator

### EXP-2682: Controller vs Bolus — Who Drives Corrections?

Even TOTAL insulin (bolus + controller) doesn't predict BG drop:

| Controller | Bolus | Total 2h Insulin | Bolus % | BG Drop |
|------------|-------|------------------|---------|---------|
| Loop | 4.0U | 5.1U | 78% | 78 mg/dL |
| Trio | 1.4U | 4.8U | 29% | 64 mg/dL |
| OpenAPS | 1.0U | 1.7U | 59% | 71 mg/dL |

Trio delivers **~3× the insulin** of OpenAPS for a **smaller BG drop**.
Total insulin R²=0.0007 — even worse than bolus alone.

### EXP-2683: What Explains the 86% Unexplained Variance?

**Answer: Nothing measurable.** Full model R²=0.165:

| Predictor | R² |
|-----------|----|
| Full (FE + all) | 0.165 |
| BG₀ alone | 0.138 |
| Regression to mean | 0.130 |
| Patient FE | 0.028 |
| Hour | 0.008 |
| Dose | 0.004 |
| IOB | 0.001 |
| Glucose ROC | 0.000 |
| Has carbs | 0.000 |

- **Glucose momentum**: r=-0.036 (irrelevant)
- **Concurrent carbs**: p=0.87 (no difference, despite 51% having carbs)
- **Regression to mean**: r=0.333, slope=0.38 — the dominant signal
- **ICC**: 0.173 — only 17% between-patient

**83.5% of BG drop variance is genuinely irreducible stochastic noise** from
physiology (EGP variation, counter-regulatory hormones, activity, stress).

---

## Grand Synthesis: What We Can and Cannot Conclude

### ⚠️ Methodological Caution: Observational vs. Causal Claims

AID systems are closed-loop: the controller continuously adjusts insulin delivery
(basal modulation, temp basals, SMBs) based on the same glucose readings we analyze.
This creates systematic confounding that breaks observational correlations:

- **Low R² does NOT mean insulin doesn't work.** Insulin is the mechanism by which ALL
  controllers operate. Low bolus-outcome correlations reflect the controller compensating
  through other channels, not insulin ineffectiveness.
- **Cross-patient setting-outcome correlations near zero do NOT mean settings don't matter.**
  Settings configure controller behavior. Different patients need different settings. The
  absence of a cross-patient correlation means settings are appropriately individualized,
  not that they're irrelevant.
- **Observational data cannot isolate individual treatment effects** in a closed-loop system.
  The controller's response to the same glucose signal confounds any attempt to attribute
  outcomes to a single factor (bolus, settings, or physiology).

### 1. Observed ISF (drop/dose) Is a Poor Estimator in AID Data

ISF = BG_drop / dose. Because the controller manages insulin through multiple channels
simultaneously (basal, SMB, temp rates), the observed BG drop reflects the TOTAL system
response, not just the user's bolus. Estimating ISF from correction events in closed-loop
data is confounded by controller co-intervention. This does not mean ISF as a physiological
concept is invalid — it means observational estimation is unreliable.

### 2. AID Controllers Manage Corrections Through Multiple Channels

The controller responds to high BG through temp basals, SMBs, and basal modulation.
Trio delivers ~4.8U total insulin vs OpenAPS ~1.7U over 2h corrections, reflecting
different controller strategies, not different physiology. Each channel contributes
to the correction — user bolus, controller SMBs, and basal modulation all deliver
insulin that lowers glucose. Isolating any one channel's effect requires causal
methods, not observational correlation.

### 3. Regression to the Mean Is a Major Confounder

The BG≥180 filter selects observations above the patient's equilibrium, which
tend to revert toward the mean. EXP-2687 showed no-bolus events at BG≥180 drop
61.7 mg/dL over 2h — but this does NOT mean boluses don't work. In no-bolus events,
the controller is still actively managing insulin (temp basals, SMBs). The "null" is
not zero-insulin; it's controller-only insulin. EXP-2689 showed users bolus in harder
situations (rising BG, concurrent meals), creating confounding by indication.

### 4. Individual Event Variance Is High; Aggregate Patterns Are Clear

83.5% of individual correction variance is unexplained by measurable factors.
This reflects the complexity of glucose physiology (meals, activity, stress, hormones)
plus controller compensation. However, **aggregate outcomes differ systematically**:
Trio achieves 89.9% TIR vs Loop 73.3% vs OpenAPS 68.4%. The controllers' different
strategies (bang-bang vs proportional, SMB vs no-SMB) produce measurably different
population-level outcomes even though individual events are noisy.

### 5. Settings, Algorithm, and Physiology Are Coupled

Settings configure how the controller responds. The controller adapts to physiology.
Physiology varies with meals, activity, and time. This three-way coupling means:
- Changing ISF changes how aggressively the controller corrects
- Changing CR changes how the controller covers meals
- The controller compensates for modest setting errors, but settings still matter
- Optimal settings depend on the individual AND the controller algorithm

The correct conclusion is not "settings don't matter" but rather "the effect of
settings is mediated through the controller and cannot be estimated by simple
cross-patient correlation."

**Quantitative evidence (EXP-2690/2691)**:
- Multi-channel regression (R²=0.296) shows ALL insulin channels contribute
  significant partial effects: bolus uniquely explains 7.3%, excess basal 6.4%,
  SMBs 0.9% of BG drop variance — when controlling for each other.
- Mediation path: ISF → SMB rate (r=−0.115, p=1.2e-11) → TIR (r=+0.169, p=2.2e-23).
  Lower ISF → more aggressive controller → higher TIR.
- Patient-level (settings + controller → TIR): R²=0.335 (n=22).
- Within-patient, settings are very stable (ISF range ≈ 0.1 mg/dL/U), limiting
  natural experiment power but confirming settings are appropriately individualized.

### 6. AID Controllers Mitigate Hypo Severity

IOB near zero at hypo onset is not evidence of "insulin depletion" causing the hypo —
it is evidence of the **controller's response**. The hypo was caused by insulin
delivered ~2 hours earlier. The controller detected falling BG, suspended delivery, and
depleted IOB by the time glucose crossed 70 mg/dL. This is the same pattern throughout:
**observed states at the time of an event reflect the controller's response, not the
cause.** More aggressive suspension strategies (Trio's bang-bang) correlate with
shorter, shallower hypos.

---

## Source Files

- **EXP-2671**: `tools/cgmencode/exp_cross_controller_validation_2671.py`
- **EXP-2672**: `tools/cgmencode/exp_autoprepare_gate_2672.py`
- **EXP-2673**: `tools/cgmencode/exp_autoresearch_wave1_2673.py`
- **EXP-2674**: `tools/cgmencode/exp_dynisf_sr_deep_dive_2674.py`
- **EXP-2675**: `tools/cgmencode/exp_cross_controller_isf_2675.py`
- **EXP-2676**: `tools/cgmencode/exp_pk_model_comparison_2676.py`
- **EXP-2677**: `tools/cgmencode/exp_aid_compensation_artifact_2677.py`
- **EXP-2678**: `tools/cgmencode/exp_bg_floor_sensitivity_2678.py`
- **EXP-2679**: `tools/cgmencode/exp_circadian_isf_deep_dive_2679.py`
- **EXP-2680**: `tools/cgmencode/exp_definitive_isf_2680.py`
- **EXP-2681**: `tools/cgmencode/exp_bg_drop_model_2681.py`
- **EXP-2682**: `tools/cgmencode/exp_controller_vs_bolus_2682.py`
- **EXP-2683**: `tools/cgmencode/exp_unexplained_variance_2683.py`
- **EXP-2684**: `tools/cgmencode/exp_aggregate_outcomes_2684.py`
- **EXP-2685**: `tools/cgmencode/exp_controller_strategy_2685.py`
- **EXP-2686**: `tools/cgmencode/exp_safety_analysis_2686.py`
- **EXP-2687**: `tools/cgmencode/exp_null_model_2687.py`
- **EXP-2688**: `tools/cgmencode/exp_temporal_trends_2688.py`
- **EXP-2689**: `tools/cgmencode/exp_confounding_2689.py`
- **EXP-2690**: `tools/cgmencode/exp_multi_channel_2690.py`
- **EXP-2691**: `tools/cgmencode/exp_settings_mediation_2691.py`
- **Pipeline**: `tools/ns2parquet/grid.py` (grid construction + percent-fix)
- **Data**: `externals/ns-parquet/training/grid.parquet` (1.3M rows, 49 columns)
- **Manifest**: `externals/experiments/autoprepare-qualified.json`

## Next Research Directions

Given the insulin irrelevance finding, the productive research directions shift:

1. ✅ **Aggregate outcome modeling** (EXP-2684): Settings don't predict TIR
2. ✅ **Controller strategy comparison** (EXP-2685): Bang-bang vs proportional
3. ✅ **Regression to mean quantification** (EXP-2687): Null model > bolus drop
4. ✅ **Safety analysis** (EXP-2686): IOB at hypo = controller response, not cause
5. ✅ **Confounding by indication** (EXP-2689): Users bolus in harder situations
6. ✅ **Temporal trends** (EXP-2688): No learning curve, outcomes stable

Remaining:
1. **Controller decision tree**: Map the actual if/then decision logic from source
2. **DynISF vs standard within Trio**: Does DynISF formula explain Trio's TIR advantage?
3. **Patient selection bias**: Are Trio users more engaged / better at carb counting?
4. **Open-loop periods**: Do any patients have open-loop data for true treatment effect?

---

## Phase 6: Controller Strategy & Safety (EXP-2684–2686)

### EXP-2684: Aggregate Outcome Modeling

Individual correction events are unpredictable (83.5% irreducible variance), but
**aggregate outcomes differ dramatically by controller**:

| Controller | TIR (%) | Hypo (%) | Mean BG | TDD (U) |
|------------|---------|----------|---------|---------|
| Trio | 89.9 | 4.8 | 127 | 41.4 |
| Loop | 73.3 | 4.0 | 155 | 37.6 |
| OpenAPS | 68.4 | 6.3 | 161 | 21.1 |

**Settings (ISF, CR, TDD) show zero correlation with TIR** (all r<0.2, p>0.2).
Controller algorithm/strategy is the dominant factor.

### EXP-2685: Controller Strategy Comparison

| Metric | Loop | Trio | OpenAPS |
|--------|------|------|---------|
| % time suspended | 64.7% | 82.6% | 33.9% |
| SMB delivery rate | 15.0% | 19.8% | 0% |
| Mean SMB size | 0.26U | 0.32U | — |
| % normal basal | 6% | 5% | 33% |

**Loop/Trio are "bang-bang" controllers**: mostly suspended, with aggressive SMB bursts.
**OpenAPS is proportional**: smooth basal modulation, no SMBs (likely oref0 without SMB enabled).
Trio's more extreme bang-bang strategy achieves the best TIR.

### EXP-2686: Safety Analysis

**Clinical target (TIR≥70% AND hypo≤4%)**:
- Trio: 5/10 (50%) — best
- Loop: 3/9 (33%)
- OpenAPS: 1/3 (33%)

**IOB at hypo onset vs overall (median)**:

| Controller | Overall IOB | IOB at Hypo Onset | Δ |
|-----------|-------------|-------------------|---|
| Loop | 0.69U | −0.03U | −0.72U |
| Trio | 0.00U | 0.00U | 0.00U |
| OpenAPS | 0.08U | 0.00U | −0.08U |

**⚠️ Causal interpretation**: Near-zero IOB **at** hypo onset does not mean "insulin
depletion caused the hypo." Hypos are caused by insulin delivered earlier. The controller
detects falling BG and suspends delivery, depleting IOB by the time glucose crosses 70
mg/dL. Loop's large IOB drop (0.69→−0.03U) shows aggressive suspension. The controller
**mitigates severity** — without AID suspension, hypos would be deeper and longer.

**OpenAPS hypos are deepest** (nadir 57 vs 62 mg/dL) and longest (25 min vs 15–20 min),
consistent with its less aggressive suspension strategy (proportional, not bang-bang).

**DynISF formula within Trio**: Log formula → 90.5% TIR / 5.1% hypo (more aggressive);
Sigmoid → 86.0% TIR / 3.3% hypo (more conservative). The log formula pushes harder for
TIR at the cost of higher hypo risk.

---

## Phase 7: Null Model & Confounding (EXP-2687–2689)

### EXP-2687: Null Model Benchmark

**The AID controller alone brings BG down from 180+ faster than when users also bolus.**

| Category | Median 2h BG Drop | N events |
|----------|-------------------|----------|
| No-bolus (null) | **61.7 mg/dL** | 40,016 |
| Bolus | 53.0 mg/dL | 3,981 |
| "Treatment effect" | **−8.7 mg/dL** | — |

The null model accounts for **116.5%** of the bolus drop. By controller:
- **Loop**: null=63, bolus=51, Δ=−12
- **Trio**: null=86, bolus=52, Δ=−34
- **OpenAPS**: null=55, bolus=57, Δ=+2

After null subtraction, dose-response correlation r=−0.065 (no signal).

### EXP-2688: Within-Patient Temporal Trends

**No learning curve detected.** TIR is stable from the start:

| Metric | Value |
|--------|-------|
| First→last month TIR change | +0.9 pp (p=0.579) |
| Sig. improving patients | 3/22 |
| Sig. declining patients | 1/22 |
| Median slope | −0.013 pp/week |

Settings (ISF, CR, basal) show minimal drift over time. Controller strategy is
established early and outcomes don't change as settings are tuned.

### EXP-2689: Confounding by Indication

**Explains why bolus events drop less** (EXP-2687's negative "treatment effect"):

| Confound | Bolus | No-bolus | Impact |
|----------|-------|----------|--------|
| Pre-slope (mg/dL/5min) | **+1.9 (rising)** | −0.4 (falling) | Users bolus when BG going up |
| % meal boluses | 53% | 0% | Incoming carbs fight BG drop |
| IOB at event | **2.5U** | 1.8U | Controller already maxed |
| Correction-only drop | 58 mg/dL | 61 mg/dL | Even corrections ≈ null |

**Stratified by pre-event trajectory**:
- BG FALLING: bolus=61, null=74, Δ=−13 (controller handles falling BG alone)
- BG RISING: bolus=47.5, null=46, Δ=+1.5 (no treatment effect even when BG rising)

**Conclusion**: In AID systems, "easy" highs (already falling) resolve autonomously
via the controller. Users bolus in "hard" situations (rising BG, meals, resistant highs).
The treatment effect of a correction bolus cannot be isolated from observational data
because the controller co-intervenes through other channels simultaneously. Multi-factor
analysis (EXP-2690) reveals that boluses uniquely explain 7.3% of BG drop variance when
controlling for other channels — significant and meaningful.

---

## Phase 8: Multi-Factor Decomposition (EXP-2690–2691)

### EXP-2690: Multi-Channel Insulin Decomposition

**Multi-factor analysis recovers R²=0.296** (vs 0.015 for bolus-only univariate):

| Channel | Unique R² | β (standardized) | p-value |
|---------|-----------|-------------------|---------|
| Starting BG | 13.3% | +28.6 | ≈0 *** |
| **Bolus** | **7.3%** | −28.2 | ≈0 *** |
| **Excess basal** | **6.4%** | −20.2 | ≈0 *** |
| SMB total | 0.9% | −8.9 | ≈0 *** |
| Carbs | 0.6% | +6.9 | ≈0 *** |
| Glucose ROC | 0.5% | −5.0 | ≈0 *** |
| IOB at start | 0.04% | +1.5 | ≈0 *** |

All insulin channels have significant, measurable partial effects. The earlier
"insulin irrelevance" finding was an artifact of univariate analysis not controlling
for controller co-intervention through other channels.

**Model hierarchy**: BG₀ only (R²=0.097) → All channels (0.296) → With interactions (0.309)
→ Within-patient (0.318).

**Controller-stratified**: Loop R²=0.378, Trio R²=0.394, OpenAPS R²=0.132.

### EXP-2691: Settings Mediation Analysis

Settings affect outcomes through a mediation pathway:

**Settings → Controller behavior → Glucose outcomes**

| Link | Variables | r | p-value |
|------|-----------|---|---------|
| a-path | ISF → SMB rate | −0.115 | 1.2e-11 |
| b-path | SMB rate → TIR | +0.169 | 2.2e-23 |
| Total | ISF → TIR | −0.114 | 1.8e-11 |

Lower ISF → controller is more aggressive (more SMBs) → higher TIR.

Patient-level model (settings + controller type → TIR): R²=0.335 (n=22).
Trio has largest controller effect (β=+6.25) but underpowered (p=0.141).

Within-patient settings are very stable (ISF range ≈ 0.1 mg/dL/U), confirming
settings are appropriately individualized but limiting natural experiment power.

---

## Phase 9: Advanced Multi-Factor Analysis (EXP-2692–2694)

### EXP-2692: Per-Channel Dose-Response & Non-Linear Effects

**Marginal effects per unit insulin** (controlling for all other channels):

| Channel | mg/dL per U | 95% CI | Interpretation |
|---------|-------------|--------|----------------|
| Bolus | **−7.48** | ±0.11 | More bolus → less BG drop (confounding) |
| SMB | **−4.34** | ±0.18 | Same direction, weaker per unit |
| Excess basal | **−7.88** | ±0.12 | Strongest per-unit association |

**All coefficients are negative** — the opposite of what we'd expect if more insulin
causes more BG drop. This is **confounding by indication**: the controller gives
more insulin precisely in harder situations (resistant highs, meals in progress,
rising BG). Even after controlling for starting BG, carbs, and ROC, residual
confounding from unobserved controller predictions remains.

**Channel substitution**: 0.58U SMB ≈ 1U bolus effect; 1.05U excess basal ≈ 1U bolus.

**Non-linearity**: Quadratic model R²=0.320 vs linear R²=0.296 (F=2165, p≈0).
Statistically significant but only +2.4pp practical improvement. The relationship
is mostly linear — no dramatic threshold or saturation effects.

**Per-controller marginal effects differ substantially**:

| Controller | Bolus (mg/dL/U) | SMB (mg/dL/U) | Excess Basal (mg/dL/U) |
|------------|-----------------|----------------|------------------------|
| Loop | −8.56 | −3.41 | −8.25 |
| Trio | −5.05 | **−11.20** | −3.04 |
| OpenAPS | −6.43 | 0.00 | −4.32 |

Trio's SMBs have the strongest per-unit association (−11.20), suggesting they are
deployed strategically in the most challenging situations. Loop boluses are
strongest (−8.56), consistent with Loop users relying more on manual boluses.

### EXP-2693: TIR Gap Decomposition

The Trio-OpenAPS TIR gap (**11.4pp**: 82.4% vs 71.0%) is **nearly fully decomposed**:

| Factor | Contribution | Explanation |
|--------|-------------|-------------|
| CV glucose | **+11.9pp** | Trio patients have lower glucose variability |
| SMB rate | **+11.6pp** | Trio has SMBs (19.8%), OpenAPS doesn't (0%) |
| TDD | **−9.3pp** | Trio uses 76 U/day vs OpenAPS 44 U/day |
| ISF | −5.1pp | Trio ISF=57 vs OpenAPS 73 (more sensitive settings) |
| Days of data | −3.5pp | OpenAPS has longer histories |
| Suspend rate | +5.8pp | Trio suspends more (strategic) |
| Other | +0.2pp | Residual |

**Key insight**: The TIR gap is a mix of **patient selection** (lower BG variability),
**algorithm features** (SMB availability), and **insulin dose** (higher TDD).
It is NOT purely an algorithm effect — patients who choose Trio may have
different physiological characteristics or engagement levels.

**Patient-level multi-factor model**: R²=0.702 (n=22)
- Controller type alone: R²=0.427
- Settings + behavior alone: R²=0.564
- Full model: R²=0.702

70% of patient-level TIR variance is explained by measurable factors.

### EXP-2694: Time-Resolved Channel Decomposition

The multi-factor model's explanatory power **grows with horizon**:

| Horizon | R² | New insight at this horizon |
|---------|----|-----------------------------|
| 30 min | 0.183 | Starting BG dominates (regression to mean) |
| 60 min | 0.215 | Bolus + SMB effects begin to emerge |
| 90 min | 0.254 | Controller adaptation visible |
| 120 min | 0.296 | Full channel effects accumulated |

**Controller response to user bolus** reveals channel substitution:

| Metric (2h cumulative) | After user bolus | No user bolus |
|-------------------------|------------------|---------------|
| SMBs delivered | 2.29 U | 0.00 U |
| Excess basal | −3.51 U | −1.41 U |

When a user boluses, the controller responds by **suspending basal more aggressively**
(−3.51 vs −1.41 U excess) while also delivering SMBs (2.29 vs 0.00 U). The controller
is dynamically substituting between channels, which explains why single-channel
analysis produces misleading conclusions.

**BG₀-matched trajectory comparison** (190-210 mg/dL band):
Events with and without user boluses follow similar BG trajectories, confirming
that the controller compensates through other channels when boluses are absent.

---

## Grand Synthesis

### What We Know (21 experiments, 181K events, 22 patients)

1. **Multi-factor analysis is mandatory** for closed-loop AID systems. Single-factor
   correlations are confounded by controller co-intervention. The controller
   dynamically substitutes between channels (bolus, SMB, temp basal, suspend),
   making each channel's observational effect appear weaker than its true causal
   effect.

2. **All insulin channels have measurable effects** when properly isolated:
   - Unique R²: bolus 7.3%, excess basal 6.4%, SMB 0.9%
   - Total multi-factor R²: 0.296 (vs 0.015 univariate)
   - Marginal effects are negative due to confounding by indication

3. **The TIR gap between controllers is 70% explained** by measurable factors:
   patient physiology (BG variability), algorithm features (SMB availability),
   and insulin delivery patterns (TDD, suspend rate).

4. **Controller strategy matters more than individual settings**: controllers with
   SMB capability (Trio, Loop) achieve higher TIR. Within a controller, settings
   are appropriately tuned and show little variation.

5. **The "insulin irrelevance" finding was an artifact** of univariate analysis.
   In multi-factor models, insulin channels explain meaningful variance. However,
   ~70% of event-level BG drop variance remains unexplained — reflecting
   unmeasured physiology, meal absorption kinetics, exercise, and stress.

### Methodological Lessons

| Lesson | Evidence |
|--------|----------|
| Never use single-factor analysis in closed-loop | EXP-2680 R²=0.015 vs EXP-2690 R²=0.296 |
| Negative coefficients ≠ harmful treatment | EXP-2692: confounding by indication |
| Controller substitutes between channels | EXP-2694: bolus → suspend + SMB |
| Patient selection confounds controller comparison | EXP-2693: CV_bg explains 11.9pp |
| BG ≥ 180 floor required for correction analysis | EXP-2677: 57% negative ISF without |
| IOB at hypo onset reflects controller response | EXP-2686: suspension is treatment, not cause |

### Next Steps

1. **Causal inference methods** (instrumental variables, regression discontinuity)
   to estimate true treatment effects from observational AID data
2. **Meal vs correction event separation** — 53% of boluses are meal-related
3. **Within-patient longitudinal analysis** — exploit settings changes as natural experiments
4. **Cross-validation** with the 6 additional datasets still loading

---

## Phase 10: Causal Inference Toolkit (EXP-2695–2697)

### EXP-2695: Propensity Score Matching for Causal Bolus Effect

**47,045 matched pairs** (caliper=0.05, exact match on BG band, PS on 7 covariates).

| Covariate | SMD Before | SMD After | Balanced? |
|-----------|-----------|-----------|-----------|
| BG₀ | 0.047 | 0.003 | ✅ |
| ROC | **0.510** | **0.141** | ❌ residual |
| IOB | 0.094 | 0.041 | ✅ |
| Carbs prior | 0.002 | 0.007 | ✅ |
| Hour | 0.077 | 0.038 | ✅ |

**Average Treatment Effect on Treated (ATT):**

| Horizon | ATT (mg/dL) | p-value | Interpretation |
|---------|-------------|---------|----------------|
| 30 min | **−11.8** | <0.001 | Bolus events drop 11.8 LESS (harder situations) |
| 60 min | −8.0 | <0.001 | Gap narrowing as insulin acts |
| 90 min | −4.0 | <0.001 | Controller compensation accumulating |
| 120 min | **−1.2** | 0.009 | Nearly converged — controller offsets ~90% |

ATT is **robust across calipers** (−1.2 at all tested widths 0.01–0.20).

**Channel compensation (PS-matched events):**

| Channel | Bolus group | No-bolus group | Δ |
|---------|-------------|----------------|---|
| SMBs (2h) | 2.35 U | 0.89 U | +1.46 U |
| Excess basal | −3.60 U | −2.31 U | −1.29 U |
| Net controller | | | **+0.17 U** |

When a user boluses, the controller adds +1.46U of SMBs but suspends −1.29U of
basal, for a **net additional +0.17U** — near-perfect offset. The controller
operates as a closed-loop compensator: bolus in → basal out.

**Key insight**: The −11.8 → −1.2 mg/dL ATT trajectory over 2h shows the controller
**compensating for the disadvantage** of bolus events (harder situations). By 120 min,
the bolus + controller have nearly equalized outcomes with the controller-only path.
This doesn't mean boluses don't work — it means the controller adapts its strategy
based on what the user does.

### EXP-2696: Impulse Response Functions (Local Projection)

Using Jordà (2005) Local Projections with BG history controls:

**Bolus impulse response**: Peak −1.63 mg/dL at 105 min per 1U bolus.

**Granger causality**: **15/15 patients significant** (p<0.05).
Insulin delivery does temporally precede BG changes — the weakest form of
causal evidence, but it holds universally.

**Falsification test FAILS**: Pre-event coefficient = −5.948 (should be ≈0).
This means BG was already changing systematically before the bolus, confirming
that users bolus in response to BG trajectory. The temporal ordering (Granger)
is real, but the causal identification is contaminated by anticipatory behavior.

**Cross-correlation asymmetry**: The BG→Insulin (reactive) direction is stronger
than Insulin→BG (causal), confirming the dominant relationship is the controller
and user reacting to BG, not insulin driving BG.

### EXP-2697: Within-Patient Variance Decomposition

**Hierarchical variance decomposition (ANOVA)**:

| Level | % of Variance | ICC | Implication |
|-------|--------------|-----|-------------|
| Between-patient | **1.9%** | 0.019 | Patients differ very little in mean BG drop |
| Between-day | **14.2%** | — | Day-to-day variation (meals, activity, circadian) |
| Within-day residual | **83.9%** | — | Stochastic glucose variation dominates |

**Patient-specific bolus effects (forest plot)**:
- All 21 patients have **negative** bolus coefficients (−2.1 to −29.7 mg/dL/U)
- This is confounding by indication at the individual level
- Even within a single patient, at the same starting BG, more bolus is given
  when the situation is harder (meals, resistant highs)

**Between-patient model**: R²=0.276 (settings + controller predict mean BG drop).

**Within-patient day-level model**: R²=0.164 (demeaned BG₀, bolus, SMB, carbs predict
day-to-day variation in BG drop after removing patient fixed effects).

**Settings change natural experiments**: ISF barely changes within patients
(range ≈ 0.1 mg/dL/U). ΔISF → ΔBG_drop: r=−0.144 (p=0.533) — no power to
detect settings effects from natural variation.

**Hierarchical R² summary**:

| Level | R² | Interpretation |
|-------|-----|---------------|
| Event-level (all channels) | 0.296 | ~30% of individual events explained |
| Day-level (within-patient) | 0.164 | Day patterns explain 16% of day variation |
| Patient-level | 0.276 | 28% of between-patient differences explained |
| Patient TIR | **0.702** | 70% of patient-level outcomes explained |

**Key insight**: More aggregation → more explainable. Individual glucose events are
83.9% stochastic, but patient-level outcomes are 70% predictable. This is the
fundamental structure of AID data: noisy at the micro level, patterned at the macro level.

---

## Revised Grand Synthesis (27 experiments)

### The Causal Identification Problem in Closed-Loop AID

Three independent causal inference methods converge on the same conclusion:

| Method | Finding | Limitation |
|--------|---------|------------|
| PS Matching (EXP-2695) | ATT = −1.2 mg/dL at 120m | ROC still imbalanced; controller compensates |
| Local Projection (EXP-2696) | Peak −1.6 mg/dL/U; Granger 15/15 | Pre-trends fail (−5.9) |
| Variance Decomp (EXP-2697) | 21/21 patients negative β | All reflect confounding by indication |

**Observational data from closed-loop AID systems cannot identify causal treatment
effects through standard econometric methods.** The fundamental barriers are:

1. **Simultaneous co-intervention**: The controller adjusts basal, SMBs, and suspend
   simultaneously with the user's bolus. No method can separate these when they
   occur at the same time in response to the same signal.

2. **Unobserved controller predictions**: The controller uses internal predictions
   (eventual_bg, predicted curves) that are not fully captured in our 5-min grid.
   These are confounders we cannot control for.

3. **Anticipatory user behavior**: Users bolus in response to expected meals and
   BG trends, not just current BG. The pre-trends failure (EXP-2696) confirms this.

4. **Channel substitution**: The controller's near-perfect offset (+0.17U net when
   user boluses) means that insulin delivery is a _system property_, not an
   independent treatment.

### What We CAN Conclude (with confidence)

1. **Insulin Granger-causes BG changes** (15/15 patients, EXP-2696). The temporal
   ordering is real even if the magnitude is confounded.

2. **All insulin channels carry information** about BG outcomes (EXP-2690: R²=0.296
   multi-factor vs 0.015 univariate). Multi-factor is mandatory.

3. **The TIR gap is 70% decomposable** (EXP-2693). Patient physiology + algorithm
   features + settings explain most of the outcome differences.

4. **84% of event-level variance is stochastic** (EXP-2697). Individual BG events
   are inherently unpredictable; aggregate patient outcomes are not.

5. **Controller channel substitution is the dominant mechanism** (EXP-2694, 2695).
   The controller is a closed-loop compensator that offsets user boluses with
   basal suspension (+0.17U net from controller when user boluses).

### What Would Be Needed for True Causal Estimates

| Approach | Feasibility | Notes |
|----------|-------------|-------|
| Randomized trial | Unethical | Cannot randomize insulin in T1D |
| Instrumental variables | Possible | Controller software updates as instruments |
| Regression discontinuity | Possible | At controller threshold BG values |
| Structural PK/PD models | Possible | Mechanistic simulation with known parameters |
| Controller open-loop periods | Natural experiment | Compare open vs closed loop |

### Methodological Lessons (Complete)

| # | Lesson | Evidence |
|---|--------|----------|
| 1 | Never use single-factor in closed-loop | EXP-2680 R²=0.015 vs EXP-2690 R²=0.296 |
| 2 | Negative coefficients = confounding, not harm | EXP-2692, 2695, 2697: all negative |
| 3 | Controller substitutes between channels | EXP-2694: bolus → suspend + SMB |
| 4 | PS matching insufficient for AID | EXP-2695: ATT converges to ~0, ROC imbalanced |
| 5 | Granger holds but pre-trends fail | EXP-2696: temporal ordering ≠ causal magnitude |
| 6 | 84% of event variance is stochastic | EXP-2697: ICC(patient) = 0.019 |
| 7 | Patient selection confounds controllers | EXP-2693: CV_bg explains 11.9pp of TIR gap |
| 8 | Aggregate more explainable than individual | EXP-2697: event R²=0.30, TIR R²=0.70 |
| 9 | BG ≥ 180 floor required for corrections | EXP-2677: 57% negative ISF without |
| 10 | IOB at hypo onset = controller response | EXP-2686: suspension is treatment, not cause |
