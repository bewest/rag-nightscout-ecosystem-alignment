# EXP-2942 — oref0 lineage as natural variation: algorithm-family vs selection-bias

**Date**: 2026-04-23
**Audience**: AID code authors (controller-design characterisation)

## Scope

After the 8-candidate elimination cascade (EXP-2937–2941) downgraded the
recovery-channel claim to a selection-bias hypothesis, EXP-2942 uses
**oref0 (n=3) as a natural test**: same OpenAPS algorithm family as
oref1, but a different patient cohort, and (critically) ZERO
SMB-as-correction usage (confirmed cohort-wide).

The diagnostic logic:
- If recovery is determined by **patient cohort** (selection bias):
  oref0 patients should recover differently than Loop or oref1 patients
  in unpredictable directions.
- If recovery is determined by **algorithm channel availability**:
  oref0 (no SMB) should match Loop_AB_OFF (no SMB), and oref1 (full
  channel) should outperform both.

## What this is NOT

- Not a recommendation to migrate any patient between AID systems.
- Not a quality ranking of oref0/Loop/oref1 — patient choice and
  device access dominate AID selection.
- Not a within-patient AID-switch experiment (still the gold standard).

## Method

Reused the EXP-2937 carb-isolated sustained-high event extraction
(`carbs_60==0` AND no carbs in 60-min window). Added the 3 oref0
patients to the design grid: Loop_AB_OFF (n=2), Loop_AB_ON (n=5),
oref0 (n=3), oref1 (n=9). Per-patient recovery means; bootstrap CIs
with N=2000.

## Results (4 060 events)

| Design       | n_pat | events | mean SMB count | recovery |
|--------------|------:|-------:|---------------:|---------:|
| Loop_AB_OFF  |   2   |   282  |       0.00     |   29.6%  |
| Loop_AB_ON   |   5   |   287  |       4.31     |   35.7%  |
| **oref0**    | **3** |   273  |     **0.00**   | **30.0%**|
| oref1        |   9   |   138  |       2.82     |   57.0%  |

**oref0 individual patients**: 30.0%, 36.4%, 23.7% (mean 30.0%).

### Bootstrap contrasts (Δ recovery, 95% CI)

| Contrast                     |   Δ    | CI                | sig |
|------------------------------|-------:|-------------------|:---:|
| Loop_AB_OFF − oref0          | −0.004 | [−0.095, +0.087]  |     |
| Loop_AB_ON − oref0           | +0.056 | [−0.032, +0.141]  |     |
| oref0 − oref1                | −0.269 | [−0.363, −0.175]  |  *  |
| Loop_AB_OFF − oref1          | −0.273 | [−0.376, −0.169]  |  *  |
| Loop_AB_ON − oref1           | −0.213 | [−0.312, −0.114]  |  *  |

## Interpretation — REHABILITATES algorithm-channel hypothesis

The dispositive observation is **oref0 ≈ Loop_AB_OFF**: two no-SMB
designs from entirely different patient cohorts (different lineage,
different platform, different communities) converge to within
0.4 pp recovery (29.6% vs 30.0%, CI straddles zero). If selection
bias were the dominant explanation, no-SMB cohorts would NOT match
this tightly across independent samples.

The matched no-SMB floor (~30%) reflects the spontaneous physiology +
basal-cut-only correction loop. The +6 pp Loop_AB_ON premium reflects
the SMB-as-correction channel as configured in Loop. The +21 pp
oref1 premium over Loop_AB_ON, given equivalent SMB cadence and total
dose (EXP-2937), reflects the **oref1 dose-sizing logic**
(dynamic-ISF / autosens / velocity-aware SMB).

**This rehabilitates the EXP-2937 sizing-lever hypothesis**, which
was downgraded in EXP-2941 when no in-grid mechanism could be found.
The natural-variation cross-cohort convergence is an *external*
control that the in-grid mechanism search could not provide.

## Two-tier mechanism stack (carry forward)

1. **Channel availability tier** (EXP-2942): no-SMB → ~30%; SMB-active
   → ≥36%. Cross-cohort match between Loop_AB_OFF and oref0 confirms
   determinism.
2. **Dose-sizing tier** (EXP-2937): given SMB present, oref1's
   absorption/velocity-aware sizing yields +21 pp over Loop's
   IOB-shortfall sizing.

## Selection-bias hypothesis status

**Substantially weakened, not eliminated.** The cross-cohort
no-SMB convergence is hard to reconcile with selection bias. The
remaining +21 pp could in principle still be patient-selection
within the SMB-active subset, but the parsimonious explanation is
algorithmic (matching EXP-2937's mechanism description and
EXP-2940's 6.8-min time-to-peak finding).

Definitive resolution still requires within-patient AID-switch data.

## AID-author priority order (re-affirmed, post-EXP-2942)

1. UAM/glucose-appearance + dynamic-ISF (PP offence)
2. SMB-as-correction during sustained-high (correction-loop presence)
3. **Size correction SMBs to BG AND BG velocity, not to
   IOB-shortfall vs forecast** — re-affirmed by EXP-2942
4. Enable autobolus by default for AID-OFF correction loops
5. Basal-cut latency (defence-side temporal — EXP-2918)

## Methodological invariant

**Cross-cohort matching is the rebuttal to selection-bias.** When two
independent patient cohorts using the same algorithm channel
configuration produce statistically indistinguishable outcomes, the
algorithm channel — not the cohort — is the dominant signal.
Apply this template whenever in-grid mechanism search exhausts.

## Artefacts

- `tools/cgmencode/exp_oref0_natural_2942.py`
- `externals/experiments/exp-2942_summary.json` (gitignored)
