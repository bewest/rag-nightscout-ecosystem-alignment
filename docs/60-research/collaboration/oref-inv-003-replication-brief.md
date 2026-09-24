# OREF-INV-003: our replication, and an 18-feature algorithm-neutral set

**Status:** living document, revised 2026-09-24. EXP-2519 numbers are from
`tools/oref_inv_003_replication/results/exp_2519_grouped_cv.json`, produced 2026-09-24 by
`exp_repl_2519.py` over the training grid in `externals/ns-parquet/training/`. Rerun the
script rather than copying a number from here.

**For:** tim2000s, author of OREF-INV-003 ("What Drives Outcomes in oref Closed-Loop Insulin
Delivery"), and anyone extending it. Start page for the wider collaboration:
[`README.md`](README.md).

This is data analysis about how well models predict glucose outcomes from logged data. It is
not advice about anyone's settings, and none of it should be read as a recommendation to change
therapy.

## 1. Summary

- We replicated OREF-INV-003's feature-importance findings on an independent, mostly Loop
  cohort: 5 of 11 findings strongly agree, 3 agree, 3 partially agree, none disagree
  (`tools/oref_inv_003_replication/reports/synthesis_report.md`).
- In April we found that an **18-feature, algorithm-neutral set** (glucose, its rate of change
  and acceleration, time of day, and 13 channels computed from insulin and carb
  pharmacokinetics) scored higher than the 32-feature OREF set: 4-hour hypo AUC 0.815 vs 0.803
  (EXP-2514).
- That comparison used row-shuffled cross-validation, which mixes each patient's decisions
  across train and test folds: the leakage your own leave-one-user-out analysis measured, and
  which our EXP-2432 had already reproduced for the 32-feature set (hypo 0.80 vs 0.67). Under
  **patient-grouped** folds (EXP-2519), every feature set falls to hypo AUC 0.67 to 0.69 and
  hyper 0.77 to 0.80, in line with your leave-one-user-out 0.67 and 0.78.
- Under patient-grouped folds, **the 18-feature set performs on par with the 32-feature set**:
  ahead on the larger cohort (31 patients: +0.027 hypo, +0.031 hyper, 4 of 5 folds each), mixed
  on the April cohort (19 patients: −0.008 hypo, +0.018 hyper). Parity, not an improvement.
- Parity matters because the 18 features need **no oref decision record**: no `suggested.*`, no
  `reason` text. They are built from glucose, treatments, profile schedules and total IOB,
  which every AID controller writes to Nightscout. A model on that set could be trained and
  applied across Trio, AAPS, OpenAPS and Loop users alike. Your warehouse is where that can be
  tested at the scale it needs.

## 2. What we replicated

**Our data.** The training grid built by `tools/ns2parquet` from Nightscout exports:

| Cohort | Patients | Composition | Rows (4h labels) |
|---|---|---|---|
| April (EXP-2401 to 2518) | 19 | 11 Nightscout sites (mostly Loop), 8 AAPS from the OpenAPS Data Commons | 666,934 |
| Current | 31 | the 19, plus 12 sites from our Dynamic-ISF cohort | 1,143,127 |

**Scorecard** against your findings F1 to F10 (F5 split into F5a and F5b):

| | Your finding | Ours |
|---|---|---|
| F1, F2 | `cgm_mgdl` top for hypo and hyper | agree / strongly agree |
| F3 | `iob_basaliob` #2 for hypo | partially agrees: #12 without PK features, #10 with them, #9 for AAPS patients only |
| F4 | hour #2 for hyper | partially agrees |
| F5a, F5b | user-controllable settings about 36% of hypo importance; eventualBG R² about 0 at 4h | strongly agree (settings 25 to 28% here; eventualBG R² negative) |
| F6, F8, F9 | settings about 28% of hyper; ISF and CR top-5 hypo; bg_above_target top-5 hyper | agree / agree / strongly agree |
| F7 | CR × hour the strongest interaction | strongly agrees (ISF × hour top in our data) |
| F10 | rankings stable | partially agrees: SHAP ρ = 0.609 with PK; CR × hour ranked #9 in training and #1 in verification |

Best SHAP rank correlation with your hypo ranking: ρ = 0.679 (p = 0.008), with per-patient DIA
fitting (EXP-2541).

**Where our method differs from yours**, each a reason a number may not transfer:

- Most of our patients run Loop, not oref. Loop writes no `suggested` or `reason` fields, so 5 of
  your 32 features are approximated here (`iob_basaliob`, `iob_bolusiob`, `iob_activity`,
  `reason_Dev`, `reason_BGI`) and 2 are constants (`maxSMBBasalMinutes`,
  `maxUAMSMBBasalMinutes`). See `FEATURE_QUALITY` in
  `tools/oref_inv_003_replication/data_bridge.py`.
- `pk_bridge.py` replaces the 5 approximations with values computed from insulin and carb
  pharmacokinetics, using a fixed DIA of 5 h and peak of 55 min for every patient.
- SHAP rankings use 50,000-row samples.

## 3. The 18-feature set

| Group | Features |
|---|---|
| Glucose | `cgm_mgdl`, `glucose_roc`, `glucose_accel` |
| Time | `time_sin`, `time_cos` |
| PK replacements for the approximated features | `pk_basal_iob`, `pk_bolus_iob`, `pk_activity`, `pk_dev`, `pk_bgi` |
| PK channels with no OREF counterpart | `pk_insulin_total`, `pk_insulin_net`, `pk_basal_ratio`, `pk_carb_rate`, `pk_carb_accel`, `pk_hepatic_prod`, `pk_net_balance`, `pk_isf_curve` |

Definitions: `tools/oref_inv_003_replication/pk_bridge.py` (`get_pk_only_features`,
`PK_REPLACEMENT_FEATURES`, `PK_AUGMENTATION_FEATURES`) and `tools/cgmencode/continuous_pk.py`.

**Inputs it needs.** Grid columns `glucose`, `bolus`, `bolus_smb`, `carbs`, `net_basal` or
`actual_basal_rate`, `scheduled_basal_rate`, `scheduled_isf`, `scheduled_cr`, and `iob`. In
Nightscout terms: `entries.sgv`; treatments boluses, SMBs, carbs and temp basals; `profile`
basal, ISF and carb-ratio schedules; and total IOB from devicestatus (`openaps.iob.iob` or
`loop.iob.iob`). Only `pk_hepatic_prod` and `pk_net_balance` read the reported IOB; it can also
be recomputed from treatments.

### 3.1 Results

4-hour outcomes, LightGBM (500 trees, depth 6), 5 folds. **Row**: `StratifiedKFold(shuffle=True)`
over decisions, as EXP-2511 to 2514 used. **Patient**: `StratifiedGroupKFold` by patient, so no
patient appears in both train and test.

| Cohort | Outcome | Feature set | Row AUC | Patient AUC ± fold SD |
|---|---|---|---|---|
| April (19) | hypo | OREF-32 | 0.803 | 0.677 ± 0.011 |
| | | OREF-32, PK replacements | 0.813 | 0.685 ± 0.023 |
| | | **18 algorithm-neutral** | 0.815 | **0.669 ± 0.025** |
| | hyper | OREF-32 | 0.901 | 0.778 ± 0.031 |
| | | OREF-32, PK replacements | 0.905 | 0.779 ± 0.039 |
| | | **18 algorithm-neutral** | 0.907 | **0.796 ± 0.013** |
| Current (31) | hypo | OREF-32 | 0.792 | 0.666 ± 0.025 |
| | | OREF-32, PK replacements | 0.799 | 0.681 ± 0.025 |
| | | **18 algorithm-neutral** | 0.798 | **0.692 ± 0.024** |
| | hyper | OREF-32 | 0.892 | 0.768 ± 0.038 |
| | | OREF-32, PK replacements | 0.894 | 0.773 ± 0.038 |
| | | **18 algorithm-neutral** | 0.894 | **0.799 ± 0.022** |

Base rates: hypo 23.5% (April) and 25.7% (current); hyper 55.1% and 47.7%.

**Paired by fold** (the folds are identical across feature sets), 18-feature minus OREF-32:

| Cohort | Hypo: per-fold difference | Mean | Hyper: per-fold difference | Mean |
|---|---|---|---|---|
| April (19) | −0.004, −0.002, +0.026, −0.033, −0.029 | −0.008 | −0.001, +0.055, +0.014, −0.028, +0.048 | +0.018 |
| Current (31) | −0.019, +0.030, +0.005, +0.036, +0.081 | +0.027 | +0.050, +0.086, +0.004, +0.015, −0.001 | +0.031 |

### 3.2 How to read it

- The row-shuffled numbers reproduce April exactly (0.8031, 0.8126, 0.8148), so the code and
  data are unchanged. The row-to-patient drop, 0.11 to 0.15 for hypo and 0.10 to 0.12 for hyper,
  is the same size as the 5-fold to leave-one-user-out gap in your own analysis (about 0.16 and
  0.10), and the patient-grouped OREF-32 hypo AUC matches our April leave-one-patient-out
  figure (EXP-2432, 0.67).
- The April "improvement" of +0.012 was smaller than the leakage it sat inside. It does not
  survive as an improvement.
- What does survive: removing every oref-specific input and 14 features costs nothing
  measurable on unseen patients, and on the larger cohort the 18-feature set is slightly
  ahead. With 19 to 31 patients and fold SDs of 0.01 to 0.04, that is a statement of parity.
- These are 5 grouped folds, not leave-one-user-out; each fold holds out about 4 to 6 patients.

## 4. What your data could settle

Your warehouse has what ours lacks: oref users with logged `suggested` and `iob` fields, so
none of the 32 features is approximated, and years of history per user. Each experiment below
returns pooled aggregates only (AUCs per fold, ranks, correlations), and its result file should
pass `python3 -m nsprobe check`.

| Id | Experiment | What it settles |
|---|---|---|
| E1 | EXP-2519's three feature sets on your cohort, leave-one-user-out | whether 18-feature parity holds with logged, not approximated, OREF features, on oref users |
| E2 | our PK reconstructions against your logged `iob_basaliob`, `iob_bolusiob`, `iob_activity`, `reason_Dev`, `reason_BGI` (MAE, bias, rank correlation) | how good `pk_bridge.py` is; nsprobe task T4a |
| E3 | the 18-feature set plus your 6 lag features (0.6746 to 0.6902 leave-one-user-out on the 32) | whether the lag signal, strongest for 2-hour cumulative insulin, is already in `pk_insulin_total` and `pk_activity` |
| E4 | `iob_basaliob` hypo rank under leave-one-user-out, logged vs PK | F3, the one finding we could not reproduce |
| E5 | CR × hour interaction rank across time splits | F10 stability |
| E6 | leave-one-user-out over-prediction (your mean +9 pp hypo, +11 pp hyper) with the 18-feature set | whether a feature set with no algorithm-specific inputs carries less cohort prior into unseen users |

**Running ours on your data.** From raw Nightscout exports:

```bash
PYTHONPATH=tools python3 -m nsprobe layout --src <raw> --dest <corpus> --key <private>/key.json
PYTHONPATH=tools python3 -m ns2parquet convert-all -d <corpus>/v1 -o <parquet> -q
PYTHONPATH=tools python3 -m oref_inv_003_replication.exp_repl_2519 \
    --parquet-dir <parquet> --out <out>/tasks/exp_2519.json
PYTHONPATH=tools python3 -m nsprobe check <out>
```

Both cohorts here (1.1 million and 0.67 million rows) took 11 minutes on one machine. The result holds AUCs, fold values and
cohort counts, and names no patient. For E1 with your own logged OREF features, map your
decision-table columns onto `OREF_FEATURES` in `data_bridge.py`, which follows the same
`sug_*`, `iob_*`, `reason_*` naming as your tables (case differs in places: `sug_COB` here,
`sug_cob` in `boost_decisions`).

## 5. Why this belongs in the alignment work

The 18-feature set is a practical case for the schema work: a model whose inputs are
exactly the fields every controller writes and the schema describes. What the schema says
about those inputs today:

| Input | Schema evidence | Question that tests it |
|---|---|---|
| `entries.sgv`, `date` | measured on 11 sites; fractional `date` quirk | Q09 |
| bolus and SMB treatments | SMB marking differs by client; Trio uses `eventType: "SMB"` alone | Q04 |
| temp basals | Loop writes absolute + rate; oref clients unmeasured | Q05 |
| profile schedules | four spellings of units; schedule times need `profile.timezone` | Q06, Q07 |
| total IOB | `loop.iob.iob` measured; `openaps.iob` from one site | Q01, Q11 |

A larger corpus through `tools/nsprobe` answers those questions; the same corpus through
EXP-2519 answers whether the model built on them generalises. The two go together.

## 6. Corrections we made to our own record

- `synthesis_report.md` now agrees with its final scorecard on F3 (partially agrees) and in its
  executive summary.
- `tools/oref_inv_003_replication/reports/exp_2511_report.md` reports EXP-2512 and 2513 but not EXP-2514's numbers; they are in
  §3.1 above and in a status note at the top of that report.
- Every AUC in `tools/oref_inv_003_replication/reports/` except EXP-2431/2432 (leave-one-patient-out)
  and EXP-2519 is from row-shuffled cross-validation and carries the leakage described
  in §3.2. That includes the feature-set comparisons EXP-2511 to 2518.
