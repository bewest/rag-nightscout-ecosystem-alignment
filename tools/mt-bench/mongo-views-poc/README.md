# Mongo views PoC — is there a server-enforced RLS equivalent after all?

Backs a maintainer's pushback on
[`nightscout-multitenancy-discussion-2026-09-09.md`](../../../docs/30-design/nightscout-multitenancy-discussion-2026-09-09.md)
§6.1: *"Mongo's projections and tooling should be equally feasible; people
just find tables more familiar."*

§6.1 concluded that **"MongoDB has no server-enforced per-document ACL
comparable to RLS"**, and §6.1.1 tested an *application-level* seam and found
it leaks on bypass. Neither tested the mechanism MongoDB actually provides
for this: a **read-only view whose pipeline reads `$$USER_ROLES`** (7.0+),
with users granted `find` on the view and **no privilege on the base
collection**.

Measured against a live MongoDB **8.3.9** container, not argued.

## Running

```bash
docker run -d --name mongo-views-poc -p 27118:27017 mongo:8 --auth
sleep 6
docker cp setup.js  mongo-views-poc:/tmp/ && docker exec mongo-views-poc mongosh --quiet --file /tmp/setup.js
docker cp test.js   mongo-views-poc:/tmp/ && docker exec mongo-views-poc mongosh --quiet --file /tmp/test.js
docker cp limits.js mongo-views-poc:/tmp/ && docker exec mongo-views-poc mongosh --quiet --file /tmp/limits.js
```

## What works — §6.1's claim is too strong

| Test | Result |
|---|---|
| `alice` (role `tenant_a`) reads the view | `[101, 102]` — her tenant only |
| `bob` (role `tenant_b`), **same view definition** | `[201, 202]` |
| `nobody` — has the view privilege, holds no tenant role | **0 rows.** Not an error, not everything |
| Reading the base collection directly | `Unauthorized` |
| Reaching it via `aggregate` instead | `Unauthorized` |
| Client re-requests the projected-out `deviceToken` | still absent |
| Client filters *by* `deviceToken` | 0 — it cannot be selected on either |
| A second, stricter view (`effect-only`) | returns `["sgv"]` and nothing else |

One view definition serves every tenant, because the predicate reads the
connected user's roles rather than a literal. That is the property that makes
it comparable to RLS rather than to "one view per customer", and it is
**fail-closed in exactly the sense §6.1 called the value proposition**:
forgetting to grant a tenant role yields zero rows, not all rows.

Field-level projection lands in the same place, which matters for the
sensitivity work: a disclosure profile is expressible as a view, and the
credential never leaves the server for any consumer of it.

## What does not work — three real asymmetries

**1. Views are read-only.** Every write is refused:

| Attempt | Result |
|---|---|
| `insertOne` into the view | `Unauthorized` |
| `updateOne` through the view | `Unauthorized` |
| `insertOne` into the base collection | `Unauthorized` |

So reads are server-enforced and **writes are not covered at all**. Granting
write on the base collection reopens exactly the bypass §6.1.1 measured.
Postgres RLS policies apply to `INSERT`/`UPDATE`/`DELETE` as well as
`SELECT`. This is the sharpest difference found.

**2. The role-keyed predicate cannot seek to one tenant.** 60,004 rows, an
index on `{tenantId: 1, sgv: 1}`, query `sgv >= 150`:

| Path | Scan | Docs examined | Keys examined | ms |
|---|---|---|---|---|
| Role-keyed view | **COLLSCAN** | 60,004 | 0 | 60 |
| Role-keyed view, static `$in` prefix to coax an index | IXSCAN | 25,002 | 25,003 | 45 |
| Base collection, explicit `tenantId` filter | IXSCAN | 12,500 | 12,500 | 11 |

The `$match` is `$expr` over a value computed from `$$USER_ROLES`, so the
planner has no constant to build index bounds from. Adding a static prefix
recovers an index scan but examines **every tenant's keys** and filters by
role afterwards — index-*assisted*, still O(all tenants) rather than O(one
tenant). ~4–5× here, and the gap grows with tenant count, which is the wrong
direction for the thing this would be adopted for.

A Postgres RLS predicate is an ordinary predicate on a real column; the
planner uses it for index bounds like any other.

**3. Tenant identity is bound to the authenticated user**, not to the
connection state. Postgres rebinds with `set_config(..., is_local => true)`
inside a transaction on a shared pool. MongoDB would need a distinct
authenticated identity per tenant, so a hub serving many tenants cannot
multiplex them over one pool. At the tenant counts §7.4 discusses this is an
operational difference, not a detail.

One shared caveat: `root` still reads everything, as a Postgres table owner
does — except Postgres has `FORCE ROW LEVEL SECURITY` to close that even for
the owner, and MongoDB has no equivalent for a `root` role.

## Conclusion

The maintainer's challenge is **substantially right**, and §6.1 should be
corrected: MongoDB 7.0+ does have a server-enforced, fail-closed, one-
definition-for-all-tenants mechanism for **row scoping and field
projection**, and it is not a familiarity artefact.

What survives is narrower and specific: **writes, index locality, and
connection multiplexing**. Those are the grounds on which to prefer one
engine for a *multitenant* deployment — not "Mongo cannot project".
