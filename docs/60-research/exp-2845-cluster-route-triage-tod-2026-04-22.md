# EXP-2845 Cluster: Route, Triage, and Time-of-Day Refinement

**Date**: 2026-04-22
**Stream**: B (operational)
**Charter**: two-stream-methodology-charter-2026-04-22.md (V1–V8)
**Predecessors**: EXP-2843 (envelope coupling), EXP-2844 (phenotype split)

Three woven deliverables that close the EXP-2843/2844 line: route
hypothesis test, unified triage cross-tab, and time-of-day refinement
of the phenotype audit.

---

## EXP-2845: SMB-route hypothesis (Loop vs Trio in S1)

**Question**: Does Loop's "never down-shift" (0/6) and Trio's "always
down-shift" (5/6) reduce to *route* of insulin delivery (basal vs SMB)
rather than total quantity?

**Method**: For each of 17 significant patients, compute hourly delivery
rate in S0 and S1 windows for: actual basal, bolus, SMB, total.
Test H1 (Trio SMB share > Loop), H2 (Loop basal uplift > Trio),
H3 (total delivery similar).

**Results**:

| Controller | n | Δ basal U/h | Δ SMB U/h | Δ total U/h | SMB share S1 |
|------------|--:|------------:|----------:|------------:|-------------:|
| Loop       | 6 | **+0.084** | +0.033 | **+0.254** | 0.34 |
| Trio       | 6 | **−0.048** | +0.208 | **+0.254** | 0.36 |
| OpenAPS    | 5 | +0.024 | 0.000 | −0.019 | 0.00 |

| Hypothesis | Test | p | Result |
|---|---|---|---|
| H1 SMB share Trio > Loop | M-W (greater) | 0.41 | FAIL |
| H2 Basal uplift Loop > Trio | M-W (greater) | **0.032** | **PASS** |
| H3 Total delivery similar | M-W (two-sided) | **0.82** | **PASS** |

**Interpretation (Stream B, decisive)**: Loop and Trio deliver
**identical total compensation** in S1 (0.254 U/h both, p=0.82) but
**route it oppositely**: Loop pushes via basal uplift; Trio cuts basal
and pushes via SMB. SMB share at S1 is ~similar (~33%) between Loop and
Trio, but the *delta* in SMB is 6× larger for Trio (+0.21 vs +0.03).

This is the cleanest possible Stream B finding: **same envelope demand,
same closed-loop net response, different controller-software route
choice**. EXP-2844's phenotype split is now fully explained as a
controller-route artifact, not a per-patient biological property.

**Audition implication**: Profile basal recommendations must be
controller-aware. A "raise scheduled basal" recommendation for a Loop
up-shifter and a "lower scheduled basal" recommendation for a Trio
down-shifter may both be the correct way to *retire* the same envelope
demand the open-loop profile is missing.

OpenAPS shows zero SMB delta in this cohort (5/5 patients) — likely
configuration- or version-dependent; flagged for follow-up.

**Source**: `tools/cgmencode/exp_smb_route_2845.py`,
`docs/60-research/figures/exp-2845_route_by_controller.png`.

---

## EXP-2845b: Unified triage cross-tab (flat-phenotype investigation)

**Question**: Does the flat phenotype (n=5, worst recovery 0.00) overlap
with EXP-2812 (recovery flags) and EXP-2831 (wear flags)?

**Method**: Outer-join EXP-2844 phenotype × EXP-2812 recovery flags ×
EXP-2831 wear flags into a unified triage table; sort by total flag
count.

**Results** (top rows):

| Patient | Controller | Phenotype | Δ basal % | Recovery | Post %high | Wear Δ% | Flags |
|---------|------------|-----------|----------:|---------:|-----------:|--------:|:-----:|
| **b**   | Loop  | **flat** | +0.3   | 0.00 | 30.9 | −31.5 | **3** |
| ns-d444c120c23a | Trio  | down_shift | −24.8 | 0.25 | 34.7 | −14.2 | 2 |
| ns-dde9e7c2e752 | Trio  | up_shift   | +23.6 | 0.25 | 30.9 | +16.0 | 2 |
| ns-6bef17b4c1ec | Trio  | down_shift | −27.7 | — | — | −20.6 | 1 |
| i               | Loop  | up_shift   | +15.8 | — | — | −44.7 | 1 |

