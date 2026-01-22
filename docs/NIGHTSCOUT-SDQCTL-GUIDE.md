# sdqctl Workflow Guide for Nightscout Ecosystem

**Date:** 2026-01-22  
**For:** rag-nightscout-ecosystem-alignment team  
**sdqctl Version:** 0.1.1+

---

## Overview

This guide maps sdqctl capabilities to the Nightscout ecosystem's **5-facet documentation methodology**:

1. **Terminology** → `mapping/cross-project/terminology-matrix.md`
2. **Gaps** → `traceability/gaps.md`
3. **Requirements** → `traceability/requirements.md`
4. **Deep Dives** → `docs/10-domain/{component}-deep-dive.md`
5. **Progress** → `progress.md`

sdqctl orchestrates AI-assisted workflows that systematically update these facets.

---

## Quick Start

```bash
# Activate sdqctl
source ./activate-sdqctl.sh

# Validate all workflows (lenient mode for aspirational patterns)
sdqctl validate workflows/*.conv --allow-missing

# Run a single discovery workflow
sdqctl run workflows/discovery/component-discovery.conv

# Multi-cycle analysis with fresh context each cycle
sdqctl cycle workflows/iterate/facet-refresh.conv -n 5 --session-mode fresh

# Batch verification workflows
sdqctl flow workflows/verify-*.conv --parallel 3
```

---

## Session Modes for Different Use Cases

| Mode | Description | Best For |
|------|-------------|----------|
| `fresh` | New context each cycle, sees file changes | Autonomous editing, discovery |
| `accumulate` | Context grows, compact at limit | Iterative refinement, research |
| `compact` | Summarize after each cycle | Long workflows, token economy |

### When to Use Each Mode

**Fresh Mode** - Use for exploratory sessions where the AI edits files:
```bash
sdqctl cycle workflows/discovery/component-discovery.conv \
  -n 3 --session-mode fresh
```
Each cycle sees the file changes from the previous cycle.

**Accumulate Mode** - Use for research that builds on previous findings:
```bash
sdqctl cycle workflows/design/deep-dive-template.conv \
  -n 5 --session-mode accumulate
```
Context grows, allowing the AI to reference earlier discoveries.

**Compact Mode** - Use for long-running verification across many files:
```bash
sdqctl cycle workflows/iterate/verification-loop.conv \
  -n 10 --session-mode compact
```
Summarizes between cycles to prevent context overflow.

---

## Validation Modes

