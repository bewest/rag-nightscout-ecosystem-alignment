# DRAFT — PR #8898 description update

## Summary

This draft adds an explicitly configured multitenant API preview over PostgreSQL/RLS,
Vault Transit and persisted current authorization. The default preview exposes API3
entries; prepared namespaces and explicit domain selection add the implemented
legacy v1/inherited-v2 handlers and API3 collection handlers for entries, treatments,
devicestatus, profile, food and settings, plus legacy activity.

This continuation adds actual v2 properties, ddata/as-of and summary handlers over
request-local tenant snapshots and shipping property calculations. It also adds
source-pinned synthetic NightscoutKit uploader/LoopFollow follower workflow replay
through the real executable, and independent current-authority/audience probes.
These tests replay extracted client patterns; they do not execute Swift clients.

## Review boundary

- Existing single/Mongo behavior and the global MongoDB-only backend registry remain.
- Only the explicit `nightscout multitenant api` preview runs. Owner/operator,
  evaluator, realtime and connector roles remain unavailable.
- Startup checks prepared catalogues and privileges read-only; it never migrates,
  provisions tenants or imports credentials implicitly.
- Properties/ddata retain shipping entries-and-treatments permission semantics,
  including the inherited secondary-domain snapshot surface; summary retains its
  wildcard read permission. This is compatibility acceptance, not a new policy.
- Current grants are checked for every protected operation; successful exchange
  never freezes authority in the JWT.
- Administration, notices/debug, notification receipts/egress and assistant routes
  remain incomplete. Full route/client coverage, import/resource bounds, production
  identity/trust, lifecycle, recovery and M0–M6 promotion remain open.

## Validation

Recorded on local `ded254b9acf5a94e3a4fd99c85b23e1413fa08b6` in the alignment
integration record R40: complete nonbrowser6926passing/80pending/0failing;
browser684/0/0; enabled focused138/0/0; separate migration/HTTP30/0/0.
These overlap. Archived authority and semantic source controls detect the exercised
isolation, current-grant, derived-value, retry/response and route-wiring failures;
restored acceptance passes. Pending/disabled labs remain incomplete. Changed-file
lint has0errors/9warnings and the494-file tier map passes. Fresh remote CI/CodeQL
must cover the published continuation before readiness is claimed.

## Companion records

- [Delivery dashboard](https://github.com/bewest/rag-nightscout-ecosystem-alignment/blob/main/docs/30-design/tenancy/multitenant-delivery-dashboard.md)
- [REST delivery plan](https://github.com/bewest/rag-nightscout-ecosystem-alignment/blob/main/docs/30-design/tenancy/multitenant-rest-api-delivery-plan-2026-11-04.md)
- [Release integration record](https://github.com/bewest/rag-nightscout-ecosystem-alignment/blob/main/docs/30-design/remedial/rc-16.0.0-integration-record.md)

The PR remains a draft for bounded implementation review. It is not merged,
released, full REST compatibility acceptance or production multitenant enablement.
