# Autonomous Auto-Research Plan

## Problem Statement

410+ experiments have established strong empirical foundations across glucose forecasting (MAE=10.41, near-CGM-grade), classification (UAM F1=0.971), and state tracking (ISF drift 9/11 patients). The research is at an inflection point:

- **7 production-ready** sub-use-cases (A1, A6, B1, B4-2h, C1, D1, D3)
- **6 designed-but-untested** strategic planning experiments (E1-E5, EXP-412-416)
- **Several high-probability untested combinations** of proven techniques
- **Missing validation**: most results lack multi-seed replication + held-out test

The question: **what autonomous research loops yield the highest ROI?**

## Approach: Three Parallel Research Tracks

### Track 1: CREDIBILITY (Validation & Replication)
_Goal: Establish publishable confidence intervals for all production claims_

The auto-research framework is 100% ready for 3/5 objectives. Zero existing experiments use it. This is the #1 blocker for any deployment or publication claim.

### Track 2: FORECASTING FRONTIER (h120-h360 PK Advantage Zone)
_Goal: Push transformer+PK into the under-explored extended horizon territory_

h60 is within 1% of CGM MARD — diminishing returns. h120-h360 has proven PK advantage (-10 to -17 MAE) but only with CNNs. The PKGroupedEncoder transformer has NEVER been tested there. This is the single highest expected-value experiment.

### Track 3: STRATEGIC PLANNING LAYER (E-series)  
_Goal: Fill the 6h-4d clinical gap that no product addresses_

The "treatment planning" layer between real-time AID (≤2h) and quarterly endo visits is completely unserved. E5 (weekly hotspots) and E1 (overnight risk) are the lowest-complexity, highest-clinical-impact entries.

---

## Prioritized Experiment Queue

### Phase 1: Foundation (Validation + Quick Wins)

| ID | Experiment | Track | Expected Impact | Effort | Auto-Runnable? |
|----|-----------|-------|-----------------|--------|----------------|
| P1-1 | Multi-seed replication: UAM (EXP-313-v2) | T1 | CI on F1=0.939 | Low | ✅ Yes |
| P1-2 | Multi-seed replication: Override (EXP-327-v2) | T1 | CI on F1=0.852 | Low | ✅ Yes |
| P1-3 | Multi-seed replication: Hypo (EXP-324-v2) | T1 | CI on F1=0.676 | Low | ✅ Yes |
| P1-4 | `run_validated_forecast()` wrapper | T1 | Unblocks forecast validation | Very Low | N/A (code) |
| P1-5 | Glucose derivative channels on champion | T2 | -0.5 to -1.5 MAE | Very Low | ✅ Yes |
| P1-6 | Cosine LR + warmup on champion | T2 | -0.3 to -0.8 MAE | Very Low | ✅ Yes |

### Phase 2: PK Advantage Zone (The Big Bet)

| ID | Experiment | Track | Expected Impact | Effort | Auto-Runnable? |
|----|-----------|-------|-----------------|--------|----------------|
| P2-1 | Future PK on PKGroupedEncoder w48 (EXP-411) | T2 | **-3 to -8 MAE at h120** | Low | ✅ Yes |
| P2-2 | History sweep: w48/w72/w96 for h120-h360 | T2 | -2 to -5 MAE at h120+ | Low | ✅ Yes |
| P2-3 | Horizon-weighted loss (upweight h60+) | T2 | -0.5 to -2 MAE at h60 | Low | ✅ Yes |
| P2-4 | Hard patient optimization (b, j, a) | T2 | -1 to -3 overall | Medium | Partially |

### Phase 3: Strategic Planning Layer (New Capability)

| ID | Experiment | Track | Expected Impact | Effort | Auto-Runnable? |
|----|-----------|-------|-----------------|--------|----------------|
| P3-1 | E5: Weekly routine hotspots (EXP-416) | T3 | **Lowest complexity, highest clinical ROI** | Low | ✅ Yes |
| P3-2 | E1: Overnight risk assessment (EXP-412) | T3 | Night TIR=60.1% is worst period | Medium | ✅ Yes |
| P3-3 | E7: Proactive meal scheduling | T3 | Leverages UAM F1=0.971 | Low | ✅ Yes |
| P3-4 | E2: Next-day TIR prediction (EXP-413) | T3 | Enables proactive planning | Medium | ✅ Yes |
| P3-5 | E4: Event recurrence (EXP-415) | T3 | "3 PM hypo cluster" detection | Medium | ✅ Yes |
| P3-6 | E8: Acute absorption degradation | T3 | PK residual monitoring | Medium | Partially |

