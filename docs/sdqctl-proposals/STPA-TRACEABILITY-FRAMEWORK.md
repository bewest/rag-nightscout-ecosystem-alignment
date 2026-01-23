# Proposal: STPA-Based Traceability Framework for FDA-Compatible QMS

> **Status**: Draft / Discussion  
> **Date**: 2026-01-23  
> **Author**: Ecosystem alignment initiative  
> **Scope**: FDA Design Controls, STPA hazard analysis, cross-project traceability

---

## Executive Summary

This proposal outlines a framework for achieving FDA-compatible traceability in the Nightscout AID ecosystem using **STPA (Systems-Theoretic Process Analysis)** as the organizing methodology. STPA is particularly suited for AID systems because they are inherently control systems with feedback loops.

**Key insight**: The AID ecosystem already has traceability infrastructure (REQ-NNN, GAP-XXX, ADRs). What's missing is the **hazard analysis** that links safety requirements to system control structures.

---

## Problem Statement

### Current State

The rag-nightscout-ecosystem-alignment workspace tracks:
- ~60 requirements (REQ-NNN format)
- ~50 gaps (GAP-XXX-NNN format)
- 3 Architecture Decision Records (ADRs)
- Conformance scenarios with test assertions
- Cross-project terminology matrix

**What's missing for FDA Design Controls (21 CFR 820.30):**

| FDA Requirement | Current Status |
|-----------------|----------------|
| Design Inputs documented | Partial (REQ-NNN) |
| Design Outputs traced to inputs | Missing |
| Verification evidence | Partial (scenarios) |
| Risk analysis (hazards identified) | Missing |
| Traceability matrix | Partial (gen_traceability.py) |

### Why STPA?

STPA is a hazard analysis technique that asks: "What unsafe control actions could the system take?"

For AID systems, this maps directly to:
- **Controller**: Loop, AAPS, Trio, oref0/oref1 algorithm
- **Controlled Process**: Human body glucose regulation
- **Actuator**: Insulin pump
- **Sensor**: CGM (Dexcom, Libre, etc.)
- **Control Actions**: Basal rate, bolus, temp target, override, suspend

