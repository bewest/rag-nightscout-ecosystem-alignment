# Audit Verification Tooling Proposal

> **Purpose**: Define tooling to verify claims and complete audits within sdqctl workflows  
> **Priority**: P1  
> **Effort**: Medium  
> **Created**: 2026-01-29  
> **Status**: Proposal

## Executive Summary

This proposal consolidates lessons learned from recent audit work and proposes new tooling to automate verification of documentation claims, traceability completeness, and conformance testing.

### Key Findings from Recent Work

| Finding | Impact | Proposed Solution |
|---------|--------|-------------------|
| 23 orphaned assertions | 0% requirement coverage | Assertion-REQ linkage validator |
| 28 connector gaps, 0 requirements | Gaps can't be verified | REQ generator from gaps |
| 69% oref0 divergence discovered manually | Algorithm drift invisible | CI conformance runs |
| 8% broken refs (31/386) | Stale documentation | Automated ref refresh |
| Line anchors validated at 99.3% | Line validation works | Extend to all refs |

---

## Proposed Tool Suite

### 1. Traceability Completeness Validator (`tools/verify_traceability.py`)

**Purpose**: Ensure gaps have requirements, requirements have tests, tests have results.

**Checks**:
```python
CHECKS = [
    ("gaps_have_requirements", "Every GAP-* should have REQ-* references"),
    ("requirements_have_scenarios", "Every REQ-* should have ≥1 scenario"),
    ("assertions_have_links", "Every assertion should link to REQ or GAP"),
    ("orphan_threshold", "Orphaned items below threshold"),
]
```

**Output**:
```
Traceability Completeness Report
================================
GAP→REQ Coverage: 72% (164/228 gaps have requirements)
REQ→Scenario Coverage: 85% (107/126 reqs have scenarios)  
Assertion Coverage: 29% (7/24 linked)

Domains with gaps:
- connectors: 28 gaps, 0 requirements ⚠️
- cgm-sources: 49 gaps, 18 requirements (37%)

Orphaned assertions: 23
- syncidentifier-preserved → no REQ
- identifier-preserved → no REQ
...
```

**CLI**:
```bash
python tools/verify_traceability.py --json
python tools/verify_traceability.py --domain connectors
python tools/verify_traceability.py --threshold 80  # fail if <80% coverage
```

---

### 2. Gap-to-Requirement Generator (`tools/gen_requirements.py`)

**Purpose**: Semi-automated REQ generation from GAP entries.

**Input**: `traceability/*-gaps.md` files

**Process**:
1. Parse GAP-* entries (description, impact, solutions)
2. Generate REQ-* stubs with:
   - Statement derived from "Possible Solutions"
   - Rationale from "Impact"
   - Suggested verification scenarios
3. Output to `traceability/*-requirements.md`

**Example**:
```bash
# Generate requirements for connector gaps
python tools/gen_requirements.py --domain connectors --output traceability/connectors-requirements.md

# Preview without writing
python tools/gen_requirements.py --domain connectors --dry-run
```

**Generated Template**:
```markdown
### REQ-CONNECT-001: [Title from GAP]

**Statement**: The system MUST/SHOULD [derived from solution].

**Rationale**: [From GAP impact]

**Scenarios**:
- [ ] Scenario 1: [suggested]
- [ ] Scenario 2: [suggested]

**Verification**: [suggested approach]

**Gap Reference**: GAP-CONNECT-001
```

---

### 3. Assertion Linker (`tools/link_assertions.py`)

**Purpose**: Link orphaned assertions to requirements/gaps.

**Input**: `conformance/assertions/*.yaml`, `traceability/*-requirements.md`

**Process**:
1. Find orphaned assertions (no `requirements:` or `gaps:`)
2. Suggest links based on:
   - Name similarity (e.g., `syncidentifier-preserved` → REQ matching "sync" + "identifier")
   - Domain matching (sync-deduplication → sync-identity domain)
3. Interactive or batch mode

**CLI**:
```bash
# Show suggestions
python tools/link_assertions.py --suggest

# Interactive linking
python tools/link_assertions.py --interactive

# Batch apply suggestions with confidence > 0.8
python tools/link_assertions.py --apply --threshold 0.8
```

---

### 4. Conformance CI Runner (`tools/run_conformance_ci.py`)

**Purpose**: Execute conformance suite with CI-friendly output.

**Features**:
- Run all algorithm conformance tests
- Generate JUnit XML for CI systems
- Slack/webhook notification on regression
- Badge generation for README

