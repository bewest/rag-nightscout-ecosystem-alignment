# Bounded work: what each operation should cost, and what changes

*Brief, 2026-11-24. Multitenant candidate only; the single-site MongoDB implementation is the
compatibility reference and is unchanged. Source heads: core `37f18c6ee` (next join, descends from the
five-fix successor `2643ca01b` and Candidate 5 `eae3b2056`), deploy `963fe08e6`, alignment `2b79be1abb`.
Evidence comes from the paid Candidate 5 ladder (3k, 5k, 10k), its bounded-work attribution and three audits
of the code at these heads. Labels: **reproduced** means a sealed run or a local control. **read-derived** means
it was read from code and not yet measured.*

## 1. Where the candidate stands

| Point | Result | What bound it |
|---|---|---|
| 1k (kind, including 100 connector tenants) | Pass | none observed |
| 3k paid, C5 | Not granted: 15 latest-device-status 503s; status GET p95 1.765 s; 73 viewer deliveries over 120 s | specific routes; PostgreSQL and pools had headroom (busiest pool 0.54 of 8 seats) |
| 5k paid, C5 | Fail: 17.5% 5xx, HTTP p95 10.25 s, 67.4 of 82.6 req/s served | **API data pools 96.6% busy** while PostgreSQL read at 0.57 ms with 99.97% buffer hits |
| 10k paid, C5 | Unmeasured: 22,360 of 26,000 viewers primed; four realtime pods exited; observer used 32,338 of 32,768 ports | realtime start-up and ownership, harness viewer source |

