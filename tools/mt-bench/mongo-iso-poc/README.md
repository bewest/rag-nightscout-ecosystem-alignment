# Mongo isolation PoC — enforced-filter seam vs. bypass, and aggregation-as-view

Backs the maintainer's specific pushback on §6.1/§6.2 of
[`nightscout-multitenancy-discussion-2026-09-09.md`](../../../docs/30-design/nightscout-multitenancy-discussion-2026-09-09.md):
"most of the change is a tenant discriminator, and Mongo's projections/aggregation can
cover what Postgres joins/views do — does multitenancy really require leaving Mongo?"

Two things measured against a live MongoDB 7 container, not asserted:

1. **Does a single enforced-filter repository seam actually hold**, i.e. is (a) from
   §6.1's three Mongo options ("application-only isolation behind a single enforced
   query-builder seam") actually leak-proof if every call site is disciplined to go
   through it — and does it still leak the moment *one* call site (mirroring today's
   `ctx.store.collection(env.entries_collection)`, `lib/server/entries.js:203-205`)
   bypasses it.
2. **Can Mongo's aggregation pipeline reproduce a Postgres-join/view use case** —
   correlating `treatments` (temp basal) with `entries` (glucose in the same window),
   which is the kind of query a Postgres view or `JOIN` would be reached for.

## Running

```bash
docker run -d --name mongo-iso-poc -p 27117:27017 mongo:7
sleep 3
node seed.js
node test.js
docker rm -f mongo-iso-poc
```

## What it shows — live results, this run

| Test | Result |
|---|---|
| Repository seam (`repo.list(tenantId, ...)`), used correctly | 10 rows, all tenant A |
| Repository seam called with no `tenantId` | throws `tenantId is required` — **fail-loud**, a bug caught only if that code path is ever exercised, not **fail-closed** the way RLS is (§6.1) regardless of code path |
| Same collection accessed directly, bypassing the seam (mirrors `ctx.store.collection(env.entries_collection)`, `lib/server/entries.js:203-205`) | **20 rows, both tenants** — the leak |
| `$lookup`-based join (temp basal correlated with nearby SGV), tenantId matched on both sides | 1 doc, `nearbyEntries` from tenant A only — **aggregation genuinely can do the join/view job** |
| Same `$lookup`, sub-pipeline's tenantId `$match` omitted | `nearbyEntries` from **both tenants** — the same bug class, just moved into pipeline authoring |

**Conclusion**: the maintainer's two claims are both correct as far as they go, and neither
changes §6.1's isolation-mechanism conclusion:

1. **"Most of the change is a tenant discriminator" — true for the data model.** Adding
   `tenantId` + a compound index is the whole schema change; nothing about Mongo's document
   model resists multitenancy.
2. **"Aggregation/projections can do what joins/views do" — also true, demonstrated
   above.** `$lookup` reproduces a Postgres-view-shaped correlation query correctly.

**What does not change**: both the repository seam and the `$lookup` pipeline are
*hand-written code that must remember to filter by tenant*, in exactly the way §6.1 already
established. The seam and the pipeline both do the *filtering* job fine; neither does the
*enforcement* job — a bypass or an omitted `$match` still leaks, and nothing at the database
layer stops it, because Mongo (as used here, without a paid Atlas/Queryable-Encryption tier)
has no per-document ACL analogous to Postgres RLS. This PoC does not show Mongo is
inadequate for multitenancy; it shows the isolation guarantee is exactly what §6.1
described — a discipline property enforced by code review and a single seam, not a database
property enforced regardless of code path. Whether that distinction is worth a storage
migration is a §10 cost/risk question, not a capability question — Mongo can do the query
shapes fine.