**CLI**:
```bash
# Full run with JUnit output
python tools/run_conformance_ci.py --junit conformance/results/junit.xml

# Compare against baseline
python tools/run_conformance_ci.py --baseline conformance/results/baseline.json

# Notify on regression
python tools/run_conformance_ci.py --webhook $SLACK_WEBHOOK
```

**GitHub Actions Integration**:
```yaml
# .github/workflows/conformance.yml
name: Algorithm Conformance
on:
  schedule:
    - cron: '0 6 * * *'  # Daily at 6 AM
  push:
    paths: ['conformance/**', 'externals/oref0/**']

jobs:
  conformance:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          submodules: recursive
      - uses: actions/setup-node@v4
      - run: make conformance-ci
      - uses: mikepenz/action-junit-report@v4
        with:
          report_paths: conformance/results/junit.xml
```

---

### 5. Reference Staleness Detector (`tools/detect_stale_refs.py`)

**Purpose**: Find refs likely to be stale based on file modification.

**Logic**:
1. For each code reference in docs:
2. Get last modified date of referenced file
3. Get last modified date of referencing doc
4. If code newer than doc by >30 days → flag as potentially stale

**Output**:
```
Potentially Stale References
============================
docs/10-domain/loop-deep-dive.md:45
  → externals/LoopWorkspace/.../Algorithm.swift#L123
  Code modified: 2026-01-15
  Doc modified: 2025-12-01
  Days stale: 45

docs/10-domain/aaps-divergence.md:89
  → externals/AndroidAPS/.../SMBPlugin.kt#L200
  Code modified: 2026-01-20
  Doc modified: 2026-01-10
  Days stale: 10
```

---

### 6. sdqctl Plugin: ecosystem-audit

**Purpose**: Bundle all verification into single sdqctl command.

**Registration**:
```yaml
# .sdqctl/directives.yaml
plugins:
  ecosystem-audit:
    description: Run comprehensive ecosystem audit
    commands:
      - refs: python tools/verify_refs.py --json
      - traceability: python tools/verify_traceability.py --json
      - assertions: python tools/verify_assertions.py --json
      - conformance: python tools/conformance_suite.py --report-only
    aggregate: true
```

**Usage**:
```bash
sdqctl verify plugin ecosystem-audit
```

**Output**:
```
Ecosystem Audit Report
======================

## References
- Total: 386
- Valid: 355 (92%)
- Broken: 31 (8%)

## Traceability
- GAP→REQ: 72%
- REQ→Scenario: 85%
- Assertion coverage: 29%

## Conformance
- oref0: 26/85 (31%)
- aaps: pending
- loop: pending

## Recommendations
1. [P1] Link 23 orphaned assertions
2. [P1] Generate connectors requirements (28 gaps)
3. [P2] Fix 31 broken references
```

---

## Implementation Priority

| Tool | Priority | Effort | Dependencies |
|------|----------|--------|--------------|
| verify_traceability.py | P1 | Medium | None |
| link_assertions.py | P1 | Low | verify_traceability.py |
| gen_requirements.py | P2 | Medium | Gap file parsing |
| run_conformance_ci.py | P2 | Low | conformance_suite.py exists |
| detect_stale_refs.py | P3 | Low | verify_refs.py exists |
| ecosystem-audit plugin | P3 | Low | All above tools |

---

## Integration with VERIFICATION-DIRECTIVES.md

This proposal complements the existing VERIFICATION-DIRECTIVES.md proposal:

| VERIFICATION-DIRECTIVES | This Proposal |
|------------------------|---------------|
| `VERIFY refs` built-in | ✅ verify_refs.py exists |
| `VERIFY traceability` | ➕ verify_traceability.py |
| `VERIFY assertions` | ➕ link_assertions.py |
| CLI commands | ➕ Additional ecosystem-specific |
| CI integration | ➕ run_conformance_ci.py |

Recommend merging as Phase 5 of VERIFICATION-DIRECTIVES.md.

---

## Success Criteria

| Metric | Current | Target |
|--------|---------|--------|
| Assertion coverage | 0% | 80% |
| GAP→REQ coverage | ~70% | 90% |
| Broken refs | 8% | <2% |
| Conformance visibility | Manual | CI dashboard |

---

## Next Steps

1. Implement verify_traceability.py (P1)
2. Run traceability audit to establish baseline
3. Implement link_assertions.py to resolve orphans
4. Set up conformance CI workflow
5. Generate missing connector requirements
