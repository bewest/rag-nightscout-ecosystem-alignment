# Requirements

This document is an index of requirements organized by domain.

## Domain Files

- [Aid Algorithms](aid-algorithms-requirements.md) - 56 requirements (+3 OREF)
- [Cgm Sources](cgm-sources-requirements.md) - 18 requirements
- [Connectors](connectors-requirements.md) - 52 requirements (+4 BLE)
- [Nightscout Api](nightscout-api-requirements.md) - 57 requirements (+4 IDP)
- [Pumps](pumps-requirements.md) - 10 requirements
- [Sync Identity](sync-identity-requirements.md) - 74 requirements (+4 FOLLOW)
- [Treatments](treatments-requirements.md) - 35 requirements

Total: 310 requirements

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

### REQ-ALARM-* Coverage (Level 5 #28)

| Total | Covered | Uncovered | % |
|-------|---------|-----------|---|
| 10 | 10 | 0 | 100% |

**All covered** via `alarm-requirements.yaml`: REQ-ALARM-001 to REQ-ALARM-010

**Related gaps**: GAP-ALARM-001 (alarm config sync), GAP-ALARM-002 (predictive horizon)

### REQ-REMOTE-* Coverage (Level 5 #29)

| Total | Covered | Uncovered | % |
|-------|---------|-----------|---|
| 11 | 11 | 0 | 100% |

**All covered** via `remote-command-requirements.yaml`: REQ-REMOTE-001 to REQ-REMOTE-011

**Related gaps**: GAP-REMOTE-001 (override auth), GAP-REMOTE-002 (command signing), GAP-REMOTE-003 (key rotation)

### REQ-INTEROP-* Coverage (Level 5 #30)

| Total | Covered | Uncovered | % |
|-------|---------|-----------|---|
| 3 | 3 | 0 | 100% |

**All covered** via `interop-unit-requirements.yaml`: REQ-INTEROP-001 to REQ-INTEROP-003

**Related gaps**: GAP-SYNC-009 (timestamp format), GAP-TREAT-001 (eventType), GAP-SYNC-008 (device ID)

### REQ-UNIT-* Coverage (Level 5 #31)

| Total | Covered | Uncovered | % |
|-------|---------|-----------|---|
| 4 | 4 | 0 | 100% |

**All covered** via `interop-unit-requirements.yaml`: REQ-UNIT-001 to REQ-UNIT-004

**Related gaps**: GAP-TREAT-002 (duration units), GAP-TZ-004 (utcOffset units)

### REQ-ALG-* Coverage (Level 5 #32)

| Total | Covered | Uncovered | % |
|-------|---------|-----------|---|
| 56 | 22 | 34 | 39% |

**Partially covered** - Degraded operation, safety limits, insulin model, profile schema, prediction complete

**Traceability Matrix**: [`domain-matrices/aid-algorithms-matrix.md`](domain-matrices/aid-algorithms-matrix.md)

**Covered categories**:
- Degraded Operation (REQ-DEGRADE-001-006): ✅ 100% via `degraded-operation.yaml`
- Algorithm Core (REQ-ALG-003): ✅ 25% via `safety-limits.yaml`
- Insulin Model (REQ-INS-001-005): ✅ 100% via `safety-limits.yaml` + `insulin-model.yaml`
- Profile Schema (REQ-PROF-001-007): ✅ 100% via `profile-structure.yaml`
- Prediction (REQ-PRED-001-003): ✅ 100% via `prediction-requirements.yaml`

**Uncovered categories**:
- Carb Absorption (REQ-CARB-001-006): 0%
- Sensitivity/Dosing/Target: 0%

**Data quality issue**: Duplicate REQ IDs (REQ-CARB-001-003, REQ-INS-001-003)

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