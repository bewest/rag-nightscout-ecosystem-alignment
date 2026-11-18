# Experiment run catalog

The catalog reads retained Compose observations and Kubernetes packets. It
keeps one immutable private JSON record per run directory under
`/mnt/data/nightscout-workspace/artifacts/capacity-index/`. The directory path
relative to `artifacts/` is the run ID. Listing derives the index from these
records. Independent runs can finish at the same time. Reimporting an identical
record succeeds. Reusing an ID for changed evidence fails and preserves the
original.

Run from the alignment checkout that contains this tool.

```bash
catalog=tools/mt-bench/run-catalog/catalog.py
artifacts=/mnt/data/nightscout-workspace/artifacts
python3 "$catalog" add "$artifacts/<lane>/<completed-run>"
python3 "$catalog" session "$artifacts/<lane>/<session>"
python3 "$catalog" list
python3 "$catalog" show '<lane>/<completed-run>'
python3 "$catalog" compare '<lane>/<current-run>' '<lane>/<baseline-run>'
```

Use `add --partial` after an interrupted run's writers have stopped if its
result file is missing or unreadable. Startup failures with a terminal result
are indexed without that option. The record keeps each source, oracle and
signal at the scope indicated by its evidence. Missing values are JSON `null`
or `UNMEASURED`. The catalog extracts aggregate fields from named documents
and stores relative evidence paths. Config and allocation fingerprints are
hashes. Raw configuration, retained SQL statements, role logs, credentials and
per-tenant observations stay in their original directories.

Comparison checks the instrument, workload, population, timing and cadence,
allocation, environment and runtime history. Use `--change source` for a
deliberate comparison across source and image tuples. Inconsistent pins within
a run always refuse comparison. Changes in config hash, pre-load host load and
elapsed runtime are displayed alongside compatible results. The report shows
issued work and each oracle verdict. Signal deltas require matching units,
denominators and observation scopes. Sample sizes remain visible, including
when the denominator definition matches and sample sizes differ. Comparison
reports observed deltas. Capacity acceptance remains `NOT_GRANTED`.

Local signal coverage includes sparse client and durable-output latency,
fixed-boundary evaluator drain, PostgreSQL statements and execution time per
unit, sampled lock-wait fraction and load-window CPU as a fraction of the
configured role quota. Kubernetes catalog coverage depends on the retained
packet's instruments. Pooled scenario latency remains `UNMEASURED` where the
retained output contains shard percentiles without a pooled distribution.

```bash
python3 -m unittest discover -s tools/mt-bench/run-catalog -v
```
