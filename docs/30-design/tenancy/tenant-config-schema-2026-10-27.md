# Tenant configuration schema for hosted Nightscout (T30-SCHEMA-CONFIG)

*Contributor-facing. Draft of 2026-10-27, for the maintainer's review. Queue item
`T30-SCHEMA-CONFIG`. It builds on D22 ([execution plan
§2.13](nightscout-multitenancy-execution-plan-2026-09-14.md)), the [census re-measured on
dev](../../60-research/tenancy/t30-census-dev-2026-10-27.md) (§3a), and the [configuration-surface
document](tenant-owner-config-surface-2026-09-15.md) (§A, §A.3, §B.3, §C, §E, §F.1). The schema
runs in [`tools/lab/tenant-config-schema/`](../../../tools/lab/tenant-config-schema/README.md),
which holds 59 tests and 77 controls. Nothing here decides a question those documents leave
open: such questions are listed in §11.*

*Revised the same day after three maintainer answers: class D values live in each role's
environment; `tenant_members` names a person by provider and subject; and rollback against a
changed policy is refused whole (Q3, now decided). The first round's migrations `0002` to
`0007` are now `0003` to `0008`.*

Marks: **[M]** means measured by the lab, in the run recorded in its `results.json` (PostgreSQL
16.15). **[R]** means read or reasoned, not measured. Test ids (`ISO-…`, `FLOOR-…`) name the
lab's tests.

## 1. What this is

Under `TENANCY_MODE=multi`, a tenant's configuration decides what a person's site shows, who
may read it, what it connects to and, once multi-mode alarms pass the gate in §7a, when an
alarm fires. D22 gives that configuration three layers:

1. project floors, which are fixed in code;
2. the operator's policy, written on the operator plane;
3. the owner's values, written on the tenant-owner listener.

D22 also says that integrations are typed records, that credentials live in a separate
secrets component, and that every change is versioned and can be rolled back.

This document gives those decisions a PostgreSQL schema. It has three design goals:

- a wrong value fails loudly at the moment it is written, and is never stored and then
  silently rewritten;
- a forgotten tenant filter returns nothing (D3);
- no table holds secret material.

## 2. The tables, and why each exists

Two tables already exist on the seam branch (`81a1f6ce:lib/admin/platform.sql`):

- `tenants` has no RLS, because it is read before a tenant context exists. This schema leaves
  it unchanged.
- `tenant_members` has RLS. Migration `0002` changes it as the maintainer decided on
  2026-10-27: a person is identified by **identity provider and subject, both text, unique
  together**, with no foreign key to any identity table of Nightscout's, so a Kratos, Clerk or
  any OIDC subject fits (D17 as amended).
  - The lab makes the pair unique **within a tenant**, as `(tenant_id, provider, subject_id)`,
    so that one person can be a member of two tenants.
  - The column keeps the seam's name, `subject_id`, so seam code still reads it.
  - `0002` refuses to run while the table holds rows, because nothing records which provider
    issued them.

  `MEMBER-identity` and `MEMBER-migration-refuses-rows` cover this, with three controls. [M]

The lab's migration `0001` is that file byte for byte. [M]

