# Scenario: Override Supersede

## Summary

This scenario validates that when a new override is activated while a previous override is still active, the system correctly:

1. Marks the previous override as superseded
2. Activates the new override
3. Maintains an auditable history of both events

## Preconditions

- User has an active profile
- An override ("Exercise") is currently active with 30 minutes remaining
- System time is known and consistent

## Trigger

User activates a new override ("Low Treatment") while "Exercise" is still active.

## Expected Behavior

### Immediate Effects

1. "Exercise" override status changes to `superseded`
2. "Exercise" override gains a `superseded_by` reference to the new override
3. "Low Treatment" override becomes active
4. "Low Treatment" override has `supersedes` reference to "Exercise"

### Data Integrity

- Neither override is deleted
- Both overrides have accurate timestamps
- The supersession relationship is bidirectional and consistent

### API Response

When querying active overrides:
- Only "Low Treatment" should appear
- Query for historical overrides should return both

## Test Data

### Input: Exercise Override (pre-existing)

```json
{
  "id": "override-001",
  "type": "override",
  "name": "Exercise",
  "started_at": "2024-01-15T14:00:00Z",
  "duration_minutes": 60,
  "target_range": { "min": 140, "max": 160 },
  "status": "active"
}
```

### Input: Low Treatment Override (new)

```json
{
  "id": "override-002",
  "type": "override",
  "name": "Low Treatment",
  "started_at": "2024-01-15T14:30:00Z",
  "duration_minutes": 45,
  "target_range": { "min": 120, "max": 140 },
  "status": "active"
}
```

### Expected Output: Exercise Override (after supersession)

```json
{
  "id": "override-001",
  "type": "override",
  "name": "Exercise",
  "started_at": "2024-01-15T14:00:00Z",
  "duration_minutes": 60,
  "target_range": { "min": 140, "max": 160 },
  "status": "superseded",
  "superseded_at": "2024-01-15T14:30:00Z",
  "superseded_by": "override-002"
}
```

## Assertions

See [assertions/override-supersede.yaml](../../assertions/override-supersede.yaml)

## Coverage

| Project | Status | Notes |
|---------|--------|-------|
| Nightscout | 🟡 | Partial - no supersession tracking |
| Loop | ✅ | Full support |
| AAPS | 🟡 | Uses different mechanism (ProfileSwitch) |
| Trio | ✅ | Full support |

## Related

- [ADR-001: Override Supersession Semantics](../../../docs/90-decisions/adr-001-override-supersession.md)
- [Schema: aid-events.schema.json](../../../specs/jsonschema/aid-events.schema.json)
