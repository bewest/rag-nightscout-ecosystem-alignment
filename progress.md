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

## Wave-3: BG-Adjusted Circadian ISF, SC Ceiling Detection, Multi-Factor (2026-04-19)

Three experiments combining deconfounding techniques for maximum signal extraction.

| EXP | Title | Verdicts | Key Finding |
|-----|-------|----------|-------------|
| 2708 | BG-Adjusted Circadian ISF | H1✓ H2✓ H3✗ H4✓ | Peak shifts 12-16h→20-24h; 15.2% MAE improvement; TRUE circadian ratio 5.57× (larger, not smaller) |
| 2709 | SC Ceiling BG-Controlled | H1✗ H2✓ H3✓ H4✗ | Within-BG-band: ALL 6 bands show SC ceiling; power-law R²=0.934 vs linear 0.418 (β=0.595) |
| 2710 | Multi-Factor Deconfounding | H1✓ H2✓ H3✓ H4✓ | Combined R²=0.183; CV reduced 19.8%; BG MAE: 145.8→24.8 mg/dL; ALL 21 patients improve |

**Key Discoveries**:
- BG stratification successfully reveals SC ceiling hidden in raw observational data
- Multi-factor deconfounding reduces BG prediction error by 83% vs profile ISF
- True circadian ISF variation is LARGER than raw data suggests (BG confound was suppressing it)
- 6 of 7 deconfounding factors contribute incremental R² in stepwise addition

**Gaps**: GAP-ALG-073 (SC ceiling β=0.595 ≠ forward_simulator β=0.9)

## Follow-Up Experiments: Deconfounding the Deconfounders (2026-04-19)

Three follow-up experiments investigated confounds identified in the Tier-1 wave.

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| EXP-2705 | `tools/cgmencode/exp_midday_isf_peak_2705.py` | Midday ISF peak is BG confound; after control, peak shifts to 16-20h |
| EXP-2706 | `tools/cgmencode/exp_sc_slope_2706.py` | SC slope is positive (confounding by indication); ceiling not detectable this way |
| EXP-2707 | `tools/cgmencode/exp_glycogen_confound_2707.py` | Loaded glycogen → higher ISF is REAL; supports EGP as useful decomposition |

**Key Findings**:
- **Circadian confound identified**: Midday ISF peak (EXP-2702) is partially a BG-level confound. BG0 explains 71% of the joint model. After BG control, pattern shape changes completely (rank r=0.203 vs raw). Peak shifts from 12-16h to 16-20h.
- **BGI subtraction REVEALS signal**: Counter-intuitively, deviation has MORE circadian variance (η²=0.018) than raw ISF (η²=0.003). This means BGI subtraction removes a confound (BG level) that was masking the true circadian insulin effect.
- **SC ceiling undetectable by slope**: Dose-response slope is positive (median 0.856) — confounding by indication. Higher IOB → higher starting BG → more room to fall. The SC ceiling requires different methodology (likely comparison to simulated linear absorption, not observational dose-response).
- **Glycogen effect is REAL, not confounded**: EXP-2707 found that controlling for BG does NOT remove the glycogen effect within BG bands (effect is actually stronger: 3.2 vs 1.6 mg/dL/U). BG does not mediate the pathway (-9%). Interpretation: loaded glycogen → suppressed EGP → insulin is genuinely more effective. This validates EGP as a useful decomposition axis.
- **Confounding by indication is pervasive**: Both SC ceiling (EXP-2706) and glycogen (EXP-2707 H1) show controller behavior masking or reversing expected relationships. The controller gives more insulin when BG is high, creating positive correlations where negative ones are expected.

**Gaps Identified**: GAP-ALG-072 (confounding by indication makes SC ceiling undetectable from observational dose-response)

---

## Tier-1 Deconfounding Experiments: Circadian, SC Ceiling, Glycogen (2026-04-19)

Ran three Tier-1 experiments on full 22-patient cohort using the new deconfounding infrastructure.

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| EXP-2702 | `tools/cgmencode/exp_circadian_demand_isf_2702.py` | Circadian ISF: 1.35× population, 2.02× per-patient; 76% patients improve |
| EXP-2703 | `tools/cgmencode/exp_sc_ceiling_per_patient_2703.py` | SC ceiling highly variable; reliable (r=0.811) but ceiling↔wall correlation weak |
| EXP-2704 | `tools/cgmencode/exp_glycogen_state_detection_2704.py` | 48h carb signal exists (r=0.131, 13/21 sig) but too weak for settings |

**Key Findings**:
- Circadian demand-ISF is real and actionable: peak at 12-16h (28.8 mg/dL/U) vs trough 04-08h (21.3). All controllers show it.
- Dawn phenomenon is NOT a simple ISF shift — dawn and overnight ISF are nearly identical. The circadian peak is midday, not dawn.
- SC ceiling methodology needs refinement: IOB quantile binning at 50% threshold is too coarse. Most patients show no measurable ceiling. Consider dose-response slope instead of threshold.
- Glycogen (48h carbs) is a real but weak signal: 13/21 patients have significant correlation, but effect size is only -6.5% ISF modification. Not enough for settings extraction. Confirms EXP-2627's 9.2% R² as an upper bound.
- Counter-intuitive: loaded glycogen shows HIGHER ISF (26.3) than depleted (24.7). This contradicts insulin resistance expectation — may reflect confounding (more carbs → more insulin → more corrections at high BG where ISF is naturally higher).

**Gaps Identified**: GAP-ALG-071 (circadian ISF peak is midday, not dawn — implication for dawn phenomenon modeling)

---

## Deconfounding Pipeline Infrastructure & Three-Audience Report (2026-04-19)

