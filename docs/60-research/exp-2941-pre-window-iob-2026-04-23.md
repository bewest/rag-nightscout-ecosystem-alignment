# EXP-2941 — Pre-window IOB-proxy test (refuted)

**Date:** 2026-04-23
**Status:** Closed
**Scope:** Design-feature characterisation for open-source AID author
audience. NOT therapy advice.

## Question

EXP-2940 narrowed the recovery mechanism to pre-window state.
Direct test: compute `prior_smb_3h` (sum of SMB units delivered in
the 3 hours before correction-window entry) as IOB proxy. Does:
1. oref1 enter windows with higher prior_smb_3h?
2. Within-design, higher prior_smb_3h predict better recovery?
3. Conditioning on prior_smb_3h tertile (Guard #8) collapse the gap?

## Method

Reuse EXP-2937 carb-isolated cohort (3 242 events). Compute
`prior_smb_3h`. Per-patient and per-event analyses; 2000-bootstrap
CIs.

## Results

### 1. Pre-window IOB-proxy by design

| design       | n_event | mean (U) | median | q25  | q75  |
|--------------|--------:|---------:|-------:|-----:|-----:|
| Loop_AB_OFF  |     564 |    0.000 |  0.000 | 0.00 | 0.00 |
| Loop_AB_ON   |    1437 |    2.864 |  2.500 | 1.40 | 4.10 |
| oref1        |    1241 |    2.846 |  2.450 | 1.15 | 3.90 |

Per-patient mean: oref1 3.072 U vs Loop_AB_ON 2.749 U.
Bootstrap diff +0.323 U  CI [−1.140, +1.712]  **not significant**.

**Loop and oref1 deliver essentially identical 3-hour pre-window SMB
sums.** Pre-event insulin context (as proxied by prior SMB) is the
same.

### 2. Within-design: does prior_smb_3h predict recovery?

| design        | prior_bin | n   | recovery_% | mean_prior |
|---------------|-----------|----:|-----------:|-----------:|
| Loop_AB_ON    | low       | 479 |      33.82 |       0.79 |
| Loop_AB_ON    | mid       | 479 |      35.28 |       2.56 |
| Loop_AB_ON    | high      | 479 |      36.53 |       5.24 |
| oref1         | low       | 416 |      50.72 |       0.74 |
| oref1         | mid       | 411 |      57.42 |       2.43 |
| oref1         | high      | 414 |      57.97 |       5.38 |

Within-design slope: Loop +2.7 pp (low→high), oref1 +7.3 pp.  Both
are weak; pre-window dose has only minor predictive power on
within-window recovery.

### 3. Recovery gap conditioned on prior_smb_3h (Guard #8)

| prior_bin   | gap     | 95 % CI               | sig |
|-------------|--------:|:---------------------:|-----|
| low_prior   | +0.225  | [+0.112, +0.351]      | ★   |
| mid_prior   | +0.228  | [+0.109, +0.356]      | ★   |
| high_prior  | +0.198  | [+0.062, +0.333]      | ★   |

**The +21 pp recovery gap is essentially constant across pre-window
IOB-proxy tertiles.** Conditioning on pre-event SMB context does NOT
collapse the design gap.

### Distribution sanity-check

| design       | low_prior | mid_prior | high_prior |
|--------------|----------:|----------:|-----------:|
| Loop_AB_OFF  |    100.0  |       0.0 |        0.0 |
| Loop_AB_ON   |     18.2  |      39.9 |       41.9 |
| oref1        |     20.9  |      40.5 |       38.6 |

Loop and oref1 distributions across prior tertiles are nearly
identical. Loop_AB_OFF predictably 100 % low (delivers no SMBs).

## Mechanism map after EXP-2941

| Candidate                          | EXP    | Status       |
|------------------------------------|--------|--------------|
| Within-window cadence              | 2937   | Refuted      |
| Within-window first-fire latency   | 2937   | Refuted      |
| Within-window total dose           | 2937   | Refuted      |
| Dose-to-velocity                   | 2938   | Refuted      |
| Dose-per-mgdl above target         | 2939   | Refuted      |
| Dynamic-ISF amplification slope    | 2939   | Refuted      |
| Within-window dose schedule shape  | 2940   | Refuted      |
| Pre-window SMB IOB proxy           | **2941** | **Refuted** |
| Basal-channel posture difference   | —      | Not measured |
| **Patient self-selection**         | —      | **Candidate** |
| Pre-event autosens calibration     | —      | Not directly measurable |

## Reckoning: selection bias must now be considered

After 8 mechanism candidates refuted, the most honest assessment is
that the +21 pp recovery gap may not be design-driven. The cohort is:

- 2 patients on Loop_AB_OFF
- 5 patients on Loop_AB_ON
- 9 patients on oref1

Patients who self-selected onto oref1 may differ systematically from
those on Loop:

- Insulin sensitivity (intrinsic ISF)
- Carb ratio adherence to settings
- Activity patterns
- Diet composition (slow-carb fraction, fat-protein delays)
- Day-night BG variability

If oref1 attracts more "engaged" or more insulin-sensitive patients,
**every observed advantage may be patient-level rather than design-
level.** EXP-2937 cited dose magnitude, EXP-2939 dose-per-mgdl, and
this experiment shows pre-event dose distribution: oref1 patients are
not behaviourally different in any of these. But intrinsic
metabolic sensitivity (which we cannot directly measure here) could
explain the residual gap.

This is NOT a refutation of the prior findings — the avoidance/
recovery decomposition (EXP-2934), the Pareto-dominance at four
granularities, and the constant recovery gap are all real *in this
cohort*. What's now unresolved is whether the recovery gap is
**caused by oref1's algorithmic choices** or by **the intrinsic
properties of patients who chose oref1**.

## Next experimental queue

1. **EXP-2942**: examine the oref0 (n=3) cohort against Loop and
   oref1. If oref0 (different algorithm family but same OpenAPS
   lineage) shows similar recovery to oref1, that supports the
   algorithm-family explanation. If oref0 looks like Loop, that
   supports the selection-bias explanation. Sample is tiny but it's
   the closest thing to natural variation.
2. **EXP-2943**: per-patient correction-effectiveness scatter — plot
   recovery_% vs mean basal rate, vs TDD/kg, vs BG variability.
   Look for patient-level covariates that explain within-design
   variance. If patient-level covariates explain most variance, the
   design effect is suspect.
3. **AAPS ingestion**: would expand oref0/oref1 cohort and break the
   2-vs-5-vs-9 imbalance.

## What this changes in the synthesis

The mechanism story for the recovery channel must be downgraded to:

> **Within this 19-patient cohort**, oref1 patients show a +21 pp
> sustained-high recovery advantage over Loop_AB_ON patients that
> cannot be attributed to within-window SMB cadence, latency, total
> dose, dose-magnitude scaling, dose-per-velocity, dose-per-mgdl,
> dose-schedule shape, or pre-window SMB context. Either:
> (a) the algorithmic difference acts through an unmeasured channel
>     (basal-cut intensity, internal autosens state),
> (b) patient self-selection produces a metabolic-cohort difference
>     that masquerades as a design effect, or
> (c) some combination of (a) and (b).
>
> AID-author guidance is downgraded from "tune correction-loop dose
> sizing" to "the correction-loop effectiveness gap measured here may
> not generalise; replication on a within-patient AID-switch dataset
> is needed before recommending design changes."

The avoidance channel (EXP-2934 high_lag distribution: oref1 24.8 %
vs Loop_AB_OFF 47 %) is more robust because it ties directly to the
EXP-2929/2930 PP dose-shape findings, which have a clear within-
window mechanism.

## Cross-reference

- EXP-2937–2940: serial elimination of within-window mechanisms
- EXP-2934: outcome decomposition (avoidance + recovery)
- Synthesis: synthesis-design-comparison-2026-04-23.md (needs update)
- Guard #8 applied at step 3 above

## Methodological lesson

When 8 sequential mechanism candidates fail to explain a real,
robust effect, the prior probability that the effect is confounded
by an unmeasured upstream variable rises substantially. Per-patient
self-selection is the single biggest such variable here, and the
research design (cohort, n=19) cannot rule it out. Future work
should prioritise within-patient AID-switch data over cross-cohort
comparisons.
