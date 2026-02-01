# Orphan Artifact Priority Analysis

Generated: 2026-02-01
Source: Task #4 - Identify high-value orphan artifacts

## Summary

Analysis of 88 uncovered requirements (after cycle 84 conformance coverage) to identify high-value targets for linking or archival.

> **Note**: 11 REQs covered in cycle 84 (REQ-DS-002/003/004, REQ-PROF-002/003/004/006, REQ-NS-025, REQ-TZ-002, REQ-MIGRATION-002/003, REQ-INTEROP-003)

---

## Priority Tiers

### Tier 1: High Priority (Core Interoperability)

These requirements directly impact AID controller sync and data exchange.

| REQ ID | Title | Domain | Rationale |
|--------|-------|--------|-----------|
| REQ-SPEC-003 | Document Deduplication Algorithm | sync | Critical for preventing duplicate treatments |
| REQ-SPEC-004 | Define isValid Semantics | sync | Soft delete behavior varies across systems |
| REQ-PLUGIN-003 | Document IOB/COB Calculation Models | algorithm | Core to insulin dosing decisions |
| REQ-ALG-002 | Semantic Equivalence Assertions | algorithm | Validates algorithm parity across systems |
| REQ-ALG-003 | Safety Limit Validation | algorithm | Patient safety critical |
| REQ-NOCTURNE-002 | Cross-Implementation Algorithm Conformance | algorithm | Validates Nocturne oref1 implementation |
| REQ-CONNECT-006 | Formal Vendor Driver Interface | connector | Standardizes CGM/pump driver API |

**Recommended Action**: Link to existing mappings/specs or create targeted conformance assertions

---

### Tier 2: Medium Priority (Feature Completeness)

These requirements address documented gaps but aren't blocking interoperability.

| REQ ID | Title | Domain | Rationale |
|--------|-------|--------|-----------|
| REQ-AUTH-002 | Token Revocation Capability | auth | Security improvement |
| REQ-AUTH-003 | Document Role Requirements Per Endpoint | auth | API documentation |
| REQ-SDK-001 | v3 API Support | sdk | NightscoutKit modernization |
| REQ-SDK-002 | Multiple Authentication Methods | sdk | Client flexibility |
| REQ-SDK-003 | Incremental Sync | sdk | Efficiency improvement |
| REQ-FOLLOW-002 | Unified Remote Command Abstraction | follow | Remote bolus standardization |
| REQ-FOLLOW-003 | Portable Alarm Infrastructure | follow | Cross-app alarm sharing |
| REQ-BOLUS-002 | IOB Subtraction Transparency | bolus | User understanding |
| REQ-BOLUS-003 | Nightscout Wizard Sync | bolus | Feature parity |
| REQ-SENS-002 | Sensitivity Visibility in Nightscout | sensitivity | Autosens reporting |

**Recommended Action**: Add to future conformance expansion or SDK design docs

---

### Tier 3: Low Priority (Implementation-Specific)

These requirements are platform/implementation-specific or have limited ecosystem impact.

| REQ ID | Title | Domain | Rationale |
|--------|-------|--------|-----------|
| REQ-UI-002 | Chart Accessibility | ui | Platform-specific UI |
| REQ-UI-003 | Offline Data Access | ui | Client implementation detail |
| REQ-SPM-001 | SPM Adoption for Standalone Libraries | build | iOS build system |
| REQ-SPM-002 | LoopKit Bundle Resource Resolution | build | iOS build system |
| REQ-SPM-003 | Fork Consolidation via SPM | build | iOS build system |
| REQ-WATCH-002 | Display Live Glucose on Complications | watch | watchOS specific |
| REQ-WATCH-003 | Shared Complication Components | watch | watchOS specific |
| REQ-WIDGET-002 | Minimum Widget Family Support | widget | iOS specific |
| REQ-WIDGET-003 | Standardized Color Scheme | widget | UI design |
| REQ-HK-002 | Cross-App Source Detection | healthkit | iOS specific |
| REQ-HK-003 | Standardized Metadata Keys | healthkit | iOS specific |
| REQ-DIST-002 | Standardized Build Configuration | build | CI/CD specific |
| REQ-DIST-003 | Unified Build Documentation | build | Documentation |

