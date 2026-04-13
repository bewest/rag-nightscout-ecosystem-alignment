# AID Alignment Workspace - Progress Tracker

This document tracks completed documentation cycles and candidates for future work.

> **Archive**: Older entries moved to:
> - [progress-archive-2026-03-18-to-31.md](docs/archive/progress-archive-2026-03-18-to-31.md) (Phase 1-3 cross-validation, simulation, gap coverage)
> - [progress-archive-2026-02-01.md](docs/archive/progress-archive-2026-02-01.md) (14 entries)
> - [progress-archive-2026-01-30-batch1.md](docs/archive/progress-archive-2026-01-30-batch1.md)
> - [progress-archive-2026-01-30-batch2.md](docs/archive/progress-archive-2026-01-30-batch2.md)
> - [progress-archive-2026-01-30-batch3.md](docs/archive/progress-archive-2026-01-30-batch3.md)
> - [progress-archive-2026-01-30-batch4.md](docs/archive/progress-archive-2026-01-30-batch4.md)

---

## 🎉🎉🎉 MILESTONE: All 4 Domains 100% REQ + 100% GAP (2026-02-01) 🎉🎉🎉

| Domain | REQs | GAPs |
|--------|------|------|
| Treatments | 35/35 ✅ | 9/9 ✅ |
| CGM Sources | 18/18 ✅ | 52/52 ✅ |
| Sync-Identity | 32/32 ✅ | 25/25 ✅ |
| Algorithm | 56/56 ✅ | 66/66 ✅ |
| **Total** | **141/141** | **152/152** |

**Session Stats (Cycles 102-120)**: 363 assertions, 50 REQs covered, 138 GAPs covered, 17 commits

---

## Digital Twin & Settings Autoresearch (2026-07-14/15)

12 experiments (EXP-2561–2572) systematically tested digital twin and settings optimization hypotheses.
1 production module updated. Branch: `workspace/digital-twin-fidelity`.

### Key Results

| EXP | Hypothesis | Verdict | Key Finding |
|-----|-----------|---------|-------------|
| 2561 | Metabolic phase hypo predictor | NEGATIVE | -0.008 AUC; ceiling is information-theoretic |
| 2562 | Forward sim counterfactuals | POSITIVE | ISF+20%→+2.1pp, CR+20%→+3.3pp TIR |
| 2563 | Per-patient ISF/CR optimization | SUPPORTED | 95% ISF≠1.0, 100% CR≠1.0 |
| 2564 | Forward sim fidelity | PARTIAL | Correction r=0.74 ✅, meal r=0.37 ❌ |
| 2565 | Per-patient DIA/ISF calibration | MARGINAL | Population params sufficient for NS |
| 2566 | Circadian ISF/CR variation | WEAK | Not significant at population level |
| 2567 | Extended CR grid [0.8-3.0] | SUPPORTED | Mean optimal CR×2.10, 8/11 clear peaks |
| 2568 | Joint ISF×CR optimization | SUPPORTED | TIR 0.309→0.720 (+41pp), synergy +8.9pp |
| 2569 | Sim TIR vs actual TIR | NOT SUPPORTED | MAE=0.409; sim can't predict absolute TIR |
| 2570 | Closed-loop digital twin | NOT SUPPORTED | MAE 0.409→0.380; loop can't compensate |
| 2571 | Phenotype→optimization direction | NOT SUPPORTED | ISF↓/CR↑ universal across phenotypes |
| 2572 | ISF artifact check | MIXED | Sim overshoots 22%; ISF×0.5 partially artifact |

### Productionization

- **`advise_forward_sim_optimization()`** added to `settings_advisor.py` (EXP-2568 → production)
- Joint 7×7 ISF×CR grid search via forward simulator
- Directional recommendations only (NOT magnitude predictions)
- All 348 production tests pass

### Lines of Research Closed

- Metabolic phase hypo features (ceiling is fundamental)
- Per-patient DIA/ISF calibration (population params sufficient)
- Circadian CR/ISF profiling (individual, not population effect)
- Forward sim absolute TIR prediction (missing loop model)
- Phenotype-based optimization direction (direction is universal)

### Lines of Research Open

- Extended CR grid for patients a,g (still saturating at 3.0)
- ISF bias correction (sim overshoots 22% — needs dampening)
- Meal-size-dependent CR optimization
- Natural experiment validation (settings changes → outcome)

## E-Series: Strategic Clinical Classification Experiments (2026-07-12)

