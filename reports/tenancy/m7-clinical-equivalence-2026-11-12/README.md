# M7 frozen-candidate clinical timeline equivalence — 2026-11-12

**Reproduced:** all six fresh cross-tree traces are byte-identical between capacity baseline `5c60aec669362b032a10d6dd7ac368e9c61e8003` and coordinator-frozen candidate `d5e2e874659155c952b5b5deb862f12f982ac02e`. This closes the specified synthetic timeline criterion, with the coverage limits below. It does not establish complete clinical, database, browser or deployment acceptance.

## Sources, dependencies and resources

Both product commits were checked out into uniquely owned source worktrees; both stayed clean and were not edited. Instruments came from clean tracked paths in alignment tree `811576c143e0847a5d716cf27a07abe138012449`:

- [eval-cost/trace.cjs](../../../tools/tenancy/eval-cost/trace.cjs), SHA-256 `47a1de898c1e4be658599832b91f3f04774cc9560c2d97abdc9a55860969f593`.
- [eval-cost/compare.cjs](../../../tools/tenancy/eval-cost/compare.cjs), SHA-256 `0df9c949b1a897a14babe781cd645f15d1e332d5a2cbb8cd4b5bc2f8c55dd921`.
- [perf-evaluator/equivalence.cjs](../../../tools/tenancy/perf-evaluator/equivalence.cjs), SHA-256 `1a37bcea1ab415786a7bc5b6b00764245c4eb5ef7b1b1feacd3d18170207a28b`.

The package lock is byte-identical across both trees: SHA-256 `6418fe21c18346435f643b8496d6b7ec23c9c6de28f1925c3bb2028eb575e93e`. The only package.json change is an added check script. A lane-owned dependency installation used that lock with `npm ci --ignore-scripts`; no peer dependencies or databases were reused. Offline installation first failed `ENOTCACHED` for yocto-queue; the subsequent normal lock-based installation succeeded. Both installation logs are retained. Node, npm, timezone, installed dependency-lock hash and immutable PostgreSQL image are in [environment.json](runs/environment.json).

A uniquely owned PostgreSQL 16.15 container/database was provisioned and independently queried. **The unmodified clinical instruments performed zero Pool queries and zero Pool connects:** the selected evaluator path answers projection reads in memory. This is an observed execution boundary, despite the trace header's historical “actual PostgreSQL” description. The aggregate [observer](instruments/observe-pg.cjs) was validated with a real query, recording one query and one connect in [its positive control](runs/pg-positive-control.log). No PostgreSQL projection-read, RLS, authority, restore or connection-pool coverage is claimed here.

## Six cross-tree comparisons

Every run used the same synthetic timeline, one hour of lead-in plus twelve hours, fresh evaluator/view/plugin instances, and actual shipping component outputs. Deploy means the instrument's five-plugin set; full means its 22-plugin set. `base` evaluates each second; `due` uses the component's due instant plus the specified slow timer.

| Plugin set | Schedule | Cycles in each tree | Cross-tree result |
|---|---|---:|---|
| deploy | 1-second ticks | 46,801 | IDENTICAL; zero differences |
| deploy | due; slow 1000 ms | 6,093 | IDENTICAL; zero differences |
| deploy | due; slow 60000 ms | 288 | IDENTICAL; zero differences |
| full | 1-second ticks | 46,801 | IDENTICAL; zero differences |
| full | due; slow 1000 ms | 46,917 | IDENTICAL; zero differences |
| full | due; slow 60000 ms | 1,032 | IDENTICAL; zero differences |


Each trace line contains evaluation instant, acquisition/time-only kind, the first 128 bits of SHA-256 over JSON `{emitted, requested, properties, due}`, and an alarm summary. Requested messages and all JSON-serializable properties participate in the output hash; functions are omitted by JSON serialization. The comparator checks the entire line. Whole-file SHA-256s and cycle counts for both independently executed traces are in [trace-manifest.json](trace-manifest.json). Raw synthetic traces are retained as deterministic gzip files under `traces/`; per-case comparisons and execution logs are under `runs/`. No peer trace was reused.

## Meaningful clinical output control

