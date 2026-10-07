# T3.0: the census gate, and the credential half of the schema

> **Snapshot — evidence as of 2026-10-07.** The census was measured on `crm-seam` `81a1f6ce` and on
> `official/dev` `43289dde`. The schema change is on the local branch `seam/t30-schema-cred`
> (`65ce54b9`), based on `seam/t1-2-storage-interface` `81a1f6ce`. Nothing here is pushed.
> Queue items: `T30-RESEARCH`, `T30-SCHEMA-CRED`. Specification:
> [tenant-owner configuration surface](../../30-design/tenancy/tenant-owner-config-surface-2026-09-15.md).

Two things were done:

1. The §G.3 census script now lives in the queue as a gate:
   [`tools/queue/gates/t30-census-differential.js`](../../../tools/queue/gates/t30-census-differential.js).
2. The device and data-path credential tables were added to `lib/admin/platform.sql`, and
   [`tools/queue/gates/platform-sql-surface.js`](../../../tools/queue/gates/platform-sql-surface.js)
   was tightened. Before the change it could not tell a column from a comment.

Environment: Node 24.20.0, the version the seam's `engines` field (`^22.23.2 || ^24.20.0`)
accepts; the default `node` on this machine is 24.15.0, which it does not. MongoDB 7.0.43 in
container `t30-mongo` on host port 27154, started with `--ulimit nofile=64000`. PostgreSQL 16.15
(`postgres:16-alpine`, `wal_level=logical`) in container `t30-pg` on host port 54354. Both
containers were removed afterwards.

## 1. The census gate

### What it compares

The gate builds two sets of configuration names independently, then compares them name by name.

- **The code side** starts with the four §G.3 sources, using the regexes unchanged, so the
  quoted transcript can be checked: `s1` (by running `lib/settings.js`), `s2` (`lib/server/env.js`),
  `s3prefixes` and `s4` (`README.md`). It adds the places §B.2 says configuration enters that
  those sources cannot see, each found by parsing code:
  - direct `process.env.X` and `process.env['X']` reads anywhere in `lib/` and `bin/`
  - literal arguments to api3's `setENVTruthy`, plus the `'API3_AUTOPRUNE_' + colName` call,
    expanded over api3's `enabledCollections`
  - readers that take an env object defaulting to `process.env` (`lib/admin/*`, `bin/feed.js`)

  Every dynamic `process.env[expr]` site outside `env.js` must belong to a reader whose callers
  are parsed. Otherwise the gate fails.
- **The report side** is parsed from the specification's class lists (§B.4), the gap 5 table
  (§B.2) and §B.6. Abbreviations are expanded. Each `PREFIX_*` (N) group must expand to exactly
  N code-side names. Each class heading's count must equal the number of names in its list.
  No name may appear in two classes.

There are two modes: `--ref <ref>` reads the `cgm-remote-monitor` object database, and
`--root <dir>` reads a working tree or a copy of one. There is no default tree, because the
document names the commit it measured.

### Results at `81a1f6ce`

```
QUEUE_GATE_ROOT=<shared checkout> node tools/queue/gates/t30-census-differential.js --ref 81a1f6ce
node tools/queue/gates/t30-census-differential.js --root externals/work/crm-t30-cred
```

Both are green, with 11 checks and 0 failing. The §G.3 transcript
`{"s1":70,"s2":51,"s3prefixes":37,"s4":208,"union":247}` reproduces. The verbatim §G.3 script,
extracted from the document and run against the same tree, prints the same line.

**247 and 277 reconcile.** They measure different things:

- **247** is the §G.3 union, s1 ∪ s2 ∪ s4. It is what a census of the settings layer, `env.js`
  and the README can see.
- **277** is the whole surface. It is 247 plus the 30 names the union cannot see, and the gate
  finds all 30 by parsing code: 3 `AWS_*`, `CI`, 10 API v3 names, 4 `WEBHOOK_*`, and 12
  `ADMIN_*`/`FEED_*`. The arithmetic is the same as the reconciliation note in §B.4.

The report side also comes to 277 distinct names, and both set differences are empty. The class
headings match their lists: T 161, TS 28, D 48 (+3 `AWS_*` in parentheses, outside the count),
B 2, X 8. The ten-table holds 15, gap 5 holds 12 and §B.6 holds 2.

