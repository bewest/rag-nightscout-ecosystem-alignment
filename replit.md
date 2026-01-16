# AID Alignment Workspace

A documentation workspace for coordinating semantics, schemas, and conformance across multiple Automated Insulin Delivery (AID) systems: Nightscout, Loop, AAPS, and Trio.

## Project Structure

```
workspace/
├── docs/                    # Narrative documentation
│   ├── 00-overview/         # Mission, goals
│   ├── 10-domain/           # Domain concepts, glossary
│   ├── 20-specs/            # Spec explanations
│   ├── 30-design/           # Design proposals
│   ├── 40-implementation-notes/
│   ├── 50-testing/
│   ├── 60-research/
│   ├── 90-decisions/        # ADRs (Architecture Decision Records)
│   ├── _includes/           # Shared snippets, code refs
│   └── _generated/          # Auto-generated files
├── specs/                   # Normative definitions
│   ├── openapi/             # OpenAPI specs
│   ├── jsonschema/          # JSON Schema definitions
│   └── fixtures/            # Test fixtures
├── conformance/             # Executable tests
│   ├── scenarios/           # Test scenarios
│   ├── assertions/          # Assertion definitions
│   └── runners/             # Test runners
├── mapping/                 # Per-project interpretation
│   ├── nightscout/
│   ├── aaps/
│   ├── trio/
│   └── loop/
├── traceability/            # Coordination control plane
│   ├── coverage-matrix.md   # Scenario vs project status
│   ├── gaps.md              # Blocking gaps
│   ├── requirements.md      # Derived requirements
│   └── glossary.md
├── tools/                   # Workspace utilities
│   ├── bootstrap.py         # Clone external repos
│   ├── linkcheck.py         # Verify code refs and links
│   └── gen_refs.py          # Generate permalink files
├── externals/               # Cloned repos (gitignored)
└── workspace.lock.json      # Repository pins
```

## Quick Start

1. **Bootstrap external repos**:
   ```bash
   python tools/bootstrap.py
   ```

2. **Check link validity**:
   ```bash
   python tools/linkcheck.py
   ```

3. **Generate reference files**:
   ```bash
   python tools/gen_refs.py
   ```

## Key Concepts

- **Normative** (specs/, conformance/assertions/): Must be true
- **Informative** (docs/, mapping/): Explanations and rationale
- **Decisions** (docs/90-decisions/): ADRs explaining tradeoffs

## Workflow

Each iteration cycle should update:
1. Scenario backlog
2. Requirements snippet
3. Spec delta (schema changes)
4. Mapping notes (per project)
5. Conformance update
6. Gap/coverage update

## Tools

- `bootstrap.py` - Clone and manage external repositories
- `linkcheck.py` - Verify code references resolve correctly
- `gen_refs.py` - Generate GitHub permalinks from lockfile

## Recent Changes

- 2024-01-15: Initial workspace setup with override-supersede scenario
