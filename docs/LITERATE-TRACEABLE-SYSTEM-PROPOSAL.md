# Proposal: Literate Programming & Traceable System for Nightscout Ecosystem

## Executive Summary

This proposal outlines a system that combines:
1. **Enhanced tooling** for the Nightscout alignment workspace
2. **GitHub Copilot CLI integration** via skills, instructions, and agent automation
3. **Literate programming patterns** where documentation generates/validates code
4. **Full traceability** from requirements → specs → tests → implementations

The result: A self-documenting, AI-augmented development environment where human experts guide high-level decisions while AI agents handle repetitive analysis, cross-referencing, and verification.

---

## Part 1: Current State Analysis

### Existing Tooling Strengths

The workspace already has solid foundations:

| Tool | Purpose | Output |
|------|---------|--------|
| `query_workspace.py` | Search REQ/GAP/docs | JSON/interactive |
| `gen_traceability.py` | Link requirements→tests→docs | JSON/markdown |
| `run_workflow.py` | Orchestrate validation pipelines | JSON reports |
| `verify_*.py` suite | Static analysis (refs, coverage, terminology) | Reports |
| `gen_coverage.py` | Scenario coverage matrix | JSON/markdown |

### Current Gaps

1. **No AI Integration Points** - Tools output JSON but no structured interface for AI agents
2. **No Literate Programming** - Documentation doesn't generate/validate code
3. **Manual Cross-Project Analysis** - 16 external repos require manual review
4. **No Provenance Tracking** - Findings aren't traced to source analysis sessions
5. **Batch Processing Missing** - Multi-component audits require manual orchestration

---

## Part 2: Proposed Tooling Improvements

### 2.1 Agent-Friendly Query Interface

**New: `tools/agent_query.py`**

```python
#!/usr/bin/env python3
"""
Agent Query Interface - Structured queries for AI agents.

Provides machine-readable responses optimized for LLM consumption:
- Compact context with relevant metadata
- Explicit action suggestions
- Traceability links

Usage:
    # What requirements lack test coverage?
    python tools/agent_query.py untested-requirements --json
    
    # What gaps affect a specific project?
    python tools/agent_query.py gaps-for-project --project aaps --json
    
    # Generate analysis prompt for a component
    python tools/agent_query.py audit-prompt --component dexcom-g7 --facets all
"""

FACETS = {
    "terminology": "mapping/cross-project/terminology-matrix.md",
    "gaps": "traceability/gaps.md",
    "requirements": "traceability/requirements.md",
    "progress": "progress.md",
    "deep-dive": "docs/10-domain/{component}-deep-dive.md"
}

def generate_audit_prompt(component: str, facets: list) -> dict:
    """Generate structured prompt for agent to audit a component."""
    return {
        "task": f"Audit {component} across specified facets",
        "component": component,
        "facets": facets,
        "context_files": [FACETS[f].format(component=component) for f in facets],
        "output_requirements": {
            "terminology_updates": "List any terms to add/modify in terminology-matrix.md",
            "gap_ids": "New GAP-XXX-NNN identifiers for any gaps found",
            "requirement_ids": "New REQ-NNN identifiers for any requirements extracted",
            "progress_entry": "Structured progress.md entry with findings summary"
        },
        "validation_command": "make verify"
    }
```

### 2.2 Literate Programming Engine

**New: `tools/literate.py`**

Extracts executable code/assertions from markdown documentation:

