# EXP-2934 — Day-level TIR decomposed by lagged-BG state

**Date:** 2026-04-23
**Status:** Closed
**Scope:** Design-feature characterisation for open-source AID author
audience. NOT therapy advice. NOT a recommendation to migrate AID
systems.

## Question

EXP-2925 showed oref1 Pareto-dominates Loop on day-level TIR (82.6 % vs
66.1 %). Guard #8 (introduced in EXP-2933) requires asking: how much of
this advantage is "tighter baseline begets tighter present" (in-band
autoregressive momentum from a tighter pre-existing BG distribution)
versus "active controller pull-back from excursions"?

If the gap collapses within strata of lagged BG, the day-level edge is
momentum. If the gap holds — or grows — within strata, oref1 is
actively pulling back faster.

## Method

For each 5-min cell of 16 patients (7 Loop, 9 oref1; 665 178 cells):

1. Compute `lag_60_bg` = BG at t − 60 min.
2. Bin globally into tertiles: `low_lag` ≤109, `mid_lag` 110–154,
   `high_lag` >154 mg/dL.
3. Per-patient TIR within each lag_bin.
4. Mean per design (Loop_AB_OFF, Loop_AB_ON, oref1).
5. Within-lag-bin gap with 2000-bootstrap 95 % CI on patient-mean
   difference (oref1 − design).

Patient autobolus split: Loop_AB_ON {c, d, e, g, i}, Loop_AB_OFF
{a, f}.

## Results

### Cell distribution across lag_bins (% of design's cells)

| design       | low_lag | mid_lag | high_lag |
|--------------|--------:|--------:|---------:|
| Loop_AB_OFF  |    27.3 |    25.7 |     47.0 |
| Loop_AB_ON   |    26.7 |    32.6 |     40.6 |
| oref1        |    39.4 |    35.9 |     24.8 |

**oref1 spends 24.8 % of time with high lagged BG vs 47 % for
Loop_AB_OFF (1.9× difference).** This is the "avoidance" channel.

### Per-patient TIR within (design, lag_bin)

| design       | lag_bin  | n  | TIR    | TAR    | TBR    | mean BG |
|--------------|----------|---:|-------:|-------:|-------:|--------:|
| Loop_AB_OFF  | low_lag  |  2 | 83.62  |  7.92  | 8.46   |  111.79 |
| Loop_AB_OFF  | mid_lag  |  2 | 82.45  | 15.42  | 2.13   |  136.53 |
| Loop_AB_OFF  | high_lag |  2 | 34.45  | 64.92  | 0.63   |  220.99 |
| Loop_AB_ON   | low_lag  |  5 | 82.55  |  7.22  | 10.23  |  113.39 |
| Loop_AB_ON   | mid_lag  |  5 | 84.73  | 12.56  | 2.71   |  134.94 |
| Loop_AB_ON   | high_lag |  5 | 46.60  | 52.62  | 0.78   |  193.96 |
| oref1        | low_lag  |  9 | 89.74  |  3.80  | 6.46   |  107.22 |
| oref1        | mid_lag  |  9 | 89.19  |  8.28  | 2.53   |  127.26 |
| oref1        | high_lag |  9 | 64.26  | 34.41  | 1.33   |  166.31 |

### Within-lag-bin TIR gap (oref1 − design, pp)

| lag_bin  | vs design    | gap        | 95 % CI            | sig |
|----------|--------------|-----------:|--------------------|-----|
| low_lag  | Loop_AB_OFF  |    +6.11   | [−0.35, +12.69]    |     |
| low_lag  | Loop_AB_ON   |    +7.19   | [−0.91, +16.06]    |     |
| mid_lag  | Loop_AB_OFF  |    +6.74   | [+3.25, +10.41]    | ★   |
| mid_lag  | Loop_AB_ON   |    +4.46   | [−0.94, +9.79]     |     |
| high_lag | Loop_AB_OFF  |  **+29.81**| [+21.71, +37.52]   | ★   |
| high_lag | Loop_AB_ON   |  **+17.66**| [+8.13, +27.20]    | ★   |

