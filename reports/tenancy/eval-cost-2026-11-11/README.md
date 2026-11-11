# Evaluator per-evaluation cost: candidates C, D, E, B and A (2026-11-11)

*Contributor-facing measurement record for decisions
[evaluation-cost-candidates](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#evaluation-cost-candidates) and
[view-reads-total-order](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#view-reads-total-order). Multitenant
only. Captured 2026-11-11 06:47–08:20 local time; not edited after capture. Synthetic tenants and data, plus the
alignment corpus sets read in place and reported by position and count only. Figures are **reproduced** (run here,
output in [`runs/`](runs/)) unless labelled otherwise. Other lanes shared the host; each run quotes its load average.*

## Anchors

| what | value |
|---|---|
| base | `codex/perf-evaluator-20261110` at `9c46b95e` (confirmed at start) |
| lane | branch `codex/eval-cost-20261111`, worktree `externals/work/crm-eval-cost-20261111` (own `npm ci`). Not pushed |
| commits | `d5b4f7ec` C, D, E · `2af5a3c5` E same-checkpoint test · `bdc9e326` B · `7f5f518e` A (with a port of PostgreSQL's sort) · `745c7f4e` view reads in one total order (replaces the port) |
| port kept aside | branch `codex/eval-cost-pgsort-port-20261111` at `7f5f518e`; not in the lane's final state |
| alignment `main` when written | `bbf88ae8407b90ac87cd75fe857aae6af13f0221` |
| PostgreSQL / MongoDB | dedicated containers `ns-ec-pg` (`postgres:16`, 16.15, `pg_stat_statements`, database `ns_ec_test`) and `ns-ec-mongo` (`mongo:7`, 7.0.x, `--ulimit nofile=64000`); both removed afterwards, no image created |
| harnesses | [`../../../tools/tenancy/perf-evaluator/profile.cjs`](../../../tools/tenancy/perf-evaluator/profile.cjs), [`equivalence.cjs`](../../../tools/tenancy/perf-evaluator/equivalence.cjs); this lane: [`trace.cjs`](../../../tools/tenancy/eval-cost/trace.cjs) + [`compare.cjs`](../../../tools/tenancy/eval-cost/compare.cjs), [`read-lab.cjs`](../../../tools/tenancy/eval-cost/read-lab.cjs), [`tiebreak-bench.cjs`](../../../tools/tenancy/eval-cost/tiebreak-bench.cjs), [`date-forms.cjs`](../../../tools/tenancy/eval-cost/date-forms.cjs) |

## Result

Per evaluation, `profile.cjs` (one tenant, 576 rows, actual PostgreSQL, K = 200):

| head | time-only deployed: CPU-ms / statements / DB-ms | time-only 22 plugins: CPU-ms | acquisition deployed: CPU-ms / statements / DB-ms | acquisition 22 plugins: CPU-ms | load |
|---|---|---|---|---|---|
| base `9c46b95e` | 19.52 / 44 / 3.24 | 20.56 | 31.96 / 58 / 9.47 | 33.66 | 5.1 → 3.8 |
| C+D+E `d5b4f7ec` | 13.87 / 44 / 3.46 | 15.24 | 20.40 / 57 / 8.52 | 22.76 | 2.7 → 2.8 |
| B `bdc9e326` | 10.57 / 44 / 3.04 | 11.56 | 25.31 / 57 / 7.76 | 26.93 | 2.5 → 2.6 |
| A + total order `745c7f4e` | **4.57 / 0 / 0** | **5.46** | **14.31 / 13 / 4.54** | **16.03** | 1.0 → 1.2 |

Mean CPU per cycle over the 13-hour trace, a cycle every second (`traces-*.log`): deployed 6.82 → 1.48 ms, 22 plugins
9.73 → 2.37 ms (load 13–18 for the earlier heads, 4.5–4.9 for the last).

Time-only busy shares at `745c7f4e` (deployed / 22 plugins): other app code 54 / 50% (the working-set copy, the
answer witness, the in-process read), moment 12 / 13%, read translation and decoding 11 / 9%, GC 9 / 10%, plugins
2 / 4%. Base shares are in the perf-evaluator Round 3 record.

The acquisition rose with B (the kept copy and clock edges are built on each load) and fell with A.

## Clinical equivalence

Every head was traced on the 13-hour synthetic timeline (one hour lead-in + 12 h) with `trace.cjs`. Each cycle's full
output is hashed: emitted, requested with message text, every property, and the due instant. The runs cover the
deployed plugin set and all 22 plugins, a cycle every 1 s (46,801 cycles), and due mode with a 1 s and a 60 s slow
timer. `compare.cjs` against base:

| head | 6 runs |
|---|---|
| C+D+E, B, A + total order | **IDENTICAL**, every cycle (`equivalence/compare-*.txt`) |

`equivalence.cjs` (base vs due within a tree) prints the same verdict lines at every head as at base (deploy PASS/PASS;
22 plugins PASS alarm sets and base's pre-existing CONTENT DIFF lines). The trace harness gives each row its insertion
ordinal from `7f5f518e` on. Rerunning base with that harness gives identical traces.

## The steps

| step | what | proof | break-it control (red, then restored) |
|---|---|---|---|
| C | the evaluator retains the JSON round trip of its input, deep-frozen, with each domain's projection source prepared once. Private-acquisition copies use `json-copy`, which equals `JSON.parse(JSON.stringify())` without the text. Shared defaults unchanged | `json-copy.test.js` (special cases, 2,000 random structures, mutation); `EV_COST_MUTATION_GUARD` (8 scenarios: a plugin that vandalises everything it reaches in one cycle changes no later cycle) | nested objects shared → 4 failing incl. "copies independent". The same break leaves the mutation guard green, so that guard is vacuous for C: the SQL boundary re-created every document |
| D | the plugins' single-string `moment()` calls return clones of moment's own first parse, with their own parsing flags; bounded per cycle | `moment-memo.test.js`: every corpus date shape (`date-forms.cjs`: 16 shapes in 7 sets) and ISO/fallback forms; 14,579 distinct corpus strings read in place, all equal | date-only form via `Date` → red `"2026-11-10" first parse` (host TZ PST); shared flags → mutation case red |
| E | the signature reconcile skips the read-back, deep compare and copy for a committed, unchanged signature; the evaluator reuses its retained rows | replay suite in both signature modes plus skip/rollback cases; `EV_COST_E_SAME_CHECKPOINT` (hard delete at the same checkpoint) | evaluator ignores the signature → trace lab IDENTICAL: vacuous, because the lab's replay moves its checkpoint with every write. The same-checkpoint case is red: "the evaluation sees the delete". Replay ignores the signature → `EV_COST_E_CHANGED` red |
| B | the view keeps its working set while the retained rows are the same, and reuses a copy only when every read answer and every clock rule outside the reads is unchanged | `EV_COST_B_WINDOW_CUT`: kept vs fresh at 193 instants over a projection that crosses every window. Wall clock at the instant: 136 reused / 57 loaded. Wall clock 2.5 s late: 130 / 63. Working sets (key order, shared values), reads and outputs equal | kept set handed out → 8 mutation-guard cases red ("time-only cycle 2 after the hostile cycle") and both window-cut cases red. No clock-edge check → red on `lastProfileFromSwitch` and on treatments retention. The first attempt was vacuous: keep() refused shared values, which the no-copy control exposed (`controls/B0-*`) |
| A | views' reads answered in process from the retained rows, through the shipping collection intent with an injected reader that applies postgres-filter's rules and refusals | read lab (below); `projection-memory-read.test.js`; `EV_COST_A_NO_STATEMENTS` (five time-only cycles, no statement) | `$ne` on a missing field → 3,938 reads different. Views read through SQL → "the views read nothing through PostgreSQL" |
| total order | ties break on the insertion ordinal (nulls last), then the typed identity, on both paths. The reconcile carries `insertion_ordinal` where the table has one | `EV_COST_A_TOTAL_ORDER`: 600 random tie-heavy reads with typed twins and null ordinals; 544 equal on both paths (203 with ties), 56 refused identically. `EV_COST_A_ORDINALS` | tie-break dropped in process → red "sql 2,5 memory 2,0"; dropped on SQL → red "sql 2,1 memory 2,5" |

## Tie order (decision view-reads-total-order)

Read lab at `745c7f4e` (`runs/read-lab-total-order.txt`) covers 17 views-equality scenarios × 4 instants, a
typed-twin/tie set, 12 views-replay timelines every 2 h, and 7 corpus sets × 3 instants: 498 view instants and 5,976
reads. The ordinal is each document's position in its dataset, the order MongoDB received them in.

| measure | count |
|---|---|
| reads, in-process vs SQL with the total order | 5,976 / 5,976 equal; working sets and outputs equal at 498 / 498 instants |
| reads whose order differs between today's SQL and the total order (ties only; 0 differ in membership) | 402: treatments `{created_at:1}` 242, devicestatus `{created_at:-1}` 126, entries `{date:1}` 32, entries `{date:-1}` limit 12 2 |
| of those, single-site MongoDB 7 returns the order of | **the total order 400**, today's PostgreSQL order 0, neither 2 (the two limit-12 reads on the typed-twin set) |
| mingo membership vs SQL (unbounded reads) | 1,245 / 1,245 agree |

Changes against today's order, every one at an instant with a tie read (0 without one). Each comes from two or more
readings with the same `date`:

| view | field | dataset | instants |
|---|---|---|---|
| properties, alarms | output `emitted[].clear` | typed-twin set (twin readings with different values) | 2 + 2 |
| properties | output `bgnow.sgvs[]._id` | timeline twoUploaders | 4 |
| properties | output `delta.previous.sgvs[]._id` | timeline twoUploaders | 2 |
| properties, alarms | working set `sgvs[].mgdl` | typed-twin set | 2 + 2 |
| properties | working set `sgvs[]._id` | replay timelines | 24 |

The 13-hour timeline has no ties: its traces are identical to base with either order.

Cost of the tie-break (`runs/tiebreak-bench.txt`, 288 rows, load 4.6): on the SQL path +0.2 to +0.7 ms server
execution per sorted read (entries 0.80 → 1.12, device status 1.28 → 2.01, newest 12 1.11 → 1.33 ms). The in-process
read takes 0.11–0.30 ms per read in total. No index applies: the read sorts its recordset in memory.

Superseded: the PostgreSQL 16 quicksort and bounded-heap port at `7f5f518e` matched the server on 5,314 random reads
and 5,976 corpus reads. A stable sort without it differed on 394 tie orders and changed output on typed twins. Records
are in `runs/a-port-superseded/`. The port is not in the lane's final state.

## Other gates

| gate | base `9c46b95e` | C+D+E | B | A + total order |
|---|---|---|---|---|
| affected suites (evaluator-*, producer, consumers, replay, projection evaluator, views-equality with the corpus, `current-state-recovery` with `NS_M5_CURRENT_STATE_PROOF_TEST=1`, ddata/cache/dataloader, the lane's suites) | 477 / 0 | 501 / 0 | 502 / 0 | 512 / 0 |
| unit tier | — | 3243 / 0 (1 pending) | 3243 / 0 | 3249 / 0 |
| `test:tiers`, write-boundary, eslint `lib` | — | ok, 9, 0 errors | ok, 9, 0 errors | ok (640 files), 9, 0 errors |
| partition lab (`tools/tenancy/evaluator-partition/run.cjs`) | 20/23 | 20/23 | 20/23 | 20/23 |

The partition lab fails the same three checks at every head, base included: the 2 → 3 duplicate gate, the SIGKILL
stale socket, and the kill MEASURE. They passed 23/23 on the perf-db join `3b858586`.

The affected run at the port head had one timeout: the preview drain fixture held the cycle at its first
`jsonb_to_recordset` statement, which A no longer sends. The fixture now also holds the statistics read
(`pg_column_size(doc)`).

## Changes a reviewer should read

- `lib/data/tenant-projection-evaluator.js`: the retained input, prepared sources, the E reuse, `keep` and `memory`/`totalOrder`.
- `lib/data/views/index.js` `keepOrLoad`, `lib/data/working-set.js`: B.
- `lib/storage/projection-memory-read.js`, `postgres-projection-read.js` (`prepare`, `TIE_BREAK`), `postgres-collection-intent.js` (`reader`, `tieBreak`), `postgres-entries-read.js` (`tieBreak`, shared `internals`): A and the total order.
- `lib/storage/postgres-durable-replay.js`: E memo and the insertion ordinal on signature reconciles.
- Three evaluator tests that injected SQL read failures now inject them in the statistics read.
- `ddata.js`/`cache.js` take an optional `copy`, and `cache.js` exports its age and retention rules. Defaults are unchanged.

Not measured: the lane at deployment scale (1,000 tenants) and on the perf-db join. The batch join combines them.
