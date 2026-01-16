# Requirements

This document captures requirements derived from scenarios. Each requirement is testable and linked to the scenarios that depend on it.

## Format

Requirements follow the pattern:
- **ID**: REQ-XXX
- **Statement**: The system MUST/SHOULD/MAY...
- **Rationale**: Why this matters
- **Scenarios**: Which scenarios depend on this
- **Verification**: How to test this

---

## Override Requirements

### REQ-001: Override Identity

**Statement**: Every override MUST have a unique, stable identifier that persists across system restarts and data synchronization.

**Rationale**: Required for supersession tracking and cross-system data correlation.

**Scenarios**: 
- [Override Supersede](../conformance/scenarios/override-supersede/)

**Verification**: 
- Create override, restart system, query override by ID
- Sync override to another system, verify ID preserved

---

### REQ-002: Override Supersession Tracking

**Statement**: When an override is superseded, the system MUST record:
1. The ID of the superseding override
2. The timestamp of supersession
3. Update the status to "superseded"

**Rationale**: Enables accurate historical queries and audit trails.

**Scenarios**:
- [Override Supersede](../conformance/scenarios/override-supersede/)

**Verification**:
- Create override A
- Create override B while A is active
- Query A and verify supersession fields

---

### REQ-003: Override Status Transitions

**Statement**: Override status MUST follow valid transitions:
- `active` → `completed` (duration elapsed)
- `active` → `cancelled` (user cancellation)
- `active` → `superseded` (new override activated)

**Rationale**: Prevents invalid states and ensures consistent behavior.

**Scenarios**:
- [Override Supersede](../conformance/scenarios/override-supersede/)

**Verification**:
- Attempt invalid transitions and verify rejection
- Verify valid transitions succeed

---

## Timestamp Requirements

### REQ-010: UTC Timestamps

**Statement**: All timestamps MUST be in ISO 8601 format with UTC timezone (Z suffix or +00:00).

**Rationale**: Eliminates timezone ambiguity in multi-device, multi-region scenarios.

**Scenarios**: All

**Verification**:
- Parse timestamps from all event types
- Verify timezone handling across DST boundaries

---

## Data Integrity Requirements

### REQ-020: Event Immutability

**Statement**: Once created, the core identity and timestamp of an event MUST NOT be modified. Only status and relationship fields may be updated.

**Rationale**: Ensures audit trail integrity and reproducible queries.

**Scenarios**: All

**Verification**:
- Attempt to modify event timestamp
- Verify rejection or versioning

---

## Template

```markdown
### REQ-XXX: [Title]

**Statement**: [The system MUST/SHOULD/MAY...]

**Rationale**: [Why this matters]

**Scenarios**: 
- [Link to scenarios]

**Verification**: 
- [Test steps]
```
