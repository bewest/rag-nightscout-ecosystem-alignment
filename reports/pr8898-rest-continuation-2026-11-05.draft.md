# DRAFT — PR #8898 REST continuation description (2026-11-05)

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

The local continuation adds a dormant persisted subject update/delete and known-role
assignment service with separately authorized writer privileges, atomic metadata/role
updates and redacted audit. No management HTTP route or owner policy is enabled.
Strict mixed-version treatment tests cover edits, null/omitted fields, retries,
conditionals, replacement and delete/history; rename tests preserve shipping
raw/JWT versus full-token-hash behavior.

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

Recorded on local `94c57f1f37370215ef25b69691ef63918c876db3`, alignment R41:
complete nonbrowser 6944 passing / 80 pending / 0 failing; browser 684 / 0 / 0;
enabled focused 162 / 0 / 0; migration/HTTP 30 / 0 / 0; affected authority upgrade
8 / 0 / 0; archived subject gate 13 / 0 / 0. These groups overlap. Subject
current-grants/tenant/atomic and compatibility metadata/conditional/refusal controls
fail meaningfully; restored focused acceptance passes. Changed-file lint and
496-file / 8-tier classification pass; final prcheck contains current dev.

A separate repeated bounded 15.0.9/dev/published-PR-single matrix is pinned to
`ded254b9`, not this new join. It records no dev/PR-single semantic differences
within its corpus; omitted identity/settings families and historical projection
residuals remain explicit. It establishes no old-release-to-PG transitivity.
Client binaries, full route coverage and operations remain unmeasured/incomplete.

CodeQL analysis succeeded on the earlier published head; production alerts 147
and 148 remain open. No dismissal or new remote CI result is claimed. Fresh CI
must cover this continuation after maintainer publication.

## Companion records

- [Delivery dashboard](https://github.com/bewest/rag-nightscout-ecosystem-alignment/blob/main/docs/30-design/tenancy/multitenant-delivery-dashboard.md)
- [REST delivery plan](https://github.com/bewest/rag-nightscout-ecosystem-alignment/blob/main/docs/30-design/tenancy/multitenant-rest-api-delivery-plan-2026-11-04.md)
- [Release integration record](https://github.com/bewest/rag-nightscout-ecosystem-alignment/blob/main/docs/30-design/remedial/rc-16.0.0-integration-record.md)

The PR remains a draft for bounded implementation review. It is not merged,
released, full REST compatibility acceptance or production multitenant enablement.
