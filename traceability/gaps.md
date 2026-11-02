# Gaps

This document is an index of gaps organized by domain.

## Hosted-tenancy integration follow-up (2026-11-02)

The maintainer's [delivery roadmap](../docs/30-design/tenancy/multitenant-delivery-roadmap-2026-11-02.md)
removes Celld from scope and adopts storage-first/current-dev integration,
headless owner API with UI deferred, operator-only provisioning, legacy
per-tenant credentials and a reviewed settings subset. Early Vault feasibility
supports the existing secrets decision; a cryptographic API is not the complete
tenant secret store. Human identity and durable runtime/next-gen execution are
separate workstreams, not prerequisites to a synthetic storage proof.

**Measured continuation:** current-connection PgBouncer/DDL isolation now has
9 passing checks and actual RLS/binding/privileged-role controls. M1 preflight
exposes a historical-DDL identity gap: ObjectId/string twins collapse under
ordinary JSON encoding. Local upstream `6b1bf889` and the opt-in generated
typed-key candidate pass 4 narrow identity checks; the complete adapter,
current v3/partial-unique indexes, import fidelity and migration runner remain
open. See the roadmap and `tools/lab/postgres-foundation/results.json`.
No new protocol GAP IDs or hosted acceptance are claimed.

Current-state revocation enforcement is now an explicit control-plane/runtime
gap: the next protected operation must not accept a revoked grant from an
unexpired JWT or stale worker cache, and unavailable authorization state must
fail closed. The selected guarantee still needs cross-worker/socket race and
outage acceptance; it is not supplied by the PG storage proofs.

MIG-RUNNER now has a local PostgreSQL-only operator-command foundation
(`68828b8d`): 39 migration/CLI checks pass, including 12 disposable-PG checks.
Atomic SQL/ledger, locking and read-only inspection are measured; standalone
MongoDB lease/fencing/resumability, production catalogues/baselines, catalogue
authenticity and serving-role wiring remain gaps. This does not close the
two-store runner or authorize default boot migrations.

ST-PG now also has a dormant read/filter subset (`7d4f3872`) with 6 real
PG/MongoDB differential and 4 refusal/parameterization checks, included in a
145-passing combined regression. `findFiltered`, `count` and `findOne` are
measured only for the supported subset. Regex/v1/projection/dotted-path and
array-sort compatibility, bounded/cursor reads, remaining methods, writes/
events, indexes/identifier retry and actual backend registration remain open.

Local upstream `7bcfc8b0` subsequently adds a dormant five-method persistence
write subset: scalar inserts/patches and deletes. Eight real PG/MongoDB checks
and one refusal check pass within a 158-test regression. Actual lock contention
exposed and now guards a stale-snapshot no-op bug; identity-kind and no-op-count
mutations also fail. Full M1 still owes bulk/replace/every-form writes,
constraint-specific retry/error mapping, source/validation/commit-event
integration, reviewed DDL and bounded resource/query/backend acceptance.
Migrations, settings/subject policy and secrets belong to the parallel session.

Integration `6943dccb` incorporates the parallel provider-neutral/Vault
component, PG ciphertext/audit and maintenance rewrap/CAS commits. The merged
tree passes 230 focused tests with no pending; 465 files classify. Backup/
restore, actual process-crash acceptance, consumer credential cutover,
minimum owner policy APIs, MongoDB runner and serving-role wiring remain open.
Unit/DOM/core/harness tiers pass after building local bundles, but the
dependency tier still fails an unchanged assertion using ancestor-installed
AJV 6.12.6. No full-suite or production/backend acceptance is inferred.

The [multitenancy priorities assessment](../docs/10-domain/nightscout-multitenancy-priorities-deep-dive.md)
maps existing ST-PG, TEN-RESOLVE, T30-WIRING and TEN-LAB planning gaps to current
dev `61eb3733`. The storage harness and scope are merged; the PostgreSQL adapter,
hosted bootstrap and runtime bindings are not. Existing PG/pooler/config labs
are valuable dated evidence, not current-dev integration acceptance.

The initial assessment found ST-PG, TEN-RESOLVE and TEN-LAB only on the platform
map; the adopted roadmap has now added queue items and bounded PG/Vault gates.
Full adapter/config/runtime acceptance remains open. Do not make an obsolete
whole-seam refresh a prerequisite. Celld was evaluated, not adopted, and is now
out of scope. Reuse the existing work identifiers; no duplicate protocol GAP IDs
or new v16 blockers are added.