### Phase 4: Advanced (After P1-P3 Results)

| ID | Experiment | Track | Expected Impact | Effort |
|----|-----------|-------|-----------------|--------|
| P4-1 | Dynamic ISF (circadian-varying) | T2 | -0.5 to -1 MAE | Medium |
| P4-2 | Encoder-decoder transformer | T2 | Unknown | High |
| P4-3 | E3: Multi-day control quality (EXP-414) | T3 | Trend monitoring | High |
| P4-4 | E9: Override→profile recommendation | T3 | Autotune for overrides | Medium |
| P4-5 | Stochastic future PK | T2 | Better calibration | High |

---

## Auto-Research Pipeline Design

### What "Autonomous" Means Here

Each experiment should be runnable with a single command like:
```bash
python tools/cgmencode/run_experiment.py --exp EXP-411 --seeds 5 --validate
```

The pipeline should:
1. Load data via `load_multiscale_data_3way()` (60/20/20 temporal split)
2. Train across 5 seeds (42, 123, 456, 789, 1337)
3. Run appropriate validator (Classification/Forecast/Retrieval/Drift)
4. Compute bootstrap CIs
5. Save structured JSON with `validation_metadata`
6. Compare against baseline automatically
7. Log results to experiment registry

### Infrastructure Needed

| Item | Status | Effort |
|------|--------|--------|
| `run_validated_classification()` | ✅ Ready | 0 |
| `run_validated_retrieval()` | ✅ Ready | 0 |
| `run_validated_forecast()` | ❌ Missing | ~30 min |
| `run_validated_drift()` | ❌ Missing | ~30 min |
| Experiment registry/comparator | ❌ Missing | ~2 hours |
| Auto-gating (pass/fail criteria) | ❌ Missing | ~1 hour |

### Continuous Loop Pattern

```
1. SELECT next experiment from priority queue
2. RUN experiment with validated pipeline
3. COMPARE against baseline + gate criteria
4. IF significant improvement:
     UPDATE champion, log finding, unlock dependent experiments
5. IF no improvement:
     LOG null result, remove from consideration
6. UPDATE priority queue based on new evidence
7. GOTO 1
```

### Gate Criteria for Each Track

**Track 1 (Credibility)**:
- Pass: CI excludes null hypothesis (e.g., UAM F1 > 0.90 at 95%)
- Pass: Test set within 5% of validation set

**Track 2 (Forecasting)**:
- Pass: Significant MAE reduction (> 0.5 at h120+)
- Pass: No regression at h30-h60

**Track 3 (Strategic)**:
- Pass: AUC > 0.70 for probabilistic predictions (E1, E4)
- Pass: Hotspot stability across weeks (E5)
- Pass: Platt-calibrated ECE < 0.05

---

## Key Hypotheses Ranked by Expected Value

1. **Future PK + PKGroupedEncoder is the single highest-value untested combination** — two proven techniques that have never been combined on the champion architecture. Expected: -3 to -8 MAE at h120.

2. **E5 (Weekly Hotspots) is the highest clinical-ROI strategic experiment** — pure descriptive analytics (no ML needed), reuses proven patterns, directly actionable for patients.

3. **Multi-seed validation will likely CONFIRM existing results** — the 5-seed consistency in EXP-410 (±0.16 MAE) suggests low variance. But CI establishment is mandatory for any deployment claim.

4. **E7 (Meal Scheduling) bridges detection to prevention** — UAM is solved (F1=0.971). Adding temporal clustering makes it proactive. This is the "killer app" transition from reactive to preventive.

5. **Longer history + PK resolves the DIA Valley** — EXP-353 proved the crossover at 4h. Transformer + PK at w96 should produce the best extended-horizon results ever seen in this workspace.

---

## Notes

- All Phase 1 experiments are independent → can run in parallel
- P2-1 (Future PK + transformer) is the single most important experiment
- P3-1 (Weekly hotspots) needs no ML — can be done with pandas + descriptive stats
- The experiment_lib.py infrastructure is solid; main gap is the forecast wrapper
- GPU budget: ~12 GPU-hours for Phase 1, ~20 for Phase 2, ~15 for Phase 3
