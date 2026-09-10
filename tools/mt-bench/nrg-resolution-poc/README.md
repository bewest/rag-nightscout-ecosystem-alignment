# NRG resolution PoC — cost of a sidecar host→tenant resolution hop

Backs §9.4 of
[`nightscout-multitenancy-discussion-2026-09-09.md`](../../../docs/30-design/nightscout-multitenancy-discussion-2026-09-09.md):
`~/src/nightscout-roles-gateway` (NRG) is a real, already-built external gateway that
resolves an `expected_name` (hostname) to a tenant/upstream via a two-table SQL join,
then enforces RBAC/group-policy/schedule rules, and hands NGINX an `x-upstream-origin`
header (`lib/routes.js:327-330`, `lib/policies/index.js:33-49`). This measures the
concrete cost of that hop, mirroring its actual query shape, against the alternative of
folding host→tenant resolution directly into `cgm-remote-monitor`'s own request path
(§5.1/§9.1's tenant-resolution middleware).

## Running

```bash
docker run -d --name nrg-poc-pg -e POSTGRES_PASSWORD=poc -p 15434:5432 postgres:16-alpine
sleep 5
docker exec -i nrg-poc-pg psql -U postgres -c "CREATE DATABASE nrgpoc;"
docker exec -i nrg-poc-pg psql -U postgres -d nrgpoc -c "CREATE EXTENSION IF NOT EXISTS pgcrypto;"
cat setup.sql | docker exec -i nrg-poc-pg psql -U postgres -d nrgpoc

npm init -y && npm install pg knex --no-audit --no-fund
node bench.js

docker rm -f nrg-poc-pg   # cleanup
```

## What it shows — live results, two independent runs, 5 000 lookups over 2 000 sites

| Shape | p50 | p99 |
|---|---:|---:|
| **Sidecar** — knex/Postgres `LEFT JOIN`, mirroring NRG's `find_expected_name` exactly | 0.21 / 0.45 ms | 1.08 / 1.11 ms |
| **In-core** — same data loaded once into a `Map<hostname, siteRow>`, consulted in-process | 0.0002 / 0.0004 ms | 0.0011 / 0.0025 ms |

**~1 000× difference, run to run consistent.** This is the concrete number behind §9.3's
"every added hop is another place tenant identity must be re-derived" argument, applied
specifically to *resolution* rather than to the RLS/isolation check itself (§6.1's RLS
overhead, ~0.3–0.6 ms, is a separate, already-measured cost that still applies on top of
whichever resolution path is chosen).

## What this does and does not argue

**Does not argue** NRG is poorly built, or that a network hop for resolution is always
wrong — 0.2–1.1 ms is negligible against Nightscout's actual request rate (§2.3), and NRG's
job is considerably richer than a hostname lookup: RBAC groups, weekly schedules, ORY
Kratos/Hydra identity verification, delegated authorization — none of which a `Map` lookup
can replace. The comparison is deliberately narrow (the resolution step alone) because
that is the specific piece §9.1 proposed folding into core.

**Does argue**: if host→tenant resolution is *only* "look up which tenant owns this
hostname" (the shared-process multitenant target's actual need, not NRG's full RBAC scope),
a sidecar round-trip is a measurable, avoidable tax relative to doing it in-process — small
per request, but multiplied by every request to every tenant, and it is exactly the kind of
"small, avoidable, cumulative" cost the doc's cost-per-tenant findings (§7.4) keep
surfacing elsewhere. Where NRG's richer RBAC/schedule/delegation features are actually
needed (§9.4 discusses this directly), the hop is justified by the functionality, not a
regression to be eliminated.
