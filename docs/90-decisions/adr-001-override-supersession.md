# ADR-001: Override Supersession Semantics

## Status

Proposed

## Date

2024-01-15

## Context

When a user activates a new override while another override is still active, we need to define what happens to the original override. Different AID systems handle this differently:

- **Loop/Trio**: Explicitly track supersession with bidirectional references
- **AAPS**: Uses ProfileSwitch which has different semantics
- **Nightscout**: Currently has no supersession tracking

We need a consistent semantic model that:
1. Preserves audit history
2. Enables accurate historical queries
3. Can accommodate different implementation approaches

## Decision

We will adopt an **explicit supersession model** where:

1. When override B supersedes override A:
   - A's status changes from `active` to `superseded`
   - A gains a `superseded_by` field pointing to B's ID
   - A gains a `superseded_at` timestamp
   - B may optionally have a `supersedes` field pointing to A's ID

2. Supersession is **not deletion**:
   - The original override remains in the data store
   - All original fields are preserved
   - Only status and supersession fields are modified

3. Query semantics:
   - "Active overrides" returns only status=active
   - "Override history" returns all, including superseded
   - "Override at time T" uses started_at, ended_at/superseded_at

## Consequences

### Positive

- Complete audit trail of override changes
- Accurate historical queries possible
- Matches Loop/Trio existing behavior
- Supports data synchronization without loss

### Negative

- Nightscout requires schema changes
- AAPS mapping requires inference logic
- More complex query logic for "current state"

### Neutral

- Storage requirements slightly higher (superseded overrides retained)

## Alternatives Considered

### Implicit supersession via timestamps

Track only start/end times; infer supersession from overlapping ranges.

**Rejected because**: Loses information about why an override ended early; ambiguous when overrides have gaps.

### Delete-and-replace

Delete the old override when a new one starts.

**Rejected because**: Loses audit history; breaks data sync; violates event sourcing principles.

### Status field only

Just mark as superseded without bidirectional references.

**Rejected because**: Cannot answer "what superseded this override?" without scanning all later overrides.

## Related

- [Scenario: Override Supersede](../../conformance/scenarios/override-supersede/)
- [REQ-002: Override Supersession Tracking](../../traceability/requirements.md#req-002-override-supersession-tracking)
- [GAP-001: Nightscout lacks override supersession tracking](../../traceability/gaps.md#gap-001-nightscout-lacks-override-supersession-tracking)