| table | tenant-scoped | written by | why it exists |
|---|---|---|---|
| `config_setting` | no | migrations only | The catalogue of setting names hosted configuration may carry. It records each setting's type, whether the owner may set it, whether it is an alarm setting, whether it needs a deletion confirmation, and its **project floor**. A name missing from here cannot appear in any policy or owner row, because foreign keys forbid it. That absence is how the "not offered" floors reach the database. |
| `integration_kind` | no | migrations only | The driver catalogue. For each kind: the schema its settings must satisfy, the hosts a driver may call, and the *names* of the credential parts the owner and the operator each supply. |
| `deployment_policy` | no | operator | D22's one deployment policy of **tenant-facing** settings: per setting, a default, a mode (`open`, `bounded` or `pinned`), a constraint and a pin. Deployment-level (class D) values are not here: they are environment variables of the role that reads them (maintainer, 2026-10-27). |
| `tenant_policy_override` | yes | operator, with the tenant bound | D22's operator overrides for individual tenants. A row replaces the deployment row for that tenant and setting. |
| `tenant_setting_value` | yes | tenant-owner listener | The owner's values, accepted only within the governing policy row and the floor. |
| `tenant_alarm_thresholds` | yes | nobody yet (see §5) | The owner's four glucose thresholds, as typed `NOT NULL` integer columns in mg/dL. It exists so the §A.3 hazard cannot be expressed. See §6. |
| `tenant_config_version` | yes | tenant-owner listener (insert only) | One numbered, append-only row per change. It records the plane, the identity provider (required for an owner) and its subject, the time, the kind (`change`, `rollback`, `bootstrap`, `import`) and the full owner-scope state after the change. |
| `deployment_integration` | no | operator | The operator's part of a kind's credential (for example a push service's application token), held as a **reference**. |
| `tenant_integration` | yes | tenant-owner listener | One record per connector, webhook or push target. Each has a kind, settings validated by the kind's schema, a reference to the owner's credential, and an `enabled` flag. |
| `tenant_integration_status` | yes | consumer and connector roles | The last success and last error. They are kept apart so that a connector's polling never creates a configuration version. |

Three functions carry the write path. All are `SECURITY INVOKER`, so RLS and table grants apply
to everything they do:

- `cfg_apply(tenant, changes, plane, subject, …)` is the single write path for owner-scope
  state.
- `cfg_rollback(tenant, version, …)` restores an earlier version.
- `cfg_policy_for(tenant, key)` returns the governing policy row: the override, else the
  deployment row, else the catalogue default.

### 2.1 Roles

The lab's roles are `cfg_owner`, `ns_operator`, `ns_tenant_admin` and `ns_api`.

- `cfg_owner` runs the migrations and owns every table. It is `NOSUPERUSER NOBYPASSRLS`.
- The other three own nothing. They map to D7's operator plane, D16's tenant-owner listener,
  and D5/D21's consumer, evaluator and connector roles.

The grants are in `0008_grants.up.sql`.

**Measured, and in tension with a claim in the seam's code (§10, M7):** the tables are owned by
a role that is not the application role. RLS is still active for every application role, with
`row_security_active()` true on all seven tenant tables (`ISO-roles`, `ISO-<table>`). [M]

## 3. The merge rule, and where it runs

**Rule (D22).** For each setting, the effective value is:

1. the **code default**;
2. replaced by the **operator default**, if the governing row has one;
3. replaced by the **owner value**, if:
   - the catalogue marks the setting owner-settable,
   - the value is well typed,
   - it satisfies the floor,
   - the mode is not `pinned`,
   - and, where the mode is `bounded`, the constraint accepts it;
4. replaced by the **operator pin**, if the mode is `pinned`.

An owner value that fails step 3 is not used, and it is **reported** in
`ignoredOwnerValues` with the reason (`MERGE-override-narrows`, `MERGE-pin-beats-owner`). [M]

A floor is checked once more on the effective value. For example, with no operator row,
`WRITE_VALIDATION` falls back to the code default `off`, which breaks the floor. The merge
reports this so that the process refuses to serve (`MERGE-floor-on-effective`). [M]

The thresholds are merged as a set:

- the owner's row if one exists;
- otherwise the effective `BG_*` values, key by key.

A set that is out of order is reported. It is **never nudged**, unlike dev's `verifyThresholds`
(`lib/settings.js:311-334` on `db3b9e4e`, BF-67) (`MERGE-thresholds-refused-not-rewritten`). [M]

**Where it runs.** The merge runs in **application code** (`lib/merge.js` in the lab). The
**write-time** checks run in the **database**, as triggers. There are four reasons. [R]

1. The code defaults live in the code (`lib/settings.js`, `lib/server/env.js`). A merge in
   SQL would need them passed in, or copied into the database, and a second copy can drift.
2. The process environment is visible only to code. D22 says floors are "enforced in code
   under `multi`", and several of them are process-level (§4).
3. D22's "saving invalidates the tenant's cached settings" implies that the merged result is
   cached in the process. The merge is computed on a cache miss, and the result is what the
   evaluator and the API use.
4. An operator or owner can write rows through a path other than the intended code. A wrong
   row must not be storable at all, so acceptance (type, floor, mode, constraint) is checked
   by triggers on every write.

Two spellings of one rule can drift. The lab therefore runs a differential test: 30 cases go
through the JavaScript acceptance rule and the SQL one, and the test requires agreement. Its
control plants an off-by-one in the JavaScript ordinal minimum, and the test goes red
(`MERGE-differential`). [M] A release should generate both rules from one source, or keep this
differential in CI. [R]

## 4. Project floors: the database or the application

D22 lists five floor groups.

> The execution plan's §2.13 now says five as well. It said "four groups" when this document
> was first drafted (M1, fixed on main in `2222116ea`).

| group | floor | where | test |
|---|---|---|---|
| no deployment secrets | `API_SECRET`, `API_SECRET_FILE` refused at start | **application**: only code sees the environment | `FLOOR-app-process` [M] |
| | neither name can be a setting | **database**: absent from `config_setting`, so a foreign key refuses any row naming them | `FLOOR-not-offered` [M] |
| | no credential-like name can enter the catalogue, even through a migration | **database**: `config_setting_no_secret_names` CHECK | `FLOOR-catalogue-no-secret-names` [M] |
| | `API3_SECURITY_ENABLE=false` refused at start | **application** | `FLOOR-app-process` [M] |
| no anonymous writes | default roles only from `denied`, `readable` and `status-only` | **database**: the catalogue floor checks owner values even when the policy is `open`, and checks operator defaults, pins and allowed lists | `FLOOR-anon-roles-owner`, `FLOOR-anon-roles-policy` [M] |
| | `TREATMENTS_AUTH` not offered | **database**: absent from the catalogue | `FLOOR-not-offered` [M] |
| network safety | `TRUST_PROXY` a hop count or CIDR, never empty | **application**: a listener property of the process (census row 5: never a tenant row) | `FLOOR-app-process` [M] |
| | webhooks to public addresses only | **both**. The database refuses non-https URLs, URLs with user-info, literal private, loopback, link-local, shared or multicast IPs, and local-only names. The **application** must check the resolved address at send time, which the database cannot see (DNS) | `FLOOR-webhook-public` [M]; send-time check [R], not built |
| | connector endpoints only on driver-defined hosts | **database**: a URL field marked `hosts: driver` accepts only the kind's `driver_hosts` | `FLOOR-connector-driver-hosts` [M] |
| | `BASE_URL` derived from the slug | **database**: absent from the catalogue. The derivation itself is application code (D10). | `FLOOR-not-offered` [M] |
| app settings stay private | reading an app's settings record by identifier needs `api:settings:admin` | **application**: a route check, with `API3_SETTINGS_STRICT_READ_ENABLED` absent from the catalogue | `FLOOR-app-settings-private`, `FLOOR-not-offered` [M] |
| data and log safety | `WRITE_VALIDATION` at least `log` | **database** (owner values, operator defaults, pins) **and application** (on the effective value, when no operator row exists) | `FLOOR-write-validation`, `MERGE-floor-on-effective` [M] |
| | `DEBUG_LOGGING` off | **application**: process-level; absent from the catalogue | `FLOOR-app-process`, `FLOOR-not-offered` [M] |
| | `IMPORT_CONFIG` ignored, with a warning | **application** | `FLOOR-app-process` [M] |
| | permanent autoprune needs an explicit confirmation, with an export offered first | **both**. The **database** refuses an `API3_AUTOPRUNE_*` value without `confirmed_at` and `export_offered_at`. The **application** must actually offer the export; the database can only see that one was recorded. | `FLOOR-autoprune-confirmation` [M] |
| *(D22, alarm decision)* | alarm settings hidden until §7a's gate | **database**: the owner listener has no write grant on `tenant_alarm_thresholds`, alarm keys are not owner-settable, and a CHECK forbids making them so | `FLOOR-alarms-hidden` [M] |

The rule behind the split [R]:

- A floor goes in the **database** when it is a property of a row, so that no tool, script or
  future endpoint can store a row that breaks it. Each such check is in a trigger or CHECK that
  the application roles cannot alter: `FLOOR-catalogue-readonly` shows the catalogue is
  read-only to all three. [M]
- A floor goes in the **application** when its input is something the database cannot see:
  - the process environment;
  - a DNS answer at send time;
  - whether the person was actually shown an export offer;
  - the merged value when no row exists.

## 5. Census §3a, row by row

| # | settings | how the schema expresses it | evidence |
|---|---|---|---|
| 1 | `AUTH_DEFAULT_ROLES`, `TREATMENTS_AUTH` | `AUTH_DEFAULT_ROLES` is a `role_list` with floor `{"allowed": ["denied","readable","status-only"]}`. The catalogue ships it `bounded` within the floor. The operator may narrow it per deployment or per tenant. `TREATMENTS_AUTH` is absent. | `FLOOR-anon-roles-*`, `POLICY-bounded`, `POLICY-per-tenant-override` [M] |
| 2 | `API_SECRET`, `API_SECRET_FILE` | absent from the catalogue; refused at start | `FLOOR-not-offered`, `FLOOR-app-process` [M] |
| 3 | `IMPORT_CONFIG` | absent; warned and ignored at start | same [M] |
| 4 | outbound endpoints | Not scalar settings. They become `tenant_integration` records of kind `webhook` or `cgm-connector` (driver hosts only). The operator's switches are policy rows: `INTEGRATION_MAX:<kind>` (0 disables a kind; otherwise the per-tenant count) and the optional webhook allow-list `INTEGRATION_HOSTS:webhook`. `BASE_URL` is absent. | `FLOOR-webhook-public`, `FLOOR-connector-driver-hosts`, `INTEGRATION-kind-limits`, `POLICY-webhook-allowlist` [M] |
| 5 | `TRUST_PROXY` | absent from the catalogue; refused at start unless it is a hop count or CIDR | `FLOOR-app-process` [M] |
| 6 | `WRITE_VALIDATION` | an `ordinal` (`off` < `log` < `reject`) with floor `{"min": "log"}`. The catalogue ships `bounded {"min": "log"}`; an operator may raise the minimum, and the owner may tighten above it. | `FLOOR-write-validation`, `MERGE-floor-on-effective` [M] |
| 7 | `API3_SETTINGS_STRICT_READ_ENABLED` | absent; always on under multi, in code | `FLOOR-app-settings-private` [M] |
| 8 | `API3_SECURITY_ENABLE` | absent; refused at start if false | `FLOOR-app-process` [M] |
| 9 | `API3_AUTOPRUNE_*` (six names, `lib/server/env.js:286-293`) | Integers in days, floor `{"min": 1}`, `needs_confirmation`. The catalogue ships them `pinned` with no pin, so they are **off** until the operator writes a policy. The operator's minimum retention is the `bounded` constraint's `min`. Turning one on needs a fresh confirmation, also on rollback. | `FLOOR-autoprune-confirmation`, `POLICY-bounded`, `VERSION-rollback-needs-fresh-confirmation` [M] |
| 10 | alarm thresholds and enables | **Hidden** (see §4). `BG_HIGH`, `BG_TARGET_TOP`, `BG_TARGET_BOTTOM` and `BG_LOW` are operator-only integers in mg/dL, with floor `{"min": 20, "max": 600}`. `ALARM_URGENT_HIGH`, `ALARM_HIGH`, `ALARM_LOW` and `ALARM_URGENT_LOW` are operator-only booleans. The owner's own thresholds go in `tenant_alarm_thresholds` (§6) once the gate passes. | `FLOOR-alarms-hidden`, `MMOL-*` [M] |
| 11 | plugin credentials | Never in a settings row. Each kind names its credential **parts**. The owner's parts are referenced from `tenant_integration.owner_secret_ref`, and the operator's from `deployment_integration.operator_secret_ref`. The owner listener can see *that* the operator's part exists, not its reference. | `SECRETS-*`, `INTEGRATION-credential-parts` [M] |
| 12 | `DEBUG_LOGGING`, `DBSIZE_*` | absent; `DEBUG_LOGGING` refused at start | `FLOOR-not-offered`, `FLOOR-app-process` [M] |

**Class D values (decided 2026-10-27).** Deployment-level values live in each role's
**environment**. This covers `TRUST_PROXY`, `DEBUG_LOGGING`, ports, storage URIs and the
release-driven compatibility switches. None is in the catalogue, so the database refuses each
of them as a deployment policy row or a per-tenant override. The lab's
`deploymentValues(env)` reads them from the role's own environment, so two roles can differ.
`CLASSD-environment` covers both halves. Its two controls add `API_V3_DATA_WARNINGS` to the
catalogue, and make the roles ignore their environment. [M]

**The eight names new on dev:**

- `API_V3_DATA_WARNINGS`, `API_V1_COUNT_LEADING_NUMBER` and `API_V1_COUNT_ZERO_WINDOW` are
  class D: environment variables of the role that reads them (`CLASSD-environment`). [M]
- `SHOW_SECONDS` is open to the owner. [M]
- The two `CUSTOMCONNSTR_*` spellings are absent. [R]

The lab's catalogue (`0004`) covers these rows plus `SHOW_SECONDS` and `DISPLAY_UNITS`. It does
not cover the remaining class-T names. A release would generate the catalogue from the census
(J7). [R]

## 6. Alarm thresholds and the §A.3 hazard

§A.2 drafted the thresholds as keys inside a JSON settings object, guarded by one CHECK. §A.3
predicted, from PostgreSQL's documentation, that a partial mmol override would pass that CHECK
on SQL NULL. The lab applied §A.2's `tenant_settings` verbatim (`old-shape/`) and measured it
(`MMOL-old-shape-profile`). [M]

| input | §A.2 draft | this schema |
|---|---|---|
| partial `{"bgHigh": 14}` | **accepted** | refused: all four are written together (and the columns are `NOT NULL`) |
| complete mmol `{3.1, 4.5, 10, 14}` | refused (`23514`) | refused: not a whole mg/dL value; convert mmol/L at the write boundary |
| integer mmol-looking `{3, 5, 10, 14}` | refused | refused: `tenant_alarm_thresholds_plausible_mgdl` |
| misordered `{80, 55, 180, 260}` | refused | refused: `tenant_alarm_thresholds_ordered`. It is not rewritten (contrast BF-67). |
| string `{"x", 80, 180, 260}` | refused, `23514` (the read-derived cast error did not reproduce on this input) | refused: must be a number |
| valid `{56, 81, 180, 252}` | accepted | accepted, stored exactly |

The draft's CHECK works when all four keys are present. It fails only on the NULL path. In
this schema the NULL path does not exist, because each threshold is its own `NOT NULL`
column. `MMOL-stored-safely` is green on the new shape. It goes red on the old shape, and red
again when the new shape's range CHECK is dropped and the columns are made nullable. [M]

The **write boundary** is the application's. It converts mmol/L with dev's factor 18.01559
(`lib/constants.json:10`), stores mg/dL, keeps `entered_units`, and echoes the stored numbers
back (§A.3 defence 2). The lab's `thresholdsForStorage` turns 3.1/4.5/10/14 mmol/L into
56/81/180/252. Its control skips the conversion, and the database then refuses the write
(`MMOL-converted-and-echoed`). [M]

Refusing partial input follows J11's recommendation, and **J11 is still open**. A
nullable-per-column variant would also refuse a lone mmol `bgHigh` on range. Its ordering
could then only be checked after the merge, in code. [R]

## 7. Versions and rollback

**Recording.** `cfg_apply` takes a per-tenant transaction advisory lock, applies the changes,
and appends version *N+1* with the state after the change.

- Two owner sessions saving at once get consecutive versions. Without the lock, the second
  fails with a duplicate version (`VERSION-concurrent-writers`). [M]
- A deferred constraint trigger requires, at commit, that the tenant's live owner-scope state
  equals its newest version's state. A direct `UPDATE`, `INSERT` or `DELETE` that skips
  `cfg_apply` cannot commit (`VERSION-unversioned-write-refused`). [M]
- **Limit:** this guard compares the live state with the version through the same
  `cfg_current_state` function. If that function were wrong, the guard would not notice; the
  test did (`VERSION-numbered`, control). [M]
- Versions are append-only:
  - the owner listener has no `UPDATE` or `DELETE` grant;
  - a trigger refuses both, even to the owning migration role (`VERSION-append-only`);
  - the one exception is the cascade from deleting the tenant. [M]

**Rollback.** `cfg_rollback(tenant, N)` computes the changes that make the live state equal
version *N*. It applies them through `cfg_apply` as a new version, with kind `rollback` and
`rollback_of N`. Values, thresholds and integrations are all restored
(`VERSION-rollback-restores`). [M]

**Rollback against a policy that has changed since version *N*.** Every restored row passes
the same checks as a fresh write, against the **current** policy and floors.

- **Decided (maintainer, 2026-10-27; Q3).** An owner's rollback to an earlier version is
  **refused whole** when the operator has since pinned or narrowed a setting that version
  used. The error names **each** blocked setting and the operator rule behind it. Nothing
  changes, and no version is written.
  - `cfg_rollback` pre-checks every value it would restore with the same function the write
    trigger uses (`cfg_owner_value_error`), and raises one error listing all of them.
  - Measured message, with one deployment pin and one per-tenant narrowing:
    `rollback to version 1 refused; 2 setting(s) blocked: policy: AUTH_DEFAULT_ROLES =
    ["readable"] is outside the operator's constraint (override rule: bounded {"allowed":
    ["denied"]}); policy: SHOW_SECONDS is pinned by the operator (deployment rule: pinned to
    false)`.
  - The test is `VERSION-rollback-vs-new-policy`. Its two controls remove the checks, and
    report only the first blocked setting. [M]
  - The first round's lab stopped at the first blocked setting. That did not meet the
    decision, and is fixed.
  - Integration records restored by a rollback are still checked one at a time by their
    trigger, so a blocked integration is reported alone (Q13). [R]
- A rollback to a version with permanent deletion turned on needs a **fresh** confirmation.
  The old confirmation is not part of the version state and is not carried forward
  (`VERSION-rollback-needs-fresh-confirmation`). [M]


**What is versioned.** Owner-scope state is versioned: owner values, thresholds and
integration records. Integration status is not. Operator policy changes are not versioned
here, so whether they need history is open (Q5). Saving a new version should invalidate the
tenant's cached merge; how the hosted processes learn of that (D6's feed, or a version-number
check) is not built here. [R]

