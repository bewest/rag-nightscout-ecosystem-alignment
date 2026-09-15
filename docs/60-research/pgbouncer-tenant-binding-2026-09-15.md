# pgbouncer and the D3 tenant binding — isolation holds, and two of the three modes are usable

Date: 2026-09-15 · Harness: [`tools/qc/pgbouncer-tenant-binding.js`](../../tools/qc/pgbouncer-tenant-binding.js)
Under test: `crm-seam` at **`239f8c25`** ("Close the seam between the tenant reader and its
writer"), read from an independent detached worktree. **No shipping code was changed by this work
and nothing was committed to the branch under test.**

Arms: real PostgreSQL **16.14** and a real **pgbouncer 1.25.2** in front of it, in each of its
three pooling modes, connected as a `NOSUPERUSER NOBYPASSRLS` role against the **emitted** schema
(`lib/storage/postgres/generated/entries.sql`) under `FORCE ROW LEVEL SECURITY`.

This closes one row of the execution plan's *"What is still unmeasured"* table:

> | **pgbouncer + `set_config(is_local)`** | T2.5 | {M} §6.7 says the pooler may be required; its interaction with transaction-scoped binding is untested |

| ref | document |
|---|---|
| **{P}** | [multitenancy execution plan](../30-design/nightscout-multitenancy-execution-plan-2026-09-14.md) — §7 the unmeasured table, and the `is_local` vacuity note above it |
| **{T}** | [T2.5 PostgreSQL backend verification](t25-postgres-backend-verification-2026-09-15.md) — house style, and the run this one follows |
| **{B}** | [backfix register](../30-design/nightscout-backfix-register.md) |

---

## 0. The question, and what is deliberately not re-asked

Tenant isolation on this backend rests on one statement in
`lib/storage/postgres-storage.js` `runBound()`:

```js
await client.query('BEGIN');
// is_local => true. The whole reason this is a transaction.
await client.query("SELECT set_config('app.current_tenant_id', $1, true)", [ uuid ]);
```

and one predicate in the emitted DDL:

```sql
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)
```

`tests/postgres-entries-rls.test.js` already proves this holds with **no pooler**, including that a
connection handed back to node-postgres's own pool carries no binding, each check paired with a
break. **None of that is re-tested here.** The only question asked is: *does the property survive a
real pgbouncer in between, in each of its pooling modes?*

The failure being looked for is specific, and is the ordinary way RLS isolation dies in production.
A pooler in `transaction` mode changes **the unit of connection reuse**: the server connection one
client's transaction ran on is handed to a *different* client's next transaction. A session-scoped
binding — `set_config(name, value, false)`, or a bare `SET` — would outlive the transaction that set
it and be visible to whatever ran next on that backend. pgbouncer does **not** issue `DISCARD ALL`
between transactions: `server_reset_query` is a *session*-mode reset unless `server_reset_query_always`
is on, and it is off by default. That would be one tenant reading another tenant's glucose data with
nothing logged and nothing raised.

{P} is explicit that this was previously unmeasurable rather than measured:

> Breaking `set_config(…, is_local => true)` to `false` produced **0 failures** — because the
> adapter binds every operation anyway, so nothing distinguished a transaction-local binding from a
> session-local one. The entire argument for `is_local` … was unmeasured.

Through a transaction-pooling pgbouncer, that same break now produces **50 leaked rows in the serial
probe and 250 in the concurrent one** (§4). The property is measurable, and it is measured.

### Verdicts

| # | question | answer |
|---|---|---|
| 1 | Does isolation hold under `session` pooling? | **yes** — 0 cross-tenant rows, shared backend proven |
| 2 | Does isolation hold under `transaction` pooling? | **yes** — 0 cross-tenant rows over 50 bound transactions and 50 unbound reads on one shared backend |
| 3 | Does isolation hold under `statement` pooling? | **not applicable — the backend cannot run there at all.** `BEGIN` is refused `08P01` |
| 4 | Is the binding transaction-local in fact, not just in source? | **yes**, observed: no binding survives `COMMIT` onto the next client |
| 5 | Can the probe go red? | **yes** in `transaction` mode (50 / 250 rows). **No** in `session` mode, and §4 says why and what carries the evidence instead |
| 6 | Did the clients actually share a backend connection? | **yes**, by `pg_backend_pid()` and by pgbouncer's own `SHOW POOLS` / `SHOW SERVERS` |

**Three defects were found on the way, none of them in the binding.** They are in §6 and proposed as
BF-27, BF-28 and BF-29. BF-28 is the serious one.

---

## 1. Setup

| piece | value |
|---|---|
| PostgreSQL | 16.14 (`postgres:16-alpine`), container `pool-pg`, host port 15438 |
| pgbouncer | 1.25.2 (`edoburu/pgbouncer`), container `pool-bouncer`, host port 16438 |
| role | `ns_test_app_<random>`, `NOSUPERUSER NOBYPASSRLS`, created per run by `tests/support/postgres.js` |
| schema | one per arm, `CREATE SCHEMA … AUTHORIZATION <role>`, so `FORCE RLS` has an owner to subject |
| `default_pool_size` | **1** for every isolation measurement |
| `query_wait_timeout` | 15 s, so a pool of one queues visibly instead of hanging the run |
| `auth_type` | `scram-sha-256`, userlist written at 0600 into a `mkdtemp` directory and deleted on exit |
| `server_reset_query` | `DISCARD ALL`, `server_reset_query_always = 0` (both defaults, read back off the admin console) |
| `max_prepared_statements` | 200 (the 1.25 default) |

`default_pool_size = 1` is the load-bearing choice. With **one** server connection behind the pool,
two clients *cannot* avoid sharing a backend, so a green isolation result is a result about a shared
backend rather than about two clients that happened never to meet. That is the exact way this
measurement would go vacuous, and §5 shows it did not.

Every arm is driven through the **shipping** modules — `lib/storage/postgres-storage.js`,
`lib/api3/storage/pgCollection/`, the emitted DDL — via `store.withTenant()` and
`store.storageCollection(…).insertOne()`. Nothing is reimplemented.

### Two shapes, because one shape cannot answer for all three modes

- **Serial handoff.** One live client connection at a time. A client connects, binds a tenant,
  commits and disconnects; then an *unbound* client connects and reads. With `default_pool_size = 1`
  this forces the single server connection to be handed from one client to the next in **every**
  pooling mode, which is the literal shape of the failure being looked for.
- **Concurrent interleave.** Three live client connections — tenant A, tenant B, and an unbound
  bystander — alternating short transactions through a pool of one. This is what a hoster actually
  runs, and it is the shape transaction pooling exists for.

The **unbound bystander** is the party that matters. The adapter has no unbound path — `query()`
always binds — but a deployment has plenty of things that reach the database outside `withTenant()`:
a health check, a monitoring query, a migration, and whatever code is written next. Under a
transaction-local binding that reader is unbound, `NULLIF(…)` yields `NULL`, and RLS gives it zero
rows. Under a session-local one it inherits whichever tenant used the backend last. Every row it can
see is a row belonging to somebody else, so its row count *is* the leak count.

---

## 2. The mechanism: read, then observed

Read: `postgres-storage.js:189` passes `true` as the third argument to `set_config`, which is
`is_local` — **transaction**-local, not session-local. That is the correct choice under transaction
pooling. It is also what `tenant-scope.js` and the file's own header say it is.

Reading is not evidence. Observed, through the pooler, in each mode:

1. A client binds tenant A, runs a read, commits and **disconnects**.
2. A different client connects — onto the same backend, proven in §5 — and reads
   `current_setting('app.current_tenant_id', true)` and then the `entries` table.

| mode | binding seen by the next client (10 rounds) | rows it could then read |
|---|---|---|
| session | `0/10` — none | **0** |
| transaction | `0/10` — none | **0** |
| statement | n/a — the adapter cannot open a transaction at all | n/a |

The adapter's own `store.pooledTenantBinding()` — which exists so that `is_local => true` can be
*measured* rather than asserted — returns `null` after every committed transaction in both usable
modes.

---

## 3. Per-mode results

`bound cross-tenant rows` counts every row a **bound** client saw that belongs to the other tenant.
`unbound reader rows` counts every row the **unbound** bystander saw at all; each one would be a
leak.

| pool mode | adapter boots | explicit `BEGIN` | shared backend | rounds | bound cross-tenant rows | unbound reader rows | verdict |
|---|---|---|---|---|---|---|---|
| **session** | yes | accepted | **yes**, 1 pid | 10 serial + 2 concurrent | **0** | **0** | **isolation holds** — usable, with a caveat below |
| **transaction** | yes | accepted | **yes**, 1 pid | 10 serial + 25 concurrent | **0** | **0** | **isolation holds** — this is the mode hosters want, and it works |
| **statement** | **boots**, then every operation fails | **REFUSED** `08P01 transaction blocks not allowed in statement pooling mode` | — | — | — | — | **cannot carry this backend at all** |

The transaction-mode concurrent figure is over **50 bound transactions and 50 unbound reads**
alternating between two tenants on **one** shared backend connection, with 5 rows per tenant
present the whole time. Zero rows crossed in either direction.

### `session` mode queues rather than failing, and it is severe

`session` pooling assigns a server connection to a client for the whole life of that client's
connection. Three live clients against `default_pool_size = 1` therefore serialise at
*client-connection* granularity, and the thing that eventually frees the server is node-postgres's
own `idleTimeoutMillis` (10 s by default) closing an idle client. Measured:

| mode | concurrent interleave |
|---|---|
| transaction | **25/25 rounds in 193 ms** — 8 ms/round |
| session | **2/25 rounds in 80 095 ms** — 40 048 ms/round |

That is a ~5000× difference on the same work, and it is not a subtlety of the configuration: any
deployment whose client-side pool is larger than its pgbouncer pool will do this. It is a
*performance* result, not an isolation one — isolation held in every round that ran — but it is the
reason `transaction` is the mode {M} §6.7 is talking about.

### `statement` mode: the adapter boots and then fails everything

This is a mismatch, and it is reported as one rather than worked around.

```
explicit BEGIN/COMMIT in this mode : REFUSED [08P01] transaction blocks not allowed in statement pooling mode
--- statement / GREEN(shipping)
  boot                    : ok
  entries table in schema : FAILED [08P01] transaction blocks not allowed in statement pooling mode
  role through pooler     : FAILED [08P01] transaction blocks not allowed in statement pooling mode
  seed                    : FAILED [08P01] transaction blocks not allowed in statement pooling mode
```

**`boot: ok` is the finding.** `connect()` runs `assertNotBypassingRls()` and `ensureSchema()`, and
every statement in both is a single statement outside a transaction — exactly what `statement`
pooling allows. So the store is constructed, the boot-time safety check passes, the process reports
itself healthy, and then *every* storage operation fails, because `runBound()` opens a transaction
and `withTenant()` is the only way in. A deployment misconfigured this way comes up green and
serves nothing. That is BF-27.

No arm was re-run in another mode to obtain a green result.

---

## 4. Non-vacuity

### RED-1 — the binding, made session-scoped

The harness writes a **copy** of the shipping `postgres-storage.js` next to the original (so its
relative `require` and `__dirname` still resolve) with one substitution:

```js
-  await client.query("SELECT set_config('app.current_tenant_id', $1, true)", [ uuid ]);
+  await client.query("SELECT set_config('app.current_tenant_id', $1, false)", [ uuid ]);
```

and drives the entire battery through the copy. The shipping file is never opened for writing; the
copy is deleted on exit, including on `SIGINT` and on an uncaught throw. Same pooler, same schema
shape, same probes, same comparator.

| mode | probe | GREEN (shipping) | RED-1 (session-scoped) | sensitive? |
|---|---|---|---|---|
| **transaction** | bindings inherited by an unbound client | 0/10 | **10/10** | **yes** |
| **transaction** | rows that unbound client could read (serial) | 0 | **50** | **yes** |
| **transaction** | rows the unbound bystander read (concurrent) | 0 | **250** | **yes** |
| **transaction** | binding surviving `COMMIT` (`pooledTenantBinding()`) | none | **`11111111-…`** | **yes** |
| **session** | bindings inherited by an unbound client | 0/10 | **0/10** | **NO** |
| **session** | rows that unbound client could read | 0 | **0** | **NO** |
| **session** | binding surviving `COMMIT` (`pooledTenantBinding()`) | none | **`11111111-…`** | **yes** |

In `transaction` mode the leak probes go red hard, and the leaked rows are named: both tenants'
uuids appear, in both directions. The green result above them is therefore evidence.

**In `session` mode the cross-client leak probe cannot go red, and saying so is the point.** The
reason was measured rather than guessed. A session-scoped GUC set outside a transaction was written
by one client, that client disconnected, and the next client on the same backend read it back:

| mode | session GUC across a client disconnect |
|---|---|
| session | **cleared** |
| transaction | **SURVIVED** |

That is `server_reset_query = DISCARD ALL`, which pgbouncer issues when a *client* disconnects in
session mode and does not issue between transactions in transaction mode
(`server_reset_query_always = 0`). So under session pooling the pooler itself scrubs a session-local
binding at the handoff boundary, and a deployment running session mode would be *accidentally* safe
against the RED-1 defect. The evidence that `session` mode's green result is not vacuous is
therefore the third row — `pooledTenantBinding()` still distinguishes the two adapters, because the
leak is real *within* one client's own session, which is the axis the no-pooler suite already
covers.

**Do not read this as "session mode is safe, so `is_local` does not matter".** It means session
mode's safety here is supplied by pgbouncer's default `server_reset_query`, which is a configurable
knob on someone else's component, and the transaction-mode number two rows up is what happens when
that scrubbing is not there.

### RED-2 — the boot-time `BYPASSRLS` refusal, through the pooler

pgbouncer authenticates the client and then opens its **own** server connection. The question is not
whether the check works — the shipping suite covers that — but whether a pooler in between hides the
answer. `BYPASSRLS` was granted to the very role the run connects as, and the store was booted
through the pooler:

```
store refused to boot under BYPASSRLS : YES
error : PostgreSQL role "ns_test_app_…" is BYPASSRLS, so row-level security is not enforced for it
        and tenant isolation would be absent. Connect as a role that is NOSUPERUSER NOBYPASSRLS.
```

`current_user` read through the pooler is the application role in every mode, with
`rolsuper=false rolbypassrls=false`. The pooler does not launder the role.

---

## 5. Connection reuse was demonstrated, not assumed

A green isolation result from two clients that never shared a server connection measures nothing.
Two independent witnesses:

**`pg_backend_pid()`, read inside every bound transaction and by the bystander.** In every arm that
ran, across both tenants' clients and the unbound bystander, across serial and concurrent shapes:
**one distinct pid**. Example, transaction mode, GREEN:

```
SERIAL HANDOFF        : 10/10 rounds in 151 ms, 1 distinct backend pid(s) [323]
CONCURRENT INTERLEAVE : 25/25 rounds in 193 ms, 50 bound txns + 50 unbound reads
  SHARED BACKEND      : YES (1 distinct pid) [323]
```

**pgbouncer's own account**, off the admin console:

```
SHOW POOLS   : db=postgres user=ns_test_app_… cl_active=0 sv_active=0 sv_idle=1 sv_used=0 pool_mode=transaction
SHOW SERVERS : pid=323 state=idle
SHOW CONFIG  : default_pool_size="1" pool_mode="transaction" server_reset_query="DISCARD ALL"
               server_reset_query_always="0" max_prepared_statements="200" server_lifetime="3600"
```

One server connection existed for the pool, its backend pid is the pid both tenants' transactions
ran on, and pgbouncer agrees.

---

## 6. What the pooler broke — three defects, none in the binding

### 6.1 BF-27 · the store boots under a pooling mode that cannot run it

Covered in §3. `assertNotBypassingRls()` and `ensureSchema()` are transaction-free, so they pass
under `statement` pooling and the store is handed back as ready. Every subsequent operation fails
`08P01`.

*Fix*: an `assertTransactionsWork()` beside `assertNotBypassingRls()` — open a transaction, bind,
roll back — so the store refuses to boot into a configuration where it cannot serve a single read.
Both checks share the same rationale: the failure is otherwise invisible until it is a production
outage.

### 6.2 BF-28 · an error on an idle pooled connection ends the process

**This is the serious one, and it is not pgbouncer's fault.** It is in this report because the
pooler is what made it visible: the `statement` mode arms produced nine uncaught
`Connection terminated unexpectedly` exceptions, and the only reason the harness survived to report
anything is an `uncaughtException` instrument it carries for that purpose.

`pg-pool` re-emits an idle client's error on the Pool (`node_modules/pg-pool/index.js:62`,
`pool.emit('error', err, client)`). Node's `EventEmitter` **throws** on an `'error'` event with no
listener. `postgres-storage.js` registers `pool.on('connect', …)` and **no `'error'` listener** —
grep confirms there is none anywhere under `lib/storage/` or `lib/api3/storage/`.

