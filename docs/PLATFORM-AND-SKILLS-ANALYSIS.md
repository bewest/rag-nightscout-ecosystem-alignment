# Analysis: Platform & Skills for SDLC Automation

## Question: Are Makefile + Python the Right Choice?

### Current Assessment

| Aspect | Makefile | Python (stdlib-only) | Verdict |
|--------|----------|---------------------|---------|
| **Portability** | ✅ Universal on Unix, WSL | ✅ Python 3 everywhere | Good |
| **Dependency burden** | ✅ Zero deps | ✅ Zero deps (intentional) | Excellent |
| **Orchestration** | ✅ Declarative, parallel | ⚠️ Subprocess-based | Adequate |
| **Extensibility** | ⚠️ Shell escaping pain | ✅ Easy to add features | Good |
| **AI agent friendly** | ⚠️ Hard to parse/modify | ✅ JSON output, structured | Good |
| **Cross-platform** | ⚠️ Windows needs WSL/MSYS2 | ✅ Works everywhere | Acceptable |

**Verdict: Makefile + Python is a reasonable choice**, especially given:
- Zero external dependencies (maximum portability)
- JSON output for agent consumption
- Familiar patterns for Unix developers

### Alternatives Considered

#### Option 1: Pure Python with Click/Typer
```python
# Replace Makefile with Python CLI
@app.command()
def verify():
    """Run all static verification tools."""
    ...
```
**Pros:** Single language, better Windows support, richer CLI
**Cons:** Adds dependency, loses Make's parallelism

#### Option 2: Node.js/TypeScript
```typescript
// Given 31% of ecosystem is Node.js
import { $ } from 'bun'  // or zx
await $`python tools/verify_refs.py`
```
**Pros:** Matches Nightscout (cgm-remote-monitor) stack, npm ecosystem
**Cons:** Python still needed for some tools, adds node_modules weight

#### Option 3: Deno/Bun with TypeScript
**Pros:** Modern, single binary, TypeScript native
**Cons:** Smaller ecosystem, team learning curve

#### Option 4: Just (justfile)
```just
# Modern command runner
verify: verify-refs verify-coverage verify-terminology
verify-refs:
    python3 tools/verify_refs.py
```
**Pros:** Better syntax than Make, cross-platform
**Cons:** Not as universal as Make

### Recommendation

**Keep Makefile + Python as the foundation**, but consider:

1. **Add a `pyproject.toml`** for future dependency management:
```toml
[project]
name = "nightscout-alignment-tools"
version = "0.1.0"
requires-python = ">=3.9"
dependencies = []  # Keep zero for now

[project.optional-dependencies]
dev = ["pytest", "pyyaml"]
```

2. **Consider Node.js for new tooling** when it touches cgm-remote-monitor directly

3. **Keep tools language-agnostic** - output JSON, accept JSON input

---

## Skills Needed for SDLC Matrix Cycling

### The SDLC Matrix

For each **component** (16 repos × N modules), cycle through **lifecycle phases**:

```
                    │ Requirements │ Design │ Implementation │ Testing │ Documentation │
────────────────────┼──────────────┼────────┼────────────────┼─────────┼───────────────┤
Loop (Swift)        │      ○       │   ○    │       ○        │    ○    │       ○       │
AAPS (Kotlin)       │      ○       │   ○    │       ○        │    ○    │       ○       │
Nightscout (Node)   │      ○       │   ○    │       ○        │    ○    │       ○       │
xDrip+ (Java)       │      ○       │   ○    │       ○        │    ○    │       ○       │
...                 │      ...     │  ...   │      ...       │   ...   │      ...      │
```

Each cell requires different skills.

### Proposed Skill Categories

#### 1. **Language Analysis Skills** (per platform)

| Skill Name | Languages | Capabilities |
|------------|-----------|--------------|
| `swift-analyzer` | Swift | Parse Swift AST, extract protocols/structs, find CGM-related code |
| `kotlin-analyzer` | Kotlin/Java | Parse Gradle projects, extract data classes, find Entity classes |
| `node-analyzer` | JavaScript/TypeScript | Parse package.json, extract API routes, find MongoDB schemas |
| `python-analyzer` | Python | Parse setup.py/pyproject.toml, extract CLI commands |