Built reusable deconfounding infrastructure (4 production modules) and validated against EXP-2698. Extracted settings for 22 patients. Wrote three-audience transition report covering data understanding, settings optimization, and AID controller R&D recommendations.

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| Deconfounding strategies | `tools/cgmencode/production/deconfounding.py` | BGI subtraction, channel decomposition, event categorization, isolation, experiment presets |
| Experiment base class | `tools/cgmencode/production/experiment_base.py` | Standard data loading, declarative pipeline, auto-validation |
| R² Waterfall analysis | `tools/cgmencode/production/waterfall.py` | 5-stage R² (0.01→0.84), category models, controller splits, ISF recovery |
| Accuracy/precision framework | `tools/cgmencode/production/accuracy_precision.py` | Precision Grade A (CI 4.2), accuracy varies by patient |
| Integration test | `tools/cgmencode/production/test_waterfall_integration.py` | 6/6 scientific patterns, 8/11 quantitative, reproduces EXP-2698 |
| Three-audience report | `docs/60-research/deconfounding-pipeline-report-2026-04-19.md` | Data understanding + settings optimization + controller R&D |
| Waterfall visualization | `visualizations/waterfall-integration/waterfall_comparison.png` | Side-by-side R² comparison |

**Key Findings**:
- BGI subtraction is the dominant deconfounding lever (+0.31 R²; oref0 architecture validated)
- All 3 insulin channels interchangeable for subtraction (~−124 to −131 mg/dL/U)
- Precision Grade A across all patients (CI width 4.2 mg/dL/U); accuracy varies 0.3–2.8× ISF inflation
- ISF inflation measurable per-patient: Loop median 1.1×, Trio 1.2×, OpenAPS 1.3×
- Subtraction-over-exclusion keeps Trio/SMB data (exclusion yields ~0 events)
- 12/21 patients have accurate ISF extraction (bias <15 mg/dL/U)
- Trio basals well-calibrated (6/6 appropriate); Loop basals run high (3/4 too high)

**Gaps Identified**: None new (infrastructure consolidates existing findings)

**Source Files Analyzed**: EXP-2698, 45+ EGP/hepatic experiments catalogued, 22-patient settings extraction

---

## Expanded Cohort Experiment Validation (2026-04-18)

Reran 5 priority experiments on expanded 31+12 patient cohort after robustness audit.
Fixed Nyquist violations (2h→6h isolation, 4h→12h blocks), added NaN guards, parameterized
parquet paths, and added controller stratification.

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| Expanded Cohort Report | `docs/60-research/expanded-cohort-validation-report-2026-04-18.md` | 3 findings strengthened, 3 weakened at larger N |
| DynISF Characterization | `docs/60-research/dynisf-cohort-characterization-report-2026-04-18.md` | Cross-cohort reproducibility analysis |
| EXP-2651 results | `externals/experiments/exp-2651_two_phase_isf*.json` | N=25+12, demand ISF wins 92-100% at 2h |
| EXP-2652 results | `externals/experiments/exp-2652_circadian_profiling*.json` | N=18+10, 12h blocks modest improvement |
| EXP-2656 results | `externals/experiments/exp-2656_sc_ceiling*.json` | N=29+12, 100% slower than linear |
| EXP-2662 results | `externals/experiments/exp-2662_patience_mode*.json` | N=27+12, safe, 34-42% SMB savings |
| EXP-2640 results | `externals/experiments/exp-2640_per_patient_isf.json` | N=6, log model 5/6, LOO stable |

**Key Findings**:
- Two-phase ISF: Universally replicated (25/25 + 12/12). Demand ISF 1.3-5.3× lower than apparent.
- SC ceiling: 100% of patients slower than linear at high IOB. Ceiling range 30-56%.
- Patience mode: Safe across all patients. Max hyper +2.1pp. Mean hypo -0.4pp.
- Circadian 12h RMSE: Day/night split rarely improves prediction — signal detectable but weak.
- SC ceiling ↔ sticky hyper correlation weakens: r=-0.29 at N=29 (was r=-0.60 at N=12).

**Gaps Identified**: GAP-ALG-070 (circadian ISF insufficient RMSE gain for recommendation)

**Source Files Analyzed**: 5 experiment scripts in `tools/cgmencode/exp_*`

---

## Tier-2 DynISF Cross-Validation (2026-04-18)

Cross-validated 4 tier-2 experiments on 12-patient DynISF cohort to confirm algorithm-independence.

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| DynISF Cross-Validation Report | `docs/60-research/tier2-dynisf-cross-validation-report-2026-04-18.md` | Core findings replicate across AID algorithms |
| EXP-2663 dynisf | `externals/experiments/exp-2663_demand_dose_dependence_dynisf.json` | Demand |r|=0.110 (dose-independent, replicates orig 0.097) |
| EXP-2667 dynisf | `externals/experiments/exp-2667_sc_ceiling_demand_isf_dynisf.json` | Higher ceiling 34.4% (vs 22.5% orig); H4 flips FAIL→PASS |
| EXP-2669 dynisf | `externals/experiments/exp-2669_wall_resolution_mechanism_dynisf.json` | 78% unaccounted (vs 68% orig) |
| EXP-2668 dynisf | `externals/experiments/exp-2668_controller_isf_signatures_dynisf.json` | H1-H4 SKIP (single controller type, expected) |

**Key Findings**:
- Demand ISF dose-independence replicates (|r|<0.15 both cohorts)
- DynISF patients show higher SC ceiling (34.4% vs 22.5%) — better absorption
- Higher unaccounted wall resolution (78% vs 68%) — DynISF users may intervene more

---

## Tier-3 Therapy & Phenotyping (2026-04-18)

Ran 4 tier-3 synthesis experiments (2291/2321/2331/2351) on 31+12 patients.

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| Tier-3 Report | `docs/60-research/tier3-therapy-phenotype-report-2026-04-18.md` | 16/31 safe to implement; mean TIR -0.5pp |
| EXP-2351 results | `externals/experiments/exp-2351-2358_insulin_pk*.json` | 26/31 slow PK type, DIA 12.3h median |
| EXP-2321 results | `externals/experiments/exp-2321-2328_phenotype*.json` | 8 HIGH, 11 MOD, 3 LOW risk |
| EXP-2331 results | `externals/experiments/exp-2331-2338_prediction_bias*.json` | Only 2/29 safe; most show prediction benefit |
| EXP-2291 results | `externals/experiments/exp-2291-2298_integrated*.json` | 16/31 safe, 20/31 ≥70% TIR |
| EXP-2665 results | `externals/experiments/exp-2665_nyquist_circadian_isf*.json` | H4 PASS: demand ISF has NO circadian variation |

