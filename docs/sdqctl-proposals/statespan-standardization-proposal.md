# StateSpan Standardization Proposal

> **Date**: 2026-01-30  
> **Status**: Draft  
> **Related Items**: OQ-010 Extended #14  
> **Related Gaps**: GAP-NOCTURNE-001, GAP-V4-001, GAP-V4-002

---

## Executive Summary

This proposal evaluates Nocturne's V4 StateSpan model for ecosystem-wide standardization. StateSpan provides a unified abstraction for time-ranged system states (pump modes, overrides, profiles, user activities) that addresses multiple gaps in the current treatment-based approach.

### Recommendation

**Adopt a minimal StateSpan subset as a V3 extension** (not V4-only) to enable:
- Profile history tracking beyond current snapshot
- Override/TempTarget duration visualization
- Pump mode tracking across AID systems
- Cleaner data model for time-ranged states

---

## Problem Statement

### Current State (cgm-remote-monitor)

Time-ranged states are stored as **treatments** with implicit duration:

```javascript
// Profile Switch - point-in-time event
{
  eventType: "Profile Switch",
  profile: "Weekday",
  created_at: "2026-01-30T10:00:00Z"
  // No explicit end time - ends when next Profile Switch arrives
}

// Temporary Override - has duration
{
  eventType: "Temporary Override",
  duration: 60,  // minutes
  insulinNeedsScaleFactor: 0.8
  // End time must be calculated
}

// Override Cancel - separate event
{
  eventType: "Temporary Override Cancel"
  // No reference to which override it cancels
}
```

### Issues

| Issue | Impact |
|-------|--------|
| **No explicit time ranges** | Must calculate end times from duration or next event |
| **Cancel events disconnected** | No foreign key linking cancel to original |
| **Mixed with treatments** | Time-ranged states mixed with point-in-time events |
| **No pump mode tracking** | Closed-loop vs open-loop state not queryable |
| **No activity annotations** | No way to record sleep/exercise/illness context |

---

## Nocturne StateSpan Model

### Core Schema

```typescript
interface StateSpan {
  id: string;                    // UUID
  category: StateSpanCategory;   // Enum: Profile, Override, TempBasal, PumpMode, etc.
  state: string;                 // State value within category
  startMills: number;            // Epoch milliseconds
  endMills?: number;             // null = currently active
  source: string;                // Data source identifier
  metadata?: Record<string, any>; // Category-specific data
  originalId?: string;           // Source system ID for dedup
  canonicalId?: string;          // Cross-source dedup group
  createdAt: string;             // ISO timestamp
  updatedAt: string;             // ISO timestamp
}
```

### Categories

| Category | States | Metadata Fields |
|----------|--------|-----------------|
| `Profile` | Active | `profileName`, `percentage`, `timeshift` |
| `Override` | None, Custom | `insulinNeedsScaleFactor`, `targetTop`, `targetBottom`, `reason` |
| `TempBasal` | Active, Cancelled | `rate`, `percent`, `durationMins` |
| `PumpMode` | Automatic, Manual, Boost, Sleep, etc. | Controller-specific |
| `PumpConnectivity` | Connected, Disconnected | `reason`, `device` |
| `Sleep` | (user-defined) | `quality` |
| `Exercise` | (user-defined) | `type`, `intensity` |
| `Illness` | (user-defined) | `symptoms`, `sensitivity_factor` |
| `Travel` | (user-defined) | `timezone_change` |

### API Endpoints

```
GET  /api/v4/state-spans?category=Profile&from=...&to=...
GET  /api/v4/state-spans/profiles
GET  /api/v4/state-spans/overrides
GET  /api/v4/state-spans/pump-modes
GET  /api/v4/state-spans/{id}
POST /api/v4/state-spans
PUT  /api/v4/state-spans/{id}
DELETE /api/v4/state-spans/{id}
```

---

## Standardization Options

### Option A: V4-Only (Nocturne Native)

Keep StateSpan as Nocturne V4 feature, no ecosystem adoption.

| Pros | Cons |
|------|------|
| No cgm-remote-monitor changes | Nocturne diverges from ecosystem |
| Nocturne can evolve independently | No interoperability |
| Already implemented | AID apps can't use standard API |

### Option B: V3 Extension (Recommended)

Add minimal StateSpan subset to V3 API with backward compatibility.

| Pros | Cons |
|------|------|
| Backward compatible | Implementation work in cgm-remote-monitor |
| All AID apps can adopt | Dual storage (treatments + spans) |
| Unified ecosystem API | Schema maintenance burden |

### Option C: Treatments Enhancement

Extend treatment model with explicit time ranges instead of new collection.

| Pros | Cons |
|------|------|
| Single collection | Treatment collection bloat |
| No migration needed | Time-range queries still inefficient |
| Minimal changes | Mixes concepts |

---

## Recommended: Option B - V3 Extension

### Minimal Viable Subset

For ecosystem adoption, start with **4 core categories**:

| Category | Justification |
|----------|---------------|
| `Profile` | All AID systems have profile switching |
| `Override` | Loop/AAPS/Trio all have override/TempTarget |
| `TempBasal` | All AID systems use temp basals |
| `PumpMode` | Critical for closed-loop state tracking |

Defer user annotation categories (Sleep, Exercise, Illness, Travel) to Phase 2.

### V3 Endpoint Proposal

