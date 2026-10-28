# Migration tooling for MongoDB and PostgreSQL: a plan

*Contributor-facing. A draft of 2026-10-27, asked for by the maintainer. It covers how
cgm-remote-monitor could adopt migration tooling for **both** of its storage backends: MongoDB,
which stays permanent for single-tenant sites (D4), and PostgreSQL, the multitenant service
(D3). The facts are in §1 to §3 and §6.1-§6.4. The recommendations, kept separate, are in §4 and §6.5. Nothing has been
added to cgm-remote-monitor.*

*Revised the same day. The maintainer asked for the alternative to be measured against the
same properties as umzug, with the MongoDB side measured for both options. §3 is now a
side-by-side table of four measured arms:*

- *umzug with a project PostgreSQL adapter;*
- *node-pg-migrate 9.0.0;*
- *umzug with a project MongoDB ledger and lease lock;*
- *migrate-mongo 14.0.7.*

Marks: **[M]** means measured, in [`tools/lab/tenant-config-schema/`](../../../tools/lab/tenant-config-schema/README.md)
(`compare.js`, `compare-results.json`; `harness.js` for the `MIGRATE-*` tests). The setup:

- PostgreSQL 16.15, in container `cfgschema-pg`;
- MongoDB 8.0.34, **standalone**, in container `cfgschema-mongo` with `nofile` 64000;
- Node 22.23.4, which is dev's floor (`engines.node` `^22.23.4`);
- umzug 3.8.3, node-pg-migrate 9.0.0, migrate-mongo 14.0.7, mongodb driver 6.21.0, pg 8.13.1.

**[R]** means read or reasoned.

## 1. What cgm-remote-monitor does today

### 1.1 Dev (`official/dev` at `db3b9e4e`): MongoDB

There is no migration ledger, no schema version and no `migrate` command. The database is
shaped at boot by three mechanisms. [R]

- **Indexes are ensured at every boot.**
  - The boot sequence's `ensureIndexes` step (`lib/server/bootevent.js:313-350`) gathers each
    collection's `indexedFields`. The lists are in:
    - `lib/server/entries.js:438`, `treatments.js:552`, `devicestatus.js:316`;
    - `profile.js:378`, `food.js:232`, `activity.js:164`;
    - API v3's set (`lib/api3/storage/mongoCollection/index.js:147`).
  - It sends one `createIndexes` per collection. If that fails, it retries one index at a time,
    and it never rejects (`lib/storage/mongo-storage.js:255-294`).
  - Authorization's two indexes are ensured earlier, in `setupAuthorization`
    (`bootevent.js:240-241`; `lib/authorization/storage.js:248-252`).
  - Each API v3 collection ensures its indexes again when it is constructed
    (`mongoCollection/index.js:52-54`).
  - Boot waits up to `INDEX_WAIT_MS` = 20 s, then continues while the builds finish
    (`bootevent.js:41-62`).
  - Creating an index that already exists is a no-op. A changed index definition is logged
    and skipped. Nothing ever drops or alters an index.
- **Configuration is rewritten in memory at boot, not stored.**
  - `migrateBridgeToConnect` (`bootevent.js:108-117`, applied at `:420-432`) copies the legacy
    bridge settings into the connector's settings (`lib/server/bridge-connect-compat.js`).
  - `applyMmconnectToConnectCompatibility` (`bootevent.js:425`) does the same for the MiniMed
    settings (`lib/server/mmconnect-connect-compat.js`).
  - Neither writes to the database. Each runs on every boot.
- **Documents are adapted when read, not migrated.**
  - The profile editor aligns old profile records when it loads them
    (`lib/client-core/profile-editor/migrate.js:51-63`).
  - Treatment target units are converted on write. Stored records are left as they are
    (`lib/treatmentTargetUnits.js:36`: "Records already stored are not migrated").

The admin plugins (`lib/admin_plugins/clean*.js`, `futureitems.js`, `daterangedelete.js`) are
operator-triggered data clean-ups from the UI. They are not schema migrations. [R]