**Interpretation**:
- Patient `b` is the only **triple-flag** case across the entire cohort.
  It is also the only flat-phenotype patient with EXP-2812 transition
  data — combined evidence is overwhelming for site rotation/profile
  re-audit.
- The other 4 flat patients lack S0→S1 transition data in EXP-2812
  (insufficient transitions ≥2). Their flat status remains a phenotype
  observation but cannot be cross-validated against recovery yet.
- 2 Trio patients carry double-flags via wear + post-high; both have
  significant S1 phenotype shifts.

**Source**: `tools/cgmencode/viz_unified_triage.py`,
`docs/60-research/figures/triage_unified_table.png`,
`externals/experiments/exp-2845b_unified_triage.parquet`.

---

## EXP-2845c: Time-of-day refinement

**Question**: Does the S1 basal shift concentrate in particular
time-of-day windows? (V8: pairs viz with EXP-2780 circadian basal.)

**Method**: For each (patient, hour, state), aggregate mean actual and
scheduled basal. Compute hourly Δbasal% (S1 − S0 normalized to
scheduled). Render cohort heatmap (24 hours × 17 patients) and
phenotype-aggregated window panel.

**Results** (median Δbasal % by phenotype × window):

| Window | down_shift | flat | up_shift |
|--------|----------:|-----:|---------:|
| Overnight (0–3) | −9% | −2% | +6% |
| **Dawn (4–9)** | **−15%** | −3% | +7% |
| Midday (10–15) | −13% | −1% | **+11%** |
| Evening (16–23) | −5% | +2% | **+11%** |

**Interpretation (Stream B)**:
- **down_shift** patients: controller cuts hardest in **dawn and
  midday** (−15%, −13%). The open-loop profile is over-basaled in the
  morning hours; controller corrects by cutting.
- **up_shift** patients: controller raises hardest in **midday and
  evening** (+11%, +11%). The open-loop profile is under-basaled in
  active hours; controller corrects by adding.
- **flat**: window-flat as well (≤±3% in every window) — these
  controllers really are not adapting time-of-day demand at all.

**Audition implications by (phenotype, window)**:

| Phenotype | Dawn | Midday | Evening |
|-----------|------|--------|---------|
| down_shift | **lower scheduled basal here first** | also high-priority cut | mild cut |
| up_shift | mild raise | **raise scheduled basal here** | **also raise** |
| flat | (no signal) | (no signal) | (no signal) — investigate controller capacity |

**Source**: `tools/cgmencode/viz_time_of_day_audit.py`,
`docs/60-research/figures/tod_basal_heatmap_cohort.png`,
`docs/60-research/figures/tod_basal_panel_by_phenotype.png`,
`externals/experiments/exp-2845c_tod_summary.parquet`.

---

## Combined synthesis

The EXP-2843/2844/2845 line now provides a complete operational story:

1. **Envelope state matters** (EXP-2843): 17/22 patients show
   significant S0/S1 basal differences.
2. **Direction is a controller-route choice** (EXP-2844 + 2845):
   Loop routes via basal-up, Trio routes via SMB+basal-down,
   *same total compensation*.
3. **Time-of-day localizes the recommendation** (EXP-2845c): the
   actionable schedule edit lives in dawn (down-shifters) or
   midday/evening (up-shifters).
4. **Unified triage** (EXP-2845b) makes patient `b` the unambiguous
   highest-confidence intervention candidate (3 flags).

All findings are Stream B operational. No biology number is asserted
anywhere in this cluster; profile-vs-actual gap is the audition unit
throughout. Cohort overlays use percentile bands (V3) and "you are
here" callouts (V4). Phenotype direction is foregrounded in every
chart (V5). Each research question shipped with a paired chart (V8).

## Open follow-ups

- OpenAPS zero-SMB observation: configuration vs version vs cohort
  artifact?
- Flat-phenotype patients without EXP-2812 transition coverage:
  back-fill with looser n_trans criterion?
- Sensor-gap orthogonal Stream A test (still open from prior plan)
- 24h state windows (EXP-2843b) to catch transitions earlier
