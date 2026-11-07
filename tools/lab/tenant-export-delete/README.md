# Tenant export/import fidelity and deletion: early Batch C proof

Contributor-facing research instrument, 2026-11-06. This is the Batch C early proof the
[completion plan](../../../docs/30-design/tenancy/multitenant-integration-batching-plan-2026-11-06.md#5-current-completion-schedule-adopted-2026-11-06)
names in its "Populated restore/import and contention" row and the roadmap's
[M6 packet](../../../docs/30-design/tenancy/multitenant-delivery-roadmap-2026-11-02.md)
row C8. It builds beside, not inside, the source-only
[populated recovery preflight](../populated-recovery-proof/README.md) and R62's schema-level
`pg_dump`/`pg_restore` laboratory (`tests/fixtures/populated-recovery/lab.js` in the
application tree): those answer whether a whole-schema dump restores; this one answers whether
**one tenant** can be exported, re-imported and deleted with typed identity, tenant binding and
ciphertext/key references intact.

**The artifact this lab writes is a research artifact format, not an adopted backup format.**
No backup tool, retention rule, numeric bound or owner capability is selected here; see the
DECISION lines below and in the module README.

## What it measures

The application-side primitives are the dormant, opt-in module
`lib/tenant-lifecycle/` on the CRM branch `codex/tenant-export-delete-20261106`
(`README.md` there describes the operations and refusals). The lab requires them by worktree
path, provisions its own disposable PostgreSQL 16 and Vault dev server, and decides every
fidelity claim with an **independent admin-side oracle** (`SELECT *` per admitted table and
tenant, canonical JSON, multiset comparison) that shares no code with the module.

```bash
df -h /home   # rule 3: stop under 10 GB free; the runner refuses below the floor
node tools/lab/tenant-export-delete/run.js --worktree "$CRM_WORKTREE"
# optional: --stages positive,controls,restored   --out results/<date>
```

One invocation runs eight isolated stages (own schemas, roles and Vault keys each): the positive
stage, six controls, then the positive stage again (restored). It records the PostgreSQL and
Vault version strings, every count, each control's exact red text, and cleanup verification
(`docker inspect` must say "No such" for every container and volume the run created).

| Step | Mechanism exercised | Green means |
|---|---|---|
| export | `exportTenant` under `withTenant(A)` in one `REPEATABLE READ` snapshot through the lower port (`postgres-connection`, NOSUPERUSER NOBYPASSRLS role) | manifest counts equal the oracle's counts for every admitted table |
| typed identity | `id_kind` travels beside the JSONB document (`postgres-identity` codec kinds) | the ObjectId/string twins with the same hex text both survive |
| ciphertext only | `secret_records` rows travel as stored Transit ciphertext plus `{scheme, keyVersion}` references | no fixture plaintext appears anywhere in the artifact |
| interrupted import (kill) | the admin terminates the importing backend after five rows (`pg_terminate_backend`) | the target holds zero rows afterwards |
| import rerun | `importArtifact` into empty target schemas, one transaction, `OVERRIDING SYSTEM VALUE` for identity columns | oracle equal across every table, including generated columns and `food.insertion_ordinal`; foreign tenant absent |
| decrypt at target | the secrets component with the Vault Transit provider reads the imported rows | each synthetic plaintext decrypts |
| request deletion | `requestDeletion` writes the ledger row | row `requested`, nothing deleted |
| stale refusal | one row inserted after the export | `LIFECYCLE_ARTIFACT_STALE`, counts intact |
| interrupted delete (throw) | `onRow` throws after the second table | rollback leaves A and B exactly as before |
| execute deletion | `executeDeletion` verifies ledgers, every table digest and every secret's ciphertext/key reference, then deletes in reverse catalogue order | zero rows under A in every admitted table, B unchanged, request `executed` |
| re-import | A's artifact back into the source schemas | oracle equal, ciphertexts byte-identical, secrets decrypt again (recoverable key material); the Vault key is still present and non-exportable |

## Controls (each in its own isolated stage; predicted red)

| Control | Damage | Predicted red (exact assertion text is recorded in the report) |
|---|---|---|
| `empty-catalogue` | the treatments table exported with zero rows, artifact rebuilt consistently | the oracle reports `treatments.treatments: expected 2 rows, got 0` after a successful import |
| `drop-catalogue` | the treatments catalogue removed from the manifest | import refuses `LIFECYCLE_CATALOGUE_INCOMPLETE: treatments`, target stays empty |
| `flatten-objectid` | the ObjectId twin's kind rewritten to `string`, the string twin dropped | the typed-identity assertion fails: `got kinds [string]` |
| `omit-ciphertext` | one secret's row removed, its key reference kept | import refuses `LIFECYCLE_KEY_REFERENCE_WITHOUT_CIPHERTEXT` before any write |
| `wrong-binding-delete` | a defective executor trusting the binding alone, bound to B while deleting A | B's rows vanish and the foreign-tenant assertion fails; A's rows remain |
| `no-rollback` | a connection whose `transaction` is a plain call, so every statement commits alone | `interrupted import left 5 rows in the target (expected 0)` |

A control that stays green is a mismatch, and a control red for a reason other than the
predicted one is reported as such; neither is a pass.

## Captured result

See `results/<date>/report.json` beside this file once a run has been recorded; the handoff
and the release record quote its figures from that file, never from this page.

## Decision questions (not agent defaults)

- DECISION: key retention after tenant deletion. Secrets rows go only after their ciphertext
  and key references are verified in the artifact; Vault Transit keys are never deleted by this
  proof, so the artifact stays decryptable. Destroying keys, and how long artifacts and the
  `tenant_lifecycle_requests` tombstone are retained, is policy.
- DECISION: re-homing under a new tenant id. The secrets envelope binds the tenant id
  (`lib/secrets/component.js`), so the import target must equal the artifact's tenant.
- DECISION: artifact size and transaction bounds; one transaction, no numeric cap here.
- DECISION: who calls `requestDeletion` (owner request) versus `executeDeletion` (private
  operator plane); the module enforces no authorization.

## UNMEASURED

Real tenant data, backup tooling, M6 acceptance, capacity thresholds, MongoDB-backed
catalogues, concurrent writers during export, and Vault key destruction remain UNMEASURED.
