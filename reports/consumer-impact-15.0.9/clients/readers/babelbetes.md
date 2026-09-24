# babelbetes — consumer impact against cgm-remote-monitor 15.0.9 candidate

- Repo: externals/babelbetes (Python library normalising clinical-study datasets; docs, notebooks).
- Ref analysed: `origin/develop` **07a7f07 (2026-07-21)** — the remote's default branch
  (`origin/HEAD -> origin/develop`). Local HEAD = 07a7f07 (not in the corpus staleness file;
  measured here: behind 0, dirty 0).
- All claims **read-derived**.

## Verdict: reads files, not the Nightscout API

**Positive control (the search reaches its data-loading code):**
`git grep -n -i -E "read_json|gzip|json\.load|read_csv" origin/develop -- 'babelbetes/*.py'`
finds its loaders, e.g. `babelbetes/studies/loop.py:64-190` (`pd.read_csv` / `dd.read_csv` on
study "Data Tables" `.txt` files) and `babelbetes/pandas_helper.py:280`.

**Absence searches (no hit anywhere in the repo):** outbound HTTP
(`requests\.(get|post)|httpx\.|fetch\(|axios|urlopen`), `api/v1`, `api/v3`, `api-secret`, `token=`,
`socket`. The only Nightscout material is one exploratory notebook that opens **archived
Nightscout exports** (`.gz` collection dumps inside a study zip):
`notebooks/understand-dana-dataset/2024-05-15 - LoadingLoopDataFromNightScout.ipynb:55,401-429`.
That consumes stored documents, so of the candidate's changes only the stored-data shape could
matter, and the candidate changes no stored data.

| S-id | finding | patterns |
|---|---|---|
| S1–S15 | none: no Nightscout request of any kind | as above |

**Impact: none.**