## 8. Integrations and secret references

`tenant_integration` has these guarantees:

- Settings are validated against the kind's schema: required fields, no unknown fields, enums,
  types, lengths and host rules (`INTEGRATION-settings-schema`). [M]
- The operator controls which kinds are enabled and how many each tenant may have
  (`INTEGRATION-kind-limits`). [M]
- A kind's owner credential parts require a reference. A kind with an operator part is
  refused until the operator has configured that part (`INTEGRATION-credential-parts`). [M]

**No plaintext secret column anywhere** (`SECRETS-schema-scan`). [M] The test scans
`information_schema` and requires:

- no column named like a credential, except `*_ref` and `*_parts`;
- no `bytea` column;
- that every `*_ref` column is guarded by the reference-format CHECK.

Three controls each add an offending column, and the test goes red each time. Two more checks
close the gaps around the scan:

- Settings cannot smuggle a credential. An unknown field such as `password` is refused, and
  no kind's schema may declare a credential-like field (`SECRETS-not-in-settings`). [M]
- A pasted plaintext value in a reference column is refused by the format check
  (`SECRETS-reference-format`). [M]

The reference format `sref:v1:<backend>:<opaque id>` is a lab placeholder. The format CHECK
catches accidents only: a plaintext value shaped like a reference would pass it. Whether a
reference belongs to the tenant can only be checked by the secrets component, which holds the
keys (D22: keys never leave it). [R]

