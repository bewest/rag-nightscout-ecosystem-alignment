# AID Alignment Workspace - Progress Tracker

This document tracks completed documentation cycles and candidates for future work.

> **Archive**: Entries before 2026-01-28 moved to [progress-archive-2026-01-17-to-23.md](docs/archive/progress-archive-2026-01-17-to-23.md)

---

## Completed Work

### Playwright E2E Test Suite for Nightscout (2026-01-29)

Created Playwright E2E test infrastructure for cgm-remote-monitor.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Config** | `conformance/e2e-nightscout/playwright.config.js` | 101 lines |
| **Dashboard Tests** | `conformance/e2e-nightscout/dashboard.spec.js` | 179 lines |
| **API Tests** | `conformance/e2e-nightscout/api.spec.js` | 144 lines |
| **README** | `conformance/e2e-nightscout/README.md` | 167 lines |

**Key Features**:
- Multi-browser support (Chrome, Firefox, Safari, mobile)
- Dashboard smoke tests (8 scenarios)
- API v1/v3 smoke tests (9 scenarios)
- CI integration template for GitHub Actions
- Ready to submit as PR to cgm-remote-monitor

**Total**: 591 lines of test infrastructure

---

### Loop vs oref0 Semantic Equivalence Analysis (2026-01-29)

Analyzed Loop algorithm to determine conformance testing feasibility with oref0 vectors.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Deep Dive** | `docs/10-domain/loop-oref0-semantic-equivalence.md` | 400 lines |