### 1.2 The seam (`81a1f6ce`): PostgreSQL

There is no ledger and no version here either. Each component carries its own "create if
missing" code. [R]

- `lib/admin/platform-store.js:120-158` (`ensureSchema`) runs the whole `platform.sql` in one
  transaction, but only when **none** of `PLATFORM_TABLES` exists. If some but not all exist,
  it throws and tells the operator to repair the schema by hand. A database that already holds
  the two tables silently never gets a third (config-surface §I.1).
- `lib/feed/bounded-poll.js:382-414` (`ensureSchema`) follows the same all-or-nothing pattern
  for the feed tables.
- `lib/storage/postgres-storage.js:295-325` (`ensureSchema`) creates each emitted document
  table if it is missing. It is not one transaction. It also calls `ack-store.ensureTable`
  (`lib/storage/ack-store.js:199-215`).
- There is no path for `ALTER`. The only form of change is "add a table that does not exist
  yet".
- The seam's comments require the **connecting** role to own the tables "or FORCE ROW LEVEL
  SECURITY has nobody to subject" (`postgres-storage.js:290-293`, `ack-store.js:199-203`).
  Measured: tables owned by a separate non-superuser migration role still leave RLS active for
  every non-owner application role (`ISO-roles`). [M] So a migration role that differs from the
  serving role is compatible with RLS. See the schema spec, M7.

## 2. The constraints a tool must meet