Full-scale validation (11 patients, 5 seeds) of 8 clinical classification tasks.
Discovered 2 deployable classifiers (AUC ≥ 0.80) and critical methodological insights.

### Infrastructure Fix: Per-Patient Temporal Split
Fixed critical data leakage in `temporal_split()` — pooled multi-patient data caused
val set = last patient only. Now splits chronologically within each patient via `pids=` param.
Commit: `3aa1837`.

### Full-Scale Results (11 patients, 5 seeds)

| EXP | Task | Key Metric | Deployable? |
|-----|------|-----------|-------------|
| 412 | Overnight HIGH risk | AUC=0.805 ±0.009 | ✅ YES |
| 412 | Overnight HYPO risk | AUC=0.676 ±0.007 | ⚠️ Not yet |
| 413 | Next-day TIR (CNN) | MAE=12.0% | Useful |
| 413 | Bad-day classification | AUC=0.784 | Near |
| 415 | High recurrence 24h | AUC=0.882 | ✅ YES |
| 415 | High recurrence 3d | AUC=0.919 | ✅ YES |
| 415 | Hypo recurrence | AUC=0.63-0.67 | ⚠️ Not yet |
| 416 | Weekly hotspot analytics | Two phenotypes found | Actionable |
| 417 | PK channel benefit | Task-specific (not uniform) | Insight |
| 418 | EMA smoothing | Helps high, hurts hypo | Insight |

### Key Scientific Findings

1. **Overnight HIGH is deployable** (AUC=0.805) — evening alert feasible today
2. **High recurrence at 24h/3d is excellent** (AUC=0.88-0.92) — pattern-based alerts work
3. **Hypo prediction is the bottleneck** (AUC 0.63-0.73 across all tasks)
4. **PK channels are task-specific**: PK6 helps hypo at 4-6h, 16ch helps high at 2-4h
5. **Two patient phenotypes** (EXP-416): "morning-high" (dawn phenomenon) vs "night-hypo"
6. **Quick mode (4pt) is unreliable** for feature selection — EXP-418 EMA direction reversed at full scale
7. **Cross-patient generalization fails** for multi-day quality (EXP-414 LOSO F1=0.17)

### Gaps Identified
- GAP-ALG-080: Hypo classification AUC stuck below 0.75 across all tasks
- GAP-ALG-081: Cross-patient transfer learning not viable without adaptation
- GAP-ALG-082: Quick mode (4 patients) gives directionally wrong feature importance

### Source Files
- `tools/cgmencode/exp_treatment_planning.py` (EXP-411 through EXP-418)
- `externals/experiments/exp41[2-8]_*.json` (all results)

---

## Completed Work

### Phase 3 Completion: 3-Way Cross-Validation & All Prediction Curves Aligned (2026-03-31)

Achieved full cross-implementation parity across JS, Swift, and AAPS-JS oref0
implementations on 300 test vectors (100 oref0-native + 200 Loop). All 4
testable prediction curves (IOB, ZT, COB, UAM) now have <0.02 mg/dL avg MAE.

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| IOB/tau activity derivation | `adapters/oref0-js/index.js`, `main.swift` | `activity = IOB / (DIA*60/1.85)` when activity=0; fixes Loop vectors |
| 3-way parity (JS/Swift/AAPS) | `adapters/aaps-js/index.js` | Same IOB/tau fallback; all 3 agree on 294/295 eventualBG |
| ZT activity fallback | `main.swift` | When iobWithZeroTemp absent, fall back to regular activity |
| UAM formula port | `Predictions.swift` | 3 fixes: uci vs ci separation, dual decay model, predDev term |
| Assessment A14–A16 | `docs/architecture/cross-validation-assessment.md` | Full metrics history |
| Loop vectors | `conformance/loop/vectors/` | 200 vectors from 90-day NS fixture |

**Final 3-Way Results (300 vectors)**:

| Vector Suite | EventualBG | Rate ±0.5 |
|-------------|------------|-----------|
| oref0-native (100) | **100/100 (100%)** | **72/72 (100%)** |
| Loop (200) | **194/195 (99.5%)** | **129/131 (98.5%)** |
| **Combined (300)** | **294/295 (99.7%)** | **201/203 (99.0%)** |

**All 4 Prediction Curves Aligned (JS ↔ Swift)**:

