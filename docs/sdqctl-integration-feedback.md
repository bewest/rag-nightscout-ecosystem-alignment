# sdqctl Integration Feedback Report

**From:** rag-nightscout-ecosystem-alignment workspace  
**To:** sdqctl development team  
**Date:** 2026-01-24 (Updated)  
**sdqctl Version Tested:** 0.1.0 → 0.1.1

---

## Executive Summary

We've been evaluating sdqctl for orchestrating AI-assisted workflows in a complex multi-repository documentation workspace. Our workspace has evolved over months through iterative Replit AI development, resulting in 14 ConversationFile workflows, 14+ Python tools, and extensive cross-project documentation.

**UPDATE (2026-01-24):** After iterative improvements, **all 14 workflows now pass validation**. Key improvements:

- **50% reduction in false positives** (502 → 249 broken refs)
- **Glob pattern fixes** resolved all `@mapping/*/README.md` style issues
- **VALIDATION-MODE lenient** directive now available for exploratory workflows
- **verify refs** now supports `alias:path` references using refcat resolution

### Compatibility Score (Updated)

| Category | Previous | Current | Notes |
|----------|----------|---------|-------|
| ConversationFile parsing | ✅ Works | ✅ Works | All .conv files parse correctly |
| Context file resolution | ⚠️ Partial | ✅ Works | Globs and wildcards fully supported |
| Validation strictness | ❌ Blocking | ✅ Resolved | `VALIDATION-MODE lenient` available |
| Command coverage | ⚠️ Partial | ✅ Full | verify refs/links/traceability implemented |

### Resolved P0 Issues

1. ~~**P0:** Add `--allow-missing` flag or `MODE lenient` directive~~ → ✅ `VALIDATION-MODE lenient`
2. ~~**P0:** Fix glob pattern matching for `@mapping/*/README.md` style patterns~~ → ✅ Fixed
3. ~~**P1:** Make CONTEXT validation warn by default~~ → ✅ Lenient mode available
4. ~~**P2:** Implement workspace/verify/trace subcommands~~ → ✅ `sdqctl verify refs/links/traceability`

---

## Part 1: Validation Issues

### 1.1 Workflow Validation Matrix (Updated 2026-01-24)

| Workflow | Previous | Current | Notes |
|----------|----------|---------|-------|
| `ci-pipeline.conv` | ❌ Failed | ✅ Valid | Glob patterns fixed |
| `cross-project-alignment.conv` | ❌ Failed | ✅ Valid | Path resolution improved |
| `deep-dive-template.conv` | ✅ Valid | ✅ Valid | - |
| `example-audit.conv` | ✅ Valid | ✅ Valid | - |
| `faceted-analysis.conv` | ✅ Valid | ✅ Valid | - |
| `full-verification.conv` | ❌ Failed | ✅ Valid | CONTEXT-OPTIONAL now recognized |
| `gap-detection.conv` | ✅ Valid | ✅ Valid | - |
| `gen-coverage-report.conv` | ❌ Failed | ✅ Valid | Glob patterns fixed |
| `gen-inventory.conv` | ✅ Valid | ✅ Valid | - |
| `gen-traceability.conv` | ❌ Failed | ✅ Valid | Glob patterns fixed |
| `verify-assertions.conv` | ❌ Failed | ✅ Valid | YAML patterns now work |
| `verify-coverage.conv` | ❌ Failed | ✅ Valid | Glob patterns fixed |
| `verify-refs.conv` | ✅ Valid | ✅ Valid | - |
| `verify-terminology.conv` | ❌ Failed | ✅ Valid | `@mapping/*/README.md` fixed |

**Result: 14/14 workflows pass (was 6/14)**

### 1.2 Root Cause Analysis

#### Issue 1: Aspirational Context Patterns

Our workflows were written to define the *intended* file structure, not just the current state. This is intentional—the workflow acts as a spec for what files should exist.

**Example from `ci-pipeline.conv`:**
```dockerfile
CONTEXT @conformance/scenarios/**/*.yaml
```

**Reality:** We have `conformance/scenarios/override-supersede/README.md` (markdown), not YAML files. The YAML format is aspirational—we planned to convert but haven't yet.

**Desired Behavior:** Run the workflow anyway, with a warning that some context is missing.

#### Issue 2: Naming Divergence

Our workflow references a simplified name that doesn't exist:

**Example from `cross-project-alignment.conv`:**
```dockerfile
CONTEXT @mapping/xdrip/README.md
```

**Reality:** We have:
- `mapping/xdrip-android/README.md`
- `mapping/xdrip4ios/README.md`

