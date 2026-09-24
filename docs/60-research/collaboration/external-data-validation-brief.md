# External data validation: a brief for Nightscout data holders

**Status:** living document. Baseline numbers are from `reports/nsprobe/baseline/`, generated
2026-09-23 at commit `234253d1` from this repository's 2026-04-01 snapshot (11 sites).
Regenerate with `make nsprobe-baseline` rather than copying a number from here.

**Audience:** researchers who hold their own collection of Nightscout sites or OpenAPS/oref
logs, and the coding agents they work with. It was written with the tim2000s repositories in
mind (oref-digital-twin, Insulin-Kinetics, dynamic-isf-calculations, Smoothing-Investigations,
exercise-eval, clinical-advice-analysis), and applies to any holder.

This work is about the shape of stored data: field names, types, how often each form occurs,
which client writes it. It does not evaluate anyone's therapy settings or dosing, and nothing
here is medical advice.

## 1. What we are asking

This repository publishes schemas, a quirks registry and data-pipeline heuristics for the
Nightscout ecosystem (`specs/`, `specs/quirks/`, `tools/ns2parquet/`). They were measured on a
corpus that is too small and too uniform to settle many of the claims built on it. We ask a
data holder to run a fixed set of aggregate-only probes on their own data, on their own
machine, and, if they choose, return the aggregate results. The kit is `tools/nsprobe/`.
Instructions for a coding agent are in
[`tools/nsprobe/AGENTS.md`](../../../tools/nsprobe/AGENTS.md), and the questions in
[`tools/nsprobe/questions.yaml`](../../../tools/nsprobe/questions.yaml).

## 2. Why another corpus changes the answers

| | This repository's corpus | What a larger oref corpus adds |
|---|---|---|
| Sites | 11 | tens to hundreds |
| Closed-loop clients | 9 Loop, 1 Trio, 1 none | AAPS, Trio, iAPS, OpenAPS rigs, AAPS forks |
| Pumps | 10 of 11 Insulet Dash | other pumps and their `pump.*` shapes |
| API | fetched through v1 only | v3 envelope (`identifier`, `srvModified`, `isValid`), `/history` |
| Time span | two snapshots 25 days apart | years, so fields can be dated by client version |
| Activity | no `activity` collection on any site | heart rate and steps, if uploaded |

The consequences are specific. Every `openaps.*` path frequency in the devicestatus spec comes
from one Trio site. Four of the devicestatus quirks rest on that one site. Every AndroidAPS
statement in the specs was read from source code, not observed. The heart-rate and activity
models have never been checked against data. Source:
[`nightscout-typed-schema-evidence-2026-09-10.md`](../../30-design/platform/nightscout-typed-schema-evidence-2026-09-10.md)
§1.2 and §10.

Aggregate cohort figures from the holder's public repositories show the difference in scale:
31 adults (9 AndroidAPS, 22 Trio) in Insulin-Kinetics; 171 users (23 Trio, 39 AAPS, 109
OpenAPS) in dynamic-isf-calculations.

## 3. What the holder runs, and what comes back

Three tracks. A holder can do any subset.

| Track | Input | Command | Answers |
|---|---|---|---|
| A | raw REST exports per site (v1, and v3 if available) | `nsprobe layout`, `run`, `census` | Q00 to Q14, Q16, Q17 |
| B | a flattened SQL warehouse (one row per decision, per treatment) | `nsprobe warehouse` | Q00, Q04, Q08, Q11, Q15 to Q17 |
| C | the holder's own analysis code | tasks T1 to T5 in AGENTS.md | Q00, Q07, Q08, Q15 to Q17 |

What comes back is a directory of JSON files holding counts, shares and the number of sites
that contributed to each. The rules:

- No document, row, timestamp finer than a calendar quarter, free-text value, device string or
  site name. Sites are renamed `S001`, `S002`... by `nsprobe layout`, and the key stays with
  the holder.
- A value (an eventType, a field path, a pump model) is named only if at least 3 sites wrote
  it. Everything else is folded into one `_other` count.
- `nsprobe check` scans every file for URLs, emails, hostnames, identifiers and timestamps, and
  the probes will not write a file that fails.
- This repository is public. A result contributed here is published. The holder decides
  whether to send results, and whether publicly or privately.

## 4. The questions

Each has a claim in this repository behind it; `questions.yaml` names the file.

