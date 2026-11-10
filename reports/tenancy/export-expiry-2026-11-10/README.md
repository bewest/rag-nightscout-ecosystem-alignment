# MT-EXPORT-EXPIRY: key destruction removes the export artifact file

*Supersedes the operator note in §7 of the [key-retention record](../key-retention-2026-11-10/README.md) (which stays as captured): the export file is now removed by key destruction; copies made elsewhere remain the operator's responsibility.*

*Measurement record, 2026-11-10. Contributor-facing, except the operator note in section 6. Not edited after capture.*

## 1. Anchors

| tree | ref | commit |
|---|---|---|
| cgm-remote-monitor lane | `codex/export-expiry-20261110` head | `701eba6f` (1 commit on base) |
| base (draft #8898 head, `refs/pull/8898/head` read from `ls-remote` at start) | `b70ad83f` | `b70ad83fa4cdaeb7e6023137a05bd811d7db606a` |
| `official/dev` at start | | `4a482627` |

Worktree `externals/work/crm-export-expiry-20261110`, local, unpushed. Item `MT-EXPORT-EXPIRY` was `not-started` in `make queue-status` at start. Decision implemented: [`key-destruction-removes-export`](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#key-destruction-removes-export), refining `tenant-deletion-key-retention`.

## 2. What the change does

- `destroyRetainedKeys` (`lib/tenant-lifecycle/key-retention.js`): after the custodian confirms every key absent, `removeExport(digest)` calls the `removeArtifact` capability with the `artifact_digest` held in the retention record (the digest column is CHECK-constrained to 64 hex). The outcome goes into the same UPDATE that writes `destroyed`, and the result carries `artifact: { digest, removal[, code] }`.
- `removeTenantArtifact` / `createFilesystemArtifactRemover` (`lib/tenant-lifecycle/filesystem-artifact.js`): path = configured private directory + `tenant-artifact-<digest>`; digest must match `^[a-f0-9]{64}$`; the directory must be absolute, private, not a symlink; the entry must be a real directory (symlink or file refused `LIFECYCLE_ARTIFACT_PATH_REFUSED`); removes that directory only; checks it is gone.
- Migration `0006_tenant_lifecycle_artifact_removal` (checksum `5299e9db…1e1c`): `artifact_removal` (`removed|absent|failed`) and `artifact_removal_code`, with a CHECK tying them to `phase = 'destroyed'` and to each other. Operator grants need `UPDATE` on both columns (native suite grant updated). Any lane adding a lifecycle migration renumbers after 0006.
- Without the capability, destroy refuses `LIFECYCLE_ARTIFACT_REMOVER_REQUIRED` before any state change.

## 3. Partial-failure behaviour (as implemented)

| case | keys | audit row | caller sees |
|---|---|---|---|
| file removed | destroyed | `removed` | `artifact.removal = 'removed'` |
| file already gone (ENOENT) | destroyed | `absent` | `absent` |
| cannot remove (I/O error, permission) | destroyed | `failed`, code `LIFECYCLE_ARTIFACT_REMOVE_FAILED` | `failed` + code; no path or system message |
| entry is a symlink/non-directory | destroyed | `failed`, code `LIFECYCLE_ARTIFACT_PATH_REFUSED`; target untouched | same |
| window open / intent / operator / remover missing | not destroyed | no change | refusal; file untouched |

The brief stated keys must remain destroyable and the audit must say what happened to the file; the cases above follow from that. Not stated, left as decision questions: (a) a repeat destroy on a `destroyed` row reports the recorded outcome and does not retry a `failed` removal (an operator deletes by hand, or a retry is added); (b) an interrupted attempt whose file was removed before the crash is recorded `absent` on the resumed call.

## 4. Commands and results (from tool output, worktree)

| run | result |
|---|---|
| `tests/tenant-lifecycle.test.js` (31 before, +5 new expiry cases) | 36 passing, 0 failing |
| 14 focused unit files (migrations, inventory, secrets, deployment ops, insertion x4, lifecycle, logical restore, maintenance window, operations, window readiness, operation window) | 234 passing |
| native `tests/tenant-key-retention.integration.test.js`, `postgres@sha256:9e2cf628…0a97` (the local `postgres:16`; image now overridable by `NS_KEY_RETENTION_PG_IMAGE`) and Vault `hashicorp/vault@sha256:962a9287…`, containers removed after (`docker ps -a` shows none) | 6 passing (destroy case now asserts the file removed, the restored request's file kept, the audit row, and two CHECK refusals `23514`) |
| `scripts/test-multitenant.js --only` tenant-insertion-upgrade / tenant-insertion-readiness / tenant-operations / postgres-migrations / tenant-key-retention (script-owned container) | 5 / 4 / 5 / 13 / 6 passing, 0 failing |
| `node scripts/test-tiers.js check` | 614 test files, 8 tiers: ok |
| `npm run lint`; ESLint on the changed files | 0 errors; 49 warnings elsewhere, none in changed files |

Tests required by the brief: after-window removes and audits (unit, native); before-window refuses and leaves the file (unit, native refusal step); missing file `absent` and keys destroyed (unit); unremovable file `failed` and keys destroyed (unit); malformed digests and a symlink-named artifact refused, victim file untouched, also through the destroy step (unit).

## 5. Break-it controls (each restored; `cmp`-identical to the pre-ablation copy)

| ablation | unit (`tenant-lifecycle.test.js`) | native | restored |
|---|---|---|---|
| skip the removal (`removeExport` returns `'removed'` without calling the remover) | 4 failing; first "expiry: destroy after the window removes…" `AssertionError: the export file is gone`; others compare `removal: 'removed'` against `'absent'`, since the test runs no file | 1 failing, `destroy removed the export file` | 36 / 6 passing |
| remove before the window check | 2 failing: "destroy after the window…" (`removal 'absent'` where `'removed'` expected, the file was already taken at the refused first call) and "destroy before the window refuses and leaves the export file" (strict-equal on file presence) | 1 failing, `refusals leave the export file` | 36 / 6 passing |

Both reds are for the intended reason (the named file assertion). The skip-removal unit run also fails the audit assertions, a second layer, stated.

## 6. Operator note (plain language)

When you destroy a deleted site's keys after the 30 days, Nightscout also deletes that site's export file from the export directory and records, in the same entry, whether it was removed, was already gone, or could not be removed. If it could not be removed, delete the file yourself. Copies you made elsewhere, such as backups, downloads or files on other servers, are your responsibility to delete; Nightscout only knows about the one file in the export directory.

## 7. UNMEASURED

Full suite, `test:browser`, full multitenant corpus and prcheck on this head (coordinator's frozen candidate); production directory permissions and a real read-only filesystem failure (failure is simulated by an injected `rm`); whole-deployment backups that contain the export file; lab `tools/lab/tenant-whole-c/core.js` lifecycle grants (the retention table and now the new columns are not in them); merge with sibling lanes touching `lib/tenant-lifecycle` (not run).
