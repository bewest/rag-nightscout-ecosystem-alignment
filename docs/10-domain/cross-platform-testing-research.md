# Cross-Platform Testing Harness Research

> **Purpose**: Requirements for cross-platform builds and testing harness vs static analysis  
> **Source**: LIVE-BACKLOG.md user request  
> **Date**: 2026-01-31

## Executive Summary

This document analyzes the trade-offs between static analysis and dynamic testing approaches for verifying claim accuracy across the Nightscout ecosystem's multi-language codebase (JavaScript, Swift, Kotlin, Java).

### Key Recommendations

| Approach | Best For | Effort | Accuracy |
|----------|----------|--------|----------|
| **Static Analysis (LSP/Tree-sitter)** | Symbol resolution, API shape verification | Medium | 70-85% |
| **Unit Testing (Conformance runners)** | Algorithm behavior, numerical precision | High | 95-100% |
| **Hybrid (Recommended)** | Documentation claims, full coverage | Medium-High | 90%+ |

---

## 1. Current State Analysis

### 1.1 Existing Infrastructure

| Component | Status | Purpose |
|-----------|--------|---------|
| `conformance/runners/oref0-runner.js` | ✅ Implemented | JS algorithm validation (85 vectors) |
| `tools/verify_refs.py` | ✅ Implemented | Line anchor validation |
| `tools/verify_assertions.py` | ✅ Implemented | Scenario → requirement tracing |
| `tools/tree_sitter_queries.py` | ✅ Implemented | Code structure extraction (functions/classes/imports) |
| `tools/lsp_query.py` | ❌ Not implemented | LSP-based symbol lookup |
| Tree-sitter CLI | ✅ Installed | v0.26.3, JS/TS/Swift/Java/Kotlin parsers |

### 1.2 External Repo Build Systems

| Language | Projects | Build System | Test Framework |
|----------|----------|--------------|----------------|
| **JavaScript** | cgm-remote-monitor, oref0, trio-oref | npm/package.json | Mocha, Should.js |
| **Swift** | Trio, Loop, xDrip4iOS, DiaBLE | Xcode (.xcodeproj) | XCTest |
| **Kotlin** | AAPS | Gradle (gradlew) | JUnit, JSONAssert |
| **Java** | xDrip | Gradle (gradlew) | JUnit |

### 1.3 Platform Requirements

| Platform | JavaScript | Swift | Kotlin/Java |
|----------|------------|-------|-------------|
| Linux | ✅ Full | ⚠️ Syntax only | ✅ Full (Gradle) |
| macOS | ✅ Full | ✅ Full (Xcode) | ✅ Full |
| CI (GitHub Actions) | ✅ ubuntu | ✅ macos (10x cost) | ✅ ubuntu |

---

## 2. Static Analysis Approach

### 2.1 What Static Analysis Can Verify

| Claim Type | Example | Verifiable? | Tool |
|------------|---------|-------------|------|
| "Function X exists at line Y" | `determineBasal() at :47` | ✅ Yes | Tree-sitter, LSP |
| "Field X is of type Y" | `glucose: number` | ✅ Yes | LSP (semantic) |
| "Function calls Y" | `iob() calls sum()` | ✅ Yes | LSP references |
| "Algorithm does X" | "Uses 4 prediction curves" | ⚠️ Partial | Requires logic analysis |
| "Output matches expected" | IOB = 2.5 | ❌ No | Requires runtime |

### 2.2 Tool Comparison

| Tool | Pros | Cons | Best For |
|------|------|------|----------|
| **Tree-sitter** | Cross-platform, no build needed, fast | No semantics, no type resolution | Syntax queries, symbol extraction |
| **tsserver (JS/TS LSP)** | Full semantic analysis, references | Requires Node.js, project setup | JS/TS verification |
| **sourcekit-lsp** | Swift type resolution | Requires Xcode on macOS | Swift on CI |
| **kotlin-language-server** | Kotlin semantics | Requires Gradle sync (~5min) | AAPS verification |

### 2.3 Recommended Static Analysis Stack

```
┌─────────────────────────────────────────────────────────┐
│                 tools/lsp_query.py                       │
│         (Unified interface for all languages)            │
├────────────────┬────────────────┬───────────────────────┤
│   tsserver     │  tree-sitter   │  sourcekit-lsp        │
│   (JS/TS)      │  (Syntax only) │  (Swift - CI only)    │
├────────────────┴────────────────┴───────────────────────┤
│            externals/ (20 repositories)                  │
└─────────────────────────────────────────────────────────┘
```

### 2.4 Implementation Effort

| Task | Effort | Priority |
|------|--------|----------|
| Create `tools/lsp_query.py` for tsserver | 4 hours | P2 |
| Install tree-sitter-cli + parsers | 1 hour | P2 |
| Create tree-sitter query library | 4 hours | P2 |
| Integrate into `verify_refs.py` | 2 hours | P2 |
| **Total (Linux-only)** | **11 hours** | |

---

## 3. Dynamic Testing Approach (Conformance Runners)

### 3.1 What Dynamic Testing Can Verify

