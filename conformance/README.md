# Conformance Testing Suite

This directory contains conformance tests for verifying algorithm behavior and data transformations across the Nightscout ecosystem.

## Directory Structure

```
conformance/
├── assertions/        # YAML assertion definitions
├── e2e-nightscout/    # End-to-end Nightscout tests
├── field-transforms/  # Field transformation tests
├── results/           # Generated test results (git-ignored)
├── runners/           # Algorithm-specific test runners
├── scenarios/         # Test scenario definitions
├── schemas/           # JSON schemas for validation
├── unit-conversions/  # Unit conversion test data
└── vectors/           # Algorithm test vectors
```

## Quick Start

### Run All Conformance Tests

```bash
# Run both assertion tests and algorithm conformance
make conformance-ci

# Or run separately:
make conformance             # Assertion-based tests (fast)
make conformance-algorithms  # Algorithm conformance (oref0, etc.)
```

### Run Specific Tests

```bash
# Assertions only
python tools/run_conformance.py

# Algorithm suite with specific runner
python tools/conformance_suite.py --runner oref0

# Generate report from existing results
python tools/conformance_suite.py --report-only
```

## Test Types

### 1. Assertion-Based Tests (`run_conformance.py`)

Tests data transformations and field mappings against scenario fixtures.

**Location**: `conformance/assertions/`, `conformance/scenarios/`

**Example**:
```yaml
# conformance/assertions/sync-deduplication.yaml
scenario: sync-deduplication
requirements:
  - REQ-SYNC-036
  - REQ-SYNC-037
assertions:
  - name: UUID v5 identifier generation
    type: field_present
    field: identifier
```

### 2. Algorithm Conformance (`conformance_suite.py`)

Validates algorithm implementations against shared test vectors.

**Runners**:
| Runner | Status | Vectors | Description |
|--------|--------|---------|-------------|
| oref0 | ✅ Available | 85 | JavaScript oref0 determine-basal |
| aaps | ❌ Not implemented | - | Kotlin AAPS algorithm |
| loop | ❌ Not implemented | - | Swift Loop algorithm |

**Location**: `conformance/runners/`, `conformance/vectors/`

## CI Integration

### GitHub Actions

The CI workflow runs conformance tests automatically:

```yaml
# .github/workflows/ci.yml
jobs:
  conformance:           # Fast assertion tests
  algorithm-conformance: # Full algorithm suite
```

### Local CI Mode

```bash
# Strict exit codes for CI
python tools/conformance_suite.py --ci
```

Exit codes:
- `0` - All tests pass
- `1` - Test failures (expected for known divergence)
- `2` - Configuration/runtime error

## Test Vectors

Algorithm test vectors are extracted from oref0 fixtures:

```
conformance/vectors/
├── oref0/
│   ├── basal-treatment/     # 85 determine-basal vectors
│   └── README.md
└── shared/
    └── profiles/            # Shared therapy profiles
```

### Vector Format

```json
{
  "name": "test-case-001",
  "input": {
    "iob": {...},
    "glucose": [...],
    "profile": {...}
  },
  "expected": {
    "rate": 0.5,
    "duration": 30,
    "reason": "..."
  }
}
```

## Adding New Tests

### Add Assertion Test

1. Create scenario in `conformance/scenarios/`
2. Add assertions in `conformance/assertions/`
3. Run: `python tools/run_conformance.py`

### Add Algorithm Runner

1. Create runner in `conformance/runners/`
2. Register in `tools/conformance_suite.py` RUNNERS dict
3. Add test vectors to `conformance/vectors/`

## Results

Results are written to `conformance/results/`:

```
conformance/results/
├── oref0-results.json      # Raw test results
├── conformance-report.md   # Human-readable summary
└── conformance-report.json # Machine-readable summary
```

### Viewing Results

```bash
# Generate/update report
python tools/conformance_suite.py --report-only

# View summary
cat conformance/results/conformance-report.md
```

## Known Issues

### oref0 Divergence

The oref0 runner shows ~69% divergence from expected outputs. This is documented in GAP-ALG-* entries and reflects:
- Different rounding approaches
- Prediction curve variations
- SMB enablement logic differences

See `conformance/results/oref0-results.json` for details.

## Related Documentation

- [Algorithm Conformance Proposal](../docs/sdqctl-proposals/algorithm-conformance-proposal.md)
- [oref0 Runner Documentation](runners/README.md)
- [Test Vector Extraction](../docs/10-domain/algorithm-conformance-deep-dive.md)
