# EXP-2995: Re-stratification of EXP-2886 phenotype clusters by `algorithm_mode`

**Date**: 2026-04-23
**Audience**: open-source AID code authors.
**Scope**: with the EXP-2992 `algorithm_mode` schema column (Loop-AB-ON,
Loop-AB-OFF, Trio-oref1, AAPS-oref0, unknown) plus the EXP-2986 AAPS
labelling fix, re-examine whether EXP-2886's three phenotype axes
(stacking, braking, counter-regulation) and 8 archetypes are
genuinely orthogonal patient signatures or whether they were
confounded by AID design all along.
**What this is NOT**: a re-classification of any individual patient;
n is too small (max cell = 5) for definitive per-cell claims.

Implementation: `tools/cgmencode/exp_phenotype_restratification_2995.py`
Outputs (gitignored):
`externals/experiments/exp-2995_phenotype_x_algorithm_mode.parquet`,
`exp-2995_summary.json`.

---

## Headline

**Mixed — and the mix is informative.** The three EXP-2886 axes split
into two regimes:

- **`braking_ratio`**: η² vs `algorithm_mode` = **0.650** (within-mode
  std 0.10–0.32 vs overall ≈ 1.0) → this axis is *primarily an
  algorithm property*. EXP-2886's braking phenotype was, in retrospect,
  a re-discovery of the basal-cut-aggressiveness gap between Loop
  (low brake ratio) and oref1 (very low) and oref0 (high).
- **`stack_score`**: η² = **0.044** (within-mode std 0.78–1.75 vs
  overall ≈ 1.0) → this axis is *patient heterogeneity that
  cross-cuts algorithm_mode*. Each algorithm contains the full
  spectrum of stacking behaviour.
- **`counter_reg_intercept`**: η² = **0.225** → modest alignment;
  consistent with the (still unproven) HAAF-feedback hypothesis from
  EXP-2886 §4.2 / EXP-2887.
- **`hidden_leverage` (= stack × (1 − brake))**: η² = **0.091** —
  cross-cuts (despite its braking ingredient, the stacking ingredient
  dominates the dispersion).

This implies the EXP-2886 archetype labels mix algorithm-driven and
patient-driven features. The "well-defended" / "algorithm-dependent"
axis is mostly a Loop-vs-oref1 design fingerprint; the "stacker /
hidden-leverage" axis is genuine patient heterogeneity worth
preserving in any per-patient audition.

---

## Method

Reused `externals/experiments/exp-2891_simpson_dose_response.parquet`
(now carrying `algorithm_mode` after EXP-2992 + EXP-2986 fixes).

Three measures of confounding:

1. Cramér's V (bias-corrected) on the categorical contingency
   `archetype × algorithm_mode`.
2. ANOVA-style η² on each continuous phenotype axis vs
   `algorithm_mode` (β between-mode SS / total SS).
3. Within-mode standard deviation / overall standard deviation per
   phenotype axis (ratio < 1 → mode reduces variance →
   alignment; ratio ≈ 1 → mode has no effect → cross-cut).

---

## Result

### Contingency: archetype × algorithm_mode

| archetype \\ mode    | AAPS-oref0 | Loop-AB-OFF | Loop-AB-ON | Trio-oref1 | unknown |
|---|---:|---:|---:|---:|---:|
| algorithm_dependent  | 0 | 0 | 2 | 4 | 0 |
| exposed_stacker      | 1 | 1 | 0 | 0 | 0 |
| hidden_leverage      | 0 | 0 | 2 | 1 | 0 |
| insufficient_data    | 0 | 0 | 0 | 0 | 5 |
| lax_braking          | 1 | 0 | 0 | 0 | 0 |
| stacker_balanced     | 1 | 0 | 0 | 0 | 0 |
| stacker_weak_defense | 0 | 0 | 0 | 1 | 0 |
| well_defended        | 0 | 1 | 1 | 3 | 0 |

- Cramér's V (archetype vs mode) = **0.564** (moderate)
- Cramér's V (lineage vs mode) = **0.975** (sanity: mode is a refinement of lineage)

### Continuous axes (η² vs algorithm_mode)

| axis | η² | within-mode std / overall std (per mode) | Interpretation |
|---|---:|---|---|
| `stack_score`           | 0.044 | 1.35 / 1.75 / 1.27 / 0.78 / 0.98 | CROSS-CUTS — patient-level |
| `braking_ratio`         | **0.650** | 1.71 / 0.32 / 0.10 / 0.19 / NaN | ALIGNS — algorithm-level (within-AAPS oref0 still has spread) |
| `counter_reg_intercept` | 0.225 | 0.73 / 1.03 / 1.01 / 1.06 / 0.82 | mostly cross-cuts; modest mode signal |
| `hidden_leverage`       | 0.091 | (composite) | CROSS-CUTS |

