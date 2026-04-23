# EXP-2913 — HAAF-adjacent blunting investigation

**Date:** 2026-04-23 (overnight)
**Source:** `tools/cgmencode/exp_haaf_blunting_2913.py`
**Status:** **HAAF interpretation NOT supported.** The EXP-2912
sub-finding (negative ρ(cf, intercept) in Loop −0.56 / oref1 −0.20)
is driven by potential-load (cf) correlation, NOT by actual
experienced hypo exposure after AID coverage. Sub-finding withdrawn.

## Question

EXP-2912 found ρ(cf_severe, counter_reg_intercept) negative in two
lineages. Candidate interpretation: HAAF (hypoglycemia-associated
autonomic failure / counter-reg blunting from chronic exposure).
Could chronically high-load patients have biologically blunted
recovery?

## Method

For each patient compute three exposure metrics from EXP-2891 and
correlate with EXP-2875 counter_reg intercept:

| Metric | Meaning |
|--------|---------|
| `cf_severe` | Counter-factual severe-event rate WITHOUT AID (potential load) |
| `aid_protection_severe` | Fraction of cf-events the AID prevented |
| `true_exposure_rate = cf × (1 − protection)` | Actual experienced severe hypo (post-AID) |

True biological HAAF should correlate with **actual** experienced
hypos (true_exposure), not potential load (cf). If EXP-2912's
negative rho strengthens under true_exposure, HAAF is supported;
if it weakens or flips sign, the EXP-2912 finding was a load-coverage
correlation artifact.

Bootstrap 1 000 resamples per (lineage, metric) for CIs.

## Results

| Lineage         | n | ρ(cf, intercept) | ρ(true_exposure, intercept) | Verdict             |
|-----------------|--:|-----------------:|----------------------------:|---------------------|
| Loop (iOS)      | 7 | **−0.60**        | **−0.10**                   | weakened — no HAAF  |
| oref1 (modern)  | 9 | **−0.27**        | **+0.39 (sign flip)**       | reversed — no HAAF  |
| oref0 (legacy)  | 3 | −0.27            | −0.48                       | n=3, inconclusive   |

All bootstrap 95 % CIs include zero. None of the rho's are
statistically distinguishable from noise at this cohort size.

The qualitative pattern is decisive: the EXP-2912 negative
ρ(cf, intercept) reflects how AID coverage is distributed across
the load distribution, NOT counter-reg blunting. The relationship
between actual experienced hypos and intercept is **null in Loop
and positive in oref1** (more hypos → faster recovery, consistent
with normal physiology — possibly trained physiology / no blunting).

## Mechanism (why the sign flipped in oref1)

In oref1 (best-protected design), high-cf patients have low
true_exposure because protection ~63–72 %. So ρ(cf, intercept) and
ρ(true_exposure, intercept) measure orthogonal things:
- ρ(cf, ·): "do high-load patients have lower intercept?"
- ρ(true_exposure, ·): "do patients with more actual hypos have
  lower intercept?"

The first picks up load-related selection or measurement; the
second picks up biology. They give opposite answers in oref1.

## Withdrawal of EXP-2912 sub-finding

Update the deconfounding-toolkit guidance: when correlating
**outcomes** with **load** in AID data, AID protection mediates
the link. Substituting `true_exposure = cf × (1 − protection)`
for cf is the minimum correction. EXP-2912 negative ρ(cf, intercept)
should not be cited as HAAF evidence going forward.

## Takeaway for the deconfounding toolkit

New §2.11 candidate: **AID protection is a mediator between load
proxies and physiology outcomes.** Any cross-sectional correlation
of `cf_*` with downstream physiological markers must be re-tested
with `true_exposure_rate = cf × (1 − protection)` before claiming
biological causation. The default-guard equivalent: **Guard #7
(load-mediation guard)** — companion to Guard #6 (cf-conditioning).

(Wiring of Guard #7 deferred to a follow-up doc edit.)

## Caveats

- Cross-sectional only; cannot establish or refute HAAF causally.
  HAAF requires longitudinal exposure-then-blunting timecourse data
  unavailable in this cohort.
- n=3 oref0; cannot conclude either way for legacy design.
- Counter_reg intercept is itself a noisy patient-level estimate
  (EXP-2875 R² is low for many patients).
- True biological HAAF blunting in this T1D AID population would
  benefit from a clinical-grade autonomic test, not closed-loop
  inference.

## What this rules out

- HAAF blunting as a cohort-level explanation for EXP-2912 negative
  ρ(cf, intercept).
- The need to add patient-level "HAAF risk" audition flags from
  this cohort.

## What this does NOT rule out

- Individual-patient HAAF (would require longitudinal data).
- HAAF in larger or longer-exposure cohorts.
- Other mediators of (load → physiology) — exercise, glucagon
  reserves, autonomic neuropathy stage.

## Linked artefacts

- `externals/experiments/exp-2913_summary.json`
- `externals/experiments/exp-2913_haaf_blunting.parquet`
- `docs/60-research/exp-2912-cf-conditioned-counter-reg-2026-04-23.md` (parent)
- `docs/60-research/deconfounding-toolkit-2026-04-22.md` (Guard #7 candidate)

## Next

- Add Guard #7 (load-mediation) to deconfounding toolkit
- Continue to EXP-2917 (bootstrap design-cell CIs) per plan