## 9. RLS on every tenant-scoped table

Every tenant-scoped table has RLS enabled and forced, with the seam's predicate copied
character for character:
`tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid`, in both
`USING` and `WITH CHECK`.

`ISO-complete` discovers tables by their `tenant_id` column, as the seam's
`tenantScopedTables` does, and requires all three properties. Its control adds an unprotected
table, and the test goes red. [M]

For each of the seven tables, the role bound to tenant A:

- reads only A's rows;
- reads nothing when unbound;
- updates none of B's rows;
- is refused (`42501`) when inserting a row for B.

| table | reader in the test | cross-tenant insert attempted by |
|---|---|---|
| `tenant_members` | `ns_api` | `ns_tenant_admin` |
| `tenant_policy_override` | `ns_api` | `ns_operator` |
| `tenant_setting_value` | `ns_api` | `ns_tenant_admin` |
| `tenant_alarm_thresholds` | `ns_api` | `ns_tenant_admin` (with the post-gate grant) |
| `tenant_config_version` | `ns_api` | `ns_tenant_admin` |
| `tenant_integration` | `ns_api` | `ns_tenant_admin` |
| `tenant_integration_status` | `ns_api` | `ns_api` |

Each table has two controls, RLS disabled and the same reads done as the container superuser.
All 14 go red. [M]

