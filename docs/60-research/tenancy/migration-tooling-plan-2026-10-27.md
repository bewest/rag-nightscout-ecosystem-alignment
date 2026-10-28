# Migration tooling for MongoDB and PostgreSQL: a plan

*Contributor-facing. A draft of 2026-10-27, asked for by the maintainer. It covers how
cgm-remote-monitor could adopt migration tooling for **both** of its storage backends: MongoDB,
which stays permanent for single-tenant sites (D4), and PostgreSQL, the multitenant service
(D3). The facts are in §1 to §3. The recommendation, kept separate, is in §4. Nothing has been
added to cgm-remote-monitor.*

Marks: **[M]** means measured, in [`tools/lab/tenant-config-schema/`](../../../tools/lab/tenant-config-schema/README.md)
(PostgreSQL 16.15, umzug 3.8.2, Node 22.23.4). **[R]** means read or reasoned.

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
| A restart mid-migration must not leave a half-migrated database | maintainer brief | PostgreSQL: each migration and its ledger row commit together [M]. MongoDB: no transactions to lean on, so each step must be idempotent and the ledger written after it [R]. |
| Several hosted processes start at once (D21 roles) | D21 | Exactly one applies each migration; the others wait or refuse to serve. PostgreSQL: advisory lock [M]. MongoDB: a lease document with an expiry, because a dead holder cannot release it [R]. |
| Rollback | maintainer brief | `down` migrations for development and pre-release. In production, prefer roll-forward plus a backup, because a `down` that drops a table also drops its data (the lab's `0006` down destroys version history). [R] |
| An explicit operator subcommand versus at boot | D21 (`nightscout migrate …` named as a later subcommand) | Hosted: `nightscout migrate up` as a one-shot job before `serve`, with serving roles refusing a stale schema [M]. Single: at boot, under the same lock, as index creation is today [R]. |
| No dependency added to cgm-remote-monitor without review | D12, maintainer brief | A small dependency, or none, and no second runtime. |

## 3. Candidates

Only umzug was run. Every other row is read from the tool's documentation or package metadata.

| tool | backends | lock | atomic migration + ledger | down | fits a Node process at boot | notes |
|---|---|---|---|---|---|---|
| **umzug** 3.8.2 | any (storage interface). Ships JSON, memory, MongoDB and Sequelize storages | **none built in.** The lab adds a PostgreSQL session advisory lock [M] | **no.** It calls `storage.logMigration` after `up()` returns, as a separate step (`node_modules/umzug/lib/umzug.js:166-172`) [M]. The lab writes the ledger row inside the migration's transaction instead [M] | yes, with `to` | yes, as a library; an optional CLI | one runner and one ledger shape for both backends; the safety pieces are the project's to write |
| **node-pg-migrate** (8.0.4 Dec 2025; 9.0.0 Jul 2026) | PostgreSQL only | advisory lock built in [R] | one transaction per migration by default [R] | yes [R] | yes, as a library or CLI | does PostgreSQL well; MongoDB would still need a second tool |
| **migrate-mongo** 14.0.7 | MongoDB only | a lock collection with an optional TTL (`lockCollectionName`, `lockTtl`) [R, readme] | transactions optional, and only where the server supports them [R, readme] | yes [R] | mainly a CLI with a config file | a second tool and a second ledger format beside the PostgreSQL one |
| **knex** migrations 3.3.0 | SQL databases (PostgreSQL); not MongoDB | a lock table (`knex_migrations_lock`) [R] | a transaction per migration by default [R] | yes [R] | yes | brings a query builder the seam does not use |
| **Flyway**, **Atlas** | PostgreSQL (and others) | built in [R] | yes [R] | yes, or diff-based [R] | **no**: a JVM or Go binary outside the Node process | suits an operator's deployment pipeline; does not serve self-hosters on MongoDB |

### 3.1 What the lab measured (umzug with a project-written PostgreSQL storage)

| test | result | its control |
|---|---|---|
| `MIGRATE-up-down-up` | applies `0001`-`0007` (46 schema objects), rolls all back to an empty schema, and re-applies [M] | a `down` that forgets one function leaves 1 object, so red |
| `MIGRATE-crash-mid` | a runner killed during migration 0004 leaves 0004 neither applied nor recorded; a re-run completes [M] | **umzug's default split** (implicit transaction per file, ledger row afterwards): the server **finished and committed 0004 after the client died** (the orphaned session ran about 5.4 s), the ledger row was never written, and the re-run fails on `relation "deployment_policy" already exists`. Red. |
| `MIGRATE-crash-after` | a runner killed just after 0005 returns leaves the ledger matching the schema; a re-run completes [M] | default split: 0005 applied but not recorded. Red. |
| `MIGRATE-concurrent` | four `migrate up` processes started together: all exit 0, and one applies all 7 migrations [M] | lock off: 3 of 4 fail on `duplicate key … pg_type_typname_nsp_index`. Red. |
| `MIGRATE-drift` | a migration file edited after it was applied stops the next run [M] | drift check off. Red. |
| `MIGRATE-serve-refuses-stale-schema` | a serving role at start refuses a schema with pending migrations [M] | fully migrated schema: no refusal, so the check is not constant. Red. |

The `MIGRATE-crash-mid` control matters for any tool. **Killing the client does not stop the
server.** If the `COMMIT` is implicit at the end of the statement the server is already running,
the migration commits without its ledger row. The fix is to send `BEGIN`, the migration, the
ledger insert and `COMMIT` as separate statements in one transaction, which is what the lab's
runner does. Setting `client_connection_check_interval` on the migration role would also
shorten the orphaned session. That was not measured. [R]

## 4. Recommendation

*This section is a recommendation, not a fact. It is for the maintainer to accept or reject.*

**One runner, umzug, with two project-owned storage adapters**, and a `nightscout migrate`
subcommand in D21's dispatcher.

1. **The runner.** umzug, as a library inside `bin/nightscout.js migrate {status|up|down --to}`.
   It is one dependency, with one ledger shape and one lock discipline for both backends. Its
   gaps (lock, atomic ledger, drift) are each about 20 lines in the lab's
   `lib/migrator.js`. They are measured, and are better owned by the project than hidden in a
   tool.
2. **PostgreSQL adapter.**
   - The ledger is a `schema_migrations` table holding name, checksum and time.
   - A session advisory lock is held for the run.
   - Each migration is `BEGIN; <file>; INSERT ledger; COMMIT`, with explicit statements.
   - Migrations are plain `.up.sql` and `.down.sql` files, like the lab's, so DDL stays
     reviewable and portable into the seam's `platform.sql` layout.
   - A **separate migration role** owns the schema. The serving roles own nothing (M7).
3. **MongoDB adapter.**
   - The ledger is a `schema_migrations` collection.
   - The lock is a lease document: an insert on a fixed `_id`, an expiry that the holder
     renews, and a takeover allowed only after the expiry.
   - Each step must be idempotent and resumable, because standalone servers have no
     transactions. The ledger entry is written after the step.
   - Today's boot-time index creation stays as it is. It is already idempotent and is part of
     D1's "single unchanged". The ledger is only for changes that rewrite data.
4. **When migrations run.**
   - **Hosted (`multi`):** only `nightscout migrate up`, run as a one-shot job before
     `nightscout serve <roles>`. Every serving role checks at start that the schema matches
     its release and refuses to serve if it does not (`MIGRATE-serve-refuses-stale-schema`).
     No serving role migrates.
   - **Single:** at boot, under the lock, before `ensureIndexes`. This keeps today's
     zero-step upgrade for self-hosters. `nightscout migrate status` is offered for
     operators who want to look first.
5. **Rollback.**
   - `down` files are kept and tested (up, down, up in CI), for development and pre-release.
   - In production, a bad migration is fixed by a new forward migration.
   - A `down` that destroys data needs a flag and an export first, which is the same rule as
     the autoprune floor.
6. **How the lab's schema is expressed in it.** As it already is: `0001`-`0007` are umzug
   migrations, applied and rolled back cleanly (§3.1). [M] Porting to the seam would mean:
   - replacing `platform-store.js:120-158`'s all-or-nothing `ensureSchema` with a call to the
     runner;
   - adding a baseline migration that records `0001` as applied on databases that already
     have `tenants` and `tenant_members`;
   - giving `postgres-storage.js`'s emitted tables a migration of their own.

**The alternative**, if the maintainer prefers tools that bring their own safety:
node-pg-migrate for PostgreSQL and migrate-mongo for MongoDB. That means two ledgers, two CLIs
and two lock designs, and the self-hoster's MongoDB path gains a tool built mainly as a CLI.
Neither was measured here.

## 5. Open questions

1. Should single-tenant MongoDB sites migrate at boot? The recommendation says yes, to keep
   self-hosters' zero-step upgrade. Or should they need `nightscout migrate up`?
2. Which existing hosted deployments, if any, already hold the seam's `tenants` table? This
   decides whether a baseline migration is needed or whether the platform schema is young
   enough to recreate (config-surface §I.1, J10).
3. Is a production `down` ever run, or are `down` files for development only?
4. Should the MongoDB lease and its expiry be measured against a real replica set and a
   standalone server before adoption? (Not done here.)
5. Should migration files carry a signature or checksum list in the release, so that the drift
   check also catches a tampered image, not only an edited file?
