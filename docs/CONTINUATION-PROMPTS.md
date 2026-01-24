# Continuation Prompts for Nightscout Ecosystem Work

**Date:** 2026-01-22  
**Purpose:** Ready-to-use prompts for continuing research and documentation work

---

## How to Use These Prompts

Copy a prompt below, paste it into your AI coding assistant (GitHub Copilot CLI, Replit AI, etc.), and customize the placeholder values:
- `{{COMPONENT}}` - Component name (e.g., "treatments", "devicestatus", "bolus-wizard")
- `{{PROJECT}}` - Project name (e.g., "Loop", "AAPS", "Trio", "xDrip")
- `{{GAP-ID}}` - Gap identifier (e.g., "GAP-SYNC-001")
- `{{REQ-ID}}` - Requirement identifier (e.g., "REQ-042")

---

## Discovery Prompts

### Start a New Component Analysis

```
Analyze the {{COMPONENT}} implementation across the Nightscout ecosystem.

Follow the 5-facet methodology:
1. **Terminology** - Extract and map terms to mapping/cross-project/terminology-matrix.md
2. **Gaps** - Document undocumented behaviors in traceability/gaps.md
3. **Requirements** - Extract testable requirements to traceability/requirements.md  
4. **Deep Dive** - Create docs/10-domain/{{COMPONENT}}-deep-dive.md
5. **Progress** - Log this session in progress.md

Start by exploring:
- externals/cgm-remote-monitor/ for Nightscout implementation
- externals/LoopWorkspace/ for Loop implementation
- externals/AndroidAPS/ for AAPS implementation
- externals/Trio/ for Trio implementation

For each project, find:
- Where {{COMPONENT}} is defined
- Key data structures and types
- How it syncs to Nightscout
- Differences from other implementations
```

### Explore a Specific Project

```
Deep dive into {{PROJECT}}'s implementation of {{COMPONENT}}.

1. Find the source files in externals/{{PROJECT}}/
2. Document:
   - File locations and key classes/functions
   - Data structures and field names
   - API endpoints or sync methods
   - Any unique behaviors

3. Update mapping/{{PROJECT}}/README.md with findings
4. Add new terms to terminology-matrix.md
5. Note any gaps for traceability/gaps.md

Reference format for code:
- Use `alias:Full/Path/To/File.ext#L123` for line references
- Example: `loop:LoopKit/LoopKit/TemporaryScheduleOverride.swift#L45`
```

### Compare Implementations

```
Compare {{COMPONENT}} across Loop, AAPS, and Trio.

For each project, document:
1. Field names and types
2. Sync identifiers (syncIdentifier, pumpId, etc.)
3. Timestamp formats and handling
4. Deduplication strategy

Create a comparison table:
| Aspect | Loop | AAPS | Trio | Nightscout |
|--------|------|------|------|------------|
| ... | ... | ... | ... | ... |

Identify:
- Same concept, different names → add to terminology-matrix.md
- Same name, different semantics → document as GAP
- Missing in some projects → document as GAP

Update mapping/cross-project/field-mapping.md with findings.
```

---

## Gap Resolution Prompts

### Analyze an Existing Gap

```
Analyze {{GAP-ID}} from traceability/gaps.md.

1. Read the gap description
2. Research affected systems in externals/
3. Find actual implementations to understand:
   - Why this behavior is undocumented
   - What the expected behavior should be
   - How different projects handle it

4. Recommend resolution:
   - Can this be standardized?
   - What should be documented?
   - Are code changes needed?

5. If resolved, update gap status
6. If requirements emerge, add to requirements.md
```

### Find Gaps in OpenAPI Specs

```
Review specs/openapi/ for undocumented gaps.

Check each spec file for:
1. Fields without x-aid-gap annotations that should have them
2. Missing x-aid-controllers (which systems use this field?)
3. Undocumented eventTypes in treatments
4. Missing validation rules

For each gap found:
1. Assign GAP-ID (GAP-SPEC-NNN)
2. Document in traceability/gaps.md
3. Add x-aid-gap to the spec if appropriate

