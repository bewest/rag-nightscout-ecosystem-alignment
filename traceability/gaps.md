# Gaps

This document is an index of gaps organized by domain.

## Domain Files

- [Aid Algorithms](aid-algorithms-gaps.md) - 61 gaps
- [Cgm Sources](cgm-sources-gaps.md) - 52 gaps
- [Connectors](connectors-gaps.md) - 40 gaps
- [Nightscout Api](nightscout-api-gaps.md) - 64 gaps
- [Pumps](pumps-gaps.md) - 9 gaps
- [Sync Identity](sync-identity-gaps.md) - 60 gaps
- [Treatments](treatments-gaps.md) - 25 gaps

## Quick Reference

| Domain | Gap Count | File | Last Verified |
|--------|-----------|------|---------------|
| nightscout-api | 67 | [nightscout-api-gaps.md](nightscout-api-gaps.md) | 2026-01-31 (GAP-IDP-001/002/003 added) |
| sync-identity | 68 | [sync-identity-gaps.md](sync-identity-gaps.md) | 2026-01-31 (GAP-FOLLOW-001/002, GAP-CAREGIVER-001/002 added) |
| aid-algorithms | 63 | [aid-algorithms-gaps.md](aid-algorithms-gaps.md) | 2026-01-31 (GAP-TRIO-SWIFT-001/002 added) |
| cgm-sources | 52 | [cgm-sources-gaps.md](cgm-sources-gaps.md) | 2026-01-29 |
| connectors | 46 | [connectors-gaps.md](connectors-gaps.md) | 2026-01-31 (GAP-TEST-004/005 added) |
| treatments | 25 | [treatments-gaps.md](treatments-gaps.md) | - |
| pumps | 9 | [pumps-gaps.md](pumps-gaps.md) | - |

Total: 330 gaps across 7 domains

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