## Tenant-cell SQLite experiment follow-up (2026-11-02)

The [separate SQLite feasibility track](../docs/10-domain/tenant-cell-sqlite-deep-dive.md)
demonstrates local tenant-owned storage on celld, not a supported third NS
backend. Twelve local checks and a broken-routing control pass; no actual NS
adapter, fleet/bucket experiment or matched MongoDB/PG comparison ran.
The remaining gaps are runtime/adapter integration, full storage semantics,
host-loss/fencing/recovery, plugin/socket isolation, schema/restore lifecycle
and measured economics. Receipts also need bounded retention before production.

These checks do not close existing ST-PG/TEN-LAB acceptance, alter a delivery
roadmap or introduce duplicate protocol GAP IDs. An SQL diagnostic initially
failed because the runtime forbids `sqlite_version()`; the final lab uses
`sql.databaseSize`, without claiming the embedded SQLite version was measured.

The comparative report now separates database-per-tenant MongoDB from shared
MongoDB, shared PG/RLS and cell/SQLite. Historical PG adapter/pooler evidence and
the November PG transaction-foundation record do not supply a current matched
benchmark. Open decision gaps include the storage-only versus whole-runtime
boundary, durable evaluator delivery, per-cell schema/restore tools, privileged
fleet blast radius and the ongoing three-backend contract-test burden.
Four diagrams explain those boundaries; they are not experiment acceptance or
an amendment of the adopted PG delivery stream.

## Release-readiness follow-up (2026-11-02)

The [current v16 ecosystem/acceptance record](../docs/10-domain/nightscout-v16-ecosystem-deep-dive.md)
supersedes the November 1 operational status without adding duplicate protocol
GAP IDs. Public CI is green on `61eb3733`; private security integration,
final-tree validation, live notification evidence and cohort/rollback acceptance
remain open. Cohort testing has started (maintainer-reported over 24-48 hours);
its version-pinned outcomes have not yet been collected here.

The absent MongoDB 4.4 check has been removed from master protection. The two
remaining required lanes are present and green; review and the decided aggregate
check policy remain release-stewardship work. For
nightscout/cgm-remote-monitor#8829, the reporter reports persistence on dev,
but neither maintainer reproduced it and many DIY and production/service
environments work (maintainer report). The maintainer explicitly dispositions it
**nonblocking** for v16. `RT-16-TOKEN-8829` tracks the bounded environment
comparison/reproducer, not a release prerequisite or confirmed root cause.
Scheduled storage/identity and frontend modernization are merged, not open
implementation gaps. No elapsed soak time or metadata survey closes a gap.

The maintainer reports prior testing of contributed patches and high confidence;
missing per-cohort rows are record-reconciliation work, not evidence of untested
patches. This session clarifies compatibility then reconciles acceptance; private
security, live operations/cohorts, candidate review and #8829 follow-up are
assigned to other sessions. No new universal-compatibility requirement or release
blocker is invented from the source-shape catalogue's limits.

## Domain Files

- [Aid Algorithms](aid-algorithms-gaps.md) - 66 gaps
- [Cgm Sources](cgm-sources-gaps.md) - 53 gaps
- [Connectors](connectors-gaps.md) - 71 gaps
- [Nightscout Api](nightscout-api-gaps.md) - 74 gaps
- [Pumps](pumps-gaps.md) - 10 gaps
- [Sync Identity](sync-identity-gaps.md) - 71 gaps
- [Telemetry and Observability](telemetry-observability-gaps.md) - 5 gaps
- [Treatments](treatments-gaps.md) - 29 gaps

## Quick Reference

| Domain | Gap Count | File | Last Verified |
|--------|-----------|------|---------------|
| nightscout-api | 78 | [nightscout-api-gaps.md](nightscout-api-gaps.md) | 2026-04-10 |
| sync-identity | 71 | [sync-identity-gaps.md](sync-identity-gaps.md) | 2026-02-01 |
| aid-algorithms | 71 | [aid-algorithms-gaps.md](aid-algorithms-gaps.md) | 2026-02-08 |
| connectors | 71 | [connectors-gaps.md](connectors-gaps.md) | 2026-07-07 |
| cgm-sources | 53 | [cgm-sources-gaps.md](cgm-sources-gaps.md) | 2026-07-16 |
| treatments | 29 | [treatments-gaps.md](treatments-gaps.md) | 2026-03-10 |
| pumps | 13 | [pumps-gaps.md](pumps-gaps.md) | 2026-02-03 |
| telemetry-observability | 5 | [telemetry-observability-gaps.md](telemetry-observability-gaps.md) | 2026-07-16 |

