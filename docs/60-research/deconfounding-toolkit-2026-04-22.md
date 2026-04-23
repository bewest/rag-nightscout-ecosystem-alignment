# Deconfounding Toolkit for AID / CGM Research

**Date:** 2026-04-22
**Purpose:** Composing techniques to combat counter-causal
reasoning at different timescales for different problem classes.

## Why this document exists

In AID / CGM data, almost every interesting quantity is
*confounded by the system's own behavior*.  The controller
intervenes on the very variables we want to learn about, and
patients self-select settings based on observed outcomes.  Naïve
correlation and regression routinely yield **reversed-sign** or
**zero-effect** results that look like null hypotheses but are
actually artefacts of counter-causal structure.

This catalog pairs **problem classes** with **techniques we've
empirically validated** (or empirically rejected) across the
2755-2888 experiment arc.  It's meant as a recipe book for future
experiments and as a guard against past mistakes.

---

## 1. The confounders we keep encountering

| # | Confounder | Where it bites |
| - | ---------- | -------------- |
| C1 | Controller suspension (basal-0 closed-loop) | Observed ISF / EGP / carb response |
| C2 | Confounding by indication (harder events get more insulin) | Correction-factor regression |
| C3 | Patient self-selection (aggressive settings by observed hypo rate) | Cohort-level setting/outcome correlations |
| C4 | CGM smoothing + autocorrelation | 5-min forecasting vs hourly physics |
| C5 | Single patient dominates pooled stats | All pooled medians |
| C6 | Sample composition across lineages/controllers | Cross-controller mean comparisons |
| C7 | Collider bias: AID intervention modifies the outcome used to validate AID-related constructs | Any construct designed for counterfactual risk |
| C8 | Reverse causation at long horizons (72 h insulin → BG) | Long-window roll-up features |

---

## 2. Techniques × problem class

### 2.1  Subtract-the-physics: BGI decomposition

**Problem:** Observed ΔBG bundles insulin, carb, EGP, exercise,
circadian, and controller effects.

**Technique:** Pre-subtract a physics-based "expected" ΔBG (BGI
from insulin + carb-effect model), regress residuals against the
factor of interest.

**Validated by:** EXP-2755 (grand synthesis), EXP-2741/2742
(multi-factor ISF/CR).

**Addresses:** C1 partially, C2 partially.

**Caveat:** If the physics model uses profile ISF, you reintroduce
the very parameter you're estimating (circularity — EXP-2757 vs
2758).  Always use an *indication-blind* subtraction.

---

### 2.2  Correction-denominator: isolate active corrections

**Problem:** Dividing BG drop by *total* insulin (basal included)
conflates scheduled steady-state with event-driven correction.

**Technique:** Use only the *correction* component of insulin
(delta over scheduled) in the denominator.

**Validated by:** EXP-2755, EXP-2753 (controller decomposition).

**Addresses:** C1, C2.

**Caveat:** Works for 90.9 % of patients; closed 67 % of the
naive-to-profile ISF gap.  Remaining gap is controller dynamics
(not removable — C1 residual) + confounding-by-indication (C2
residual).

---

### 2.3  Category-specific AR(2) modeling

**Problem:** Pooled AR(1) on 5-min data gives R²≈0.25 and hides
factor-of-two differences between meal / correction / quiet
periods.

**Technique:** Fit separate autoregressive models per context
category.

**Validated by:** EXP-2793 (R²=0.449 vs 0.248 pooled).

**Addresses:** C4, C2.

---

### 2.4  Hourly aggregation: switch timescales

**Problem:** At 5-min resolution, CGM smoothing + AR dominate (22 %
variance); BGI physics contributes only 2 %.

**Technique:** Aggregate to hourly; BGI rises to 16 % variance,
category-specific modeling reaches 34.5 %.

**Validated by:** EXP-2800, EXP-2806 dual-pipeline.

**Addresses:** C4.

**Caveat:** Hourly and 5-min are **orthogonal** (EXP-2806:
r = −0.575 feedback between them).  Do not feed hourly corrections
into 5-min models.  Use hourly for **settings extraction**; 5-min
for **BG forecasting**.

---

### 2.5  Per-patient aggregation before pooling

**Problem:** A single prolific patient with 2 000 events can swing
a pooled median; Loop/Trio/OpenAPS can look identical even when
their users behave very differently.

**Technique:** Compute statistic per patient first, then pool over
patients (one-person-one-vote).  Pair with rank-based tests
(Wilcoxon, Friedman, Kruskal).

**Validated by:** EXP-2885 (Simpson decomposition of braking
signatures — three controller families emerged only after this
step).

