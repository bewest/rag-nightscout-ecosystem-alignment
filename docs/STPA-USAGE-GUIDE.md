# STPA Usage Guide for Nightscout Ecosystem

> **Version**: 1.0  
> **Created**: 2026-01-27  
> **Work Package**: WP-005 step 4  
> **Audience**: Ecosystem team members performing safety analysis

---

## Introduction

This guide provides a practical workflow for applying **STPA (Systems-Theoretic Process Analysis)** to projects in the Nightscout AID ecosystem. STPA is a hazard analysis technique that identifies unsafe control actions in complex systems.

**Why STPA for AID systems?**

AID (Automated Insulin Delivery) systems are control systems with feedback loops. STPA excels at finding:
- Software logic errors (not just hardware failures)
- Timing issues (action too early/late)
- Missing actions (system should have acted but didn't)
- Context-dependent hazards (safe in one state, dangerous in another)

---

## Quick Start (15 minutes)

### Step 1: Identify the Control Action

Pick ONE control action to analyze. Start with the highest-risk action in your component.

**Common control actions in AID:**
| Control Action | Component | Risk Level |
|----------------|-----------|------------|
| Deliver bolus | Pump driver | High |
| Set temp basal | Algorithm | High |
| Sync treatment | Nightscout client | Medium |
| Display glucose | UI | Low |

### Step 2: Apply the 4-Question Framework

For your chosen control action, ask:

| # | Question | Example (Bolus) |
|---|----------|-----------------|
| 1 | **Not provided** - Hazard if NOT taken when needed? | Hyperglycemia if bolus not delivered for carbs |
| 2 | **Provided incorrectly** - Hazard if taken when NOT needed? | Hypoglycemia if bolus when BG < 70 |
| 3 | **Wrong timing** - Hazard if too early/late? | Postprandial spike if delayed >15 min |
| 4 | **Wrong duration** - Hazard if stops too soon/continues too long? | Hypoglycemia if bolus not cancelled |

### Step 3: Document Your First UCA

Use this minimal template:

```markdown
## UCA-BOLUS-001: Bolus not delivered when carbs entered

**Control Action**: Bolus  
**Type**: Not provided  
**Hazard**: Hyperglycemia from undelivered insulin  
**Severity**: S2 (Moderate)
```

**Congratulations!** You've completed your first UCA. Continue to the full workflow below.

---

## Full Workflow

### Phase 1: Scope Definition

1. **Select project tier**:
   - **Tier 1** (Safety-Critical): Loop, AAPS, Trio, oref0 - Full STPA required
   - **Tier 2** (Safety-Relevant): xDrip+, xDrip4iOS, DiaBLE - Focused STPA
   - **Tier 3** (Monitoring): LoopFollow, Nightguard - Data integrity only

2. **List control actions** in your component using the inventory:

   | Control Action | Actuator | Safety Impact |
   |----------------|----------|---------------|
   | Set scheduled basal | Pump | Background insulin |
   | Set temp basal | Pump | Algorithm adjustment |
   | Deliver bolus | Pump | Immediate insulin |
   | Super Micro Bolus (SMB) | Pump | Automatic correction |
   | Set temp target | Algorithm | Target BG range |
   | Activate override | Algorithm | Modified parameters |
   | Suspend delivery | Pump | Stop all insulin |
   | Resume delivery | Pump | Restart insulin |

3. **Prioritize** by risk: Start with actions that directly affect insulin delivery.

### Phase 2: UCA Discovery

For each control action, systematically work through the 4 questions:

```bash
# Optional: Use sdqctl to structure analysis
sdqctl iterate workflows/stpa-audit.conv --context "Control action: Deliver bolus"
```

**Document each UCA** using the full template:

```markdown
## UCA-{ACTION}-{NNN}: {Brief description}

**Control Action**: {Basal | Bolus | TempTarget | Override | Suspend | Resume}  
**Type**: {Not provided | Provided incorrectly | Wrong timing | Wrong duration}  
**Hazard**: {What harm could occur}  
**Severity**: {S1 | S2 | S3 | S4} (see severity scale below)  
**Likelihood**: {Rare | Unlikely | Possible | Likely | Almost Certain}  

**Causal Factors**:
- CF-{CATEGORY}-{NNN}: {Description} (see GAP-{XXX} if applicable)

**Safety Constraints**:
- SC-{ACTION}-{NNN}a: System SHALL {positive requirement}
- SC-{ACTION}-{NNN}b: System SHALL NOT {negative requirement}

**Projects Affected**:
- [ ] Loop
- [ ] AAPS
- [ ] Trio
- [ ] Nightscout
```

### Phase 3: Derive Safety Constraints

Each UCA should produce 1-2 safety constraints (SCs):

| UCA | Safety Constraint |
|-----|-------------------|
| UCA-BOLUS-002: Bolus when BG < 70 | SC-BOLUS-002: System SHALL NOT deliver bolus when BG < 70 mg/dL |
| UCA-BOLUS-003: Double bolus | SC-BOLUS-003a: System SHALL deduplicate by syncIdentifier |

**Naming convention**: `SC-{ACTION}-{NNN}{letter}`

### Phase 4: Link to Requirements

Connect SCs to existing requirements or create new ones:

```markdown
**Requirements**:
- REQ-020: Sync Identity (existing)
- REQ-XXX: Bolus deduplication (NEW - derived from SC-BOLUS-003a)
```

### Phase 5: Verify Traceability

Run verification tools:

```bash
# Verify all references are valid
make verify-refs

# Check requirement coverage
make verify-coverage

# Generate traceability matrix
python tools/gen_traceability.py --stpa
```

---

## Severity Scale

Use the S1-S4 scale for all UCAs:

| Level | Name | Description | Example |
|-------|------|-------------|---------|
| **S4** | Critical | Death or life-threatening | Double bolus → BG < 40 → unconsciousness |
| **S3** | Serious | Medical intervention required | Bolus when low → glucagon needed |
| **S2** | Moderate | Temporary impairment | Bolus delay → BG spike to 300 |
| **S1** | Minor | Inconvenience only | Display shows wrong bolus history |

**Rule**: When in doubt, rate higher. S3/S4 UCAs require human review.

---

## Templates

### UCA Template (Full)

```markdown
## UCA-{ACTION}-{NNN}: {Brief description}

**Control Action**: {Action name}  
**Type**: {Not provided | Provided incorrectly | Wrong timing | Wrong duration}  
**Hazard**: {Specific harm that could occur}  
**Severity**: {S1 | S2 | S3 | S4}  
**Likelihood**: {Rare | Unlikely | Possible | Likely | Almost Certain}  

**Causal Factors**:
- CF-{CATEGORY}-{NNN}: {Root cause description}
  - Related Gap: GAP-{XXX} (if applicable)
  - Evidence: {Code reference or documentation link}

**Safety Constraints**:
- SC-{ACTION}-{NNN}a: System SHALL {positive requirement}
- SC-{ACTION}-{NNN}b: System SHALL NOT {negative requirement}

**Requirements**:
- REQ-{NNN}: {Requirement text} (existing | NEW)

**Verification**:
- TEST-{ACTION}-{NNN}: {Test scenario or assertion reference}

**Projects Affected**:
- [ ] Loop
- [ ] AAPS  
- [ ] Trio
- [ ] Nightscout
- [ ] {Other}
```

### Safety Constraint Template

```markdown
## SC-{ACTION}-{NNN}: {Brief description}

**Derived From**: UCA-{ACTION}-{NNN}  
**Requirement Type**: {Functional | Safety | Performance}  

**Specification**:
The system SHALL {positive statement} / SHALL NOT {negative statement}.

**Rationale**: {Why this constraint prevents the UCA}

**Verification Method**: {Test | Inspection | Analysis | Demonstration}
```

### Causal Factor Template

```markdown
## CF-{CATEGORY}-{NNN}: {Brief description}

**Related UCA**: UCA-{ACTION}-{NNN}  
**Related Gap**: GAP-{XXX} (if applicable)  

**Description**: {Detailed explanation of root cause}

**Evidence**:
- Source: `{project}:{file}#{lines}`
- Observation: {What was found}

**Mitigation**: {How SC addresses this factor}
```

---

## Integration with Existing Tools

### gen_traceability.py

Generate traceability matrix including STPA artifacts:

```bash
python tools/gen_traceability.py --stpa --output traceability/stpa-matrix.md
```

Output includes:
- UCA → SC links
- SC → REQ links
- REQ → TEST links

### verify_refs.py

Validate STPA artifact references:

```bash
python tools/verify_refs.py --include-stpa
```

Checks:
- All `UCA-XXX` references resolve to definitions
- All `SC-XXX` references resolve to definitions
- All `GAP-XXX` in causal factors exist in gaps.md

### query_workspace.py

Search STPA artifacts:

```bash
# Find all UCAs for bolus
python tools/query_workspace.py --pattern "UCA-BOLUS"

# Find UCAs by severity
python tools/query_workspace.py --pattern "Severity: S4"
```

---

## Common Pitfalls

### 1. Starting Too Broad

❌ **Wrong**: "Analyze the entire Loop app for UCAs"  
✅ **Right**: "Analyze bolus delivery in Loop's pump driver"

**Fix**: Scope to ONE control action at a time.

### 2. Confusing Hazard with Harm

❌ **Wrong**: Hazard = "User might die"  
✅ **Right**: Hazard = "Severe hypoglycemia from double bolus"

**Fix**: Hazard is the unsafe state; harm is the consequence.

### 3. Missing the "Not Provided" Case

Most teams find "provided incorrectly" UCAs but miss "not provided" ones.

**Fix**: Always start with question #1: What if this action is NOT taken when needed?

### 4. Skipping Severity Assignment

UCAs without severity can't be prioritized for mitigation.

**Fix**: Assign severity immediately using the S1-S4 scale.

### 5. Orphan Safety Constraints

SCs that don't link to requirements aren't actionable.

**Fix**: Every SC must link to a REQ (existing or NEW).

### 6. Cross-Project UCAs Treated as Single-Project

Many UCAs span Loop ↔ AAPS ↔ Nightscout (especially sync-related).

**Fix**: Check "Projects Affected" and document cross-project patterns.

---

## STPA Analysis Checklist

Use this checklist before marking analysis complete:

### Scope
- [ ] Project tier identified (Tier 1/2/3)
- [ ] Control actions listed and prioritized
- [ ] Analysis scope documented

### UCA Discovery
- [ ] All 4 questions applied to each control action
- [ ] Each UCA has unique ID (UCA-{ACTION}-{NNN})
- [ ] Severity assigned (S1-S4)
- [ ] Likelihood estimated

### Safety Constraints
- [ ] At least 1 SC per UCA
- [ ] Each SC has unique ID (SC-{ACTION}-{NNN})
- [ ] SHALL/SHALL NOT format used

### Traceability
- [ ] Causal factors linked to GAPs where applicable
- [ ] SCs linked to REQs (existing or NEW)
- [ ] Cross-project UCAs identified
- [ ] `make verify-refs` passes

### Review
- [ ] S3/S4 UCAs reviewed by human domain expert
- [ ] Cross-project patterns checked against `cross-project-patterns.md`
- [ ] Checklist signed off

---

## Cross-Project Patterns

Before creating new UCAs, check if your scenario matches a known pattern:

| Pattern | UCAs | Priority | Reference |
|---------|------|----------|-----------|
| Sync/Deduplication | UCA-BOLUS-003, UCA-CARB-001, UCA-SYNC-001 | P0 | [cross-project-patterns.md](../traceability/stpa/cross-project-patterns.md) |
| Remote Command Safety | UCA-REMOTE-001, UCA-REMOTE-002 | P1 | [cross-project-patterns.md](../traceability/stpa/cross-project-patterns.md) |
| Override Conflicts | UCA-OVERRIDE-001, UCA-OVERRIDE-002 | P2 | [cross-project-patterns.md](../traceability/stpa/cross-project-patterns.md) |

If your UCA fits a pattern, reference the existing SCs rather than creating new ones.

---

## References

### Ecosystem STPA Artifacts
- [Cross-Project Patterns](../traceability/stpa/cross-project-patterns.md) - Shared UCAs and SCs
- [Severity Scale](../../../sdqctl/docs/stpa-severity-scale.md) - S1-S4 definitions
- [STPA Framework](sdqctl-proposals/STPA-TRACEABILITY-FRAMEWORK.md) - Full methodology

### External Resources
- [MIT STPA Handbook](https://psas.scripts.mit.edu/home/materials/) - Authoritative reference
- [ISO 14971:2019](https://www.iso.org/standard/72704.html) - Risk management for medical devices
- [IEC 62304:2006](https://www.iso.org/standard/38421.html) - Medical device software lifecycle

---

## Getting Help

- **Questions**: Add to `docs/OPEN-QUESTIONS.md` with `Source: STPA-analysis`
- **Gaps found**: Add to `traceability/gaps.md` with `Related: UCA-XXX`
- **Tool issues**: File issue in sdqctl repository

---

**Document Version**: 1.0  
**Last Updated**: 2026-01-27
