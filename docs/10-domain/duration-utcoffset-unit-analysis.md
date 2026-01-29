# Duration and utcOffset Unit Impact Analysis

> **Purpose**: Analyze unit inconsistencies across AID systems and evaluate standardization options  
> **Scope**: Duration (temp basal, eCarbs) and utcOffset fields  
> **Last Updated**: 2026-01-29

## Executive Summary

Duration and timezone offset fields use different units across Nightscout, Loop, and AAPS, creating interoperability risks. This analysis documents the inconsistencies, assesses their impact, and evaluates standardization alternatives.

### Key Findings

| Field | Nightscout | Loop | AAPS | Risk |
|-------|------------|------|------|------|
| `duration` (TBR) | minutes | seconds | milliseconds | 60x or 60000x error |
| `duration` (eCarbs) | minutes | N/A | milliseconds | 60000x error |
| `utcOffset` | minutes | N/A | milliseconds (internal) | 60000x error |

---

## Current State by System

### Nightscout (cgm-remote-monitor)

| Field | Unit | Evidence |
|-------|------|----------|
| `duration` | minutes | `lib/api3/generic/collection.js` - all duration fields |
| `utcOffset` | minutes | `lib/profilefunctions.js` - moment.utcOffset() returns minutes |

```javascript
// Nightscout expects duration in minutes
treatment.duration = 30;  // 30 minutes
treatment.utcOffset = -480;  // UTC-8 (8 hours * 60 minutes)
```

### Loop (iOS)

| Field | Unit | Evidence |
|-------|------|----------|
| `duration` (TBR) | seconds | `LoopKit/DoseEntry.swift` - `TimeInterval` type |
| `absorptionTime` | seconds | `LoopKit/CarbEntry.swift` - carb absorption time |
| `utcOffset` | N/A | Uses `TimeZone` object, converts on upload |

```swift
// Loop uses TimeInterval (seconds)
let tempBasal = DoseEntry(
    type: .tempBasal,
    startDate: Date(),
    endDate: Date().addingTimeInterval(1800),  // 30 minutes = 1800 seconds
    value: 0.5,
    unit: .unitsPerHour
)
```

### AAPS (Android)

| Field | Unit | Evidence |
|-------|------|----------|
| `duration` (internal) | milliseconds | `database/entities/TemporaryBasal.kt` |
| `duration` (upload) | minutes | `nssdk/RemoteTreatment.kt` - converted for NS |
| `durationInMilliseconds` | milliseconds | AAPS-specific field, preserved for accuracy |
| `utcOffset` (internal) | milliseconds | `DBEntryWithTime.kt` |
| `utcOffset` (upload) | minutes | Converted for NS compatibility |

```kotlin
// AAPS internal storage (milliseconds)
val temporaryBasal = TemporaryBasal(
    timestamp = System.currentTimeMillis(),
    duration = 1800000,  // 30 minutes = 1,800,000 ms
    rate = 0.5
)

// AAPS upload to Nightscout (converted to minutes)
val treatment = RemoteTreatment(
    duration = 30,  // 30 minutes
    durationInMilliseconds = 1800000  // preserved for precision
)
```

---

## Gap Analysis

### GAP-TREAT-002: Duration Unit Inconsistency

| System | Internal Unit | Upload Unit | Conversion |
|--------|---------------|-------------|------------|
| Nightscout | minutes | minutes | None |
| Loop | seconds | minutes | ÷ 60 |
| AAPS | milliseconds | minutes | ÷ 60000 |

**Risk**: Incorrect conversion causes:
- 30-minute TBR interpreted as 30 seconds (Loop → NS without conversion)
- 30-minute TBR interpreted as 30 milliseconds (AAPS → NS without conversion)

### GAP-TZ-004: utcOffset Unit Mismatch

| System | Internal Unit | Upload Unit | Conversion |
|--------|---------------|-------------|------------|
| Nightscout | minutes | minutes | None |
| AAPS | milliseconds | minutes | ÷ 60000 |

**Risk**: -480 minutes (UTC-8) could be misinterpreted as -480 milliseconds (< 1 second offset).

### GAP-PUMP-003: TBR Duration Across Pumps

Pump drivers add another layer of complexity:

| Pump | Duration Unit | Notes |
|------|---------------|-------|
| Omnipod | 30-min increments | Rounded to 30 min blocks |
| Dana RS | minutes | Integer minutes only |
| Medtronic | minutes | Max 24 hours |

---

## Standardization Alternatives

### Option 1: Standardize on Minutes (Status Quo)

**Description**: All systems convert to minutes for Nightscout interchange.

| Aspect | Assessment |
|--------|------------|
| **Pros** | Already implemented, human-readable |
| **Cons** | Precision loss (sub-minute TBRs impossible) |
| **Changes** | Document existing behavior clearly |
| **Risk** | Low (existing behavior) |

**Implementation**:
- Document unit expectations in OpenAPI specs
- Add validation: `duration` must be > 0 and < 1440 (24 hours)

### Option 2: Standardize on Seconds

**Description**: All systems use seconds for duration fields.

