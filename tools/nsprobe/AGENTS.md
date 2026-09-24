# nsprobe: instructions for a coding agent working on a data holder's machine

You are running on the machine of someone who holds Nightscout data: raw exports from many
sites, a flattened analysis warehouse, or both. The Nightscout ecosystem alignment repository
(this repository) wants that data to confirm or correct the schema claims it measured on a
small corpus. **The data never leaves this machine.** What leaves is a directory of aggregate
JSON files that you generate with `nsprobe`, check with `nsprobe check`, and hand to the
person you work for. They decide whether to send it and where.

The questions, and the claim each one tests, are in [`questions.yaml`](questions.yaml). Read
it first.

## Rules that do not bend

1. **Raw data stays put.** Never copy documents, rows, CGM traces, profiles or device logs
   into a commit, an issue, a pull request, a chat message, a log you paste, or a file outside
   the data holder's own storage. This applies to this repository and to any repository of
   theirs.
2. **Only `nsprobe` output is returned.** If a task below needs a number that `nsprobe` does
   not produce, compute it as a pooled aggregate (counts, shares, rank correlations), apply
   the same site threshold (a value is named only if at least 3 sites or users produced it),
   and write it as JSON in the result directory so `nsprobe check` scans it.
3. **Run `python3 -m nsprobe check <out>` last, and stop if it fails.** Fix the cause, never
   the checker.
4. **Secrets come from the environment.** The warehouse DSN is read from `$NSPROBE_DSN` (or
   the variable `dsn_env` names). Never write a DSN, API secret, token or site URL into a
   config file, script, commit or result.
5. **The site key is private.** `nsprobe layout` writes a file mapping `S001...` back to real
   site names. It identifies people. Keep it outside the corpus and outside the result
   directory, and never return it.
6. **Results may become public.** This repository is public. If the result directory is
   contributed here, every number in it is published. Tell the person you work for this
   before they send anything.
7. **This measures data shape, not therapy.** Nothing here evaluates whether anyone's
   settings or dosing are right, and no result should be phrased as if it did.

## Setup

```bash
git clone https://github.com/bewest/rag-nightscout-ecosystem-alignment
cd rag-nightscout-ecosystem-alignment
git checkout <commit named in the brief>      # results record the commit they ran at
python3 -m pip install pyyaml pytest          # plus psycopg (or psycopg2) for Track B
PYTHONPATH=tools python3 -m pytest tools/nsprobe/test_nsprobe.py -q   # synthetic data only
```

Run everything from the repository root with `PYTHONPATH=tools`.

## Track A: raw Nightscout documents

This track answers most questions. It needs one directory per site holding the REST
responses as returned.

### A1. Export (skip if the holder already has raw exports)

Per site, for `entries`, `treatments`, `devicestatus`, `profile`, `activity` and `food`, plus
`/api/v1/status.json` saved as `settings.json`:

- **API v1** (`/api/v1/<collection>.json`): always pass an explicit date filter. A v1 query
  with no date filter returns only the most recent 4 days (`lib/server/query.js`, the
  `deltaAgo` default). Page on `find[date][$gte]`/`$lt` for entries and on
  `find[created_at][$gte]`/`$lt` for the others, with a `count` large enough that no page is
  truncated. Pages must not overlap: `nsprobe layout` counts repeated `_id`s so an overlap
  shows up, but it cannot tell an overlap from a real repeat.
- **API v3** (`/api/v3/<collection>?limit=...&sort=date` or `/api/v3/<collection>/history/<ms>`),
  if the holder has v3 access. Save the responses as returned, envelope and all; `layout`
  unwraps `{"status","result"}`. A `/history` export includes soft-deleted documents
  (`isValid: false`), which is what probe Q13 counts.
- `activity` is served by v1 only.

Put them in `<raw>/<any-site-name>/<collection>.json`, or under `v1/` and `v3/`
subdirectories when both exist. A collection may be a directory of page files.

### A2. Lay out, probe, census, check

```bash
python3 -m nsprobe layout  --src <raw> --dest <corpus> --key <private>/site-key.json
python3 -m nsprobe run     --root <corpus> --out <out> --contributor <label>
python3 -m nsprobe census  --root <corpus> --out <out>
python3 -m nsprobe check   <out>
python3 -m nsprobe compare <out> > <out>/compare.md
python3 -m nsprobe check   <out>
```

`<label>` is a short lower-case name the holder chooses, for example `holder-a`. A smoke run
over a large warehouse: add `--max-docs 5000` to `run` and `census`.

`run` writes `<out>/nsprobe/*.json`, one file per probe. `census` writes
`<out>/schema-census-v1/` (and `-v3/`): this repository's own census, reconcile, quirks and
dosing-input reports, computed over the holder's corpus. `compare` prints where the holder's
corpus and ours disagree about a claim.

## Track B: a flattened warehouse

If the holder has already flattened Nightscout into analysis tables (one row per loop
decision, one per treatment), copy [`warehouse.example.yaml`](warehouse.example.yaml), set the
table and column names, and run:

```bash
export NSPROBE_DSN=...        # in the shell only
python3 -m nsprobe warehouse --config <config.yaml> --out <out> --contributor <label>
python3 -m nsprobe check <out>
```

The example config uses the column names in the holder's public Insulin-Kinetics code. A
missing column makes only the probe that needs it report `skipped` or `error`.

