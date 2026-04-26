# EXP-3012 — Per-patient (T*, M*) recommendation (2026-04-26)

**Branch**: `main` (post-Phase-2 merge)
**Code**: `tools/cgmencode/autoresearch_cf/exp_3012_per_patient.py`
**Inputs**: `externals/experiments/exp-3007_ascent_events.parquet`
**Extends**: EXP-3011 (per-controller frontier → per-patient frontier)

## Method
Same 6 × 5 (T, M) grid as EXP-3011 with EXP-3010's corrected hypo accounting, evaluated **per patient** (n=31, 29 with ≥30 events). Recommendation = max overshoot reduction subject to Δhypo ≤ 1 pp from the patient's own baseline.

## Headline findings

### 1. Almost everyone has a Pareto improvement available

| Outcome | Count |
|---|---:|
| Patients with Pareto improvement (Δoversht < 0, Δhypo ≤ 1pp) | **21 / 29** |
| Patients already at optimum (T=0, M=1) | 0 |
| Patients with measurable headroom (Δoversht ≤ −1 pp) | 18 / 29 |

### 2. Patient heterogeneity dominates controller identity

```
η²(controller → benefit) = 0.268
```

Between-controller variance explains only **27 %** of per-patient benefit-magnitude variance — patient-level effects are 2.7× larger than controller-level effects. The Phase 2 controller-level recommendation is robust on average but masks substantial within-controller variation.

### 3. Recommendation distribution is multimodal

| Recommended (T*, M*) | n patients | Interpretation |
|---|---:|---|
| **T=30, M=0.5** | **13 (45%)** | Phase 2 modal recommendation |
| **T=0, M=0.5** | **8 (28%)** | Magnitude-down only — already-late patients |
| T=20, M=1.0 | 3 | Modest earlier-firing, current magnitude |
| T=15, M=1.0 | 2 | Even gentler timing-only shift |
| Other singletons | 3 | — |

The 8 patients wanting `M=0.5` with `T=0` are interesting: shifting earlier *worsens* their hypo more than it helps overshoot, so the optimal lever is purely magnitude reduction. These patients likely fire SMB earlier in the ascent already (Trio-flavoured even within Loop); pulling earlier wouldn't help.

### 4. Per-controller summary

| Controller | n | mean Δoversht | std | mean T* | mean M* |
|---|---:|---:|---:|---:|---:|
| Trio    | 9 | **−3.08 pp** | 0.89 | **27.8 min** | **0.61** |
| Loop    | 8 | −2.29 pp | 1.75 | 18.1 min | 0.69 |
| AAPS-oref0 | 5 | −0.25 pp | 0.50 | 4.0 min | 0.50 |
| (unlbl) | 7 | −2.67 pp | 2.45 | 17.9 min | 0.64 |

- **Trio** patients have the largest *and* most uniform unrealised benefit (std=0.89). Phase 2 recommendation T=30, M=0.5 fits well.
- **Loop** patients are more heterogeneous (std=1.75 — 2× Trio's). Mean T*=18 min suggests Loop's controller-level T=30 is too aggressive for half the cohort.
- **AAPS-oref0** patients have negligible benefit available (no SMB to redistribute) and mean T* near 0 — confirms the "switch to oref1" recommendation as the only real lever.

## Top-5 patients with largest unrealised benefit

| Patient | Controller | T* | M* | Δoversht | Δhypo |
|---|---|---:|---:|---:|---:|
| odc-39819048      | (unlabeled / AAPS) | 30 | 0.5 | **−7.14 pp** | −5.36 pp |
| `d`               | Loop | 30 | **1.0** | **−5.59 pp** | +0.19 pp |
| ns-8ffa739b986b   | (unlabeled) | 30 | 0.5 | −4.93 pp | −35.03 pp |
| ns-6bef17b4c1ec   | Trio | 30 | 0.5 | −4.40 pp | −8.65 pp |
| ns-9b9a6a874e51   | Trio | 20 | 1.0 | −4.21 pp | +0.64 pp |

Patient `d` is interesting — the only top-5 patient with `M*=1.0` (don't shrink magnitude). This says `d`'s overshoot is timing-bound more than magnitude-bound; firing earlier alone fixes it. Stored memory notes Patient `g` (Loop_AB_ON, mid-conservatism) is a *sweet-spot*; `d` shares Loop_AB_ON membership but is in the *largest-headroom* group, not the sweet-spot.

## Implications for autoresearch fitness

The v2 score function in `cf_replay_score_v2.py` currently uses a single `--smb-multiplier` knob applied uniformly. This experiment shows that **a single knob is wrong**: 28 % of patients want a different shape (T=0, M=0.5) than the cohort modal (T=30, M=0.5). For meaningful per-patient tuning, the score function should accept (T, M) jointly *and* operate on the per-patient sub-cohort.

Action item logged for follow-up: extend `cf_replay_score_v2.py` to accept `--per-patient` mode that applies (T*, M*) from the EXP-3012 parquet rather than uniform.

## Verdict
**`per_patient_heterogeneity_substantial`** — Phase 2 controller-level recommendation is correct directionally (cohort gain ≈ −2.5 pp overshoot, −3 pp hypo) but lossy at patient resolution. 28 % of patients are mis-served by the controller-level recommendation; per-patient mode is needed for clinical/individual deployment.

## Deliverables
```
tools/cgmencode/autoresearch_cf/exp_3012_per_patient.py
externals/experiments/exp-3012_per_patient.parquet      (gitignored)
externals/experiments/exp-3012_grid.parquet             (gitignored)
externals/experiments/exp-3012_summary.json             (gitignored)
docs/60-research/figures/exp-3012_per_patient.png
```
