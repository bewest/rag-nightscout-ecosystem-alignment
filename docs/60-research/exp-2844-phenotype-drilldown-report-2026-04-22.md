# EXP-2844: Phenotype Drilldown — Direction of S1 Basal Shift

**Date**: 2026-04-22
**Stream**: B (operational)
**Charter**: two-stream-methodology-charter-2026-04-22.md (V1–V8 viz appendix)
**Predecessor**: EXP-2843 (envelope-coupling)
**Inputs**:
- `externals/experiments/exp-2843_state_basal_coupling.parquet`
- `externals/experiments/exp-2812_triage_flags.parquet`
- `externals/experiments/exp-2831_triage_flags.parquet`

## Question

EXP-2843 found that 17/22 patients show statistically significant
(p<0.001) differences in actual basal between S0 and S1 windows, but
the **sign** of the shift is mixed (median +18% in some, −60% in
others). What predicts the direction?

## Method

Restricted to the 17 significant patients. Classified each by
`actual_basal_shift_pct`:

| Phenotype | Range | n |
|-----------|-------|---|
| `up_shift`   | > +15% | 6 |
| `flat`       | −15% to +15% | 5 |
| `down_shift` | < −15% | 6 |

Tested associations with controller (chi-square), baseline override
magnitude (Mann–Whitney U), recovery fraction (Mann–Whitney U), wear
delta.

## Results

### Phenotype × controller

| Controller | down_shift | flat | up_shift |
|------------|-----------:|-----:|---------:|
| **Loop**    | **0** | 3 | 3 |
| **OpenAPS** | 1 | 2 | 2 |
| **Trio**    | **5** | 0 | 1 |

**Striking pattern**:
- Trio overwhelmingly down-shifts on S1 entry (5/6 Trio patients)
- Loop never down-shifts (0/6); only flat or up
- OpenAPS spans all three roughly evenly

Chi-square not formally interpretable (cells <5) but the directional
contrast is unambiguous in the cohort observed.

### Override magnitude as predictor

Mann–Whitney up vs down: U=13, p=0.48 — **not** significant. Patients
who up-shift have slightly more-negative S0 baseline override
(−0.83 vs −0.63), but this is noise at n=12.

### Recovery vs phenotype

| Phenotype | Median recovery |
|-----------|----------------:|
| down_shift | 0.25 |
| flat       | **0.00** |
| up_shift   | 0.25 |

Worst recovery is in the **flat** group (the patients whose controller
does NOT adapt basal between states), consistent with: when the
controller doesn't audition basal in S1, BG stays high.

### Wear delta vs phenotype

Median wear delta is similar (~−17%) in up_shift and down_shift,
slightly milder in flat (−6%). Wear is **not** the phenotype driver.

## Charter checks

| Check | Result |
|-------|:------:|
| ≥2 phenotypes populated | PASS |
| Phenotype split useful (≥5 non-flat) | PASS |
| Controller test attempted | (cells too sparse for chi-square) |
| Override predictor signal (p<0.10) | FAIL (p=0.48) |
| No quantitative biology | PASS |

**3/5 PASS**, but the negative result on override magnitude is
informative: baseline operating point alone does **not** explain
direction.

## Interpretation (Stream B only)

The S1 basal-shift direction is **predominantly a controller-software
property**, not a per-patient biological property. The same envelope
state (S1 = high-glycemic 48h window) provokes opposite operational
responses across controllers:

- **Trio**: cuts basal further in S1 (already-aggressive baseline,
  treats S1 as low-risk, leans on SMB).
- **Loop**: raises basal in S1 (no SMB, must cover with temp basal).
- **OpenAPS**: heterogeneous (algorithm tuning per implementation).

This is **not** a biology claim. It is a claim that *given the same
envelope state*, the choice of controller materially changes the
basal audition profile a clinician would derive from observed data.

### Audition implications (Stream B operational)

| Controller observed | Audition recommendation |
|---------------------|--------------------------|
| Trio + down_shift   | Profile basal probably too high; controller already cutting. Consider lowering scheduled basal, but verify S1 BG control is acceptable. |
| Loop + up_shift     | Profile basal probably too low; controller compensating with temps. Consider raising scheduled basal in time-of-day blocks where shift concentrates (cross-ref: viz-time-of-day-audit). |
| Any + flat + low recovery | Controller is NOT adapting; either profile is right and BG is wrong (reconsider ISF/CR), or controller is unable to act (low autonomy / aggressive caps / wear). Cross-ref: site-age and wear flags. |

## Visualizations

`docs/60-research/figures/`:
- `cohort_phenotype_panel.png` — 4-panel summary (split, controller,
  recovery, baseline override predictor)
- `cohort_recovery_vs_shift.png` — "you are here" scatter with cohort IQR
  band; markers = controller, color = phenotype
- `cohort_controller_phenotype.png` — count heatmap

All comply with charter Appendix V (V1 no biology numbers; V3 percentile
bands; V5 phenotype-direction is a first-class facet; V7 cohort form).

## Open questions / next experiments

1. **Why does Loop never down-shift?** Hypothesis: lack of SMB forces
   basal-up as the only available high-state response. Test:
   compare Loop vs Trio on time-since-bolus-only-correction.
2. **Time-of-day localization**: do Trio down-shifts and Loop up-shifts
   concentrate in dawn vs evening windows? (→ viz-time-of-day-audit)
3. **Flat + low recovery**: are these the same patients flagged by
   EXP-2812 + EXP-2831? Cross-tab against patient `b` (yes — `b` is
   `flat` here, no recovery).

## Source files

- `tools/cgmencode/exp_phenotype_drilldown_2844.py`
- `tools/cgmencode/viz_cohort_overlay.py`
- `externals/experiments/exp-2844_phenotype_drilldown.json`
- `externals/experiments/exp-2844_phenotype_table.parquet`