**Desired Behavior:** Either warn and continue, or support brace expansion `@mapping/xdrip{,-android,4ios}/README.md`.

#### Issue 3: Glob Pattern Bug (Suspected)

**Example from `verify-terminology.conv`:**
```dockerfile
CONTEXT @mapping/*/README.md
```

**Reality:** 14 README.md files exist:
```
mapping/aaps/README.md
mapping/cgm-remote-monitor/README.md
mapping/diable/README.md
mapping/loop/README.md
mapping/loopcaregiver/README.md
mapping/loopfollow/README.md
mapping/nightguard/README.md
mapping/nightscout/README.md  # Note: not at this exact path
mapping/nightscout-connect/README.md
mapping/nightscout-reporter/README.md
mapping/nightscout-roles-gateway/README.md
mapping/openaps/README.md
mapping/oref0/README.md
mapping/trio/README.md
mapping/xdrip4ios/README.md
mapping/xdrip-android/README.md
mapping/xdrip-js/README.md
```

**Observed:** Validation fails claiming pattern matches no files.

**Expected:** Pattern should match 14+ files.

**Hypothesis:** The glob implementation may have an issue with `*/` in the middle of paths, or may be using a different CWD than expected.

### 1.3 Proposed Solutions

#### Solution A: Validation Modes

Add a `MODE` value or flag for validation strictness:

```dockerfile
# In .conv file
MODE lenient        # Warn on missing context, continue execution
MODE strict         # Current behavior - fail on any missing context
MODE exploratory    # Warn on missing, allow dynamic context addition
```

Or via CLI:
```bash
sdqctl validate workflow.conv --allow-missing
sdqctl run workflow.conv --allow-missing-context
```

#### Solution B: CONTEXT-OPTIONAL Directive

Allow marking specific context as optional:

```dockerfile
CONTEXT @traceability/requirements.md           # Required
CONTEXT @traceability/gaps.md                   # Required
CONTEXT-OPTIONAL @conformance/scenarios/**/*.yaml  # Nice to have
```

#### Solution C: Warning vs Error Behavior

Change default behavior:
- **Current:** Missing context = validation error
- **Proposed:** Missing context = warning (stderr), continues execution
- **Strict mode:** Missing context = error (current behavior)

```bash
# Default: warns and continues
sdqctl run workflow.conv

# Strict: fails on any issue
sdqctl run workflow.conv --strict
```

---

## Part 2: Ergonomic Friction

### 2.1 Iterative Development Pattern

Our workspace evolved through what we call the "5-facet documentation cycle":

```
For each component analyzed:
1. Update terminology matrix (mapping/cross-project/terminology-matrix.md)
2. Add gaps discovered (traceability/gaps.md)
3. Extract requirements (traceability/requirements.md)
4. Write deep-dive doc (docs/10-domain/{component}-deep-dive.md)
5. Log progress (progress.md)
```

This pattern emerged organically from Replit AI sessions. Each session:
1. Explores source code in `externals/`
2. Discovers implementation details
3. Creates/updates documentation
4. Logs what was done

**Key Insight:** The file structure evolves *during* work, not before.

### 2.2 Living Workspace vs Declarative Workflow

| sdqctl Model | Our Model |
|--------------|-----------|
| Files exist before workflow runs | Files created during workflow |
| CONTEXT defines inputs | CONTEXT defines expected outputs too |
| Workflow is repeatable | Each run explores new territory |
| Checkpoints capture state | progress.md captures narrative |

**Tension:** sdqctl optimizes for CI/CD repeatability. We need exploratory research support.

### 2.3 Session Tracking Pattern

We use `progress.md` as a session log:

```markdown
### Component Name (YYYY-MM-DD)

Brief description of what was analyzed.

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| Doc Name | `docs/10-domain/component-deep-dive.md` | Summary |

**Gaps Identified**: GAP-XXX-001, GAP-XXX-002
```

**Request:** Consider native session logging that:
- Auto-appends to a configured file
- Captures workflow outputs
- Links to checkpoints

---

## Part 3: Feature Requests

### 3.1 From INTEGRATION-PROPOSAL.md

The sdqctl team's own proposal identifies features we strongly endorse:

#### Priority: High

| Feature | Proposed Command | Our Use Case |
|---------|------------------|--------------|
| Workspace sync | `sdqctl workspace sync` | Clone/update 16 external repos |
| Workspace status | `sdqctl workspace status` | Check repo health |
| Workspace freeze | `sdqctl workspace freeze` | Pin commit SHAs |
| Verify refs | `sdqctl verify refs` | Validate code references |
| Verify coverage | `sdqctl verify coverage` | REQ/GAP coverage matrix |

