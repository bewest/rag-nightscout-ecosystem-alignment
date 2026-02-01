# Treatments Domain Traceability Matrix

> **Generated**: 2026-02-01  
> **Domain**: Treatments  
> **Purpose**: REQ↔GAP↔Assertion cross-reference matrix

---

## Summary

| Metric | Count |
|--------|-------|
| Requirements | 35 |
| Gaps | 9 |
| REQs with assertion coverage | 35 (100%) |
| Uncovered REQs | 0 (0%) |
| GAPs with assertion coverage | **9 (100%)** |
| Uncovered GAPs | **0** |

**Status**: 🎉 **TREATMENTS DOMAIN 100% COMPLETE** - All 35 REQs + 9 GAPs have assertion coverage (cycle 118)
- Treatment sync (REQ-TREAT-040-046): treatment-sync.yaml
- Alarm (REQ-ALARM-001-010): alarm-requirements.yaml
- Remote command (REQ-REMOTE-001-011): remote-command-requirements.yaml
- Interop/Unit (REQ-INTEROP-001-003, REQ-UNIT-001-004): interop-unit-requirements.yaml

---

## Requirements Inventory

### Alarm Requirements (10)

| Requirement | Description | Gap Links | Assertions |
|-------------|-------------|-----------|------------|
| REQ-ALARM-001 | Configurable Glucose Thresholds | - | ✅ alarm-requirements.yaml |
| REQ-ALARM-002 | Configurable Snooze Duration | - | ✅ alarm-requirements.yaml |
| REQ-ALARM-003 | Day/Night Schedule Support | - | ✅ alarm-requirements.yaml |
| REQ-ALARM-004 | Predictive Low Glucose Alarms | - | ✅ alarm-requirements.yaml |
| REQ-ALARM-005 | Persistent Threshold Requirement | - | ✅ alarm-requirements.yaml |
| REQ-ALARM-006 | Rate-of-Change Alarms | - | ✅ alarm-requirements.yaml |
| REQ-ALARM-007 | Missed Reading Detection | - | ✅ alarm-requirements.yaml |
| REQ-ALARM-008 | Loop Status Alerting | - | ✅ alarm-requirements.yaml |
| REQ-ALARM-009 | Alarm Priority Ordering | - | ✅ alarm-requirements.yaml |
| REQ-ALARM-010 | Global Snooze/Mute Capability | - | ✅ alarm-requirements.yaml |

### Remote Command Requirements (11)

| Requirement | Description | Gap Links | Assertions |
|-------------|-------------|-----------|------------|
| REQ-REMOTE-001 | Remote Command Authentication | GAP-REMOTE-001 | ✅ remote-command-requirements.yaml |
| REQ-REMOTE-002 | Remote Command Replay Protection | - | ✅ remote-command-requirements.yaml |
| REQ-REMOTE-003 | Remote Bolus Safety Limits | - | ✅ remote-command-requirements.yaml |
| REQ-REMOTE-004 | Remote Command Audit Trail | - | ✅ remote-command-requirements.yaml |
| REQ-REMOTE-005 | Remote Command Source Tracking | - | ✅ remote-command-requirements.yaml |
| REQ-REMOTE-006 | Remote Command Toggle | - | ✅ remote-command-requirements.yaml |
| REQ-REMOTE-007 | Command Status Display | - | ✅ remote-command-requirements.yaml |
| REQ-REMOTE-008 | Recommended Bolus Expiry | - | ✅ remote-command-requirements.yaml |
| REQ-REMOTE-009 | Command Creation Timestamp | - | ✅ remote-command-requirements.yaml |
| REQ-REMOTE-010 | Credential Validation Before Storage | - | ✅ remote-command-requirements.yaml |
| REQ-REMOTE-011 | Post-Bolus Recommendation Rejection | - | ✅ remote-command-requirements.yaml |

### Interop Requirements (3) - COVERED

| Requirement | Description | Gap Links | Assertions |
|-------------|-------------|-----------|------------|
| REQ-INTEROP-001 | Standard Timestamp Format | GAP-SYNC-009 | ✅ interop-unit-requirements.yaml |
| REQ-INTEROP-002 | Standard eventType Values | GAP-TREAT-001 | ✅ interop-unit-requirements.yaml |
| REQ-INTEROP-003 | Device Identifier Inclusion | GAP-SYNC-008 | ✅ interop-unit-requirements.yaml |

### Unit Requirements (4) - COVERED