Total: 386 unique GAP IDs reported by `python tools/find_gap_duplicates.py` after adding GAP-REMOTE-010 on 2026-09-26 (384 after GAP-CGM-035 on 2026-07-16). The treatments count is the number of `### GAP-` headings in treatments-gaps.md on 2026-09-26. The quick-reference table remains a human-maintained domain index.

## Duplicate Resolution (2026-02-01)

All 10 duplicate GAP IDs have been renumbered:

| Original ID | New ID | File | Reason |
|-------------|--------|------|--------|
| GAP-BLE-001..005 | GAP-G7-001..005 | cgm-sources-gaps.md | G7 protocol specific |
| GAP-BRIDGE-001..003 | GAP-CGM-NODE-001..003 | cgm-sources-gaps.md | CGM bridge Node.js issues |
| GAP-OREF-001..003 (Trio) | GAP-TRIO-001..003 | aid-algorithms-gaps.md | Trio-specific gaps |
| GAP-OREF-001..003 (Nocturne) | GAP-NOCTURNE-010..012 | sync-identity-gaps.md | Nocturne-specific gaps |

**Verification**: `python tools/find_gap_duplicates.py` → 0 duplicates

## Verification Status

| Date | Domain | Gaps Verified | Result |
|------|--------|---------------|--------|
| 2026-01-29 | cgm-sources | GAP-BLE-001, GAP-BLE-002 | Still open (J-PAKE, certs undocumented) |
| 2026-01-29 | aid-algorithms | GAP-ALG-001/002/003, GAP-CARB-001 | 100% accurate (7 claims verified) |
| 2026-01-29 | nightscout-api | GAP-API-001/002/003/004/005 | 100% accurate (6 claims verified) |
| 2026-01-29 | sync-identity | GAP-SYNC-001/002/005/006/007, GAP-TZ-* | 100% accurate (9 claims verified) |
| 2026-01-29 | treatments | GAP-OVERRIDE-*, GAP-REMOTE-*, GAP-TREAT-* | 100% accurate (11 claims verified) |
| 2026-01-29 | connectors | GAP-CONNECT-*, GAP-SHARE-*, GAP-LIBRELINK-*, etc | 100% accurate (8 claims verified) |
| 2026-01-29 | aid-algorithms | Algorithm comparison claims | 100% accurate (7 claims verified) |
| 2026-01-29 | cgm-sources | CGM data sources deep dive | 100% accurate (8 claims verified) |
| 2026-01-29 | cgm-sources | Libre protocol deep dive | 100% accurate (7 claims verified) |
| 2026-01-29 | pumps | Pump communication deep dive | 100% accurate (8 claims verified) |
| 2026-01-29 | nightscout-api | DeviceStatus deep dive | 100% accurate (8 claims verified) |
| 2026-01-29 | nightscout-api | Entries deep dive | 100% accurate (8 claims verified) |
| 2026-01-29 | nightscout-api | Treatments deep dive | 100% accurate (8 claims verified) |
| 2026-06-17 | Trio / Loop / Nightscout active docs | Trio Nightscout sync, Loop safety, Nightscout auth claims | Updated stale Trio/Loop claims; Nightscout auth identity claims still accurate |

## Mapping Verification Status

| Date | Mapping | Result | Impact on Gaps |
|------|---------|--------|----------------|
| 2026-01-29 | xdrip-android/nightscout-sync.md | 100% accurate | No gap changes needed |
| 2026-01-29 | aaps/nsclient-schema.md | 100% accurate | No gap changes needed |
| 2026-01-29 | loop/sync-identity-fields.md | 100% accurate | No gap changes needed |
| 2026-01-29 | trio/nightscout-sync.md | 100% accurate | No gap changes needed |
| 2026-01-29 | terminology-matrix.md (10% sample) | 100% accurate | No gap changes needed |
| 2026-06-17 | trio/nightscout-sync.md, loop/safety.md, terminology-matrix.md | Trio and Loop claims refreshed against current source | No new gaps; corrected stale terminology and client-behavior notes |

*Last updated: 2026-07-16*