Measured in three child processes, so "the process dies" is an exit code rather than an inference.
The disconnect is a plain `pg_terminate_backend()`, which is what a failover, a restart, an
idle-connection reaper, a pgbouncer restart or an operator does:

| arm | what it is | exit | outcome |
|---|---|---|---|
| `store` | **the shipping adapter's own pool** | **1** | `throw er; // Unhandled 'error' event` — `terminating connection due to administrator command` |
| `bare` | a `pg.Pool` with no `'error'` listener | **1** | identical — the mechanism alone |
| `handled` | the same pool **with** `pool.on('error')` | **0** | `POOL ERROR HANDLED: …` then `SURVIVED` |

The third arm is the fix, demonstrated in the same run: one listener is the whole difference between
a logged reconnect and a dead Nightscout.

*Scope, stated honestly*: this reproduces **against a direct connection** and is not caused by
pgbouncer. A pooler adds ways to trigger it — pgbouncer restart or `RELOAD`, `client_idle_timeout`,
and the `statement`-mode connection close above — but so does any database restart or failover, and
a multitenant deployment on managed PostgreSQL will see those routinely. Severity is **high** on
availability: a single tenant's database blip takes down every tenant on that process.

*Fix*: `pool.on('error', …)` on the Pool created in `connect()`, logging and no more. The MongoDB
adapter has no equivalent exposure because the driver owns its own topology; this is a property of
using `pg.Pool` directly.