**Key Findings**:
- Conservative guardrails: most patients show benefit potential but few pass all 7 safety checks
- Demand ISF circadian variation confirmed absent at all Nyquist-appropriate block sizes
- DynISF patients show similar risk/phenotype distributions
- Mean TIR improvement slightly negative (-0.5pp) — settings optimization is harder than expected

**Gaps Identified**: GAP-ALG-072 (integrated recommendation TIR degradation needs investigation)

---

## Tier-2 Expanded Cohort: Dose-Dependence & Wall Resolution (2026-04-18)

Reran 5 tier-2 experiments (EXP-2636/2640/2663/2667/2669) after robustness audit.
Fixed 6h Nyquist isolation (was 2h), NaN guards on scipy, argparse parameterization,
dynamic patient discovery from parquet.

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| Tier-2 Report | `docs/60-research/tier2-expanded-cohort-report-2026-04-18.md` | Demand ISF dose-independent, wall episodes 68% out-of-band |
| EXP-2636 results | `externals/experiments/exp-2636_dose_dependent_isf*.json` | N=18+dynisf, 175 corrections, H4 PASS (19.2% RMSE improvement) |
| EXP-2663 results | `externals/experiments/exp-2663_demand_dose_dependence.json` | N=23, demand |r|=0.097 — dose-INDEPENDENT |
| EXP-2667 results | `externals/experiments/exp-2667_sc_ceiling_demand_isf.json` | N=29, demand-ISF ceiling beats scheduled-ISF |
| EXP-2669 results | `externals/experiments/exp-2669_wall_resolution_mechanism.json` | N=24, 1763 episodes, 68% unaccounted resolution |
| EXP-2640 results | `externals/experiments/exp-2640_per_patient_isf.json` | N=6 (3 new patients), log model wins 6/6 |

**Key Findings**:
- Demand-phase ISF is dose-INDEPENDENT (|r|=0.097) — constant per-patient ISF sufficient for dosing
- SC ceiling model with demand ISF outperforms scheduled ISF (EXP-2667 H3 PASS)
- 68% of wall resolutions show glucose drops without IOB increase — out-of-band interventions
- EXP-2636 H1/H2 reversed at 6h isolation: larger boluses → LESS drop/unit (ISF deflation)
- Resolution timing clusters at 2-4h (demand-phase cycle, 58.3% in 1.5-4.5h window)

**Gaps Identified**: GAP-ALG-071 (out-of-band interventions invisible to telemetry, 68% confound)

**Source Files Analyzed**: 5 experiment scripts in `tools/cgmencode/exp_*_26{36,40,63,67,69}.py`

---

## Cross-Controller Validation & Autoprepare Gate (2026-04-19)

Validated cross-controller data fidelity on expanded 31-patient dataset (Loop=9, Trio=13, 
OpenAPS=8). Two experiments: EXP-2671 (8-panel validation dashboard) and EXP-2672 
(qualification gate). Fixed enacted-rate percent-encoding bug in grid.py.

### Key Results

| EXP | Purpose | Verdict | Key Finding |
|-----|---------|---------|-------------|
| 2671 | Cross-controller data fidelity | PASS (w/ caveats) | Core fields safe; 7 patients flagged |
| 2672 | Autoprepare qualification gate | ALL 4 GATES PASS | 22 qualified patients ready for autoresearch |

### Autoresearch Wave (EXP-2673–2675)

| EXP | Question | Key Finding |
|-----|----------|-------------|
| 2673A | Circadian ISF replication | NO signal (p=0.18, 562 events, 22 patients) |
| 2673B | Sensitivity ratio validation | Effective ISF 1.4-5.2× inflated vs demand (r=0.70) |
| 2674 | DynISF formula effect | **Sigmoid=6.6× inflation vs Log=2.5×** — formula predicts inflation |
| 2675 | Cross-controller portability | **Patient physiology = 81.9% of ISF variance** |

### Deliverables

| Deliverable | Location |
|-------------|----------|
| Validation Report | `docs/60-research/cross-controller-validation-report-2026-04-19.md` |
| EXP-2671 Figures | `visualizations/cross-controller-validation/fig[1-8]_*.png` |
| EXP-2672 Gate Figures | `visualizations/autoprepare-gate/fig[1-4]_*.png` |
| EXP-2673 Wave 1 Figures | `visualizations/autoresearch-wave1/fig[1-6]_*.png` |
| EXP-2674 DynISF Figures | `visualizations/autoresearch-wave2/fig[1-6]_*.png` |
| EXP-2675 Portability Figures | `visualizations/autoresearch-wave3/fig[1-5]_*.png` |
| Qualified Manifest | `externals/experiments/autoprepare-qualified.json` |
| Pipeline Fix | `tools/ns2parquet/grid.py` (percent-encoding auto-fix) |

### Status: 🔬 Autoresearch IN PROGRESS

---

## EGP Deconfounding & Recovery Model Comparison (2026-04-13/14)

Two rounds of autoresearch testing whether EGP or any single-factor model can improve
AID post-correction predictions. 7 experiments (EXP-2629–2635) across 219 properly-filtered
correction events from 9 patients.

### Key Results

| EXP | Hypothesis | Verdict | Key Finding |
|-----|-----------|---------|-------------|
| 2629 | AID Compensation Cascade | PASS (H1) | IOB drops 55% before hypo crossing |
| 2630 | EGP vs AID Deconfounding | COUPLED | Sum=34 vs actual=4.1 mg/dL/hr, loop gain=8.3× |
| 2634 | 5-Model Recovery Comparison | ALL FAIL | All R² negative (−2.4 to −3.2); Hill EGP worst |
| 2635 | Recovery Attribution | IOB r=−0.07 | Only bolus size significant (r=−0.31, negative) |

### Research Lines Closed

