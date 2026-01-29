# AID Alignment Workspace - Progress Tracker

This document tracks completed documentation cycles and candidates for future work.

> **Archive**: Entries before 2026-01-28 moved to [progress-archive-2026-01-17-to-23.md](docs/archive/progress-archive-2026-01-17-to-23.md)

---

## Completed Work

### Ecosystem Open PR Analysis (2026-01-29)

Analyzed open PRs across 6 key repositories for interoperability impact.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **PR Analysis** | `docs/analysis/ecosystem-pr-analysis-2026-01-29.md` | 180 lines |

| Repository | Open PRs | Interop-Relevant | Stale (>6mo) |
|------------|----------|------------------|--------------|
| cgm-remote-monitor | 10 | 4 | 2 |
| Trio | 7 | 3 | 1 |
| AndroidAPS | 10 | 3 | 0 |
| LoopWorkspace | 4 | 2 | 2 |
| oref0 | 10 | 3 | 10 |
| xDrip | 10 | 4 | 3 |

**Key Findings**:
- 51 open PRs across ecosystem, 19 interoperability-relevant
- oref0 in maintenance mode (all 10 PRs stale >6 months)
- Active development in pump drivers (Loop #402, AAPS #4513)
- Timezone fix PR #8405 confirms GAP-TZ-xxx

---

### LSP Integration Proposal (2026-01-29)

Defined 4-phase plan for Language Server Protocol integration.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Proposal** | `docs/sdqctl-proposals/lsp-integration-proposal.md` | 358 lines |

**Phases**:
1. Line validation (no LSP, 2 hours)
2. Symbol existence (LSP queries, 1-2 days)
3. Cross-reference analysis (1 week+)
4. Continuous monitoring (ongoing)

**Platform Constraints**: Swift LSP requires macOS for iOS projects.

---

### Broken References Fix (2026-01-29)

Fixed broken code references in active documentation files.

| Metric | Before | After |
|--------|--------|-------|
| Valid refs | 352 (91.2%) | 355 (92.0%) |
| Broken refs | 34 | 31 |

**Fixed**:
- `trio:Preferences.swift` → full path (2 files)
- `aaps:NSClientV3Service.kt` → correct `/services/` path (1 file)

**Remaining**: 31 broken (archive files, intentional examples)

---

### sdqctl vs Custom Python Tools Comparison (2026-01-29)

Analyzed 32 Python tools against sdqctl capabilities.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Proposal** | `docs/sdqctl-proposals/tools-comparison-proposal.md` | 140 lines |

**Key Findings**:
- 4 tools to deprecate (workflow orchestration → use sdqctl)
- 3 tools to integrate as sdqctl plugins (hygiene tools)
- 2 tools to evaluate further (ai_advisor, workspace_cli)
- 23 tools to keep (domain-specific)

---

### Hygiene Tooling Suite Verification (2026-01-29)

Verified all three hygiene tools are implemented and working.

| Tool | Lines | Status |
|------|-------|--------|
| `tools/queue_stats.py` | - | ✅ One-line status output |
| `tools/backlog_hygiene.py` | 413 | ✅ Queue validation |
| `tools/doc_chunker.py` | 1164 | ✅ Size checking |

**Design Doc**: `docs/sdqctl-proposals/hygiene-tooling-design.md` (466 lines)

**Finding**: progress.md needs chunking (1060 lines, 2.1x over threshold)

---

### nightscout-roles-gateway Audit (2026-01-29)

Verified comprehensive existing documentation and migrated gaps/requirements to traceability.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Authorization** | `mapping/nightscout-roles-gateway/authorization.md` | 114 lines (existing) |
| **Integration** | `mapping/nightscout-roles-gateway/integration.md` | 107 lines (existing) |
| **Gap Migration** | `traceability/nightscout-api-gaps.md` | GAP-RG-001 added |
| **Requirements** | `traceability/nightscout-api-requirements.md` | REQ-RG-001-004 added |

**Key Findings**:
- Three-mode access control (anonymous, identity-mapped, API secret bypass)
- Kratos/Hydra OAuth integration
- Time-based scheduled policies for schools/clinics
- HIPAA-adjacent audit trail via consent logging
- Not yet integrated into core Nightscout (requires separate deployment)

**Gaps Added**: GAP-RG-001

---

### Large File Analysis (2026-01-29)

Analyzed 53 files over 500 lines for autonomous workflow optimization.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Analysis** | `docs/sdqctl-proposals/large-file-analysis.md` | 174 lines |

**Key Findings**:
- 53 files over 500 lines, 6 over 1000 lines
- Largest: terminology-matrix.md (3024 lines)
- Traceability already properly chunked (7 domain files)
- Deep dives appropriately sized (single topic each)
- No immediate chunking needed

**Recommendation**: Add TOC to terminology-matrix.md (P3)

---

### Reporting Needs Analysis (2026-01-29)

Comparison of nightscout-reporter vs cgm-remote-monitor built-in reports.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Analysis** | `docs/10-domain/reporting-needs-analysis.md` | 250 lines |
| **Gaps Added** | `traceability/nightscout-api-gaps.md` | GAP-REPORT-001-003 |

**Key Findings**:
- cgm-remote-monitor: 11 report plugins (4,738 lines), HTML only
- nightscout-reporter: 17 print forms (15,000+ lines), PDF export
- Both compute statistics client-side (duplication)
- nightscout-reporter has superior PDF generation and multi-language

**Gaps Identified**:
| Gap ID | Issue |
|--------|-------|
| GAP-REPORT-001 | No server-side statistics API |
| GAP-REPORT-002 | No PDF export in cgm-remote-monitor |
| GAP-REPORT-003 | Loop analysis fragmented |

---

### CGM Sensor Session Handling Comparison (2026-01-29)

Cross-system analysis of sensor session start/stop and calibration patterns.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Comparison** | `docs/10-domain/cgm-session-handling-comparison.md` | 353 lines |
| **Gaps Added** | `traceability/cgm-sources-gaps.md` | GAP-SESSION-001-003 |

**Key Findings**:
- xDrip+ uses database entity model with pluggable calibration algorithms
- Loop uses BLE message protocol with 17-state calibration machine
- AAPS delegates session management to CGM source apps
- Only xDrip+ uploads sensor lifecycle events to Nightscout

**Gaps Identified**:
| Gap ID | Issue |
|--------|-------|
| GAP-SESSION-001 | Session events not standardized |
| GAP-SESSION-002 | Calibration state not exposed |
| GAP-SESSION-003 | Pluggable calibration unique to xDrip+ |

---

### Documentation Reorganization Proposal (2026-01-29)

Analyzed documentation structure for AI and human comprehension optimization.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Proposal** | `docs/sdqctl-proposals/documentation-reorganization-proposal.md` | 223 lines |


> **Archive**: More 2026-01-29 entries moved to [progress-archive-2026-01-29-batch2.md](docs/archive/progress-archive-2026-01-29-batch2.md)

- Loop: Full (push notifications)

> **Archive**: Earlier 2026-01-29 entries (Statistics API through Algorithm Conformance runners) moved to [progress-archive-2026-01-29-batch1.md](docs/archive/progress-archive-2026-01-29-batch1.md)

### Algorithm Conformance Suite Proposal (2026-01-29)

Proposal for cross-project AID algorithm testing infrastructure.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Proposal** | `docs/sdqctl-proposals/algorithm-conformance-suite.md` | 400+ lines, test vector schema, 5-phase plan |
| **Gaps** | `traceability/gaps.md` | GAP-ALG-001/002/003 added |

**Key Findings**:
- oref0: Mocha tests with inline fixtures, ~40 test scenarios
- AAPS: ReplayApsResultsTest with 50+ JSON fixtures, compares JS vs Kotlin
- Loop: XCTest with scattered fixtures in LoopKitTests/Fixtures/
- No cross-project test vectors exist today

**Proposed Architecture**:
1. Unified test vector JSON schema (`conformance-vector-v1.json`)
2. Category-based vectors: basal-adjustment, smb-delivery, safety-limits, etc.
3. Language-specific runners: oref0-runner.js, aaps-runner.kt, loop-runner.swift
4. Cross-language comparison matrix and gap documentation

**Recommendations**:
1. Extract 50+ vectors from AAPS replay test fixtures (ready-made)
2. Create oref0-runner.js as baseline validator
3. Define semantic equivalence for Loop vs oref comparison

---

### share2nightscout-bridge PR Analysis (2026-01-29)

Analyzed open PRs, issues, and WIP branches for ecosystem impact.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **PR Analysis** | `docs/10-domain/share2nightscout-bridge-pr-analysis.md` | 242 lines, 1 PR, 13 issues |
| **Gaps** | `traceability/gaps.md` | GAP-BRIDGE-001/002/003 added |

**Key Findings**:
- PR #59: Security fix for error handling - **merge immediately**
- Issue #61: Node 16+ EOL blocks cgm-remote-monitor upgrade
- Issue #52: Trend string bug already fixed, close issue
- WIP branch `wip/bewest/axios` nearly complete - finish and merge

**Recommendations**:
1. Merge PR #59 (security)
2. Complete axios migration to resolve Node EOL
3. Close stale 2015-era meta issues

---

### Cross-project Testing Plan (2026-01-29)

Proposal for Ubuntu-compatible testing strategies for Swift AID projects.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Proposal** | `docs/sdqctl-proposals/cross-project-testing-plan.md` | 363 lines, 4 strategies |
| **Gaps** | `traceability/gaps.md` | GAP-TEST-001/002/003 added |

**Key Findings**:
- Trio: GitHub Actions (macOS-15), 211 test files
- Loop: Travis CI (outdated xcode12.4), 233 test files
- LoopKit Package.swift marked "not complete yet"
- Swift on Linux lacks CoreData/HealthKit/UIKit

**Strategies Proposed**:
1. Extract pure-Swift algorithm packages (Medium effort, High impact)
2. Remote macOS test execution (Low effort)
3. Test fixture extraction (Low effort, High impact)
4. Docker-based Swift testing (Limited scope)

---

### Override/Profile Switch Comparison Update (2026-01-29)

Updated override comparison with deep source code analysis across Loop, AAPS, and Trio.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Deep Dive** | `docs/10-domain/override-profile-switch-comparison.md` | 416 lines, enhanced with Trio Exercise eventType |
| **Gaps** | `traceability/gaps.md` | GAP-OVERRIDE-005/006/007 added |

**Key Findings**:
- **Critical**: Trio uses `Exercise` eventType (NOT `Temporary Override`)
- Loop: `Temporary Override` with syncIdentifier (UUID)
- AAPS: `Profile Switch` with interfaceIDs.nightscoutId
- Three incompatible eventTypes for similar user intent
- Trio override upload loses algorithm settings (smbIsOff, percentage, target)

---

### Playwright Adoption Proposal (2026-01-29)

Proposal for E2E testing adoption in cgm-remote-monitor using Playwright.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Proposal** | `docs/sdqctl-proposals/playwright-adoption-proposal.md` | 316 lines, 4-phase plan |

**Key Points**:
- Current: 78 Mocha tests, no E2E, browser testing disabled
- Recommendation: Playwright over Cypress (multi-browser, Socket.IO)
- Effort: ~5-8 days initial investment
- Benefits: Safe refactoring, UI regression detection, cross-browser

---

### cgm-remote-monitor Database Layer Audit (2026-01-29)

Full audit of Nightscout's MongoDB storage layer for Loop compatibility.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Deep Dive** | `docs/10-domain/cgm-remote-monitor-database-deep-dive.md` | 455 lines, 6 collections, indexes, ordering |
| **Gaps** | `traceability/gaps.md` | GAP-DB-001/002/003 added |

**Key Findings**:
- MongoDB driver 3.6.0 (compatible with MongoDB 5.x)
- Treatment batch ordering preserved via `async.eachSeries`
- Loop's ordering requirement is satisfied
- Entries use `forEach` (unordered) but not critical for Loop
- API v3 uses `identifier` field with fallback deduplication

---

### Loop Sync Identity Fields Extraction (2026-01-29)

Extracted sync identity patterns from Loop/LoopKit for cross-project comparison.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Mapping** | `mapping/loop/sync-identity-fields.md` | 318 lines, syncIdentifier + ObjectIdCache patterns |
| **Gaps** | `traceability/gaps.md` | GAP-SYNC-005/006/007 added |

**Key Findings**:
- Loop uses `syncIdentifier` (pump hex or UUID) as primary identity
- `ObjectIdCache` maps to Nightscout `_id` (24-hour memory-only)
- Uses v1 POST only - no server-side deduplication
- Duplicates possible on app restart due to cache loss

---

### nightscout-librelink-up Deep Dive (2026-01-29)

Full audit of LibreLink Up to Nightscout bridge.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Deep Dive** | `docs/10-domain/nightscout-librelink-up-deep-dive.md` | 378 lines |

#### Key Findings

| Component | Purpose | Details |
|-----------|---------|---------|
| LibreLink API | Auth + glucose fetch | 8 regions, stealth mode |
| Interfaces | TypeScript models | GlucoseItem, Connection |
| Nightscout | v1 upload only | v3 stub exists |

| Feature | Status |
|---------|--------|
| Multi-patient | ✅ Supported |
| Historical backfill | ❌ Not implemented |
| API v3 | ❌ Stub only |

**Gaps Identified**: GAP-LIBRELINK-001, GAP-LIBRELINK-002, GAP-LIBRELINK-003

---

### tconnectsync Deep Dive (2026-01-29)

Full audit of Tandem t:connect to Nightscout sync tool.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Deep Dive** | `docs/10-domain/tconnectsync-deep-dive.md` | 368 lines |

#### Key Findings

| Component | Purpose | Files |
|-----------|---------|-------|
| API | t:connect OAuth2/OIDC auth | 7 files, 1400+ lines |
| Domain | Bolus, TherapyEvent, Profile | 3 key models |
| Sync | NS v1 API upload | 10+ treatment types |

| Treatment Type | NS eventType |
|----------------|--------------|
| Combo Bolus | `Combo Bolus` |
| Temp Basal | `Temp Basal` |
| Site Change | `Site Change` |
| Exercise/Sleep | `Exercise`, `Sleep` |

**Gaps Identified**: GAP-TCONNECT-001, GAP-TCONNECT-002, GAP-TCONNECT-003

---

### OpenAPS/oref0 Deep Dive (2026-01-29)

Full audit of the foundational OpenAPS ecosystem - the original DIY closed-loop system.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Deep Dive** | `docs/10-domain/openaps-oref0-deep-dive.md` | 371 lines, 2 repos |

#### Key Findings

| Component | Purpose | Language |
|-----------|---------|----------|
| openaps | Device toolkit (pump/CGM drivers) | Python |
| oref0 | Reference algorithm (determine-basal) | JavaScript |

| Algorithm File | Lines | Function |
|----------------|-------|----------|
| determine-basal.js | 1192 | Main dosing calculation |
| autosens.js | 454 | Sensitivity detection |
| cob.js | 211 | Carbs on board |
| iob/history.js | 572 | IOB history processing |

**Gaps Identified**: GAP-OREF-001, GAP-OREF-002, GAP-OREF-003

---


> **Archive**: 2026-01-28 entries moved to [progress-archive-2026-01-28.md](docs/archive/progress-archive-2026-01-28.md)

---

### LIVE-BACKLOG Hygiene Cycle (2026-01-29)

Processed 3 pending human requests from LIVE-BACKLOG.

| Request | Action | Result |
|---------|--------|--------|
| Fix backlog checkbox format | Audited all backlogs | tooling.md fixed (hygiene suite → completed) |
| Reevaluate sdqctl-proposals | Audited 14 proposals | 2 already in queue, 3 new items identified |
| Chunk docs accuracy review | Queued to documentation | Added systematic review item |

#### Format Issues Fixed

| File | Issue | Fix |
|------|-------|-----|
| `backlogs/tooling.md` | Hygiene suite still in Active | Moved to Completed table |

#### Proposals Audit Summary

| Status | Count | Examples |
|--------|-------|----------|
| Ready for implementation | 2 | playwright-adoption, algorithm-conformance |
| Needs upstream review | 3 | statistics-api, HELP-INLINE, RUN-BRANCHING |
| Research/Draft | 4 | nocturne-modernization, STPA, nightscout-connect |
| Complete | 5 | hygiene-tooling, tools-comparison, etc. |


---

### Sync Requirements Traceability (2026-01-29)

Added detailed requirements REQ-030 through REQ-035 with scenarios and source references.

| Requirement | Title | Scenarios | Gap Refs |
|-------------|-------|-----------|----------|
| REQ-030 | Sync Identity Preservation | 3 | - |
| REQ-031 | Self-Entry Exclusion | 3 | - |
| REQ-032 | Incremental Sync Support | 3 | GAP-API-003 |
| REQ-033 | Server Deduplication | 3 | GAP-SYNC-009 |
| REQ-034 | Cross-Controller Coexistence | 3 | GAP-SYNC-008 |
| REQ-035 | Conflict Detection | 3 | GAP-SYNC-008, REQ-NS-028 |

**Source Files Referenced**:
- `mapping/cross-project/aid-controller-sync-patterns.md`
- `mapping/trio/carb-math.md`
- `mapping/cgm-remote-monitor/api-versions.md`
- `mapping/cgm-remote-monitor/deduplication.md`
- `docs/10-domain/authority-model.md`

**Requirements Total**: 126 (+6)

