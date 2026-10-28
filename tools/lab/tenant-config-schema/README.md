# Tenant configuration schema lab (T30-SCHEMA-CONFIG)

*Contributor-facing. Built 2026-10-27 to support
[the tenant configuration schema spec](../../../docs/30-design/tenancy/tenant-config-schema-2026-10-27.md)
(queue `T30-SCHEMA-CONFIG`) and
[the migration-tooling plan](../../../docs/60-research/tenancy/migration-tooling-plan-2026-10-27.md).
It uses synthetic tenants, hosts and credential references only. No real data and no real
credentials are involved.*

Marks: **[M]** means this lab measured it, in the run recorded in `results.json`. **[R]** means
it is read or reasoned, not measured.

## What it is

The lab has three parts:

- **The schema**, as seven ordered migrations in `migrations/`, each with a `.down.sql`.
  - `0001` is the seam's `lib/admin/platform.sql` from cgm-remote-monitor `81a1f6ce`,
    byte-identical below a three-line header. It has the same sha256, `b50efaf0…`, as
    `git show 81a1f6ce:lib/admin/platform.sql`.
  - `0002` to `0007` add the configuration tables without altering `tenants` or
    `tenant_members`.
- **A runner**, `lib/migrator.js`, which drives the migrations through
  [umzug](https://github.com/sequelize/umzug) 3.8.2. It adds the three things umzug leaves to
  its caller: one transaction per migration and its ledger row, an advisory lock, and a
  checksum drift check.
- **A harness**, `harness.js`, with 57 tests. Each test runs twice on a fresh database cloned
  from a migrated template:
  - the **pass run** must be green;
  - each **control** removes the protection under test, and the same test must then go red.

  A control that stays green is reported as `VACUOUS?`, and the harness exits non-zero.

## Roles, and why the isolation tests are not vacuous

`bootstrap/roles.sql` creates four roles. The harness gives each one a random password per run
and keeps it in memory only.

| role | is | owns |
|---|---|---|
| `cfg_owner` | the migration role: `NOSUPERUSER NOBYPASSRLS` | every table (it runs the migrations) |
| `ns_operator` | the operator plane (D7) | nothing |
| `ns_tenant_admin` | the tenant-owner listener (D16) | nothing |
| `ns_api` | the consumer, evaluator and connector roles (D5, D21) | nothing |

Every tenant-scoped check runs as a non-superuser, non-owner application role. A superuser
bypasses RLS and would make an isolation test pass whatever the policy says. The harness checks
this three ways:

- `ISO-roles` asserts that each role is `NOSUPERUSER NOBYPASSRLS`, owns no table, and has
  `row_security_active()` true on every tenant table. Its control adds the container superuser
  to the list, and the test goes red. [M]
- Every `ISO-<table>` test has a second control that repeats the same reads as the superuser.
  It goes red on all seven tables, because the superuser sees tenant B's rows. [M]
- `ISO-roles`' second control removes `FORCE` from one table, and the owning migration role
  then escapes RLS. [M]

## How to run

You need Docker, Node 22 and a free port. The lab used 5447, checked free with `ss -ltn`.

```sh
S=/path/outside/the/repo            # holds the superuser password; never inside the repository
mkdir -p "$S" && chmod 700 "$S" && (umask 077; openssl rand -hex 24 > "$S/pg-superuser-password")
docker run -d --name cfgschema-pg -p 127.0.0.1:5447:5432 \
  -e POSTGRES_PASSWORD="$(cat "$S/pg-superuser-password")" postgres:16
cd tools/lab/tenant-config-schema && npm ci
node harness.js --secrets "$S"                    # about 60 s; writes results.json
node harness.js --secrets "$S" --only isolation   # one group, or test ids; results.json untouched
```

Before every run, the harness asserts that `cfgschema-pg` is running and is published on
`127.0.0.1:<port>`. It refuses a `--secrets` directory inside the repository.

## Results

Run of 2026-10-27, on PostgreSQL 16.15 (`postgres:16`) and Node v22.23.4: **57 tests green,
72 of 72 controls red.** The full record, including each control's error and the observations,
is in `results.json`. [M]

| id | what it shows | pass run | control (each must go red) |
|---|---|---|---|
| `ISO-tenant_members` | tenant_members: a role bound to tenant A reads, updates and inserts only A's rows; unbound it reads none | green | red: RLS disabled on the table<br>red: same reads as the container superuser (RLS bypassed) |
| `ISO-tenant_policy_override` | tenant_policy_override: a role bound to tenant A reads, updates and inserts only A's rows; unbound it reads none | green | red: RLS disabled on the table<br>red: same reads as the container superuser (RLS bypassed) |
| `ISO-tenant_setting_value` | tenant_setting_value: a role bound to tenant A reads, updates and inserts only A's rows; unbound it reads none | green | red: RLS disabled on the table<br>red: same reads as the container superuser (RLS bypassed) |
| `ISO-tenant_alarm_thresholds` | tenant_alarm_thresholds: a role bound to tenant A reads, updates and inserts only A's rows; unbound it reads none | green | red: RLS disabled on the table<br>red: same reads as the container superuser (RLS bypassed) |
| `ISO-tenant_config_version` | tenant_config_version: a role bound to tenant A reads, updates and inserts only A's rows; unbound it reads none | green | red: RLS disabled on the table<br>red: same reads as the container superuser (RLS bypassed) |
| `ISO-tenant_integration` | tenant_integration: a role bound to tenant A reads, updates and inserts only A's rows; unbound it reads none | green | red: RLS disabled on the table<br>red: same reads as the container superuser (RLS bypassed) |
| `ISO-tenant_integration_status` | tenant_integration_status: a role bound to tenant A reads, updates and inserts only A's rows; unbound it reads none | green | red: RLS disabled on the table<br>red: same reads as the container superuser (RLS bypassed) |
| `ISO-roles` | the roles the tests use are NOSUPERUSER NOBYPASSRLS, own no table, and RLS is active for each on every tenant table (row_security_active) | green | red: include the container superuser among the roles<br>red: NO FORCE on one table: the owning migration role escapes RLS |
| `ISO-complete` | every table with a tenant_id column has RLS enabled and forced and a policy on app.current_tenant_id (discovered, not listed); only `tenants` is exempt | green | red: a new tenant table without RLS |
| `MERGE-layers` | code default, operator default, per-tenant override default, owner value and operator pin each win where D22 says | green | red: merge ignores per-tenant overrides |
| `MERGE-override-narrows` | an override that narrows tenant B's policy after B's owner set a value: B falls back to the override default and the stale value is reported; A is unaffected | green | red: merge ignores per-tenant overrides |
| `MERGE-pin-beats-owner` | a per-tenant pin on A overrides A's stored owner value; B keeps its own | green | red: merge applies the pin before the owner value |
| `MERGE-floor-on-effective` | with no operator row for WRITE_VALIDATION the code default 'off' breaks the floor: the merge reports it so the process refuses | green | red: floors skipped in the merge |
| `MERGE-thresholds-refused-not-rewritten` | operator threshold defaults that are out of order are reported as a violation and left as written (no silent nudge, contrast BF-67) | green | red: threshold order check skipped |
| `MERGE-differential` | the merge's acceptance rule (JS) and the database's (cfg_value_ok + cfg_satisfies) agree on every case | green | red: an off-by-one in the JS ordinal minimum |
| `FLOOR-anon-roles-owner` | no anonymous writes: with the operator policy OPEN, an owner still cannot pick careportal or admin as a default role | green | red: project floor removed from the catalogue row |
| `FLOOR-anon-roles-policy` | no anonymous writes: the operator cannot offer, default to or pin a write role, at deployment or per tenant | green | red: project floor removed from the catalogue row |
| `FLOOR-write-validation` | data safety: WRITE_VALIDATION below 'log' is refused as an owner value (policy open), an operator default and an operator pin | green | red: project floor removed |
| `FLOOR-not-offered` | names the floors withdraw under multi cannot appear in any policy or owner row: API_SECRET, API_SECRET_FILE, TREATMENTS_AUTH, IMPORT_CONFIG, TRUST_PROXY, BASE_URL, DEBUG_LOGGING, API3_SECURITY_ENABLE, API3_SETTINGS_STRICT_READ_ENABLED, DBSIZE_MAX, CONNECT_SOURCE_ENDPOINT, WEBHOOK_HOST | green | red: TREATMENTS_AUTH added to the catalogue |
| `FLOOR-catalogue-no-secret-names` | no deployment secrets, no secrets as settings: even the migration role cannot put a credential-like name in the catalogue | green | red: name CHECK dropped |
| `FLOOR-catalogue-readonly` | no application role can edit the catalogue (and so cannot loosen a floor) | green | red: UPDATE granted to the operator |
| `FLOOR-autoprune-confirmation` | data safety: turning on permanent deletion needs a recorded confirmation and export offer | green | red: needs_confirmation cleared |
| `FLOOR-alarms-hidden` | alarm settings hidden until the 7a gate: the owner listener cannot write thresholds or alarm keys, and no alarm key can be made owner-settable | green | red: post-gate GRANT applied<br>red: alarms-hidden CHECK dropped |
| `FLOOR-webhook-public` | network safety: a webhook url must be https, carry no credentials, and not name a private, loopback, link-local or local-only host | green | red: public-host check replaced by `true` |
| `FLOOR-connector-driver-hosts` | network safety: a connector endpoint may only name a host its driver defines | green | red: kind's endpoint rule changed from driver to public |
| `FLOOR-deployment-scope` | a deployment value (API_V3_DATA_WARNINGS) cannot be overridden per tenant or set by an owner, and must be pinned | green | red: catalogue row re-scoped to tenant and owner-settable |
| `FLOOR-app-process` | process start under multi refuses API_SECRET(_FILE), API3_SECURITY_ENABLE=false, an empty or non-numeric TRUST_PROXY and DEBUG_LOGGING; IMPORT_CONFIG is ignored with a warning | green | red: secret check off<br>red: API3 security check off<br>red: TRUST_PROXY check off<br>red: DEBUG_LOGGING check off |
| `FLOOR-app-settings-private` | app settings stay private: under multi, reading a settings record by identifier needs api:settings:admin even when API3_SETTINGS_STRICT_READ_ENABLED=false | green | red: multi honours the env value |
| `POLICY-pinned` | an owner value for a setting the operator has pinned is refused | green | red: owner-value trigger dropped |
| `POLICY-bounded` | values outside a bounded list or range are refused; inside are accepted | green | red: owner-value trigger dropped |
| `POLICY-per-tenant-override` | B's override narrows AUTH_DEFAULT_ROLES to denied: readable is refused for B and accepted for A | green | red: owner-value trigger dropped |
| `POLICY-type-and-ownership` | wrongly typed values and operator-only keys are refused | green | red: owner-value trigger dropped |
| `POLICY-planes` | the owner listener cannot write policy; the operator plane cannot write owner values | green | red: owner listener granted policy writes |
| `POLICY-webhook-allowlist` | the operator's optional webhook host allow-list (census row 4) refuses other public hosts | green | red: policy lookup made blind to INTEGRATION_HOSTS keys |
| `VERSION-numbered` | each change is a numbered version with plane, subject, time, kind and the full state after it | green | red: state snapshot broken: cfg_current_state returns an empty state |
| `VERSION-unversioned-write-refused` | a write that skips cfg_apply cannot commit (update, insert or delete; values and integrations) | green | red: commit-time version guards dropped |
| `VERSION-append-only` | versions cannot be edited or deleted, even by the owning migration role | green | red: append-only trigger dropped |
| `VERSION-rollback-restores` | rollback to v1 writes a new version (kind rollback, rollback_of 1) whose state, and the live state, equal v1: values, thresholds and integrations | green | red: rollback restores values only |
| `VERSION-rollback-vs-new-pin` | rollback to a version whose value the operator has since pinned is refused whole, naming the setting; nothing changes and no version is written | green | red: owner-value trigger dropped |
| `VERSION-rollback-needs-fresh-confirmation` | rolling back to a version that had permanent deletion on needs a fresh confirmation; the old one is not carried forward | green | red: needs_confirmation cleared |
| `VERSION-concurrent-writers` | two owner sessions saving at once get consecutive versions; neither fails | green | red: advisory lock removed from cfg_apply |
| `SECRETS-schema-scan` | information_schema: no column named like a credential (except *_ref / *_parts), no bytea column, and every *_ref column is CHECKed by cfg_is_secret_ref | green | red: a plaintext password column added<br>red: a bytea material column added<br>red: an unconstrained *_ref column added |
| `SECRETS-not-in-settings` | integration settings cannot carry a credential: unknown fields are refused and no kind's schema may declare a credential-like field | green | red: kind CHECK dropped and a password field added to the webhook schema |
| `SECRETS-reference-format` | a reference column refuses a value that is not a reference (a pasted plaintext credential) | green | red: reference CHECKs dropped |
| `SECRETS-owner-cannot-see-operator-part` | the owner listener can see that the operator's part exists, not its reference | green | red: whole-table SELECT granted to the owner listener |
| `MMOL-stored-safely` | A.3: a partial mmol override, a full mmol set, an integer mmol-looking set and a misordered set are all refused; a valid mg/dL set is stored exactly | green | red: the OLD shape: tenant_settings as drafted in config-surface §A.2<br>red: new shape with the range CHECK dropped and the columns made nullable |
| `MMOL-old-shape-profile` | the §A.2 draft, measured: its CHECK is live (a complete mmol set is refused) yet a partial mmol override passes on SQL NULL; each input's outcome is recorded | green | red: the same inputs against the new shape |
| `MMOL-converted-and-echoed` | the write boundary converts mmol/L to mg/dL and the stored numbers come back for the owner to see (A.3 defence 2): 3.1/4.5/10/14 -> 56/81/180/252 | green | red: conversion skipped at the write boundary |
| `INTEGRATION-kind-limits` | kinds the operator disabled are refused, and the per-tenant count is held | green | red: integration trigger dropped |
| `INTEGRATION-settings-schema` | settings are validated against the kind's schema: required, unknown, enum, type, length | green | red: integration trigger dropped |
| `INTEGRATION-credential-parts` | an owner part needs a reference; a kind with an operator part needs the operator's part configured first; a record's kind is fixed | green | red: integration trigger dropped |
| `MIGRATE-up-down-up` | umzug applies 0001-0007, rolls all of them back to an empty schema, and applies them again | green | red: 0005's down migration forgets one function |
| `MIGRATE-crash-mid` | a migrate process killed while a migration runs: once the server finishes with the orphaned session, the migration is either applied and recorded or neither; a re-run completes | green | red: umzug's default split: migration and ledger row in separate steps |
| `MIGRATE-crash-after` | a migrate process killed just after a migration returns (before the next starts) leaves the ledger matching the schema; a re-run completes | green | red: umzug's default split: migration and ledger row in separate steps |
| `MIGRATE-concurrent` | four migrate processes started at once on an empty database: all succeed and each migration is applied once | green | red: advisory lock off |
| `MIGRATE-drift` | a migration file edited after it was applied stops the next run | green | red: drift check off |
| `MIGRATE-serve-refuses-stale-schema` | a hosted role at start refuses a schema with pending migrations instead of migrating it | green | red: schema fully migrated (the check must not be constant) |

### Observations worth reading in `results.json`

- **The §A.2 draft, measured** (`MMOL-old-shape-profile`). On the old shape:
  - the partial override `{"bgHigh": 14}` is **accepted**;
  - the complete mmol set, the integer mmol-looking set, the misordered set and a string
    threshold are refused with `23514`.

  So the old CHECK is live, and only the NULL path lets the partial override through. The
  document's second hole, a cast error instead of a clean refusal, was read-derived. It did not
  reproduce on this input: the string threshold gave `23514`, not `22P02`. That does not rule
  the hole out, because the evaluation order is still not guaranteed. [M]
- **The new shape** (`MMOL-stored-safely`) refuses all five bad inputs, each with a message
  naming the reason, and stores `56/81/180/252` exactly. [M]
- **umzug's default split loses a migration, even when the kill comes mid-migration**
  (`MIGRATE-crash-mid`, control).
  - With one implicit transaction per file and the ledger row written afterwards, a runner
    killed during migration 0004 left 0004 **committed**, because the server finished the
    statement after the client was gone. The ledger row was never written.
  - The orphaned server session ran for about 5.4 s after the kill.
  - In the lab's runner, which sends `COMMIT` and the ledger row in the same transaction, the
    same kill leaves nothing applied, and a re-run completes. [M]
- **Concurrent starters**: four `migrate up` processes started together on an empty database.
  - With the advisory lock, one applied all seven migrations and three found nothing pending.
  - Without the lock, 3 of 4 failed with `duplicate key value violates unique constraint
    "pg_type_typname_nsp_index"`. [M]
- **The commit-time version guard is only as good as `cfg_current_state`** (`VERSION-numbered`,
  control). If the state function is broken, every write still commits, because the guard
  compares the state with itself. The test catches this. The guard does not. [M]

## Compatibility with the seam

- `tenants` and `tenant_members` are untouched. [M] (`0001` is byte-identical to `81a1f6ce`.)
- New tables add `tenant_id` foreign keys to `tenants` with `ON DELETE CASCADE`.
- The seam's `ensureSchema` (`81a1f6ce:lib/admin/platform-store.js:120-158`) creates the
  platform tables only when none of them exist. It cannot add these tables to an existing
  database, which is the migration-tooling plan's subject. [R]
- `tenantScopedTables()` (`platform-store.js:186-197`) would discover every new table that has
  a `tenant_id` column. Those tables would enter the export and the deletion gate unless they
  are added to `NOT_TENANT_DATA`. This is an open question in the spec. [R]

## Files

| path | what |
|---|---|
| `migrations/0001-0007.{up,down}.sql` | the schema |
| `bootstrap/roles.sql` | the four roles (run once by a database administrator) |
| `old-shape/a2-tenant-settings.sql` | config-surface §A.2's `tenant_settings`, extracted verbatim, for the A.3 measurement |
| `lib/merge.js` | D22's merge, process-level floors, the threshold write boundary |
| `lib/migrator.js`, `lib/run-migrate.js` | the umzug runner and a child-process wrapper for crash and concurrency tests |
| `lib/db.js` | connections; the container assertion |
| `harness.js`, `results.json` | tests and the last full run |

The container `cfgschema-pg` is left running after a run so that results can be re-checked.
Stop it by name: `docker rm -f cfgschema-pg`.