- ❌ EGP as additive prediction term (WORST model, R² = −3.2)
- ❌ IOB decay as recovery driver (r = −0.068, no correlation)
- ❌ Glycogen/48h carbs → recovery (r = −0.15, wrong direction)
- ❌ Circadian recovery (p = 0.85, no effect)
- ❌ ALL single-factor physiological models (all R² < 0)

### Reports & Figures

| Deliverable | Location |
|-------------|----------|
| Round 1 Report | `docs/60-research/egp-deconfounding-report-2026-04-13.md` |
| Round 2 Report (Revised) | `docs/60-research/egp-calibration-report-2026-04-13.md` |
| Figures 19–24 | `visualizations/egp-deconfounding/fig19-24*.png` |
| Figures 29–31 | `visualizations/egp-deconfounding/fig29-31*.png` |

### GAP-EGP-004/005/006

- GAP-EGP-004: No single recovery model works (all R² < 0)
- GAP-EGP-005: IOB decay does not drive recovery (r = −0.068)
- GAP-EGP-006: Bolus-size-dependent ISF needed (r = −0.307)

## Dose-Dependent ISF & Methodology Validation (2026-04-13, Rounds 3–4)

Two rounds continuing EGP deconfounding: Round 3 discovered dose-dependent ISF as the
strongest signal; Round 4 validated methodology and characterized per-patient curves.
5 experiments (EXP-2636–2640), 8 figures (fig32–39), 2 reports.

### Key Results

| EXP | Hypothesis | Verdict | Key Finding |
|-----|-----------|---------|-------------|
| 2636 | Dose-Dependent ISF | CONFIRMED | r = −0.56, ISF = 100→22 mg/dL/U (4.6× range) |
| 2637 | Stacking Worsens Outcomes | REFUTED | AID compensates, CV diff −5.6% (p=0.28) |
| 2638 | Controller Predictability | UNPREDICTABLE | R² = 0.074, oscillates at 1.42h |
| 2639 | Sampling Robustness | ALL PASS | Bootstrap CI [−0.67, −0.44], survives subsampling |
| 2640 | Per-Patient ISF Curves | LOG MODEL | 5/6 patients log-ISF, LOO all r < −0.49 |

### New Discoveries

- **Logarithmic ISF**: ISF ≈ 50 − 28 × ln(dose_U), universal across patients
- **Cross-patient convergence**: CV = 8–9% at matched doses (1.5–3.0U)
- **Methodology validated**: Block bootstrap, subsampling, LOO all confirm findings
- **48h carb effects underpowered**: Need N=347 vs our N=219

### GAP-EGP-007/008/009

- GAP-EGP-007: ISF is dose-dependent with logarithmic scaling
- GAP-EGP-008: Glucose drop ceiling (~140 mg/dL population average, up to 340 individual)
- GAP-EGP-009: Cross-patient ISF convergence at medium doses (universal correction factor feasible)

### Reports & Figures

| Deliverable | Location |
|-------------|----------|
| Round 3 Report | `docs/60-research/egp-dose-isf-report-2026-04-13.md` |
| Round 4 Report | `docs/60-research/egp-methodology-validation-report-2026-04-13.md` |
| Figures 32–35 | `visualizations/egp-deconfounding/fig32-35*.png` |
| Figures 36–39 | `visualizations/egp-deconfounding/fig36-39*.png` |

## Descriptive-Prescriptive Paradox (2026-04-13, Round 5)

Tests whether dose-dependent ISF can improve correction dosing. Reveals a fundamental
paradox: the best descriptive model is the worst prescriptive one.

### Key Results

| EXP | Hypothesis | Verdict | Key Finding |
|-----|-----------|---------|-------------|
| 2641 | Forward Sim Log-ISF | PARTIAL | Per-patient log MAE=59 (30% better), but all R² < 0 |
| 2642 | Retrospective Dose Audit | ALL FAIL | Log-ISF recommends 2.3× optimal dose; fixed ISF closer |

### Core Discovery

Apparent ISF from corrections is an **emergent closed-loop property** that includes the
AID controller's response (basal withdrawal). Using it for dosing creates a circular
dependency: changing the dose changes the controller response, invalidating the ISF.

- Fixed ISF + controller feedback is near-optimal
- 16% hypo rate is from irreducible per-event variability, not systematic ISF error
- Controller gain ~8× means the controller, not the bolus, drives glucose trajectory

### GAP-EGP-010/011

- GAP-EGP-010: Apparent ISF is emergent (closed-loop), not intrinsic (cannot be used for dosing)
- GAP-EGP-011: Per-event ISF variability irreducibly high (all models R² < 0)

### Reports & Figures

| Deliverable | Location |
|-------------|----------|
| Round 5 Report | `docs/60-research/egp-prescriptive-paradox-report-2026-04-13.md` |
| Figures 40–43 | `visualizations/egp-deconfounding/fig40-43*.png` |

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

### Phase 9: Validation, Overrides & Advisory Maturity (2026-07-16)

Loop prediction validation, override ISF detection, and advisory
convergence analysis. Two findings productionized.

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| EXP-2620 | `exp_loop_prediction_validation_2620.py` | Universal positive bias in loop predictions |
| EXP-2621 | `exp_override_exercise_2621.py` | 8/12 show ISF split during overrides → productionized |
| EXP-2622 | `exp_advisory_convergence_2622.py` | CR stable by 21d, direction by 7d → productionized |
| Productionized | `settings_advisor.py` | 2 new advisories, 12 new tests (360 total) |

**Productionized**:
- `advise_override_isf()` — ISF split detection during overrides
- `compute_advisory_confidence_tier()` — Data-dependent confidence tiers
- Advisory count: 17 (up from 15), test count: 360 (up from 348)

**Closed Research Lines** (cumulative: 27 lines closed):
- Loop prediction as ISF validation, exercise ISF, override filtering,
  corrections→convergence speed

### Phase 10: Validation & Production Hardening (2026-07-15)

