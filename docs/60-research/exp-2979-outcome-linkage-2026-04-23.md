# EXP-2979 — Outcome linkage: Loop magnitude vs oref1 frequency lever

**Date**: 2026-04-23
**Audience**: Open-source AID code authors
**Scope**: Post-event outcomes (time-to-target, overshoot,
hypo-entry) for SMB-firing events in BG ∈ [70, 100), rising
velocity > 0.5 mg/dL/min, no recent carbs. Compares
Loop_AB_ON vs oref1 (= Trio).
**What this is NOT**: a TIR study; not a per-patient therapy
recommendation; not a head-to-head clinical comparison.

## Question

EXP-2972/2973 showed Loop and oref1 use **complementary mechanisms**
to dose SMBs in this sweet spot:

- Loop: per-event MAGNITUDE lever (large boluses, low frequency)
- oref1: emission FREQUENCY lever (small boluses, high frequency)

Do these mechanisms produce **different outcomes**?

## Result — MIXED / DIRECTIONAL POSITIVE (with caveat)

Pooled metrics (1,253 qualifying events across both designs):

| Design     | n events | smb median | TTT median (cens.) | overshoot 180 (60min) | hypo 70 (60min) |
|------------|---------:|-----------:|--------------------:|----------------------:|----------------:|
| Loop_AB_ON |      363 |  **0.40 U** | **10 min** (cens 0.30) | **10.7%**            | 12.7% |
| oref1      |      890 |  0.15 U     | 15 min (cens 0.43)  | 3.5%                 | 18.4% |

**Directional finding**: Loop's magnitude lever returns BG to
target ~5 min faster (10 vs 15 min median) but produces ~3×
higher overshoot (10.7% vs 3.5%). oref1's frequency lever is
slower-but-flatter, with marginally higher hypo-entry (18.4% vs
12.7%). This is **consistent with the mechanism prediction**: a
single large dose punches through to target faster but creates
overshoot risk; many small doses titrate gradually with less
overshoot but accumulate IOB that occasionally triggers hypo.

## Critical caveat — sample structure

In this rising-stratum 70-100 sweet spot, **only patient `i`**
contributes Loop_AB_ON events (361 of 363). Patients c/d/e/g
contribute 0–1 events each (they fire SMB elsewhere; in this
sweet-spot stratum they essentially do not). This means:

1. The Loop pooled outcomes are effectively a **single-patient
   estimate**.
2. Per-patient MWU between Loop_AB_ON and oref1 cannot be run
   (need n ≥ 3 per group, only 1 Loop patient passes threshold).
3. The directional finding is **internally consistent with the
   mechanism prediction**, but external validity to other Loop
   patients is unverified in this dataset.

| Patient (kept n ≥ 3) | design | n events | smb med (U) | TTT med | overshoot | hypo |
|----------------------|--------|---------:|------------:|--------:|----------:|-----:|
| i                    | Loop_AB_ON |   361 | 0.400 |  10 min | 10.5% | 12.5% |
| ns-1ccae8a375b9      | oref1     |   118 | 0.150 |  15 min |  3.4% | 11.9% |
| ns-6bef17b4c1ec      | oref1     |   108 | 0.138 |  10 min |  0.0% |  1.9% |
| ns-8b3c1b50793c      | oref1     |    10 | 0.725 |  42 min |  0.0% |  0.0% |
| ns-8f3527d1ee40      | oref1     |    79 | 0.350 |  15 min |  2.5% | 16.5% |
| ns-9b9a6a874e51      | oref1     |    23 | 0.050 |  15 min |  8.7% |  4.3% |
| ns-a9ce2317bead      | oref1     |   295 | 0.150 |  40 min |  2.4% | 32.2% |
| ns-adde5f4af7ca      | oref1     |   191 | 0.150 |  10 min |  6.8% |  8.4% |
| ns-d444c120c23a      | oref1     |    58 | 0.250 |  10 min |  5.2% | 32.8% |
| ns-dde9e7c2e752      | oref1     |     8 | 0.125 |  22 min |  0.0% | 50.0% |

oref1 patients show wide hypo-entry spread (0% – 50%); the higher
pooled hypo rate is patient-driven (a9ce, d444, dde9) not a
systemic frequency-lever artifact.

## Verdict

**MIXED-DIRECTIONAL POSITIVE.** The mechanism difference is
mirrored in pooled outcomes — Loop's magnitude lever is faster but
overshoots more; oref1's frequency lever is slower but tighter on
overshoot. **The Loop arm is essentially a single-patient
estimate in this stratum**, so the verdict is not statistically
generalizable. The DIRECTION matches mechanism prediction, which
is the cleanest evidence we can extract from this cohort.

## Implication for AID authors

If accepted as directional-only:

- **Magnitude-lever AIDs** should consider an **overshoot governor**
  (e.g., post-SMB cool-down, or a prediction-aware sizing cap when
  the projected post-SMB BG > 180).
- **Frequency-lever AIDs** should consider an **IOB-stacking
  governor** at sustained corrections — the small-frequent pattern
  can accumulate into hypo when the cohort scatter (0% – 50% hypo)
  shows individual-patient sensitivity to over-titration.

Both implications match Lever 1 (settings discipline) and Lever 3
(meal-state-aware shaping) priorities; they do not rewrite the
lever order but they suggest **per-mechanism guard-rails** rather
than identical guard-rails for both designs.

## Source / data

- Script: `tools/cgmencode/exp_outcome_linkage_2979.py`
- Output: `externals/experiments/exp-2979_summary.json`
- Cohort: `exp-2891_simpson_dose_response.parquet`
- Filters: BG ∈ [70, 100), velocity > 0.5 mg/dL/min, no carbs in
  prior 120 min, look-ahead 120 min, target 100 sustained 30 min.