**Key Findings**:
- Loop uses single combined prediction curve (vs oref0's 4 curves)
- Loop has no Autosens - uses RetrospectiveCorrection instead
- Loop has no SMB or UAM curve
- Direct output comparison NOT feasible
- Loop needs its own Swift-based conformance runner
- oref0 test vectors cannot be reused (missing raw dose history)

**Gaps Identified**: GAP-ALG-013, GAP-ALG-014, GAP-ALG-015, GAP-ALG-016

---

### AAPS vs oref0 Divergence Analysis (2026-01-29)

Analyzed 69% divergence in conformance testing between AAPS and oref0 algorithm outputs.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Deep Dive** | `docs/10-domain/aaps-oref0-divergence-analysis.md` | 280 lines |

**Key Findings**:
- 85 test vectors from AAPS ReplayApsResultsTest fixtures
- OpenAPSSMBPlugin (vanilla oref0): 94% pass rate - effectively identical
- OpenAPSSMBDynamicISFPlugin: 18% pass rate - major divergence
- OpenAPSSMBAutoISFPlugin: 5% pass rate - very high divergence
- Root cause: DynamicISF and AutoISF are AAPS-specific extensions not in oref0
- Core oref0 algorithm is preserved in AAPS Kotlin port

**Gaps Identified**: GAP-ALG-009, GAP-ALG-010, GAP-ALG-011, GAP-ALG-012

---

### Algorithm Core Terminology Mapping (2026-01-29)

Added comprehensive algorithm terminology mapping across Loop, AAPS, Trio, and oref0.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Terminology** | `mapping/cross-project/terminology-matrix.md` | +95 lines |

**Key Findings**:
- ISF: `sens` (oref0/Trio) vs `insulinSensitivity` (Loop) vs `isf/getIsfMgdl()` (AAPS)
- CR: `carb_ratio` (oref0) vs `carbRatio` (Loop) vs `ic/getIc()` (AAPS)
- DIA: Consistent `dia` or `actionDuration` across systems
- UAM: Full support in oref0/AAPS/Trio; notification-only in Loop (`MissedMeal`)
- SMB: Supported in oref0/AAPS/Trio; NOT supported in Loop
- Autosens: Supported in oref0/AAPS/Trio; NOT in Loop (uses `RetrospectiveCorrection`)

**Gaps Referenced**: GAP-ALG-005 (Loop lacks SMB/UAM), GAP-ALG-006 (DynISF differences)

---

### xDrip+ Nightscout Field Mapping (2026-01-29)

Created comprehensive field mapping for xDrip+ Nightscout uploads.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Field Mapping** | `mapping/xdrip/nightscout-fields.md` | 306 lines |
| **README** | `mapping/xdrip/README.md` | 64 lines |

**Key Findings**:
- Uses Nightscout v1 API only (entries, treatments, devicestatus, activity)
- Device string format: `"xDrip-{collection_method}"` with optional source_info
- Treatment sync via UUID field and lookup/delete pattern
- Activity endpoint for heart rate, steps, motion (non-standard)
- Supports 20+ CGM data sources via collection method setting
- GZIP compression support for uploads

**Gaps Identified**: GAP-XDRIP-001, GAP-XDRIP-002, GAP-XDRIP-003

---

### CGM Sensor Session Handling Comparison (2026-01-29)

Created cross-project comparison of CGM sensor session handling across xDrip+, DiaBLE, Loop, and AAPS.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Deep Dive** | `docs/10-domain/cgm-session-handling-deep-dive.md` | 407 lines |

**Key Findings**:
- xDrip+: Comprehensive CalibrationState enum with 25+ states
- DiaBLE: SensorState enum (notActivated, warmingUp, active, expired, shutdown, failure)
- Loop: CgmEvent model with explicit warmupPeriod property
- AAPS: TherapyEvent types (SENSOR_CHANGE, SENSOR_STARTED, SENSOR_STOPPED)
- No standard Nightscout schema for session events
- Warm-up duration varies by sensor (30min to 2hr) but not uploaded

**Gaps Identified**: GAP-SESSION-001, GAP-SESSION-002, GAP-SESSION-003, GAP-SESSION-004

---

### DiaBLE Deep Dive (2026-01-29)

Created comprehensive deep-dive documentation for DiaBLE iOS/watchOS CGM reader application.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Deep Dive** | `docs/10-domain/diable-deep-dive.md` | 487 lines |

**Key Findings**:
- Supports both Abbott Libre (1/2/3) and Dexcom (G6/G7) sensors
- Nightscout integration: v1 API only, SGV entries upload, no treatments
- Libre 3: Partial support (eavesdrop mode, cannot decrypt independently)
- Dexcom G7: App-dependent (no standalone J-PAKE authentication)
- Native Apple Watch app with direct BLE connectivity proof-of-concept
- Temperature-based calibration from LibreLink 2.3 algorithm

**Gaps Identified**: GAP-DIABLE-002, GAP-DIABLE-003 (GAP-CGM-001 previously existed)

---

### LoopCaregiver Deep Dive (2026-01-29)

Created comprehensive deep-dive documentation for LoopCaregiver remote command app.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Deep Dive** | `docs/10-domain/loopcaregiver-deep-dive.md` | 417 lines |

**Key Findings**:
- Remote commands: Bolus, Carbs, Override, Autobolus, Closed Loop
- Security: API secret + TOTP + 5-minute expiration
- V1 commands via push notifications
- V2 commands (experimental) add status tracking
- Loop-only support (no Trio/OpenAPS)

**Gaps Identified**: GAP-LOOPCAREGIVER-001, GAP-LOOPCAREGIVER-002, GAP-LOOPCAREGIVER-003

---

### LoopFollow Deep Dive (2026-01-29)

Created comprehensive deep-dive documentation for LoopFollow caregiver monitoring app.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Deep Dive** | `docs/10-domain/loopfollow-deep-dive.md` | 411 lines |

**Key Findings**:
- Consumes Nightscout API v1: entries, treatments, devicestatus, profile
- Supports Loop, OpenAPS, and Trio devicestatus formats
- Multi-source: Dexcom Share primary with Nightscout fallback
- Remote commands via APNS (Loop), TRC (Trio), Nightscout
- Multi-instance: 3 concurrent LoopFollow apps supported

**Gaps Identified**: GAP-LOOPFOLLOW-001, GAP-LOOPFOLLOW-002, GAP-LOOPFOLLOW-003

---

### nightscout-librelink-up Field Mapping (2026-01-29)

Created comprehensive field mapping documentation for LibreLink Up bridge.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **README** | `mapping/nightscout-librelink-up/README.md` | 76 lines, index |
| **API** | `mapping/nightscout-librelink-up/api.md` | 258 lines, LibreLink Up API |
| **Entries** | `mapping/nightscout-librelink-up/entries.md` | 274 lines, field mapping |

**Key Findings**:
- 8 API regions (EU, EU2, US, AU, DE, FR, JP, AP)
- Multi-patient support via `LINK_UP_CONNECTION`
- Trend arrow limited to 5 values (no DoubleUp/DoubleDown)
- Uses FactoryTimestamp (sensor time) not local phone time
- v1 API only (v3 stub throws error)

**Gaps Identified**: GAP-LIBRELINK-001, GAP-LIBRELINK-002, GAP-LIBRELINK-003

---

### share2nightscout-bridge Field Mapping (2026-01-29)

Created comprehensive field mapping documentation for Dexcom Share bridge.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **README** | `mapping/share2nightscout-bridge/README.md` | 70 lines, index |
| **API** | `mapping/share2nightscout-bridge/api.md` | 178 lines, Dexcom Share API |
| **Entries** | `mapping/share2nightscout-bridge/entries.md` | 176 lines, field mapping |

**Key Findings**:
- Dexcom timestamp format: `/Date(milliseconds-offset)/` parsed with regex
- Trend values 0-9 map to direction strings
- Device identifier always `"share2"`
- Uses v1 API only (no v3 support - GAP-SHARE-001)
- No backfill logic for missed readings (GAP-SHARE-002)
- Hardcoded applicationId (GAP-SHARE-003)

**Gaps Identified**: GAP-SHARE-001, GAP-SHARE-002, GAP-SHARE-003

---

### tconnectsync Field Mapping (2026-01-29)

Created comprehensive field mapping documentation for Tandem t:connect sync tool.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **README** | `mapping/tconnectsync/README.md` | 79 lines, index |
| **Models** | `mapping/tconnectsync/models.md` | 159 lines, Bolus/TherapyEvent/Profile |
| **API** | `mapping/tconnectsync/api.md` | 198 lines, t:connect endpoints |
| **Treatments** | `mapping/tconnectsync/treatments.md` | 171 lines, 10+ treatment types |

**Key Findings**:
- Maps 10+ t:connect events to Nightscout treatment types
- Uses v1 API only (no v3 support - GAP-TCONNECT-001)
- 3 auth methods: OIDC, Android credentials, web form
- No trend direction in CGM data (GAP-TCONNECT-004)
- Batch sync only, no real-time push

**Gaps Identified**: GAP-TCONNECT-004 (no trend direction)

---

### Nocturne Field Mapping (2026-01-29)

Created comprehensive field mapping documentation for Nocturne .NET rewrite.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **README** | `mapping/nocturne/README.md` | 64 lines, index |
| **Models** | `mapping/nocturne/models.md` | 187 lines, 6 models |
| **Connectors** | `mapping/nocturne/connectors.md` | 244 lines, 8 connectors |
| **API Versions** | `mapping/nocturne/api-versions.md` | 207 lines, v1-v4 coverage |

**Key Findings**:
- Full v1/v2/v3 API parity with cgm-remote-monitor
- 8 native connectors (Dexcom, Libre, Glooko, CareLink, MFP, NS, t:connect, Tidepool)
- V4 endpoints are Nocturne-specific (GAP-NOCTURNE-001)
- Rust oref implementation for algorithm calculations

**Gaps Identified**: GAP-CONNECTOR-001, GAP-CONNECTOR-002, GAP-CONNECTOR-003

---

### Duration/utcOffset Unit Impact Analysis (2026-01-29)

Analyzed unit inconsistencies across AID systems for duration and timezone fields.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Impact Analysis** | `docs/10-domain/duration-utcoffset-unit-analysis.md` | 256 lines |
| **Requirements** | REQ-UNIT-001 to REQ-UNIT-004 | 4 new requirements |

**Key Findings**:
- Duration: NS=minutes, Loop=seconds, AAPS=milliseconds (60x/60000x mismatch)
- utcOffset: NS=minutes, AAPS internal=milliseconds
- 4 standardization alternatives evaluated (recommend Option 1 Enhanced)
- AAPS preserves `durationInMilliseconds` for round-trip accuracy

**Gaps Addressed**: GAP-TREAT-002, GAP-TZ-004, GAP-PUMP-003

---

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

> **Archive**: Earlier 2026-01-29 entries moved to [progress-archive-2026-01-29-batch3.md](docs/archive/progress-archive-2026-01-29-batch3.md)

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