Format:
```yaml
newField:
  type: string
  x-aid-gap: GAP-SPEC-001
  x-aid-controllers: [loop, aaps, trio]
```
```

### Cross-Project Sync Gap Analysis

```
Analyze synchronization gaps between {{PROJECT}} and Nightscout.

Focus on:
1. What data does {{PROJECT}} upload?
2. What format does Nightscout expect?
3. Where are there mismatches?

Check for:
- Field naming inconsistencies
- Missing required fields
- Extra fields ignored by Nightscout
- Timestamp/timezone handling
- Deduplication key mismatches

Document findings as GAP-SYNC-NNN in gaps.md.
Update mapping/{{PROJECT}}/nightscout-sync.md.
```

---

## Requirement Prompts

### Extract Requirements from Gap

```
Convert {{GAP-ID}} into formal requirements.

1. Read the gap in traceability/gaps.md
2. Identify testable requirements:
   - What MUST the system do?
   - What acceptance criteria apply?
   - How can this be verified?

3. For each requirement, use format:

### REQ-NNN: [Title]

**Source Gap**: {{GAP-ID}}
**Status**: Draft
**Priority**: P0 | P1 | P2
**Type**: Functional | Interface | Compatibility

**Statement**: The system SHALL [specific behavior].

**Acceptance Criteria**:
1. Given [precondition], when [action], then [result]

**Verification**: Test | Inspection | Analysis

4. Add to traceability/requirements.md
5. Update gap with link to requirement
```

### Create Conformance Scenario

```
Create a conformance test scenario for {{REQ-ID}}.

1. Read the requirement in requirements.md
2. Design a test scenario:

# Scenario: [Descriptive Name]

## Metadata
- Requirement: {{REQ-ID}}
- Systems: Loop, AAPS, Trio
- Priority: P0 | P1 | P2

## Preconditions
- [Setup required]

## Test Steps
1. Given [initial state]
2. When [action]
3. Then [expected outcome]

## Edge Cases
- [Edge case 1]
- [Edge case 2]

3. Save to conformance/scenarios/[category]/[name].md
4. Create fixture data if needed
5. Update requirement with scenario link
```

---

## Terminology Prompts

### Standardize a Term

```
Standardize the term "{{TERM}}" across projects.

1. Find all usages in externals/
2. Document variants in each project:
   - Loop calls it: ?
   - AAPS calls it: ?
   - Trio calls it: ?
   - Nightscout calls it: ?

