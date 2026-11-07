# Same-ID restore and public history continuity

2026-11-07. **Reproduced source protocol**, with actual write-clock allocator and
API3 history handler/filter, recording storage/transactions, stubbed authentication
and a synthetic client-cache model. This is not PostgreSQL or a mobile binary run.
[Observations](observations.json) retain synthetic inputs and actual outputs.

The executed source is `f0fac99a2fccee259c9a76eba0123058bf288d96`.
The root independently replayed the protocol against joined
`92641bd002ada37d78b165f2dd86f44ad4e8baef`; both relevant modules are byte unchanged
from that source, and observations compare exactly. Original instrument SHA256:
`f8037266d2c2e332f4f48b57e65077177e9b8f1a0019c2926ba43184987e2e8d`.
Original capture SHA256:
`e0da086a55bf38e0608f7ee7ae509db383a76162a8ed3a305ab8a0d9384d59bf`.
The private instrument/capture live in the session handoff. Initial invalid-date
setup refusal is retained there; it is not a semantic control pass.

| Case | Actual history behavior | Synthetic cache consequence |
|---|---|---|
| Restore old clock and raw document metadata | The next allocated stamp remains below the prior client cursor; actual URL history filter returns no rows. | A post-backup-only row remains cached; a restored older value also remains stale. |
| Retain live clock floor only | A subsequent new write gets a stamp above the cursor and appears in history. | Previously restored values and hard removals still have no forward history events; both stale-cache cases remain. |

Mechanism: `lib/storage/postgres-write-clock.js:60` locks `last_stamp`, then
line 67 allocates `max(requested, floor + 1)`. This guarantees progress from its
current stored floor, not from a discarded historical floor. In
`lib/api3/generic/history/operation.js:65`, URL cursor filtering selects records
with a greater `srvModified`. Copying old metadata cannot advertise changed
values or synthesize tombstones for records removed by restore. Internal evaluator
snapshot reconciliation does not reset an external client's history cursor.

**Pending policy:** prefer publishing ordinary history updates and deletion
records so existing clients converge; alternative exact snapshot metadata needs
an explicit, reliable client reset/resync procedure. Retaining the clock floor
alone is insufficient. For automatic convergence, compare current and artifact
state before destructive changes, retain the authoritative issued floor, and
measure changed-value/deletion delivery and retry behavior. No public metadata
restamping or reset policy has been adopted in this record.

Joined source currently refuses new clock-bearing full imports before SQL with
`LIFECYCLE_HISTORY_CONTINUITY_REQUIRED` (`lib/tenant-lifecycle/index.js:235`).
Counter-only component proofs remain separate; full same-ID restore is not
accepted. Other tenants must retain their current state, without a global pause.