#### Priority: Medium

| Feature | Proposed Command | Our Use Case |
|---------|------------------|--------------|
| Trace requirement | `sdqctl trace req REQ-001` | Find all refs to requirement |
| Trace gap | `sdqctl trace gap GAP-SYNC-001` | Find all refs to gap |
| Generate matrix | `sdqctl trace matrix` | Full traceability matrix |
| Verify terminology | `sdqctl verify terminology` | Cross-project term consistency |

### 3.2 Additional Feature Requests

#### FR-001: Dynamic Context Inclusion

Include tool output as context:

```dockerfile
CONTEXT @tool:verify_refs --json    # Run tool, include output
CONTEXT @shell:git diff HEAD~1      # Run command, include output
```

**Use Case:** Verification workflows need to see current state, not static files.

#### FR-002: Conditional Context

Include context based on conditions:

```dockerfile
CONTEXT-IF-EXISTS @conformance/scenarios/**/*.yaml
CONTEXT-IF-NOT-EXISTS @conformance/scenarios/**/*.yaml THEN-RUN make gen-scenarios
```

**Use Case:** Bootstrap workflows that create missing files.

#### FR-003: Output Append Mode

Append to existing file instead of overwrite:

```dockerfile
OUTPUT-FILE progress.md
OUTPUT-MODE append     # Add to end of file
OUTPUT-SECTION "## Session Log"  # Find section, append there
```

**Use Case:** Accumulating session logs.

#### FR-004: Workspace-Aware Defaults

Auto-detect workspace configuration:

```bash
# If .sdqctl/config.yaml exists, use it
sdqctl run workflow.conv  # Picks up workspace settings

# .sdqctl/config.yaml
workspace:
  root: .
  externals: externals/
  lockfile: workspace.lock.json
defaults:
  adapter: copilot
  model: claude-sonnet-4
context:
  allow_missing: true
```

---

## Part 4: Workarounds

Until features are implemented, here are workarounds we're using:

### 4.1 Workflow Splitting

Split workflows into "core" (validated) and "extended" (aspirational):

```bash
# Core workflows that pass validation
sdqctl flow workflows/verify-refs.conv workflows/gen-inventory.conv

# Extended workflows run with make (bypasses validation)
make verify
```

### 4.2 Symlink Missing Directories

```bash
# Create expected directory structure
ln -s xdrip-android mapping/xdrip
```

**Problem:** Pollutes workspace with compatibility shims.

### 4.3 Touch Empty Files

```bash
# Create placeholder YAML files
mkdir -p conformance/scenarios/placeholder
touch conformance/scenarios/placeholder/dummy.yaml
```

**Problem:** Misleading—suggests content exists when it doesn't.

### 4.4 Use make as Orchestrator

```bash
# Makefile handles tool execution, sdqctl handles AI workflows
make verify && sdqctl run workflows/gap-detection.conv
```

**Problem:** Two tools instead of one unified interface.

---

## Part 5: Compatibility Notes

### 5.1 What Works Well

1. **ConversationFile format** - Clean, readable, Dockerfile-like syntax
2. **PROMPT chaining** - Multiple prompts in sequence is intuitive
3. **CHECKPOINT** - Pause/resume pattern is valuable
4. **OUTPUT-FORMAT/OUTPUT-FILE** - Clear output specification
5. **Adapter abstraction** - `copilot` adapter works with GitHub Copilot CLI

### 5.2 Model/Adapter Observations

| Directive | Value | Notes |
|-----------|-------|-------|
| `MODEL claude-sonnet-4` | ✅ | Recognized by copilot adapter |
| `MODEL gpt-4` | ✅ | Recognized |
| `ADAPTER copilot` | ✅ | Works with Copilot CLI |
| `ADAPTER mock` | ✅ | Useful for testing |

### 5.3 Version Compatibility

- **sdqctl 0.1.0** - Current version tested
- **Python 3.11+** - Required
- **Click 8.x** - CLI framework

---

## Appendix A: Test Commands

```bash
# Validate all workflows
source ./activate-sdqctl.sh
for f in workflows/*.conv; do 
  echo "=== $f ===" 
  sdqctl validate "$f" 2>&1 | head -5
done

# Show parsed workflow
sdqctl show workflows/ci-pipeline.conv

# Check status
sdqctl status

# Dry run (doesn't execute AI)
sdqctl run workflows/verify-refs.conv --dry-run
```

## Appendix B: File Structure Reference

