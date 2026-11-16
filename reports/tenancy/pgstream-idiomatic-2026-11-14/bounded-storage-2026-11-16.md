# Bounded clinical state and raw storage delivery — focused qualification

*Contributor-facing snapshot, 2026-11-16. Reproduced on application
`3e085e056330d2f0ddf29c4000e526a968462620`, branch
`codex/bounded-storage-20261116`. Fixed locally; proposed for selection into the
integrator's coherent batch. No merge to dev, release or operating-profile claim.*

The candidate bounds clinical membership by existing engine queries, preserves
required history and whole-history accounting, and separates raw storage events
from clinical expiry. The responsibilities and client contract live in the
[architecture contract](../../../docs/30-design/tenancy/evaluator-realtime-communication.md#bounded-clinical-input-next-batch-contract).

It includes integrator commit `1dc7a74576b5d77f99cc4a42d900e1692d94a393` and
`official/dev` `4a482627bfdafb1fef8dcbe0ac6c484811cae563`. The join preserves the
populated tenant-bound storage-size backfill and shared due-query settlement
repair. Migration conflicts were resolved by keeping that exact backfill and
appending the new reviewed `0100` identity operation. Original migration SQL
before those existing candidate changes is not rewritten by this lane.

## Results and meaningful controls

| Measured scope | Result | What it establishes |
|---|---|---|
| Affected modules, actual clinical engine, protocol, migration/census, cache and delivery checks | 289 passing; 1 optional `VIEWS_CORPUS_DIR` check pending | Historical exceptions and profile fallback, corrections/deletes/settings expansion, expiry without source writes, warm-source-read refusal, storage CRUD/public identity/order, duplicate delivery, continuity-loss disconnect, authority/worker/restore fences, fleet eviction and cold notification behavior. |
| Actual scheduler module | 13 passing | Existing due-query, settlement, fairness, retry and newer-input controls survive the join. |
| Isolated PostgreSQL/wal2json plus actual replay/engine and journal modules | 10 passing | Old-history-heavy bounded bootstrap, engine/frame parity, authoritative stats, legitimate missing-history fetch, no warm range reacquisition, time-only expiry, FULL old public identifier/TOAST, equal-LSN COPY rows, replay, read-only/RLS journal access, typed completion preserving the raw tail, and actual populated ordered catalogue/backfill followed by identity migration. |
| Test tier inventory | 843 files across 8 tiers; check passes | New tests have one tier each. This is inventory, not execution of all tiers. |

These groups have different scopes; do not add their counts. RED/restored
controls cover removal of required old treatment context, restoration of warm
source acquisition, source mutation on expiry, omitted durable COMMIT, dropped
food/out-of-window mutations, invented delete identifiers, silent tail truncation,
wrong old-identity mode, stale-worker publication and disabled fleet eviction.
The actual storage client wire is checked against the single-tenant normalizer
and broadcaster. Connected-session delivery and reconnect high-water behavior are
module tests; the native suite proves WAL, database and engine boundaries.

A focused run caught a regression in the first retry repair: a failed socket join
retried instead of retiring that state (`RT_INDEX_PARTIAL_PRIME` timed out). The
repair confines retries to temporary journal reads and retains failed-join
retirement. The final focused run above includes that oracle and the new
continuity-loss cause/counter case; no timeout was increased.

## Scoped WAL measurement

For one unchanged-document metadata update of a synthetic row containing a
19,200-byte extension, the final native run measured **240 WAL bytes with DEFAULT
identity** and **19,648 bytes with FULL identity**. The fixture has no production
storage-size trigger. These are WAL bytes for that operation, not serving latency,
throughput, total production write amplification or a capacity ceiling. Earlier
retained runs have their own measured values and source attribution.

The raw tail shares the existing input-checkpoint row write. Its delivery
obligation updates completed-checkpoint metadata; it does not rewrite the clinical
frame for every mutation. Realtime frames no longer fetch or decode clinical rows.
The existing clock-seal full working-set copy remains, now bounded by clinical
membership. Whole-history statistic scan cost and total fleet heap/RSS remain
unmeasured. The historical pre-intake-delay cause remains UNKNOWN.

## Reproduction and retained evidence

Retained evidence identifier: `bounded-storage-20261116`, ignored local evidence
home `externals/work/bounded-storage-20261116/evidence/`. Node was `24.22.1`.
The exact focused command is `focused-command.sh`. The native command runs
`tests/storage-event.integration.test.js` and
`tests/clinical-working-set.integration.test.js` with an explicit owned
`CLINICAL_WINDOW_PG_SOCKET`. Source-file hashes are in the final manifest.
The native fixture used existing image tag `ns-pgstream-roles-postgres:20261113`,
network none, 0.25 CPU, 256 MiB memory and swap cap, 96 PIDs, tmpfs database data
and one owned Unix-socket bind. The exact container was removed; the socket had
no listener and its stale artifacts were removed. No actor or resource remains.

| Retained file | SHA-256 |
|---|---|
| `final-focused02.log` | `6a966e2be455b0c562c3b6ec0e4819662983b9f0aa1a64f8f9db0b30d3079b28` |
| `final-native02.log` | `699b235b2e8e58cf2830ef81f4d7c7fd729110385e523c9386f7d0d376c44a4c` |
| `final-scheduler.log` | `0ce80558ea3b1b4f43d57f3530a5d3f92fcc1a95f66fd040303d0dcd7b60d9ce` |
| `final-source-manifest.json` | `cf41346f7d1e9ca7542e9518773df94caeea336f6c4934eb47411511f2388f67` |
| `final-cleanup.json` | `e0cfeb4921fd2e567c5999cefb95d30edadf7316528869c8160249d0473918d3` |

Full/browser/enabled-native corpus acceptance, a matched deployed default-role
campaign, final prcheck and the selected operating-profile point are **not run
for this next-batch candidate**. The application integrator owns those gates
following selection. The independent operating-proof lane retains the separate
current-candidate performance work. Nothing here promotes a shipping state.