Two statements inside the specification do not match what it lists. The totals are unaffected:

- The plugin-configuration subgroup of T is headed **(97)** but lists **98** names: 33 singles
  plus 13 groups expanding to 65. The groups are BAGE 5, BOLUS_RENDER 3, BWP 4, CAGE 5, DBSIZE 5,
  ERRORCODES 3, IAGE 4, OPENAPS 11, PUMP 13, SAGE 4, TREATMENTNOTIFY 2, UPBAT 3 and XDRIPJS 3.
- The reconciliation says `TREATMENTS_AUTH` "is counted once, in §B.6, not in T". The T list does
  name it ("plus `TREATMENTS_AUTH`"). With it, T has 161 names: 19 + 21 + 7 + 16 + 98. Without it,
  T has 160. So T's 161 includes `TREATMENTS_AUTH`, and 247 = 161 + 28 + 48 + 2 + 8 − `CI` +
  `DEXCOM_BRIDGE_USE_LEGACY` holds on that reading.

The gate does not check subgroup headings. The document calls them hand-expansions.

### Controls

Each control was run against a `git archive 81a1f6ce` copy of the tree. Only the copy named in
each row was modified.

| control | expected | result |
|---|---|---|
| identical, untampered copy (positive) | green | 11 checked, 0 failing |
| `readENV('T30_CENSUS_PLANTED_CONTROL')` added to `env.js` | red, naming it | 3 failing: the transcript no longer reproduces; code-only `T30_CENSUS_PLANTED_CONTROL (lib/server/env.js)`; total 277 vs report 277 vs code 278 |
| `process.env['T30_DIRECT_PLANTED']` added to `lib/plugins/pushover.js` | red, with its site | code-only `T30_DIRECT_PLANTED (lib/plugins/pushover.js:2)`; total vs code 278 |
| `(k) => process.env[k]` added to `pushover.js` | red: a reader the gate cannot see through | "not explained by a parsed reader: lib/plugins/pushover.js:2" |
| `readENV('PUMP_T30_PLANTED')` added to `env.js` | red: a group count goes stale | `T PUMP_* stated (13), expands to 14`; class count; total 278 |
| `ADMIN_PORT` removed from a copy of the specification | red, from the report side | code-only `ADMIN_PORT (lib/admin/bind-guard.js:156)`; report 276 |
| `QUEUE_GATE_ROOT` pointed at an empty directory | red, measuring nothing | "could not read … this gate measured nothing", exit 1 |

`--ref` and `--root` were also compared on dev: a detached worktree `crm-t30-census-dev` at
`43289dde`, removed afterwards. Apart from the label, the two outputs are identical.

### How the surface moved: `81a1f6ce` against `official/dev` `43289dde`

These are not two points on one line. `git merge-base` is `a8888f0d` (2026-09-09). The seam is
545 commits past it and dev is 311. The gate at dev is red with 4 failing:

```
{"s1":70,"s2":45,"s3prefixes":39,"s4":228,"union":264}
code-side surface 266 = union 264 + CI + CUSTOMCONNSTR_DEXCOM_BRIDGE_USE_LEGACY
```

**On dev and not classified by the report (14):**

