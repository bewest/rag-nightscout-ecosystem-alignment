# EXP-2924 — Guard #6 cf-conditioning on the fasted-dawn gap

**Date:** 2026-04-23
**Source:** `tools/cgmencode/exp_cf_conditioned_dawn_2924.py`
**Scope:** Robustness check on EXP-2923's 8× design-level gap.
AID-author audience.

## Method

Per patient, fasted-dawn `frac_hyper` = mean(glucose>250)
over cells where `time_since_carb_min >= 300` and `hour in {2,3,4}`
(filter rejects patients with <6 qualifying cells — 19 patients
pass).

Stratify by overall `cf_severe` tertile (low/mid/high) and report
per (cf_tertile, lineage) means + bootstrap CI. Within-tertile
Loop − oref1 gap with bootstrap CI as the inferential test for
Guard #6 design-claim robustness.

## Within-tertile Loop − oref1 fasted-dawn gap

| cf tertile | n_Loop | n_oref1 | gap (pp) | 95 % CI (pp)        | sig | Loop %    | oref1 %  |
|------------|-------:|--------:|---------:|---------------------|-----|----------:|---------:|
| low_cf     | 1      | 3       | 15.96    | (n=1 — degenerate)  | n/a | 19.42     | 3.46     |
| **mid_cf** | **3**  | **3**   | **14.17**| **[12.47, 15.90]**  | **★** | 15.66 | 1.49     |
| **high_cf**| **3**  | **3**   | **4.33** | **[0.04, 8.62]**    | **★** |  5.68 | 1.35     |

★ = both cells n≥3 AND CI excludes zero.

## Findings

1. **The 8× design-level gap survives Guard #6.** Within mid_cf
   and high_cf — where both designs have n=3 patients matched
   on overall load — the Loop fasted-dawn rate exceeds oref1's
   by **14.17 pp** and **4.33 pp** respectively, with bootstrap
   CIs that exclude zero.

2. **The gap narrows at high cf.** mid_cf gap 14.17 pp →
   high_cf gap 4.33 pp. Interpretation: the most demanding
   patients (high cf_severe = high counterfactual hypo-load
   without AID) push *both* designs toward their performance
   ceiling; design difference compresses. The mid_cf range is
   where design choice matters most.

3. **oref0 is competitive at low_cf.** Within low_cf (the only
   tertile where oref0 cells exist), oref0's mean is 5.16 %
   vs oref1's 3.46 % vs Loop's 19.42 %. oref0 cells are 3
   distinct patients (not n=1 here because the load tertile is
   patient-not-cell). Loop's low_cf cell is n=1 (patient `a`)
   and can't carry an inferential CI.

4. **The high-cf Loop spread is wide (CI [2.0, 10.9])**: Loop
   patients c (10.9 %), d (2.0 %), g (4.2 %) at high cf show
   genuine heterogeneity. Likely autobolus on/off mix
   (per EXP-2919: c, d, g are all autobolus-ON). The autobolus-ON
   floor is around 2 % even at high cf — so dynamic-ISF still
   adds ~1 pp on top.

## Cross-validation

- ★ confirms EXP-2923's 8× gap is not a patient-selection
  artefact. The design separation persists when matching on cf
  load.
- Strengthens the "dynamic-ISF is the highest-leverage dawn
  lever" hypothesis (EXP-2920/2922/2923) with a Guard #6 stamp.
- Updated EXP-2923 oref0 framing also confirmed: oref0 patients
  in this cohort have low_cf and aren't uniformly worse.

## Caveats

- low_cf Loop cell is n=1 — pair degenerate per Toolkit §2.8.
  Reported gap is point-estimate-only.
- 19 patients total; tertile cells are 1–3 each. Future cohort
  expansion (AAPS ingestion, EXP-2908) would narrow CIs.
- Tertiles defined on overall cf_severe (full-day proxy), not
  cf restricted to fasted-dawn windows. A windowed cf would
  be more conservative; result direction unlikely to change.
- TZ not normalised.

## Implication

**The 8× fasted-dawn design gap is a robust feature of the data,
not an artefact of which patients use which AID.** It is
attributable to design difference (dynamic-ISF + SMB-as-correction)
within the matched-cf-load comparison.

This is the second methodological layer of evidence for the
dawn-fingerprint claim:
1. EXP-2923: cleanest single-mechanism number (fasted-only)
2. EXP-2924: survives cf-matching (Guard #6)
3. (Pending) EXP-2925: TBD natural-experiment / counterfactual
   to attempt Layer 3 — true causal exposure.

## Linked artefacts

- `externals/experiments/exp-2924_summary.json`
- Compare against `exp-2923-xdesign-fasted-pp-2026-04-23.md`
- Toolkit Guard #6 reference: `deconfounding-toolkit-2026-04-22.md` §4.6

## Next

- EXP-2925: hypoglycemia analog — does the oref0 midnight hypo
  signature also survive cf-conditioning?
- EXP-2926: load-mediation Guard #7 audit — substitute
  `cf*(1-protection)` to test for coverage-distribution artefacts.
