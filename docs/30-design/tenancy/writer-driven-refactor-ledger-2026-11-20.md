# Writer-driven transport: refactor and retirement ledger

*Contributor-facing, 2026-11-20. Living list for
[writer-driven-transport-direction](multitenancy-decisions.md#writer-driven-transport-direction).
Under [prerelease-schema-in-place](multitenancy-decisions.md#prerelease-schema-in-place), no
multitenant row or storage format has to be preserved. Formats are kept only where keeping them
reduces churn now. The behaviour target is single-tenant Nightscout. Source evidence is in local
handoffs `HANDOFF-spike-s{1,1b,2,3}-20261120.md` and `HANDOFF-evaluator-a-join-20261120.md`.*

## How items move

Each item is in one of three groups:
- **in the candidate:** done in the joined S4 candidate;
- **at adoption:** done once S4 holds and the maintainer adopts the direction;
- **later:** a refactor that is cleaner but not needed for capacity or correctness.

An item moves up only when a measurement or a blocker needs it.

## In the candidate

| item | why | source |
|---|---|---|
| Pending mark in the write transaction, post-commit hint, periodic sweep, window recompute, completion generation fence | the transport itself | S1 `45823c5f0` |
| Index-bounded window read: entries `"date"` bigint, devicestatus/treatments `created_at` text COLLATE "C", one statement | flat about 12 ms PostgreSQL per read from 1 to 26 weeks (was up to 914 ms) | S1b `4f83b0a56` |
| api → realtime `/storage` events; journal reader and writes removed | `/storage` without the evaluator in the path | S2 `6a1ca6a3f` |
| `lib/internal-hints/` sender and v1 contracts, wired at `postgres-intent-common.js:70` | one post-commit point covers the api's five write sites | S3 `dcdb168cb` |
| A cuts: read ports, dbsize gate, consumer wake on owed work, fewer wrappers and fences | 171.5 → about 76 statements per write, carried into either design | join `9af05fb32` |
| Grants and row-level security for the work row and the evaluator's cross-tenant reads | S1 used stand-ins | S1 blockers 2–4 |

## At adoption

These retire with the stream:
- pgstream, the patched fork, wal2json, the slot, the DBA trigger step, the streaming role, the
  subscription roster, the WAL-sender budget and `REPLICA IDENTITY FULL`;
- the evaluator receiver, the receipt transaction and its fences, `clinical-stream-sql.js` receipt
  paths, the replay input cache fed by receipts, and snapshot recovery over a replication
  connection;
- the storage-event journal module (`storage-event-journal.js`, dead code after S2) and its
  remaining tests;
- the stream DDL gate. A ledger-head check at startup replaces it, per
  [stable-evaluator-runtime](multitenancy-decisions.md#stable-evaluator-runtime);
- [private-stream-router](multitenancy-decisions.md#private-stream-router) and options C/E/F/G in
  [evaluator scaling options](evaluator-scaling-options-2026-11-19.md);
- harness parts that exist only for the stream: slot-lag sampling, the pgstream delivery reducer,
  and the slice-receiver configuration;
- non-api writers. Class (b) gets hooks: tenant-admin, admin provisioning, the deletion step.
  Class (c) ends with a per-tenant re-sweep: restore, import, recommission, migrations. Class (d)
  becomes unsupported: the entries import CLI.

## Later

The first two may be promoted by S4 measurements; the rest wait.
- Cross-tenant batched completion (option I) if completion statements bind under backlog.
- Time-only cycles without a full plugin pass (option J).
- Per-cycle main-thread CPU, about 80–95 ms with 900 window rows (S1): decode and dataloader reuse.
  CPU scales horizontally, so this waits for a profile.
- Older internal contracts moved to path versioning with unknown-field tolerance (S3 §7).
- The completion trusted scan folded into the completion transaction (A1, skipped).
- `set_config` folded into the write-lock statement, shared with the api (A1, skipped).
- Items S1b lists under "refactor later".
- From S1b:
  - other numeric generated columns (`sgv`, `mbg`, treatments/devicestatus `"date"`) have the same
    non-leakproof `numeric_ge` limit under row-level security;
  - a byte bound via the stored `storage_bytes`;
  - the unbounded profile read;
  - stream bootstrap still pages;
  - regenerate the entries schema fixture whose header says "the document is the record".
