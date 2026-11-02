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
