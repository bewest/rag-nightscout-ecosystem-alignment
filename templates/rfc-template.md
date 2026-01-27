# RFC Template

Use this template for proposals requiring community consensus on API changes,
data model modifications, or cross-project compatibility decisions.

---

# RFC: [Title]

## Status

Draft | Under Review | Accepted | Rejected | Superseded

## Summary

[1-2 sentence summary of the proposed change]

## Motivation

### Problem Statement
[What problem does this solve?]

### Related Gaps
- [GAP-XXX-NNN](../traceability/gaps.md#gap-xxx-nnn): [Brief description]

### Related Requirements
- [REQ-NNN](../traceability/requirements.md#req-nnn): [Brief description]

## Detailed Design

### Current Behavior

[How things work now. Include code references:]
```
See `externals/repo/path/file.ext:line` for current implementation.
```

### Proposed Behavior

[How things should work after this RFC is implemented]

### API Changes

#### New Endpoints
```yaml
# None | List new endpoints
```

#### Modified Endpoints
```yaml
# None | List modified endpoints with before/after
```

#### New Fields
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `fieldName` | string | yes | Description |

#### Deprecated Fields
| Field | Deprecation Date | Removal Date | Migration |
|-------|------------------|--------------|-----------|
| `oldField` | 2026-03-01 | 2026-09-01 | Use `newField` |

### Data Model Changes

#### Schema Changes
```json
{
  "type": "object",
  "properties": {
    "newField": { "type": "string" }
  }
}
```

#### Database Migrations
[Required migrations, if any]

## Implementation

### Affected Repositories

| Repository | Changes Required | Complexity |
|------------|-----------------|------------|
| cgm-remote-monitor | [Description] | Low/Medium/High |
| Loop | [Description] | Low/Medium/High |
| AAPS | [Description] | Low/Medium/High |
| Trio | [Description] | Low/Medium/High |
| xDrip+ | [Description] | Low/Medium/High |

### Implementation Order

1. [ ] [First change - usually server-side]
2. [ ] [Second change]
3. [ ] [Client updates]

### Migration Path

[How to migrate existing data/behavior]

### Backward Compatibility

| Client Version | Behavior |
|----------------|----------|
| < 1.0 | [How old clients behave] |
| >= 1.0 | [How new clients behave] |

### Testing Strategy

- [ ] Unit tests for new behavior
- [ ] Integration tests across systems
- [ ] Conformance scenario: [Link to scenario]

## Alternatives Considered

### Alternative 1: [Name]
[Description and why rejected]

### Alternative 2: [Name]
[Description and why rejected]

## Security Considerations

[Any security implications of this change]

## Open Questions

1. [Question 1]
2. [Question 2]

## References

- [GAP-XXX-NNN](../traceability/gaps.md#gap-xxx-nnn)
- [REQ-NNN](../traceability/requirements.md#req-nnn)
- [External Reference](https://example.com)

---

## Revision History

| Date | Author | Changes |
|------|--------|---------|
| YYYY-MM-DD | [Name] | Initial draft |