```
GET /api/v3/state-spans?category=...&from=...&to=...
```

### Backward Compatibility

1. **Continue accepting treatment writes** for Profile Switch, Override, TempBasal
2. **Auto-generate StateSpans** from treatments on write
3. **Return StateSpans** from new endpoint for queries
4. **Deprecate point-in-time queries** over 2 versions

### Migration Path

| Phase | Duration | Deliverables |
|-------|----------|--------------|
| Phase 1 | 3 months | StateSpan collection + read API |
| Phase 2 | 3 months | Auto-translation from treatments |
| Phase 3 | 6 months | Native StateSpan writes |
| Phase 4 | 6 months | Deprecate treatment-based queries |

---

## Consumer Adoption

### Loop

```swift
// Current: query treatments, filter by eventType
let overrides = treatments.filter { $0.eventType == "Temporary Override" }

// Proposed: direct StateSpan query
let overrides = await nightscout.getStateSpans(category: .override, from: from, to: to)
```

### AAPS

```kotlin
// Current: query treatments, calculate durations
val tempTargets = treatments.filter { it.eventType == "Temporary Target" }

// Proposed: StateSpan with explicit time ranges
val overrides = nightscoutApi.getStateSpans(StateSpanCategory.OVERRIDE, from, to)
```

### Trio

Same as Loop - uses NightscoutKit.

### xDrip+

```java
// Current: complex eventType parsing
List<Treatment> overrides = treatments.stream()
    .filter(t -> t.eventType.contains("Override"))
    .collect(Collectors.toList());

// Proposed: category-based query
List<StateSpan> overrides = NightscoutApi.getStateSpans(StateSpanCategory.OVERRIDE, from, to);
```

---

## Gap Remediation

### GAP-NOCTURNE-001: V4 API Compatibility

**Status**: Partially addressed

StateSpan standardization in V3 provides path for Loop/AAPS/Trio to consume Nocturne's enhanced data model without V4 dependency.

### GAP-V4-001: V4 StateSpan Not Standard

**Status**: Addressed by this proposal

Standardizing in V3 makes StateSpan available ecosystem-wide.

### GAP-V4-002: V4 Profile History Gap

**Status**: Addressed

`/api/v3/state-spans?category=Profile` provides query-able profile history.

---

## Requirements

### REQ-STATESPAN-001: Time Range Query

**Statement**: StateSpan API MUST support time-range queries with `from` and `to` parameters.

**Verification**: Query returns only spans overlapping the time range.

### REQ-STATESPAN-002: Category Filtering

**Statement**: StateSpan API MUST support filtering by category enum.

**Verification**: `?category=Profile` returns only Profile spans.

### REQ-STATESPAN-003: Active Span Query

**Statement**: StateSpan API MUST support querying currently active spans.

**Verification**: `?active=true` returns spans where `endMills` is null.

### REQ-STATESPAN-004: Treatment Translation

**Statement**: Implementation SHOULD auto-generate StateSpans from treatment writes.

**Verification**: Writing a Profile Switch treatment creates a Profile StateSpan.

### REQ-STATESPAN-005: Source Tracking

**Statement**: StateSpan MUST include `source` field identifying data origin.

**Verification**: StateSpan from AAPS has `source: "AAPS"`.

---

## Implementation Notes

### cgm-remote-monitor Changes

1. Add `statespans` collection to MongoDB
2. Create `lib/api3/generic/statespans/` endpoint module
3. Add translation layer in treatment write path
4. Add state-span query support to socket.io broadcasts

### OpenAPI Spec

```yaml
/api/v3/state-spans:
  get:
    summary: Query state spans
    parameters:
      - name: category
        in: query
        schema:
          type: string
          enum: [Profile, Override, TempBasal, PumpMode]
      - name: from
        in: query
        schema:
          type: integer
          format: int64
      - name: to
        in: query
        schema:
          type: integer
          format: int64
      - name: active
        in: query
        schema:
          type: boolean
    responses:
      200:
        content:
          application/json:
            schema:
              type: array
              items:
                $ref: '#/components/schemas/StateSpan'
```

---

## Conclusion

StateSpan provides a cleaner abstraction for time-ranged system states than the current treatment-based approach. Adopting a minimal subset (Profile, Override, TempBasal, PumpMode) as a V3 extension enables ecosystem-wide adoption while maintaining backward compatibility.

**Recommended next steps**:
1. Draft OpenAPI spec for `/api/v3/state-spans`
2. Prototype in cgm-remote-monitor dev branch
3. Coordinate with Loop/AAPS/Trio maintainers
4. Publish RFC for community feedback

---

## References

- [StateSpan Client SDK Patterns](../10-domain/statespan-client-sdk-patterns.md) - Query patterns, caching, platform SDKs
- [StateSpan Gap Remediation Mapping](../10-domain/statespan-gap-remediation-mapping.md) - Analysis of 47 gaps, 12 fully addressed
- [Nocturne V4 StateSpan Implementation](../../externals/nocturne/src/Core/Nocturne.Core.Models/StateSpan.cs)
- [Nocturne StateSpan Controller](../../externals/nocturne/src/API/Nocturne.API/Controllers/V4/StateSpansController.cs)
- [Nocturne V4 Profile Extensions](../10-domain/nocturne-v4-profile-extensions.md)
- [GAP-V4-001, GAP-V4-002](../../traceability/sync-identity-gaps.md)