| Aspect | Assessment |
|--------|------------|
| **Pros** | Higher precision, matches Loop native format |
| **Cons** | Breaking change for Nightscout, AAPS |
| **Changes** | NS schema change, all clients update |
| **Risk** | High (breaking change) |

**Implementation**:
- New API version (v4) with seconds
- Migration path for existing data

### Option 3: Standardize on Milliseconds

**Description**: All systems use milliseconds for duration fields.

| Aspect | Assessment |
|--------|------------|
| **Pros** | Maximum precision, matches AAPS native format |
| **Cons** | Overkill for most use cases, larger numbers |
| **Changes** | NS schema change, Loop/Trio update |
| **Risk** | High (breaking change) |

### Option 4: ISO 8601 Duration Format

**Description**: Use ISO 8601 duration strings (e.g., `PT30M`, `PT1H30M`).

| Aspect | Assessment |
|--------|------------|
| **Pros** | Self-documenting, no unit confusion, flexible |
| **Cons** | String parsing overhead, storage increase |
| **Changes** | All systems update parsing logic |
| **Risk** | Medium (new format, but unambiguous) |

**Examples**:
```json
{
  "duration": "PT30M",       // 30 minutes
  "duration": "PT1H",        // 1 hour
  "duration": "PT90S",       // 90 seconds
  "absorptionTime": "PT3H"   // 3 hours
}
```

---

## Recommendation

### Short-term (Option 1 Enhanced)

1. **Document** unit expectations clearly in OpenAPI specs
2. **Validate** duration ranges (0 < duration < 1440 minutes)
3. **Add** explicit `durationUnit: "minutes"` field for clarity
4. **Preserve** AAPS `durationInMilliseconds` for precision recovery

### Long-term (Option 4)

For Nightscout API v4 or Nocturne:
1. Adopt ISO 8601 duration format
2. Provide conversion utilities
3. Accept both formats during transition

---

## Requirements

### REQ-UNIT-001: Duration Unit Documentation

**Statement**: API specifications MUST clearly document the unit for all duration fields.

**Rationale**: Prevents off-by-60x or off-by-60000x errors.

**Verification**: OpenAPI spec includes unit in field description.

### REQ-UNIT-002: Duration Validation

**Statement**: The server SHOULD validate duration fields are within reasonable ranges.

**Rationale**: Catches unit confusion early (30000 minutes is clearly wrong).

**Verification**:
- Reject `duration > 1440` (> 24 hours) with warning
- Reject `duration < 0`

### REQ-UNIT-003: utcOffset Validation

**Statement**: The server SHOULD validate utcOffset is within ±840 minutes (±14 hours).

**Rationale**: Catches millisecond values being passed as minutes.

**Verification**:
- Reject `|utcOffset| > 840` with error
- Log warning for unusual offsets

### REQ-UNIT-004: Preserve High-Precision Fields

**Statement**: The server SHOULD preserve AAPS-specific high-precision fields (`durationInMilliseconds`) for round-trip accuracy.

**Rationale**: Allows AAPS to recover original precision on sync back.

**Verification**: Field preserved unchanged in storage and retrieval.

---

## Impact Assessment

### If No Action Taken

| Risk | Likelihood | Impact | Scenario |
|------|------------|--------|----------|
| Duration misinterpretation | Medium | High | 30-min TBR runs for 30 seconds |
| utcOffset corruption | Low | Medium | Timestamps shifted by hours |
| Data loss on sync | Low | High | Treatments silently corrupted |

### If Option 1 Enhanced Implemented

| Benefit | Effort | Timeline |
|---------|--------|----------|
| Clear documentation | Low | Immediate |
| Validation catches errors | Low | 1 sprint |
| No breaking changes | N/A | N/A |

---

## Related Gaps

| Gap ID | Title | Relationship |
|--------|-------|--------------|
| GAP-TREAT-002 | Duration Unit Inconsistency | Primary |
| GAP-TZ-004 | utcOffset Unit Mismatch | Primary |
| GAP-PUMP-003 | TBR Duration Across Pumps | Related |
| GAP-SYNC-008 | No Conflict Resolution | Tangential |

---

## Source Files Analyzed

| System | File | Relevant Lines |
|--------|------|----------------|
| Nightscout | `lib/api3/generic/collection.js` | Duration handling |
| Nightscout | `lib/profilefunctions.js` | utcOffset from moment |
| Loop | `LoopKit/DoseEntry.swift` | TimeInterval usage |
| Loop | `LoopKit/CarbEntry.swift` | absorptionTime |
| AAPS | `database/entities/TemporaryBasal.kt` | Duration in ms |
| AAPS | `database/entities/interfaces/DBEntryWithTime.kt` | utcOffset in ms |
| AAPS | `core/nssdk/remotemodel/RemoteTreatment.kt` | Upload conversion |

---

## References

- `mapping/cross-project/terminology-matrix.md` - Unit mappings
- `mapping/aaps/nsclient-schema.md` - AAPS field documentation
- `traceability/treatments-gaps.md` - GAP-TREAT-002
- `traceability/sync-identity-gaps.md` - GAP-TZ-004
- `traceability/pumps-gaps.md` - GAP-PUMP-003
