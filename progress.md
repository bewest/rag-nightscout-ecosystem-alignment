# AID Alignment Workspace - Progress Tracker

This document tracks completed documentation cycles and candidates for future work.

> **Archive**: Older entries moved to:
> - [progress-archive-2026-01-30-batch1.md](docs/archive/progress-archive-2026-01-30-batch1.md)
> - [progress-archive-2026-01-30-batch2.md](docs/archive/progress-archive-2026-01-30-batch2.md)
> - [progress-archive-2026-01-30-batch3.md](docs/archive/progress-archive-2026-01-30-batch3.md)
> - [progress-archive-2026-01-30-batch4.md](docs/archive/progress-archive-2026-01-30-batch4.md)

---

## Completed Work

### Tree-sitter Query Library (2026-01-31)

Created Python wrapper for tree-sitter code extraction across 4 languages.

**Deliverable**: `tools/tree_sitter_queries.py` (~300 lines)

| Command | Purpose | Languages |
|---------|---------|-----------|
| `functions` | Extract function/method declarations | JS, Swift, Kotlin, Java |
| `classes` | Extract class/struct/enum definitions | All |
| `imports` | Extract import statements | All |
| `all` | Combined extraction | All |
| `languages` | List supported extensions | - |

**Usage**:
```bash
python3 tools/tree_sitter_queries.py functions <file>
python3 tools/tree_sitter_queries.py --json all <file>
```

**Tested on**:
- `externals/oref0/lib/determine-basal/determine-basal.js` (8 functions)
- `externals/Trio-dev/.../DynamicISF.swift` (3 structs/enums)
- `externals/AndroidAPS/.../DetermineBasalAMA.kt` (12 functions)
- `externals/xDrip/.../CompareCgms.java` (23 methods)

---

### Tree-sitter Installation (2026-01-31)

Installed tree-sitter-cli and language parsers for static syntax analysis.

**Installation**: `npm install -g tree-sitter-cli` (v0.26.3)

| Language | Status | File Types |
|----------|--------|------------|
| JavaScript | ✅ Auto | `.js`, `.mjs`, `.cjs`, `.jsx` |
| TypeScript | ✅ Auto | `.ts`, `.tsx` |
| Swift | ✅ Auto | `.swift` |
| Java | ✅ Auto | `.java` |
| Kotlin | ⚠️ Manual | `.kt` (requires `-l <path>/kotlin.so`) |

**Parsers Location**: `/tmp/tree-sitter-grammars/node_modules/`

**Usage**:
```bash
tree-sitter parse <file>                    # Auto-detect language
tree-sitter parse -l kotlin.so <file.kt>    # Kotlin workaround
tree-sitter dump-languages                  # List available parsers
```

**Unblocks**: tooling.md #26 (query library), #24 (lsp_query.py)

---

### Cross-Platform Testing Harness Research (2026-01-31)

Research and requirements for cross-platform builds and testing harness vs static analysis.

**Deliverable**: `docs/10-domain/cross-platform-testing-research.md` (13KB)

| Approach | Best For | Accuracy |
|----------|----------|----------|
| Static Analysis (LSP/Tree-sitter) | Symbol resolution, API shape | 70-85% |
| Unit Testing (Conformance runners) | Algorithm behavior, precision | 95-100% |
| **Hybrid (Recommended)** | Full coverage | 90%+ |

**Key Findings**:
- Existing: oref0-runner.js (85 vectors, 31% pass)
- Needed: aaps-runner.kt for cross-language validation
- Swift runners require macOS CI (10x cost)
- Tree-sitter works cross-platform without builds

**Requirements Proposed**:
- REQ-TEST-001: Static analysis baseline (tree-sitter)
- REQ-TEST-002: LSP integration for JS/TS
- REQ-TEST-003: Conformance runner parity (2+ languages)
- REQ-TEST-004: CI matrix coverage
- REQ-TEST-005: Accuracy reporting

**Gaps Identified**:
- GAP-TEST-001: No cross-language validation
- GAP-TEST-002: No Swift validation on Linux
- GAP-TEST-003: Stale test vectors

**Roadmap**: 4 phases over 5 weeks (static analysis → AAPS runner → Swift runners → dashboard)

---

### LSP Environment Suitability Check (2026-01-31)

Comprehensive probe of LSP tooling availability for code verification.

**Deliverable**: `docs/10-domain/lsp-environment-check.md` (7KB)

