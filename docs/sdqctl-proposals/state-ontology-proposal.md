# State Ontology Proposal: Observed / Desired / Control

> **Status**: PROPOSED  
> **Created**: 2026-01-30  
> **Purpose**: Clarify conceptual distinction between observed state, desired state, and control decisions across the ecosystem

---

## Problem Statement

Current documentation conflates three distinct concepts:

1. **Observed State**: What actually happened (sensor readings, actual insulin delivered, actual glucose values)
2. **Desired State**: What the user/clinician wants (therapy settings, profiles, target ranges)
3. **Control Decisions**: What the algorithm recommends (temp basal suggestions, SMB recommendations)

This conflation leads to:
- Unclear data flow diagrams
- Confusing sync semantics (what is being synchronized?)
- Difficulty prioritizing interoperability gaps

---

## Proposed Ontology

### Observed State (What Happened)

Data representing actual events and measurements:

| Collection | Examples | Source |
|------------|----------|--------|
| `entries` | SGV readings, calibrations | CGM sensor |
| `treatments` (subset) | Delivered boluses, actual carbs eaten | Pump, user input |
| `devicestatus` (subset) | Battery levels, reservoir status | Device reports |

**Sync semantics**: Push from source → Nightscout → consumers. Immutable once recorded.

### Desired State (What User Wants)

User/clinician configuration of therapy:

| Collection | Examples | Source |
|------------|----------|--------|
| `profile` | Basal rates, ISF, CR schedules | User configuration |
| `treatments` (subset) | Temporary targets, overrides | User intent |
| `settings` | Alarm thresholds, display preferences | App configuration |

**Sync semantics**: Bidirectional sync with conflict resolution. Mutable.

### Control Decisions (What Algorithm Recommends)

Algorithm outputs and reasoning:

| Collection | Examples | Source |
|------------|----------|--------|
| `devicestatus.loop` | Predicted glucose, recommended temp | Loop algorithm |
| `devicestatus.openaps` | IOB/COB curves, enacted changes | oref0/oref1 algorithm |
| `treatments` (subset) | Auto-enacted temp basals, SMBs | Algorithm action |

**Sync semantics**: Push from controller → Nightscout. Read-only for other systems.

---

## Current Documentation Gaps

### Conflation Examples

1. **`treatments` collection**: Contains all three types mixed together
   - Observed: Delivered bolus with `deliveredUnits`
   - Desired: Temporary target with `targetTop`/`targetBottom`
   - Control: Auto-enacted temp basal with `automatic: true`

2. **`devicestatus`**: Contains both observed and control
   - Observed: Battery level, reservoir volume
   - Control: Prediction curves, enacted decisions

3. **Profile vs ProfileSwitch**: Conflates desired state with state change events

### Restructuring Opportunities

| Current Doc | Proposed Split |
|-------------|----------------|
| `treatments-deep-dive.md` | `observed-events.md`, `user-intents.md`, `control-actions.md` |
| `sync-identity-*.md` | By state type (different sync patterns) |
| `devicestatus-deep-dive.md` | `device-telemetry.md`, `algorithm-output.md` |

---

## Implementation Phases

### Phase 1: Ontology Definition

- [ ] Create `docs/architecture/state-ontology.md` defining the three categories
- [ ] Map each Nightscout collection/field to ontology category
- [ ] Document sync semantics per category

### Phase 2: Gap Classification

- [ ] Classify existing GAP-* IDs by ontology category
- [ ] Identify gaps that cross categories (these are the hard sync problems)
- [ ] Update gap descriptions with ontology context

### Phase 3: Documentation Restructure

- [ ] Create state-based navigation in docs
- [ ] Update terminology matrix with ontology column
- [ ] Revise deep-dives to clarify state type per section

### Phase 4: Tool Updates

- [ ] Add ontology category to `x-aid-*` OpenAPI extensions
- [ ] Update verification tools to validate ontology consistency
- [ ] Generate state flow diagrams from specs

---

## Acceptance Criteria

1. Every Nightscout field is classified into exactly one ontology category
2. Sync semantics are documented per category (not per collection)
3. GAP-* IDs include ontology context in description
4. At least one restructured doc demonstrates the pattern

---

## Related Work

- [statespan-standardization-proposal.md](statespan-standardization-proposal.md) - StateSpan provides temporal querying by category
- [adr-004-profile-override-mapping.md](../90-decisions/adr-004-profile-override-mapping.md) - Profile is desired state; ProfileSwitch is state change event
- `mapping/cross-project/terminology-matrix.md` - Terms already partially categorized

---

## Open Questions

1. Should `control decisions` be split into `recommended` vs `enacted`?
2. How do follower apps (read-only) map to this ontology?
3. Does StateSpan replace the need for some ontology clarity?
