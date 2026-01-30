# ADR-004: ProfileSwitch → Override Mapping Rules

## Status

Proposed

## Date

2026-01-30

## Context

**OQ-010** asks: Should AAPS ProfileSwitch be accepted as a valid representation of overrides, or must there be explicit mapping?

AAPS uses `ProfileSwitch` events with percentage/target modifications rather than explicit overrides. Loop/Trio use explicit override records. Cross-project queries need to understand both patterns.

### Research Findings

Six analyses were conducted to inform this decision:

| # | Analysis | Key Finding |
|---|----------|-------------|
| 1 | Nocturne ProfileSwitch model | Nocturne applies percentage/timeshift; cgm-remote-monitor doesn't |
| 2 | Percentage/timeshift handling | Profile API returns raw values; internal calculations use scaled |
| 3 | Profile sync comparison | Deduplication, srvModified, and delete semantics all differ |
| 4 | Override/TempTarget representation | No unification; no supersession tracking in either |
| 5 | V4 ProfileSwitch extensions | StateSpan API provides profile history (Nocturne-only, not V3) |
| 6 | Rust oref profile handling | PredictionService bypasses ProfileService - critical gap |

### Current System Behaviors

| System | Override Mechanism | Percentage | Target Adjustment | Supersession |
|--------|-------------------|------------|-------------------|--------------|
| **Loop** | `Temporary Override` | `insulinNeedsScaleFactor` | Implicit via scale | Tracked |
| **AAPS** | `Profile Switch` | `percentage` field | `targetTop`/`targetBottom` | Not tracked |
| **Trio** | `Temporary Override` | `insulinNeedsScaleFactor` | Implicit via scale | Tracked |
| **Nocturne** | Both supported | Applied internally | Both fields | Via StateSpan |
| **cgm-remote-monitor** | Both stored | **Not applied** | Both fields | Not tracked |

### Gaps Identified

| Gap ID | Issue |
|--------|-------|
| GAP-NOCTURNE-004 | Percentage/timeshift application divergence |
| GAP-NOCTURNE-005 | Profile API returns raw despite active ProfileSwitch |
| GAP-OVRD-005 | No unified Override/TempTarget schema |
| GAP-OVRD-006 | No supersession tracking in Nightscout |
| GAP-OREF-001 | PredictionService bypasses ProfileService |

## Decision

We will adopt a **dual-representation acceptance model** with **explicit mapping rules**:

### 1. Accept Both Representations as Valid

Both `Temporary Override` (Loop/Trio) and `Profile Switch` (AAPS) are valid ways to represent temporary therapy adjustments. Neither requires conversion to the other.

### 2. Define Semantic Equivalence Rules

| Override Aspect | Loop/Trio Field | AAPS Equivalent | Mapping |
|-----------------|-----------------|-----------------|---------|
| Insulin adjustment | `insulinNeedsScaleFactor` | `percentage / 100` | Direct conversion |
| Target adjustment | N/A (uses scale) | `targetTop`, `targetBottom` | AAPS-specific |
| Duration | `duration` (minutes) | `duration` (minutes) | Same |
| Profile reference | N/A | `profileName` | AAPS-specific |
| Reason | `reason` (free text) | `reason` (enum) | Normalize to free text |

### 3. Require Percentage Application at Query Time

Servers MUST apply percentage/timeshift when returning profile values for algorithm consumption:

```
Effective Basal = Base Basal × (percentage / 100)
Effective ISF = Base ISF × (100 / percentage)
Effective CR = Base CR × (100 / percentage)
```

This addresses GAP-OREF-001 where PredictionService bypasses ProfileService.

### 4. Recommend StateSpan for Profile History

For implementations tracking profile activation history, the V4 StateSpan model provides the recommended structure:

```json
{
  "category": "Profile",
  "state": "Active",
  "startTime": "2026-01-30T10:00:00Z",
  "endTime": "2026-01-30T14:00:00Z",
  "canonicalId": "profile-123",
  "metadata": {
    "profileName": "Exercise",
    "percentage": 80,
    "timeshift": 0
  }
}
```

### 5. Cross-Query Translation Rules

When querying across systems:

