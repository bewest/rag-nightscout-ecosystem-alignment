# Mapping: Nightscout - Override Supersede

## Overview

Nightscout stores overrides as treatment documents with `eventType: "Temporary Override"`. Currently, there is no explicit supersession tracking—overrides simply have a duration and are considered expired when that time passes.

## Terminology Mapping

| Alignment Term | Nightscout Term | Notes |
|----------------|-----------------|-------|
| Override | Temporary Override (treatment) | Stored in treatments collection |
| superseded | (no equivalent) | Gap: see GAP-001 |
| superseded_by | (no equivalent) | Gap: see GAP-001 |

## Data Structure Mapping

### Alignment Schema

```json
{
  "id": "override-001",
  "type": "override",
  "name": "Exercise",
  "started_at": "2024-01-15T14:00:00Z",
  "duration_minutes": 60,
  "status": "superseded",
  "superseded_by": "override-002",
  "superseded_at": "2024-01-15T14:30:00Z"
}
```

### Nightscout Schema

```json
{
  "_id": "ObjectId(...)",
  "eventType": "Temporary Override",
  "reason": "Exercise",
  "created_at": "2024-01-15T14:00:00Z",
  "duration": 60,
  "enteredBy": "Loop"
}
```

### Transformation Rules

1. **id**: Map from `_id.toString()`
2. **type**: Hardcode to `"override"` when `eventType === "Temporary Override"`
3. **name**: Map from `reason`
4. **started_at**: Map from `created_at`
5. **duration_minutes**: Map from `duration`
6. **status**: Infer from current time vs duration (no supersession data available)
7. **superseded_by**: Not available in Nightscout
8. **superseded_at**: Not available in Nightscout

## Semantic Differences

### Supersession Tracking

**Alignment says**: When override B supersedes A, A's status becomes "superseded" with a reference to B.

**Nightscout does**: No explicit supersession. If Loop sends a new override, the old one just has its duration. No relationship is recorded.

**Resolution**: 
- Option A: Add supersession fields to Nightscout treatment schema
- Option B: Infer supersession by looking at overlapping override periods
- Current: Accept data loss during Nightscout round-trip

### Duration vs End Time

**Alignment says**: Use `ended_at` timestamp for explicit end time.

**Nightscout does**: Uses `duration` in minutes; end time is calculated.

**Resolution**: Calculate `ended_at = started_at + duration_minutes * 60000`

## Code References

| Purpose | Location | Notes |
|---------|----------|-------|
| Treatment storage | `lib/server/treatments.js` | Core treatment handling |
| Override upload | `lib/api3/generic/update/operation.js` | API v3 update logic |

## Conformance Status

| Requirement | Status | Notes |
|-------------|--------|-------|
| REQ-001: Override Identity | ✅ | Uses MongoDB _id |
| REQ-002: Override Supersession Tracking | ❌ | Not implemented |
| REQ-003: Override Status Transitions | 🟡 | Implicit via duration only |

## Open Questions

- [ ] Would Nightscout maintainers accept PR adding supersession fields?
- [ ] Should we create a separate "supersession event" rather than modify treatments?