An isolated archive of the exact candidate changed the actual `lib/plugins/bgnow.js` calculation from `details.mean = mean` to `details.mean = mean + 1`. The product worktrees stayed untouched. On deploy/due/60000 this made the full-output comparison **RED: 286 of 288 cycles differed**, while every instant, cycle kind and alarm-summary column remained identical. This demonstrates sensitivity to a clinical property change that the alarm-summary comparison alone misses. The first difference is preserved in [control-red.log](runs/control-red.log).

Restoring the plugin byte-for-byte returned the same run to **GREEN: 288 of 288 identical**, with the same whole-file hash as the untouched candidate. See [control-green.log](runs/control-green.log), [calculated control assertions](runs/control-summary.json) and [the isolated mutation](instruments/bgnow-control.patch). Original/restored plugin SHA-256: `8202e0223e6d604bf91c39065c083aed4b80d2a84456d47399ce5b0c9e579770`; mutant: `31ff0563c7399394e00d09b36287560b441d948cfa6824cefc72331254ad8b2e`.

## Within-tree base-versus-due characterization

Reproduced on both trees: deployed-set alarm sets and requested-message content pass with both slow timers. Full-plugin alarm sets pass with both timers (52 transitions; due at most 999 ms before base). Full-plugin requested content is **DIFF on the fresh baseline and candidate alike**: slow 1000 has 245 versus 245 content transitions, with the first reported timing difference 1 ms late; slow 60000 has 245 base versus 156 due content transitions. Cross-tree verdict lines and per-mode alarm transition arrays are identical. These are preserved schedule-characterization limits, not full message equivalence between schedules.

The original equivalence instrument compares alarm-set transitions and selected requested-message content/timing, rather than every property. Its process exit code alone is insufficient: it prints content differences without exiting nonzero. The owned checker explicitly compares baseline/candidate verdict lines and transition arrays, refuses alarm failures, and requires deployed-set content checks to pass. See [within-summary.json](runs/within-summary.json) and the four `within-*.log` captures. No message expectation or clinical source was changed to turn a result green.

## Limits and integration boundary

- Candidate E's same-checkpoint deletion/signature invalidation case is absent: this replay advances its checkpoint with every write. An identical trace is not evidence for that optimization's invalidation semantics.
- This timeline has no ordering ties. It does not discriminate insertion-ordinal/typed-identity tie behavior. Dedicated corresponding source/corpus checks remain the coordinator's responsibility; see the [original evaluation record](../eval-cost-2026-11-11/README.md).
- These are component/view/plugin executions with synthetic replay and statistics. They do not exercise real ingestion, replay reconciliation, external notification delivery, sockets, alarm transport, browser presentation, lifecycle coordination or database projection reads.
- CPU, elapsed-time and load figures in raw logs are incidental on a shared host. They support no capacity or speedup claim. Diagnostics were off.
- Product source edits, full regression/browser/capacity campaigns, cloud actions and pushes were not performed. The coordinator owns final frozen-candidate acceptance and programme records.

Portable copies of owned orchestration/check helpers replace only execution-local state/worktree roots with `CLINICAL_STATE` and `CLINICAL_WORK_ROOT`. [instrument-manifest.json](instrument-manifest.json) pins the actual execution bytes before that publication normalization. Captured text replaces workspace/npm-home prefixes and trims trailing whitespace; clinical traces remain byte-exact inside gzip. No credentials, connection URLs or private data are included.

## Reproduction and record checks

With owned trees named `crm-clinical-base-20261112` and `crm-clinical-candidate-20261112` below `CLINICAL_WORK_ROOT`, set `CLINICAL_STATE` to a private output directory and supply the disposable database connection through `NS_TEST_POSTGRES_ADMIN_URI`. Place the three pinned original clinical instruments and the published observer in `$CLINICAL_STATE/instruments`. The published portable orchestration is:

```bash
python3 instruments/run.py
python3 instruments/within.py
python3 instruments/check-within.py
python3 instruments/check-control.py
```

The control checker expects fresh traces from the isolated mutation and byte-restored source archive described above; it does not mutate source itself. Offline installation failure and the exact restored clinical control are retained rather than discarded.

`make queue-check` was attempted in this isolated alignment evidence tree and exited 2 at queue validation because programme gate worktree directories are absent here. [Output](runs/queue-check.log) is preserved. No queue/gate settings were changed to hide that prerequisite failure. Programme gate execution belongs to the coordinator's populated alignment workspace.