```python
#!/usr/bin/env python3
"""
Literate Programming Engine - Extract and validate code from documentation.

Markdown documents can contain executable assertions:

    ```yaml {#assert:REQ-001}
    - input: { sgv: 100, direction: "Flat" }
    - expect: { valid: true, trend: "steady" }
    ```

    ```python {#extract:glucose_parser.py:lines=10-20}
    # This code block should match the source file
    ```

Commands:
    # Extract all assertions from docs
    python tools/literate.py extract --format yaml
    
    # Validate documentation matches code
    python tools/literate.py validate
    
    # Generate test fixtures from doc examples
    python tools/literate.py gen-fixtures --output conformance/fixtures/
"""

import re
from pathlib import Path

CODE_BLOCK_PATTERN = re.compile(
    r'```(\w+)\s*\{([^}]+)\}\n(.*?)```',
    re.DOTALL
)

def extract_assertions(doc_path: Path) -> list:
    """Extract test assertions from markdown code blocks."""
    content = doc_path.read_text()
    assertions = []
    
    for match in CODE_BLOCK_PATTERN.finditer(content):
        lang, attrs, code = match.groups()
        
        # Parse attributes like #assert:REQ-001
        attr_dict = parse_attributes(attrs)
        
        if 'assert' in attr_dict:
            assertions.append({
                "source": str(doc_path),
                "line": content[:match.start()].count('\n') + 1,
                "language": lang,
                "requirement": attr_dict['assert'],
                "code": code.strip()
            })
    
    return assertions

def validate_code_references(doc_path: Path) -> list:
    """Validate that code blocks marked with #extract match source files."""
    errors = []
    content = doc_path.read_text()
    
    for match in CODE_BLOCK_PATTERN.finditer(content):
        lang, attrs, doc_code = match.groups()
        attr_dict = parse_attributes(attrs)
        
        if 'extract' in attr_dict:
            source_ref = attr_dict['extract']
            # Parse: filename.py:lines=10-20
            source_file, line_spec = parse_source_ref(source_ref)
            
            actual_code = read_source_lines(source_file, line_spec)
            
            if normalize(doc_code) != normalize(actual_code):
                errors.append({
                    "doc": str(doc_path),
                    "source": source_file,
                    "error": "Documentation code block doesn't match source"
                })
    
    return errors
```

### 2.3 Multi-Faceted Analysis Orchestrator

**New: `tools/faceted_analysis.py`**

Automates the 5-facet analysis pattern observed in progress.md:

```python
#!/usr/bin/env python3
"""
Faceted Analysis Orchestrator - Coordinate multi-facet component analysis.

When analyzing a component (e.g., dexcom-g7), updates must propagate to:
1. terminology-matrix.md - Cross-project terminology
2. gaps.md - GAP-XXX-NNN entries
3. requirements.md - REQ-NNN entries
4. docs/10-domain/{component}-deep-dive.md - Technical deep dive
5. progress.md - Completion tracking

Usage:
    # Initialize analysis for a component
    python tools/faceted_analysis.py init dexcom-g7
    
    # Check analysis completeness
    python tools/faceted_analysis.py status dexcom-g7
    
    # Generate analysis report
    python tools/faceted_analysis.py report dexcom-g7 --json
    
    # Validate all facets updated consistently
    python tools/faceted_analysis.py validate dexcom-g7
"""

FACETS = [
    {
        "id": "terminology",
        "file": "mapping/cross-project/terminology-matrix.md",
        "marker_pattern": r"## .*{component}",
        "required_sections": ["Data Concepts", "Events"]
    },
    {
        "id": "gaps",
        "file": "traceability/gaps.md",
        "marker_pattern": r"GAP-{COMPONENT}-\d{{3}}",
        "required_sections": []
    },
    {
        "id": "requirements",
        "file": "traceability/requirements.md",
        "marker_pattern": r"REQ-\d{{3}}.*{component}",
        "required_sections": []
    },
    {
        "id": "deep-dive",
        "file": "docs/10-domain/{component}-deep-dive.md",
        "marker_pattern": None,  # File existence check
        "required_sections": ["Overview", "Data Model", "Gaps Identified"]
    },
    {
        "id": "progress",
        "file": "progress.md",
        "marker_pattern": r"### .*{Component}.*\(\d{{4}}-\d{{2}}-\d{{2}}\)",
        "required_sections": ["Deliverable", "Key Findings", "Gaps Identified"]
    }
]

def check_facet_completeness(component: str) -> dict:
    """Check if all facets have been updated for a component."""
    results = {}
    
    for facet in FACETS:
        file_path = Path(facet["file"].format(component=component))
        
        if not file_path.exists():
            results[facet["id"]] = {"status": "missing", "file": str(file_path)}
            continue
        
        content = file_path.read_text()
        
        if facet["marker_pattern"]:
            pattern = facet["marker_pattern"].format(
                component=component,
                Component=component.title(),
                COMPONENT=component.upper().replace("-", "_")
            )
            if re.search(pattern, content):
                results[facet["id"]] = {"status": "complete"}
            else:
                results[facet["id"]] = {"status": "incomplete", "missing": "marker"}
        else:
            results[facet["id"]] = {"status": "complete"}
    
    return results
```

### 2.4 External Repository Analysis Bridge

**New: `tools/external_analysis.py`**

Bridges the gap between externals/ and documentation:

```python
#!/usr/bin/env python3
"""
External Repository Analysis Bridge - Query across 16 external repos.

Provides structured queries for AI agents to explore external codebases:

Usage:
    # Find all files matching a pattern across external repos
    python tools/external_analysis.py find "*.swift" --contains "G7"
    
    # Extract function signatures for a concept
    python tools/external_analysis.py signatures "jpake" --json
    
    # Generate context bundle for AI analysis
    python tools/external_analysis.py context-bundle dexcom-g7 --max-tokens 50000
    
    # Compare implementations across projects
    python tools/external_analysis.py compare "CGMManager" --projects loop,trio,aaps
"""

from pathlib import Path
import json

EXTERNALS_DIR = Path(__file__).parent.parent / "externals"

def generate_context_bundle(topic: str, max_tokens: int = 50000) -> dict:
    """Generate a context bundle for AI analysis of a topic."""
    
    # Topic patterns (could be extended to config file)
    TOPIC_PATTERNS = {
        "dexcom-g7": {
            "file_patterns": ["**/G7*.swift", "**/g7*.kt", "**/G7*.java", "**/DexcomG7*.swift"],
            "search_terms": ["G7", "jpake", "libkeks"],
            "priority_repos": ["DiaBLE", "xDrip", "xdripswift", "LoopWorkspace"]
        },
        "nightscout-sync": {
            "file_patterns": ["**/Nightscout*.swift", "**/nightscout*.kt", "**/NS*.swift"],
            "search_terms": ["NightscoutAPI", "uploadToNS", "NSClient"],
            "priority_repos": ["cgm-remote-monitor", "AndroidAPS", "Trio", "LoopWorkspace"]
        }
    }
    
    config = TOPIC_PATTERNS.get(topic, {})
    bundle = {
        "topic": topic,
        "files": [],
        "search_results": [],
        "estimated_tokens": 0
    }
    
    # Gather relevant files
    for repo_dir in EXTERNALS_DIR.iterdir():
        if not repo_dir.is_dir() or repo_dir.name.startswith('.'):
            continue
        
        for pattern in config.get("file_patterns", []):
            for file_path in repo_dir.rglob(pattern):
                if bundle["estimated_tokens"] < max_tokens:
                    content = file_path.read_text(errors="ignore")
                    tokens = len(content) // 4  # Rough estimate
                    
                    bundle["files"].append({
                        "repo": repo_dir.name,
                        "path": str(file_path.relative_to(EXTERNALS_DIR)),
                        "tokens": tokens,
                        "content": content[:10000]  # Truncate large files
                    })
                    bundle["estimated_tokens"] += min(tokens, 2500)
    
    return bundle
```

---

## Part 3: GitHub Copilot Integration

### 3.1 Nightscout CGM Skill

**Location: `~/.copilot/skills/nightscout-cgm/`**

**`SKILL.md`:**

```markdown
# Nightscout CGM Ecosystem Skill

## Description
Expert knowledge of the Nightscout CGM ecosystem, including diabetes terminology, 
AID systems (Loop, AAPS, Trio, oref0), CGM protocols, and data interoperability.

## Capabilities

### Domain Knowledge
- **CGM Protocols**: Dexcom G6/G7, Libre 2/3, xDrip+ BLE communication
- **AID Systems**: Loop, AAPS (oref0/oref1), Trio closed-loop algorithms
- **Nightscout API**: entries, treatments, devicestatus, profile collections
- **Terminology**: BG, SGV, IOB, COB, CR, ISF, DIA, basal, bolus, SMB

### Analysis Patterns
When asked to analyze CGM/diabetes data or code:

1. **Identify the source system** (Loop, AAPS, Trio, xDrip+, Nightscout)
2. **Map terminology** using the Cross-Project Terminology Matrix
3. **Check for known gaps** in traceability/gaps.md
4. **Reference requirements** in traceability/requirements.md
5. **Validate against OpenAPI specs** in specs/openapi/

### Multi-Faceted Analysis
For component audits, update all 5 facets:
1. `mapping/cross-project/terminology-matrix.md`
2. `traceability/gaps.md` (GAP-XXX-NNN format)
3. `traceability/requirements.md` (REQ-NNN format)
4. `docs/10-domain/{component}-deep-dive.md`
5. `progress.md`

## Tools Available
```bash
# Query workspace documentation
python tools/query_workspace.py --search "<term>" --json

# Generate traceability matrix
python tools/gen_traceability.py --json

# Run validation workflow
python tools/run_workflow.py --workflow quick --json

# Check faceted analysis status
python tools/faceted_analysis.py status <component>
```

## Output Conventions

### Gap IDs
Format: `GAP-<CATEGORY>-<NNN>`
Categories: G7, CGM, SYNC, TREAT, DS, ALG, ENTRY, PROF

### Requirement IDs
Format: `REQ-<NNN>`
Number ranges:
- 001-009: Override
- 010-019: Timestamp
- 020-029: Sync
- 050-059: CGM Data Source

### References
Use backtick code refs: `externals/xDrip/app/src/.../File.java:123`
```

### 3.2 Repository Instructions

**Location: `.github/copilot-instructions.md`**

```markdown
# Nightscout Ecosystem Alignment Workspace

## Repository Structure

This workspace coordinates analysis across 16 external CGM/AID repositories:

```
externals/           # Git-ignored external repos (run `make bootstrap`)
mapping/             # Per-project and cross-project field mappings
specs/               # OpenAPI and JSON Schema specifications
conformance/         # Test scenarios and assertions
traceability/        # Requirements, gaps, coverage matrices
docs/                # Research and deep-dive documentation
tools/               # Python automation scripts
```

## Working with External Repos

- External repos are in `externals/` (git-ignored, reproducible via `workspace.lock.json`)
- **Never commit to main/master** in external repos
- Use `make bootstrap` to clone/update all repos
- Use `make freeze` to pin current commits

## Multi-Faceted Analysis Pattern

When analyzing a component, **always update all 5 facets**:

1. **Terminology** - `mapping/cross-project/terminology-matrix.md`
2. **Gaps** - `traceability/gaps.md` with GAP-XXX-NNN IDs
3. **Requirements** - `traceability/requirements.md` with REQ-NNN IDs  
4. **Deep Dive** - `docs/10-domain/{component}-deep-dive.md`
5. **Progress** - `progress.md` with dated entry

## Validation Commands

```bash
make verify           # Run all static verification
make traceability     # Generate traceability matrix
make workflow TYPE=quick  # Fast validation
make workflow TYPE=full   # Complete pipeline
```

## ID Conventions

### Gap IDs: `GAP-<CATEGORY>-<NNN>`
- G7: Dexcom G7 protocol
- CGM: CGM data source
- SYNC: Synchronization
- TREAT: Treatments
- DS: DeviceStatus
- ALG: Algorithm
- ENTRY: Entries
- PROF: Profile

### Requirement IDs: `REQ-<NNN>`
Check `traceability/requirements.md` for next available number in category.

## Code References

Use explicit file:line references:
```
`externals/xDrip/app/src/main/java/com/eveningoutpost/dexdrip/models/BgReading.java:45`
```
```

### 3.3 Component-Specific Instructions

**Location: `.github/instructions/analysis-patterns.instructions.md`**

```markdown
# Analysis Patterns for Nightscout Ecosystem

## CGM Protocol Analysis

When analyzing a CGM protocol (Dexcom G6/G7, Libre, etc.):

### Step 1: Identify Source Files
```bash
python tools/external_analysis.py find "*.swift" --contains "G7"
python tools/external_analysis.py find "*.java" --contains "G7"
```

### Step 2: Generate Context Bundle
```bash
python tools/external_analysis.py context-bundle dexcom-g7 --max-tokens 50000
```

### Step 3: Check Existing Analysis
```bash
python tools/faceted_analysis.py status dexcom-g7
python tools/query_workspace.py --search "G7" --json
```

### Step 4: Update All Facets
1. Add new terminology to `mapping/cross-project/terminology-matrix.md`
2. Add gaps as `GAP-G7-NNN` in `traceability/gaps.md`
3. Add requirements as `REQ-NNN` in `traceability/requirements.md`
4. Create/update `docs/10-domain/g7-*-deep-dive.md`
5. Add progress entry to `progress.md`

### Step 5: Validate
```bash
make verify
python tools/faceted_analysis.py validate dexcom-g7
```

## Nightscout API Analysis

When analyzing Nightscout API collections (entries, treatments, devicestatus):

### Required Context Files
- `specs/openapi/aid-entries-2025.yaml`
- `specs/openapi/aid-treatments-2025.yaml`
- `specs/openapi/aid-devicestatus-2025.yaml`
- `mapping/nightscout/README.md`

### Cross-Reference Checklist
- [ ] Field names match terminology matrix
- [ ] eventTypes documented in treatments spec
- [ ] Controller support matrix updated
- [ ] x-aid-* annotations present in OpenAPI
```

---

## Part 4: Literate Programming Workflows

### 4.1 Documentation-Driven Testing

Documentation becomes the source of truth for test assertions:

**Example in `docs/10-domain/entries-deep-dive.md`:**

````markdown
## SGV Field Validation

A valid SGV entry must satisfy:

```yaml {#assert:REQ-010}
# Valid SGV with UTC timestamp
input:
  sgv: 120
  dateString: "2026-01-20T12:00:00.000Z"
  direction: "Flat"
expect:
  valid: true
  normalized_direction: "steady"
```

```yaml {#assert:REQ-010}
# Invalid: non-UTC timestamp
input:
  sgv: 120
  dateString: "2026-01-20T12:00:00-05:00"
expect:
  valid: false
  error: "timestamp must be UTC"
```
````

**Extraction to conformance tests:**

```bash
# Extract assertions from documentation
python tools/literate.py extract --format yaml > conformance/fixtures/doc-generated.yaml

# Validate extracted assertions
python tools/run_conformance.py --fixtures conformance/fixtures/doc-generated.yaml
```

### 4.2 Code-Documentation Synchronization

Ensure code examples in docs match actual source:

**Example in `docs/10-domain/g7-jpake-implementation-guide.md`:**

````markdown
## J-PAKE Calculation Core

The core calculation from xDrip's libkeks:

```java {#extract:externals/xDrip/libkeks/src/main/java/jamorham/keks/Calc.java:lines=45-60}
public static byte[] calculateZKP(BigInteger x, ECPoint G, ECPoint X, 
                                   String participantId) {
    // Zero-knowledge proof calculation
    BigInteger v = randomScalar();
    ECPoint V = G.multiply(v);
    BigInteger h = hash(G, V, X, participantId);
    BigInteger r = v.subtract(x.multiply(h)).mod(n);
    return encode(V, r);
}
```
````

**Validation:**

```bash
# Check documentation matches source
python tools/literate.py validate

# Output:
# docs/10-domain/g7-jpake-implementation-guide.md: OK
# docs/10-domain/treatments-deep-dive.md: MISMATCH at line 234
#   Expected: public void processEntry(...)
#   Actual:   public Entry processEntry(...)
```

### 4.3 Progress Tracking Integration

Automatically update progress.md when analysis completes:

```bash
# After completing analysis
python tools/faceted_analysis.py complete dexcom-g7 \
  --key-findings "J-PAKE uses secp256r1, 5-phase auth sequence documented" \
  --gaps-identified "GAP-G7-001,GAP-G7-002,GAP-G7-003" \
  --source-files "DiaBLE/DexcomG7.swift,xDrip/libkeks/Calc.java"

# Generates progress.md entry:
# ### Dexcom G7 Protocol Analysis (2026-01-20)
# 
# | Deliverable | Location | Key Insights |
# |-------------|----------|--------------|
# | G7 Analysis | docs/10-domain/g7-*-deep-dive.md | J-PAKE uses secp256r1... |
# 
# **Gaps Identified**: GAP-G7-001, GAP-G7-002, GAP-G7-003
```

---

## Part 5: Batch Processing (Current Workarounds)

Until `copilot agent batch` becomes available, use these patterns:

### 5.1 Sequential Component Audit

**`scripts/audit-components.sh`:**

```bash
#!/bin/bash
# Audit multiple components sequentially

COMPONENTS=(
    "dexcom-g7"
    "libre-2"
    "xdrip-plus"
    "oref0-algorithm"
    "loop-algorithm"
    "nightscout-sync"
)

OUTPUT_DIR="audit-results-$(date +%Y%m%d)"
mkdir -p "$OUTPUT_DIR"

for component in "${COMPONENTS[@]}"; do
    echo "=== Auditing $component ==="
    
    # Check current status
    python tools/faceted_analysis.py status "$component" > "$OUTPUT_DIR/$component-status.json"
    
    # Generate context bundle for AI
    python tools/external_analysis.py context-bundle "$component" \
        --max-tokens 50000 > "$OUTPUT_DIR/$component-context.json"
    
    # Run Copilot analysis (when available)
    # copilot --prompt "Analyze $component using nightscout-cgm skill. 
    #   Update all 5 facets. Output findings in JSON." \
    #   --allow-all --silent --share "$OUTPUT_DIR/$component-findings.md"
    
    echo "Completed $component"
done

# Aggregate results
echo "=== Aggregating Results ==="
python tools/faceted_analysis.py report --all --json > "$OUTPUT_DIR/aggregate-report.json"
```

### 5.2 Makefile Integration

Add to `Makefile`:

```makefile
# AI-assisted analysis targets

.PHONY: copilot-audit copilot-batch copilot-validate

# Single component audit
copilot-audit:
	@echo "Auditing $(COMPONENT)..."
	@python tools/faceted_analysis.py status $(COMPONENT)
	@python tools/external_analysis.py context-bundle $(COMPONENT) --max-tokens 50000

# Batch audit all components
copilot-batch:
	@echo "Running batch audit..."
	@./scripts/audit-components.sh

# Validate AI-generated content
copilot-validate:
	@echo "Validating AI outputs..."
	@python tools/literate.py validate
	@make verify
	@python tools/faceted_analysis.py validate --all
```

---

## Part 6: Future Integration (copilot agent)

When the proposed `copilot agent` commands become available:

### 6.1 Workflow Files

**`workflows/audit-cgm-component.copilot`:**

```dockerfile
# CGM Component Audit Workflow
MODEL claude-sonnet-4.5
MODE full
MAX-CYCLES 2
MAX-CONTEXT-TOKENS 150000
COMPACT-EVERY 50000

# Load skill for domain knowledge
SKILL nightscout-cgm

# Facet 1: Terminology
@mapping/cross-project/terminology-matrix.md
PROMPT Analyze {{COMPONENT}} protocol and update terminology matrix with any new terms found.

# Facet 2: Gap identification
@traceability/gaps.md
PROMPT Identify implementation gaps for {{COMPONENT}} using GAP-{{CATEGORY}}-NNN format.

# Facet 3: Requirements extraction
@traceability/requirements.md
PROMPT Extract formal requirements for {{COMPONENT}} using REQ-NNN format.

# Facet 4: Deep dive documentation
RUN python tools/external_analysis.py context-bundle {{COMPONENT}} --max-tokens 30000
PROMPT Create comprehensive deep-dive documentation at docs/10-domain/{{COMPONENT}}-deep-dive.md

# Facet 5: Progress tracking
@progress.md
PROMPT Add dated progress entry for {{COMPONENT}} analysis completion.

# Validation
RUN make verify
PROMPT Review validation results and fix any issues.

CHECKPOINT "{{COMPONENT}}-analysis-complete"
```

### 6.2 Batch Orchestration

```bash
# When copilot agent batch is available:
copilot agent batch \
  --parallel 4 \
  --format jsonl \
  workflows/audit-*.copilot \
  --output audit-results.jsonl

# Aggregate findings
copilot agent apply "Summarize all audit findings" \
  --mode read-only \
  --input audit-results.jsonl \
  --output AUDIT-SUMMARY.md
```

---

## Part 7: Implementation Roadmap

### Phase 1: Enhanced Tooling (Week 1-2)

- [ ] Create `tools/agent_query.py` - Structured queries for AI agents
- [ ] Create `tools/literate.py` - Extract assertions from markdown
- [ ] Create `tools/faceted_analysis.py` - Multi-facet orchestration
- [ ] Create `tools/external_analysis.py` - Cross-repo query bridge
- [ ] Update Makefile with new targets

### Phase 2: Copilot Integration (Week 2-3)

- [ ] Create Nightscout CGM skill at `~/.copilot/skills/nightscout-cgm/`
- [ ] Create `.github/copilot-instructions.md`
- [ ] Create `.github/instructions/analysis-patterns.instructions.md`
- [ ] Test skill with interactive Copilot CLI

### Phase 3: Batch Automation (Week 3-4)

- [ ] Create `scripts/audit-components.sh`
- [ ] Create component workflow templates
- [ ] Test sequential batch processing
- [ ] Document patterns for team use

### Phase 4: Literate Programming (Week 4-5)

- [ ] Add `{#assert:REQ-NNN}` annotations to existing docs
- [ ] Add `{#extract:file:lines}` annotations for code examples
- [ ] Create validation pipeline for doc-code sync
- [ ] Integrate with CI/CD

### Phase 5: Full Integration (Ongoing)

- [ ] Monitor `copilot agent` feature availability
- [ ] Migrate shell scripts to `.copilot` workflow files
- [ ] Implement parallel batch processing
- [ ] Continuous improvement based on usage

---

## Appendix A: Tool Command Reference

| Command | Purpose |
|---------|---------|
| `make copilot-audit COMPONENT=x` | Audit single component |
| `make copilot-batch` | Batch audit all components |
| `make copilot-validate` | Validate AI-generated content |
| `python tools/agent_query.py untested-requirements` | Find untested requirements |
| `python tools/faceted_analysis.py status x` | Check facet completeness |
| `python tools/literate.py validate` | Validate doc-code sync |
| `python tools/external_analysis.py context-bundle x` | Generate context for AI |

## Appendix B: ID Reference

### Gap Categories
| Prefix | Domain |
|--------|--------|
| GAP-G7-NNN | Dexcom G7 |
| GAP-CGM-NNN | CGM Data Source |
| GAP-SYNC-NNN | Synchronization |
| GAP-TREAT-NNN | Treatments |
| GAP-DS-NNN | DeviceStatus |
| GAP-ALG-NNN | Algorithm |
| GAP-ENTRY-NNN | Entries |
| GAP-PROF-NNN | Profile |

### Requirement Ranges
| Range | Domain |
|-------|--------|
| REQ-001-009 | Override |
| REQ-010-019 | Timestamp |
| REQ-020-029 | Sync Identity |
| REQ-030-039 | Data Validation |
| REQ-050-059 | CGM Data Source |
| REQ-060-069 | Algorithm |

---

**Document Version**: 1.0  
**Date**: 2026-01-20  
**Status**: Proposal
