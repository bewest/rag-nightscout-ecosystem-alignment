# EXP-2920 — Time-of-day × design severe-event profile

**Date:** 2026-04-23
**Source:** `tools/cgmencode/exp_tod_design_profile_2920.py`
**Scope:** Design-level scientific characterisation of WHEN each
AID design's residual severe-event burden lands. Per binding scope
(`exp-2916-design-gap-2026-04-23.md`): for AID-author audience,
NOT therapy advice.

## Method

- Source: `externals/ns-parquet/training/grid.parquet` 5-minute
  cells (944k rows after lineage filter, 19 patients).
- Per-patient hourly fractions of `glucose < 54` (severe hypo)
  and `glucose > 250` (severe hyper).
- Patient-mean within (lineage, hour-of-day) before pooling
  (per Toolkit §2.5 — avoids patient-volume Simpson trap).
- 95 % CI by patient bootstrap (2 000 resamples).
- Hour is **local clock time as recorded in the source data**;
  per-patient timezone offsets not normalised — caveat below.

## Headline

| Design | n | Peak HYPO hour | Peak HYPO % | Peak HYPER hour | Peak HYPER % |
|--------|--:|----------------|------------:|-----------------|------------:|
| Loop (iOS)     | 9 | **09:00** | 2.54 % | **03:00** | **18.93 %** |
| oref0 (legacy) | 3 | **00:00** | 4.66 % | 13:00     | 7.41 %      |
| oref1 (modern) | 9 | **01:00** | 1.27 % | 19:00     | 4.29 %      |

Three distinct design fingerprints emerge:

1. **Loop has a massive 3am dawn-hyperglycemia signature**: nearly
   1-in-5 cells over 250 mg/dL. This is consistent with Loop's
   non-dynamic ISF (without manual sensitivity overrides), the
   dawn-cortisol surge raising EGP, and Loop's brake-only
   conservatism in the absence of autobolus.
2. **oref1's dynamic-ISF pays off overnight**: peak hyper is post-
   dinner (19:00) at only 4.3 %, and overnight peak hypo is 1.27 %.
   The dawn signature is essentially absent.
3. **oref0 has a midnight hypo peak (4.66 %)**: consistent with
   EXP-2918 (10 min basal-cut latency), EXP-2892 (20 % brake
   utilisation), and EXP-2916 (0.36 protection deficit). However
   oref0 is n=3 and one patient is the EXP-2905 manual-SMB
   outlier — point estimate, not inferential claim.

## Mechanism stack interpretation (for AID authors)

| Observed pattern | Plausible design lever |
|------------------|------------------------|
| Loop 3am hyperglycemia | No dynamic-ISF; conservative basal at low BG; EGP rise outpaces correction |
| oref1 dawn protection | `sensitivityRatio` widens overnight; SMBs pre-emptively dose against rising trend |
| oref1 19:00 hyper peak | Post-dinner absorption tail; SMB cap or absorption mismatch |
| oref0 00:00 hypo peak | Slower basal cut + no SMB-as-correction → over-suspension when low |
| Loop 09:00 hypo peak | Morning-bolus stacking (post-breakfast); brake-only kicks in late |

The Loop 09:00 hypo + 03:00 hyper combination suggests that Loop
patients in this cohort run with conservative settings (preventing
overnight hypo) at the cost of dawn-hyperglycemia, and then
autobolus-corrected post-breakfast leads to morning-stacking
hypo. This matches EXP-2919's finding that Loop autobolus
subscribers have 3× longer basal-cut latency.

## Caveats

- **Hour-of-day is local clock time as recorded.** Per-patient
  timezone offsets and DST not normalised — could shift dawn
  signatures by ±1 h. The Loop 03:00 peak is too sharp to be a
  TZ artefact for the whole cohort.
- **n=3 for oref0; n=9 for Loop and oref1.** oref0 numbers are
  case-study scale.
- **Local hour is not necessarily wake/sleep hour.** The "dawn"
  interpretation assumes a typical sleep window; shift-workers
  would invert.
- **Hyperglycemia at 03:00 includes carry-over from late-evening
  meals** in some patients — separate post-prandial vs
  basal-fasted is left to a successor experiment.
- **No counterfactual run.** This characterises observed AID
  behaviour, not what would happen disengaged. For "where does
  the AID protect best" use EXP-2891's protection metric.

## Implications for AID authors

1. **Dynamic-ISF is the highest-leverage dawn intervention** in
   this dataset. Closed-loop systems without it (Loop default)
   show a dramatic pre-wake hyperglycemia signature that brake-
   only behaviour cannot resolve.
2. **Overnight basal-cut latency matters**: oref0's 10-min latency
   (EXP-2918) coincides with its midnight hypo peak. oref1's
   instant cut + SMB-as-correction shows the lowest overnight hypo
   burden of the three designs.
3. **Loop morning-hypo signature** suggests autobolus + post-
   breakfast brake interaction is worth studying. Combined with
   EXP-2919, autobolus-on Loop patients may benefit most from
   tightening morning carb-ratio rather than from basal changes.

## Linked artefacts

- `externals/experiments/exp-2920_summary.json`
- `externals/experiments/exp-2920_hourly.parquet`
- `docs/visualizations/exp-2920-tod-profile.png`

## Next candidate experiments

- **EXP-2921**: split Loop tod-profile by autobolus on/off
  (per EXP-2919) — does autobolus-off Loop show oref0-like
  midnight hypo?
- **EXP-2922**: post-prandial vs basal-fasted decomposition of
  the 3am Loop signature (was patient eating after 21:00?).
- **Per-patient TZ normalisation** as a data-quality task.
