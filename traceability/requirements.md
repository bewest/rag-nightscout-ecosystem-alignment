# Requirements

This document is an index of requirements organized by domain.

## Domain Files

- [Aid Algorithms](aid-algorithms-requirements.md) - 25 requirements
- [Cgm Sources](cgm-sources-requirements.md) - 18 requirements
- [Connectors](connectors-requirements.md) - 28 requirements
- [Nightscout Api](nightscout-api-requirements.md) - 35 requirements
- [Pumps](pumps-requirements.md) - 10 requirements
- [Sync Identity](sync-identity-requirements.md) - 34 requirements
- [Treatments](treatments-requirements.md) - 35 requirements

Total: 185 requirements (180 unique)

## Coverage Status

| Metric | Value | Date |
|--------|-------|------|
| Requirements with scenarios | 27/180 | 2026-01-29 |
| Orphaned assertions | 0 | 2026-01-29 |
| Requirement coverage | 15% | 2026-01-29 |

**Source**: `python tools/verify_assertions.py`

## Mapping Verification (Supporting Evidence)

| Date | Mapping Verified | Requirements Supported |
|------|------------------|------------------------|
| 2026-01-29 | xdrip-android/nightscout-sync.md | REQ-020 (sync identity), REQ-050 (CGM upload) |
| 2026-01-29 | aaps/nsclient-schema.md | REQ-030 (field validation), REQ-010 (timestamp) |
| 2026-01-29 | loop/sync-identity-fields.md | REQ-020-025 (sync identity, ObjectIdCache) |
| 2026-01-29 | trio/nightscout-sync.md | REQ-030 (field validation), REQ-060 (algorithm) |
| 2026-01-29 | terminology-matrix.md (10% sample) | Cross-domain terminology accuracy |

## Deep Dive Verification (Supporting Evidence)

| Date | Deep Dive | Requirements Supported |
|------|-----------|------------------------|
| 2026-01-29 | algorithm-comparison-deep-dive.md | REQ-060-069 (algorithm behavior) |
| 2026-01-29 | g7-protocol-specification.md | REQ-050-059 (CGM data source) |
| 2026-01-29 | cgm-data-sources-deep-dive.md | REQ-050-059 (CGM data source) |
| 2026-01-29 | devicestatus-deep-dive.md | REQ-030 (field validation), REQ-010 (timestamp) |
| 2026-01-29 | entries-deep-dive.md | REQ-050-059 (CGM data source), REQ-030 (field validation) |
| 2026-01-29 | treatments-deep-dive.md | REQ-TREAT (treatments), REQ-020 (sync identity) |

**Level 2 Complete**: 5/5 mapping verifications passed (100%)
**Level 3 Progress**: 6/8 deep dive verifications (75%)

*Last updated: 2026-01-29*