| Query | Loop/Trio | AAPS | Translation |
|-------|-----------|------|-------------|
| "Active overrides" | `eventType: Temporary Override` | `eventType: Profile Switch` where `percentage != 100` OR `targetTop/Bottom` differ from profile | Include both |
| "Insulin sensitivity multiplier" | `insulinNeedsScaleFactor` | `percentage / 100` | Normalize to decimal |
| "Is override active at time T?" | Check `created_at` + `duration` | Check `created_at` + `duration` | Same logic |

## Consequences

### Positive

- **No forced migration**: Existing data remains valid
- **Cross-system queries**: Clear translation rules enable ecosystem-wide analysis
- **Algorithm accuracy**: Percentage application requirement fixes prediction gaps
- **Future-proof**: StateSpan model provides path to unified history

### Negative

- **Query complexity**: Consumers must understand both patterns
- **Nocturne deviation**: cgm-remote-monitor would need changes to apply percentage
- **V3 limitation**: Profile history requires V4 StateSpan (Nocturne-only for now)

### Neutral

- **Documentation burden**: Both patterns must be documented
- **Test coverage**: Conformance tests need both patterns

## Alternatives Considered

### Option A: Force Conversion to Override

Require all ProfileSwitch events to be converted to Override format on ingest.

**Rejected because**:
- Loses AAPS-specific semantics (targetTop/Bottom)
- Breaks existing AAPS integrations
- Unnecessary data transformation

### Option B: Force Conversion to ProfileSwitch

Require all Override events to be converted to ProfileSwitch format.

**Rejected because**:
- Loses Loop/Trio-specific semantics (insulinNeedsScaleFactor)
- ProfileSwitch implies profile document, Override doesn't
- Unnecessary data transformation

### Option C: Create New Unified Schema

Define a new "TherapyAdjustment" schema combining both patterns.

**Rejected because**:
- Breaking change for all clients
- Migration complexity outweighs benefits
- Current translation rules sufficient for cross-query

## Compliance

### Verification Criteria

1. **Percentage application**: Profile endpoints return scaled values when ProfileSwitch active
2. **Translation accuracy**: Cross-system queries return equivalent results
3. **History preservation**: Both Override and ProfileSwitch events retained with original semantics

### Conformance Tests

```yaml
# conformance/scenarios/profile-override-mapping.yaml
scenarios:
  - name: "ProfileSwitch percentage applied"
    given:
      - Profile with basal=1.0, ISF=50, CR=10
      - Active ProfileSwitch with percentage=150
    when:
      - Query effective profile values
    then:
      - Basal = 1.5 (1.0 × 1.5)
      - ISF = 33.3 (50 / 1.5)
      - CR = 6.67 (10 / 1.5)

  - name: "Override insulinNeedsScaleFactor translated"
    given:
      - Override with insulinNeedsScaleFactor=0.8
    when:
      - Query as percentage
    then:
      - percentage = 80
```

## References

### Analysis Documents

- [Nocturne ProfileSwitch Analysis](../10-domain/nocturne-profileswitch-analysis.md)
- [Nocturne Percentage/Timeshift Handling](../10-domain/nocturne-percentage-timeshift-handling.md)
- [Profile Sync Comparison](../10-domain/nocturne-cgm-remote-monitor-profile-sync.md)
- [Override/TempTarget Analysis](../10-domain/nocturne-override-temptarget-analysis.md)
- [V4 ProfileSwitch Extensions](../10-domain/nocturne-v4-profile-extensions.md)
- [Rust oref Profile Analysis](../10-domain/nocturne-rust-oref-profile-analysis.md)

### Related ADRs

- [ADR-001: Override Supersession Semantics](adr-001-override-supersession.md)
- [ADR-002: Sync Identity Strategy](adr-002-sync-identity-strategy.md)

### Gaps Addressed

- GAP-NOCTURNE-004, GAP-NOCTURNE-005
- GAP-OVRD-005, GAP-OVRD-006
- GAP-OREF-001

### Requirements Satisfied

- REQ-SYNC-054, REQ-SYNC-055, REQ-SYNC-056
- REQ-SYNC-057, REQ-SYNC-058
- REQ-OREF-001

---

*Drafted: 2026-01-30*
*OQ-010 Research Queue: Item #11 (final)*