| Curve | Avg MAE | Before | Fix |
|-------|---------|--------|-----|
| IOB | 0.005 | 0.888 | A12: IOB array architecture |
| ZT | 0.013 | 13.4 (1 outlier) | ZT activity fallback |
| COB | 0.000 | 38.5 | A4: deviation-based COB |
| UAM | 0.002 | 71.7 | A16: UCI/ci separation, dual decay, predDev |

**Key Technical Discoveries (A14–A16)**:
- **IOB/tau derivation**: When NS devicestatus has `activity=0` but `IOB>0` (common
  in Loop data), derive: `activity = IOB / tau` where `tau = DIA * 60 / 1.85`
- **UCI vs CI**: JS maintains two variables — `uci` (uncapped) for UAM decay,
  `ci` (capped at maxCI) for predDev. Must preserve this separation.
- **UAM dual decay**: `predUCI = min(slope_decay, linear_decay)`, NOT `exp(-t/90)`
- **ZT absent vs zero**: When `iobWithZeroTemp` is nil (not just activity=0),
  fall back to regular activity rather than computing separate IOB/tau value

**Commits**:
- `130ff11`, `c8d80ce` (A14): IOB/tau derivation + assessment
- `7af6428`, `a05c6c0` (A15): AAPS-JS adapter + 3-way assessment
- `9054aa6`: ZT activity fallback fix
- `447b97d` (A16): UAM assessment
- `7a7fee5` (apex): UAM formula port to Swift


### Digital Twin Forward Sim Phase 4: Basal Adequacy, Meal Response & CSF Calibration (2026-07-15)

Extended the forward simulator calibration with 8 experiments (EXP-2589–2596)
and 3 productionizations, bringing total advisories to 14.

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| EXP-2589 Basal adequacy | `exp_basal_adequacy_2589.py` | Quadrant analysis for closed-loop |
| EXP-2590 Dawn phenomenon | `exp_dawn_phenomenon_2590.py` | Selection bias kills EGP measurement |
| EXP-2591 IOB-corrected EGP | `exp_iob_corrected_egp_2591.py` | 6/9 patients have positive EGP |
| EXP-2592 Dual-pathway sim | `exp_dual_pathway_sim_2592.py` | Complexity ceiling (closes line) |
| EXP-2593 Loop workload | `exp_loop_workload_2593.py` | 9/12 basal too high (systematic) |
| EXP-2594 Meal response | `exp_meal_response_2594.py` | Sim ranks r=0.917, peaks -54 mg/dL |
| EXP-2595 Carb calibration | `exp_carb_calibration_2595.py` | Root cause: ISF/CR coupling |
| EXP-2596 Decoupled CSF | `exp_decoupled_csf_2596.py` | CSF=2.0 sweet spot (r=0.933, 53%) |
| Research report update | `digital-twin-autoresearch-2026-07-14.md` | Phase 4 added |

**Key Findings**:
- Overnight basal quadrant analysis invented (glucose slope × net basal direction)
- 9/12 patients have scheduled basal systematically too high
- Forward sim is a ranking tool (r=0.88-0.92), not magnitude predictor
- ISF and CSF serve different purposes; coupling via ISF/CR kills meal prediction
- Population CSF=2.0 mg/dL/g is the optimal decoupled value