Shifted from exploration to validation. Tested whether 17 advisories work
coherently, generalize to unseen patients, and are clinically safe.

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| EXP-2623 | `tools/cgmencode/production/exp_multi_feature_isf_2623.py` | R²=7.6%, closes ISF prediction line |
| EXP-2624 | `tools/cgmencode/production/exp_advisory_audit_2624.py` | 0 contradictions, SQS↔TIR r=0.717 |
| EXP-2625 | `tools/cgmencode/production/exp_odc_crossval_2625.py` | Generalizes to 7 ODC patients |
| EXP-2626 | `tools/cgmencode/production/exp_safety_guardrails_2626.py` | 36% exceed 25%, safety clamp added |
| Safety clamp | `tools/cgmencode/production/settings_advisor.py` | apply_safety_clamp(), 366 tests pass |
| Research report | `docs/60-research/digital-twin-autoresearch-2026-07-14.md` | Phase 10 section |

**Key Findings**:
- Advisory pipeline validated across 16 patients (9 NS + 7 ODC)
- Zero contradictions, consistent priority (CR > ISF > basal)
- Settings Quality Score correlates with TIR (r=0.717, p=0.030)
- Safety clamp caps magnitudes at 25% per cycle

**Gaps Identified**: Advisory deduplication (per-block CR fires 3-5x),
forward sim lacks glycogen model for >2h accuracy.

**Closed Research Lines**: Per-window ISF prediction, multi-feature ISF,
loop workload ratio as ISF predictor (3 new closures, 30 total).

### Phase 10 Addendum: EXP-2627-2628 (2026-07-15)

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| EXP-2627 | `tools/cgmencode/production/exp_deduplication_2627.py` | 52% reduction, 100% direction agreement |
| EXP-2628 | `tools/cgmencode/production/exp_autosens_validation_2628.py` | Autosens ≠ ISF calibration |
| Deduplication | `tools/cgmencode/production/settings_advisor.py` | _deduplicate_same_direction(), 371 tests |
| Final report | `docs/60-research/digital-twin-autoresearch-2026-07-14.md` | Cumulative research summary |

**Cumulative totals**: 68 experiments, ~147 hypotheses, ~75 confirmed (51%).
19 production features. 371 tests. 34 closed research lines.
Validated across 16 patients from 2 independent sources.

### Cross-Controller PK Model Comparison — EXP-2676 (2026-04-19)

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| PK model comparison | `tools/cgmencode/exp_pk_model_comparison_2676.py` | All 4 AID systems use identical exponential PK formula |
| 6-panel dashboard | `visualizations/pk-model-comparison/fig[1-6]_*.png` | IOB decomposition, decay, activity, BG prediction |
| Updated report | `docs/60-research/cross-controller-validation-report-2026-04-19.md` | PK section added |

**Key Findings**:
- ALL 4 systems (Loop, oref0, AAPS, Trio) share identical exponential IOB formula from LoopKit #388
- Difference is only parameters: DIA (3h-10h), peak (45-75min)
- IOB decomposition is perfect: bolus_iob + basal_iob = total IOB (MAE < 0.001U)
- Empirical IOB decay does NOT match theory — AID continuous dosing masks true PK
- IOB semantics differ: Loop median=0.69U, Trio=0.00U, OpenAPS=0.08U
- pred_iob_30 is a BG prediction (mg/dL), not insulin — OpenAPS best accuracy (MAE=13.9)

**Cumulative (EXP-2671-2676)**: 6 cross-controller experiments, 22 qualified patients
(Loop=8, Trio=11, OpenAPS=3), 44 visualizations.

### AID Compensation Artifact — EXP-2677 (2026-04-19)

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| AID compensation analysis | `tools/cgmencode/exp_aid_compensation_artifact_2677.py` | 57% negative ISF is artifact |
| 6-panel dashboard | `visualizations/aid-compensation-artifact/fig[1-6]_*.png` | Prevalence, trajectory, insulin, basal, timing, BG |

**Key Findings**:
- 57% of correction events show negative ISF (glucose RISES) — universal across ALL controllers
- Root cause: corrections at in-range glucose (median BG=106 for neg ISF vs 160 for positive)
- NOT AID backing off (IOB change is HIGHER for neg ISF events)
- NOT glucose already rising (pre-bolus ROC lower for neg ISF events)
- BG floor filter dramatically reduces: ≥120→39%, ≥160→27%, ≥180→23%, ≥200→20%
- Remaining ~20% at high BG is genuine AID compensation + regression to mean
- METHODOLOGY FIX: All correction ISF extraction must require BG ≥ 150-180 mg/dL

### BG Floor Sensitivity Analysis — EXP-2678 (2026-04-19)

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| Sensitivity analysis | `tools/cgmencode/exp_bg_floor_sensitivity_2678.py` | 3 key findings change with BG floor |
| Summary figure | `visualizations/bg-floor-sensitivity/fig1_sensitivity_summary.png` | All 3 tests on one chart |

**Key Findings**:
- CIRCADIAN ISF: At BG≥180, p=0.0009 — genuine circadian signal MASKED by meal noise in EXP-2673
  - BG≥0: p<0.001 (artifact from meal timing), BG≥120: p=0.82, BG≥150: p=0.15, BG≥180: p=0.0009
- VARIANCE DECOMPOSITION: ROBUST — patient >> controller at all BG floors (0.4-3.8% controller)
- DYNISF INFLATION: Lower with BG floor (1.2-1.8× vs 6.6× in EXP-2674) — earlier extremes from near-range corrections

**Methodology revision**: EXP-2673's "no circadian signal" conclusion is QUALIFIED.
True corrections (BG≥180) DO show circadian ISF variation. Must re-investigate.

### Circadian ISF Deep Dive — EXP-2679 (2026-04-19)

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| Circadian ISF analysis | `tools/cgmencode/exp_circadian_isf_deep_dive_2679.py` | Loop-specific circadian signal |
| 5-panel dashboard | `visualizations/circadian-isf-deep-dive/fig[1-5]_*.png` | Hourly, controller, patient, dawn, magnitude |

