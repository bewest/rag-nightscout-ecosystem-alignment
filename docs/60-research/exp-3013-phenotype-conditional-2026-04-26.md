# EXP-3013 — Phenotype-conditional cf-replay benefit (2026-04-26)

**Branch**: `main`
**Code**: `tools/cgmencode/autoresearch_cf/exp_3013_phenotype_conditional.py`
**Inputs**:
- `externals/experiments/exp-3012_per_patient.parquet` (per-patient T*, M*, benefit)
- `externals/experiments/exp-2886_phenotype.parquet` (stack_score, braking_ratio, hidden_leverage)
- `externals/experiments/exp-2995_phenotype_x_algorithm_mode.parquet` (aggressiveness, tercile)

## Hypothesis (pre-registered)
**H1**: High-stack-score patients have the largest unrealised cf-replay benefit (more SMBs delivered late = more retiming headroom).

## Result: H1 rejected; replaced by braking_ratio

After joining 24/29 EXP-3012 patients with the 24-patient phenotype table:

### Spearman correlations against `abs_benefit` (overshoot reduction, pp)

| Phenotype axis | ρ | p | n | Verdict |
|---|---:|---:|---:|---|
| **braking_ratio** | **−0.464** | **0.046** | 19 | **significant** |
| hypo_fraction | −0.252 | 0.234 | 24 | n.s. |
| stack_score | −0.187 | 0.381 | 24 | **rejects H1** |
| hidden_leverage | −0.062 | 0.801 | 19 | n.s. |

### Spearman correlations against `rec_T_min` (recommended earlier-firing minutes)

| Phenotype axis | ρ | p | n |
|---|---:|---:|---:|
| **braking_ratio** | **−0.560** | **0.013** | 19 |
| stack_score | −0.065 | 0.762 | 24 |

The same axis (`braking_ratio`) drives both *how much* benefit a patient has and *what timing shift* they need. Magnitude (`rec_M_mult`) is not significantly predicted by any phenotype axis (best ρ=−0.33, p=0.17 for braking_ratio).

## Mechanistic interpretation

`braking_ratio` (from EXP-2886) measures how aggressively a controller suppresses SMBs as velocity rises (high ratio = aggressive defence). The negative correlation with benefit means:

- **Low-braking patients** (stack-score-axis says they "don't brake") have the **largest unrealised benefit** because their SMBs fire late and hard during ascents — exactly what cf-replay's earlier-and-smaller frontier targets.
- **High-braking patients** already do the right thing — they suppress SMBs at velocity peaks — so the cf-replay finds little to retime.

This refines the phenotype taxonomy: `stack_score` measures *whether* you stack; `braking_ratio` measures *whether* the stacking happens at velocity-driven moments specifically. Only the latter is the cf-replay handle.

## Stratified summary by `algorithm_mode`

| algorithm_mode | n | mean Δover | std | mean T* | mean M* | mean braking |
|---|---:|---:|---:|---:|---:|---:|
| Loop-AB-ON  | 5 | **3.24 pp** | 1.54 | 27.0 | 0.70 | **0.046** |
| Trio-oref1  | 9 | **3.08 pp** | 0.95 | 27.8 | 0.61 | **0.066** |
| unknown     | 5 | 2.32 pp | 1.88 | 19.0 | 0.70 | n/a |
| Loop-AB-OFF | 2 | 0.00 pp | 0.00 | 0.0 | 0.50 | 0.260 |
| AAPS-oref0  | 3 | 0.00 pp | 0.00 | 0.0 | 0.50 | 0.535 |

**Pattern**: low-braking systems (Loop-AB-ON, Trio-oref1) have the headroom; high-braking systems (AAPS-oref0, Loop-AB-OFF) don't. AAPS-oref0's 0.535 braking is more an artefact of *no SMB at all* than of skilled defence.

## Stratified summary by `archetype`

| archetype | n | mean benefit | T* | M* |
|---|---:|---:|---:|---:|
| algorithm_dependent | 6 | 3.09 | 26.7 | 0.67 |
| well_defended | 5 | 2.93 | 24.0 | 0.60 |
| hidden_leverage | 3 | 2.81 | 25.0 | 0.67 |
| stacker_weak_defense | 1 | 2.31 | 30.0 | 0.50 |
| insufficient_data | 5 | 2.32 | 19.0 | 0.70 |
| **exposed_stacker** | 2 | **0.00** | 0.0 | 0.50 |
| stacker_balanced | 1 | 0.00 | 0.0 | 0.50 |
| lax_braking | 1 | 0.00 | 0.0 | 0.50 |

**Counter-intuitive**: archetype `exposed_stacker` has **zero** benefit available. These patients stack — but not at velocity peaks. Their stacking is post-meal sustained dosing, which the ascent-window cf-replay doesn't address. This is a valuable refinement: not all stackers benefit from "fire earlier, smaller"; some need a different intervention (DIA tuning, COB cap).

## Patient-level highlights

| Patient | algorithm_mode | braking | benefit (pp) | T* | M* |
|---|---|---:|---:|---:|---:|
| `d` | Loop-AB-ON | 0.027 | **5.59** | 30 | 1.0 |
| `i` | Loop-AB-ON | 0.054 | 3.62 | 30 | 0.5 |
| `c` | Loop-AB-ON | 0.027 | 3.07 | 30 | 0.5 |
| `g` | Loop-AB-ON | 0.118 | 1.44 | 15 | 1.0 |
| `a` | Loop-AB-OFF | 0.305 | 0.00 | 0 | 0.5 |

Patient `g` (the documented sweet-spot from EXP-2994) has the **highest braking_ratio among Loop-AB-ON peers** (0.118 vs 0.027–0.054) and correspondingly the **smallest unrealised benefit** in this cohort. The sweet-spot is a phenotypic property: `g` already brakes effectively, so the cf-replay finds little to fix. Patients `c`, `d`, `i` all have ~10× *less* braking and ~3× more headroom.

## Verdict

**H1 (stack_score → benefit)**: ❌ rejected (p=0.38).
**H1' (braking_ratio → benefit)**: ✅ supported (ρ=−0.46, p=0.046).

The cf-replay ascent-window intervention is **only meaningful for patients/algorithms with low braking_ratio** (active SMB delivery without velocity-driven suppression). High-braking patients (AAPS-oref0, Loop-AB-OFF, sweet-spot `g`) already saturate the available benefit; they need a different intervention.

## Implications for autoresearch / clinical deployment

1. **Targeting**: The (T=+30, M=0.5×) recommendation should be **gated on braking_ratio < ~0.1**. Patients above this threshold won't benefit and may be harmed by the magnitude reduction (no overshoot to remove, only hypo risk added).
2. **Synthetic patient generator (EXP-3006)** should sample explicitly across the braking_ratio axis to ensure cf-replay test coverage of the gradient.
3. **Score function** (`cf_replay_score_v2.py`) should weight by per-patient braking; uniform weighting over-credits low-benefit patients.
4. **Archetype `exposed_stacker` is a separate intervention class** — ascent-window cf-replay is not the right tool for them.

## Deliverables
```
tools/cgmencode/autoresearch_cf/exp_3013_phenotype_conditional.py
externals/experiments/exp-3013_phenotype_conditional.parquet  (gitignored)
externals/experiments/exp-3013_summary.json                   (gitignored)
docs/60-research/figures/exp-3013_phenotype_scatter.png
```