**Implementation approach:**
```bash
# Each could be a Copilot skill or standalone tool
~/.copilot/skills/
├── swift-analyzer/
│   └── SKILL.md  # Instructions for analyzing Swift codebases
├── kotlin-analyzer/
│   └── SKILL.md
└── node-analyzer/
    └── SKILL.md
```

#### 2. **SDLC Phase Skills**

| Skill Name | Phase | What It Does |
|------------|-------|--------------|
| `requirements-extractor` | Requirements | Find MUST/SHALL statements, extract REQ-NNN |
| `api-mapper` | Design | Extract OpenAPI from code, compare schemas |
| `implementation-tracer` | Implementation | Link code to requirements, find untested paths |
| `test-analyzer` | Testing | Parse test files, extract coverage, find gaps |
| `doc-generator` | Documentation | Generate/update docs from code analysis |

#### 3. **Cross-Cutting Skills**

| Skill Name | Purpose |
|------------|---------|
| `terminology-aligner` | Ensure consistent naming across projects |
| `gap-detector` | Find interoperability gaps between systems |
| `sync-tracer` | Track data flow: xDrip → AAPS → Nightscout → Loop |
| `schema-differ` | Compare data models across versions/projects |

### Skill Invocation Patterns

#### Pattern 1: Single Component, Full Lifecycle
```bash
# Analyze one component across all SDLC phases
copilot --prompt "
  Using skills: swift-analyzer, requirements-extractor, test-analyzer, doc-generator
  
  Analyze LoopWorkspace/LoopAlgorithm for:
  1. Extract requirements from code comments and tests
  2. Map API surface to OpenAPI spec
  3. Identify untested code paths
  4. Update documentation gaps
  
  Update all 5 facets.
"
```

#### Pattern 2: Single Phase, All Components
```bash
# Run one phase across all repos
for repo in loop aaps trio xdrip nightscout; do
  copilot --prompt "
    Using skill: test-analyzer
    
    Analyze $repo test coverage for CGM data handling.
    Output: JSON with coverage percentage, untested functions.
  " --share "coverage-$repo.json"
done
```

#### Pattern 3: Matrix Batch (Future `copilot agent batch`)
```bash
# When batch becomes available
copilot agent batch \
  --parallel 4 \
  workflows/analyze-*.copilot \
  --output matrix-results.jsonl

# Where workflows/ contains:
# analyze-loop-requirements.copilot
# analyze-loop-testing.copilot
# analyze-aaps-requirements.copilot
# ...
```

### Skill Implementation Architecture

#### Option A: Copilot Skills (Instructions-Based)

```markdown
# ~/.copilot/skills/swift-analyzer/SKILL.md

## Description
Analyze Swift codebases for CGM/AID patterns.

## Capabilities
- Parse Swift files for struct/class definitions
- Identify protocol conformances (e.g., CGMManager, PumpManager)
- Extract @Published properties for state management
- Find HealthKit integration points

## Usage Patterns
When asked to analyze Swift code:
1. Look for files matching *Manager.swift, *Plugin.swift
2. Extract public API surface
3. Identify delegation patterns
4. Map to terminology matrix
```

**Pros:** Zero code, just instructions
**Cons:** Relies on LLM understanding Swift

#### Option B: Hybrid Skills (Instructions + Tools)

```markdown
# SKILL.md
## Tools Available
```bash
# Run Swift syntax extraction
swift-demangle < symbols.txt
xcrun swift-symbolgraph-extract ...