| Tool | Status | Notes |
|------|--------|-------|
| Swift/sourcekit-lsp | ✅ Installed | swiftly 6.2.3, needs PATH source |
| Node.js/tsserver | ✅ Ready | v20.20.0, fully operational |
| Java | ✅ OpenJDK 21 | kotlin-language-server not installed |
| Python/pyright | ⚠️ Partial | Python 3.12, pyright not installed |
| Tree-sitter | ✅ Installed | v0.26.3 via npm, 5 languages working |

**Key Findings**:
- JS/TS verification ready immediately via tsserver
- Swift 6.2.3 installed but iOS projects need Xcode for full resolution
- Tree-sitter recommended as hybrid approach for syntax queries
- 6 actionable items queued to tooling.md

**Recommendation**: Hybrid LSP + tree-sitter approach

---

### Trio Comprehensive Analysis (2026-01-31)

Complete analysis of Trio's oref integration, Nightscout sync patterns, and APSManager architecture comparison with Loop.

**Deliverable**: `docs/10-domain/trio-comprehensive-analysis.md` (20KB)

| Component | Key Findings |
|-----------|--------------|
| **oref Integration** | Embedded JavaScriptCore, trio-oref/lib/ bundles, SMB scheduling customizations |
| **OpenAPSSwift Port** | Native Swift implementation with DynamicISF (log+sigmoid), dual validation architecture |
| **Nightscout Sync** | 7 upload pipelines, 2-second throttle, API v1 only |
| **APSManager vs Loop** | JS bridge vs native Swift, 4 vs 1 prediction curves, CoreData vs HealthKit |

**Gaps Identified**:
- GAP-TRIO-SYNC-001: API v1 Only
- GAP-TRIO-SYNC-002: Limited Deduplication
- GAP-TRIO-SYNC-003: No Offline Queue
- GAP-TRIO-OREF-001: oref Bundle Version Tracking
- GAP-TRIO-SWIFT-001: JS vs Swift Parity Validation
- GAP-TRIO-SWIFT-002: Sigmoid Formula Edge Cases

**Requirements Added**:
- REQ-TRIO-001: SMB Scheduling Support
- REQ-TRIO-002: Multi-AID Deduplication
- REQ-TRIO-003: Upload Throttling

**5 Facets Updated**:
1. ✅ Deep-dive: `trio-comprehensive-analysis.md`
2. ✅ Gaps: 6 new gaps in sync-identity-gaps.md + aid-algorithms-gaps.md
3. ✅ Requirements: 3 new REQ-TRIO-* in sync-identity-requirements.md
4. ✅ Terminology: Upload pipeline terms + manager comparison
5. ✅ Progress: This entry

**Source Files Analyzed (Trio-dev)**:
- `externals/Trio-dev/Trio/Sources/APS/APSManager.swift` (~1345 lines)
- `externals/Trio-dev/Trio/Sources/APS/OpenAPSSwift/` (OpenAPSSwift.swift, DynamicISF.swift, DetermineBasalGenerator.swift)
- `externals/Trio-dev/Trio/Sources/Services/Network/Nightscout/NightscoutManager.swift` (~1200 lines)
- `externals/Trio-dev/trio-oref/lib/` (determine-basal.js, iob/, meal/, profile/)
- `externals/LoopWorkspace/Loop/Loop/Managers/LoopDataManager.swift` (~2600 lines)

---

### sdqctl iterate Effectiveness Report #3 (2026-01-30)

Comprehensive analysis of 20-cycle backlog-cycle-v2 session.

**Deliverable**: `docs/10-domain/sdqctl-iterate-effectiveness-report-3.md` (10.5KB)

| Metric | Value |
|--------|-------|
| Runtime | 102 min 52 sec |
| Cycles | 20 (cycles 19-38) |
| Tool Success | 99.8% (818 calls) |
| Tokens | ~71M in / ~251K out |
| Deep-dives | 99 |
| Gaps | 294 |
| Requirements | 260 |

**Key Findings**:
- backlog-cycle-v2 6-phase structure highly effective
- Mandatory commits eliminated accumulated work problem
- LIVE-BACKLOG dual-queue system processed 213 items
- Token efficiency: 0.35% output/input ratio

**v3 Recommendations**:
- V3-01: Context budget check phase
- V3-02: Auto-archive at 200 lines
- V3-03: Auto-promote Ready Queue
- V3-04: Error telemetry logging
- V3-05: REFCAT caching integration

---

### sdqctl Workflow Integration (2026-01-30)