The operator writes per-tenant overrides with the tenant bound, which is J12's option 1 shape
applied to a new table. **J12 is still open.** [R]

## 10. `single` mode

Nothing changes. `single` reads the process environment, as today (D15, D1). It does not
create or read these tables, does not run these migrations, and does not apply the floors
above. The floors are `multi`-only (D22). The environment names keep their meaning, including
`CONNECT_*`, `BRIDGE_*`, `WEBHOOK_*` and `PUSHOVER_*` as aliases (D22). The lab's
`settingsReadByIdPermission` keeps dev's behaviour for `single`, and `FLOOR-app-settings-private`
checks it. [M]

## 10a. Comparison with Nocturne

Nocturne at `42275c812` was read for comparison. [R]

- Generic settings are rows keyed by tenant and key, with a value (`SettingsEntity`).
- Thresholds are alert rules with JSON parameters (`AlertRuleEntity.condition_params`).
- `TenantAlertSettingsEntity` holds a do-not-disturb schedule, not thresholds.
- Connector configuration keeps its secret properties encrypted in a `secrets` JSON column on
  the same row (`ConnectorConfigurationEntity.SecretsJson`, AES-256-GCM per its comment).
- Migrations are EF Core migrations, run at start under a dedicated migrator role, separate
  from the application role (`DatabaseInitializationExtensions.cs:80-113`).