### 6.3 BF-29 · `SET search_path` is not a per-connection guarantee under transaction pooling

`postgres-storage.js` issues `SET search_path` in two places, both **outside** any transaction:

```js
pool.on('connect', function (client) {
  client.query(`SET search_path TO "${schema}"`)…      // "Every connection in the pool"
});
…
await client.query(`SET search_path TO "${schema}"`);  // ensureSchema(), then the emitted DDL
if (!exists.rowCount) await client.query(ddlFor(specName));   // CREATE TABLE entries — unqualified
```

Under transaction pooling a statement outside a transaction *is* its own transaction, and the server
connection it lands on is not the server connection the next statement from the same client lands
on. `SET` is session state on the server, so the guarantee the `on('connect')` comment describes —
*"Every connection in the pool, including ones created later"* — does not exist through pgbouncer.

Demonstrated deterministically at `default_pool_size = 2`, by pinning the first server connection
inside an open transaction held by another client so the fallback is certain rather than hoped for:

```
before pinning : search_path=ns_test_searchpath_85cdf613  backend=351
                 unqualified SELECT   : resolved
pinned backend : 351 (held inside an open transaction by another client)
after pinning  : search_path="$user", public            backend=353
                 unqualified SELECT   : [42P01] relation "entries" does not exist
```