### What the cross-cut axes look like within mode

Within Loop-AB-ON (n=5): stack scores span the full peer range
(c/d/e/g/i), and the hidden-leverage spread is 0.81 (g) down to 0.21
(d). Within Trio-oref1 (n=9): the ns-8b3c1b50793c and
ns-8f3527d1ee40 hidden-leverage outliers coexist with multiple
"well-defended" patients. Same algorithm, different patients,
different phenotype.

Within AAPS-oref0 (n=3): stack scores remain spread (1.35× overall
std), confirming the previously-flagged `lax_braking_controller` pattern
(EXP-2843/2844) is a genuine three-patient phenotype subset, not an
artifact of AAPS-oref0 itself being uniform.

---

## Interpretation

1. **The phenotype framework was partially design-confounded.** The
   `braking_ratio` axis is mostly a property of the algorithm
   (oref1 cuts harder than Loop than oref0). EXP-2886's "braking
   phenotype" should therefore be re-read as a per-algorithm
   description rather than a per-patient classification. This was
   already half-acknowledged in EXP-2886 §4.2 ("oref1 has the
   strongest braking") but is now formalised: η² = 0.65 means
   65% of the cross-patient variance in `braking_ratio` is explained
   by algorithm assignment alone.

2. **Stacking and hidden-leverage are genuine patient heterogeneity.**
   These axes are nearly orthogonal to `algorithm_mode` (η² ≈ 0.04
   and 0.09). This survives the new `algorithm_mode` lens. AID-author
   audition logic that ranks patients by stack_score continues to
   identify per-patient risk independent of which AID is in use.

3. **Counter-regulation sits in the middle.** The HAAF-feedback
   hypothesis (EXP-2886 §4.2) was "tighter algorithm → more hypo →
   attenuated CR". EXP-2887 rejected the strong-form mediation
   chain at n=19. EXP-2995 finds η² = 0.225, consistent with
   "some" mode signal but not enough to claim the algorithm
   *causes* the CR difference. Direction is preserved
   (oref1 lowest CR, oref0/Loop higher CR), magnitude is modest,
   the cohort still under-powers a clean test.

4. **The "algorithm_dependent" archetype is now visibly mode-tagged.**
   6 of 6 algorithm_dependent patients are on Loop-AB-ON or
   Trio-oref1 (the SMB-emitting designs). 0/3 are on AAPS-oref0
   (no SMB → no algorithm to depend on). 0/2 are on Loop-AB-OFF
   (autobolus channel disabled). This is consistent with capstone
   Section 4: SMB-emitting designs create algorithm-dependence
   because they take over per-event corrections.

5. **The 5 `unknown`-mode patients are all `insufficient_data`.**
   Their phenotype was undefinable for the same reason their mode
   is undefinable: missing the telemetry needed to distinguish
   AB-ON from AB-OFF (EXP-2992) is correlated with missing the
   telemetry needed to fit braking ratios.

---

## AID-author actionable findings

1. **When marketing "phenotype-aware" tuning to users, distinguish:**
   - "Algorithm-driven phenotype" (braking_ratio, partly CR) — re-read
     as a property of which AID is running, not of the user.
   - "Patient-driven phenotype" (stacking, hidden-leverage) — these
     follow the user across AID changes and should drive
     audition flags / settings recommendations.
2. **Drop `braking_ratio` from per-patient archetype labels** when the
   target audience is a single-AID user (e.g., a Loop-only Insights
   tab); use the algorithm baseline directly. Keep it for
   cross-AID research dashboards.
3. **Preserve `stack_score` and `hidden_leverage`** in audition
   inputs across AID changes; they survive `algorithm_mode`
   re-stratification.
4. **Mark counter-regulation as a "weak alignment" axis**; do not
   make claims like "switching to Trio reduces your counter-reg" —
   the data don't support that level of causal claim (η² 0.225,
   confounded by HAAF feedback that EXP-2887 could not measure).

---

## Verdict

**Phenotype clusters partially align with `algorithm_mode`** (Cramér's V
= 0.56). The breakdown is informative: braking ratio is essentially an
algorithm signature (η² 0.65), stacking and hidden-leverage are
genuine patient heterogeneity (η² 0.04, 0.09), counter-regulation is
in between (η² 0.22). The EXP-2886 archetype labels remain useful but
should be read with the per-axis confounding profile in mind.
