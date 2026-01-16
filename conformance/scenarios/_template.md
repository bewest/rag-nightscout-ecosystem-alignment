# Scenario: [Name]

## Summary

[One paragraph describing what this scenario tests and why it matters.]

## Preconditions

- [State that must exist before the scenario runs]
- [Required data, configurations, etc.]

## Trigger

[What action initiates the scenario]

## Expected Behavior

### Immediate Effects

1. [What should happen immediately]
2. [State changes]

### Data Integrity

- [Data consistency requirements]
- [Relationship requirements]

### API Response

[Expected responses from queries]

## Test Data

### Input: [Description]

```json
{
  "example": "data"
}
```

### Expected Output: [Description]

```json
{
  "example": "output"
}
```

## Assertions

See [assertions/scenario-name.yaml](../../assertions/scenario-name.yaml)

## Coverage

| Project | Status | Notes |
|---------|--------|-------|
| Nightscout | ⬜ | |
| Loop | ⬜ | |
| AAPS | ⬜ | |
| Trio | ⬜ | |

## Related

- [Links to ADRs, requirements, related scenarios]