| constraint | source | what it asks of a tool |
|---|---|---|
| Self-hosters stay on MongoDB permanently, across a wide range of hosting | D1, D4 | It must run inside the Node process at boot, with no extra binary or runtime. Many self-hosted platforms cannot run a separate one-off command before the app starts. [R] It must work on a standalone MongoDB, so it cannot rely on multi-document transactions, which need a replica set. [R] |
| A restart mid-migration must not leave a half-migrated database | maintainer brief | PostgreSQL: each migration and its ledger row commit together [M]. MongoDB: no transactions to lean on, so each step must be idempotent and the ledger written after it [M] (§3.1, P2). |
| Several hosted processes start at once (D21 roles) | D21 | Exactly one applies each migration; the others wait or refuse to serve. PostgreSQL: advisory lock [M]. MongoDB: a lease document with an expiry, because a dead holder cannot release it [M] (§3.1, P3 and P3b). |
| Rollback | maintainer brief | `down` migrations for development and pre-release. In production, prefer roll-forward plus a backup, because a `down` that drops a table also drops its data (the lab's `0007` down destroys version history). [R] |
| An explicit operator subcommand versus at boot | D21 (`nightscout migrate …` named as a later subcommand) | Hosted: `nightscout migrate up` as a one-shot job before `serve`, with serving roles refusing a stale schema [M]. Single: at boot, under the same lock, as index creation is today [R]. |
| No dependency added to cgm-remote-monitor without review | D12, maintainer brief | A small dependency, or none, and no second runtime. |

## 3. Candidates, measured side by side

### 3.1 What was compared, and how

Each arm runs as a child process through one wrapper (`lib/run-tool.js`), which has the shape a
`nightscout migrate up|down` subcommand in D21's dispatcher would have.

- **PostgreSQL arms.** Both apply the lab's eight schema migrations. node-pg-migrate gets the
  same SQL, converted to its one-file `-- Up Migration` / `-- Down Migration` format.
- **MongoDB arms.** Both apply the same three CommonJS migration files:
  - an index build (idempotent);
  - a filtered backfill (idempotent);
  - a new collection plus a seed document (**not** idempotent: a second run hits `E11000`).

Every measurement carries its own non-vacuity check, and a measurement that fails its check is
reported invalid. All rows below passed theirs. The checks:

- the kill landed while the migration was running (a `PgSleep` wait in PostgreSQL; a printed
  mark between two steps in MongoDB);
- the four concurrent runs overlapped in time;
- the edited migration had been applied first.

The concurrency rows were measured three times, and the outcome was the same each time.

| property | umzug + project PG adapter | node-pg-migrate 9.0.0 | umzug + project Mongo adapter (ledger + lease) | migrate-mongo 14.0.7 |
|---|---|---|---|---|
| **P1** up, down to zero, up again | 8 / 8 / 8; state after down equals the start [M] | 8 / 8 / 8; state after down equals the start [M] | 3 / 3 / 3; state after down equals the start [M] | 3 / 3 / 3, but `down` undoes one migration per call, so the wrapper loops [M] |
| **P2** runner killed mid-migration | **consistent**: the killed migration neither applied nor recorded. The orphaned server session ran about 5.3 s, then rolled back. Re-run completes. [M] umzug's *default* split (ledger written after `up()`) left the migration **committed but unrecorded** (`MIGRATE-crash-mid` control). [M] | **consistent**: same as the umzug adapter. Re-run completes. `runner()` called without `singleTransaction` ran one transaction per migration, so 0001-0004 stayed applied and recorded. Its type file says that option defaults to `true`. [M] | **applied but unrecorded**: the seed step ran and the migration was not recorded, because a standalone server has no transactions. Re-run as written fails on `E11000` (after waiting about 5 s for the 5 s lease). Re-run with the step written idempotently completes. [M] | **applied but unrecorded**, as for the umzug adapter. The crashed run **left its lock behind**: re-runs were refused ("a lock is in place") for about 62-77 s (`lockTtl` 30 s plus the server's TTL sweep). Then: as written, `E11000`; idempotent, completes. [M] |
| **P3** four runners started at once, tool's lock on | 4/4 exit ok; one applies all 8, three wait and find nothing pending [M] | default mode `fail`: **1/4 ok**, three exit with "Another migration is already running". Mode `wait`: 4/4 ok, applied once. [M] | 4/4 exit ok; one applies all 3, three wait on the lease [M] | **lock not exclusive**. In 3 of 3 runs, three or four runners passed the lock check and ran the migrations again. The ledger holds 6 or 9 duplicate rows, and 3 runners failed on the seed `E11000`. [M] |
| **P3** same, lock off | 1/4 ok; 3 fail `duplicate key … pg_type_typname_nsp_index` [M] | 1/4 ok; 3 fail on the same catalogue race or on creating `pgmigrations` [M] | 1/4 ok; the ledger's unique `_id` refuses duplicate records (`E11000`), but the idempotent steps ran up to four times [M] | 1/4 ok; 6 duplicate ledger rows [M] |
| **P3b** one runner, then three more while it runs (separates "racy" from "does nothing") | lock on: 3/3 wait, then exit ok, applying 0 [M] | `fail`: 0/3, refused. `wait`: 3/3 ok. [M] | lock on: 3/3 wait, then exit ok [M] | lock on: 0/3, refused ("a lock is in place"). The lock works against a runner that is *already* running; it only races at the same start. [M] |
| **P4** an applied migration file edited | **detected**: the run is refused, naming the file (checksum) [M] | **ignored**: the run succeeds, applies nothing and says nothing [M] | **detected**: the run is refused, naming the file (checksum) [M] | `useFileHash: false`: **ignored**. `useFileHash: true`: **re-run**: the edited migration is applied again and the ledger gains a second row (3 to 4). [M] |
| **P5** behind a CommonJS `nightscout migrate` dispatcher | `require('umzug')`; a library; `pending()` / `executed()` give `status` [M] | ESM-only package; loads with `require()` through require(esm) on Node 22.23.4, dev's floor; `runner({direction, count, …})`; lock modes `fail` / `wait` / off [M] | as for umzug; the ledger and lease are about 120 lines (`lib/mongo-migrator.js`) [M] | ESM main. `require()` returns a Proxy whose properties are promises, so `import()` is the usable path. `config.set()` works with no config file. `up`/`down`/`status` take an existing `(db, client)`, so the server's own connection can be reused. [M] |
| what the project must write | ledger, lock, one-transaction-per-migration, checksum (`lib/migrator.js`, about 150 lines) | a checksum check, if drift is to be caught; choose lock mode `wait` if several processes may start it | ledger, lease lock, checksum (`lib/mongo-migrator.js`) | a real lock (or run it from one process only), a drift check, and its own recovery from a stale lock |