Unlike FMEA (failure modes), STPA captures:
- Software logic errors (not just hardware failures)
- Timing issues (action too early/late)
- Missing actions (system should have acted but didn't)
- Context-dependent hazards

---

## The AID Control Loop

```
┌─────────────────────────────────────────────────────────────────┐
│                     CONTROLLER (Loop/AAPS/Trio)                 │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐         │
│  │  Algorithm  │ →  │   Safety    │ →  │  Command    │         │
│  │  (oref0/1)  │    │   Limits    │    │  Generator  │         │
│  └─────────────┘    └─────────────┘    └─────────────┘         │
└────────────────────────────┬────────────────────────────────────┘
                             │ Control Actions
                             │ (basal rate, bolus, temp target)
                             ↓
┌─────────────────────────────────────────────────────────────────┐
│                    CONTROLLED PROCESS (Human Body)              │
│  Blood Glucose ← Insulin Absorption ← Pump Delivery             │
└────────────────────────────┬────────────────────────────────────┘
                             │ Feedback
                             │ (CGM readings every 5 min)
                             ↓
┌─────────────────────────────────────────────────────────────────┐
│                         SENSORS (CGM)                           │
│  Dexcom G6/G7, Libre 2/3, Medtronic Guardian, etc.             │
└─────────────────────────────────────────────────────────────────┘
```

### Control Actions in AID Systems

| Control Action | Source | Safety Impact |
|----------------|--------|---------------|
| Set basal rate | Algorithm | Hypoglycemia if too high, hyperglycemia if too low |
| Deliver bolus | User + Algorithm (SMB) | Immediate hypoglycemia risk |
| Set temp target | User (override) | Affects algorithm behavior |
| Suspend delivery | Safety limit or user | Hyperglycemia if prolonged |
| Resume delivery | Automatic or user | Hypoglycemia if BG already dropping |

---

## STPA Unsafe Control Actions (UCAs)

For each control action, STPA systematically asks:

| # | UCA Type | Question |
|---|----------|----------|
| 1 | Not provided | Is there a hazard if this action is NOT taken when needed? |
| 2 | Provided incorrectly | Is there a hazard if this action IS taken when NOT needed? |
| 3 | Wrong timing | Is there a hazard if this action is taken too early or too late? |
| 4 | Wrong duration | Is there a hazard if this action stops too soon or continues too long? |

### Example: Bolus Delivery

| UCA # | UCA Type | Unsafe Control Action | Hazard |
|-------|----------|----------------------|--------|
| UCA-BOLUS-001 | Not provided | Bolus not delivered when carbs entered | Hyperglycemia |
| UCA-BOLUS-002 | Provided incorrectly | Bolus delivered when BG < 70 mg/dL | Severe hypoglycemia |
| UCA-BOLUS-003 | Provided incorrectly | Double bolus due to sync failure | Severe hypoglycemia |
| UCA-BOLUS-004 | Wrong timing | Bolus delayed > 15 min after carbs | Postprandial spike |
| UCA-BOLUS-005 | Wrong duration | Bolus not fully delivered (partial) | Hyperglycemia |

### Mapping Existing GAPs to UCAs

| Existing GAP | Related UCA |
|--------------|-------------|
| GAP-003: No unified sync identity | UCA-BOLUS-003 (double bolus) |
| GAP-001: Override supersession missing | UCA-OVERRIDE-002 (conflicting targets) |
| GAP-TREAT-012: Cross-controller bolus | UCA-BOLUS-003 (double dose) |

**Key insight**: Many existing GAPs describe *causal factors* for UCAs, but the link isn't explicit.

---

## Proposed Framework Structure

### New Traceability Artifacts

```
traceability/
├── stpa/
│   ├── README.md                      # STPA methodology overview
│   ├── control-structure.md           # Step 2: Define control loops
│   ├── unsafe-control-actions.md      # Step 3: UCA catalog by control action
│   ├── causal-factors.md              # Step 4: Why UCAs might occur
│   └── safety-constraints.md          # Step 5: Derived requirements
│
├── requirements.md                    # Existing (add UCA: references)
├── gaps.md                           # Existing (add CF: references)
├── design-trace.md                   # NEW: REQ → Module → Test matrix
└── verification-matrix.md            # NEW: Test → Requirement coverage
```

### Linking Convention

```markdown
## UCA-BOLUS-003: Double bolus due to sync failure

**Control Action**: Deliver bolus  
**Type**: Provided incorrectly (when not needed)  
**Hazard**: Severe hypoglycemia from insulin stacking  
**Severity**: Critical (life-threatening)  

**Causal Factors**:
- CF-SYNC-001: POST-based upload creates duplicates (see GAP-003)
- CF-SYNC-002: No client-side sync acknowledgment

**Safety Constraints**:
- SC-BOLUS-003a: System SHALL deduplicate boluses by syncIdentifier
- SC-BOLUS-003b: System SHALL NOT accept bolus if identical ID exists within 5 minutes

**Requirements Derived**:
- REQ-020: Sync Identity (existing)
- REQ-XXX: Bolus deduplication (NEW)

**Verification**:
- TEST-BOLUS-003: Duplicate bolus rejection test
```

---

## Scope: Essential vs Future Work

### Tier 1: Safety-Critical (Essential)

Projects where software errors could directly cause hypoglycemia or hyperglycemia:

| Project | Role | Priority |
|---------|------|----------|
| **Loop** | AID Controller | P0 - Essential |
| **AAPS** | AID Controller | P0 - Essential |
| **Trio** | AID Controller | P0 - Essential |
| **oref0** | Core Algorithm | P0 - Essential |
| **Nightscout** | Data Hub (dosing decisions flow through) | P1 - High |

### Tier 2: Safety-Relevant (Future Work)

Projects that affect data quality but don't directly issue dosing commands:

| Project | Role | Priority |
|---------|------|----------|
| xDrip+ | CGM data collection | P2 - Important |
| xDrip4iOS | CGM data collection | P2 - Important |
| DiaBLE | Libre sensor interface | P2 - Important |
| Nightscout Connect | Data bridge | P3 - Moderate |

### Tier 3: Monitoring/Display (Deferred)

Projects that display but don't control:

| Project | Role | Priority |
|---------|------|----------|
| LoopFollow | Caregiver monitoring | P4 - Low |
| LoopCaregiver | Remote commands | P2 - Important (has control) |
| Nightguard | Watch display | P4 - Low |
| Nightscout Reporter | PDF reports | P5 - Lowest |

---

## Integration with sdqctl

### Proposed Workflows

#### 1. STPA Audit Workflow

```dockerfile
# stpa-audit.conv - Analyze component for UCAs
MODEL claude-sonnet-4.5
MAX-CYCLES 2

@traceability/stpa/control-structure.md
@traceability/stpa/unsafe-control-actions.md
@externals/{{PROJECT}}/{{MODULE}}

PROMPT Analyze this code module for control actions.
       For each control action found:
       1. Identify if UCAs already cataloged in unsafe-control-actions.md
       2. If not, propose new UCAs using the 4-question framework
       3. Cross-reference with existing GAPs
       
       Output format: YAML with UCA-IDs, descriptions, severity, related-gaps

RUN python tools/validate_uca_refs.py {{PROJECT}}
ELIDE
PROMPT Review validation output. Are all UCAs properly linked to requirements?
```

#### 2. Traceability Verification Workflow

```dockerfile
# trace-verification.conv - Validate trace completeness
MODEL gpt-4
MAX-CYCLES 1

@traceability/design-trace.md
@traceability/requirements.md

RUN python tools/gen_traceability.py --json
PROMPT Analyze the traceability matrix:
       1. Which requirements have no linked tests?
       2. Which tests don't trace to requirements?
       3. Which UCAs lack safety constraints?
       
       Prioritize gaps by severity rating.
```

### Tool Enhancements Needed

| Tool | Current State | Enhancement |
|------|---------------|-------------|
| `gen_traceability.py` | REQ → doc links | Add UCA, SC, CF linking |
| `verify_refs.py` | Validates doc refs | Add STPA reference validation |
| `query_workspace.py` | Search docs | Add `--uca` and `--severity` filters |

---

## Implementation Phases

### Phase 1: Foundation (Weeks 1-2)
- [ ] Create `traceability/stpa/README.md` with methodology
- [ ] Create `traceability/stpa/control-structure.md` for Tier 1 projects
- [ ] Draft UCA catalog for ONE control action (bolus)
- [ ] Validate linking convention works

**Deliverable**: Proof-of-concept STPA analysis for bolus delivery

### Phase 2: Catalog (Weeks 3-4)
- [ ] Complete UCA catalog for all Tier 1 control actions
- [ ] Add UCA: references to existing requirements
- [ ] Add CF: references to existing gaps
- [ ] Create safety-constraints.md

**Deliverable**: Complete UCA catalog for Tier 1 projects

### Phase 3: Tooling (Weeks 5-6)
- [ ] Enhance gen_traceability.py for STPA links
- [ ] Create stpa-audit.conv workflow
- [ ] Create trace-verification.conv workflow
- [ ] Add CI validation for trace completeness

**Deliverable**: Automated STPA traceability validation

### Phase 4: Integration (Weeks 7-8)
- [ ] Evaluate experimental_qms merge strategy
- [ ] Generate QMS-format documents from traceability
- [ ] Document severity classification (ISO 14971 alignment)
- [ ] Create templates for Tier 2 projects

**Deliverable**: FDA-compatible traceability package

---

## Open Questions for Discussion

### 1. Severity Classification Standard

**Options**:
- **ISO 14971**: Negligible, Minor, Serious, Critical, Catastrophic
- **IEC 62304**: Class A (no injury), B (non-serious injury), C (death/serious injury)
- **Custom**: Map to diabetes-specific outcomes (mild hypo, severe hypo, DKA)

**Recommendation**: Use IEC 62304 classes for software classification, ISO 14971 for harm severity.

### 2. Artifact Location

**Options**:
- **A**: All STPA artifacts in rag-nightscout-ecosystem-alignment
- **B**: Analysis in rag-nightscout, formal docs in experimental_qms
- **C**: Separate stpa-analysis repo

**Recommendation**: Option B - analysis close to code, formal docs in QMS.

### 3. Scope of "Nightscout" Analysis

Nightscout is a data hub, not a controller. But:
- Incorrect data could cause incorrect dosing decisions
- Data loss could affect safety (no CGM = open loop)

**Recommendation**: Treat Nightscout as "data integrity" scope, not "control" scope.

### 4. Who Maintains STPA Artifacts?

**Options**:
- Core team maintains centrally
- Each project maintains their own
- AI-assisted with human review

**Recommendation**: AI-assisted initial analysis, human review for safety-critical UCAs.

---

## Relationship to Other Proposals

### LITERATE-TRACEABLE-SYSTEM-PROPOSAL.md

That proposal focuses on:
- Extracting assertions from documentation
- Validating code examples match source
- Multi-faceted analysis automation

**Synergy**: STPA artifacts become another "facet" in the 5-facet methodology.

### sdqctl VERIFICATION-DIRECTIVES

The proposed VERIFY directive could:
- Check UCA → REQ links exist
- Validate severity ratings are assigned
- Confirm test coverage for safety constraints

### sdqctl PIPELINE-ARCHITECTURE

External transformation (jsonnet) could:
- Select workflows based on project tier (Tier 1 = more rigorous)
- Filter UCA analysis by severity
- Generate project-specific audit scope

---

## Success Criteria

1. **Completeness**: ≥90% of Tier 1 control actions have UCA analysis
2. **Linkage**: ≥80% of existing REQ-NNN linked to UCAs or marked "functional-only"
3. **Automation**: CI can validate trace completeness
4. **Usability**: New contributors can add UCAs using templates
5. **FDA-ready**: Traceability matrix satisfies 21 CFR 820.30 structure

---

## References

- **STPA Handbook**: [MIT Partnership for Systems Approaches to Safety and Security](https://psas.scripts.mit.edu/home/materials/)
- **FDA Design Controls**: 21 CFR 820.30
- **IEC 62304:2006+AMD1:2015**: Medical device software lifecycle
- **ISO 14971:2019**: Risk management for medical devices
- **OpenAPS Safety**: [OpenAPS docs - Understanding your loop](https://openaps.readthedocs.io/en/latest/docs/Understanding%20Your%20Loop/)

---

## Appendix A: UCA Catalog Template

```markdown
## UCA-{ACTION}-{NNN}: {Brief description}

**Control Action**: {Basal | Bolus | TempTarget | Override | Suspend | Resume}  
**Type**: {Not provided | Provided incorrectly | Wrong timing | Wrong duration}  
**Hazard**: {What harm could occur}  
**Severity**: {Class A | Class B | Class C} (per IEC 62304)  
**Likelihood**: {Rare | Unlikely | Possible | Likely | Almost Certain}  

**Causal Factors**:
- CF-{CATEGORY}-{NNN}: {Description} (see GAP-{XXX})

**Safety Constraints**:
- SC-{ACTION}-{NNN}a: System SHALL {requirement}
- SC-{ACTION}-{NNN}b: System SHALL NOT {negative requirement}

**Requirements**:
- REQ-{NNN}: {Existing requirement} (if applicable)
- REQ-{NNN}: {New requirement derived} (if needed)

**Verification**:
- TEST-{ACTION}-{NNN}: {Test scenario reference}

**Projects Affected**:
- [ ] Loop
- [ ] AAPS
- [ ] Trio
- [ ] Nightscout
```

---

## Appendix B: Control Action Inventory (Tier 1)

| Control Action | Controller | Actuator | Safety Impact |
|----------------|------------|----------|---------------|
| Set scheduled basal | Loop/AAPS/Trio | Pump | Background insulin |
| Set temp basal | Loop/AAPS/Trio | Pump | Algorithm adjustment |
| Deliver bolus | User + Algorithm | Pump | Immediate insulin |
| Super Micro Bolus (SMB) | Algorithm | Pump | Automatic correction |
| Set temp target | User (override) | Algorithm | Target BG range |
| Activate override | User | Algorithm | Modified parameters |
| Suspend delivery | Safety/User | Pump | Stop all insulin |
| Resume delivery | Auto/User | Pump | Restart insulin |
| Close loop | Algorithm | All | Full automation |
| Open loop | User/Safety | All | Manual mode |

---

**Document Version**: 0.1  
**Last Updated**: 2026-01-23  
**Status**: Draft for discussion