Cycle 38: Standardized sdqctl usage across workflows and Makefile.

**Deliverable**: `docs/10-domain/sdqctl-workflow-integration.md` (5KB)

**New Makefile Targets**:
| Target | Purpose |
|--------|---------|
| `make sdqctl-cycle` | Single backlog cycle |
| `make sdqctl-cycle-multi N=5` | Multi-cycle execution |
| `make sdqctl-verify-parallel` | Parallel verification |

**Patterns Documented**:
- `sdqctl run` - Single workflow
- `sdqctl iterate -n N` - Multi-cycle
- `sdqctl flow --parallel` - Batch execution
- `--json-errors` - CI integration

**tooling.md #15**: ✅ COMPLETE

---

### Trio OpenAPS.swift Bridge Analysis (2026-01-30)

Cycle 37: Analyzed Swift↔JS bridge in Trio for algorithm execution.

**Deliverable**: `docs/10-domain/trio-openaps-bridge-analysis.md` (9.7KB)

**Architecture**:
```
Swift (OpenAPS.swift) → JavaScriptWorker → JSContext Pool (5) → oref bundles
```

**Bridge Functions**:
| Function | JS Bundle | Purpose |
|----------|-----------|---------|
| iob() | iob.js | Insulin on board |
| meal() | meal.js | Carb absorption |
| autosense() | autosens.js | Sensitivity ratio |
| determineBasal() | determine-basal.js | Main algorithm |

**Gaps Identified**:
- GAP-TRIO-BRIDGE-001: No type safety across bridge
- GAP-TRIO-BRIDGE-002: Synchronous JS execution
- GAP-TRIO-BRIDGE-003: Middleware security

**Key Insights**: Embedded JavaScriptCore, 5-context pool, middleware extensibility

**aid-algorithms.md #7**: ✅ COMPLETE

---

### Housekeeping + Queue Replenishment (2026-01-30)

Cycle 36: Pushed commits, archived progress.md, replenished Ready Queue.

| Task | Before | After |
|------|--------|-------|
| Commits unpushed | 4 | 0 |
| progress.md lines | 314 | 193 |
| Ready Queue items | 1 actionable | 5 actionable |

**New Ready Queue Items**:
1. Idiomatic sdqctl workflow integration (existing)
2. Trio-dev oref integration mapping (NEW)
3. Trio Nightscout sync analysis (NEW)
4. Trio OpenAPS.swift bridge analysis (NEW)
5. backlog-cycle-v3.conv (NEW)

**Archive**: `docs/archive/progress-archive-2026-01-30-batch4.md`

---

### Nightscout PR Coherence Review Protocol (2026-01-30)

Cycle 35: Created systematic PR review methodology.

**Deliverable**: `docs/10-domain/nightscout-pr-review-protocol.md` (8.8KB)

**6-Step Review Process**:
1. PR Identification (metadata, files changed)
2. Gap Alignment Search (GAP-* cross-reference)
3. Requirement Alignment Search (REQ-* cross-reference)
4. Proposal Alignment Check (sdqctl-proposals/)
5. Ecosystem Impact Assessment (Loop, AAPS, Trio, xDrip+)
6. Generate Recommendation (verdict, priority, dependencies)