The two designs agree in several places:

- a generic key/value layer;
- typed side-tables where constraints matter;
- a migrator role separate from the application role.

They differ in one place. D22 moves secret material into a separate component, so this schema
holds references only, where Nocturne keeps ciphertext beside the configuration it belongs to.
That difference follows from D22's keys-stay decision. It is not a judgement on Nocturne's
choice. [R]

## 10b. Mismatches found (stop-and-report)

These are inconsistencies between decisions, documents and code. None was resolved by this
work. M1, M2, M4 and M5 were settled on 2026-10-27, as each entry says.

- **M1.** *(Fixed on main in `2222116ea`.)* The execution plan's §2.13 listed five floor
  groups but introduced them as "Decided as four groups". [R]
- **M2.** *(Settled 2026-10-27: provider and subject, both text, unique together, no foreign
  key. Migration `0002`.)* D17 as amended makes the identity provider interchangeable and
  `tenant_members.subject_id` the provider's subject, with no foreign key. Two places do not
  fit that:
  - On the seam (`81a1f6ce`), the column is `uuid NOT NULL`. A provider whose subjects are not
    UUIDs cannot be stored.
  - On `seam/t30-schema-cred` (`65ce54b9`), the column became `text` **with** a composite
    foreign key to `tenant_subject`, against "no foreign key".

  The first round left `tenant_members` unchanged. [R]
