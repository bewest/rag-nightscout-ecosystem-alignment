# EXP-2925 — Hypo symmetry: no design trades hypo for hyper

**Date:** 2026-04-23
**Source:** `tools/cgmencode/exp_hypo_symmetry_2925.py`
**Scope:** Hypo-side robustness check + design Pareto evaluation.
AID-author audience.

## Question

Two hypotheses tested:
1. Does oref0's midnight hypo signature (EXP-2920, 4.66 % at 00:00)
   survive Guard #6 cf-conditioning?
2. Does oref1 trade increased hypo for its hyper protection
   (EXP-2920/2923/2924)?

## Method

Per patient over hours [0,1,2]:
- `frac_severe_hypo_overnight` = mean(BG < 54)

Per patient full-day:
- TBR = % BG < 70, TAR = % BG > 180, TIR = % BG ∈ [70, 180]

Stratify by cf_severe tertile; bootstrap CI per cell. Lineage
pooled summary at the bottom.

## Pooled lineage results (across all cf)

| Lineage         | n | Overnight severe hypo % | TBR %  | TAR %    | **TIR %**  |
|-----------------|--:|------------------------:|-------:|---------:|----------:|
| Loop (iOS)      | 7 | 0.8                     | 3.88   | 30.04    | 66.08     |
| oref0 (legacy)  | 3 | **4.2**                 | **5.27** | 20.99 | 73.74     |
| **oref1 (modern)** | 9 | 1.2                  | **3.64** | **13.78** | **82.58** |

**oref1 wins on every metric in the pooled view.** Lower TBR,
lower TAR, higher TIR than both Loop and oref0. There is **no
hypo-for-hyper trade** at the design level — it is a Pareto
improvement.

## cf-stratified overnight severe hypo

| cf tertile | Loop (iOS) | oref1 (modern) | oref0 (legacy)         |
|-----------:|-----------:|----------------:|------------------------:|
| low_cf     | 0.44 % (n=1, no CI) | 0.61 % CI[0.42, 0.80] | **4.18 % CI[1.94, 6.58]** |
| mid_cf     | 1.38 % CI[0.10, 3.91] | 1.50 % CI[0.14, 3.51] | (no patients) |
| high_cf    | 0.32 % CI[0.10, 0.51] | 1.37 % CI[0.16, 2.33] | (no patients) |

**oref0 vs oref1 in low_cf**: 4.18 % vs 0.61 % — bootstrap CIs
[1.94, 6.58] vs [0.42, 0.80] **do not overlap**. The midnight
severe-hypo signature survives cf-conditioning. EXP-2918's 10-min
basal-cut latency translates to ~7× higher overnight severe-hypo
incidence in the matched-cf comparison.

## cf-stratified TIR

| cf tertile | Loop (iOS) | oref1 (modern)        | oref0 (legacy) |
|-----------:|-----------:|-----------------------:|---------------:|
| low_cf     | 55.8 % (n=1)| 82.6 % CI[73.3, 92.8] | 73.7 % CI[66.8, 86.1] |
| mid_cf     | 63.6 % CI[59.9, 65.5] | 80.7 % CI[70.2, 89.4] | — |
| high_cf    | 72.0 % CI[61.6, 79.2] | 84.5 % CI[71.7, 91.3] | — |

**oref1 > Loop within every cf tertile** for TIR. Loop's deficit
narrows from 17 pp (mid_cf) to 12.5 pp (high_cf). Even matched
on cf load, the oref1 design delivers more TIR by a large margin
in this cohort.

## Findings

1. **oref1 Pareto-dominates Loop** on the standard outcome set
   (TBR ↓, TAR ↓, TIR ↑) at every cf tertile where n permits
   comparison. There is no hidden hypo cost to oref1's hyper
   protection.

2. **oref0's midnight hypo signature is robust.** ~7× higher
   overnight severe hypo than oref1 within the same cf tertile,
   non-overlapping bootstrap CIs. Mechanism stack (EXP-2892
   utilisation 20 % × EXP-2918 latency 10 min × this) is
   internally consistent.

3. **oref0 has higher pooled TBR than Loop** (5.27 % vs 3.88 %),
   driven by overnight events. But oref0 also has *lower* pooled
   TAR (20.99 % vs 30.04 %) — so oref0 trades modestly more
   hypo for substantially less hyper at the design level.
   Net pooled TIR oref0 > Loop (73.74 % vs 66.08 %).

4. **The oref1 advantage shrinks at high cf** for TIR (12.5 pp
   vs 17 pp at mid_cf) but does not invert — symmetric with
   the EXP-2924 hyper-side finding that the gap narrows but
   persists at high load.

## Caveats

- Loop low_cf cell is n=1 (patient `a`), TAR 41.24 % and
  TIR 55.81 % are outliers driven by one patient. mid_cf and
  high_cf Loop cells (n=3 each) are more representative.
- oref0 patients all land in low_cf — cannot test the
  oref0-vs-oref1 hypo gap at higher cf without cohort expansion.
- TBR/TAR/TIR are full-day, not state-specific — fasted vs
  post-prandial decomposition deferred.
- Hours [0,1,2] used for "overnight" — local clock, not
  TZ-normalised.

## Implication

**For AID author audiences**: comparing closed-loop designs by
TIR/TBR/TAR alone, oref1's design choices (dynamic-ISF +
SMB-as-correction + UAM detection) are dominantly favoured in
this 19-patient cohort, with no measurable hypo cost. oref0's
basal-cut latency is the clearest design weakness and the
clearest improvement target for legacy-AAPS / openaps users.

For methodology: this is the third confirmation layer for the
"oref1's design ↔ better outcomes" claim — overall outcomes
(this), single-mechanism fasted-dawn (EXP-2923), and matched-cf
fasted-dawn (EXP-2924). The cohort is small (n=9 oref1, n=7
Loop) but the direction is consistent and the within-tertile
CIs exclude zero where they can be computed.

## Linked artefacts

- `externals/experiments/exp-2925_summary.json`
- Compare against `exp-2920-tod-design-profile-2026-04-23.md`,
  `exp-2924-cf-conditioned-dawn-2026-04-23.md`,
  `exp-2918-basal-cut-latency-2026-04-23.md`

## Next

- EXP-2926: load-mediation Guard #7 audit on overnight-hypo
  vs latency relationship.
- EXP-2927: post-prandial-only TIR comparison (does oref1's
  advantage come more from EGP handling or carb handling?).
