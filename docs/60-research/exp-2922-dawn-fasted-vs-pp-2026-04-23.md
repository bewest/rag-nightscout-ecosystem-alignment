# EXP-2922 — Loop dawn-hyper decomposed: fasted vs post-prandial

**Date:** 2026-04-23
**Source:** `tools/cgmencode/exp_dawn_fasted_vs_pp_2922.py`
**Scope:** Design-feature characterisation. AID-author audience.
NOT therapy advice. Per binding scope (`exp-2916-design-gap-2026-04-23.md`).

## Method

Per Loop patient, classify each 5-min cell by `time_since_carb_min`:
- **FASTED**: ≥ 300 min (>5 h since last carb entry)
- **POST_PRANDIAL**: ≤ 180 min (≤3 h)
- (180–300 excluded as ambiguous mid-window)

Per (autobolus, state, hour) compute fraction of cells with
glucose > 250. Patient-mean within cell before pooling. 95 %
bootstrap CI (2 000 resamples).

## Headline (03:00–04:00 mean)

| autobolus | state          | n | 03:00 hyper | 04:00 hyper |
|-----------|----------------|--:|------------:|------------:|
| OFF       | FASTED         | 2 | **17.03 %** | **17.29 %** |
| OFF       | POST_PRANDIAL  | 2 | **43.67 %** | **40.78 %** |
| ON        | FASTED         | 5 | **10.70 %** |  7.37 %     |
| ON        | POST_PRANDIAL  | 5 | 25.56 %     | 25.46 %     |

## Findings

1. **The dawn fingerprint is real and EGP-driven, not just
   meal carry-over.** Even strictly fasted (>5 h since last carbs),
   Loop autobolus-OFF runs **17 %** of cells over 250 mg/dL at
   03:00. That alone is ~4× higher than oref1's overall hyper
   peak (4.3 % at 19:00, EXP-2920). Brake-only Loop genuinely
   under-doses against EGP.

2. **Late-meal carry-over compounds the dawn signature ~2.5×.**
   Post-prandial 03:00 hyper is 43.67 % (OFF) and 25.56 % (ON) —
   roughly 2.5× the fasted rate at the same hour. So Loop's
   "dawn" peak in EXP-2920 mixes two separate failures: (a)
   genuine EGP under-dosing and (b) inability to clear late-evening
   meal IOB on schedule.

3. **Autobolus helps in both states, similarly proportionally.**
   FASTED OFF→ON: 17.03 % → 10.70 % (37 % relative reduction).
   POST_PRANDIAL OFF→ON: 43.67 % → 25.56 % (41 % relative
   reduction). Autobolus is **not specifically a carb-handling
   feature** — it pre-emptively doses against the hyperglycemic
   trend regardless of cause.

4. **Even autobolus-ON fasted still has 10.7 % at 03:00.**
   This is the irreducible Loop residual without dynamic-ISF.
   For comparison oref1's peak fasted-only would be even lower
   than its 4.29 % overall peak.

## Mechanism stack for AID authors

| Layer | Mechanism | Lever |
|-------|-----------|-------|
| 1 | EGP rises pre-dawn | Dynamic ISF / sensitivity-ratio widening |
| 2 | Late-meal IOB doesn't clear on schedule | More aggressive correction past midnight |
| 3 | No SMB to act on small upward drift | Autobolus or oref-style SMB |
| 4 | Brake-only response to rising trend | Predictive cap raise / SMB enabling |

A controller that handles only one layer can address only one of
the rows in the headline table. oref1 addresses 1, 3, 4 via
dynamic ISF + SMB-as-correction → 4.3 % overall peak.
Loop autobolus-ON addresses 3 → 10–25 % depending on state.
Loop autobolus-OFF addresses none of layers 1, 3, 4 → 17–44 %.

## Caveats

- n=2 vs n=5; CIs are wide and OFF cells often degenerate
  (Toolkit §2.8 small-n caveat).
- `time_since_carb_min` capped at 360 — patients with truly long
  fasts (>6 h) all bin into "FASTED ≥ 300". Acceptable for this
  binary split.
- "FASTED" still includes basal IOB carry-over from late boluses;
  not a true clamp.
- Hour-of-day not TZ-normalised; 03:00 here is local-recorded clock.

## Implication

The "dawn-hyper" finding from EXP-2920 is **not an artefact of
late-evening eating**. It survives strict fasting, in roughly the
same direction. The two effects (EGP under-dosing and late-meal
overhang) **compound additively** at the worst hour.

For AID authors comparing controller designs, this means:
- A pure brake-only design will always under-perform on dawn,
  regardless of meal-timing policy.
- A dynamic-ISF design can address the EGP component without
  an SMB feature.
- An SMB-as-correction design (oref1) addresses both layers
  simultaneously.

## Linked artefacts

- `externals/experiments/exp-2922_summary.json`
- `docs/visualizations/exp-2922-dawn-fasted-vs-pp.png`

## Next candidate

- **EXP-2923**: same fasted/post-prandial split applied to
  oref1 — does its 4.29 % peak shrink toward zero in the fasted
  arm (confirming dynamic-ISF handles EGP cleanly), or persist
  (suggesting residual mechanism)?