- **M3.** `tenant_secret` stores `material bytea` in the platform schema. It is drafted in
  config-surface §A.2 and §C.5 (J4) and built on `65ce54b9`. D22's later decisions say keys
  never leave the secrets component. They do not say where the built-in signer keeps its
  encrypted keys. This schema holds references only, and `SECRETS-schema-scan` forbids `bytea`
  in it. If the built-in signer's store is to live in the same schema, that check needs a
  defined scope. [R]
- **M4.** *(Settled 2026-10-27: class D values live in the environment, so neither is a
  policy row.)* Census §3a row 5 says `TRUST_PROXY` is "never a tenant row", and row 12 gives
  `DEBUG_LOGGING` no policy. The call-path lab's `lib/policy.js` models both as per-tenant
  pinned policy rows. That lab is evidence for the call path, not for the setting model, but
  the two disagree. [R]
- **M5.** *(Settled 2026-10-27: each role's environment; `deployment_policy` holds only
  tenant-facing defaults, modes and constraints; D15 reads as "no per-tenant configuration from
  the environment". The `scope` column and the deployment-scope row were removed.)*
  Config-surface §B.3 says class D settings are read from `process.env` under `multi`,
  "as today". D22 and census §3a describe release-driven D names as "deployment values the
  operator pins", which is a policy row. D15 says env-sourced configuration must not reach the
  multi path. Where D values live under `multi` is therefore not stated consistently. The
  first round supported pinned deployment rows (`scope = 'deployment'`), and the process-level floors
  read the environment. [R]
- **M6.** Config-surface §A.3 cites `settings.js:290-296` and a `bgHigh < 50` heuristic.
  Dev at `db3b9e4e` converts each threshold on its own when it is below 30
  (`lib/settings.js:292-305`). The silent rewriter BF-67 is still present
  (`lib/settings.js:311-334`). The citations are stale, and the hazard remains. [R]
- **M7.** The seam's comments say the connecting role must own the tables, or "a setup step
  run as a superuser would leave the policy quietly unenforced"
  (`81a1f6ce:lib/storage/postgres-storage.js:290-293`, `lib/storage/ack-store.js:199-203`).
  Measured here: with the tables owned by a separate non-superuser migration role, RLS is
  active for every non-owner application role (`ISO-roles`). `FORCE` matters only for the
  owner. [M] The danger the comment names is real only if the application itself connects as
  a superuser. This bears on who runs migrations ([plan](../../60-research/tenancy/migration-tooling-plan-2026-10-27.md) §4).
- **M8.** The queue item's note says Nocturne's `TenantAlertSettingsEntity` is a typed
  side-table "where constraints matter". At `42275c812` it holds a do-not-disturb schedule;
  Nocturne's thresholds are JSON parameters on alert rules (§10a). [R]

## 11. Open questions for the maintainer

The lab made a working choice for each question below, so that it could run. Rows marked
**decided** were answered by the maintainer on 2026-10-27. For the others, the working choice
is not a decision.

| # | question | lab's working choice |
|---|---|---|
| Q1 | Does an operator override replace the deployment row whole, or field by field? | **decided (2026-10-29):** whole row. A later deployment change does not leak into overridden tenants |
| Q2 | When the operator has written no row, what applies? Is there a project-shipped default policy? | the catalogue's shipped mode and constraint. Autoprune and alarm keys are pinned off, ordinary T settings open, contested rows bounded within the floor |
| Q3 | Rollback against a changed policy: refuse it whole, apply it partly with a report, or restore values the merge then ignores? | **decided:** refused whole, naming each blocked setting and the operator rule behind it (§7) |
| Q4 | When an operator narrows or pins a setting, owners' stored values fall outside it. Who tells the owner, and how? D22's "review list, never dropped silently" covers migration only. | the merge ignores and reports them; nothing tells the owner |
| Q5 | Are operator policy changes, at deployment and per tenant, versioned or audited? How do they invalidate tenants' caches? | **direction (2026-10-29):** audited, by whichever of audit, invalidation and versioning each need calls for, but through one audit approach shared across the code base, not a second incompatible one. An inventory of the existing audit and history mechanisms comes first (see the note under this table); the lab's working shape is AFTER triggers writing append-only audit rows with the operator's identity from `SET LOCAL`, a policy generation number and `pg_notify` |
| Q6 | J11: refuse partial threshold input, or allow it per key with nullable typed columns? | refuse partial (J11's recommendation) |
| Q7 | Threshold bounds: §A.2 uses 20 to 600 mg/dL. Dev now treats values below 30 as mmol/L. Which bounds, after clinical review? | 20 to 600 |
| Q8 | The secret-reference format, and how a reference is bound to its tenant. | placeholder format; binding left to the secrets component |
| Q9 | Where does the built-in signer keep encrypted keys: in this database (separate schema and role) or outside it? (M3) | outside this schema |
| Q10 | `tenant_members.subject_id` type and foreign key under D17 as amended (M2; J1, I.2) | **decided:** provider and subject, both text, unique together, no foreign key (`0002`) |
| Q11 | Under `multi`, do class D values live in the environment or as pinned deployment rows? (M5) | **decided:** each role's environment |
| Q12 | Export and deletion: which configuration tables are "tenant data" for `tenantScopedTables` and `NOT_TENANT_DATA`? Owner values, versions and integrations are the owner's. Overrides are the operator's. | **decided (2026-10-29):** export carries the owner's tables (values, thresholds, versions, integrations with references only, integration status), not operator overrides; deleting the tenant deletes all of them, overrides included |
| Q13 | An integration restored by rollback may reference a secret since deleted or rotated, and an operator may lower a kind's maximum below a tenant's current count. What happens in each case? | neither handled |
| Q14 | May the operator plane read owner values (for support)? | no grant |
| Q15 | The post-gate change for alarm settings, a migration that grants the owner listener writes and drops the hidden CHECK: is a reviewed migration the intended switch? | yes, as a migration |
| Q16 | The send-time webhook check (DNS resolution, pinning the resolved address): where does it live? | not built |
| Q17 | Generate the catalogue from the census gate (J7)? | hand-written `0004` |
| Q18 | Existing `tenant_members` rows have no recorded provider. Should they be backfilled with a stated provider (the seam's rows came from the Kratos proof), or the table emptied? | **decided (2026-10-29), question dissolved:** the table is on no merged branch, so the migrations are rewritten instead of migrated: one `CREATE TABLE` with provider and subject from the start, no row migration. The table is renamed `tenant_access_grants`: one row is one identity the tenant has granted access to, with its permissions (owner, care team, family, followers; uploader apps keep tokens). Single-tenant needs the same contract (see the note under this table) |
| Q19 | Is "unique together" per tenant (one person, several tenants) or global? Should `subject_id` be renamed `subject`? | per tenant; name kept for seam compatibility |
| Q20 | Should a `nightscout serve` role refuse to start when a class D value it needs is missing, as the floors already do for `TRUST_PROXY`? | only the floors refuse |

**Maintainer notes, 2026-10-29.**

- **One access-grant contract, two stores.** Single-tenant Nightscout on MongoDB will need the same
  logic once a login plugin is enabled (D17 as amended: a pluggable identity provider). The plugin would
  link an identity provider's (provider, subject) to an existing authorization subject (`auth_subjects`),
  and today's token mechanics would then issue that subject's roles. `tenant_access_grants` is the
  multitenant store of the same contract. Not yet designed; no plan row yet.
- **One audit approach.** Before Q5 is built, inventory what already records history or attribution:
  this schema's `tenant_config_version`, API v3 history by `srvModified`, the write step's internal commit
  event, the authority spec's §8 (which lists "who took an owner action and when" as not recorded),
  commands CM1, and the agent trust boundaries' append-only audit requirement. Propose one audit record
  shape that both MongoDB and PostgreSQL can hold. Q5 then uses it.

## 12. Evidence

- Lab: `tools/lab/tenant-config-schema/`: `README.md` (how to run, the full results table) and
  `results.json` (each control's error and observation).
- Migration-tool comparison: `tools/lab/tenant-config-schema/compare.js` and `compare-results.json` (umzug, node-pg-migrate and migrate-mongo, on PostgreSQL 16.15 and a standalone MongoDB 8.0.34).
- Migration tooling: [`docs/60-research/tenancy/migration-tooling-plan-2026-10-27.md`](../../60-research/tenancy/migration-tooling-plan-2026-10-27.md).