3. Choose canonical name (prefer Nightscout's)
4. Update terminology-matrix.md:

| Term | Category | Loop | AAPS | Trio | Nightscout | Notes |
|------|----------|------|------|------|------------|-------|
| {{TERM}} | [cat] | [variant] | [variant] | [variant] | [canonical] | [notes] |

5. Document deprecated terms
6. Note any GAPs if semantics differ
```

### Build Terminology for Feature Area

```
Document all terminology for {{FEATURE_AREA}}.

Examples: CGM data, bolus handling, temp basals, predictions

1. Find all related terms in externals/
2. Categorize:
   - Data fields (what's stored)
   - Event types (what happens)
   - States (system status)
   - Calculations (derived values)

3. For each term:
   - Name in each project
   - Type/format
   - When it's used
   - How it syncs

4. Add to terminology-matrix.md
5. Note any gaps or inconsistencies
```

---

## Documentation Prompts

### Update Deep Dive Document

```
Update docs/10-domain/{{COMPONENT}}-deep-dive.md.

Verify and update each section:

## 1. Overview
- Is the description accurate?
- Any new features to document?

## 2. Architecture
- Are diagrams current?
- Any structural changes?

## 3. Key Data Structures
- All fields documented?
- Types accurate?

## 4. Integration Points
- All sync paths documented?
- API endpoints current?

## 5. Code References
- Do all file:line refs resolve?
- Update stale references

## 6. Related Requirements
- Link to requirements.md
- Note REQ-IDs

## 7. Known Gaps
- Link to gaps.md
- Note GAP-IDs

Log updates in progress.md.
```

### Create New Deep Dive

```
Create a new deep dive document for {{COMPONENT}}.

Template structure:

# {{COMPONENT}} Deep Dive

## Overview
Brief description of what this component does.

## Architecture
- System context diagram
- Key components and relationships

## Key Data Structures

### [Structure Name]
| Field | Type | Description |
|-------|------|-------------|
| ... | ... | ... |

## Implementation Details

### Loop
- Location: `loop:LoopKit/LoopKit/TemporaryScheduleOverride.swift`
- Key behavior: ...

### AAPS
- Location: `aaps:database/impl/src/main/kotlin/app/aaps/database/entities/TemporaryTarget.kt`
- Key behavior: ...

### Nightscout
- Location: `crm:lib/server/treatments.js`
- Key behavior: ...

## Integration Points
How this component syncs/communicates.

## Related Requirements
- REQ-NNN: ...

## Known Gaps
- GAP-XXX-NNN: ...

## References
- [External doc links]

Save to docs/10-domain/{{COMPONENT}}-deep-dive.md.
Log in progress.md.
```

---

## Verification Prompts

### Run Full Verification

```
Run the full verification suite and analyze results.

1. Execute verification tools (if available):
   - python tools/verify_refs.py --json
   - python tools/verify_coverage.py --json
   - python tools/verify_terminology.py --json
   - python tools/verify_assertions.py --json

2. Analyze each result:
   - What issues were found?
   - What's the priority?
   - What can be fixed immediately?

3. For immediate fixes:
   - Update broken references
   - Add missing links
   - Correct terminology

4. For issues needing more work:
   - Create GAPs if appropriate
   - Add to progress.md next steps

5. Generate summary in traceability/verification-report.md
```

### Fix Broken References

```
Fix broken code references in documentation.

1. Run: python tools/verify_refs.py --json
2. For each broken reference:
   - What file was expected?
   - Did the file move, rename, or get deleted?
   - Find the correct location

3. Update references in format:
   - Old: project:old/path/file.ext#L123
   - New: project:new/path/file.ext#L456

4. If file no longer exists:
   - Remove the reference OR
   - Find equivalent functionality OR
   - Note as GAP if feature removed

5. Re-run verify_refs to confirm fixes
```

---

## Progress Prompts

### Log a Session

```
Log today's work session in progress.md.

Format:

### {{TOPIC}} (YYYY-MM-DD)

Brief description of what was analyzed or documented.

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| [Name] | `docs/10-domain/component-deep-dive.md` | One-line summary |
| ... | ... | ... |

**Gaps Identified**: GAP-XXX-001, GAP-XXX-002 (or "None")
**Requirements Extracted**: REQ-NNN (or "None")
**Next Steps**: What should be done next

Add under "## Completed Work" in chronological order (newest first).
```

### Plan Next Session

```
Review progress.md and plan the next work session.

1. Review recent entries:
   - What was completed?
   - What "Next Steps" were noted?
   - Any blockers or dependencies?

2. Check open gaps:
   - Which have highest priority?
   - Which are ready for work?

3. Check requirement coverage:
   - Which requirements need scenarios?
   - Which need implementation verification?

4. Suggest next session focus:
   - Component to analyze
   - Gaps to resolve
   - Documentation to update

5. List specific actions for next session
```

---

## Quick Reference

| Task | Start With |
|------|------------|
| New component | "Start a New Component Analysis" |
| Specific project | "Explore a Specific Project" |
| Compare projects | "Compare Implementations" |
| Resolve a gap | "Analyze an Existing Gap" |
| Create requirement | "Extract Requirements from Gap" |
| Add terminology | "Standardize a Term" |
| Update docs | "Update Deep Dive Document" |
| Run checks | "Run Full Verification" |
| Log work | "Log a Session" |

---

## See Also

- [NIGHTSCOUT-SDQCTL-GUIDE.md](./NIGHTSCOUT-SDQCTL-GUIDE.md) - sdqctl workflow guide
- [workflows/README.md](../workflows/README.md) - All available workflows
- [TOOLING-GUIDE.md](./TOOLING-GUIDE.md) - Python tool usage
