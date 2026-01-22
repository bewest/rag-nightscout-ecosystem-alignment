# Proposal: Unified Verification Directives

**Date:** 2026-01-22  
**Status:** Proposal  
**Author:** Generated via sdqctl planning session  
**Related:** INTEGRATION-PROPOSAL.md (Phase 3: Verify Commands)

---

## Summary

This proposal extends sdqctl with **built-in verification capabilities** exposed through:

1. **CLI commands** (`sdqctl verify refs`) - standalone execution without AI
2. **Declarative .conv directives** (`VERIFY refs`) - integrated workflow verification

This unifies the currently separate approaches:
- External tools invoked via `RUN` directive
- Proposed but unimplemented `sdqctl verify` CLI commands

---

## Motivation

### Current State

Verification in sdqctl workflows requires external tooling:

```dockerfile
# Current approach - requires external tool
RUN-ON-ERROR continue
RUN-OUTPUT always
RUN python tools/verify_refs.py --json 2>/dev/null || echo "No tool"

PROMPT Analyze the verification output...
```

**Problems:**
- External tool must exist at expected path
- No standardized output format
- Manual error handling
- Not portable across projects

### Desired State

Built-in verification with declarative syntax:

```dockerfile
# Proposed approach - built-in
VERIFY-ON-ERROR continue
VERIFY-OUTPUT always

VERIFY refs
VERIFY traceability

PROMPT Analyze the verification results...
```

**Benefits:**
- Works without external dependencies
- Structured, parseable output
- Consistent error handling
- Portable across any sdqctl project

---

## Design

### Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    User Interface                        │
├─────────────────────────┬───────────────────────────────┤
│   CLI Commands          │   .conv Directives            │
│   sdqctl verify refs    │   VERIFY refs                 │
│   sdqctl verify links   │   VERIFY links                │
│   sdqctl verify all     │   CHECK-TRACEABILITY          │
└─────────────────────────┴───────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│              sdqctl.verifiers (shared core)              │
├─────────────────────────────────────────────────────────┤
│  refs.py        - Code reference validation              │
│  links.py       - URL/file link checking                 │
│  terminology.py - Term consistency checking              │
│  traceability.py - Req→Spec→Test matrix                  │
│  assertions.py  - Assertion tracing                      │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│              VerificationResult (dataclass)              │
├─────────────────────────────────────────────────────────┤
│  passed: bool                                            │
│  errors: list[VerificationError]                         │
│  warnings: list[VerificationWarning]                     │
│  summary: str                                            │
│  details: dict                                           │
└─────────────────────────────────────────────────────────┘
```

### Layer 1: CLI Commands

Standalone verification without AI involvement:

```bash
# Run all verifications
sdqctl verify all

# Individual verifiers
sdqctl verify refs [--json] [--fix-stale] [--verbose]
sdqctl verify links [--json] [--external] [--timeout N]
sdqctl verify terminology [--json] [--glossary FILE]
sdqctl verify traceability [--json] [--matrix] [--gaps-only]
sdqctl verify assertions [--json]

# Output options
sdqctl verify refs --json           # Machine-readable JSON
sdqctl verify refs --fix-stale      # Auto-fix stale references
sdqctl verify all --report FILE     # Write report to file
```

**Exit codes:**
- `0` - All verifications passed
- `1` - One or more verifications failed
- `2` - Configuration/runtime error

### Layer 2: Declarative Directives

New ConversationFile directives for workflow-integrated verification:

#### Core Directives

| Directive | Description | Example |
|-----------|-------------|---------|
| `VERIFY <type>` | Run verification | `VERIFY refs` |
| `VERIFY-ON-ERROR` | Failure behavior | `VERIFY-ON-ERROR continue` |
| `VERIFY-OUTPUT` | Output injection | `VERIFY-OUTPUT always` |
| `VERIFY-LIMIT` | Output size limit | `VERIFY-LIMIT 10K` |

#### Verification Types

| Type | Description |
|------|-------------|
| `refs` | Validate code references resolve to files |
| `links` | Check URLs and file links |
| `terminology` | Verify term consistency |
| `traceability` | Check req→spec→test links |
| `assertions` | Trace assertion coverage |
| `all` | Run all verifications |

#### Convenience Aliases

| Alias | Equivalent |
|-------|------------|
| `CHECK-REFS` | `VERIFY refs` |
| `CHECK-LINKS` | `VERIFY links` |
| `CHECK-TRACEABILITY` | `VERIFY traceability` |

#### Configuration Options

**VERIFY-ON-ERROR** - What to do when verification fails:
- `fail` (default) - Stop workflow execution
- `continue` - Log error, continue workflow
- `warn` - Treat as warning, continue

**VERIFY-OUTPUT** - When to inject output into prompt context:
- `on-error` (default) - Only when verification fails
- `always` - Always inject results
- `never` - Don't inject (just log)

**VERIFY-LIMIT** - Maximum output size:
- `5K`, `10K`, `50K` - Character limit
- `none` - No limit (use with caution)

### Layer 3: Workflow Integration

#### Execution Model

VERIFY directives execute **synchronously before the next PROMPT**:

```dockerfile
VERIFY refs           # Runs immediately
VERIFY traceability   # Runs after refs completes
PROMPT Analyze...     # Has access to verification results
```

#### Output Injection

Verification results are injected as a structured section:

```markdown
## Verification Results

