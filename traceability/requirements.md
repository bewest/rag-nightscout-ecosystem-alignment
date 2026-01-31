# Requirements

This document is an index of requirements organized by domain.

## Domain Files

- [Aid Algorithms](aid-algorithms-requirements.md) - 53 requirements
- [Cgm Sources](cgm-sources-requirements.md) - 18 requirements
- [Connectors](connectors-requirements.md) - 46 requirements
- [Nightscout Api](nightscout-api-requirements.md) - 53 requirements (+3 IDP)
- [Pumps](pumps-requirements.md) - 10 requirements
- [Sync Identity](sync-identity-requirements.md) - 67 requirements
- [Treatments](treatments-requirements.md) - 35 requirements

Total: 278 requirements

## Coverage Status

| Metric | Value | Date |
|--------|-------|------|
| Requirements with scenarios | 27/184 | 2026-01-29 |
| Orphaned assertions | 0 | 2026-01-29 |
| Requirement coverage | 14.7% | 2026-01-29 |

**Source**: `python tools/verify_assertions.py`

### REQ-SYNC-* Coverage (Level 5 #24)

| Total | Covered | Uncovered | % |
|-------|---------|-----------|---|
| 18 | 15 | 3 | 83% |

**Uncovered**: REQ-SYNC-001 (WebSocket docs), REQ-SYNC-002 (v1/v3 identity), REQ-SYNC-003 (status response)

### REQ-TREAT-* Coverage (Level 5 #25)

| Total | Covered | Uncovered | % |
|-------|---------|-----------|---|
| 7 | 7 | 0 | 100% |

**All covered** via `treatment-sync.yaml`: REQ-TREAT-040 to REQ-TREAT-046

**Related gaps**: REQ-REMOTE-* (0%), REQ-ALARM-* (0%), REQ-UNIT-* (0%)

### REQ-CONNECT-* Completeness (Level 5 #26)

| Total GAPs | GAPs with REQs | Orphaned | % |
|------------|----------------|----------|---|
| 28 | 28 | 0 | 100% |

**Perfect 1:1 mapping**: All 8 connector categories have corresponding requirements

### REQ-API-* OpenAPI Alignment (Level 5 #27) - **LEVEL 5 COMPLETE**

| Total | With Spec | No Spec | Out of Scope | % |
|-------|-----------|---------|--------------|---|
| 35 | 22 | 10 | 3 | 63% |

**Gaps**: REQ-STATS-* (5), REQ-AUTH-* (3), REQ-RG-* (4) need OpenAPI specs

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
| 2026-01-29 | libre-protocol-deep-dive.md | REQ-050-059 (CGM data source), REQ-030 (field validation) |
| 2026-01-29 | pump-communication-deep-dive.md | REQ-PUMP (pump protocols), REQ-030 (field validation) |
| 2026-01-29 | nightscout-devicestatus-schema-audit.md | REQ-DS-001-004 (devicestatus schema) |
| 2026-01-29 | profile-schema-alignment.md | REQ-PROF-001-004 (profile schema) |
| 2026-01-29 | bolus-wizard-formula-comparison.md | REQ-BOLUS-001-003 (bolus wizard) |
| 2026-01-29 | autosens-dynamic-isf-comparison.md | REQ-SENS-001-003 (sensitivity) |
| 2026-01-29 | carb-absorption-model-comparison.md | REQ-CARB-001-003 (carb absorption) |
| 2026-01-30 | prediction-curve-documentation.md | REQ-PRED-001-003 (predictions) |
| 2026-01-30 | temp-basal-vs-smb-comparison.md | REQ-DOSE-001-003 (dosing) |

**Level 2 Complete**: 5/5 mapping verifications passed (100%)
**Level 3 Complete**: 8/8 deep dive verifications (100%) ✅

*Last updated: 2026-01-29*