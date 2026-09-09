# mt-bench — Nightscout multitenancy micro-benchmarks

Seed harness for the experiments in
[`docs/30-design/nightscout-multitenancy-discussion-2026-09-09.md`](../../docs/30-design/nightscout-multitenancy-discussion-2026-09-09.md).

These are **micro-benchmarks used to rank hypotheses**, not the full multi-tenant load
harness described in §9 of that document. They answer narrow questions: how expensive is a
cold tenant wake, does SQLite-in-WASM help on the server, does a columnar representation
pay, and does SQLite-file-per-tenant survive a thousand tenants.

## Synthetic tenant

`gen.js` builds one 48-hour window shaped like real Nightscout data:

- 576 SGV entries (5-minute cadence, xDrip/Dexcom field set)
- 600 treatments (temp basals with `duration`/`absolute`/`mills`/`endmills`)
- 576 devicestatus documents (Loop-shaped, including 72-point `predicted.values` arrays)

Field sets were taken from `externals/cgm-remote-monitor-official/lib/data/ddata.js` and
the retention windows in `lib/server/cache.js:26-31`. It is synthetic: treatment
heterogeneity and real upload burstiness are **not** modelled, which is exactly what the
full harness in §9 must add.

## Scripts

| Script | Question | Notes |
|---|---|---|
| `coldwake.js` | How long does it take to wake one cold tenant? | Compares `JSON.parse` snapshot, `v8.deserialize`, and `node:sqlite` cold/warm paths |
| `wasmvsnative.js` | Is SQLite-in-WASM faster than native? | `better-sqlite3` vs `@sqlite.org/sqlite-wasm` |
| `columnar.js` | Do typed arrays beat JS objects? | Measures `heapUsed + external` (Buffer memory is off-heap — measuring `heapUsed` alone gives a wildly wrong answer) |
| `handles.js` | Does SQLite-file-per-tenant scale? | Creates K tenant DBs (default 1 000), measures cold open, first query, and RSS holding all handles open |

## Running

```bash
cd tools/mt-bench
npm init -y && npm i better-sqlite3 @sqlite.org/sqlite-wasm   # wasmvsnative.js only
node coldwake.js
node --expose-gc columnar.js      # --expose-gc is required for the memory numbers
K=1000 node handles.js
node wasmvsnative.js 2>/dev/null  # sqlite-wasm prints SQL traces to stderr
```

`node:sqlite` requires Node 22.5+ (release-candidate status as of Node 25/26);
`coldwake.js` uses it, the others use `better-sqlite3`.

## Interpreting results

Recorded numbers in the discussion document came from a **shared development machine**
with no remote database in the loop. Treat them as ordinal (which approach wins) rather
than cardinal (what the latency will be in production). In particular, a real deployment
adds Mongo/Atlas network round-trips that are expected to dominate every local cost
measured here — see EXP-MT-026.

Always re-run on the target hardware before quoting a number.