**Recommended Action**: Leave as platform-specific, document in iOS backlog

---

### Tier 4: Alarm Domain (Cluster)

8 alarm-related requirements form a coherent cluster for future alarm standardization effort.

| REQ ID | Title | Priority |
|--------|-------|----------|
| REQ-ALARM-002 | Configurable Snooze Duration | Medium |
| REQ-ALARM-003 | Day/Night Schedule Support | Medium |
| REQ-ALARM-004 | Predictive Low Glucose Alarms | High |
| REQ-ALARM-005 | Persistent Threshold Requirement | Medium |
| REQ-ALARM-006 | Rate-of-Change Alarms | Medium |
| REQ-ALARM-007 | Missed Reading Detection | High |
| REQ-ALARM-008 | Loop Status Alerting | Medium |
| REQ-ALARM-009 | Alarm Priority Ordering | Low |

**Recommended Action**: Create dedicated alarm conformance scenario file

---

### Tier 5: Pump/BLE Domain (Cluster)

6 pump-related requirements for future pump communication standardization.

| REQ ID | Title | Priority |
|--------|-------|----------|
| REQ-PUMP-002 | Command Acknowledgment Verification | High |
| REQ-PUMP-003 | Bolus Progress Reporting | Medium |
| REQ-PUMP-004 | History Reconciliation | High |
| REQ-PUMP-005 | Clock Drift Handling | Medium |
| REQ-PUMP-008 | BLE Session Establishment Security | High |
| REQ-PUMP-009 | CRC Validation for Pump Messages | Medium |

**Recommended Action**: Create dedicated pump conformance scenario file

---

### Tier 6: External Integration (Cluster)

External service integrations that depend on third-party APIs.

| REQ ID | Title | Service |
|--------|-------|---------|
| REQ-TIDEPOOL-001 | iOS CGM App Tidepool Integration | Tidepool |
| REQ-TIDEPOOL-002 | OAuth2 Authentication for Android | Tidepool |
| REQ-TIDEPOOL-003 | Nightscout Tidepool Connector | Tidepool |
| REQ-TIDEPOOL-004 | Dosing Decision Parity | Tidepool |
| REQ-TCONNECT-002 | Control-IQ Algorithm Data Export | Tandem |
| REQ-TCONNECT-003 | Batch Sync Documentation | Tandem |
| REQ-TCONNECT-004 | Trend Direction Handling | Tandem |
| REQ-SHARE-002 | Gap Detection and Backfill | Dexcom |
| REQ-SHARE-003 | Configurable Application ID | Dexcom |
| REQ-LIBRELINK-002 | Historical Backfill Support | Abbott |
| REQ-LIBRELINK-003 | Trend Arrow Mapping Documentation | Abbott |

**Recommended Action**: Document in integration inventories (already partially complete)

---

## Action Items

### Immediate (Next 3 Cycles)

1. **Create alarm-assertions.yaml** - Cover 8 REQ-ALARM-* requirements
2. **Create pump-assertions.yaml** - Cover 6 REQ-PUMP-* requirements
3. **Link REQ-SPEC-003/004** to existing deduplication documentation

### Near-Term (Next 10 Cycles)

4. **Link Tier 1 requirements** to existing specs/mappings where documentation exists
5. **Add SDK requirements** to NightscoutKit design document
6. **Update integration inventories** with Tier 6 requirements

### Archive Candidates

None recommended - all requirements have value for future reference.

---

## Metrics

| Category | Count | Percentage |
|----------|-------|------------|
| Tier 1 (High Priority) | 7 | 8% |
| Tier 2 (Medium Priority) | 10 | 11% |
| Tier 3 (Low Priority) | 13 | 15% |
| Tier 4 (Alarm Cluster) | 8 | 9% |
| Tier 5 (Pump Cluster) | 6 | 7% |
| Tier 6 (External) | 11 | 13% |
| Already Covered (Cycle 84) | 11 | 13% |
| Other | 22 | 25% |
| **Total Analyzed** | 88 | 100% |

---

## Cross-References

- [coverage-analysis.md](coverage-analysis.md) - Full coverage report
- [conformance/assertions/](../conformance/assertions/) - Existing assertion files
- [requirements.md](requirements.md) - Requirements index