**Key Findings**:
- Overall Kruskal-Wallis p=0.0009 with BG≥180 filter (confirms EXP-2678)
- Signal is LOOP-SPECIFIC: Loop p=7e-06 (n=597), OpenAPS p=0.40 (n=402), Trio p=0.40 (n=57)
- Peak ISF at 2PM UTC (31.7 mg/dL/U), trough at midnight (2.0)
- NO dawn phenomenon: dawn (4-8AM) ISF=17.0 vs non-dawn=15.6, p=0.95
- 75.3% positive ISF with BG≥180 floor (vs 43% without)
- Interpretation: likely controller behavior artifact (Loop temp basal patterns) not pure physiology,
  since OpenAPS (n=402) shows no signal with adequate power

### Definitive ISF Characterization — EXP-2680 (2026-04-19)

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| Definitive ISF analysis | `tools/cgmencode/exp_definitive_isf_2680.py` | BG≥180 + 2h isolation on 22 patients |
| 7-panel dashboard | `visualizations/definitive-isf/fig[1-7]_*.png` | Distribution, per-patient, variance, profile, DynISF, stability, summary |

**Key Findings**:
- 7986 events (all BG), 1226 at BG≥180 — 73-88% positive ISF with floor vs 36-43% without
- Trio severely underpowered at BG≥180 (only 66 events — tight control)
- ISF differs significantly across controllers (Kruskal-Wallis p<0.0001)
- Demand ISF appears dose-dependent (r=-0.418) at BG≥180 — REVISES EXP-2663

### BG Drop Direct Modeling — EXP-2681 (2026-04-19)

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| BG drop model | `tools/cgmencode/exp_bg_drop_model_2681.py` | Dose-independent drop, BG0 is best predictor |
| 6-panel dashboard | `visualizations/bg-drop-model/fig[1-6]_*.png` | Dose-response, BG, IOB, multivariate, per-patient, bins |

**BREAKTHROUGH FINDING**: BG drop after correction is ~74 mg/dL REGARDLESS of dose:
- Loop: 78 mg/dL drop with 4.0U dose
- OpenAPS: 71 mg/dL drop with 1.0U dose
- Trio: 64 mg/dL drop with 1.4U dose

Model R² breakdown:
- log(dose): 0.015 — dose barely predicts BG drop
- BG0: 0.141 — starting BG is the best single predictor
- IOB: 0.001 — IOB doesn't help
- Full: 0.146 — adding all predictors barely improves

**Implication**: In observational AID data, bolus dose shows low correlation with BG drop
(R²=0.015). This reflects the controller compensating through other channels (SMB, temp
basal), NOT that insulin is ineffective. The "dose-dependent ISF" from EXP-2680 is a ratio
artifact (constant drop / varying dose). Isolating the bolus treatment effect requires causal
methods — the controller's co-intervention confounds observational estimates.

### Controller vs Bolus Insulin — EXP-2682 (2026-04-19)

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| Controller vs bolus | `tools/cgmencode/exp_controller_vs_bolus_2682.py` | Neither bolus NOR total insulin predicts BG drop |
| 5-panel dashboard | `visualizations/controller-vs-bolus/fig[1-5]_*.png` | Insulin, fraction, response, trajectory, models |

**HEADLINE**: Total 2h insulin (R²=0.0007) predicts BG drop even LESS than bolus alone (R²=0.004).
Trio delivers 4× OpenAPS insulin (8.3U vs 2.3U) for a SMALLER BG drop (64 vs 71 mg/dL).

R² model comparison:
- BG0: 0.141 — starting BG is the only meaningful predictor
- Net basal excess: 0.011
- Bolus dose: 0.004
- IOB start: 0.001
- Total 2h insulin: 0.001
- Full model: 0.192

**Bolus fraction of total 2h insulin**:
- Loop: 58% (bolus-dominant correction)
- OpenAPS: 42% (mixed)
- Trio: 20% (controller-dominant — aggressive SMBs)

**Implication**: 86% of BG drop variance is unexplained by ANY insulin measure.
BG drop is dominated by physiological factors (EGP, carb absorption, exercise, stress)
not by insulin dose — whether manual or controller-delivered.

### Unexplained BG Drop Variance — EXP-2683 (2026-04-19)

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| Variance analysis | `tools/cgmencode/exp_unexplained_variance_2683.py` | 83.5% irreducible stochastic variance |
| 5-panel dashboard | `visualizations/unexplained-variance/fig[1-5]_*.png` | ROC, carbs, regression, random effects, model |

**HEADLINE**: Full model with ALL available predictors achieves R²=0.165.
83.5% of correction BG drop variance is IRREDUCIBLE noise.

R² Model Comparison:
- Full (FE + all): 0.165 — ceiling
- BG₀ alone: 0.138 — most of what's predictable
- Regression to mean: 0.130 — BG returns toward mean regardless
- Patient FE: 0.028 — patient identity barely helps
- Glucose ROC: 0.000 — momentum is irrelevant
- Has carbs: 0.000 — concurrent carbs don't change drop

Additional findings:
- 51% of BG≥180 correction events have concurrent carbs (>5g)
- Carb events show identical drop (75 vs 74 mg/dL, p=0.87)
- ICC = 0.173 — only 17% of variance is between-patient
- Regression to mean slope = 0.38 (each 10 mg/dL above patient mean → 3.8 mg/dL extra drop)

**Interpretation**: BG correction outcome is dominated by stochastic physiological factors
(EGP variation, stress hormones, physical activity, meal timing uncertainty).
Neither insulin dose, controller behavior, glucose momentum, nor carb presence meaningfully
predicts whether a correction will be effective. The BG≥180 → ~74 mg/dL drop is essentially
regression to the mean plus physiological noise.

### Aggregate Outcome Modeling — EXP-2684 (2026-04-19)

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| Aggregate outcomes | `tools/cgmencode/exp_aggregate_outcomes_2684.py` | Settings don't predict TIR |
| 6-panel dashboard | `visualizations/aggregate-outcomes/fig[1-6]_*.png` | By controller, ISF, CR, TDD, safety, summary |

**HEADLINE**: Trio achieves 89.9% TIR (median) vs Loop 73.3% vs OpenAPS 68.4%.
But ISF/CR/TDD settings show ZERO correlation with outcomes:

- ISF vs TIR: r=-0.046 (p=0.84)
- CR vs TIR: r=0.194 (p=0.39)  
- TDD vs TIR: r=-0.120 (p=0.59)