*Why it did not bite the measurements above*: `tableFor()` qualifies every table name
(`"schema"."entries"`), so ordinary reads and writes do not consult `search_path` at all, and every
arm in §3 ran at `default_pool_size = 1` where there is no second server to land on. The exposure is
`ensureSchema()` at boot under a pool larger than one: its `SET` and its unqualified
`CREATE TABLE entries` can reach different backends. The usual outcome is loud — `42P01`, or
`permission denied for schema public`, since PostgreSQL 15 removed the public `CREATE` grant. The
outcome that is **not** loud is a deployment where a schema named after the role exists, in which
case the emitted table is created in the wrong namespace and nothing complains.

*Fix*: qualify the DDL, or run `ensureSchema()`'s `SET` and DDL inside one explicit transaction, and
delete the `pool.on('connect')` handler rather than leave a comment promising something the pooler
does not provide. Severity **medium**: boot-time, usually loud, and only under a pool larger than
one.

### 6.4 Prepared statements and `DISCARD ALL` — measured, nothing found

- **The adapter uses no named prepared statements.** Every query it issues is an unnamed
  extended-protocol statement (`client.query(text, params)`); grep found no `{ name: … }` query
  object anywhere in `lib/storage/` or `lib/api3/storage/`. pgbouncer's historic transaction-mode
  weak point is therefore not reachable from this code today.