Findings that hold for every MongoDB option [M]:

- **A step and its ledger record cannot be made atomic on a standalone server.** Both MongoDB
  arms left the seed step applied and unrecorded. Only an idempotent step made the re-run
  safe. Whatever tool is chosen, MongoDB migrations must be written idempotent and resumable.
- **`createCollection` with identical options on an existing collection succeeded on 8.0.34.**
  The lab's first non-idempotent step was in fact idempotent, and the first comparison run
  showed no failure. The step was changed to a seed `insertOne`, which does fail. This is a
  case of a break that did not break anything, and it was caught by asking why the re-run
  passed.

### 3.2 Tools not measured

| tool | backends | notes |
|---|---|---|
| **knex** migrations 3.3.0 | SQL databases (PostgreSQL); not MongoDB | a lock table (`knex_migrations_lock`) and a transaction per migration by default [R]; brings a query builder the seam does not use |
| **Flyway**, **Atlas** | PostgreSQL (and others) | a JVM or Go binary outside the Node process [R]. It could suit an operator's pipeline, but it does not serve self-hosters on MongoDB, and it adds a second runtime. |

### 3.3 The earlier umzug-only measurements

These are still in force, in `harness.js` (59 tests, 77 controls):

| test | result | its control |
|---|---|---|
| `MIGRATE-up-down-up` | applies `0001`-`0008`, rolls all back to an empty schema, and re-applies [M] | a `down` that forgets one function leaves 1 object, so red |
| `MIGRATE-crash-mid` | the killed migration is neither applied nor recorded; a re-run completes [M] | umzug's default split: the server committed the migration after the client died, and the ledger row was never written. Red. |
| `MIGRATE-crash-after` | a kill just after a migration returns leaves the ledger matching the schema [M] | default split: applied but not recorded. Red. |
| `MIGRATE-concurrent` | four processes at once: all exit 0, and one applies every migration [M] | lock off: 3 of 4 fail. Red. |
| `MIGRATE-drift` | an edited applied file stops the next run [M] | drift check off. Red. |
| `MIGRATE-serve-refuses-stale-schema` | a serving role refuses a schema with pending migrations [M] | a fully migrated schema is accepted. Red. |
| `MEMBER-migration-refuses-rows` | `0002` refuses to run while `tenant_members` holds rows [M] | without lifting `FORCE` around its count, the migration role counts zero rows under RLS, and the check passes vacuously. Red. |

The last row matters for any tool. A data check inside a migration, run by a role subject to
`FORCE ROW LEVEL SECURITY`, sees nothing unless it binds a tenant or lifts `FORCE`. [M]

## 4. Recommendation

*This section is a recommendation, not a fact. It is for the maintainer to accept or reject.
It rests on the measurements in §3.*

**One runner, umzug 3.8.3, with two project-owned storage adapters**, and a
`nightscout migrate {status|up|down --to}` subcommand in D21's dispatcher. Five reasons:

1. **MongoDB decides it.** Of the two MongoDB arms, only umzug with the project ledger and
   lease was measured to:
   - serialise four simultaneous starters (P3);
   - detect an edited migration (P4);
   - recover from a crashed runner without about a minute of refused runs (P2).

   migrate-mongo's lock raced when the runners started together (3 of 3 runs). It left a
   stale lock after a crash. With `useFileHash` it re-ran an edited migration instead of
   refusing it.
2. **PostgreSQL is a close call.** node-pg-migrate met the restart property out of the box
   (P2), and its lock is real in both of its modes (P3, P3b). It did not detect drift (P4),
   and its default lock mode turns simultaneous starters away rather than making them wait.
   Using it would mean a second tool and a second ledger format beside the MongoDB runner,
   for a saving of about 150 lines that are already written and measured.
