# Tenant export/import fidelity and deletion: early Batch C proof

Contributor-facing research instrument, 2026-11-06. This is the Batch C early proof the
[completion plan](../../../docs/30-design/tenancy/multitenant-integration-batching-plan-2026-11-06.md#5-current-completion-schedule-adopted-2026-11-06)
names in its "Populated restore/import and contention" row and the roadmap's
[M6 packet](../../../docs/30-design/tenancy/multitenant-delivery-roadmap.md)
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

## Captured result (2026-11-07 UTC, two runs)

[results/2026-11-07/report.json](results/2026-11-07/report.json) is the record; figures below
are copied from it. Application tree `fd827e350a185ad73c838b013b25fe889434b036`
(branch `codex/tenant-export-delete-20261106`), fixture sha256 `e6afbf4e7a26…`,
PostgreSQL `16.15 (Debian 16.15-1.pgdg13+2)` from `postgres:16`, Vault `2.2.1` from the pinned
digest, wall clock 00:02:49 to 00:02:59 UTC, free disk 77,813,408 KB before and 77,813,304 KB after.

- **Run 1** (`report-run1-fatal.json`, application tree `7255414e`): fatal at the first migration;
  the lifecycle ledger candidate's CHECK patterns had lost their quotes when generated through a
  shell string (`syntax error at or near "^"`). No stage ran; its two containers and two volumes
  were verified absent. Fixed in `fd827e35`; trap recorded in the handoff.
- **Run 2**: `result: pass`. Positive stage: tenant A **39 rows across 29 admitted tables**
  (entries 6 with the ObjectId/string twins, treatments 2, food 2, tenant_settings_history 2,
  secret_records 2, secret_audit 2, one row in each of the other 23), tenant B 17 rows across
  16 tables. All 14 checks green: export counts equal the oracle; twins kept as
  `[objectid,string]`; 2 ciphertexts, no plaintext; backend terminated after row 5 left the target
  at 0 rows; rerun imported 39 rows, oracle equal across 29 tables; typed identity at the target;
  2 secrets decrypted at the target; request recorded with nothing deleted;
  `LIFECYCLE_ARTIFACT_STALE` with 40 rows intact; deletion thrown after the second table rolled
  back to 39 rows with B unchanged; execution deleted 39 rows, 29 tables at zero, B unchanged at
  17 rows, request `executed`; re-import restored 39 rows with 2 ciphertexts byte-identical;
  2 secrets decrypted after re-import; the Transit key present and non-exportable.
- **Controls**, each red for the predicted mechanism: `empty-catalogue` →
  `oracle: treatments.treatments: expected 2 rows, got 0` (import had accepted 37 rows);
  `drop-catalogue` → `LIFECYCLE_CATALOGUE_INCOMPLETE: treatments`, target 0 rows;
  `flatten-objectid` → `typed identity for 0123456789abcdef01234567: expected kinds
  [objectid,string] …, got kinds [string]` (38 rows imported); `omit-ciphertext` →
  `LIFECYCLE_KEY_REFERENCE_WITHOUT_CIPHERTEXT: secrets.secret_records.vendor-cloud`, target
  0 rows; `wrong-binding-delete` → `foreign tenant B changed:` 16 tables `expected N rows,
  got 0 | A (the deletion target) differences: none, A rows remain`; `no-rollback` →
  `interrupted import left 5 rows in the target (expected 0): entries.entries=5`.
- **Restored** stage: all 14 checks green again (export digest differs from the positive stage
  only by `exportedAt`; counts identical).
- Cleanup: both containers (`ns-lifecycle-04383f99-pg`, `-vault`) and the Vault container's two
  anonymous volumes verified absent by `docker inspect`; the PostgreSQL data directory was a
  tmpfs with no volume.

## Adopted decisions and remaining questions

- [Key/artifact retention policy is adopted](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#tenant-deletion-key-retention).
  R69 measures retained keys and artifact decryptability. Operator key destruction
  and restore-after-window refusal remain UNMEASURED; request-tombstone retention
  remains a separate policy question.
- [Restore identity and cloning policy is adopted](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#restore-identity-and-cloning).
  This probe exercises original-tenant restore. Cloning implementation and native
  acceptance remain UNMEASURED.
- DECISION: artifact size and transaction bounds; one transaction, no numeric cap here.
- DECISION: who calls `requestDeletion` (owner request) versus `executeDeletion` (private
  operator plane); the module enforces no authorization.

## UNMEASURED

Real tenant data, backup tooling, M6 acceptance, capacity thresholds, MongoDB-backed
catalogues, concurrent writers during export, and Vault key destruction remain UNMEASURED.