**Key Features**:
- Quick reference checklist
- Detailed step-by-step process
- PR review output template
- Two worked examples (PR #8405, #8421)
- Integration with workspace tools

**tooling.md #17**: ✅ COMPLETE

---

### LSP Verification Setup Research (2026-01-30)

Cycle 34: Documented LSP requirements for claim verification.

**Deliverable**: `docs/10-domain/lsp-verification-setup-requirements.md` (10KB)

**Language Coverage**:
| Language | LSP Server | Linux | Effort | Priority |
|----------|------------|-------|--------|----------|
| JS/TS | tsserver | ✅ Ready | Low | P1 |
| Kotlin | kotlin-language-server | ✅ Feasible | Medium | P2 |
| Java | Eclipse JDT LS | ✅ Feasible | Medium | P2 |
| Python | pyright | ✅ Ready | Low | P3 |
| Swift | sourcekit-lsp | ⚠️ Limited | High | P4 |

**Key Finding**: Swift LSP requires macOS for iOS projects (no UIKit/HealthKit on Linux).

**Phased Roadmap**:
- Phase 1: JS/TS (1 day) - covers Nightscout
- Phase 2: Kotlin/Java (2-3 days) - covers AAPS/xDrip
- Phase 3: Python (2 hours) - covers tools/
- Phase 4: Swift (deferred) - requires macOS CI

**tooling.md #16**: ✅ COMPLETE

---

### Known vs Unknown Dashboard (2026-01-30)

Cycle 33: Created project health summary tool.

**Deliverable**: `tools/known_unknown_dashboard.py`

**Metrics Generated**:
| Metric | Value | Status |
|--------|-------|--------|
| Repos Cloned | 22/22 | ✅ |
| Mapping Projects | 23 | ✅ |
| Total Gaps | 294 | ✅ |
| Total Requirements | 260 | ✅ |
| Deep Dives | 32 | ✅ |
| OpenAPI Specs | 8 | ✅ |
| Coverage | 105% | ✅ |
| **Confidence** | **HIGH** (101%) | ✅ |

**Features**:
- `--json` for machine-readable output
- `--markdown` for human-readable format
- Gap/requirement breakdown by category
- Mapping coverage per project

**tooling.md #20**: ✅ COMPLETE

---

### Housekeeping + Ready Queue Replenishment (2026-01-30)

Cycle 32: Pushed commits, archived progress.md, replenished Ready Queue.

| Task | Before | After |
|------|--------|-------|
| Commits unpushed | 16 | 0 |
| progress.md lines | 291 | 214 |
| Ready Queue items | 2 (PARKED) | 6 (4 actionable, 2 PARKED) |

**New Ready Queue Items**:
1. Idiomatic sdqctl workflow integration (P2, Medium)
2. LSP verification setup research (P2, High)
3. Nightscout PR coherence review protocol (P2, Medium)
4. Known vs unknown dashboard (P2, Low)

**Archive**: `docs/archive/progress-archive-2026-01-30-batch3.md`

---

### PR Recommendation Packaging (2026-01-30)

Cycle 31: Created maintainer-focused recommendations document.

**Deliverable**: `docs/10-domain/nightscout-maintainer-recommendations.md`

**Priority Areas**:
1. Quick Win PRs (6 PRs ready to merge)
2. Sync & Identity (22 gaps, profile sync priority)
3. API Completeness (food/activity specs needed)
4. Controller Output (unified schema RFC)

**Roadmap**: Feb→Apr 2026 phased implementation

**nightscout-api.md #19**: ✅ COMPLETE

---

### cgm-remote-monitor Analysis Depth Matrix (2026-01-30)

Cycle 30: Created completeness grid for all Nightscout API collections.

**Deliverable**: `docs/10-domain/cgm-remote-monitor-analysis-depth-matrix.md`

**Coverage Summary**:
| Collection | Coverage | Status |
|------------|----------|--------|
| treatments | 100% | ✅ Fully covered |
| profile | 83% | ✅ Fully covered |
| devicestatus | 75% | ⚠️ Partial |
| entries | 67% | ⚠️ Partial |
| food | 8% | ❌ Not covered |
| activity | 8% | ❌ Not covered |

**Average Coverage**: 57%

**nightscout-api.md #18**: ✅ COMPLETE

---

### GAP-SYNC Ontology Classification (2026-01-30)

Cycle 29: Classified all 22 GAP-SYNC-* entries by Observed/Desired/Control ontology.

**Deliverable**: `traceability/sync-identity-gaps.md` - added classification table + individual tags

**Distribution**:
| Category | Count | Examples |
|----------|-------|----------|
| Observed | 6 | Treatment sync, deduplication |
| Desired | 8 | Profile, overrides, user intent |
| Control | 2 | Algorithm output, multi-controller |
| Cross-category | 6 | API/identity infrastructure |

**sync-identity.md #22**: ✅ COMPLETE

---

### State Ontology Definition (2026-01-30)

Cycle 28: Created foundational architecture document defining Observed/Desired/Control state categories.

**Deliverable**: `docs/architecture/state-ontology.md`

**Categories Defined**:
| Category | Definition | Sync Pattern |
|----------|------------|--------------|
| Observed | What happened (SGV, bolus) | Push, immutable |
| Desired | What user wants (profile, targets) | Bidirectional, mutable |
| Control | What algorithm decides (temps, SMBs) | Push, read-only |

**Collection Mapping**: entries (100% observed), profile (100% desired), treatments (mixed), devicestatus (mixed).

**Unblocks**: #1 Classify GAP-SYNC-* by ontology category

**Archived** to `progress-archive-2026-01-30-batch4.md`

---

