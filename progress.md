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

