# Gaps

This document tracks gaps that block scenario implementation or conformance. These are not ideas or wish-list items—only concrete blockers.

## Active Gaps

### GAP-001: Nightscout lacks override supersession tracking

**Scenario**: [Override Supersede](../conformance/scenarios/override-supersede/)

**Description**: When a new override is created while another is active, Nightscout does not automatically mark the previous override as superseded. The old override simply expires based on duration.

**Impact**: 
- Cannot query "what override was active at time T" reliably
- No audit trail of override changes
- Data imported from Loop/Trio loses supersession relationships

**Possible Solutions**:
1. Add `superseded_by` and `superseded_at` fields to override documents
2. Create a new event type for supersession events
3. Handle in API layer rather than storage

**Status**: Under discussion

**Related**: 
- [ADR-001](../docs/90-decisions/adr-001-override-supersession.md)

---

### GAP-002: AAPS ProfileSwitch vs Override semantic mismatch

**Scenario**: [Override Supersede](../conformance/scenarios/override-supersede/)

**Description**: AAPS uses `ProfileSwitch` events rather than explicit overrides. A ProfileSwitch with percentage != 100 or modified targets functions like an override but has different semantics.

**Impact**:
- Mapping from AAPS data to alignment schema requires inference
- Some override patterns (like "return to normal after X hours") aren't explicit

**Possible Solutions**:
1. Define mapping rules for ProfileSwitch → Override conversion
2. Accept ProfileSwitch as a valid alternative representation
3. Create hybrid schema that accommodates both patterns

**Status**: Needs ADR

---

## Resolved Gaps

_None yet._

---

## Template

```markdown
### GAP-XXX: [Brief title]

**Scenario**: [Link to scenario]

**Description**: [What's missing or ambiguous]

**Impact**: 
- [How this blocks progress]

**Possible Solutions**:
1. [Option A]
2. [Option B]

**Status**: [Under discussion | Needs ADR | Resolved | Won't fix]

**Related**: [Links to ADRs, issues, etc.]
```
