# Gaps

This document is an index of gaps organized by domain.

## Domain Files

- [Aid Algorithms](aid-algorithms-gaps.md) - 66 gaps
- [Cgm Sources](cgm-sources-gaps.md) - 52 gaps
- [Connectors](connectors-gaps.md) - 68 gaps
- [Nightscout Api](nightscout-api-gaps.md) - 74 gaps
- [Pumps](pumps-gaps.md) - 10 gaps
- [Sync Identity](sync-identity-gaps.md) - 71 gaps
- [Treatments](treatments-gaps.md) - 25 gaps

## Quick Reference

| Domain | Gap Count | File | Last Verified |
|--------|-----------|------|---------------|
| nightscout-api | 74 | [nightscout-api-gaps.md](nightscout-api-gaps.md) | 2026-02-01 |
| sync-identity | 71 | [sync-identity-gaps.md](sync-identity-gaps.md) | 2026-02-01 |
| connectors | 68 | [connectors-gaps.md](connectors-gaps.md) | 2026-02-01 |
| aid-algorithms | 66 | [aid-algorithms-gaps.md](aid-algorithms-gaps.md) | 2026-02-01 |
| cgm-sources | 52 | [cgm-sources-gaps.md](cgm-sources-gaps.md) | 2026-02-01 |
| treatments | 25 | [treatments-gaps.md](treatments-gaps.md) | 2026-02-01 |
| pumps | 10 | [pumps-gaps.md](pumps-gaps.md) | 2026-02-01 |

Total: 366 gaps across 7 domains (335 unique IDs, 10 duplicate ID groups requiring renumbering)

## Duplicate IDs (2026-02-01 Audit)

10 GAP IDs are used in multiple files with different meanings. These require renumbering:

| Duplicate ID | Locations | Resolution Needed |
|--------------|-----------|-------------------|
| GAP-BLE-001 | connectors-gaps.md, cgm-sources-gaps.md | Renumber one |
| GAP-BLE-002 | connectors-gaps.md, cgm-sources-gaps.md | Renumber one |
| GAP-BLE-003 | connectors-gaps.md, cgm-sources-gaps.md | Renumber one |
| GAP-BLE-004 | connectors-gaps.md, cgm-sources-gaps.md | Renumber one |
| GAP-BLE-005 | connectors-gaps.md, cgm-sources-gaps.md | Renumber one |
| GAP-BRIDGE-001 | connectors-gaps.md, cgm-sources-gaps.md | Renumber one |
| GAP-BRIDGE-002 | connectors-gaps.md, cgm-sources-gaps.md | Renumber one |
| GAP-OREF-001 | aid-algorithms-gaps.md (×2), sync-identity-gaps.md | Consolidate or renumber |
| GAP-OREF-002 | aid-algorithms-gaps.md (×2), sync-identity-gaps.md | Consolidate or renumber |
| GAP-OREF-003 | aid-algorithms-gaps.md (×2), sync-identity-gaps.md | Consolidate or renumber |

**Recommendation**: cgm-sources GAP-BLE-* and GAP-BRIDGE-* should be renumbered to GAP-CGM-BLE-* and GAP-CGM-BRIDGE-* to avoid collision with connectors domain.

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

## Mapping Verification Status

| Date | Mapping | Result | Impact on Gaps |
|------|---------|--------|----------------|
| 2026-01-29 | xdrip-android/nightscout-sync.md | 100% accurate | No gap changes needed |
| 2026-01-29 | aaps/nsclient-schema.md | 100% accurate | No gap changes needed |
| 2026-01-29 | loop/sync-identity-fields.md | 100% accurate | No gap changes needed |
| 2026-01-29 | trio/nightscout-sync.md | 100% accurate | No gap changes needed |
| 2026-01-29 | terminology-matrix.md (10% sample) | 100% accurate | No gap changes needed |

*Last updated: 2026-01-29*