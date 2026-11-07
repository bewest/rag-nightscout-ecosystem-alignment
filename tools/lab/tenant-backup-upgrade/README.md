# Focused tenant backup/upgrade PostgreSQL proof

This lab runs the application's explicit five-case PostgreSQL suite against an
owned disposable PostgreSQL 16 fixture, then semantic mutants and restorations.
It archives the selected committed application source into scratch and uses an
explicit private dependency copy whose recorded source lock must match.

A coordinator runtime grant is required. `--grant` records its reference; it does
not obtain a slot. No serving listeners, Vault, MongoDB, full suite, browser or
corpus campaign runs here. Representative entries/clock evidence does not establish
full Batch C inventory, durable backup storage or provider-key recovery.

```bash
python tools/lab/tenant-backup-upgrade/run.py \
  --worktree "$CRM_WORKTREE" --deps "$PRIVATE_NODE_MODULES" \
  --out "$NEW_CAPTURE_DIRECTORY" --grant "$COORDINATOR_GRANT"
```

Before running, copy the exact source `package-lock.json` into private node_modules
as `.codex-source-package-lock.json`. No dependency install or application pool is
used. The local `postgres:16` image must already exist; pulling is disabled. Fixture
credentials are random, passed through the child environment and never recorded.

Every invocation captures a JSON reporter result, stderr, resource audit, source
archive and semantic patch metadata. Exact owned containers and their observed
anonymous volumes must be physically absent; the independent Docker inventory
must return to baseline. Emergency cleanup is restricted to a recorded exact
container ID and invalidates acceptance. No unrelated resource is removed.

Predictions: initial five cases green; four semantic mutations each produce one
assertion failure (not an SQL/setup/timeout error), then the corresponding restored
test passes. Final five-case restoration must be green with zero pending.

| Control | Required red symptom |
|---|---|
| Disable artifact file-digest check | Damaged artifact loses the prewrite RESTORE_DIGEST_MISMATCH refusal |
| Disable restored-row comparison | Lying successful insert no longer raises RESTORE_ORACLE_MISMATCH |
| Substitute COMMIT for ROLLBACK | Interrupted restore leaves rows visible to independent raw SQL |
| Suppress independent comparison differences | Self-consistent lost tenant-B entries are no longer named |

`--stages initial`, `--stages controls` or `--stages restored` limits an invocation
to an explicitly selected stage after a stopped run or focused repair. Existing
capture directories are refused. Unexpected outcomes stop the campaign and retain
raw failed history; repairs require a new committed source head and new capture.
`manifest.json` and `sha256.json` freeze attribution and artifact hashes. No disabled
suite, registered case or fake-client result counts as native evidence.

## Recovery scope

The [representative native proof](../../../reports/tenancy/backup-upgrade-native-f77-2026-11-06.md)
records the executed entries/clock boundary. Apply the
[restore identity and cloning decision](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#restore-identity-and-cloning):
this laboratory exercises original-tenant recovery. Cloning implementation/native
acceptance, the full selected catalogue and durable backup storage remain unmeasured.
