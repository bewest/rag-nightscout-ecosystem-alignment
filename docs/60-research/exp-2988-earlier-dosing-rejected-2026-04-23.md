# EXP-2988: Earlier-dosing hypothesis at sustained-high — REJECTED

**Date**: 2026-04-23
**Audience**: open-source AID code authors (Loop)
**Scope**: Test whether peers c/d/e/g fire SMBs DURING the
100-140 ascent immediately preceding a 70-100 entry, dosing the
rise BEFORE it matters and explaining their quiescence at 70-100.
Compared per-patient pre-entry SMB rate (last 60 min) and
marginal 100-140 ascent SMB rate.
**What this is NOT**: not a control-system simulation; not a
mechanistic prediction reconstruction. Observational only.

---

## 1. Per-patient table

```
patient n_70_100_entries  pre_entry_ascent_cells  smb_fired  pre_entry_rate  marginal_ascent_cells  marginal_smb  marginal_rate
c             1050                  1373            231           0.1682              4723                1504           0.3184
d              808                  2004            922           0.4601              6760                2906           0.4299
e              703                  1120            341           0.3045              4637                2155           0.4647
g             1329                  2431            854           0.3513              6831                2912           0.4263
i             1255                  1758            985           0.5603              4569                2655           0.5811
```

i pre_entry_fire_rate = **0.5603** vs peer-mean = **0.3210**
i marginal_ascent_rate = **0.5811** vs peer-mean = **0.4098**

---

## 2. Findings

1. **Patient i fires MORE in 100-140 ascent**, both pre-entry
   (56% vs 32%) and marginally across all 100-140 ascent cells
   (58% vs 41%). This is the OPPOSITE direction predicted by
   the earlier-dosing hypothesis.
2. **Combined with EXP-2987**, this confirms patient i is
   uniformly more aggressive across all glucose bands — there is
   no temporal-strategy difference (peers don't pre-empt the rise),
   only an absolute rate difference at every band.
3. **Therefore the EXP-2979 "Loop overshoot" reframe stands as
   in EXP-2985**: the 10.7% overshoot signal is concentrated in
   the single Loop_AB_ON patient who is configured aggressively
   across the board, not in a time-of-dose strategy.

---

## 3. Code references

- `tools/cgmencode/exp_earlier_dosing_2988.py` — this experiment

---

## 4. Verdict

**NEGATIVE — earlier-dosing hypothesis REJECTED.** Peers do not
pre-empt 70-100 by dosing the rise; they simply fire less at
every band, including the ascent into 70-100. The patient-i-vs-
peer asymmetry is not a temporal-strategy difference — it is a
uniform-aggressiveness difference, supporting the synthesis
re-framing of EXP-2979 as a single-configuration finding rather
than a population-level Loop magnitude lever.

Output: `externals/experiments/exp-2988_summary.json`.