# Parse Swift AST (requires swift-syntax)
python tools/swift_parser.py --file File.swift --json
```

**Pros:** Precise extraction, deterministic
**Cons:** Requires tooling per language

#### Option C: Language Server Integration

```bash
# Use LSP for precise analysis
sourcekit-lsp --request definition --file Loop.swift --offset 1234
```

**Pros:** IDE-level accuracy
**Cons:** Complex setup, per-language servers

### Recommended Skill Architecture

```
~/.copilot/skills/
├── nightscout-cgm/          # ✅ Already exists - live CGM data analysis
│   └── SKILL.md
│
├── ecosystem-alignment/     # NEW - Cross-project analysis
│   ├── SKILL.md            # Instructions for multi-faceted analysis
│   └── scripts/
│       └── faceted_analysis.py  # Tool for 5-facet updates
│
├── swift-patterns/          # NEW - Swift codebase patterns
│   └── SKILL.md            # How to analyze Loop/Trio/xDrip4iOS
│
├── kotlin-patterns/         # NEW - Kotlin/Java patterns  
│   └── SKILL.md            # How to analyze AAPS/xDrip
│
├── node-patterns/           # NEW - Node.js patterns
│   └── SKILL.md            # How to analyze cgm-remote-monitor
│
└── sdlc-matrix/            # NEW - SDLC orchestration
    ├── SKILL.md            # How to cycle through matrix
    └── templates/
        ├── requirements-phase.copilot
        ├── design-phase.copilot
        ├── implementation-phase.copilot
        ├── testing-phase.copilot
        └── documentation-phase.copilot
```

### SDLC Matrix Workflow Templates

#### `templates/requirements-phase.copilot`
```dockerfile
MODEL claude-sonnet-4.5
MODE read-only
MAX-CYCLES 1

# Context
@traceability/requirements.md
@mapping/{{PROJECT}}/README.md

# Analysis
PROMPT Analyze {{REPO_PATH}} for requirements.
  
  Look for:
  1. Code comments with MUST, SHALL, SHOULD
  2. Test file assertions (expected behaviors)
  3. Error handling (required validations)
  4. Protocol/interface definitions (contracts)
  
  Output format:
  - New REQ-NNN entries (check next available in requirements.md)
  - Links to source files
  - Verification criteria

PROMPT Update traceability/requirements.md with findings.
```

#### `templates/testing-phase.copilot`
```dockerfile
MODEL claude-sonnet-4.5
MODE read-only
MAX-CYCLES 1

# Context  
@traceability/requirements.md
@conformance/assertions/{{SCENARIO}}.yaml

# Analysis
PROMPT Analyze test coverage in {{REPO_PATH}}/tests/ or {{REPO_PATH}}/Tests/.

  For each requirement in scope:
  1. Find tests that verify it
  2. Identify untested requirements
  3. Check assertion completeness
  
  Output:
  - Coverage percentage
  - List of REQ-NNN with test status
  - Suggested new test scenarios
```

---

## Summary: What's Needed

### Keep (Current Stack)
- ✅ **Makefile** - Orchestration layer (familiar, parallel)
- ✅ **Python (stdlib)** - Tool implementation (portable, JSON-friendly)
- ✅ **JSON** - Data interchange format

### Add (Skills Layer)
| Skill | Purpose | Priority |
|-------|---------|----------|
| `ecosystem-alignment` | 5-facet analysis coordination | High |
| `swift-patterns` | Analyze 7 Swift repos | High |
| `kotlin-patterns` | Analyze 2 Android repos | Medium |
| `node-patterns` | Analyze 5 Node.js repos | Medium |
| `sdlc-matrix` | Phase-based workflow templates | Medium |

### Consider (Future Enhancements)
- **Language servers** for precise code analysis (when needed)
- **Node.js tooling** for cgm-remote-monitor-specific work
- **`pyproject.toml`** for optional dev dependencies

### The Key Insight

**The workspace is a documentation/coordination layer, not a code execution layer.**

The tools don't need to *run* the external projects - they need to:
1. **Read** code across languages (pattern matching, AST-lite)
2. **Track** relationships (requirements ↔ code ↔ tests)
3. **Generate** documentation (markdown, JSON)
4. **Validate** consistency (terminology, schemas)

For this purpose, **Python + Makefile is sufficient**. The heavy lifting is done by:
- AI agents (understanding code semantically)
- Skills (providing domain-specific patterns)
- Instructions (guiding consistent analysis)

---

**Document Version:** 1.0  
**Date:** 2026-01-20
