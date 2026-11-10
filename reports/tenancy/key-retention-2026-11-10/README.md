# MT-KEY-RETENTION (M6b): 30-day key retention, operator destroy, restore window

*Measurement record, 2026-11-10. Contributor-facing, except the operator note in section 7. Not
edited after capture.*

## 1. Anchors

| tree | ref | commit |
|---|---|---|
| cgm-remote-monitor lane | `codex/key-retention-20261110` head | `ed46cc4330277ccdd2a5debd0f2f384d0af3f957` (1 commit on base) |
| base (draft #8898 head) | `dc795bd1` | `dc795bd1515f11808a8d0732f2be9925cb2ffcd1` |
| `official/dev` | ancestor of the lane head | `4a482627` |
| alignment `main` at writing | | `325978710` |

Worktree: `externals/work/crm-key-retention-20261110`. 17 files changed, +889/−59. Local, unpushed.

Decision implemented: [`tenant-deletion-key-retention`](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#tenant-deletion-key-retention)
(option (a), 30 days).

## 2. What the change does

- **Completeness before removal** (`lib/tenant-lifecycle/key-retention.js` `assertKeyCompleteness`,
  called from `verifyDeletionRows` in the destructive transaction and at claim). The artifact must
  name every key a trusted `keyInventory({tenant})` capability returns (names only,
  `[{mount,name}]`) and hold every live ciphertext with its key reference. Refusals:
  `LIFECYCLE_KEY_NAMES_MISSING`, `LIFECYCLE_KEY_REFERENCE_MISSING`, `LIFECYCLE_KEY_REFERENCE_UNKNOWN`,
  `LIFECYCLE_KEY_MATERIAL_UNVERIFIED`. A missing per-ciphertext reference is refused earlier, at
  artifact validation (`LIFECYCLE_CIPHERTEXT_WITHOUT_KEY_REFERENCE`, existing).
- **Retention record**: new lifecycle migration `0005_tenant_lifecycle_key_retention`
  (checksum `a12b4238…8fa7d`), forced RLS, written in the same transaction as the deletes:
  `retained`, `retain_until = executed_at + 30 days`, key names, key-reference count. No ciphertext.
  CHECK constraints refuse `restored_at` outside the window and a destroy start before `retain_until`.
- **Restore gate**: `importArtifact` and `restoreLogical` require `ledgerNamespace`; inside their
  transaction, before the first write, they refuse `LIFECYCLE_KEYS_DESTROYED` (any record
  `destroying`/`destroyed`) or `LIFECYCLE_RETENTION_EXPIRED` (a `retained` record past its window).
  Inside the window the restore proceeds and the record becomes `restored`. Never-deleted tenants
  have no record and are unaffected.
- **Destroy**: `destroyRetainedKeys` is operator-plane only (via `authorize`, action
  `destroy-keys`), requires the intent string `destroy-retained-keys:<tenant>:<requestId>`, an ended
  window, and zero tenant rows in every admitted table. It commits `destroying` with actor/time,
  calls the custodian, then commits `destroyed` with actor/time. Provider failure leaves
  `destroying` (restore still refused); retry is explicit and idempotent.
- **Custodian**: `lib/secrets/vault-transit-custodian.js` — separate operator credential; per key it
  checks `keyAllowed`, sets `deletion_allowed`, deletes, confirms 404 (absence, not 403). Fixed error
  codes only.
- **Time** is the injected `now` of each call; the 30-day constant is not configurable.
- **Pre-existing defect fixed (reproduced)**: `ceremony.js` `ready()` admitted only
  `[tenant_lifecycle_requests, tenant_lifecycle_ceremony]` in the ledger namespace, while the
  candidate's 0003/0004 create four more tables there. On base `dc795bd1`, a namespace migrated with
  the full candidate (0001–0004) refused `requestDeletion` with
  `LIFECYCLE_RELATION_UNADMITTED: lifecycle.tenant_lifecycle_operations` (native probe, PostgreSQL 16).
  The lane head lists every candidate-created table (`LEDGER_TABLES`); the same probe returns
  `accepted`. The recording unit double modelled only two tables, so the unit tier could not see it.

## 3. Commands and results (from tool output)

Unit/protocol (worktree, `node bin/with-env.js ./tests/ci.test.env node_modules/mocha/bin/mocha.js --fail-zero --timeout 10000 --require ./tests/hooks.js --exit <files>`):

| run | result |
|---|---|
| baseline on base, 7 lifecycle files | 151 passing |
| `tests/tenant-lifecycle.test.js` on head (23 existing + 8 new retention cases) | 31 passing |
| 9 focused files (lifecycle, logical restore, insertion lifecycle, deployment ops, operations, window readiness, maintenance window, multitenant inventory, secrets) | 180 passing, 0 failing |
| `node scripts/test-select.js affected --depth 4 --since dc795bd1 --run` (own `mongo:7.0.43`) | unit 370 passing; harness 33 passing; integration 16 passing, 274 pending (opt-in); 0 failing |
| `node scripts/test-tiers.js check` | 610 test files, 8 tiers: ok |
| `node scripts/test-multitenant.js --list` | 48 opt-in suites (48 in the inventory) |
| ESLint on changed files and `lib/tenant-lifecycle`, `lib/secrets` | 0 errors; 1 warning in untouched `lib/secrets/vault-token-source.js` (same on base); 2 warnings in `scripts/test-multitenant.js` at lines 260/539, not lines this lane changed |

Native suite `tests/tenant-key-retention.integration.test.js` (`NS_KEY_RETENTION_DOCKER_TEST=1`;
own containers `ns-kr-pg-*` `postgres:16` = 16.15 (Debian 16.15-1.pgdg13+2), `ns-kr-vault-*` Vault
2.2.1 dev, digest `962a9287…`; synthetic tenants): **6 passing**.

| case | observed |
|---|---|
| control: artifact missing the signing key name | `LIFECYCLE_KEY_REFERENCE_MISSING` detail `transit/tenant-11111111-signing`; A secret/audit rows 1/1 kept; no retention row; both A keys 200 |
| execute with complete artifact | 2 rows deleted; record `retained`; `retain_until − retained_at` = 2592000000 ms; A keys still 200 |
| gate: restore at window − 1 ms | 2 rows written; ciphertext byte-identical; decrypts to the synthetic credential; record `restored`; later destroy refuses `LIFECYCLE_RETENTION_RESTORED` |
| gate: restore after window (second deletion) | `LIFECYCLE_RETENTION_EXPIRED`; 0 rows |
| gate: destroy then restore | window-open and wrong-intent refusals made no provider call (keys 200); destroy → A keys 404/404, B keys 200/200; actor recorded at both steps; restore of either artifact `LIFECYCLE_KEYS_DESTROYED`; artifact ciphertext decrypt `SECRETS_PROVIDER_REFUSED`; B secret still decrypts |
| custodian scope | policy-denied B key → `SECRETS_PROVIDER_REFUSED`; `keyAllowed` false → `SECRETS_KEY_NOT_ADMITTED`; B keys 200 |

Multitenant opt-in portions (`node scripts/test-multitenant.js --only …` ×7: tenant-insertion-upgrade,
tenant-insertion-readiness, tenant-operations, postgres-migrations, postgres-secrets (with
`NS_VAULT_DOCKER_TEST`), tenant-key-retention, multitenant-preview-process), run record `e8572f17fcf4`,
2026-11-10T19:01:16Z–19:02:40Z: **65 passing, 0 pending, 0 failing**; script-owned PostgreSQL
container and volume verified absent.

## 4. Break-it controls (each restored, file `cmp`-identical afterwards)

| ablation | unit | native | restored |
|---|---|---|---|
| skip the completeness check (`assertKeyCompleteness` returns early) | 2 failing: "records a 30-day retention window…" (key count), "gate: an artifact missing one key reference…" (`Missing expected rejection.`) | 4 failing, first "control: an artifact missing one key reference…" (`Missing expected rejection.`) | 31 / 6 passing |
| ignore the window (expired check removed) | 1 failing: "gate: restore after the window…" (`Missing expected rejection.`) | 1 failing: "gate: restore after the window…"; refusal code became `23514` — the table's CHECK on `restored_at < retain_until` rolled the restore back (second layer) | 31 / 6 passing |
| ignore destroyed (destroyed check removed) | 2 failing: "gate: destroy then restore refuses…", "a provider failure leaves the record destroying…" | 1 failing: "gate: operator destroy … then restore refuses" (`Missing expected rejection.`) | 31 / 6 passing |
| ceremony ledger inventory reverted to two tables | 20 failing (`LIFECYCLE_RELATION_UNADMITTED: lifecycle.tenant_lifecycle_windows`; one timeout) | 5 failing (`LIFECYCLE_RELATION_UNADMITTED: lifecycle.tenant_lifecycle_key_retention`) | 31 / 6 passing |

A missing per-ciphertext key reference is guarded at artifact validation and again in the
completeness check; ablating the second layer alone leaves that case refused by the first (stated,
not a vacuous pass).

## 5. Shared surfaces changed (for the sibling lane MT-OWNERSHIP-OPS and the coordinator)

- Lifecycle migration `0005_tenant_lifecycle_key_retention` (append-only; 0001–0004 unchanged).
  Any other lane adding a lifecycle migration must renumber after 0005.
- Deployment census: `tests/tenant-deployment-operations.test.js` pins 46→47 / 47→48 tables and the
  lifecycle table list; `tests/fixtures/tenant-deployment-data.js` seeds the new table for both tenants.
- `importArtifact`/`restoreLogical` now require `ledgerNamespace`; `logical-restore.restore` requires
  a `retention` gate (test fixtures updated).
- Operator role grants: the deletion role needs `INSERT` on the retention table; restore needs
  `UPDATE (phase, restored_at)`; destroy needs `UPDATE` on the `destroy_*`/`destroyed_*` columns.
  `tools/lab/tenant-whole-c/core.js` lifecycle grants do not yet include the table.
- `tests/tiers.json`, `scripts/test-multitenant.js`: one row each. `git merge-tree` against the
  sibling head `6ee8fb04` is clean.

## 6. UNMEASURED

Full suite, `test:all`, `test:browser`, the full multitenant corpus and prcheck on the lane head (the
coordinator's frozen candidate); the full current catalogue through deletion and restore (identity
tables still refuse same-ID import, existing behaviour, so the native restore measured is the
secrets domain); production `keyInventory`, `authorize`, custodian credential issuance and Vault
policy; Vault Agent sink tokens for the custodian; artifact file expiry after the window;
whole-deployment backup/restore interplay (a restored older ledger or Vault snapshot can predate
`destroyed`); concurrent destroy versus restore on separate connections; HA/replicated Vault.

## 7. Operator note (plain language)

After you delete a site, its encrypted settings and credentials can still be brought back for 30
days, because the keys that unlock them are kept. Once the 30 days have passed, Nightscout refuses
to restore that site, and you can run the destroy step. **Destroy cannot be undone**: it permanently
deletes the site's encryption keys, so the site's stored credentials — in the database and in any
saved export file — can never be decrypted again by anyone. Destroy asks you to type the exact site
and request identifiers, only runs after the 30 days, refuses if the site has data again, and records
who ran it and when. It never shows a key or a secret. Glucose and treatment records in an export
file are not encrypted by these keys; delete the export file itself when you no longer need it.