### refs
✅ Passed: 47 references validated
- Valid: 47
- Broken: 0
- Stale: 0

### traceability  
⚠️ Warnings: 3 gaps found
- Requirements: 12/12 have specs
- Specs: 9/12 have tests (3 missing)
- Tests: 15/15 implemented
```

#### Template Variable

Results also available via template:

```dockerfile
PROMPT Review these issues: {{VERIFY_RESULTS}}
```

---

## Example Workflows

### Basic Verification

```dockerfile
# verify-basic.conv
MODEL gpt-4
ADAPTER copilot
MODE audit

VERIFY refs
VERIFY links

PROMPT Summarize any broken references or links found.

OUTPUT-FILE reports/link-check-{{DATE}}.md
```

### Traceability Audit

```dockerfile
# traceability-audit.conv
MODEL gpt-4
ADAPTER copilot
MODE audit

VERIFY-ON-ERROR continue
VERIFY-OUTPUT always
VERIFY-LIMIT 20K

VERIFY traceability

PROMPT ## Traceability Gap Analysis

Based on the verification results:

1. **Coverage Summary**
   - What percentage of requirements have specifications?
   - What percentage of specs have tests?

2. **Priority Gaps**
   - Which requirements lack specs? (highest priority)
   - Which specs lack tests?

3. **Recommendations**
   - Suggest next steps to close gaps

OUTPUT-FILE reports/traceability-{{DATE}}.md
```

### CI Integration

```dockerfile
# ci-verify.conv
MODEL gpt-4
ADAPTER mock
MODE audit
MAX-CYCLES 1

# Strict mode for CI - fail on any error
VERIFY-ON-ERROR fail
VERIFY-OUTPUT on-error

VERIFY all

PROMPT If any verifications failed, explain the issues and how to fix them.
       If all passed, confirm the codebase is in good shape.

OUTPUT-FILE reports/ci-verify-{{DATE}}.md
```

---

## Comparison: RUN vs VERIFY

| Aspect | `RUN` (current) | `VERIFY` (proposed) |
|--------|-----------------|---------------------|
| **Dependencies** | Requires external tool | Built-in |
| **Portability** | Tool path must exist | Works anywhere |
| **Output format** | Raw text (manual parsing) | Structured (auto-parsed) |
| **Error handling** | Generic RUN-ON-ERROR | Verification-aware |
| **Fix capability** | Tool-specific flags | Unified `--fix` |
| **Context injection** | Raw output | Formatted section |
| **CI integration** | Exit code from tool | Standardized codes |

### Migration Path

Existing RUN-based workflows continue to work:

```dockerfile
# Old way (still works)
RUN python tools/verify_refs.py --json

# New way (recommended)
VERIFY refs
```

---

## Implementation Phases

### Phase 1: Core Library (`sdqctl/verifiers/`)

Create shared verification logic:

```python
# sdqctl/verifiers/__init__.py
from .base import VerificationResult, Verifier
from .refs import RefsVerifier
from .links import LinksVerifier
from .terminology import TerminologyVerifier
from .traceability import TraceabilityVerifier
from .assertions import AssertionsVerifier

VERIFIERS = {
    "refs": RefsVerifier,
    "links": LinksVerifier,
    "terminology": TerminologyVerifier,
    "traceability": TraceabilityVerifier,
    "assertions": AssertionsVerifier,
}
```

```python
# sdqctl/verifiers/base.py
from dataclasses import dataclass, field
from typing import Protocol
from pathlib import Path

@dataclass
class VerificationError:
    file: str
    line: int | None
    message: str
    fix_hint: str | None = None

@dataclass
class VerificationResult:
    passed: bool
    errors: list[VerificationError] = field(default_factory=list)
    warnings: list[VerificationError] = field(default_factory=list)
    summary: str = ""
    details: dict = field(default_factory=dict)
    
    def to_markdown(self) -> str:
        """Format results as markdown for context injection."""
        ...
    
    def to_json(self) -> dict:
        """Format results as JSON for CLI output."""
        ...