```
rag-nightscout-ecosystem-alignment/
├── workflows/           # 15 .conv files
│   ├── ci-pipeline.conv
│   ├── cross-project-alignment.conv
│   ├── deep-dive-template.conv
│   ├── example-audit.conv
│   ├── faceted-analysis.conv
│   ├── full-verification.conv
│   ├── gap-detection.conv
│   ├── gen-coverage-report.conv
│   ├── gen-inventory.conv
│   ├── gen-traceability.conv
│   ├── verify-assertions.conv
│   ├── verify-coverage.conv
│   ├── verify-refs.conv
│   ├── verify-terminology.conv
│   └── README.md
├── tools/               # 14+ Python verification tools
├── mapping/             # 17 project mapping directories
├── traceability/        # Requirements, gaps, coverage
├── conformance/         # Scenarios and assertions
├── specs/               # OpenAPI and JSON Schema
├── docs/                # Documentation
├── externals/           # 16 cloned repositories (gitignored)
├── workspace.lock.json  # Repository version pins
├── Makefile             # 22 orchestration targets
├── progress.md          # Session tracking
└── activate-sdqctl.sh   # venv activation script
```

## Appendix C: Related Documents

- [INTEGRATION-PROPOSAL.md](../externals/copilot-do-proposal/sdqctl/INTEGRATION-PROPOSAL.md) - sdqctl team's integration roadmap
- [workflows/README.md](../workflows/README.md) - Workflow documentation
- [replit.md](../replit.md) - Workspace overview and patterns

---

## Part 6: Recent Improvements (2026-01-24)

This section documents the improvements made since the original feedback.

### 6.1 verify refs Now Supports Alias References

The `sdqctl verify refs` command now validates both `@-references` and `alias:path` references:

```bash
# Verify all references in workspace
sdqctl verify refs

# With fix suggestions
sdqctl verify refs --suggest-fixes

# JSON output for CI integration
sdqctl verify refs --json > refs-report.json
```

**Example output:**
```
✗ FAILED: Scanned 552 file(s), found 845 reference(s): 596 valid, 249 broken
  ERROR mapping/trio/README.md:42: Broken alias reference: trio:Trio/Sources/Models/Preferences.swift
  HINT: Expected at externals/Trio/Preferences.swift
  SUGGEST: Found: externals/Trio/Trio/Sources/Models/Preferences.swift
```

### 6.2 refcat for Code Extraction

Use `refcat` to extract code snippets for context:

```bash
# Extract with line range
sdqctl refcat "loop:LoopKit/LoopKit/TemporaryScheduleOverride.swift#L1-L20"

# List what a workflow would gather
sdqctl refcat --from-workflow workflows/verify-refs.conv --list-files
```

### 6.3 Iterative Improvement Workflows

Two new workflows for improving sdqctl tools themselves:

```bash
# 3-cycle false positive reduction workflow
sdqctl cycle examples/workflows/tooling/refcat-improvement.conv -n 3

# 5-cycle TDD pattern for verifier improvements
sdqctl cycle examples/workflows/tooling/verifier-test-loop.conv -n 5
```

### 6.4 False Positive Reduction Progress

| Version | Broken Refs | Method |
|---------|-------------|--------|
| Initial | 502 | - |
| +Root-first resolution | 297 | Try workspace root before file-relative |
| +TLD exclusions | 271 | Case-insensitive .edu/.gov/.com |
| +Connection strings | 259 | localhost:, mongo:, redis: |
| +Unix sockets | 258 | sock:, unix:, docker: |
| +Timestamps | 251 | mm:, ss:, hh: |
| +path/to fixes | 249 | Replaced antipattern with real paths |

**Remaining 249 broken refs are real documentation issues** requiring path updates.

### 6.5 Correct Reference Format

For sdqctl tools to validate refs, use full paths from repo root:

```markdown
# ✅ CORRECT: Full path from repo root
See `trio:Trio/Sources/Models/Preferences.swift#L22` for the setting.

# ❌ INCORRECT: Short-form (won't validate)
See `trio:Trio/Sources/Models/Preferences.swift` for the setting.

# ❌ AVOID: Placeholder paths
See `loop:path/to/file.swift` for the implementation.
```

### 6.6 Remaining Work

The 249 remaining broken refs need ecosystem maintainer action:

| Category | Count | Action |
|----------|-------|--------|
| Short-form refs | 140+ | Use full paths |
| Moved files | 80+ | Update to new locations |
| Missing files | 20+ | Create or remove refs |

**To fix:** Run `sdqctl verify refs --suggest-fixes` and update paths.

---

*Report generated from rag-nightscout-ecosystem-alignment workspace analysis.*
