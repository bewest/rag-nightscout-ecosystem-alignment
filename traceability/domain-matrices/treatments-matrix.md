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
| REQs with assertion coverage | 28 (80%) |
| Uncovered REQs | 7 (20%) |
| Uncovered GAPs | 2 (22%) |

**Status**: Treatment sync requirements (REQ-TREAT-040-046) covered by treatment-sync.yaml. Alarm requirements (REQ-ALARM-001-010) covered by alarm-requirements.yaml. Remote command requirements (REQ-REMOTE-001-011) covered by remote-command-requirements.yaml. Interop and Unit requirements need assertion coverage.

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

### Interop Requirements (3)

| Requirement | Description | Gap Links | Assertions |
|-------------|-------------|-----------|------------|
| REQ-INTEROP-001 | Standard Timestamp Format | - | ❌ None |
| REQ-INTEROP-002 | Standard eventType Values | GAP-TREAT-003 | ❌ None |
| REQ-INTEROP-003 | Device Identifier Inclusion | - | ❌ None |

### Unit Requirements (4)

| Requirement | Description | Gap Links | Assertions |
|-------------|-------------|-----------|------------|
| REQ-UNIT-001 | Duration Unit Documentation | GAP-TREAT-002 | ❌ None |
| REQ-UNIT-002 | Duration Validation | GAP-TREAT-002 | ❌ None |
| REQ-UNIT-003 | utcOffset Validation | - | ❌ None |
| REQ-UNIT-004 | Preserve High-Precision Fields | - | ❌ None |

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
| Alarm | 10 | 0 | 0% |
| Remote | 11 | 0 | 0% |
| Interop | 3 | 0 | 0% |
| Unit | 4 | 0 | 0% |
| Treatment Sync | 7 | 7 | 100% |
| **Total** | **35** | **7** | **20%** |

### Priority Action Items

1. **High Priority**: Create alarm assertions (REQ-ALARM-001-010)
   - Cross-platform alarm behavior is critical for safety
   - No current coverage for glucose threshold or prediction alarms

2. **High Priority**: Create remote command assertions (REQ-REMOTE-001-011)
   - Security-critical functionality
   - Authentication, replay protection, audit trail

3. **Medium Priority**: Create interop assertions (REQ-INTEROP-001-003)
   - Timestamp and eventType standardization
   - Links to GAP-TREAT-003

4. **Medium Priority**: Create unit assertions (REQ-UNIT-001-004)
   - Duration and precision handling
   - Links to GAP-TREAT-002

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
