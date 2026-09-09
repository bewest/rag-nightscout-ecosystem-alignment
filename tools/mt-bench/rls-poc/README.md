# RLS PoC — Postgres row-level security, measured against a live container

Backs §5.2.1 and §5.4 of
[`nightscout-multitenancy-discussion-2026-09-09.md`](../../../docs/30-design/nightscout-multitenancy-discussion-2026-09-09.md):
does Postgres RLS actually do what Nocturne's code claims, at what cost, and how does it
compare to the isolation Nightscout gets today from MongoDB with an application-only
filter? Reimplements Nocturne's verified pattern
(`externals/nocturne/src/Infrastructure/.../NocturneDbContext.cs:14-64`,
`Migrations/20260227034745_EnforceMultitenancy.cs:66-76`,
`Interceptors/TenantConnectionInterceptor.cs`) with `knex`/`pg` instead of EF Core, because
that is Node's tool for this, not a description of the .NET version.

## Running

Requires Docker and a free port 15432.

```bash
docker run -d --name rls-poc-pg -e POSTGRES_PASSWORD=poc -p 15432:5432 postgres:16-alpine
sleep 4
docker exec -i rls-poc-pg psql -U postgres -c "CREATE DATABASE rlspoc;"
cat setup.sql | docker exec -i rls-poc-pg psql -U postgres -d rlspoc

npm init -y && npm install pg knex --no-audit --no-fund
node test.js   # correctness: fail-closed + forgotten-filter leak comparison
node perf.js   # cost: RLS overhead at 500 tenants x 600 rows, vs plain WHERE, vs no filter

docker rm -f rls-poc-pg   # cleanup
```

## What the scripts show

`test.js` — three live assertions, not descriptions:
1. A connection that never binds a tenant sees **zero rows**, not an error and not
   everything (the `current_setting(..., true)` two-argument form returns NULL rather
   than raising, and `NULL = anything` is never true in SQL — that is the actual
   fail-closed mechanism, not the `POLICY` syntax itself).
2. A query against the RLS table **with no `tenant_id` predicate written in the SQL at
   all** still returns only the bound tenant's rows.
3. The same "forgot the filter" bug, simulated against a MongoDB-shaped in-memory
   collection with only an application-layer filter, **leaks every tenant's rows** —
   this is the asymmetry the whole exercise is about.

`perf.js` — the cost of buying (1)/(2), against 300 000 rows / 500 tenants:

| Scenario | p50 |
|---|---|
| No tenant context bound (fail-closed, 0 rows) | 0.19 ms |
| RLS-scoped, **no explicit tenant_id filter in the query** | 0.95 ms |
| Plain table, explicit `WHERE tenant_id=` (no RLS) | 0.63 ms |
| Plain table, **no filter at all** (the leak, 300k rows returned) | 16.9 ms |

RLS overhead here is ~0.32 ms relative to the equivalent hand-written filter — real, but
small next to Nightscout's actual query rate (~14 ops/tenant/load cycle, once every
1–5 s, per §2.3 of the discussion doc).

## Gotchas hit while building this

- `set_config(key, value, true)` is **transaction-local** — its effect is gone by the next
  statement if that statement isn't in the same transaction. `test.js` wraps calls in an
  explicit `knex.transaction()` (mirroring per-request binding); `perf.js` instead uses
  `set_config(key, value, false)` (session-scoped) because it issues bare `.raw()` calls
  outside a transaction. Either is valid; **picking the wrong one silently returns 0 rows
  instead of erroring**, which looks like "RLS is working" when it's actually "the GUC was
  never really bound" — verify row counts, don't just check for absence of errors.
- `RESET <custom_guc>` does not reliably return to NULL once a placeholder GUC has been
  set in a session — it can revert to `''`, which then fails `::uuid` casts. Use a
  dedicated, never-touched connection to test the "no context" case rather than resetting.
- Table owners and roles with `BYPASSRLS` ignore RLS policies outright — `ALTER TABLE ...
  FORCE ROW LEVEL SECURITY` and connecting as a non-owner, non-bypass role are both
  required, not optional, for the fail-closed property to actually hold.