- **Named prepared statements work anyway** in all three modes on pgbouncer 1.25.2, including
  `statement`, with `max_prepared_statements = 200` (the 1.25 default): four uses of the same named
  statement across four separate acquisitions succeeded. Recorded for whoever adds one later; it is
  a property of pgbouncer ≥ 1.21, not of this codebase.
- **`server_reset_query = DISCARD ALL` runs on client disconnect in `session` mode and not between
  transactions in `transaction` mode**, confirmed by the GUC probe in §4. This is what makes
  `is_local => true` load-bearing rather than stylistic, and it is why a future operator who sets
  `server_reset_query_always = 1` would be *masking* a defect rather than fixing one.

---

## 7. Indicative cost, clearly labelled

{P} says the pooler "may be required", so the per-operation cost of the extra hop is useful context.
It is **not a benchmark**: one machine, one run, loopback TCP, a ten-row table entirely in cache, no
TLS, no load, and a single client at `default_pool_size = 20` — the pooler doing its ordinary job
rather than the pathological pool of one used for the isolation work.

| arm | p50 | p90 | p99 | mean |
|---|---|---|---|---|
| through pgbouncer (`transaction`) | **0.338 ms** | 0.682 ms | 1.504 ms | 0.427 ms |
| direct to PostgreSQL | **0.270 ms** | 0.462 ms | 0.889 ms | 0.318 ms |
| **p50 overhead of the extra hop** | **0.068 ms** | | | |