Trio uses 56% more insulin than Loop (42.7 vs 27.3 U/day) for 17pp higher TIR.
OpenAPS uses similar insulin to Trio (43.9 U/day) but achieves the worst TIR.

**Interpretation**: Controller algorithm strategy matters more than any individual setting.
Trio's aggressive SMB + DynISF approach achieves better outcomes regardless of ISF/CR tuning.

### Controller Decision-Making Strategy — EXP-2685 (2026-04-19)

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| Strategy comparison | `tools/cgmencode/exp_controller_strategy_2685.py` | Bang-bang vs proportional control |
| 7-panel dashboard | `visualizations/controller-strategy/fig[1-7]_*.png` | Dosing, thresholds, reaction, basal, SMB, suspend, time-of-day |

**HEADLINE**: Trio/Loop are "bang-bang" controllers (83%/65% suspended), OpenAPS is proportional (33% normal).

| Strategy | Loop | Trio | OpenAPS |
|----------|------|------|---------|
| Basal suspended | 64.7% | 82.6% | 33.9% |
| SMB rate | 15.0% | 19.8% | 0.0% |
| Normal basal | 6% | 5% | 33% |
| TIR achieved | 73.3% | 89.9% | 68.4% |

- Trio/Loop: suspend basal most of the time, deliver bursts of SMBs when BG rises
- OpenAPS (these sites): no SMBs, smooth basal modulation — likely oref0 without SMB enabled
- 0-minute reaction time: Loop/Trio deliver SMBs at the SAME 5-min interval as BG≥150 crossing
- Trio achieves best TIR with the most extreme bang-bang strategy

### Safety Analysis — EXP-2686 (2026-04-19)

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| Safety analysis | `tools/cgmencode/exp_safety_analysis_2686.py` | IOB near zero at hypo onset |
| 6-panel dashboard | `visualizations/safety-analysis/fig[1-6]_*.png` | Frontier, characterization, temporal, pre-hypo, IOB, DynISF |

**Clinical target (TIR≥70%, hypo≤4%)**:
- Trio: 5/10 (50%) — best
- Loop: 3/9 (33%)
- OpenAPS: 1/3 (33%)

**IOB at hypo onset is near zero for ALL controllers** — but this is the
controller's RESPONSE (suspension), not the cause. Hypos are caused by insulin
delivered earlier. Loop IOB trajectory into hypo: 1.95U → 0.88 → 0.28 → −0.31U
over 2h. The controller detects falling BG and suspends, mitigating severity.
Without AID suspension, hypos would be deeper and longer.

**OpenAPS has deepest hypos** (nadir 57 vs 62) and longest (25min vs 15-20) —
consistent with less aggressive suspension (proportional control, not bang-bang).

**DynISF formula within Trio**: log → 90.5% TIR / 5.1% hypo; sigmoid → 86.0% TIR / 3.3% hypo.
Log formula is more aggressive (higher TIR but more hypos).

### Null Model Benchmark — EXP-2687 (2026-04-19)

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| Null model | `tools/cgmencode/exp_null_model_2687.py` | No-bolus drop > bolus drop |
| 6-panel dashboard | `visualizations/null-model/fig[1-6]_*.png` | Null, trajectory, treatment effect, dose-response |

**BREAKTHROUGH**: No-bolus events at BG≥180 drop **MORE** than bolus events:
- Bolus drop: 53 mg/dL (median)
- No-bolus (null): 61.7 mg/dL
- "Treatment effect": **−8.7 mg/dL** (negative — bolus events do worse!)

**Null model accounts for 116.5% of bolus drop.** The AID controller alone handles
high BG more effectively than user boluses. BUT see EXP-2689 for confounding analysis.

### Within-Patient Temporal Trends — EXP-2688 (2026-04-19)

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| Temporal trends | `tools/cgmencode/exp_temporal_trends_2688.py` | No learning curve |
| 5-panel dashboard | `visualizations/temporal-trends/fig[1-5]_*.png` | Weekly TIR, first/last, settings drift |

**No learning curve detected**: TIR change first→last month = +0.9 pp (p=0.579).
Only 3/22 patients show significant improvement. Settings tuning does not measurably
improve outcomes. Controller algorithm dominates from the start.

### Confounding by Indication — EXP-2689 (2026-04-19)

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| Confounding analysis | `tools/cgmencode/exp_confounding_2689.py` | Users bolus in harder situations |
| 6-panel dashboard | `visualizations/confounding-analysis/fig[1-6]_*.png` | Pre-trajectory, carbs, matched |

**Why bolus events drop less** (explains EXP-2687):
1. **Pre-event trajectory**: Bolus pre-slope = +1.9 (rising), null = −0.4 (falling).
   Users bolus when BG is going UP, not when already coming down.
2. **53% of boluses are meal boluses** fighting incoming carbs (drop = 47 mg/dL).
3. **IOB already higher at bolus events** (2.5U vs 1.8U) — controller was already maxed.
4. **Correction-only boluses**: 58 mg/dL (closer to null 61, but still less).
5. **Rising BG only**: bolus=48, null=46 → Δ=+2 (no treatment effect when BG rising).

**Conclusion**: Confounding by indication explains the negative "treatment effect" in
EXP-2687. Users bolus in harder situations (rising BG, concurrent meals, controller
already at high effort). The "no-bolus" condition is NOT zero insulin — the controller
is still actively managing via temp basals and SMBs. We cannot estimate the true
treatment effect of a bolus from this observational data because the controller's
co-intervention confounds the comparison. All insulin channels (bolus, SMB, basal
modulation) contribute to glucose management; isolating any one requires causal methods.

### Multi-Channel Insulin Decomposition — EXP-2690 (2026-04-19)

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| Multi-channel decomposition | `tools/cgmencode/exp_multi_channel_2690.py` | All channels significant |
| 7-panel dashboard | `visualizations/multi-channel/fig[1-7]_*.png` | Correlation, effects, variance |