### Marginal reference

| design       | marginal day-level TIR |
|--------------|-----------------------:|
| Loop_AB_OFF  |                  60.68 |
| Loop_AB_ON   |                  68.24 |
| oref1        |                  82.59 |

Marginal gaps: oref1 − Loop_AB_OFF = **+21.91 pp**; oref1 − Loop_AB_ON
= **+14.35 pp**.

## Interpretation

Guard #8 result is **inverted from the EXP-2931 pattern**. The within-
high_lag gap (+29.81 pp, +17.66 pp) is *larger* than the marginal gap
(+21.91 pp, +14.35 pp). The day-level TIR edge is not momentum — it is
**active pull-back from excursions**.

Within low_lag (BG was already in/near range 1 h ago), all designs
achieve 82–90 % TIR; the design gap is small and not significant for
Loop_AB_ON. Within high_lag (BG was high 1 h ago), the design gap is
the dominant feature: Loop_AB_OFF TIR collapses to 34 %, Loop_AB_ON to
47 %, while oref1 holds 64 %.

Two compounding mechanisms produce oref1's day-level advantage:

1. **Avoidance**: oref1 spends 24.8 % of cells in high_lag vs Loop_AB_OFF
   47 % (1.9×). The dose-shape mechanism from EXP-2930 (front-loaded
   UAM dosing) keeps PP excursions from reaching the high_lag stratum.
2. **Recovery**: when oref1 *does* enter high_lag, it pulls back to
   in-range 1.3–1.9× faster than Loop variants (TIR 64.26 vs 34.45 / 46.60).

These are independent levers. (1) is the offence-side mechanism
(EXP-2929/2930). (2) is the defence-side mechanism — what happens after
an excursion is already underway. Both flow from the same algorithmic
substrate (UAM + dynamic-ISF + SMB-as-correction at higher cadence
during high-glucose-velocity intervals).

## Mechanism implication for AID authors

The day-level TIR finding decomposes cleanly into two AID-author
levers:

- **Offence (avoidance)**: front-loaded glucose-appearance/UAM detection
  + SMB-as-correction at meal onset. Prevents entry into high_lag.
  Already characterised in EXP-2930.
- **Defence (recovery)**: continuous correction-SMB cadence + dynamic-ISF
  during sustained-high windows. Pulls back from high_lag.

Both are needed — fixing only one closes ~half the day-level gap.
This is consistent with EXP-2929 (autobolus-ON closes 53 % of PP gap):
autobolus delivers offence but Loop's recovery mechanism (basal-cut +
manual user corrections) lags oref1's continuous correction-SMB cadence.

## What this is NOT

- **NOT** a therapy recommendation. Patient choice and autonomy balance
  many factors including device availability, support ecosystems, and
  hardware compatibility.
- **NOT** an attribution to a single feature. The recovery channel is a
  composite of multiple algorithmic decisions (correction cadence,
  dynamic-ISF, SMB sizing).
- **NOT** Pareto-validated for hypoglycaemia at every stratum: low_lag
  TBR is 6–10 % across designs (within-stratum hypo exposure roughly
  proportional to time spent there). High-stratum TBR remains <2 %
  across all designs.

## Cross-reference

- Guard #8: deconfounding-toolkit-2026-04-22.md §4
- Avoidance mechanism: EXP-2929, EXP-2930
- Marginal day-level finding: EXP-2925
- Synthesis: synthesis-design-comparison-2026-04-23.md (Finding A → C)

Inverted Guard #8 result deserves a third pattern in the toolkit: when
within-stratum gap *exceeds* marginal gap, the conditioning variable
is actively *suppressing* the design effect — i.e. design X is
preferentially avoiding the high-stratum cells where its advantage is
strongest. This is the offence-defence compounding signature.
