# Populated recovery: early source-only proof

Contributor-facing research instrument, 2026-11-06. This is the early Batch C
assumption check from the [completion plan](../../../docs/30-design/tenancy/multitenant-integration-batching-plan-2026-11-06.md#5-current-completion-schedule-adopted-2026-11-06).
It requires actual CRM modules by an explicit worktree path. It opens no database,
network listener, Docker service or secrets provider and implements no backup tool.
Its injected target records importer callbacks; it is not a simulated PG adapter.

```bash
node tools/lab/populated-recovery-proof/preflight.js --worktree "$CRM_WORKTREE"
node tools/lab/populated-recovery-proof/preflight.js --worktree "$CRM_WORKTREE" --control broken-snapshot
node tools/lab/populated-recovery-proof/preflight.js --worktree "$CRM_WORKTREE" --control wrong-tenant
node tools/lab/populated-recovery-proof/preflight.js --worktree "$CRM_WORKTREE" --control missing-key-reference
node tools/lab/populated-recovery-proof/preflight.js --worktree "$CRM_WORKTREE" --control partial-restore
node tools/lab/populated-recovery-proof/preflight.js --worktree "$CRM_WORKTREE"
```

Predicted positive/restored exit 0. Each control damages an independent candidate
fixture; assertions determine exit 1. None forces an exit based on the control name.
The report records the actual CRM commit, fixture hash, individual outcomes and
remaining UNMEASURED properties. The preflight refuses tracked application modifications with `CRM_TREE_DIRTY`,
so the measured code has commit-only provenance. Dependency integrity remains
the caller's responsibility; use the pinned tree's matching installation.

## Capability boundary reproduced

The actual `lib/import/entries.js` API importer accepts only nonempty textual `_id`
values. A raw ObjectId is `IMPORT_DOCUMENT_INVALID`; ObjectId/string twins exposed
as the same API string produce `IMPORT_ID_COLLISION` before the first page write.
This is fail-closed behavior, not typed import fidelity. The lower-port
`lib/storage/postgres-identity.js` codec preserves kind outside JSONB, and its actual
encode/decode functions distinguish the twins across JSON serialization.

Therefore an API JSON export/import cannot be assumed to preserve a complete typed
Mongo snapshot. Do not flatten IDs, rewrite the importer or claim typed restore
from its string-only success. The existing importer is a bounded, one-time live
baseline plus best-effort history pass, not a snapshot: moving offset boundaries
and permanent deletions remain explicit limitations. Each target page has its own
transaction; a failed later page does not imply rollback of earlier pages. Rerun
starts at the beginning; no durable cursor is implemented.

The migration runner provides catalogue validation, checksums and transactional
ledger foundations. Its Mongo primary-restart test is same-server recovery; it
has no exported-volume restore. The older execution-plan reference to
`lib/admin/platform-store.js` is absent from the frozen CRM tree used here;
that historical export path must be located and reconciled before using it as an
instrument for current implementation acceptance. It has no import counterpart
in the execution plan. No replacement export service is invented here.

## Synthetic fixture and criterion-to-artifact specification

[fixture.json](fixture.json) is a research test vector, not an adopted backup format.
It has two synthetic tenants and a populated typed row set plus an API-supported
subset. JSONB logical object equality ignores object member order; missing/null
remain distinct, array order and values remain exact. Equal-time rows do not imply
natural/insertion-order preservation; that needs a separately defined ordering key.

| Criterion | Fixture / independent oracle | Real campaign artifact required |
|---|---|---|
| Typed identity fidelity | ObjectId and string with identical text in A; same string in B; codec kind plus text key | Before/after query of tenant, kind, textual identity and document, decoded with actual codec; no flattening or cross-tenant collapse |
| Populated value fidelity | Nested source metadata, null versus absent, false/zero/empty string, array sequence, nested `_id`, soft-delete marker | Canonical logical JSON documents keyed by tenant/kind/id, with absent membership asserted separately; snapshot digest alone is insufficient |
| Import interruption/rerun | Supported API rows across two pages; injected later-page failure and full rerun | Real independent stored reads after interruption and rerun; committed page retained, failed page atomic, no duplicated identities; API importer still string-only |
| Migration compatibility | Actual entries candidate checksum validated, changed SQL rejected | Restored schema/ledger history and exact checksum comparison; serving `check` read-only and stale/drift refusal; restored data alone is insufficient |
| Tenant boundary | A/B overlap; wrong-tenant candidate fails local oracle | Actual restricted NOSUPERUSER/NOBYPASSRLS query/write attempts and unchanged B oracle under A binding |
| Ciphertext/key completeness | Synthetic opaque record reference names a synthetic provider key version | Actual provider-backed decrypt/verify after recovery, correct tenant only; key material stays outside data manifest/logs. Local metadata presence is not key recovery |
| Partial restore refusal | Candidate missing final row fails complete typed-key/value oracle | Interrupted real restore never admitted as complete; independent completeness plus startup/schema check before activation |
| Order contract | Equal `date`, distinct typed identities; array order exact | Explicit stable sort query if promised, populated import backfill test; unspecified equal-key/natural order stays unclaimed |

## Smallest early real experiment (one owned campaign; NOT RUN)

The first experiment should answer whether a populated PG snapshot, its reviewed
migration ledger and lower-port identity metadata can be restored into an isolated
fresh target without value/tenant loss, while comparing the supported API-import
subset. It can invalidate Batch C's implementation assumptions before lifecycle
and backup tooling grow around them. This is not M6 acceptance.

1. Confirm final candidate/clean tree and still-open task; stop/report a mismatch.
   Coordinate the runtime slot, disk and inotify capacity. Own all random ports,
   private output directories, container IDs and mounted volume IDs. Record
   provenance before starting; never use existing operator databases or delete
   resources by creation window alone.
2. Extend the existing `tests/entries-importer-postgres.integration.test.js`
   fixture in an owned application lane with these populated cases, reusing its
   restricted connection/tenant oracle. Use the actual operator migration
   catalogue/runner for the source schema and retain ledger/checksums; do not
   silently substitute the generated test DDL for migration acceptance. Use the
   actual lower-port writer/codec for typed twins and actual importer for the
   string-only subset; invoke the actual migration compatibility checker after
   restore. This new test extension is **UNIMPLEMENTED** here.
3. Provision disposable source and fresh restore target PostgreSQL instances.
   Use the image's actual `pg_dump --format=custom` and `pg_restore --exit-on-error`
   tools via an owned fixture helper; connection credentials remain environment/
   stdin only. Review the exact inclusion of schema, ledger, tenant data and role
   privileges before the run. A schema-only dump must never be called a populated
   snapshot. A database restore does not restore external Vault keys.
4. Seed the fixture values. Capture independent logical/typed A/B oracles and the
   migration ledger. Stop writes for this first reference experiment so the
   snapshot-consistency assumption is explicit; concurrent live snapshots require
   later separate evidence. Export, restore into the clean target, compare
   values/identities/ledger and read-only startup checks. Independently execute
   the API importer subset and interrupted-page/rerun cases against a separate
   empty namespace; compare stored values rather than callback delivery.
5. Run the controls below against owned scratch exports/targets, restore and
   rerun. Record actual error codes and stored state; setup errors are not
   semantic controls. Run the existing focused suites plus the new populated
   cases as one campaign, not one full campaign per tool:

```bash
# After extending the existing integration test in its owned application lane:
env -C "$CRM_WORKTREE" NODE_ENV=test TZ=UTC NS_TEST_POSTGRES_ADMIN_URI="$OWNED_TEST_PG_ADMIN_URI" \
  node "$CRM_WORKTREE/node_modules/mocha/bin/mocha.js" --fail-zero --exit \
  --timeout 120000 "$CRM_WORKTREE/tests/entries-importer.test.js" \
  "$CRM_WORKTREE/tests/entries-importer-postgres.integration.test.js"
# Run from CRM_WORKTREE; fixture must own/clean both fresh PG services.
# Separately reuse operator runner's existing owned migration campaign:
CRM_REST_WORKTREE="$CRM_WORKTREE" TZ=UTC \
  node tools/lab/multitenant-rest-preview/owned.js migration
```

These existing commands alone do not perform the proposed snapshot experiment:
the populated snapshot extension must exist and execute before any claim. Run the
focused additions inside the application's working directory with a private
matching dependency installation. No total or duration is predicted before the
extension inventory is measured.

| Control | Predicted real semantic red; not yet executed |
|---|---|
| Broken snapshot | An altered/truncated dump refuses `pg_restore`, or an omitted/changed row fails independent logical-value completeness; never call an apparently successful tool exit alone green |
| Wrong tenant | Bind A while selecting/restoring B through application credentials: RLS refuses/returns no B rows, with B unchanged. A privileged dump identity's cross-tenant visibility is not itself proof of serving isolation |
| Missing ciphertext key | After the provider-recovery fixture is selected, restore real synthetic ciphertext without its required key/version: actual decrypt/verify explicitly refuses; no plaintext fallback, wrong-tenant key or invented local signer |
| Partial restore | Interrupt after an identified committed restore unit. Startup/activation must not label the populated restore complete; expected incomplete oracle and supported recovery/refusal policy must be established before implementing that policy |
| Restore-loses-kind | In scratch only, flatten identity metadata: typed-twin count/value oracle fails even when textual IDs look equal |

6. After every case, collect exact-owned container mount metadata before teardown,
   verify those containers/volumes absent and compare independent before/after
   resource inventories. Unknown resources remain untouched. Publish synthetic
   results and redacted diagnostics, never credentials, user exports or key bytes.

## Choices and remaining UNMEASURED work

The first PG experiment deliberately does not select an authoritative whole-tenant
backup format, Mongo-to-PG typed migration policy, provider key export/recovery
method, deletion authorization, retention rule or numeric RPO/RTO/resource budget.
Deletion is operator-authorized/executed after the adopted lifecycle prerequisite;
owner export/deletion requests and operator capabilities remain distinct. Those
choices belong to the maintainer and adopted contracts. Missing-key metadata in
this preflight proves no ciphertext recovery. Actual key recovery, Mongo snapshot
restore, cross-store consistency, permanent deletion, live-write snapshot behavior,
upgrade/rollback, resource/egress/performance and final assembled M6 V&V remain
**UNMEASURED**.

## Captured local result (2026-11-06)

[Results](results/2026-11-06/positive.json) use actual CRM
`65bb8456618df9816106692a32f0dd5c76e216d1`: source-only positive **10 passing,
0 failing**; altered snapshot **9/1**, wrong tenant **8/2**, missing key reference
**9/1**, partial candidate **8/2**; restored **10/0**. Every red is an assertion
on damaged local fixture metadata/value state, not database or provider evidence.
The actual importer refusal, callback preservation, retry traversal, soft-delete
history and candidate-checksum checks execute the shipping modules. No fixture
service was started. All artifacts are synthetic. No full suite, browser, database
campaign or final application prcheck ran; no milestone or readiness promotion.
