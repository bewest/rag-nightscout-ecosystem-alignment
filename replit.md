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
│   ├── nightscout/          # Nightscout schema/API mappings
│   ├── cross-project/       # Cross-project comparison matrices
│   ├── aaps/
│   ├── trio/
│   └── loop/
├── traceability/            # Coordination control plane
│   ├── coverage-matrix.md   # Scenario vs project status
│   ├── gaps.md              # Blocking gaps
│   ├── requirements.md      # Derived requirements
│   └── glossary.md
├── specs/
│   └── shape/               # Lightweight shape specs (stdlib validation)
├── tools/                   # Workspace utilities
│   ├── bootstrap.py         # Clone external repos
│   ├── linkcheck.py         # Verify code refs and links
│   ├── gen_refs.py          # Generate permalink files
│   ├── validate_fixtures.py # Validate fixtures against shape specs
│   ├── run_conformance.py   # Run conformance assertions (offline)
│   └── gen_coverage.py      # Generate coverage matrix
├── externals/               # Cloned repos (gitignored)
└── workspace.lock.json      # Repository pins
```

## Quick Start

1. **Bootstrap external repos**:
   ```bash
   make bootstrap
   ```

2. **Run all checks**:
   ```bash
   make check
   ```

3. **Full CI pipeline locally**:
   ```bash
   make ci
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

### Repository Management
- `bootstrap.py` - Clone and manage external repositories
- `linkcheck.py` - Verify code references resolve correctly
- `gen_refs.py` - Generate GitHub permalinks from lockfile

### Validation & Testing
- `validate_fixtures.py` - Validate JSON fixtures against shape specifications
  - Stdlib-only by default, optional `jsonschema` dependency for full validation
  - `--strict` flag to fail on unknown keys
- `run_conformance.py` - Run conformance assertions
  - Checks state, reference, immutability, and query assertions
  - `--scenario NAME` to run specific scenario
  - `--verbose` to show all results including passes
- `gen_coverage.py` - Generate coverage matrix from filesystem state
  - Outputs both JSON and Markdown formats
  - Tracks scenario completeness across all projects

### Makefile Targets
- `make validate` - Validate fixtures
- `make conformance` - Run conformance tests
- `make coverage` - Generate coverage matrix
- `make check` - Run all checks (linkcheck + validate + conformance)
- `make ci` - Full CI pipeline locally

## CI Integration

GitHub Actions workflow (`.github/workflows/ci.yml`) runs:
1. Python syntax check
2. Link integrity validation
3. Fixture validation
4. Conformance tests (offline)
5. Coverage matrix generation

## Recent Changes

- 2026-01-16: Added Nightscout documentation integration (domain models, mappings, cross-project terminology matrix)
- 2026-01-16: Created external repository inventories (cgm-remote-monitor, nightscout-roles-gateway, nightscout-connect)
- 2026-01-16: Expanded gaps documentation with authentication and sync identity issues
- 2026-01-16: Added tooling suite (validate_fixtures, run_conformance, gen_coverage, CI workflow)
- 2024-01-15: Initial workspace setup with override-supersede scenario

## Key Documentation

### Domain Documentation (docs/10-domain/)
- `nightscout-data-model.md` - Core Nightscout data model (entries, treatments, profiles, devicestatus)
- `authority-model.md` - Actor identity and authority hierarchy model
- `glossary.md` - Terminology definitions with cross-project mappings

### Mapping Documentation (mapping/)
- `nightscout/data-collections.md` - Field-level mappings for all Nightscout collections
- `nightscout/authorization.md` - Authentication and permission model mapping
- `nightscout/override-supersede.md` - Override behavior and supersession tracking
- `cross-project/terminology-matrix.md` - Rosetta stone for AID system terminology

### Gap Tracking (traceability/gaps.md)
- GAP-001: Override supersession tracking
- GAP-002: AAPS ProfileSwitch semantic mismatch
- GAP-003: Unified sync identity field
- GAP-AUTH-001: Unverified enteredBy field
- GAP-AUTH-002: No authority hierarchy
