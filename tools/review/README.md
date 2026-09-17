# `tools/review/` — the dev-cycle review harness

Brings up one real Nightscout per candidate state, seeds each identically through
the real HTTP API, and measures the difference between them.

Plan and per-unit acceptance criteria:
[`docs/30-design/remedial/dev-cycle-review-harness-plan-2026-09-17.md`](../../docs/30-design/remedial/dev-cycle-review-harness-plan-2026-09-17.md).

## Run it

```bash
export NSREVIEW_ROOT=/var/tmp/nsreview        # anywhere with ~2 GB free
tools/review/nsctl.sh init                    # clone + private node_modules, once
tools/review/run.sh                           # boot, seed, probe, red-control
```

Whole cycle measured at **16.7 s** for six states on 2026-09-17. `run.sh` is
idempotent: it resets and re-seeds every state each time.

Individual states:

```bash
tools/review/nsctl.sh add   PAIR rc/2026-09-dev-cycle
tools/review/nsctl.sh reset PAIR production   # stop, DROP db, start
tools/review/nsctl.sh url   PAIR              # open this in a browser
tools/review/nsctl.sh status
tools/review/nsctl.sh stop  --all
```

## Layout

| path | what |
|---|---|
| `nsctl.sh` | instance lifecycle — worktrees, ports, databases, detached boot, run-id namespacing |
| `seed.js` | seeds a complete instance and emits the **expectation manifest** probes assert against |
| `lib/nsprobe.js` | shared probe half: two-instance `compare()`, arm kinds, vacuity detection |
| `probes/` | one module per merge unit. **These are the harness.** |
| `scratch/` | 42 ad-hoc scripts preserved from the reconnaissance session. Evidence of how each defect was first reproduced; **not** part of the harness and not run by `run.sh`. |
| `evidence/` | captured probe output worth keeping |

## Four rules the code enforces, each learned by being bitten

1. **Never drop a database under a live server.** The in-memory cache survives,
   and the instance then serves documents that are no longer stored. BASE once
   answered with 1145 sgv documents from a 582-document database. Use
   `nsctl.sh reset`, which stops first.
2. **Never verify the seed through the endpoint under test.**
   `/api/v1/treatments.json` applies a default time window, so 29 stored
   treatments read back as 26 and look like data loss. Authoritative counts come
   from Mongo; the API counts are kept as a separate diagnostic.
3. **Never assert a build against itself.** On `bf/reads` alone the count
   endpoint returns 5 and the list endpoint returns 5 — they agree and both are
   wrong. Every arm asserts against the seeded expectation in the manifest.
4. **Every arm declares its `kind`.** A `discriminates` arm must be RED on BASE
   or it measured nothing about the branch; an `invariant` arm must be GREEN on
   BASE or its state cannot be attributed to the branch. A probe with no
   discriminating arm refuses to pass.

## Probe contract

Probes reuse `tools/queue/gates/_gate.js` `report()` verbatim — same exit codes,
same output shape — so the existing queue machinery reads them with no new
plumbing. Exit 0 = the property holds, 1 = it does not, 2 = the probe could not
run (which is neither, and must never be read as a pass).

## Data

Everything the harness writes is synthetic and generated in `seed.js`. Every
identifier-shaped value (`device`, `enteredBy`) is a literal defined at the top
of that file. **Nothing is read from `externals/ns-data` or `externals/ns-parquet`**,
which hold real patient data; if replay is added later it must pass through the
allowlist described in the plan's §4.

The API secret is generated at `init` into `$NSREVIEW_ROOT/secret` and is never
committed. `NS_HARNESS_SECRET` overrides it.
