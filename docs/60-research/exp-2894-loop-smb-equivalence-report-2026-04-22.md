# EXP-2894 — Loop Automatic-Bolus vs oref1 SMB: Functional Equivalence

**Date:** 2026-04-22
**Stream:** Lineage-label refinement
**Status:** Loop automatic-bolus and oref1 SMB are functionally
equivalent in size and frequency; BUT 2 of 7 "Loop" patients
are legacy open-loop-only (zero SMBs).

## 1. Question

EXP-2893 labelled Loop's `bolus_smb` events as SMB-equivalent and
reported 42 % SMB fraction for Loop.  Is Loop's
"automatic-bolus" behaviour distinguishable from oref1 SMB?

## 2. Method

All rows in `ns-parquet/training/grid.parquet` with
`bolus_smb > 0`, grouped by lineage label from EXP-2891.

## 3. Results — size & frequency distribution

| Lineage | n events | mean (U) | median | 75% | 95% | per day |
| ------- | -------- | -------- | ------ | --- | --- | ------- |
| Loop    | 56 371 | 0.295 | 0.15 | 0.35 | 0.95 | 64.5 |
| oref1   | 67 565 | 0.313 | 0.20 | 0.40 | 1.00 | 53.3 |
| unknown | 39 268 | 0.247 | 0.15 | 0.30 | 0.75 | 49.5 |

Loop's automatic bolus is **slightly smaller and slightly more
frequent** than oref1 SMB but the distributions are
indistinguishable in rank order.  Treating them as the same
channel in cohort analysis is defensible.

## 4. Within-lineage stratification — the legacy-Loop cohort

Per-patient total SMB volume (U, over ~375 days):

| Patient | Lineage | Tercile | SMB (U) | Protection |
| ------- | ------- | ------- | ------- | ---------- |
| `a`     | Loop    | conservative | **0.00** | 0.453 |
| `f`     | Loop    | moderate | **0.00** | 0.639 |
| `g`     | Loop    | moderate | 1 734 | 0.635 |
| `d`     | Loop    | conservative | 2 350 | 0.519 |
| `c`     | Loop    | aggressive | 2 905 | 0.568 |
| `e`     | Loop    | aggressive | 3 514 | 0.648 |
| `i`     | Loop    | aggressive | 6 132 | 0.531 |

Two Loop patients (`a`, `f`) have **zero SMBs across the entire
record** — **Loop's automatic-bolus is a user-toggleable feature**
(and was absent entirely from Loop versions before 3.x).  These
patients have it disabled or are running legacy Loop.  Their
protection values are comparable to the SMB-enabled Loop patients
because Loop's basal-cut utilization (86–95 %) already delivers
most of the hypo protection; SMB mainly adds value on the hyper
side.

## 5. Implication for EXP-2891/2892/2893 re-interpretation

- Lineage label "Loop" is heterogeneous: 5/7 with automatic-bolus
  enabled, 2/7 disabled.  (Loop's automatic bolus is an opt-in
  feature per user preference, separate from Loop version.)
  Splitting would yield:
    Loop + autobolus (n=5):  frac_smb 0.59
    Loop − autobolus (n=2):  frac_smb 0.00
- The oref0 vs Loop-legacy comparison is apt: both have
  zero SMB.  But Loop-legacy still has basal-cut
  utilization ~86–91 %, so conservative Loop-legacy
  (patient `a`, protection 0.45) remains much better
  protected than conservative oref0-legacy
  (patient `odc-86025410`, protection 0.13).
- Conclusion: **SMB capability is not the whole story** —
  basal-cut responsiveness is the dominant differentiator
  on the hypo side, and it's separable from SMB.

## 6. Updated mechanism matrix

| Lineage (refined) | n | basal-cut util | SMB frac | Protection |
| ----------------- | - | -------------- | -------- | ---------- |
| oref1 (modern)     | 9 | 0.92 | 0.47 | 0.67 |
| Loop + autobolus   | 5 | ~0.91 | 0.59 | 0.59 |
| Loop − autobolus   | 2 | ~0.88 | 0.00 | 0.55 |
| oref0 (legacy)     | 3 | 0.20–0.75 | 0.00 | 0.41 |
| unknown            | 5 | 0.91 | 0.37 | 0.68 |

The remediation tree is now:

```
If protection < threshold:
  if basal-cut utilization is low (< 0.6):
    -> algorithm responsiveness failure
       => migrate to oref1-family
  elif SMB fraction is zero:
    -> missing SMB channel (can lead to hyper-side TIR loss
       even if hypo protection is adequate)
       => upgrade Loop ≥3.x or migrate to oref1
  else:
    -> setting / phenotype issue; apply settings-tuning advice
```

## 7. Actionable advice — updated

- For **Loop users with automatic-bolus off** (`a`, `f`):
  consider enabling the feature.  Trade-off: gives up some
  hands-on meal-bolus control in exchange for ~59 % of hyper
  corrections being automated.  Protection will rise modestly
  on the hypo side (already good) and substantially on the
  hyper side (from 0 % automatic correction to ~59 %).
- For **audition matrix**: add a `smb_absent_algorithm_gap` flag
  distinct from `lax_braking_controller_efficacy`.  The oref0
  patient fires both; the legacy-Loop patients fire only this
  new one.

## 8. Caveats

- n=2 legacy-Loop patients and n=3 oref0 patients are both
  underpowered; directional reading only.
- Loop 3.x is in some patients' data only for the latter portion
  of the time range — the label is time-averaged.  A time-split
  would reveal within-patient upgrade effects and is an obvious
  follow-up.
- We cannot distinguish "SMB unused during this specific event"
  from "SMB unavailable in this patient's algorithm version" at
  the event level; the per-patient `total == 0` test is the
  only clean version split.

## 9. Artifacts

- Per-patient SMB totals computed inline from
  `externals/ns-parquet/training/grid.parquet`
- `docs/60-research/exp-2894-loop-smb-equivalence-report-2026-04-22.md`

## 10. Next

- Audition matrix wiring: add `smb_absent_algorithm_gap` flag
- EXP-2895: within-patient time-split for legacy-Loop users —
  did they upgrade mid-record and did protection step?