**Productionized**: quadrant advisory (#13), workload advisory (#14), decoupled CSF
**Gaps Identified**: GAP-SIM-001 (magnitude accuracy), GAP-BASAL-001 (systematic overestimation)
**Tests**: 348 passing throughout

**Source Files Analyzed**:
- `tools/cgmencode/production/settings_advisor.py` (14 advisories)
- `tools/cgmencode/production/forward_simulator.py` (carb_sensitivity decoupling)
- `externals/ns-parquet/training/grid.parquet` (270 meal events, 9 patients)

### Digital Twin Autoresearch Phase 5-6 (2026-07-15)

Advisory system validation and ISF fix across 6 experiments (EXP-2601–2606).

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| EXP-2601 | `exp_dose_response_2601.py` | CRITICAL: ISF advisory magnitude inflated by sim calibration |
| EXP-2602 | `exp_isf_comparison_2602.py` | Correction-based ISF is clinically correct |
| EXP-2603 | `exp_circadian_isf_2603.py` | Circadian ISF varies 70-125% but direction is patient-specific |
| EXP-2604 | `exp_basal_adequacy_2604.py` | NEGATIVE: closed-loop confound masks basal adequacy |
| EXP-2605 | `exp_temporal_stability_2605.py` | ALL CONFIRMED: r=0.968 SQS stability |
| EXP-2606 | `exp_outcome_validation_2606.py` | SQS vs TIR r=0.726 (validated post-fix) |
| ISF fix | `settings_advisor.py` | Removed sim ISF, correction-based only |
| SQS update | `settings_advisor.py` | magnitude_pct basis (was tir_delta) |

**Key Findings**:
- ISF×0.5 sim calibration should NOT be used as clinical recommendation
- Advisory system is temporally stable (r=0.968 across halves)
- SQS with magnitude-based formula correlates with TIR (r=0.726)
- Overnight basal adequacy doesn't work for closed-loop (loop compensates)
- Circadian ISF direction is patient-specific, not universal

**Gaps Identified**: GAP-SIM-006 (sim calibration ≠ clinical recommendation)

**Productionized**: 19 features total (ISF source fix, SQS formula update)

**Source Files Modified**:
- `tools/cgmencode/production/settings_advisor.py` (19 productionized features)

### Phase 7: Advisory Hardening & Effective CR (2026-07-16)

Cross-controller validation, effective CR from meal response, SQS optimization,
and several negative results that closed research lines.

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| EXP-2607 | `exp_odc_validation_2607.py` | Cross-controller valid: combined r=0.689 (p=0.006, n=14) |
| EXP-2608 | `exp_drift_detection_2608.py` | Advisory too coarse for drift detection |
| EXP-2609 | `exp_effective_cr_2609.py` | Effective CR: 5/9 under-bolused, dawn CR tighter for 6/9 |
| EXP-2610 | `exp_cr_comparison_2610.py` | Sim CR = 0.5× artifact (same as ISF). r=0.934 with effective CR |
| EXP-2611 | `exp_prebolus_timing_2611.py` | Selection bias: pre-bolus ≠ better outcomes in observational data |
| EXP-2612 | `exp_post_cr_validation_2612.py` | Post-fix SQS still significant (p=0.043) |
| EXP-2613 | `exp_sqs_optimization_2613.py` | Weighted SQS (ISF 2×) best: r=0.603 (p=0.022) |
| EXP-2614 | `exp_isf_refinement_2614.py` | Grid boundary problem, not resolution |

**Key Findings**:
- Advisory system generalizes across AID controllers (NS + ODC)
- Sim CR has same 0.5× calibration artifact as ISF — removed from advisory
- Effective CR from meal response is actionable: +7.8pp TIR for correct bolusing
- ISF weighted 2× in SQS formula gives best TIR correlation
- Pre-bolus timing confounded by meal selection bias
- ISF grid needs extension not refinement (5/9 hit boundary)

**Gaps Identified**: Overlapping CR advisors need consolidation

**Productionized**: 23 features total (+4: effective CR, sim CR removal, SQS weighted, CR threshold)

**Source Files Modified**:
- `tools/cgmencode/production/settings_advisor.py` (23 productionized features)

**Closed Research Lines** (cumulative: 18 lines closed):
- Sim CR recommendations, pre-bolus timing, ISF grid refinement, drift detection

### Phase 8: Timescale Deconfounding & Metabolic Context (2026-07-16)

Systematic investigation of timescale hierarchy, loop deconfounding,
and metabolic state effects on insulin sensitivity.

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| EXP-2615 | `exp_circadian_cr_2615.py` | Dawn CR effect too small (p=0.96) |
| EXP-2616 | `exp_actual_delivery_2616.py` | Loop adjusts basal 65-88%, reactive SMB confound |
| EXP-2617 | `exp_suspension_natural_2617.py` | Suspension windows not cleaner |
| EXP-2618 | `exp_long_window_2618.py` | 8h sim fails: no metabolic demand model |
| EXP-2619 | `exp_metabolic_context_2619.py` | 6/9 show ISF split by carb history, patient-specific |

**Key Findings**:
- Forward sim valid regime: 2h correction windows ONLY
- Beyond 2h, unmeasured metabolic demand (glycogen, HGP) overwhelms insulin signal
- counter_reg_k absorbs both physiology AND insulin accounting errors
- Closed-loop confound is structural: loop delivery is FUNCTION of glucose
- Metabolic context explains 5-23% of ISF variance (patient-specific)
- Glycogen cycling operates on 24-72h timescale (literature + data confirm)

**Closed Research Lines** (cumulative: 23 lines closed):
- Circadian CR, actual delivery sim, suspension windows,
  8h+ sim, universal metabolic context