class Verifier(Protocol):
    def verify(self, root: Path, **options) -> VerificationResult:
        """Run verification and return results."""
        ...
```

### Phase 2: CLI Commands (`sdqctl/commands/verify.py`)

```python
# sdqctl/commands/verify.py
import click
from ..verifiers import VERIFIERS, VerificationResult

@click.group()
def verify():
    """Static verification suite."""
    pass

@verify.command()
@click.option("--json", "json_output", is_flag=True)
@click.option("--fix-stale", is_flag=True)
@click.option("--verbose", "-v", is_flag=True)
def refs(json_output: bool, fix_stale: bool, verbose: bool):
    """Verify code references resolve to actual files."""
    verifier = VERIFIERS["refs"]()
    result = verifier.verify(Path.cwd(), fix_stale=fix_stale)
    _output_result(result, json_output, verbose)

@verify.command()
def all():
    """Run all verifications."""
    results = {}
    for name, verifier_cls in VERIFIERS.items():
        results[name] = verifier_cls().verify(Path.cwd())
    # Aggregate and output
```

### Phase 3: Directive Support (`core/conversation.py`)

Add to DirectiveType enum:

```python
class DirectiveType(Enum):
    # ... existing directives ...
    
    # Verification directives
    VERIFY = "VERIFY"
    VERIFY_ON_ERROR = "VERIFY-ON-ERROR"
    VERIFY_OUTPUT = "VERIFY-OUTPUT"
    VERIFY_LIMIT = "VERIFY-LIMIT"
    
    # Aliases (parsed as VERIFY)
    CHECK_REFS = "CHECK-REFS"
    CHECK_LINKS = "CHECK-LINKS"
    CHECK_TRACEABILITY = "CHECK-TRACEABILITY"
```

### Phase 4: Execution (`commands/run.py`)

Handle VERIFY directives during workflow execution:

```python
def _execute_verify(directive: Directive, config: VerifyConfig) -> str:
    """Execute a VERIFY directive and return formatted output."""
    verify_type = directive.value.strip()
    verifier = VERIFIERS.get(verify_type)
    if not verifier:
        raise ValueError(f"Unknown verification type: {verify_type}")
    
    result = verifier().verify(Path.cwd())
    
    if not result.passed and config.on_error == "fail":
        raise VerificationError(result.summary)
    
    if config.output == "always" or (config.output == "on-error" and not result.passed):
        return result.to_markdown()
    
    return ""
```

---

## Open Questions

### 1. Blocking vs Parallel Execution

**Option A:** VERIFY runs synchronously before next PROMPT (proposed)
- Simpler mental model
- Results guaranteed available

**Option B:** VERIFY runs in parallel, results injected when ready
- Faster for multiple verifications
- More complex state management

**Recommendation:** Start with Option A (synchronous)

### 2. Output Location

**Option A:** Inject as `## Verification Results` section (proposed)
- Consistent format
- Easy for AI to find

**Option B:** Available only via `{{VERIFY_RESULTS}}` template
- More control over placement
- Requires explicit inclusion

**Recommendation:** Both - auto-inject section AND provide template

### 3. Cycle Mode Behavior

**Option A:** Run verification once at workflow start
**Option B:** Run verification each cycle
**Option C:** Explicit `VERIFY-EACH-CYCLE` directive

**Recommendation:** Option A by default, Option C for override

---

## Relationship to INTEGRATION-PROPOSAL.md

This proposal is an **extension** of INTEGRATION-PROPOSAL.md Phase 3:

| INTEGRATION-PROPOSAL.md | This Proposal |
|------------------------|---------------|
| `sdqctl verify refs` CLI | ✅ Same |
| `sdqctl verify all` CLI | ✅ Same |
| Import rag-nightscout tools | ✅ Same approach |
| No .conv directive support | ➕ Adds VERIFY directive |
| No output injection | ➕ Adds context injection |
| No template support | ➕ Adds {{VERIFY_RESULTS}} |

This proposal should be merged with or replace Phase 3 of INTEGRATION-PROPOSAL.md.

---

## Next Steps

1. Review and approve proposal
2. Decide on open questions (blocking, output location, cycle behavior)
3. Implement Phase 1 (core library) 
4. Implement Phase 2 (CLI commands)
5. Implement Phase 3 (directive parsing)
6. Implement Phase 4 (execution integration)
7. Update documentation
8. Create example workflows

---

## References

- `INTEGRATION-PROPOSAL.md` - Original integration plan
- `docs/TRACEABILITY-WORKFLOW.md` - Current traceability documentation
- `examples/workflows/verify-with-run.conv` - Current RUN-based approach
- `examples/workflows/traceability/verification-loop.conv` - Traceability example