**Multi-factor analysis recovers R²=0.296** (vs 0.015 for bolus alone):
- Starting BG: 13.3% unique variance (largest factor)
- **Bolus: 7.3% unique** (p≈0, highly significant when controlling for co-intervention)
- **Excess basal: 6.4% unique** (controller's basal modulation is a major channel)
- SMB: 0.9%, Carbs: 0.6%, ROC: 0.5% — all significant
- Within-patient R²=0.318; controller-stratified: Loop=0.378, Trio=0.394, OpenAPS=0.132

**Key correction**: Earlier "insulin irrelevance" was an artifact of single-factor analysis.
When controlling for all channels simultaneously, each shows significant partial effects.
The controller compensates through other channels, which MASKS the bolus effect in
univariate analysis but does NOT mean the bolus has no effect.

### Settings Mediation Analysis — EXP-2691 (2026-04-19)

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| Settings mediation | `tools/cgmencode/exp_settings_mediation_2691.py` | Settings → behavior → outcomes |
| 6-panel dashboard | `visualizations/settings-mediation/fig[1-6]_*.png` | Mediation, within-patient, frontier |

**Settings DO affect outcomes, mediated through controller behavior:**
- ISF → SMB rate: r=−0.115, p=1.2e-11 (lower ISF → more aggressive dosing)
- SMB rate → TIR: r=+0.169, p=2.2e-23 (more SMBs → higher TIR)
- Patient-level (settings + controller → TIR): R²=0.335 (n=22, underpowered)

**Within-patient natural experiments**: Settings barely change (ISF range=0.1 mg/dL/U),
limiting power. Mean r(ΔISF, ΔTIR)=0.110; 2/22 patients show significant effects.

**Key insight**: Settings configure controller behavior. Controller behavior determines
outcomes. The causal chain is: Settings → Controller aggressiveness → Glucose outcomes.
This is the coupled system working as designed.

### Advanced Multi-Factor Analysis — EXP-2692 to EXP-2694 (2026-04-19)

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| Dose-response curves | `tools/cgmencode/exp_dose_response_2692.py` | Marginal effects, non-linearity, substitution |
| TIR gap decomposition | `tools/cgmencode/exp_tir_gap_2693.py` | Oaxaca decomposition, multi-factor TIR model |
| Time-resolved decomposition | `tools/cgmencode/exp_time_resolved_2694.py` | R² growth 0.183→0.296, controller channel substitution |
| 18-panel visualizations | `visualizations/{dose-response,tir-gap,time-resolved}/` | Complete analysis dashboards |

**EXP-2692: Dose-Response — All coefficients are NEGATIVE (confounding by indication)**
- Bolus: −7.48 mg/dL/U, SMB: −4.34, Excess basal: −7.88
- More insulin → less BG drop because controller gives more in harder situations
- Non-linearity: R² +2.4pp (0.296→0.320), statistically significant but modest
- Trio SMBs strongest per-unit (−11.20), Loop boluses strongest (−8.56)

**EXP-2693: TIR Gap Decomposition — 11.4pp gap nearly fully explained**
- CV glucose: +11.9pp (patient selection — Trio patients less variable)
- SMB rate: +11.6pp (algorithm feature)
- TDD: −9.3pp (Trio uses more insulin)
- Full patient-level model: R²=0.702 (controller alone: 0.427)

**EXP-2694: Time-Resolved — R² grows linearly with horizon**
- 30 min: 0.183 → 60 min: 0.215 → 90 min: 0.254 → 120 min: 0.296
- Controller substitution: when user boluses, controller suspends (−3.51 vs −1.41U)
  and adds SMBs (2.29 vs 0.00U) — channels are dynamically interchangeable
- BG₀-matched comparison shows similar trajectories with/without bolus

**Cumulative findings (24 experiments, EXP-2671–2694)**:
Multi-factor decomposition is mandatory for AID analysis. Single-factor misleads.
70% of patient-level TIR variance explained. 30% of event-level variance explained.
Controller channel substitution is the primary reason observational analysis fails.

### Causal Inference Toolkit — EXP-2695 to EXP-2697 (2026-04-19)

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| Propensity score matching | `tools/cgmencode/exp_causal_psm_2695.py` | ATT = −1.2 mg/dL at 120m; controller compensates ~90% |
| Impulse response functions | `tools/cgmencode/exp_impulse_response_2696.py` | Granger 15/15 sig; pre-trends FAIL (−5.9) |
| Variance decomposition | `tools/cgmencode/exp_variance_decomp_2697.py` | ICC=0.019; 84% stochastic; 21/21 negative β |
| 18-panel visualizations | `visualizations/{causal-psm,impulse-response,variance-decomposition}/` | Complete causal analysis |

**EXP-2695: Propensity Score Matching — Controller compensates ~90%**
- 47,045 matched pairs (caliper=0.05, exact BG band match)
- ATT: −11.8 (30m) → −8.0 (60m) → −4.0 (90m) → −1.2 (120m)
- Channel substitution: user bolus → +1.46U SMB, −1.29U basal → net +0.17U
- ROC still imbalanced after matching (SMD=0.141) — residual confounding

**EXP-2696: Impulse Response — Granger yes, pre-trends fail**
- Local Projection: peak −1.63 mg/dL/U at 105 min
- Granger causality: 15/15 patients significant (insulin precedes BG change)
- Falsification FAILS: pre-event β = −5.9 (users bolus in anticipation)
- Cross-correlation: BG→insulin (reactive) stronger than insulin→BG (causal)

**EXP-2697: Variance Decomposition — 84% stochastic**
- Between-patient: 1.9%, Between-day: 14.2%, Within-day residual: 83.9%
- All 21 patients have negative bolus coefficients (confounding within patients too)
- Settings barely change (ISF range=0.1); no natural experiment power
- Hierarchical R²: event=0.296, day=0.164, patient=0.276, TIR=0.702

**Causal identification conclusion (27 experiments)**:
Standard econometric methods (regression, PSM, local projection, Granger)
CANNOT isolate causal treatment effects from observational closed-loop AID data.
The controller's simultaneous co-intervention, unobserved predictions, and
anticipatory user behavior create irreducible confounding. Structural PK/PD models,
instrumental variables, or controller open-loop periods would be needed.