n = 2000 per arm, one bound read (`withTenant` → `BEGIN` → `set_config` → `SELECT count(*)` →
`COMMIT`), back to back, same process, same table.

The isolation arms' own latency figures are **not** usable for this and are excluded: they are taken
with three live clients contending for a pool of one, and two runs of the same harness put the
transaction-mode pooled p50 at 0.74 ms and 2.85 ms. The direction was consistent across every run
(pooled is slower); the magnitude was not, which is exactly why the cost note is measured separately
and why it should not be quoted as a figure for a loaded system. **The situation a pooler is added
for — many more clients than server connections — is not measured here at all.**

---

## 8. Honest limits

- **One pgbouncer (1.25.2) and one PostgreSQL (16.14).** `max_prepared_statements` defaulting to
  200 is a 1.24+ behaviour; on an older pgbouncer the named-statement result in §6.4 would differ.
  The `is_local` result does not depend on either version — it is a property of PostgreSQL's
  transaction semantics — but the statements about pgbouncer's defaults are statements about this
  build.
- **pgbouncer only.** Odyssey, pgcat, RDS Proxy, Supavisor and PgDog all pool differently; none was
  tested. A hoster using one of those has not had this question answered.
- **`session` mode's concurrent interleave completed 2 of 25 rounds** before the wall-clock budget
  stopped it, because that configuration queues for ~40 s per round. Session mode's isolation
  evidence therefore rests on the **serial handoff** (10/10 rounds, shared backend proven), not on
  the concurrent shape. And the cross-client leak probe is **insensitive** in session mode (§4) —
  that arm's green result is carried by `pooledTenantBinding()` alone.
- **`default_pool_size = 1` throughout the isolation work.** That is what makes backend sharing
  certain, but it is not a realistic production setting, and it means nothing here exercises the
  case where pgbouncer holds *several* server connections with different residual session state.
