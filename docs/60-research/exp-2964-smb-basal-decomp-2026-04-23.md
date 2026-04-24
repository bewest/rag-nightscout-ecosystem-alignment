# EXP-2964 — SMB-vs-basal decomposition of velocity-coupling at PP (CLEAN POSITIVE w/ honest qualification)

**Date**: 2026-04-23
**Audience**: Open-source AID controller authors

## Scope

EXP-2960 measured TOTAL velocity-vs-insulin coupling. This decomposes
the pooled per-design slope into three additive channels:

- **bolus** (user announce-meal manual bolus)
- **SMB** (autonomous Super-Micro-Bolus — controller channel)
- **basal-excess** (temp-basal above scheduled — controller channel)

This maps the EXP-2960 finding to actionable controller-code-level
levers vs USER-behaviour confounds.

## What this is NOT

- Not a clinical recommendation.
- Not a within-patient claim — between-design pooled-event regression.

## Method

- Same PP events as EXP-2960 (n=4,687).
- For each design, fit independent linear regressions
  `ins_60_<channel> ~ vel_30` for each of the three channels.
- Verify per-design that channel slopes sum to total slope (additive
  by construction since `ins_60_total = bolus + smb + basal_excess`).

## Results

### Component contributions to mean ins_60 (units U)

| design | bolus | SMB | basal_x | total | bolus % | SMB % | basal_x % |
|---|---|---|---|---|---|---|---|
| Loop_AB_OFF | 12.12 | 0.00 | 0.50 | 12.62 | 96.0 | 0.0 | 4.0 |
| Loop_AB_ON  |  8.10 | 1.15 | 0.06 |  9.32 | 87.0 | 12.3 | 0.7 |
| oref0       |  3.67 | 0.00 | 0.12 |  3.80 | 96.7 | 0.0 | 3.3 |
| oref1       |  6.41 | 1.65 | 0.03 |  8.09 | 79.2 | 20.4 | 0.4 |

### Per-channel slope (U per mg/dL/min)

| design | bolus slope (95% CI) | SMB slope (95% CI) | basal_x slope (95% CI) | total |
|---|---|---|---|---|
| Loop_AB_OFF | **+0.950** (+0.62, +1.28) | n/a (no SMB) | +0.064 (+0.03, +0.09) | +1.014 |
| Loop_AB_ON  | +0.228 (+0.03, +0.42) | **+0.380** (+0.31, +0.45) | +0.009 (−0.00, +0.02) | +0.617 |
| oref0       | **−0.257** (−0.40, −0.11) | n/a (no SMB) | −0.010 (−0.02, +0.00) | −0.266 |
| oref1       | **+1.000** (+0.86, +1.13) | **+0.361** (+0.30, +0.42) | +0.004 (−0.00, +0.01) | +1.365 |

### Channel share of total slope

| design | bolus | SMB | basal_x |
|---|---|---|---|
| Loop_AB_OFF | 94% | 0% | 6% |
| Loop_AB_ON  | 37% | 62% | 2% |
| oref0       | 96% | 0% | 4% |
| oref1       | 73% | 26% | 0% |

## Interpretation — major framework update

1. **The SMB-channel velocity-coupling is essentially identical
   between Loop_AB_ON (+0.380) and oref1 (+0.361)** — 95% CIs overlap
   strongly. As a CONTROLLER channel, both auto-bolus designs respond
   to early rising velocity at the same magnitude.

2. **The +0.62 vs +1.36 pooled-total difference between Loop_AB_ON
   and oref1 (EXP-2960) is driven primarily by the BOLUS channel
   (+0.23 vs +1.00) — i.e. USER manual announce-meal bolus
   behaviour, not the controller.** oref1 patients in this cohort
   give larger announce-meal boluses for faster-rising meals; Loop
   AB ON patients tend to under-correlate (likely because Loop's
   auto-bolus does some of the work).

3. **basal-excess velocity-coupling is small in all designs**
   (max |slope| = 0.064 in Loop_AB_OFF, others ≤ 0.01). Temp-basal
   alone is too slow / coarse to be a meaningful velocity-response
   lever at the 30-minute window.

4. **oref0's negative pooled slope is in the bolus channel** (−0.26
   of −0.27 total). EXP-2963 showed this is one-patient-driven user
   reverse-causation. The controller (basal-x) channel is essentially
   zero (−0.01).

## AID-author lever priority order — REVISED

Mapping back to actionable controller code:

| Lever | Channel | Effect size at PP | Ranking |
|---|---|---|---|
| Auto-bolus / SMB on rising velocity (rising-velocity heuristic + UAM) | SMB | +0.36 to +0.38 U per mg/dL/min | **PRIMARY controller lever** |
| Temp-basal velocity modulation | basal-excess | < 0.07 U per mg/dL/min | Secondary, marginal at 30-min horizon |
| User announce-meal pre-bolus practice | (user) bolus | +0.23 to +1.00 U per mg/dL/min | Cohort-dependent, NOT a controller lever |

For AID controller authors, the actionable conclusion is: **the
controller channel that meaningfully scales with early rising
velocity is SMB**; basal-only designs cannot match the SMB response
even if the basal modulation is correctly tuned. Loop_AB_ON's
SMB-channel response and oref1's SMB-channel response are
quantitatively similar — the algorithmic differences (Loop's
PID-style vs oref1's heuristic UAM) do not translate into a
detectable difference in SMB-channel velocity-coupling slope at this
event-window.

## Honest qualifications

- The EXP-2960 headline ("oref1 couples 2.2× more strongly than
  Loop AB ON") is correct for TOTAL insulin but **misleading as a
  controller comparison**. The controller-channel comparison is a
  near-tie (+0.36 vs +0.38).
- EXP-2962's per-patient analysis already softened EXP-2960
  (MWU p=0.22). EXP-2964's decomposition explains WHY: the
  pooled-event total-insulin difference is dominated by user-bolus
  practice variance, not controller variance.

## Files

- `tools/cgmencode/exp_smb_basal_decomp_2964.py`
- `externals/experiments/exp-2964_summary.json` (gitignored)
- `externals/experiments/exp-2964_stdout.txt` (gitignored)

## Provenance

- Input grid: `externals/ns-parquet/training/grid.parquet`
- Cohort: `externals/experiments/exp-2891_simpson_dose_response.parquet`

## Next experiment

- EXP-2969 candidate: per-patient SMB-channel slope (oref1 vs
  Loop_AB_ON) to test whether the SMB-channel near-tie holds at the
  per-patient level.
- EXP-2970 candidate: same decomposition at sustained-high windows
  (replicate EXP-2961 with channels) — would test whether Loop_AB_ON's
  surprising +0.78 SMB-only slope at sustained-high (vs oref1 +0.39)
  is a genuine controller-design difference.