Your workspace has aspirational file patterns (files that should exist but don't yet). Use these strategies:

### Option 1: CLI Flag (No File Changes)
```bash
sdqctl run workflow.conv --allow-missing
sdqctl validate workflows/*.conv --allow-missing
```

### Option 2: File-Level Setting (Recommended)
Add at the top of your `.conv` file:
```dockerfile
VALIDATION-MODE lenient
```

### Option 3: Mark Specific Patterns as Optional
```dockerfile
CONTEXT @traceability/requirements.md           # Required
CONTEXT @traceability/gaps.md                   # Required
CONTEXT-OPTIONAL @conformance/scenarios/**/*.yaml  # Aspirational
CONTEXT-OPTIONAL @mapping/xdrip/README.md         # May not exist
```

### Option 4: Exclude Patterns Entirely
```dockerfile
CONTEXT-EXCLUDE conformance/**/*.yaml
```

---

## Integrating Python Tools

Use the `RUN` directive to execute your Python verification tools:

```dockerfile
# Run verification tool, output goes to AI context
RUN-OUTPUT always
RUN python tools/verify_refs.py --json

# Prompt analyzes the output
PROMPT Analyze the verification results above.
  List all broken references and suggest fixes.
```

### Error Handling
```dockerfile
RUN-ON-ERROR continue    # Don't stop on tool failure
RUN-OUTPUT on-error      # Only include output if tool fails
RUN python tools/verify_coverage.py --json
```

### Timeout and Output Limits
```dockerfile
RUN-TIMEOUT 2m           # Allow 2 minutes
RUN-OUTPUT-LIMIT 50K     # Max 50K chars in context
RUN python tools/gen_inventory.py --json
```

---

## Template Variables for Iteration

Available in PROMPT, PROLOGUE, EPILOGUE, OUTPUT-FILE:

| Variable | Description | Example |
|----------|-------------|---------|
| `{{DATE}}` | ISO date | 2026-01-22 |
| `{{DATETIME}}` | ISO datetime | 2026-01-22T23:30:00 |
| `{{CYCLE_NUMBER}}` | Current cycle | 2 |
| `{{CYCLE_TOTAL}}` | Total cycles | 5 |
| `{{COMPONENT_NAME}}` | Component name (apply command) | auth |
| `{{COMPONENT_PATH}}` | Full path (apply command) | mapping/loop/auth.md |

### Example: Dated Progress Entries
```dockerfile
PROLOGUE Session: {{DATE}} | Workflow: Deep Dive Analysis
EPILOGUE Append a dated entry to progress.md with format:
  ### {{COMPONENT_NAME}} ({{DATE}})
  | Deliverable | Location | Key Insights |
  ...
```

---

## Mapping Makefile Targets to sdqctl

| Make Target | sdqctl Equivalent | Notes |
|-------------|-------------------|-------|
| `make verify` | `sdqctl flow workflows/verify-*.conv` | Batch verify |
| `make verify-refs` | `sdqctl run workflows/verify-refs.conv` | Single verify |
| `make inventory` | `sdqctl run workflows/gen-inventory.conv` | Generate inventory |
| `make traceability` | `sdqctl run workflows/gen-traceability.conv` | Trace matrix |
| `make ci` | `sdqctl run workflows/integrate/ci-pipeline.conv` | Full CI |

---

## The 5-Facet Workflow Pattern

Each component analysis should update all 5 facets:

```dockerfile
# 5-facet-analysis.conv
MODEL claude-sonnet-4
ADAPTER copilot
MODE analysis
MAX-CYCLES 5
VALIDATION-MODE lenient

# Core documents
CONTEXT @traceability/requirements.md
CONTEXT @traceability/gaps.md
CONTEXT @mapping/cross-project/terminology-matrix.md
CONTEXT @progress.md

PROLOGUE Current date: {{DATE}}
PROLOGUE Component: {{COMPONENT_NAME}}

# Cycle 1: Terminology
PROMPT Update terminology-matrix.md:
  - Extract new terms from the component
  - Map to canonical names
  - Note cross-project variants

# Cycle 2: Gaps
PROMPT Update gaps.md:
  - Document undocumented behaviors
  - Assign GAP-<CATEGORY>-NNN IDs
  - Link to affected systems

# Cycle 3: Requirements
PROMPT Update requirements.md:
  - Extract requirements from gaps
  - Assign REQ-NNN IDs
  - Define verification criteria

# Cycle 4: Deep Dive
PROMPT Create/update deep-dive document:
  - Document implementation details
  - Include code references
  - Link to requirements and gaps

# Cycle 5: Progress
PROMPT Append session entry to progress.md:
  - Date and component name
  - Deliverables table
  - Gaps identified

EPILOGUE Summarize all changes made across facets.

OUTPUT-FORMAT markdown
OUTPUT-FILE docs/faceted-analysis-summary.md
```

---

## Apply Command for Batch Analysis

Analyze multiple components with the same workflow:

```bash
# Apply workflow to all mapping directories
sdqctl apply workflows/design/deep-dive-template.conv \
  --components "mapping/*/README.md" \
  --progress progress.md \
  --output-dir docs/10-domain/

# Template variables available:
# {{COMPONENT_NAME}} = "loop", "aaps", etc.
# {{COMPONENT_PATH}} = full path to README.md
```

---

## Workflow Categories

### Discovery Workflows
Located in `workflows/discovery/`:
- `component-discovery.conv` - Find and catalog components
- `terminology-extraction.conv` - Extract terms from source
- `gap-discovery.conv` - Identify undocumented behaviors
- `cross-project-diff.conv` - Compare implementations

### Design Workflows
Located in `workflows/design/`:
- `deep-dive-template.conv` - 5-facet analysis template
- `requirement-extraction.conv` - Convert gaps to requirements
- `spec-generation.conv` - Generate OpenAPI specs
- `conformance-scenario.conv` - Create test scenarios

### Iteration Workflows
Located in `workflows/iterate/`:
- `progress-update.conv` - Update progress.md
- `facet-refresh.conv` - Refresh all 5 facets
- `verification-loop.conv` - Continuous verification

### Integration Workflows
Located in `workflows/integrate/`:
- `tool-validation.conv` - Run Python tools, analyze results
- `ci-pipeline.conv` - Full CI with verification

---

## Common Patterns

### Pattern 1: Tool → AI Analysis
```dockerfile
RUN-OUTPUT always
RUN python tools/verify_refs.py --json
PROMPT The tool output above shows broken references.
  For each broken ref:
  1. Identify the correct file
  2. Suggest a fix
  3. Explain why it broke
```

### Pattern 2: Exploratory Research
```dockerfile
VALIDATION-MODE lenient
CONTEXT-OPTIONAL @externals/{{repo}}/README.md

PROMPT Explore the {{repo}} repository:
  - Find main entry points
  - Document key data structures
  - Note integration patterns
```

### Pattern 3: Progress Tracking
```dockerfile
PROLOGUE Session: {{DATE}}
EPILOGUE Add entry to progress.md:
  ### Component ({{DATE}})
  | Deliverable | Location | Summary |
  |-------------|----------|---------|
  | Deep Dive | docs/10-domain/... | Key findings |
  
  **Gaps Identified**: GAP-XXX-001
```

### Pattern 4: Cross-Project Comparison
```dockerfile
CONTEXT @mapping/loop/README.md
CONTEXT @mapping/aaps/README.md
CONTEXT @mapping/trio/README.md

PROMPT Compare {{FEATURE}} across Loop, AAPS, and Trio:
  1. Field names and types
  2. Behavioral differences
  3. Alignment opportunities
```

---

## Troubleshooting

### "Context file not found" errors
```bash
# Use lenient mode
sdqctl run workflow.conv --allow-missing

# Or update workflow with:
VALIDATION-MODE lenient
```

### "Pattern matches no files"
```dockerfile
# Mark as optional
CONTEXT-OPTIONAL @pattern/**/*.yaml

# Or exclude from validation
CONTEXT-EXCLUDE pattern/**/*.yaml
```

### Tool execution fails
```dockerfile
# Continue on error
RUN-ON-ERROR continue
RUN python tools/verify_refs.py

# Analyze failure
PROMPT The tool failed. Review the error and suggest fixes.
```

### Context overflow
```dockerfile
# Set explicit limits
CONTEXT-LIMIT 70%
ON-CONTEXT-LIMIT compact

# Or use compact session mode
# sdqctl cycle workflow.conv --session-mode compact
```

---

## See Also

- [sdqctl README](https://github.com/bewest/copilot-do-proposal/tree/main/sdqctl)
- [CONTINUATION-PROMPTS.md](./CONTINUATION-PROMPTS.md) - Ready-to-use prompts
- [FEEDBACK-RESPONSE.md](https://github.com/bewest/copilot-do-proposal/blob/main/sdqctl/FEEDBACK-RESPONSE.md) - P0 fixes implemented
- [workflows/README.md](../workflows/README.md) - Workflow reference