- **One collection.** `entries` is the only collection with an emitted PostgreSQL schema, so every
  row counted above is an `entries` row.
- **No TLS and no `LISTEN`.** {P} already records, from {DB} §10.3, that transaction-mode pooling
  accepts `LISTEN` and silently delivers nothing — that is T4.3's problem and was not re-verified
  here. TLS adds CPU to the per-operation term the cost model rests on and is still unmeasured, as
  {P} §7's first row says.
- **Nothing was driven over HTTP.** Every arm reaches the adapter directly through
  `store.withTenant()`; express, the router, `lib/server/entries.js` and the tenant middleware are
  not in the loop. BF-27's "the process reports itself healthy" is read from `connect()` rather than
  observed against a running server.
- **BF-28's severity is an argument, not a measurement.** That the process dies is measured. That a
  managed-PostgreSQL deployment sees such disconnects routinely is an expectation about operations,
  and a maintainer should weigh it.
- **The `statement`-mode arms leave `boot: ok` in the summary table.** That is accurate and it is
  the finding; it is not a green isolation result and is not counted as one.

---

## 9. Proposed backfixes

`BF-01`–`BF-26` are taken in {B} (the brief for this work said `BF-20` was the high-water mark; it
has moved). These are the next three.

| id | defect | where | severity | status |
|---|---|---|---|---|
| **BF-27** | The store boots successfully under a pooling mode that cannot run it; `assertNotBypassingRls()` and `ensureSchema()` are transaction-free, so `statement` pooling passes boot and then fails every storage operation `08P01` | `lib/storage/postgres-storage.js` `connect()` | medium — a misconfigured deployment reports healthy and serves nothing | open |
| **BF-28** | The `pg.Pool` has no `'error'` listener, so an error on an **idle** pooled connection is an unhandled `'error'` event and ends the process | `lib/storage/postgres-storage.js` `connect()` | **high** — availability; one database blip kills the process for every tenant on it | open |
| **BF-29** | `SET search_path` is issued outside a transaction in `pool.on('connect')` and in `ensureSchema()`, which is not a per-connection guarantee under transaction pooling; `ensureSchema()`'s unqualified DDL depends on it | `lib/storage/postgres-storage.js` `connect()` / `ensureSchema()` | medium — boot-time, usually loud, only at `default_pool_size > 1` | open |

None of them is a defect in the tenant binding, and none of them changes the answer in §3.

---

## 10. Reproduction

```sh
git -C <crm-seam> worktree add --detach <crm-pool> 239f8c25
ln -s ../crm-seam/node_modules <crm-pool>/node_modules   # worktrees do not share one

docker network create pool-net
docker run -d --name pool-pg --network pool-net \
  -e POSTGRES_PASSWORD="$PGPASSWORD" -p 15438:5432 postgres:16-alpine

cd tools/qc && npm install
PGPASSWORD=… WORKTREE=<crm-pool> node pgbouncer-tenant-binding.js
# or one mode: session | transaction | statement
# env: ROUNDS, LATENCY_ITERS, LATENCY_NOTE_ITERS, BUDGET_MS, SKIP_RED, POOL_PORT
```

pgbouncer is started and stopped **by the harness**, once per pooling mode, from a config directory
it creates under `$TMPDIR`.

**No credential is stored anywhere.** The harness exits `2` with instructions if `PGPASSWORD` is
unset. The superuser password is read from the environment and never written. The unprivileged role
the run connects as is created per run by
[`tests/support/postgres.js`](../../externals/work/crm-seam/tests/support/postgres.js) with a
password that exists only in the process's memory — reused rather than reimplemented, because RLS is
silently not enforced for a superuser and a run that connected as one would have measured nothing.
pgbouncer needs that password in a `userlist.txt`; the harness writes it at `0600` into a `mkdtemp`
directory outside the repository and removes it in a `finally`, on `SIGINT`, and on an uncaught
throw — together with the RED-1 adapter copy and the pgbouncer container.

Run this only against a throwaway database. The harness creates roles and schemas and drops them.
