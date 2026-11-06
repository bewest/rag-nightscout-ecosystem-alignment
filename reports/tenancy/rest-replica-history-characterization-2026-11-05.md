# REST replica history characterization — 2026-11-05

*Contributor-facing measurement record. Reproduced parent focused evidence at
CRM `2a6eaf738382ef62b8b3bfd0c76dbd005abb8480`; subsequent instrument/cleanup
candidate `714f6c8b229fbea171db4e75cbf8179edd7d2d57` is not accepted. Alignment
baseline `f7b555338e150c5eabce81511bfc10b932cb9f1b`; local official/dev
`4a482627bfdafb1fef8dcbe0ac6c484811cae563`. Synthetic data only. This record
establishes a failed general replica-history contract, not stateless deployment,
Kubernetes, multi-node, high availability or durable event acceptance.*

## Question and result

Can two actual `nightscout multitenant api` CLI processes be interchanged on one
operator-managed machine without losing history visibility? Selected entries
CRUD, current grants and process replacement pass, but the broader claim fails:
two already-running processes can assign equal history timestamps to sequential
committed records, and an exclusive history cursor then omits the later record.

Both processes boot before the characterized writes. A new-format tenant data
token authenticates actual HTTP requests. First process POST succeeds; an
independent PostgreSQL connection reads its raw stored `srvModified`. HTTP history
returns that record and establishes the cursor before the second process POSTs a
different identifier. Both replicas then omit the later record from
`/api/v3/entries/history/<cursor>`, although addressed GET returns it successfully.

| Parent reproduced observation | Result |
|---|---|
| First raw PostgreSQL `srvModified` | `1793948823488` |
| Second raw PostgreSQL `srvModified` | `1793948823488` |
| Later record missing after exclusive cursor, queried through each replica | `true`, `true` |
| Later record addressed GET | succeeds through both replicas |
| Next write through the first process | `1793948823489` |
| Write after restarting the second process | `1793948823490` |
| Foreign tenant stored state | unchanged |

The fixture uses an explicit child `--require` preload and
`NS_PREVIEW_REPLICA_CONTROL=history-clock` with a shared millisecond value. Only
`Date.now()` callers whose stack includes `lib/server/srv-dates.js` see that value.
The actual allocator and storage code are unmodified. Authentication, expiry,
provider and timeout clocks remain real. This makes the scheduling condition
deterministic; no frequency under normal wall-clock load is measured.

Read-derived mechanism: `lib/server/srv-dates.js:35,62-68` keeps a per-process
`tenantClocks` map and advances against wall time; `restoreResolved:76-87` hydrates
from persisted values at boot. `lib/server/serve/preview-domains.js:68` restores
before serving. `lib/api3/generic/history/operation.js:74-84,103-104` uses an
exclusive predicate for the URL cursor. Same-process advancement and restart
hydration do not coordinate already-running allocators. No clock fix is selected.

## Bounded positive campaign

Node `v22.23.4`, npm `10.9.9`, private lockfile dependencies/build. Each fixture
owns disposable PostgreSQL/Vault containers and launches real CLI children.
Parent command at immutable `2a6eaf73`:

```bash
NS_MULTITENANT_PREVIEW_REPLICAS_DOCKER_TEST=1   node node_modules/mocha/bin/mocha.js --fail-zero --exit --timeout 120000   tests/multitenant-preview-replicas.integration.test.js
```

**Reproduced: 5 passing, 0 failing (11 seconds).** These include the expected
characterization of the failed history contract; the count is not replica
acceptance. Other bounded assertions:

- Actual entries POST/PATCH/read outcomes shared by both processes; equal
  identifiers in two tenants retain distinct values; data tokens cannot access
  another tenant or enable owner routes.
- Already-used legacy and new-format credentials observe independently committed
  role revocation on their next requests in both workers. Replacing one worker
  reacquires persisted authority; restoring grants restores access.
- A fixture holds the actual POST response after the handler calls `res.end`.
  An independent PostgreSQL read proves the row committed before SIGKILL. The
  client sees a transport error; retry through the survivor returns HTTP 200 and
  leaves one row for that identifier. No event/history exactly-once claim.
- Altered migration ledger checksum refuses startup before either listener
  binds; restoring the ledger permits startup and authorized reads.

## Semantic controls and instrument correction

At `2a6eaf73`, using the same opt-in command with selector and `--grep`:

| Selector / case | Reproduced outcome | Interpretation |
|---|---|---|
| `stale-authority` / `keeps legacy` | actual HTTP 200 where 403 required after committed revocation | Stale current-authority check detected; meaningful red |
| `readiness` / `refuses schema` | assertion `refused configuration must never bind` fails after actual listener bind | Bypassed schema admission detected; meaningful red |
| initial `cross-tenant` / `alternates committed` | HTTP 404 where 200 required | **Excluded**: request clone lost wire fields when Express reset its prototype; not foreign-data evidence |

Candidate `529d9c51` corrects the last instrument by copying own request descriptors
and its already-verified request-keyed authorization before deliberately routing
to the foreign tenant. Expected red is foreign marker `181` where `121` is
required. This corrected control and restored positives remain **UNMEASURED**
after the host capacity hold; do not count the original 404 as accepted evidence.

## Incomplete broad campaign and cleanup

A complete owned all-tier campaign was attempted at `2a6eaf73`; it exited 7 during
a confirmed host disk-full interval, with output ending during views equality
and no final campaign summary. It is **not accepted** and is not classified as a
product regression. Browser and final prcheck were not run. Tier classification
was reproduced: 503 files, 8 tiers, new replica test registered in integration.

The root filesystem measured 100% with zero available space; /home retained
capacity. Future lane logs/TMPDIR reside under owned /home scratch. Containers
had already been removed by existing `rm -f` cleanup before anonymous-volume
mounts were captured. The retained Docker event buffer could not reconstruct
ownership; no orphan volume was guessed or deleted.

Candidate `bd9c3ede` uses `rm -fv` for its own containers. `d93b7fca` records exact
mount/volume IDs before removal and verifies each owned volume is absent.
`714f6c8b` attempts all resource cleanup even if one attempt fails. These cleanup
paths have syntax/whitespace review but require actual rerun once capacity is
restored. No peer resources, shared source worktrees or central records changed.

## Boundaries and next work

Single-host selected entries/current-role evidence does not establish complete
session/key revocation, live environment convergence, all REST workflows,
shared database revision, durable publication or evaluator recovery. No M0-M6
milestone or release admission is promoted.

The user selected one operator-managed machine with separate roles first, then
multi-machine proof while preserving expansion boundaries. The additive local
policy commit is `b50736d85d21df7707cae1bb06ddae6826215888`; reconcile that decision
without replacing central main with its older branch tree.

After coordinator capacity approval: rerun corrected tenant control, stale and
readiness controls; restore all five positives on the final candidate; run full
all tiers, browser and final prcheck. Central owns separate clock/fencing
investigation and integration of this evidence. No production clock modification
or workaround is part of this lane.