**Addresses:** C5.

---

### 2.6  Simpson decomposition with stratification

**Problem:** A pooled effect can hide or invert sub-population
effects.

**Technique:** Stratify by the suspected confounder (controller,
TOD, aggressiveness tercile), recompute per stratum, and examine
within-stratum vs across-stratum effects separately.

**Validated by:** EXP-2885 (Loop-specific "hidden leverage" invisible
pooled); EXP-2886 (three orthogonal phenotype axes).

**Addresses:** C3, C5, C6.

---

### 2.7  Mediation audit (Baron-Kenny + Sobel)

**Problem:** An apparent mechanistic path ("lineage → HAAF →
counter-reg") can look plausible until you check each arrow.

**Technique:** Decompose total effect into direct + indirect;
report Sobel z and mediation proportion; require the mediation
arrow to have the *predicted sign* before telling a story.

**Validated by:** EXP-2887 (rejected HAAF feedback narrative for
oref1 CR gap — Path A had *reversed* sign).

**Addresses:** C6.

**Rule to adopt:** Any cross-lineage claim must pass a
significance check **and** a mediation audit on the proposed
mechanism before being published in a report.

---

### 2.8  Bootstrap confidence on Simpson claims

**Problem:** A stratified effect can flip sign under different
random splits if the stratification is under-powered.

**Technique:** Bootstrap resample patients within strata; report
CI of the Simpson effect; require non-crossing bootstrap bounds
before publishing a paradox claim.

**Validated by:** Checkpoint 028 (bootstrap Simpson); Checkpoint 029
(bootstrap pattern across audition signals).

**Addresses:** C3, C5.

**Small-n caveat (added EXP-2917):** when a cell has n=1, the
percentile bootstrap returns a degenerate zero-width CI that
ignores between-patient variance entirely. **Paired comparisons
against an n=1 cell inherit only the multi-patient side's variance
and report CIs that are *lower bounds* on true uncertainty.** Always
flag such pairs in tables (e.g. with † or "n=1") and never
interpret a "ci_excludes_zero=True" verdict on an n=1-involving
pair as independent evidence of separation. Corroborate with
mechanism stacks (Default Guard #6 / Recipe T) instead.

---

### 2.9  Counterfactual simulation (this is the new tool)

**Problem:** For any construct designed to flag risk that the
AID *prevents* (brake-saturation, hidden leverage, fragility under
disengagement), the observed outcome is systematically depressed
*precisely in the patients the construct targets*.  Observed-outcome
validation will always fail.

**Technique:** Simulate what would have happened with the AID
disengaged (scheduled basal instead of suspension, no SMB
injection, etc.).  Use that *counterfactual* outcome as the
validation target.

**Motivated by:** EXP-2888 (composite lost predictive power
against observed severe_fraction because AID was protecting the
flagged patients).

**Addresses:** C7.

**Planned:** EXP-2889 (AID-off replay for hidden-leverage cohort).

---

### 2.10  Natural experiments only for exogenous variation

**Problem:** Insulin gaps in AID data look like "no insulin"
events but are controller *suspensions* — confounded by the
indication that caused the suspension.

**Technique:** Restrict EGP / ISF estimation to intervals where the
gap is *exogenous* — sensor dropouts, connectivity loss, site
changes — never to algorithmic suspension intervals.

**Validated by:** EXP-2808 (natural experiments).

**Addresses:** C1.

---

### 2.11  Reject long-window roll-ups at causal scale

**Problem:** 72-h rolling insulin sum shows r = 0.000 with BG;
6-h rolling BG state "predicts" future insulin at 21 % accuracy
(worse than chance — reversed causality).

**Technique:** Do not use rollup features longer than the
physiological horizon (DIA ≈ 5 h; carb effect ≈ 4-6 h).  If you
see a "long-horizon" signal, suspect reverse causation or slow
patient-level drift, not physiology.

**Validated by:** EXP-2802 (causal cascade).

**Addresses:** C8.

---

## 3. Recipe: choosing the right technique by usecase

| Usecase | Timescale | Primary technique | Backup / audit |
| ------- | --------- | ----------------- | -------------- |
| Estimate patient ISF / CR for clinician report | Event | §2.1 BGI + §2.2 correction-denominator | §2.7 mediation audit if crossing subgroups |
| Flag "at-risk on AID failure" patients | Cohort | §2.6 stratified phenotype + §2.9 counterfactual sim | §2.5 per-patient aggregation |
| Compare Loop vs Trio vs OpenAPS | Cohort | §2.5 per-patient + §2.6 Simpson + §2.7 mediation | §2.8 bootstrap |
| BG forecasting, next 30-60 min | 5-min | §2.3 category-specific AR | §2.4 do *not* use hourly features here |
| Settings optimization (ISF/CR/basal) | Hourly | §2.4 hourly aggregation + §2.2 correction-denominator | §2.1 BGI residual check |
| Quantify EGP | Windowed | §2.10 natural experiments only | §2.1 with *indication-blind* ISF |
| Discover new phenotypes | Cross-sectional | §2.6 stratified + §2.8 bootstrap | §2.7 before mechanism claims |

---

## 4. Default guards (to add to every experiment template)

For any new experiment, before reporting a result:

1. **Per-patient check**: does the finding survive one-person-one-vote?
   (§2.5)
2. **Sign check**: is every regressor's sign physiologically plausible?
   If not, suspect C2 or collider.
3. **Significance check**: with n ≈ 20 patients, require effect size
   *and* p < 0.05 *and* CI that doesn't cross zero.
4. **Mediation audit**: if a mechanistic story is proposed, test each
   arrow before publishing the chain.  (§2.7)
5. **Counterfactual check**: is the outcome variable modified by the
   intervention under study?  If yes, observed-outcome validation is
   invalid.  (§2.9)
6. **Load-stratification check (cross-lineage / cross-controller only)**:
   any claim that lineage X outperforms lineage Y on a hypo/hyper
   protection metric must report the result both marginally and after
   conditioning on `cf_severe` (or equivalent counterfactual load).
   Lineage cohorts in this dataset self-select on load intensity —
   e.g. 5 of 7 Loop patients sit in the load_saturation regime
   (cf≥0.95) versus 2 of 9 oref1.  Without this guard, behavioural
   self-selection is reported as a mechanism difference.  (§2.9 +
   EXP-2902/2904)
7. **Load-mediation guard (cross-sectional cf-vs-physiology only)**:
   when correlating a load proxy (`cf_*`) with a downstream
   physiological outcome (counter-reg intercept, recovery time,
   etc.), AID protection MEDIATES the link.  Always also report
   the same correlation against `true_exposure = cf × (1 −
   protection)` — actual experienced events after AID coverage.
   Sign or strength changes between the two flag a coverage-
   distribution artifact rather than biology.  EXP-2912 negative
   ρ(cf, intercept) flipped to +0.39 in oref1 under
   true_exposure → HAAF interpretation withdrawn (EXP-2913).

---

## 5. Techniques still missing / to build

| Gap | Why we want it | Candidate |
| --- | -------------- | --------- |
| Proper instrumental-variable estimation for ISF | C2 never fully resolved; β ≈ 0 is confounded, not real | Sensor dropout windows as IV for insulin gap (partial work EXP-2808) |
| Doubly-robust ATE for controller comparisons | Current lineage comparisons are unadjusted means | propensity-score + outcome model on per-patient phenotypes |
| Hierarchical Bayesian for small-n cohorts | n ≈ 3 per lineage gives overconfident point estimates | partial-pooling across controllers with skeptical priors |
| Continuous-treatment dose-response for insulin | Current categorical analyses discard magnitude info | g-computation with natural-effect decomposition |

These are open work items for the research roadmap.

---

## 6. Experiments referenced

EXP-2754, 2755, 2757/58, 2793, 2800, 2802, 2806, 2808, 2877, 2881,
2882, 2884, 2885, 2886, 2887, 2888, 2889, 2891, 2892, 2893, 2894,
2895, 2896, 2897, 2898, 2899, 2902, 2904, 2905, 2907, 2909, 2910,
and checkpoints 027-039.

---

## 7. Eight-dimension lineage signature (Guard-#6 audit, EXP-2910)

After EXP-2880 → EXP-2909 the lineage cohort is characterised along 8
axes. Guard-#6 status as of EXP-2910 (Apr-23):

- **Verified (cf-conditioned, survives)**: mean protection (EXP-2904),
  TOD-invariance (EXP-2907), hourly mitigation profile (EXP-2909)
- **Mechanism / construction (Guard N/A)**: basal-cut utilization
  (EXP-2892), SMB channel availability (EXP-2893), user-config
  consistency (EXP-2899)
- **Pending re-test**: setting-independence (axis 2), counter-reg
  moderation (axis 7) — see EXP-2911 / EXP-2912 backlog

6 of 8 axes pass Guard #6 or are exempt. Algorithm-migration
recommendation surface (EXP-2894 / EXP-2905) is supported by verified
axes alone. Full re-grade table: see
`docs/60-research/exp-2910-eight-dim-regrade-2026-04-23.md`.