- Added on dev since the merge base:
  - `API_V1_COUNT_LEADING_NUMBER` and `API_V1_COUNT_ZERO_WINDOW`, read in `env.js`
    (15.0.9's count compatibility)
  - `CUSTOMCONNSTR_API3_MAX_LIMIT`, a README example of the Azure prefix
- Present at the merge base and gone from the seam (cut 4 retires the legacy bridge and
  mmconnect):
  - `BRIDGE_FIRST_FETCH_COUNT`, `BRIDGE_INTERVAL`, `BRIDGE_MAX_COUNT`, `BRIDGE_MAX_FAILURES` and
    `BRIDGE_MINUTES`, documented in the README
  - `MMCONNECT_INTERVAL`, `MMCONNECT_MAX_RETRY_DURATION`, `MMCONNECT_SGV_LIMIT`,
    `MMCONNECT_STORE_RAW_DATA` and `MMCONNECT_VERBOSE`, documented in the README
  - `CUSTOMCONNSTR_DEXCOM_BRIDGE_USE_LEGACY`, a **direct** `process.env` read in
    `lib/server/bridge-connect-compat.js:6` (also at the merge base)

**Classified by the report and absent on dev (25):**

- Seam-only:
  - `ADMIN_*` (6)
  - `FEED_*` (6)
  - `TENANCY_MODE` and `TENANT_*` (7)
  - `STORAGE_NAMESPACE`
  - `AWS_*` (3), from the seam's `mongo-client-configuration.js`
  - `CONNECT_COUNTRY_CODE`, from the seam's `mmconnect-connect-compat.js`
- `MONGODB_COLLECTION`: dev's README no longer documents it (BF-50).

**What did not change.** The eleven API v3 names (BF-46) and the four `WEBHOOK_*` names (BF-48)
are read the same way on both lines. Ten come through `setENVTruthy` (`generic 10` at both refs),
and `CI` and the four webhook names are direct `process.env` reads. Dev's change is that the
README now documents them, so source 4 sees them: dev's union is 264 and only 2 names sit
outside it, against 30 at the seam. Documenting a name does not route it through `env.js`. Under
`TENANCY_MODE=multi` these names are still read deployment-wide. `TRUST_PROXY` is in `env.js` and
the README on both lines. It is not new surface.

## 2. `T30-SCHEMA-CRED`: what was added to `platform.sql`

Commit `65ce54b9` on `seam/t30-schema-cred`. Three files: `lib/admin/platform.sql`,
`lib/admin/platform-store.js`, `tests/admin-tenants.test.js`.

| table | holds | RLS |
|---|---|---|
| `tenant_secret` | `(tenant_id, kind, version)` PK. `kind IN ('root','jwt','subject-salt')`: D13's root credential, D14's signing key, and §C.3's subject-token root. `state` is active, retiring or revoked. `material bytea` plus `key_ref` (the KEK that wrapped it). One active row per kind, enforced by a partial unique index. A retiring row needs `expires_at`, and `revoked_at` is set exactly when the row is revoked | ENABLE + FORCE, shared predicate |
| `tenant_subject` | the subject store: `(tenant_id, subject_id text)` PK, `name` unique per tenant, `roles`. No token column, because the token is derived from `subject-salt` | ENABLE + FORCE |
| `tenant_role` | `(tenant_id, name)` PK, `permissions` (shiro strings) | ENABLE + FORCE |
| `tenant_members` (changed) | `subject_id` changes from `uuid` to `text`. A composite `FOREIGN KEY (tenant_id, subject_id) REFERENCES tenant_subject`, so a member can only name a subject of its own tenant | unchanged |

`platform-store.js`:

- `PLATFORM_TABLES` lists all five tables, so `ensureSchema`'s completeness check covers them.
- `NOT_TENANT_DATA` adds `tenant_secret`, `tenant_subject` and `tenant_role`, and is exported.
- Comments now say "tables" where they said "two tables".

**Nothing reads these columns yet.** No code path mints, verifies or rotates against them.
`T30-WIRING` owns that, and its D14 signature-failure test is the non-vacuous check for D14.

`plugin:<n>` secrets and human-identity columns were deliberately left out. They belong to
`T30-SCHEMA-CONFIG`.

### Gate: red, green, red

```
QUEUE_GATE_ROOT=<shared checkout> node tools/queue/gates/platform-sql-surface.js --subset=cred --ref 81a1f6ce
  -> 8 checked, 6 failing (D14, D13 root, D13 subject-salt, D13 material/key_ref, subjects, members)
QUEUE_GATE_ROOT=<shared checkout> node tools/queue/gates/platform-sql-surface.js --subset=cred --ref seam/t30-schema-cred
  -> 8 checked, 0 failing
```

Each row below breaks one column or line in a copy of the branch's `platform.sql`. In every row
the gate goes red on exactly the matching finding and nothing else (1 failing). An identical copy
is green.

| break | the one finding that went red |
|---|---|
| remove `key_ref` | D13 material/key_ref: `tenant_secret: NO` |
| `material` as `text` | D13 material/key_ref: `tenant_secret: NO` |
| `tenant_members.subject_id` back to `uuid` | members: `subject_id (uuid) references tenant_subject.subject_id (text)` |
| drop `'jwt'` from the kind CHECK | D14: `none` |
| drop `FORCE ROW LEVEL SECURITY` on `tenant_secret` | rls: `NOT: tenant_secret` |

**Why the gate was rewritten.** The previous form, `HEAD:tools/queue/gates/platform-sql-surface.js`
before this change, had two weaknesses:

- It matched the whole file, comments included, so a comment could satisfy a check.
- It judged D13 by a table name.

Run against `81a1f6ce`'s `platform.sql` with one comment line appended
(`-- TODO: per-tenant signing key and tenant_secret root_credential`), it reported **D13 and D14
green**. The new form reports the same file red on all four D13/D14 findings. The members check
also had a gap: it accepted only `FOREIGN KEY (subject_id)`, not the composite form.

### Seam test suite, before and after

```
PG_URL=postgres://postgres@127.0.0.1:54354/postgres PGPASSWORD=<generated> npm test   # Node 24.20.0
```

| | result |
|---|---|
| before (`81a1f6ce`) | 2657 passing, 1 pending, exit 0; PostgreSQL suites ran, 0 `SKIPPED` |
| after (`65ce54b9`) | 2663 passing (2657 + 6 new), 1 pending, exit 0; 0 `SKIPPED` |

The one pending test is the same both times (`Batch with mixed valid/invalid documents`).

New tests, all against PostgreSQL:

- every platform table exists, with RLS enabled and forced on each tenant-scoped one
- secrets are kept out of the export and out of the deletion data gate
- a secret is invisible under another tenant and cannot be written under one
- at most one active secret per kind, with retiring/active overlap allowed
- an unknown kind is refused, and so is a retiring row with no expiry
- a member can name its own tenant's 24-hex subject id and is refused (23503) for another
  tenant's

The cascade test now covers members, subjects, roles and secrets. Each new test was mutated and
seen red:

| mutation | failing tests |
|---|---|
| `tenant_secret` dropped from `NOT_TENANT_DATA` | 7 failing, including the export manifest and the deletion gate |
| composite FK removed | 1 failing (cross-tenant member) |
| `FORCE` dropped on `tenant_secret` | 2 failing |
| one-active index made `WHERE false` | 1 failing |

The first attempt at the FK mutation did not apply: its search string skipped the comment lines
between `UNIQUE` and `FOREIGN KEY`, and the suite stayed green. The mutation was redone and
checked by `diff` before the run.

## 3. Decisions this work rests on, and what it chose

- **J4 / J5 (§C.5, §I.4), what wraps `material`: open.** The DDL follows the specification:
  ciphertext in `bytea` plus `key_ref`. The same columns serve an env-sourced KEK, a file KEK or a
  KMS. No row is written until `T30-WIRING`, and the wrapper must be decided before then. A
  related point for review: `'root'` is only ever *verified*, so a one-way hash would serve. The
  specification wraps every kind as ciphertext instead.
- **J1 / I.2, the `subject_id` type and referent: the plan's stated fix was applied.** That is
  `text`, with a composite FK to `tenant_subject`. I.2's counter-case is still open: a member who
  is not a subject, such as a hoster's support engineer or, if D17 row 2 lands, a Kratos identity.
  If that case is adopted, the column is renamed or the FK dropped.
- **I.1 / J10, migration: no machinery added.** The seam has never been deployed, because the
  branch chain is local. So an existing two-table database cannot exist. If one did,
  `ensureSchema` would refuse it as incomplete rather than pass it.
- **Subjects and roles in the export: chose to exclude them, against §A.2b.** §A.2b says
  `tenant_subject` and `tenant_role` "should stay in the export". The code does not allow that and
  T3.2's delete test at the same time:
  - `NOT_TENANT_DATA` controls both the export and the deletion data gate.
  - With the composite FK, a member requires a subject.
  - If subjects counted as data, a tenant with one member could no longer be deleted. T3.2's
    comment and test refuse exactly that.

  This branch keeps T3.2's tested behaviour, so subjects and roles are excluded from both. The
  alternative is to split the set into export-excluded and delete-gate-excluded. Both are
  one-line changes, and nothing writes these tables yet.
