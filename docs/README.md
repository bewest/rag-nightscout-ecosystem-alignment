# Documentation Organization

This directory contains analysis, research, and decisions extracted from the Nightscout ecosystem source code.

## Philosophy

Documentation follows source code analysis → research synthesis → domain understanding → design proposals → architectural decisions. The structure supports iterative quality system development by organizing artifacts by their maturity and purpose.

## Directory Structure

### 00-overview - Project Context
**What belongs here**: Mission, vision, project scope, stakeholder context

**Purpose**: Orient new contributors to the "why" before the "what"

**Examples**:
- `mission.md` - Project goals and alignment objectives

**Creation trigger**: Initial project setup or major scope changes

---

### 10-domain - Domain Knowledge Base
**What belongs here**: Deep-dive technical analysis extracted from source code, protocol specifications, terminology mappings, comparisons across systems

**Purpose**: Build shared understanding of how systems actually work (not how they should work)

**Examples**:
- `treatments-deep-dive.md` - Analysis of treatment data structures across projects
- `insulin-curves-deep-dive.md` - Insulin action curve implementations
- `dexcom-ble-protocol-deep-dive.md` - Protocol reverse engineering
- `glossary.md` - Terminology dictionary

**Creation trigger**: 
- Analyzing source code reveals complex behavior needing documentation
- Multiple projects implement similar concepts differently
- Protocol or algorithm requires detailed explanation

**Quality criteria**:
- Includes code references with file paths and line numbers
- Shows actual implementation, not idealized version
- Documents gaps, quirks, and edge cases
- Cross-references related systems

---

### 30-design - Integration & Architecture
**What belongs here**: How-to guides for integrating with systems, architectural patterns, implementation strategies

**Purpose**: Bridge from understanding (domain) to action (implementation)

**Examples**:
- `nightscout-integration-guide.md` - Practical guide for integrating with Nightscout

**Creation trigger**:
- Common integration patterns emerge from research
- Clear architectural approach consolidates from analysis
- Implementation guide would prevent repeated mistakes

**Quality criteria**:
- Actionable guidance, not just description
- Based on domain research, not speculation
- Includes code examples or pseudocode
- References domain docs for background

---

### 60-research - Exploration & Proposals
**What belongs here**: Proposals for improvements, comparative analysis, impact assessments, external system inventories, experimental fixtures

**Purpose**: Working space for ideas that may become domain knowledge, design guidance, or decisions

**Subdirectories**:
- `external-inventories/` - Documentation audits of external projects
- `fixtures/` - Test data and examples for validation

**Examples**:
- `controller-registration-protocol-proposal.md` - New protocol proposal
- `profile-model-evolution-proposal.md` - Data model enhancement
- `stakeholder-priority-analysis.md` - Research on user needs
- `external-inventories/loop-docs.md` - Inventory of Loop documentation

**Creation trigger**:
- Gaps identified during domain analysis
- New requirements emerge from stakeholders
- Comparative analysis across projects reveals opportunities
- Inventorying external project documentation

**Quality criteria**:
- Clearly labeled as proposal/research (not accepted fact)
- References domain analysis supporting the proposal
- Includes alternatives considered
- May graduate to domain (if analyzing existing) or design (if accepted)

---

### 90-decisions - Architecture Decision Records
**What belongs here**: Formal decisions about approaches, standards, and conventions

**Purpose**: Record why choices were made for future reference

**Format**: Use ADR template (`_template.md`)

**Examples**:
- `adr-001-override-supersession.md` - How to handle override lifecycle
- `adr-002-sync-identity-strategy.md` - Standardizing sync IDs
- `adr-003-no-custom-credentials.md` - Authentication approach

**Creation trigger**:
- Significant technical decision with multiple valid approaches
- Need to prevent revisiting the same debate
- Decision impacts multiple projects or teams

**Quality criteria**:
- Follows ADR template format
- Includes context, decision, consequences
- Lists alternatives considered with rationale for rejection
- References supporting domain/research docs

---

## Workflow: From Source Code to Decisions

### 1. Source Code Analysis
**Action**: Explore external repositories in `externals/`

**Output**: Code references, behavior observations, gaps identified

**Document in**: `mapping/` (per-project specifics) or `10-domain/` (cross-cutting concepts)

### 2. Research & Synthesis
**Action**: Compare implementations, identify patterns, propose improvements

**Output**: Proposals, comparative analysis, impact assessments

**Document in**: `60-research/`

### 3. Knowledge Consolidation
**Action**: Distill research into stable domain knowledge

**Output**: Deep-dives, protocol specs, glossary entries

**Document in**: `10-domain/` (update or create)

### 4. Design Guidance
**Action**: Create actionable implementation guides

**Output**: Integration guides, architectural patterns

**Document in**: `30-design/`

### 5. Decision Making
**Action**: Formalize approach to controversial or high-impact choices

**Output**: Architecture Decision Records