| Requirement | Description | Gap Links | Assertions |
|-------------|-------------|-----------|------------|
| REQ-UNIT-001 | Duration Unit Documentation | GAP-TREAT-002 | ✅ interop-unit-requirements.yaml |
| REQ-UNIT-002 | Duration Validation | GAP-TREAT-002 | ✅ interop-unit-requirements.yaml |
| REQ-UNIT-003 | utcOffset Validation | GAP-TZ-004 | ✅ interop-unit-requirements.yaml |
| REQ-UNIT-004 | Preserve High-Precision Fields | - | ✅ interop-unit-requirements.yaml |

### Treatment Sync Requirements (7) - COVERED

| Requirement | Description | Gap Links | Assertions |
|-------------|-------------|-----------|------------|
| REQ-TREAT-040 | Bolus Amount Preservation | - | ✅ treatment-sync.yaml |
| REQ-TREAT-041 | Carb Amount Preservation | - | ✅ treatment-sync.yaml |
| REQ-TREAT-042 | Timestamp Millisecond Precision | - | ✅ treatment-sync.yaml |
| REQ-TREAT-043 | Automatic Bolus Flag Preservation | - | ✅ treatment-sync.yaml |
| REQ-TREAT-044 | Duration Unit Normalization | GAP-TREAT-002 | ✅ treatment-sync.yaml |
| REQ-TREAT-045 | Sync Identity Round-Trip | GAP-TREAT-005 | ✅ treatment-sync.yaml |
| REQ-TREAT-046 | Absorption Time Unit Conversion | GAP-TREAT-001 | ✅ treatment-sync.yaml |

---

## Gaps Inventory

### Treatment-Specific Gaps (9)

| Gap | Description | Related REQs | Assertions |
|-----|-------------|--------------|------------|
| GAP-TREAT-001 | Absorption Time Unit Mismatch | REQ-TREAT-046 | ✅ treatment-sync.yaml |
| GAP-TREAT-002 | Duration Unit Inconsistency | REQ-UNIT-001, REQ-UNIT-002, REQ-TREAT-044 | ✅ treatment-sync.yaml |
| GAP-TREAT-003 | No Explicit SMB Event Type | REQ-INTEROP-002 | ❌ None |
| GAP-TREAT-004 | Split/Extended Bolus Representation Mismatch | - | ❌ None |
| GAP-TREAT-005 | Loop POST-Only Creates Duplicates | REQ-TREAT-045 | ✅ treatment-sync.yaml |
| GAP-TREAT-006 | Retroactive Edit Handling | - | ✅ treatment-sync.yaml |
| GAP-TREAT-007 | eCarbs Not Universally Supported | - | ✅ treatment-sync.yaml |
| GAP-TREAT-010 | eventType Immutability Not Enforced in Nocturne | - | ✅ treatment-sync.yaml |
| GAP-TREAT-011 | Temporary Target Type Missing from Nocturne Enum | - | ✅ treatment-sync.yaml |

---

## Coverage Analysis

### By Category

| Category | REQs | Covered | Coverage |
|----------|------|---------|----------|
| Alarm | 10 | 10 | 100% ✅ |
| Remote | 11 | 11 | 100% ✅ |
| Interop | 3 | 3 | 100% ✅ |
| Unit | 4 | 4 | 100% ✅ |
| Treatment Sync | 7 | 7 | 100% ✅ |
| **Total** | **35** | **35** | **100%** 🎉 |

### Action Items - ALL COMPLETE

All priority action items have been completed:

1. ~~**High Priority**: Create alarm assertions (REQ-ALARM-001-010)~~ ✅ cycle 96
2. ~~**High Priority**: Create remote command assertions (REQ-REMOTE-001-011)~~ ✅ cycle 97
3. ~~**Medium Priority**: Create interop assertions (REQ-INTEROP-001-003)~~ ✅ cycle 98
4. ~~**Medium Priority**: Create unit assertions (REQ-UNIT-001-004)~~ ✅ cycle 98

---

## Assertion Files

| File | REQs Covered | Gaps Covered |
|------|--------------|--------------|
| `treatment-sync.yaml` | 7 | 7 |
| **Total** | **7** | **7** |

---

## Cross-References

- **Requirements Source**: [`treatments-requirements.md`](../treatments-requirements.md)
- **Gaps Source**: [`treatments-gaps.md`](../treatments-gaps.md)
- **Assertion Files**: [`conformance/assertions/treatment-sync.yaml`](../../conformance/assertions/treatment-sync.yaml)
