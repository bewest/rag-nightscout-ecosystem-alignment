# PostgREST PoC — a headless multitenant REST backend directly on Postgres RLS

Backs the maintainer's question on §5.3/§6.1 of
[`nightscout-multitenancy-discussion-2026-09-09.md`](../../../docs/30-design/nightscout-multitenancy-discussion-2026-09-09.md):
"would it be feasible to implement a compatible headless, multitenant Nightscout backend
using PostgREST?" Reuses the exact RLS primitive from `../rls-poc` (same
`NULLIF(current_setting(...), '')` policy shape) but puts PostgREST, not a Node API
layer, in front of it — no application code between the HTTP request and the database.

## Running

```bash
docker run -d --name postgrest-poc-pg -e POSTGRES_PASSWORD=poc -p 15433:5432 postgres:16-alpine
sleep 5
docker exec -i postgrest-poc-pg psql -U postgres -c "CREATE DATABASE nsrest;"
cat setup.sql | docker exec -i postgrest-poc-pg psql -U postgres -d nsrest

npm init -y && npm install jsonwebtoken pg --no-audit --no-fund
docker run -d --name postgrest-poc --network host \
  -v "$PWD/postgrest.conf:/etc/postgrest.conf:ro" \
  postgrest/postgrest:latest /bin/postgrest /etc/postgrest.conf

node test.js

docker rm -f postgrest-poc postgrest-poc-pg   # cleanup
```

## What it shows — live results, this run

| Test | Result |
|---|---|
| No JWT presented | `401` — `web_anon` has zero grants on `api.entries`, not a silent empty list |
| Tenant A JWT, **zero `tenant_id` in the querystring** | 5 rows, only tenant A — RLS, not the client, does the scoping |
| Date-range query, PostgREST's native `date=gte.<iso>` syntax | works — same operator shape (`gte`, `order`, `select`, `limit`) as API v3's `find[date][$gte]` |
| Tenant B JWT, `limit=1000` | only tenant B's 20 rows, never A's |
| Tampered JWT signature | `401` before RLS is ever reached — signature verification happens first |

**PostgREST's own mechanism does the tenant-role switch, no custom code required**: a JWT
with a `role` claim (here `app_tenant`) makes PostgREST `SET ROLE` into it per-request, and
PostgREST always exposes the whole verified JWT payload as the `request.jwt.claims` GUC —
the RLS policy reads `tenant_id` back out of that JSON, the same `NULLIF(current_setting
(...), '')` fail-closed shape as `../rls-poc`, no pre-request PL/pgSQL function needed for
this case.

## What this does and does not answer

**Answers**: PostgREST can serve the *storage-scoped* half of Nightscout's API (list/insert
entries and treatments, filtered/sorted/paginated, tenant-isolated) with no Node process in
front of Postgres at all — a real "headless multitenant backend" candidate for exactly the
read/write-a-collection shape most of API v3 is.

**Does not answer** (out of scope for this PoC, tracked as EXP-MT-047 in the main
document): PostgREST has no place to put computed state — `calcdelta`/IOB/COB, alarm
evaluation, plugin state, vendor-connectivity polling (`lib/plugins/bridge.js`,
`lib/plugins/mmconnect.js`) all need a process somewhere. The realistic shape is PostgREST
in front for the CRUD surface, plus a small stateless Node/other-runtime service for
computed views and connectors — not "replace Node entirely." Postgres `VIEW`s and generated
columns (§6.3) can absorb some of this (e.g. a `delta` computed column), but IOB/COB
curves are not expressible as SQL generated columns without recreating the oref
algorithm in SQL, which nobody is proposing.