**Document in**: `90-decisions/`

---

## Document Lifecycle

### Research → Domain
When a proposal in `60-research/` is validated through implementation or broad consensus, extract the factual analysis into `10-domain/`.

**Example**: A proposal about profile models reveals how they actually work → extract the "how it works" section into a domain deep-dive.

### Domain → Design
When domain analysis reveals clear patterns worth codifying into implementation guidance.

**Example**: Understanding how multiple systems handle authentication → create integration guide with best practices.

### Research → Decision
When a proposal requires formal decision with multiple stakeholders.

**Example**: Debate on sync identity strategy → write ADR documenting the chosen approach.

---

## Numbering System

Directories use decimal numbering (00, 10, 30, 60, 90) to allow insertion of new categories without renaming.

**Available numbers for future use**: 20, 40, 50, 70, 80

**Possible future categories**:
- **20-requirements** - Formal requirements from stakeholders
- **40-implementation** - Reference implementations or code snippets
- **50-testing** - Test strategies, validation approaches
- **70-operations** - Deployment, monitoring, maintenance guides
- **80-deprecated** - Superseded documents kept for historical reference

---

## Special Files

### Root-Level Documents
Documents at `docs/` root should be cross-cutting guides that don't fit category boundaries:

- `TOOLING-GUIDE.md` - How to use workspace tooling
- `DIGITAL-RIGHTS.md` - Legal/ethical considerations
- `state-of-diabetes-2026.md` - Ecosystem landscape analysis

### _includes/
Reusable snippets or fragments included in multiple documents.

---

## Quality System Elements

This documentation structure supports a quality management system by organizing:

1. **Requirements** → Research proposals, stakeholder analysis (60-research)
2. **Specifications** → Domain deep-dives, protocol specs (10-domain)
3. **Design** → Integration guides, architecture (30-design)
4. **Verification** → Mapped to conformance scenarios (in `conformance/`)
5. **Traceability** → Cross-references between levels, gaps tracking (in `traceability/`)
6. **Configuration Management** → ADRs document approved baselines (90-decisions)

---

## Decision Guide: Where Does My Document Go?

**Ask these questions:**

1. **Is it about what exists?** → `10-domain/`
2. **Is it a proposal or exploration?** → `60-research/`
3. **Is it actionable implementation guidance?** → `30-design/`
4. **Is it a formal decision?** → `90-decisions/` (use ADR format)
5. **Is it mission/vision?** → `00-overview/`
6. **Is it cross-cutting tooling/process?** → `docs/` (root level)

**Examples:**

| Document Content | Destination | Rationale |
|-----------------|-------------|-----------|
| How Loop calculates insulin on board | `10-domain/insulin-curves-deep-dive.md` | Analyzing existing implementation |
| Proposal for standardized IOB API | `60-research/iob-standardization-proposal.md` | Proposing future state |
| Guide to integrate with Nightscout API | `30-design/nightscout-integration-guide.md` | Actionable how-to |
| Decision on which auth model to use | `90-decisions/adr-004-auth-model.md` | Formal decision |
| Analysis of Trio vs Loop differences | `10-domain/algorithm-comparison-deep-dive.md` | Understanding existing systems |
| MongoDB upgrade impact analysis | `60-research/mongodb-modernization-impact-assessment.md` | Exploring change implications |
| MongoDB update readiness for team | `60-research/mongodb-update-readiness-report.md` | Team-facing status and recommendations |

---

## Tips for Effective Documentation

### Code References
Always include traceable references to source:
```markdown
**Source**: `loop:LoopKit/LoopKit/InsulinMath.swift#L45-L67`
```

### Gap Identification
When analysis reveals alignment issues, document in `traceability/gaps.md` and cross-reference:
```markdown
**Gap**: See [GAP-003: No unified sync identity](../traceability/gaps.md#gap-003)
```

### Versioning
Use revision history tables for significant updates:
```markdown
| Date | Author | Changes |
|------|--------|---------|
| 2026-01-18 | Agent | Initial analysis from Loop source |
```

### Cross-Linking
Build a web of knowledge with references:
```markdown
See also: [Treatments Deep Dive](treatments-deep-dive.md), [ADR-001](../90-decisions/adr-001-override-supersession.md)
```

---

## Maintenance

### Periodic Reviews
- **Quarterly**: Review research docs for graduation to domain or design
- **After major decisions**: Update related domain/design docs to reflect ADR
- **When gaps close**: Update domain docs and archive research proposals

### Deprecation
Don't delete outdated docs immediately:
1. Mark with deprecation notice at top
2. Reference superseding document
3. Move to `80-deprecated/` if that category is created
4. Delete only if no historical value

---

## Contributing

When adding documentation:
1. Check if existing doc can be updated vs creating new
2. Use this README to determine correct location
3. Follow quality criteria for that category
4. Add cross-references to related docs
5. Include code references where applicable