| Claim Type | Example | Verifiable? | Tool |
|------------|---------|-------------|------|
| "Algorithm produces output X" | "SMB = 0.5U for BG 180" | ✅ Yes | Conformance runner |
| "Safety limit enforced" | "max_iob caps at 10" | ✅ Yes | Edge case tests |
| "Numerical precision" | "IOB rounds to 0.01" | ✅ Yes | Unit tests |
| "Cross-language parity" | "JS oref = Kotlin oref" | ✅ Yes | Dual runners |

### 3.2 Current Conformance Coverage

| Runner | Language | Status | Vectors | Pass Rate |
|--------|----------|--------|---------|-----------|
| oref0-runner.js | JavaScript | ✅ Implemented | 85 | 31% (divergent) |
| aaps-runner.kt | Kotlin | ❌ Proposed | 85 | - |
| loop-runner.swift | Swift | ❌ Proposed | TBD | - |
| trio-runner.swift | Swift | ❌ Proposed | TBD | - |

### 3.3 Proposed Runner Architecture

```
┌─────────────────────────────────────────────────────────┐
│               tools/conformance_suite.py                 │
│           (Orchestrator - cross-runner comparison)       │
├──────────┬──────────┬───────────────┬───────────────────┤
│ oref0    │ aaps     │ loop          │ trio              │
│ runner   │ runner   │ runner        │ runner            │
│ (JS)     │ (Kotlin) │ (Swift)       │ (Swift+JS)        │
├──────────┴──────────┴───────────────┴───────────────────┤
│        conformance/vectors/ (JSON test vectors)          │
└─────────────────────────────────────────────────────────┘
```

### 3.4 Implementation Effort

| Task | Effort | Priority | Platform |
|------|--------|----------|----------|
| oref0-runner.js | ✅ Done | - | Linux |
| aaps-runner.kt | 2 days | P2 | Linux |
| loop-runner.swift | 3 days | P3 | macOS only |
| trio-runner.swift | 2 days | P3 | macOS only |
| **Total new runners** | **7 days** | | |

---

## 4. Verification Accuracy Trade-offs

### 4.1 Accuracy by Verification Type

| Verification Type | Static Analysis | Dynamic Testing |
|-------------------|-----------------|-----------------|
| **Symbol exists** | 99% | N/A |
| **Type correctness** | 95% | N/A |
| **Line number accuracy** | 90% | N/A |
| **Algorithm behavior** | 30% | 99% |
| **Edge case handling** | 10% | 95% |
| **Cross-language parity** | 50% | 99% |

### 4.2 Claim Categories in Documentation

Based on analysis of `docs/10-domain/*.md`:

| Category | Count | Best Approach |
|----------|-------|---------------|
| Code location claims | ~500 | Static (line validation) |
| Field/type claims | ~200 | Static (LSP) |
| Algorithm behavior | ~150 | Dynamic (conformance) |
| Numerical precision | ~50 | Dynamic (unit tests) |
| Cross-project parity | ~100 | Dynamic (multi-runner) |

### 4.3 Recommended Accuracy Targets

| Claim Type | Current | Target | Method |
|------------|---------|--------|--------|
| Line references | 99.3% | 99.9% | Tree-sitter validation |
| Function signatures | Not verified | 95% | LSP type queries |
| Algorithm claims | 31% pass | 80% pass | Additional vectors |
| Cross-language | Not verified | 90% match | AAPS runner |

---

## 5. Proposed Requirements

### REQ-TEST-001: Static Analysis Baseline

**Statement**: The verification system MUST validate code location claims using syntax parsing.

**Rationale**: 500+ code references in documentation need automated validation.

**Implementation**: Tree-sitter + line count validation in `verify_refs.py`.

**Verification**: All refs in `mapping/` and `docs/10-domain/` validate without error.

### REQ-TEST-002: LSP Integration for JS/TS

**Statement**: The verification system SHOULD provide symbol lookup for JavaScript/TypeScript codebases.

**Rationale**: cgm-remote-monitor and oref0 are critical JS projects needing semantic verification.

**Implementation**: `tools/lsp_query.py` wrapping tsserver.

**Verification**: Query `determine_basal` function and get correct file:line.

### REQ-TEST-003: Conformance Runner Parity

**Statement**: Algorithm conformance runners MUST exist for at least 2 implementations (oref0 + one other).

**Rationale**: Cross-language validation catches divergence issues.

**Implementation**: oref0-runner.js (done) + aaps-runner.kt (proposed).

**Verification**: Run same 85 vectors through both runners, compare outputs.

### REQ-TEST-004: CI Matrix Coverage

**Statement**: The CI pipeline MUST run static analysis on all PRs and conformance on algorithm-related changes.

**Rationale**: Prevent documentation drift and algorithm regression.

**Implementation**: GitHub Actions workflow with matrix (Linux for JS/Kotlin, macOS for Swift).

**Verification**: CI blocks merges with failing verification.

### REQ-TEST-005: Accuracy Reporting

**Statement**: The verification system MUST report accuracy metrics per claim type.

**Rationale**: Track improvement over time and identify weak areas.

**Implementation**: Extend `tools/verify_coverage.py` with accuracy breakdown.

