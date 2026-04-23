# EXP-2953 — Uniform action-curve at HYPO descent (companion to EXP-2950)

**Date**: 2026-04-23
**Audience**: AID code authors. NOT therapy advice.
**Verdict**: **CONFIRMED with refinement** — IOB-age framework holds at hypo descent under uniform curve. Cleanest signal is `act_entry` (absolute), not freshness-ratio.

## Method

Identical pipeline to EXP-2950 (uniform biexponential peak 75min, DIA
300min, applied to bolus + bolus_smb + basal_excess event history).
Anchor changed to HYPO descent: BG crosses 80 falling, prior 30min
all >80, no carbs ±60min.

## Result

5,198 events.

| Design       | n     | iob_entry | act_entry | freshness | iob_delta | bg_min_60 | tbr_54% |
|--------------|------:|----------:|----------:|----------:|----------:|----------:|--------:|
| Loop_AB_OFF  |   606 |     1.87  |   0.0188  |   0.0111  |   −0.28   |    65.7   |   5.34  |
| Loop_AB_ON   | 1,442 |     3.32  |   0.0325  |   0.0113  |   −0.18   |    63.2   |   7.03  |
| oref0        |   834 |     0.97  |   0.0089  |   0.0113  |   −0.18   |    54.9   |  17.04  |
| **oref1**    | 2,316 |     2.98  |   0.0302  |   0.0109  |   **−0.38** |  **67.3** | **3.18** |

### Loop_AB_ON vs oref1

| Metric          | Loop      | oref1     | Δ          | MW p    |
|-----------------|----------:|----------:|-----------:|--------:|
| iob_entry       |   +3.32   |   +2.98   |   +0.34    | 2.8e-3  |
| **act_entry**   | **+0.0325**| **+0.0302**| **+0.0023** | **4.4e-3** |
| freshness       |   +0.0113 |   +0.0109 |   +0.0004  | 0.318   |
| iob_delta       |   −0.18   |   −0.38   |   +0.21    | 0.039   |
| **bg_min_60**   | **+63.17** | **+67.29** | **−4.12 mg/dL** | **7.4e-25** |
| **tbr_54%**     |   +7.03%  |   +3.18%  |   +3.85 pp | 1.2e-16 |

## Interpretation

### What confirms the framework

1. **Loop has MORE active insulin at hypo entry** (act_entry 0.0325 vs
   0.0302, Δ +0.0023, p=4e-3). The fresh-IOB-as-hazard story holds.
2. **Loop sheds IOB more slowly during the window** (iob_delta −0.18
   vs oref1 −0.38, p=0.04). oref1 is actively shedding stale insulin
   faster despite less to shed.
3. **Outcomes match** (bg_min −4.1 mg/dL deeper, tbr_54 +3.85 pp).
   The 2× severe-hypo signal from EXP-2947 reproduces.

### What refines the framework

The **freshness ratio (act_entry/iob_entry) is NOT a discriminator**
at hypo entry: Loop_AB_ON 0.0113 vs oref1 0.0109 (p=0.318). The
per-unit-IOB age distribution is similar across designs.

**The discriminator is total active insulin (absolute act_entry),
which scales with recent dose magnitude AND its proximity to peak
action.** Loop_AB_ON's autobolus loop maintains a higher steady-state
of recently-delivered insulin, which translates to more activity
during the descent.

This is consistent with EXP-2947's narrative but locates the
mechanism in absolute activity rather than normalised freshness.

### Operationalisation note

For future work, the cleanest cross-design metric for IOB age is:

  **`uniform_activity_at_event` (synth_act_entry)**

Avoid:
- `synth_freshness` (ratio) — dominated by total IOB at low BG
- grid `insulin_activity` — oref1-only column (EXP-2949)
- grid `iob` — controller bookkeeping, may differ in basal accounting

## Comparison to EXP-2947 (grid)

| Metric              | EXP-2947 (grid) | EXP-2953 (uniform) | Same direction? |
|---------------------|-----------------|--------------------|----:|
| Loop iob at entry   | 0.37 (LESS)     | 3.32 (MORE)        | flipped (basal accounting) |
| iob shedding pre    | −1.45 (MORE)    | (not measured pre) | n/a |
| iob shedding window | n/a             | −0.18 (LESS)       | n/a |
| basal-cut frac      | 0.96 (MORE)     | n/a                | (still confirmed in EXP-2947) |
| bg_min              | (not in 2947)   | 63.2 (lower)       | ✓ confirms outcome |
| tbr_54              | 7.03% (HIGHER)  | 7.03%              | ✓ identical |

The grid `iob` direction-flip on iob_at_entry comes from basal
accounting: uniform curve credits Loop's basal_excess (autobolus
deliveries treated as boluses?) whereas grid `iob` may not. This
is exactly the column-source artifact EXP-2949 warned about.

The OUTCOME measurements are robust regardless. And the **direction
of the mechanism matches**: more recent insulin + more activity at
entry + less shedding during window → deeper hypos.

## What this closes

- IOB-age framework now validated at BOTH window classes (sustained-
  high in EXP-2950, hypo in EXP-2953) with a uniform action-curve
  template applied identically to all designs.
- 7 independent evidence lines for the framework now (adds EXP-2953
  to the 6 prior).
- Cleanest cross-design metric identified: `synth_act_entry`.

## What this is NOT

- Therapy advice or migration recommendation
- A claim that all hypos are caused by recent boluses (EGP, exercise,
  alcohol etc. all matter)
- A claim that more aggressive Loop tuning would fix this (it would
  likely make the gap WORSE — see EXP-2937/2944/2950 dose findings)

## What this IS

- Independent uniform-curve confirmation of EXP-2947 hypo signature
- Refinement: absolute activity, not freshness ratio, is the metric
- Operationalisation guidance for future cross-design work