## Track C: analysis tasks in the holder's own code

These need the holder's code and judgement, not just `nsprobe`. Each writes one JSON file
under `<out>/tasks/` and follows rule 2. Do the ones the holder agrees to; skipping one is
fine, and saying so in `<out>/tasks/README.md` is enough.

- **T1: classifier agreement (Q00).** For each user, compare the holder's platform label
  (for example `platform_detect.py` in Insulin-Kinetics, `variant/signals.py` in
  oref-digital-twin) with `nsprobe.family.site_family` over that user's devicestatus.
  Return the agreement matrix (label pairs to user counts, pairs under 3 users folded).
- **T2: where step counts come from (Q16, Q17).** Find the code that fills the warehouse's
  step column (`steps_60m` in the example) and report the Nightscout collection and field
  path it reads, and which client writes that path. Paths and client names only, no values.
- **T3: duplicates in the holder's loaders (Q08).** Apply the `duplicates` probe's
  definitions to the holder's own ingestion: how many rows survive `_id`/`ns_id`-only
  deduplication but match another row by the probe's rules (same sgv from two devices within
  5 s; same eventType and dose within 60 s). Pooled counts per platform.
- **T4: OREF-INV-003 with logged IOB (Q15).** Our replication approximated `iob_basaliob`,
  `iob_bolusiob`, `iob_activity`, `reason_Dev` and `reason_BGI`
  (`tools/oref_inv_003_replication/data_bridge.py`, `FEATURE_QUALITY`) and recomputed some of
  them from insulin PK (`pk_bridge.py`). Where the warehouse logs them:
  (a) error of our approximations against the logged values (MAE, bias, rank correlation),
  pooled per platform;
  (b) the rank of `iob_basaliob` in hypo-prediction importance (finding F3) and the stability
  of the CR×hour interaction across time splits (F10). Report ranks and correlations only.
  (c) EXP-2519's three feature sets (OREF-32, OREF-32 with PK replacements, the 18-feature
  algorithm-neutral set) under leave-one-user-out:
  `python3 -m oref_inv_003_replication.exp_repl_2519 --parquet-dir <grid> --out <out>/tasks/exp_2519.json`.
  Our numbers, and experiments E1 to E6 in full:
  [`docs/60-research/collaboration/oref-inv-003-replication-brief.md`](../../docs/60-research/collaboration/oref-inv-003-replication-brief.md).
- **T5: local time vs UTC (Q07).** Where the holder's code looks up a profile schedule by
  UTC hour or by the browser's zone, report the share of decisions whose scheduled basal,
  ISF or CR would differ under the site's `profile.timezone`. One share per platform.

## What the holder's code reads differently from the uploaders

These come from reading the holder's public repositories at the commits pinned in
`workspace.lock.json`, beside the uploader and server source in `externals/`. They are
offered because Track C touches the same code. Each is a read-from-code observation: check
it before changing anything.

| Where | What it assumes | What the uploader or server does |
|---|---|---|
| oref-digital-twin `variant/signals.py` | AAPS matches `\baaps\b` or `androidaps` in reason, device or keys | AAPS devicestatus `device` is `openaps://<manufacturer> <model>` (AndroidAPS `LoopPlugin.kt`), which neither pattern matches |
| clinical-advice-analysis `fetch_nightscout.py` | v1 `entries?count=N` with no date filter reaches back as far as N | v1 applies a 4-day window when no date filter is given |
| dynamic-isf-calculations `tdd_windows.py` | profile basal looked up by UTC hour; days are UTC days | profiles carry `timezone`; documents carry `utcOffset` |
| exercise-eval `nightscout.js` | schedules looked up in the browser's zone | as above |
| Insulin-Kinetics `gate1_recover_known_curve.py` vs `platform_detect.py` | one says `iob_bolusiob` is never uploaded, the other that Trio uploads it | measured on the one Trio site here: `openaps.iob` is an object; whether it carries `bolusiob` is question Q11 |
| Insulin-Kinetics `gate4_deconvolution.py` | External Insulin records of 20 to 35 U about 12 h apart are long-acting insulin | AAPS carries `isBasalInsulin` on boluses, which marks this directly |
| Insulin-Kinetics, dynamic-isf fetchers | deduplicate on `_id`/`ns_id` only | the same reading or bolus can arrive from two uploaders with different `_id`s (Q08) |

## Returning results

The result directory looks like this:

```
<out>/
  nsprobe/*.json              Track A probes
  schema-census-v1/*.json     Track A census (and -v3/)
  warehouse/*.json            Track B
  tasks/*.json, README.md     Track C
  compare.md                  optional
```

Every JSON file carries `format: nsprobe-result/1` (the census files use nsschema's format),
the contributor label, the date, and the commit it ran at. Before it is sent:

1. `python3 -m nsprobe check <out>` reports 0 problems.
2. The holder has read `compare.md` and the census files. The census files carry per-site
   document counts under the pseudonyms, and corpus-wide numeric minimum and maximum for
   fields with at least 20 observations, which for a timestamp field is the earliest and
   latest reading in the whole corpus. Remove any file the holder does not want to send.
3. The holder chooses how to send it: a pull request adding `reports/external/<label>/` to
   this repository (public), or a private copy to the maintainer.