3. **One shape for both backends.** One ledger shape (name, checksum, time), one lock
   discipline, and one `status` output, for self-hosters on MongoDB and operators on
   PostgreSQL alike.
4. **PostgreSQL adapter.**
   - The ledger is `schema_migrations`.
   - A session advisory lock is held, waiting, for the whole run.
   - Each migration is `BEGIN; <file>; INSERT ledger; COMMIT`, sent as separate statements.
   - A drift check by checksum.
   - Plain `.up.sql` and `.down.sql` files.
   - A **separate migration role** owns the schema (spec M7). A migration that checks data in
     a `FORCE`-RLS table must lift `FORCE` or bind a tenant (§3.3).
5. **MongoDB adapter.**
   - The ledger is `schema_migrations`, with a unique `_id` per migration.
   - A lease lock with an expiry, renewed while held.
   - A drift check by checksum.
   - **Every step idempotent.** This is a review rule for migration authors, because no tool
     can supply it on a standalone server.
   - Today's boot-time index creation stays as it is (D1).

**When migrations run:**

- **Hosted:** `nightscout migrate up` as a one-shot job before `nightscout serve <roles>`.
  Serving roles refuse a stale schema (`MIGRATE-serve-refuses-stale-schema`).
- **Single:** at boot, under the lock, before `ensureIndexes`, to keep self-hosters' zero-step
  upgrade.

**Rollback:**

- `down` files are kept and tested (up, down, up in CI).
- Production fixes roll forward.
- A data-destroying `down` needs a flag and an export first.

**The alternative**, if the maintainer prefers tools that bring their own safety, is
node-pg-migrate for PostgreSQL (lock mode `wait`, plus a project checksum check) with **the
umzug MongoDB adapter** for MongoDB. The measurements do not support migrate-mongo as the
MongoDB half without project work on its lock, its stale-lock recovery and drift.

## 5. Open questions

1. Should single-tenant MongoDB sites migrate at boot? The recommendation says yes, to keep
   self-hosters' zero-step upgrade. Or should they need `nightscout migrate up`?
2. Which existing hosted deployments, if any, already hold the seam's `tenants` table? This
   decides whether a baseline migration is needed or whether the platform schema is young
   enough to recreate (config-surface §I.1, J10).
3. Is a production `down` ever run, or are `down` files for development only?
4. *(Answered by MIG-VV, §6.)* The MongoDB arms were first measured on a standalone 8.0.34
   server only. They have now been repeated on an 8.0 replica set, and on 5.0.32 (dev's
   floor) standalone and as a replica set. Not yet measured: a killed (rather than stepped
   down) primary, a network partition, and a sharded cluster.
5. Should migration files carry a signature or checksum list in the release, so that the drift
   check also catches a tampered image, not only an edited file?

## 6. MIG-VV: the MongoDB adapter verified on replica sets and on dev's floor

*Added 2026-10-27. The maintainer adopted umzug for both stores provisionally (execution plan
§2.13) and asked for verification first (queue `MIG-VV`). This section holds the facts. The
verdict on the provisional choice, kept separate, is §6.5.*

### 6.1 Setup [M]

Four MongoDB servers:

| target | image, version | how it runs |
|---|---|---|
| 8.0 standalone | `mongo:8.0`, 8.0.34 | container `cfgschema-mongo`, `127.0.0.1:27747` (round 2's server) |
| 8.0 replica set | `mongo:8.0`, 8.0.34 | container `cfgschema-mongo8-rs`: **one container running three `mongod` processes**, replica set `rs0` on `127.0.0.1:27750-27752`, host network, keyfile auth (`mongo-rs/start-rs.sh`) |
| 5.0 standalone | `mongo:5.0.32`, 5.0.32 | container `cfgschema-mongo5`, `127.0.0.1:27748` |
| 5.0 replica set | `mongo:5.0.32`, 5.0.32 | container `cfgschema-mongo5-rs`, as the 8.0 set, on `127.0.0.1:27753-27755` |

- 5.0.32 is dev's floor: `docs/runtime-upgrade.md:34,46` at `db3b9e4e` (CI's oldest lane; 4.4
  is unsupported).