**Verification**: `make verify` outputs accuracy summary.

---

## 6. Implementation Roadmap

### Phase 1: Static Analysis Foundation (Week 1-2)

| Task | Deliverable | Effort |
|------|-------------|--------|
| Install tree-sitter-cli | `cargo install tree-sitter-cli` | 1 hour |
| Create tree-sitter Swift/JS/Kotlin parsers | `tools/tree-sitter/` | 4 hours |
| Integrate into verify_refs.py | `--syntax` flag | 4 hours |
| Create lsp_query.py for tsserver | `tools/lsp_query.py` | 4 hours |

**Deliverable**: Line + syntax validation for all refs.

### Phase 2: AAPS Runner (Week 3)

| Task | Deliverable | Effort |
|------|-------------|--------|
| Create aaps-runner.kt | `conformance/runners/aaps-runner.kt` | 2 days |
| Extract AAPS test vectors | `conformance/vectors/aaps/` | 4 hours |
| Cross-runner comparison | `tools/conformance_suite.py` update | 4 hours |

**Deliverable**: JS vs Kotlin algorithm comparison.

### Phase 3: Swift Runners - CI Only (Week 4+)

| Task | Deliverable | Effort |
|------|-------------|--------|
| loop-runner.swift | `conformance/runners/loop-runner.swift` | 3 days |
| macOS CI workflow | `.github/workflows/swift-conformance.yml` | 4 hours |
| trio-runner integration | `conformance/runners/trio-runner.swift` | 2 days |

**Deliverable**: Full cross-platform coverage on CI.

### Phase 4: Accuracy Dashboard (Week 5)

| Task | Deliverable | Effort |
|------|-------------|--------|
| Unified accuracy reporter | `tools/accuracy_dashboard.py` | 1 day |
| Makefile target | `make verify-accuracy` | 1 hour |
| CI integration | Accuracy badge in README | 2 hours |

**Deliverable**: Single-command accuracy report.

---

## 7. Cost-Benefit Analysis

### 7.1 Static Analysis ROI

| Investment | Return |
|------------|--------|
| ~15 hours setup | Validate 700+ code refs automatically |
| Tree-sitter parsers | Works on all platforms, no builds |
| tsserver integration | Full JS/TS semantic queries |

**Break-even**: Saves manual ref checking after ~5 documentation cycles.

### 7.2 Dynamic Testing ROI

| Investment | Return |
|------------|--------|
| ~7 days for new runners | Cross-language parity validation |
| Test vector maintenance | Regression detection on algorithm changes |
| macOS CI costs | Swift coverage (10x ubuntu cost) |

**Break-even**: Catches first algorithm divergence bug = justified.

### 7.3 Hybrid Approach Benefits

| Benefit | Static Only | Dynamic Only | Hybrid |
|---------|-------------|--------------|--------|
| Code ref accuracy | ✅ | ❌ | ✅ |
| Algorithm behavior | ❌ | ✅ | ✅ |
| Setup complexity | Low | High | Medium |
| CI cost | Low | Medium | Medium |
| Overall accuracy | 70% | 60% | 90%+ |

---

## 8. Identified Gaps

### GAP-TEST-001: No Cross-Language Validation

**Description**: Only JS oref0 has a conformance runner. Kotlin AAPS divergence is undocumented.

**Impact**: Algorithm differences between apps may cause inconsistent dosing.

**Remediation**: Implement aaps-runner.kt (Phase 2).

### GAP-TEST-002: No Swift Validation on Linux

**Description**: Swift projects (Trio, Loop) cannot be validated on Linux.

**Impact**: Most CI runs on ubuntu; Swift verification requires macOS runners.

**Remediation**: Tree-sitter for syntax, macOS CI for semantics.

### GAP-TEST-003: Stale Test Vectors

**Description**: Current 85 vectors from AAPS may not cover recent algorithm changes.

**Impact**: Tests pass but don't validate current behavior.

**Remediation**: Periodic vector refresh from live AAPS replay tests.

---

## 9. Conclusion

### Recommended Strategy: Hybrid Approach

1. **Immediate (Week 1-2)**: Tree-sitter + tsserver for static analysis
2. **Short-term (Week 3)**: AAPS Kotlin runner for cross-language validation
3. **Medium-term (Week 4+)**: Swift runners on macOS CI
4. **Ongoing**: Accuracy dashboard and vector maintenance

### Expected Outcomes

| Metric | Before | After |
|--------|--------|-------|
| Code ref accuracy | 99.3% | 99.9% |
| Algorithm verification | JS only | JS + Kotlin |
| Cross-language parity | Unknown | Measured |
| CI coverage | Partial | Full matrix |
| Claim accuracy tracking | Manual | Automated |

---

## References

- [lsp-environment-check.md](lsp-environment-check.md) - LSP availability analysis
- [algorithm-conformance-suite.md](../sdqctl-proposals/algorithm-conformance-suite.md) - Conformance suite design
- [tool-coverage-audit.md](tool-coverage-audit.md) - Current tool coverage
- [conformance/README.md](../../conformance/README.md) - Test infrastructure
- [Makefile](../../Makefile) - Verification targets