| Id | Question | This repository's corpus shows |
|---|---|---|
| Q00 | Which clients wrote the data, by one rule on every data set | 9 Loop, 1 Trio, 1 no loop |
| Q01 | Is `openaps.*` one shape across AAPS, Trio, iAPS, oref0 rigs | one site writes it |
| Q02 | Prevalence of the oref-family devicestatus quirks | each rests on 1 site |
| Q03 | The eventType vocabulary and who writes each value | 14 values, 6 on 3+ sites |
| Q04 | How SMBs are marked; does "automatic and under 5 U" find them | Trio marks SMBs by `eventType: "SMB"` alone; the size rule finds none of its 9,977 |
| Q05 | Temp basal representation | Loop writes `absolute`, `rate`, `duration` together; fractional duration on 99% |
| Q06 | mmol/L prevalence; does "ISF under 15 means mmol/L" hold | 26 of 61,368 ISF values on an mg/dL site are under 15 |
| Q07 | Do `utcOffset` and the ISO timestamp agree | yes, except xDrip-family entries: UTC ISO string with local `utcOffset` |
| Q08 | Duplicates that `_id`-only deduplication misses | 2 sites: same reading from two Share-family uploaders within 5 s, 59,827 entries (about 9% of entries) |
| Q09 | Are fractional `date` and `direction: NONE` client-specific | fractional on 10 sites, NONE on 5 |
| Q10 | Declared paths never observed | 30 across four collections |
| Q11 | Are oref0 dosing inputs recorded (`maxIob`, IOB split, `lastTemp`) | `maxIob` recorded nowhere |
| Q12 | Other pumps and uploaders | one pump family dominates |
| Q13 | The v3 envelope in real data, and v1/v3 identifier agreement | never measured |
| Q14 | Field appearance over years | 25 days of data |
| Q15 | OREF-INV-003 findings with logged, not approximated, IOB features | 5 of 32 features approximated |
| Q16 | Heart rate and steps: which apps, which keys, what cadence | no activity data |
| Q17 | Where AAPS-fork step counts live | not present |

## 5. Where this work and the holder's overlap

| Holder's repository | This repository | What each gives the other |
|---|---|---|
| oref-digital-twin | [`PROPOSAL-replay-fidelity-changes-2026-09-11.md`](../../30-design/platform/PROPOSAL-replay-fidelity-changes-2026-09-11.md), `specs/nsschema/dosing-input-sources.yaml` | the twin needs `maxIob` and the input vector that no uploader records; Q01 and Q11 measure what is recorded |
| Insulin-Kinetics | `tools/oref_inv_003_replication/pk_bridge.py`, `tools/cgmencode` PK work | logged `basaliob`/`bolusiob` test our PK approximations (T4); our dedup and SMB findings bear on its dose extraction |
| dynamic-isf-calculations | `externals/ns-parquet-dynisf-v2` (12 sites), `algorithm_isf`/`algorithm_tdd` columns | Q06 tests the ISF unit rule both codebases use; T5 measures the UTC-hour lookup |
| Smoothing-Investigations | `specs/quirks/entries.yaml`, the duplicates probe | its device-ranked dedup and our Q08 measure the same cross-uploader duplicates |
| exercise-eval | `specs/nsschema/activity.model.json`, `specs/openapi/aid-heartrate-2025.yaml` | Q16 gives the activity model its first measurement |
| clinical-advice-analysis | `conformance/assertions/sync-deduplication.yaml` | its duplicate-entry analysis is the same finding as our Q08 baseline |

AGENTS.md lists, with file references, the places where the holder's code reads Nightscout
differently from how the uploaders write it (the `openaps://` AAPS device string, the 4-day v1
default, UTC-hour schedule lookup, `isBasalInsulin`, `_id`-only deduplication). They are
read-from-code observations for the holder to check.

## 6. What this repository does with results

1. `nsprobe compare <out>` sets the holder's numbers beside ours: quirk prevalence against each
   quirk's claimed minimum, declared paths the holder observes, enum values that reach the
   3-site threshold, and the probe results.
2. Each change to a spec, quirk, primitive grade or pipeline heuristic that follows is a
   reviewed commit citing the result file and the contributor label.
3. Results sent privately stay out of this repository; a change they motivate cites them as
   "private communication, <label>, <date>".

## 7. Changes this work has already made here

Found while building and baselining the kit, and applied in the same change:

- `tools/ns2parquet/normalize.py` `_is_smb` also recognises `eventType: "SMB"` (Trio) and
  `isSMB: true` (AAPS), as its docstring already said it did. The training parquet built before
  this change flags 1,521 of its 91,369 `eventType: "SMB"` treatments as `is_smb`, so it needs a
  rebuild. No analysis reads `is_smb`; the grid's `bolus_smb` column has its own rule in
  `grid.py` and already counted them.
- `tools/nsschema/diff.py` no longer fails when the census withholds a numeric minimum or
  maximum (fewer than 20 observations), which a smaller external corpus triggers.
- `tools/nsschema/corpus.py` and `replay.js` accept `NSSCHEMA_CORPUS`, so the whole schema
  pipeline runs over a corpus outside `externals/`.
- `mapping/xdrip-android/data-models.md` shows the activity documents xDrip actually uploads
  (`type: "hr-bpm"` with `bpm`, `type: "steps-total"` with `steps`).
- `tools/oref_inv_003_replication/reports/synthesis_report.md`: the F3 section and executive
  summary agree with the final scorecard.

## 8. Contact

Ben West, maintainer. Results, questions, or a request for a different probe: open an issue on
this repository (no data in it), or ask for a private channel.