- Every container was started with `--ulimit nofile=64000:64000`. `mig-vv.js` asserts, before
  every row, that the container is running with that limit and on its address, and that each
  replica set has three members.
- Software: Node 22.23.4, mongodb driver 6.21.0, umzug 3.8.3, migrate-mongo 14.0.7.
- Record: `tools/lab/tenant-config-schema/mig-vv-results.json`, with all rows valid.

**The rows** are the same as round 2's §3.1, with three additions (P7, P2t, P6/P6w):

| row | what it does |
|---|---|
| P1 | up, down to zero, up again |
| P2 | runner killed mid-migration, after a non-idempotent seed insert |
| P3 | four runners started at once, lock on and off |
| P3b | one runner, plus three started during it |
| P4 | an applied file edited |
| P7 | the adapter running each migration and its ledger record in one transaction |
| P2t | P2 in that mode |
| P6 / P6w | a primary step-down (`replSetStepDown`) while migration 3 is running: idle in a pause (P6), or writing in a loop (P6w) |

Two checks guard P6/P6w against being vacuous:

- the step-down must return while migration 3 is still paused or looping;
- a new primary must be observed.

**Migration 3 was reordered for this round:** create the collection, build its index, insert
the seed, then a final write. Inside a transaction, an index can only be built on a collection
that is still empty (§6.3). The MongoDB rows in `compare-results.json` (round 2) ran on the
earlier order. This round's `8.0-standalone` rows repeat them on the current files.

### 6.2 Results per version and topology [M]

**umzug + the project adapter (ledger + lease):**