All of this is **reproduced** from [the execution log](execution-log.md#bounded-rest-reads-addressed-realtime-delivery-and-entries-index-removal-2026-11-24)
and the sealed campaign packets. PostgreSQL capacity has not bound any point. The limit is time spent holding
connections on work the request did not need, and machinery that turns transient slowness into lost
progress. Every point so far ran on ≤52 h of history, so the data-volume risk (section 5) is not yet measured.

## 2. Classes of excess work

Each class is fixed once and applied to every instance found. An instance found later goes into its class.

| Class | Pattern | Instances (file:line at `37f18c6ee`) | Change | Predicted impact |
|---|---|---|---|---|
| **C1 Invariant re-verified per operation** | A property that cannot change for a connection, request or revision is checked on every statement or transaction | • Settings read forces a fresh backend-identity probe (`lib/storage/postgres-connection.js:316`). It is left over from `2bff10a0b`. The screen it served moved to open and recovery in `6f1d38977` ([trusted-worker-performance-boundary](multitenancy-decisions.md#trusted-worker-performance-boundary)). • Status authenticates twice, reads the subject twice, reads the signing key separately and makes two sequential audit appends (`tenant-app/status-authorization.js:9-19`, `local-exchange.js:12-29`). • 40 permission checks per discovery request (`tenant-app/data-access.js:236-248`). • Realtime ownership runs a whole-cluster `pg_locks` query every second (`postgres-connection.js:713`). • Harness `observe()` twice around every SQL read. | Verify per connection, with the existing invalidation on error, end and process-id change. Close the one gap: the settings facade admits any `SELECT`; restrict it to its value query. Memoise principal and subject per request. Fold the signing key into the verifier read and write one audit append. Compute permissions lazily. Check the ownership lock session for liveness. | Identity was **30.9% of exported SQL time and 1.34M probes** at 3k (reproduced). Removing it per read should return most of that (read-derived). Status goes from about 7 transactions to 3–4 (read-derived). |
| **C2 Materialize, then limit** | A window or cache over every qualifying row, then one row or one page returned | Already fixed: latest device status, SGV `count=1` (575 rows to 2), ten treatments (575 to 11). Remaining: • v3 `findMany` search and history: `bool_or(...) OVER ()` over the whole history (`postgres-entries-read.js:148-150,220-255`). • `jsonb_typeof` over every window row in the latest-probe guard (`:179-182`). • Profile working set (`clinical-working-set-policy.js:118`). • `dbstats` sums `pg_column_size` over every row on each frame load (`postgres-tenant-stats.js:18-20`). • Header-authenticated follower count-only requests preload 24–60 h with no `LIMIT` (`lib/data/private-acquisition.js`). • Harness `stored()`, the fixture digest and history censuses | Probe for exceptional rows with `LIMIT 1` on a partial index, then a plain ordered `LIMIT`. Use the generic reader only when the probe hits. Cache `dbstats` per write-clock stamp. Route header-authenticated followers through the bounded readers. Harness reads use indexed per-tenant witnesses. | Per request, O(history) becomes O(page). The benchmark sends query tokens, so the **header path is unmeasured and likely what real followers use** (read-derived). AAPS history polls stop scaling with history (read-derived). |
| **C3 Work for unrelated tenants, viewers or subjects** | Cost grows with the slice, the roster or the subject count instead of the request | • Every evaluator output for any slice tenant runs receipt work, check and an update even with no viewer (`lib/pgstream/realtime-receipt.js:165`, `realtime-output.js:28-29`). • A single global realtime `tick` (`runtime.js:111-113`). • Per-socket registry and settings reads at priming (`protocol.js:222,265,422`). • Credential checks load every subject × 50 verifiers (`secrets/legacy-postgres.js:79-101`). • Evaluator due query visits 875 index entries for 32 minima. • Watcher copies (fixed in `37f18c6ee`: 540,000 keys became 200 lookups). | Do realtime work only for watched tenants. Make reads per tenant, not per socket. Match credentials in SQL by digest. Use an owner-aware due index after its churn is measured. | Removes realtime database writes entirely (D23 holds structurally). Priming cost grows with tenants, not sockets (read-derived). |
| **C4 Round trips and held transactions** | A transaction stays open across extra round trips or non-query work | • API transactions send BEGIN, `set_config`, the shared lock and the window read separately. The commit fence runs on transactions that wrote nothing (`generation-scope.js:357-385`). The merged path exists but serves only the evaluator, behind a switch. • The settings snapshot checks out a second connection while the first is idle in transaction (`generation-scope.js:333-340`). • The follower frame is built inside the authentication transaction (`data-access.js:221-229`). | Use the merged open for every role and delete the switch. Skip the commit fence when nothing was written; the shared lock already excludes replacement. Bind the settings snapshot in one statement. Process after COMMIT. | About 4 of 9 round trips per read transaction (read-derived). A likely source of the **78–123 idle-in-transaction sessions** at 10k (read-derived). This and C1 are the main levers on the 5k pool saturation, which needed ≥48% less hold time. |
| **C5 Fixed budgets that should scale** | A constant sized at 1k or two days fails at 10k or 30 days | • Bootstrap migration statement timeout of 10 s: a 13 GB partial index took 59.6 s (attempt 8, reproduced). • Provision deadline 900 s. • `/dev/shm` 64 MiB, then 1 GiB, both failed. • Native work grant = setup 310 s + load. Viewer priming at 50 opens/s is not in it (10k cutoff, reproduced). • JWT setup concurrency 1. • Catch-up gate (300 s window, 3,600 s deadline) not in the grant. • 20 s, 145 s and 900 s history reads. • Trace rows, store volume size, log caps. | Indexes: the migration runner uses `CREATE INDEX CONCURRENTLY` outside a transaction, recording the ledger row once the index is valid. Deploy runs migrations as their own job, sized from relation sizes. Derive each budget from the plan and refuse at render when it does not fit the fixture eligibility or the controller window. | Attempts 3, 5 (10k) and 8 become offline refusals instead of paid losses (read-derived until replayed). At 30 days the devicestatus heap is about 15× today. Nothing in-transaction scales to that. |
| **C6 Checks that protect no product property** | A harness or test assertion turns a measured outcome into a stop or a misleading label | • 503s and +36 surplus rows became `M7_VIEWER_WRITE_COUNTS` FAIL at 5k (`viewer_plan.py:89-93`). • Fatal pre-load access witnesses (5 s HTTP, 60 s step). • The policy check required refusal by timeout specifically. • No retry on idempotent reads (attempt 1). • Seed census. | Score HTTP failures in the HTTP stage. Viewers score accepted writes, and a lost accepted write still fails. Witness timeouts are reported UNMEASURED and rerun after drain. Retry idempotent reads inside their deadline. Delete the rest under [architecture-justified-removal](multitenancy-decisions.md#architecture-justified-removal). | One paid attempt reaches a scored window. The 5k result is read by its real failure, pool saturation. |
| **C7 Edge-triggered state patched by more state** | Marks, receipts and owed indexes that need further states to recover lost edges | Realtime: durable receipts and their triggers; `availableAt`/`publishingAt`; pending deferral plus `owesPendingPublication`; warming, `TENANT_WARMING`, `parked`; held, `missed` and `resend`; a sweep that re-arms after its walk; ownership loss leading to `process.exit(1)` | Level-triggered delivery. Per tenant: `{revision, identity, frame, generation, inflight}`. Per socket: `{rights, authorizedAt, sentRevision}`. Send when the socket's sent revision is older than the tenant's durable revision and its authorization is fresh. Per-tenant single flight with a deadline. Errors withhold frames and never disconnect. One fixed-rate sweep. On ownership session loss, quiesce and re-acquire, exiting only on a definitive conflict. | Each reproduced incident has no state to occur in: the lost watched revision, duplicate sweeps, 186,679 warming attempts, disconnects on uncertain reads, the ordinal 6 stall (a hung refresh blocked the pod's single tick; read-derived), and ownership exits during a PostgreSQL CPU spike. |

Kept deliberately: the write clock and activity gate inside write transactions (one writer per tenant),
time-only evaluator cycles (alarms without uploads), and the revocation bound.

## 3. Lanes

| Lane | Classes | Branch | Local handoff |
|---|---|---|---|
| Storage and API | C1–C5 (product) | `claude/bounded-api-20261124` from `37f18c6ee` | `HANDOFF-bounded-api-20261124.md` |
| Realtime | C7 and its C1, C3 instances; joins start-up fix `ca877562d` | `claude/realtime-level-20261124` from `37f18c6ee` | `HANDOFF-realtime-level-20261124.md` |
| Harness and deploy | C5, C6 (harness), C2 harness reads | `claude/harness-budgets-20261124`, deploy `claude/deploy-budgets-20261124` from `963fe08e6` | `HANDOFF-harness-budgets-20261124.md` |

**Testing:**
- Changes whose need is established are made without new tests. Tests that assert removed mechanisms are deleted.
- Red/green controls only where a product property is touched: restore fencing for C4, revocation for C1, parity for C2.
- Each lane runs its affected tests. The full suite runs once on the joined candidate, followed by one acceptance campaign.
- A result that does not support a prediction is diagnosed backwards from the failure, not routed around.

## 4. Experimental churn

C5 needed ten paid attempts. Attempts 1, 2, 3, 5 (10k) and 8 were lost to the harness or setup, not to the
product (reproduced). After C5 and C6 the joined harness runs a single offline `preflight`. It refuses a grant
that ends after fixture eligibility, viewer source-port use over 60%, an image missing from the private
registry, a migration whose estimated build time exceeds its budget, and host `TMPDIR` or disk shortfalls. It
is checked by replaying the retained manifests of the lost attempts. Observers move into the cluster, so a
workstation outage no longer ends a run.

## 5. Data volume

- **Volume.** About 1.6–1.94 MB per tenant-day against 0.24–0.38 MB on MongoDB. At 30 days that is about 243 GB at 5k and 486 GB at 10k before WAL and free space ([storage proposal](storage-tiering-proposal-2026-11-24.md)).
- **Untested risk.** At 52 h the working set fits PostgreSQL memory. At 30 days it does not, and the one deeper sample showed 0.952 buffer hits.
- **Proposed measurement.** One 5k point at 14–30 days of history before claiming readiness. C2 and C5 must land first: both scale with history.
- **Partitioning.** It currently comes after the first production boundary, and moves earlier if that point fails on buffer hits or vacuum.

## 6. What a reader should expect next

The joined candidate (`37f18c6ee` + the three lanes) is qualified once, then run 3k → 5k → 10k in one campaign.
Measure statements per request type and per-role SQL time at every point, and keep the realtime per-stage
counter. The predictions above are confirmed or refuted by those figures. Neither this brief nor any lane
grants capacity.

## 7. Status after reconciliation with the Codex joins (2026-11-25 UTC)

All three lanes were integrated by the joint candidate owners. The current local candidate is core `427e99bd1`
(`codex/storage-performance-join-20261124`), deploy `9cccbbbd8`, harness `13d8d4e5d9`. It joins realtime/API
`0fec9b6c8` (realtime `42f48eac0` plus bounded API `8e43602ed`), storage parity and bounded v3 history pages.
Its full qualification passed locally (reproduced: 9,368 ordinary tests, 1,199 corpus tests, three browsers).
None of it has capacity acceptance.

| Class | State on `427e99bd1` | Open |
|---|---|---|
| C1 | Fixed. Display identity is checked once per client; the settings facade refuses `set_config` and a login with role memberships. Status reads its verifier and subject once and makes one audit append. Discovery permissions are lazy. Reproduced: status 66.3 → 23.2 statements per request on the token path. | — |
| C2 | Fixed: latest SGV, treatments and device status; v3 history (11 rows per ten-entry page); tenant storage size per clock stamp. | v3 search; header-authenticated count-only treatments and device status (whole cache window); profile window guard |
| C3 | Fixed: the verifier read returns one subject (21 → 1 rows with 21 subjects); realtime work only for watched tenants. | evaluator due index (measure churn first) |
| C4 | Fixed: one round trip to open (4 → 1); read requests run READ ONLY with no commit fence; the settings snapshot is bound in one statement. Reproduced: ordinary v1 reads 14.15 → 7.15 round trips. | settings read-only proof as a separate statement; token-exchange audit append on a second connection |
| C5 | Fixed: single-index migrations build `CONCURRENTLY`; deploy budgets derive from declared sizes. | **New instance:** migration 0105 adds a stored generated column to entries, which rewrites the table under an exclusive lock. Replace it with an expression index built concurrently. |
| C6 | Fixed in the harness: derived grants, one preflight (refuses lost attempts 3, 5 and 8 offline), viewer scoring of accepted writes only, retried reads, observer in the controller Pod. | viewer actor sharding (the port-range override covers 10k) |
| C7 | Fixed: level-triggered realtime, receipts retired by migration, ownership quiesces and re-acquires. Booted locally: the role re-acquired its ordinal and released a withheld frame after fresh authorization. | 10k effect unmeasured |

The open C2, C4 and C5 items continue in the storage/API lane, from `427e99bd1`.

### Continuation on `claude/bounded-open-20261125` (2026-11-25)

Local branch from `427e99bd1`, commits `023aab125` and `6f43538db`; nothing pushed.

| Item | Result |
|---|---|
| C5: `0104_entries_clinical_time`, `0105_entries_history_ms` | **Reproduced** on PostgreSQL 16.15 up to 2.59M entries rows. Both hold ACCESS EXCLUSIVE and block writers for the whole run: 260 s and 9.9 GB WAL (0104), 49 s and 3.2 GB (0105). `0106` does not block. A linear extrapolation to 10k tenants × 30 days gives about 2.4 h and 0.47 h of blocked writes (read-derived). Expression indexes built concurrently do not block, but under row-level security the history page then examines 16,860 rows instead of 11. A leakproof wrapper restores 11 but must be created by a superuser. Two defects were found: the runner's 600 s maximum statement timeout cannot hold the rewrite at size, and `clinical_instant_ms` is declared PARALLEL SAFE while containing an EXCEPTION block, so parallel index builds fail. **Maintainer decision pending.** |
| C2: v3 search | **Fixed** (`023aab125`, reproduced). A date-sorted ten-entry page examines at most 11 rows, against 597 before. The MongoDB differential passes. One response changes: an unindexed array or subdocument value in `identifier` or `created_at` outside the page no longer answers 500, matching MongoDB. Default-sort and other-field searches remain unbounded (read-derived). |
| C2: header-authenticated count-only treatments and device status | **Not built.** Parity with the cache path needs a sparse index on rows whose `event_ms` is NULL or that carry their own `mills`; a prototype read 11 rows instead of 575 (reproduced). Sealed device status also needs `mills` exposed. The index waits on the migration decision. |
| C2: profile window guard | **Not built.** Needs a start-time text index and an exception index; a prototype read 2 rows instead of 2,000 (reproduced). |
| C4: settings read-only proof | **Fixed** (`6f43538db`): 5 → 4 statements per settings read, with a red/green control. |
| C4: token-exchange audit append | **Unchanged.** Moving it after COMMIT would reorder token issuance against the restore fence (read-derived). |

**Maintainer decisions, 2026-11-25.**
- `0104`/`0105` stay as written. No production database exists, so the table rewrite is paid once on our own fixture, migrated offline with an explicit budget.
- `clinical_instant_ms` gets a successor migration that corrects its parallel-safety declaration.
- The v3 search change is accepted: a stored array or subdocument in `identifier` or `created_at` no longer fails a read.
  Writing such values is a defect in both modes. The API v3 spec types `identifier` as a string, and `created_at` is a timestamp.
  Reproduced on `official/dev` `79144cbd0` (BF-249): a non-string `identifier` is already treated as absent, or refused under `WRITE_IDENTIFIER=strict` (#8879); it was stored on `v15.0.9`. `created_at` arrays and objects are stored as sent, or stored as a different instant, on v1 entries, profile, food, treatments and devicestatus writes and on v3 PATCH.
  The single-tenant backfix is being checked separately; reads keep tolerating values already stored.
- Both concurrent single-index migrations are approved: the header-authenticated follower read and the profile check.