| row | 8.0 standalone | 8.0 replica set | 5.0 standalone | 5.0 replica set |
|---|---|---|---|---|
| P1 up / down / up | 3/3/3, clean | 3/3/3, clean | 3/3/3, clean | 3/3/3, clean |
| P2 killed mid-migration | seed applied, not recorded; re-run as written fails `E11000` after the 5 s lease; idempotent re-run completes | same | same | same |
| P3 four at once, lock on | 4/4 ok, applied once | 4/4, once | 4/4, once | 4/4, once |
| P3 lock off | 1/4 ok (the ledger's unique `_id` refuses duplicates) | 1/4 | 1/4 | 1/4 |
| P3b one running + three | 3/3 wait, then ok | 3/3 | 3/3 | 3/3 |
| P4 drift | detected (refused) | detected | detected | detected |
| P7 transactions | **refused**: "Transaction numbers are only allowed on a replica set member or mongos" | **completes**: 2 of 3 ledger records written inside their migration's transaction (migration 1, an index on an existing collection, runs outside) | refused, same message | completes, 2 of 3 |
| P7, every migration forced into a transaction | refused | refused at migration 1: "Cannot create new indexes on existing collection … in a multi-document transaction" | refused | refused at migration 1, same |
| P2t killed mid-migration, with transactions | — | **seed not applied, migration not recorded; re-run as written completes** (about 4 s, the lease) | — | same as 8.0 |
| P6 step-down, runner idle in migration 3 | — | new primary in about 0.5 s; runner completes; ledger 3, seed 1, index present, no lock left | — | same |
| P6, with transactions | — | completes; migration 3's transaction was **retried** (it ran twice), and the result is the same | — | same |
| P6w step-down during a write loop | — | completes; the runner counted 1815 increments and the server holds 1815, so none was lost or doubled | — | completes; 1221 = 1221 |
| P6w, with transactions | — | completes after one transaction retry; 36451 = 36451 (the aborted attempt's writes are gone) | — | completes; 34069 = 34069 |

**migrate-mongo 14.0.7:**

| row | 8.0 standalone | 8.0 replica set | 5.0 standalone | 5.0 replica set |
|---|---|---|---|---|
| P1 up / down / up | 3/3/3, clean | 3/3/3, clean | 3/3/3, clean | 3/3/3, clean |
| P2 killed mid-migration | seed applied, not recorded; **stale lock refused re-runs for about 93 s**, then `E11000`; idempotent re-run completes | same, about 36 s | same, about 52 s | same, about 36 s |
| P3 four at once, lock on | **1/4 ok, 6 duplicate ledger rows**: the lock did not exclude simultaneous starters | same | same | same |
| P3 lock off | 1/4 ok, 6 duplicate ledger rows | same | same | same |
| P3b one running + three | 0/3, refused ("a lock is in place") | same | same | same |
| P4 drift, `useFileHash` off / on | ignored / re-run (ledger 3 to 4) | same | same | same |
| P6 step-down, idle | — | completes; ledger 3, seed 1, index, no lock left | — | same |
| P6w step-down during writes | — | completes; 2081 = 2081 | — | completes; 1217 = 1217 |

The stale-lock wait varies between about 36 and 93 s. That is consistent with `lockTtl` 30 s
plus the server's TTL sweep, which runs about every 60 s. [R]

### 6.3 Transactions on a replica set [M]

**Yes: the adapter can write a migration and its ledger record in one transaction, on 8.0 and
on 5.0.32 replica sets.** With it, a runner killed mid-migration leaves the migration neither
applied nor recorded, and the non-idempotent migration then re-runs cleanly (P2t). That is
the property a standalone server lacks (P2). On a standalone server, starting a transaction
is refused (P7).

Measured limits on what a transactional migration may do:

- **No index on an existing collection.** An index can be built inside a transaction only on a
  collection that is still empty: migration 1, and migration 3 before its reordering, were
  refused.
- **No `listCollections` inside the transaction.** It is not allowed there, so migration 3
  reads it outside.
- **The callback may run more than once.** `withTransaction` re-runs it after a transient
  error, as in the P6 step-down, so work outside the transaction (logs, external calls) must
  tolerate a second attempt.

### 6.4 The failover result [M]

On both replica sets the primary was stepped down while migration 3 was running. The cases:

- the runner paused (P6);
- the runner writing continuously (P6w);
- with and without transactions;
- for both tools.

In every case:

- a new primary was elected in about 0.5 s;
- the runner **completed** without operator action;
- the ledger held all 3 migrations, and the data was complete (seed present, index built);
- no lease or lock document was left behind;
- no write was lost or doubled.

With transactions, the step-down aborted the open transaction and the driver's retry ran the
whole migration again, committing once. A re-run was not needed in any failover case. (Not
measured: a primary that is killed rather than stepped down, a network partition, a member
that loses data on rollback, and writes with a write concern weaker than the driver's
default.)

### 6.5 Verdict on the provisional choice

*This is a recommendation, not a measurement.*

- **The provisional choice holds.** umzug with the project MongoDB adapter behaved the same on
  8.0 and on dev's 5.0.32 floor, standalone and as a replica set. It serialised simultaneous
  starters, detected drift, left no lock behind after a crash or a failover, and completed
  through a primary step-down. migrate-mongo repeated round 2's weaknesses on every target:
  a lock that races, a stale lock after a crash, and drift either ignored or re-run.
- **The adapter should use a transaction when the server supports one**, for migrations that
  declare `transactional: true`. It should detect support from the topology (a replica set or
  `mongos`), and fall back to the non-transactional path on a standalone server, which P7 shows
  refuses transactions outright.
- **The idempotence rule stays.** Standalone servers, which self-hosters run, and
  non-transactional steps (index builds on existing collections) still depend on it.
- **Review rules for transactional migrations:** build indexes before writing to a new
  collection; do not call `listCollections` inside the transaction; tolerate a second attempt
  of the callback.
