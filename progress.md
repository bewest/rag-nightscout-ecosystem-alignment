# AID Alignment Workspace - Progress Tracker

This document tracks completed documentation cycles and candidates for future work.

> **Archive**: Entries before 2026-01-28 moved to [progress-archive-2026-01-17-to-23.md](docs/archive/progress-archive-2026-01-17-to-23.md)

---

## Completed Work

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

**Key Findings**:
- 193 files, 74,644 lines across 5 directories
- Structure is fundamentally sound
- Naming conventions are consistent
- Some missing index files identified

**Recommendations**: Add README to docs/10-domain/, add cross-references to profile files.

---

### Profile Collection Deep Dive - Gaps Migration (2026-01-29)

Found existing comprehensive comparison (557 lines). Migrated 4 gaps to traceability.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Comparison Doc** | `docs/60-research/profile-therapy-settings-comparison.md` | 557 lines (pre-existing) |
| **Gaps Added** | `traceability/nightscout-api-gaps.md` | GAP-PROFILE-001 through 004 |

**Key Findings** (from existing doc):
- Loop uses HealthKit units; Nightscout uses strings
- AAPS uses duration blocks; Nightscout uses start-time arrays
- Loop has no profile naming (single anonymous profile)
- Loop upload-only; Trio download-only; AAPS bidirectional

**Gaps Migrated**:
| Gap ID | Issue |
|--------|-------|
| GAP-PROFILE-001 | Unit representation mismatch (HKQuantity vs string) |
| GAP-PROFILE-002 | Time block vs start-time format |
| GAP-PROFILE-003 | Loop has no profile naming |
| GAP-PROFILE-004 | Loop doesn't download profiles |

---

### Algorithm Terminology Mapping - Already Complete (2026-01-29)

Verified terminology matrix (3024 lines) already has comprehensive coverage:

| Section | Coverage |
|---------|----------|
| ISF/CR/DIA/UAM | Lines 490-500, 1170-1230 |
| Prediction methodology | Lines 1172-1180 |
| Carb absorption models | Lines 1182-1189 |
| Sensitivity mechanisms | Lines 1191-1198 |
| GAP-ALG-001 through 007 | Lines 1202-1210 |

No new work needed - terminology already documented.

---

### Device Status Collection Deep Dive - Gaps Migration (2026-01-29)

Found existing comprehensive deep dive (863 lines). Migrated 4 gaps to traceability.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Deep Dive** | `docs/10-domain/devicestatus-deep-dive.md` | 863 lines (pre-existing) |
| **Gaps Added** | `traceability/nightscout-api-gaps.md` | GAP-DS-001 through 004 |

**Key Findings** (from existing doc):
- Loop uses flat `loop` object; oref0 systems use nested `openaps` object
- Loop: single combined prediction; oref0: 4 curves (IOB, COB, UAM, ZT)
- Duration units differ: Loop=seconds, oref0=minutes
- Loop exposes less algorithm state than oref0

**Gaps Migrated**:
| Gap ID | Issue |
|--------|-------|
| GAP-DS-001 | No effect timelines in Loop |
| GAP-DS-002 | Prediction array incompatibility |
| GAP-DS-003 | Duration unit inconsistency |
| GAP-DS-004 | Missing algorithm transparency in Loop |

---

### nightscout-connect Design Review (2026-01-29)

Comprehensive design review of nightscout-connect XState architecture, vendor extensibility, and refactoring suggestions.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Design Review** | `docs/10-domain/nightscout-connect-design-review.md` | 340 lines, 7 refactoring suggestions |
| **Gaps Added** | `traceability/connectors-gaps.md` | GAP-CONNECT-004 through 006 |

**Key Findings**:
- Excellent XState usage: hierarchical machines, parallel states, service injection
- 5 vendors supported: Nightscout, Dexcom Share, Glooko, LibreLinkUp, Minimed Carelink
- Clean builder pattern for vendor registration
- Uses exponential backoff, schedule alignment, session reuse

**Refactoring Priorities**:
1. Add `@xstate/test` model-based testing (no tests currently)
2. Add API v3 output driver (v1 only)
3. Add TypeScript type definitions

**Gaps Identified**:
| Gap ID | Issue |
|--------|-------|
| GAP-CONNECT-004 | No test suite |
| GAP-CONNECT-005 | No TypeScript types |
| GAP-CONNECT-006 | Brittle adapter pattern |

**Source Files**:
- `externals/nightscout-connect/lib/builder.js`
- `externals/nightscout-connect/lib/machines/*.js`
- `externals/nightscout-connect/machines.md`

---

### Nightscout API v3 Deep Dive (2026-01-29)

Comprehensive analysis of Nightscout API v3 architecture, collections, operations, and sync patterns.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Deep Dive** | `docs/10-domain/nightscout-apiv3-deep-dive.md` | 290 lines, 6 collections, 8 operations |
| **Gaps Added** | `traceability/nightscout-api-gaps.md` | GAP-API3-001 through GAP-API3-003 |
| **Requirements** | `traceability/nightscout-api-requirements.md` | REQ-API3-001 through REQ-API3-003 |

**Key Findings**:
- 6 collections: devicestatus, entries, food, profile, settings, treatments
- 8 operations per collection: SEARCH, CREATE, READ, UPDATE, PATCH, DELETE, HISTORY, plus version endpoints
- shiro-trie permission model: `api:{collection}:{operation}`
- Query operators: eq, ne, gt, gte, lt, lte, in, nin, re
- Deduplication via `identifier` with per-collection fallback fields
- History endpoint returns soft-deleted docs (`isValid=false`) for sync completeness

**Gaps Identified**:
| Gap ID | Issue |
|--------|-------|
| GAP-API3-001 | No batch operations for bulk sync |
| GAP-API3-002 | Offset pagination inefficient for large datasets |
| GAP-API3-003 | Field projection lacks exclusion syntax |

**Source Files**:
- `externals/cgm-remote-monitor/lib/api3/index.js`
- `externals/cgm-remote-monitor/lib/api3/generic/setup.js`
- `externals/cgm-remote-monitor/lib/api3/generic/search/input.js`
- `externals/cgm-remote-monitor/lib/api3/generic/history/operation.js`

---

### Hygiene: Chunk progress.md (2026-01-29)

Maintenance task to reduce progress.md from 1713 to 807 lines (53% reduction).

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Archive** | `docs/archive/progress-archive-2026-01-17-to-23.md` | 916 lines, Jan 17-23 entries |
| **Current** | `progress.md` | 807 lines, Jan 28-29 entries |

**Approach**: Split at date boundary (2026-01-28), archive older entries, add link header.

---

### Authentication Flows Deep Dive (2026-01-29)

Comprehensive analysis of Nightscout authentication and authorization system.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Deep Dive** | `docs/10-domain/authentication-flows-deep-dive.md` | 362 lines, 3 auth methods, 4 gaps |
| **Gaps Added** | `traceability/nightscout-api-gaps.md` | GAP-AUTH-001 through GAP-AUTH-004 |
| **Terminology** | `mapping/cross-project/terminology-matrix.md` | Added Authentication Concepts section |

**Key Findings**:
- API_SECRET grants full `*` access, bypassing RBAC
- JWT secret stored in node_modules (lost on npm update)
- No account lockout (only delay list)
- enteredBy field unverified
- No token revocation mechanism

**Client Auth Patterns**:
| Client | Method | Transport |
|--------|--------|-----------|
| AAPS | Access Token | WebSocket |
| Loop | API Secret | REST |
| xDrip+ | SHA1 Secret | REST |

---

### Remote Commands API Specification (2026-01-29)

OpenAPI 3.0 specification for Remote Commands collection based on PR#7791 and Loop RemoteCommand protocol.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **OpenAPI Spec** | `specs/openapi/aid-commands-2025.yaml` | 738 lines, 7 endpoints, full schema |
| **Gap Updated** | `traceability/nightscout-api-gaps.md` | GAP-REMOTE-CMD marked addressed |
| **Terminology** | `mapping/cross-project/terminology-matrix.md` | Added Remote Commands section |

**Key Schema Features**:
- 4 action types: bolus, carbs, override, cancelOverride
- State machine: Pending → In-Progress → Complete/Error
- OTP security validation
- Push notification integration (APNs)

**Controller Support**:
- Loop: Full (push notifications)
- Trio: Full (push notifications)
- AAPS: None (uses SMS instead)
- xDrip+: None (display only)

**Source Files Analyzed**:
- `ns:lib/api/remotecommands/index.js`
- `ns:lib/server/remotecommands.js`
- `loop:NightscoutService/NightscoutServiceKit/RemoteCommands/Actions/*.swift`

---

### Insulin Profiles API Specification (2026-01-29)

OpenAPI 3.0 specification for Insulin Profiles collection based on PR#8261 and cross-project analysis.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **OpenAPI Spec** | `specs/openapi/aid-insulin-2025.yaml` | 576 lines, 5 endpoints, full schema |
| **Gap Updated** | `traceability/aid-algorithms-gaps.md` | GAP-INSULIN-001 marked addressed |
| **Terminology** | `mapping/cross-project/terminology-matrix.md` | Added Insulin Profiles section |

**Key Schema Fields**:
- `name` (string) - Insulin type name (NovoRapid, Fiasp, etc.)
- `dia` (number) - Duration of Insulin Action in hours
- `peak` (integer) - Time to peak activity in minutes
- `curve` (enum) - Activity model (rapid-acting, ultra-rapid, bilinear, etc.)
- `active` (enum) - Bolus or basal designation
- `concentration` (enum) - U100/U200/U300/U500

**Bug Found**: PR#8261 /insulin/basal endpoint calls bolus() function (line 28)

**Controller Support**:
- xDrip+: Full (InsulinInjection.insulin)
- AAPS: Partial (insulinConfiguration not synced)
- nightscout-reporter: Read-only
- Loop/Trio: Not supported

---

### Heart Rate API Specification (2026-01-29)

OpenAPI 3.0 specification for HeartRate collection based on PR#8083 and AAPS entity.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **OpenAPI Spec** | `specs/openapi/aid-heartrate-2025.yaml` | 447 lines, 6 endpoints, full schema |
| **Gap Updated** | `traceability/gaps.md` | GAP-API-HR marked addressed |
| **Requirement** | `traceability/requirements.md` | REQ-PR-001 linked to spec |

**Key Schema Fields**:
- `beatsPerMinute` (double) - HR value in BPM
- `timestamp` (int64) - Epoch milliseconds
- `duration` (int64) - Sampling window
- `device` (string) - Source device
- `identifier` (uuid) - Sync identity

**Controller Support**:
- AAPS: Full (primary source)
- Loop/Trio: None
- xDrip+: Partial (display only)

---

### Statistics API Proposal (2026-01-29)

Comprehensive API specification for server-side glucose statistics with MCP integration.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Proposal** | `docs/sdqctl-proposals/statistics-api-proposal.md` | 480 lines, 6 endpoints, MCP resources |
| **Gaps** | `traceability/gaps.md` | GAP-STATS-001/002/003 added |
| **Requirements** | `traceability/requirements.md` | REQ-STATS-001-005 added |

**Key Features**:
- `/api/v3/stats/daily` - Per-day glucose aggregations
- `/api/v3/stats/summary` - Period summaries with A1C/GMI
- `/api/v3/stats/hourly` - Hourly percentile distributions
- `/api/v3/stats/treatments` - Insulin/carb aggregations
- MCP resources for AI integration

**Benefits**:
- 90% reduction in data transfer for reports
- Server-side caching with MongoDB aggregation
- Standard formulas: A1C (DCCT/IFCC), GMI, GVI, PGS

---

### cgm-remote-monitor PR Analysis (2026-01-29)

Analysis of 68 open PRs for ecosystem impact and project trajectory.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **PR Analysis** | `docs/10-domain/cgm-remote-monitor-pr-analysis.md` | 380 lines, 68 PRs categorized |
| **Gaps** | `traceability/gaps.md` | GAP-API-HR, GAP-INSULIN-001, GAP-REMOTE-CMD, GAP-TZ-001 |
| **Requirements** | `traceability/requirements.md` | REQ-PR-001/002/003/004 added |

**Key Findings**:
- 68 open PRs spanning 2021-2026
- PR#8083 (Heart Rate) blocked AAPS integration for 2.5 years
- PR#8261 (Multi-Insulin) already used by xDrip+/reporter but not merged
- PR#7791 (Remote Commands) critical Loop caregiver feature stalled 3+ years
- Active modernization wave: Lodash, Moment, crypto-browserify removal

**Tier 1 Ecosystem PRs**:
1. #8421 MongoDB 5x (bewest) - 117 files
2. #8083 Heart Rate (buessow) - AAPS blocked
3. #8261 Multi-Insulin (gruoner) - in production
4. #7791 Remote Commands (gestrich) - Loop caregivers

---

### cgm-remote-monitor Frontend Audit (2026-01-29)

Comprehensive analysis of Nightscout's client-side architecture, D3.js charts, and plugin UI.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Deep Dive** | `docs/10-domain/cgm-remote-monitor-frontend-deep-dive.md` | 468 lines, D3, plugins, i18n |
| **Gaps** | `traceability/gaps.md` | GAP-UI-001/002/003 added |
| **Requirements** | `traceability/requirements.md` | REQ-UI-001/002/003 added |

**Key Findings**:
- Webpack bundles: main, clocks, reports
- D3.js dual-view chart: focus (70%) + context (30%) with brush
- Plugin UI: 4 container types (pill-major/minor/status, drawer)
- 33 languages via JSON translation files
- Vanilla JS/jQuery architecture (no component framework)

**Recommendations**:
1. Document frontend architecture for contributors
2. Add chart accessibility (ARIA, keyboard nav)
3. Implement offline data caching

---

### cgm-remote-monitor Authentication Audit (2026-01-29)

Comprehensive analysis of Nightscout's authorization system, Shiro permissions, and token handling.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Deep Dive** | `docs/10-domain/cgm-remote-monitor-auth-deep-dive.md` | 475 lines, Shiro, JWT, roles |
| **Gaps** | `traceability/gaps.md` | GAP-AUTH-003/004/005 added |
| **Requirements** | `traceability/requirements.md` | REQ-AUTH-001/002/003 added |

**Key Findings**:
- Shiro-style hierarchical permissions: `domain:collection:action`
- 7 default roles (admin, readable, careportal, devicestatus-upload, etc.)
- API_SECRET grants full `*` admin access, bypassing RBAC
- JWT tokens: 8-hour lifetime, symmetric key signing
- Rate limiting: 5 seconds per failed attempt, cumulative

**Recommendations**:
1. Document all permission strings
2. Add token revocation mechanism
3. Deprecate API_SECRET for write operations

---

### cgm-remote-monitor Sync/Upload Audit (2026-01-29)

Comprehensive analysis of Nightscout's real-time sync, Socket.IO architecture, and upload handlers.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Deep Dive** | `docs/10-domain/cgm-remote-monitor-sync-deep-dive.md` | 520 lines, WebSocket, sync identity |
| **Gaps** | `traceability/gaps.md` | GAP-SYNC-008/009/010 added |
| **Requirements** | `traceability/requirements.md` | REQ-SYNC-001/002/003 added |

**Key Findings**:
- Socket.IO uses 3 namespaces (`/`, `/alarm`, `/storage`)
- Delta compression: only changes broadcast, 512-byte threshold
- Sync identity: UUID v5 from device+date+eventType
- 3-tier dedup: identifier → _id → fallback fields
- LoadRetro: 24-hour devicestatus history on demand

**Recommendations**:
1. Document WebSocket API with event schemas
2. Backfill identifier field in v1 API uploads
3. Return sync metadata in upload responses

---

### cgm-remote-monitor Plugin System Audit (2026-01-29)

Comprehensive analysis of Nightscout's 38-plugin architecture and data pipeline.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Deep Dive** | `docs/10-domain/cgm-remote-monitor-plugin-deep-dive.md` | 436 lines, IOB/COB, Loop/OpenAPS |
| **Gaps** | `traceability/gaps.md` | GAP-PLUGIN-001/002/003 added |
| **Requirements** | `traceability/requirements.md` | REQ-PLUGIN-001/002/003 added |

**Key Findings**:
- 38 plugins with standardized lifecycle (setProperties, checkNotifications)
- IOB/COB use device-first with treatment fallback calculation
- Loop: single prediction array; OpenAPS: 6 curves (IOB, ZT, COB, aCOB, UAM)
- AAPS uses OpenAPS plugin (no dedicated AAPS plugin)
- Typo tolerance: accepts both `received` and `recieved` fields

**Recommendations**:
1. Document devicestatus schema per controller
2. Normalize prediction format in visualization
3. Document IOB/COB calculation models

---

### cgm-remote-monitor API Layer Audit (2026-01-29)

Comprehensive analysis of Nightscout's v1 and v3 REST API architecture.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Deep Dive** | `docs/10-domain/cgm-remote-monitor-api-deep-dive.md` | 397 lines, v1/v3 comparison, dedup logic |
| **Gaps** | `traceability/gaps.md` | GAP-API-006/007/008 added |
| **Requirements** | `traceability/requirements.md` | REQ-API-001/002/003 added |

**Key Findings**:
- v3 API uses UPSERT semantics (duplicates updated, not rejected)
- Dedup keys: treatments use `created_at + eventType`, entries use `date + type`
- Socket.IO broadcasts via `dataUpdate` event to `DataReceivers` room
- Shiro-style permissions: `api:collection:action`

**Recommendations**:
1. Document dedup keys per collection in API spec
2. Generate OpenAPI 3.0 specification for v3
3. Standardize timestamp field names across collections

---

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

### Prediction Array Formats Comparison (2026-01-28)

Cross-system analysis of glucose prediction array formats across Loop, AAPS, and Trio.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Comparison** | `docs/10-domain/prediction-arrays-comparison.md` | 319 lines, 3 systems |

#### Key Findings

| System | Prediction Model | devicestatus Field |
|--------|------------------|-------------------|
| Loop | Single combined curve | `loop.predicted.values` |
| AAPS | 4 separate curves (IOB/COB/UAM/ZT) | `openaps.suggested.predBGs.*` |
| Trio | 4 separate curves (IOB/COB/UAM/ZT) | `openaps.suggested.predBGs.*` |

**Gaps Identified**: GAP-PRED-002, GAP-PRED-003, GAP-PRED-004

---

### Batch Operation Ordering Deep Dive (2026-01-28)

Analysis of sync order requirements and ID mapping patterns across Loop, AAPS, Nightscout.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Deep Dive** | `docs/10-domain/batch-ordering-deep-dive.md` | 334 lines |

#### Key Findings

| System | Strategy | Order Sensitive |
|--------|----------|-----------------|
| Loop | v1 batch + zip() | ✅ Critical |
| AAPS | Sequential v3 | ❌ N/A |
| NS v3 | Single-doc only | ❌ N/A |

**Key Recommendation**: Parse `identifier` from response, not positional matching.

---

### Override/Profile Switch Comparison (2026-01-28)

Cross-system analysis of therapy adjustment semantics across Loop, AAPS, and Trio.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Comparison** | `docs/10-domain/override-profile-switch-comparison.md` | 331 lines, 3 systems |

#### Key Findings

| System | Model | NS eventType |
|--------|-------|--------------|
| Loop | TemporaryScheduleOverride | Temporary Override |
| AAPS | ProfileSwitch + TempTarget | Profile Switch + Temporary Target |
| Trio | Override + TempTarget | Temporary Override + Temporary Target |

**Gaps Identified**: GAP-OVERRIDE-001 through GAP-OVERRIDE-004

---

### Remote Bolus Command Comparison (2026-01-28)

Cross-system analysis of remote bolus handling in Loop, AAPS, Trio, and Nightscout.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Comparison** | `docs/10-domain/remote-bolus-comparison.md` | 348 lines, 4 systems |

#### Key Findings

| System | Auth | Key Safety Feature |
|--------|------|-------------------|
| Loop | OTP + APNs | 5-min expiration |
| AAPS | SMS passcode | 15-min distance |
| Trio | AES-256 | 20% rule + IOB check |
| Nightscout | API secret | Relay only (no limits) |

**Gaps Identified**: GAP-REMOTE-001 through GAP-REMOTE-004

---

### Nightscout v3 Treatments Schema (2026-01-28)

Extracted authoritative treatments schema from origin Nightscout server.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Schema** | `mapping/nightscout/v3-treatments-schema.md` | 248 lines, 21+ eventTypes |

#### Key Findings

| Aspect | Details |
|--------|---------|
| **eventTypes** | 21+ types (careportal + OpenAPS plugins) |
| **Date formats** | Accepts ms, seconds, or ISO-8601 |
| **Deduplication** | By identifier or `created_at + eventType` |
| **Duration** | Always minutes |

#### NS vs AAPS Comparison
- AAPS has `pumpId`/`pumpSerial` for dedup (NS doesn't)
- AAPS has bolus `type` field (NORMAL/SMB)
- eventTypes mostly compatible (different naming)

---

### Modernization Analysis: cgm-remote-monitor vs Nocturne (2026-01-28)

Comprehensive comparison of original Nightscout server vs Nocturne .NET rewrite.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Analysis** | `docs/sdqctl-proposals/nocturne-modernization-analysis.md` | 350 lines, full comparison |

#### Key Findings

| Aspect | cgm-remote-monitor | Nocturne |
|--------|-------------------|----------|
| Codebase | 35K LOC JS | 334K LOC C# |
| Plugins | 38 | Service-based |
| Connectors | Via bridges | 8 native |
| API Parity | v1/v2/v3 (origin) | v1/v2/v3 + v4 |
| Database | MongoDB | PostgreSQL |

#### Recommendation
Both should be maintained for ecosystem diversity. Nocturne viable for new deployments; migration requires testing.

---

### share2nightscout-bridge Audit (2026-01-28)

Complete audit of Dexcom Share → Nightscout bridge.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Deep Dive** | `docs/10-domain/share2nightscout-bridge-deep-dive.md` | 328 lines, full flow |

#### Key Findings

| Aspect | Details |
|--------|---------|
| **Scale** | 447 lines JavaScript, single file |
| **Dexcom API** | Auth + Login + Fetch (US/EU servers) |
| **Output** | Nightscout API v1 `/api/v1/entries.json` only |
| **Poll Interval** | 2.5 minutes default |
| **Trend Mapping** | 10 Dexcom trends → Nightscout directions |

#### Gaps Identified
- GAP-SHARE-001: No Nightscout API v3 support
- GAP-SHARE-002: No backfill/gap detection logic
- GAP-SHARE-003: Hardcoded application ID may break

---

### Nocturne Initial Audit (2026-01-28)

Complete architectural audit of Nocturne - .NET 10 rewrite of Nightscout.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Deep Dive** | `docs/10-domain/nocturne-deep-dive.md` | 279 lines, full architecture |

#### Key Findings

| Aspect | Details |
|--------|---------|
| **Scale** | 927 C# files, 438 Svelte components, ~334K LOC |
| **API Parity** | Full v1/v2/v3 compatibility confirmed |
| **Connectors** | 8 native (Dexcom, Libre, Glooko, MiniMed, MFP, NS, TConnect, Tidepool) |
| **Algorithm** | Native Rust oref with FFI/WASM support |
| **Frontend** | SvelteKit 2 + Svelte 5 + Tailwind CSS 4 |

#### Architecture Comparison

| cgm-remote-monitor | Nocturne |
|-------------------|----------|
| JavaScript/Node.js | C# .NET 10 |
| MongoDB | PostgreSQL |
| Socket.IO | SignalR |
| JS oref | Rust oref |

#### Gaps Identified
- GAP-NOCTURNE-001: V4 endpoints Nocturne-specific
- GAP-NOCTURNE-002: Rust oref may diverge from JS
- GAP-NOCTURNE-003: SignalR→Socket.IO bridge latency

---

### AAPS NSClient Schema Extraction (2026-01-28)

Documented complete Nightscout upload schema from AAPS NSClient SDK.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **NSClient Schema** | `mapping/aaps/nsclient-schema.md` | 70+ fields across 3 collections |
| **README Update** | `mapping/aaps/README.md` | Added to documentation index |

#### Key Findings

| Collection | Fields | Key Types |
|------------|--------|-----------|
| `treatments` | 50+ | Bolus, Carbs, TempBasal, ProfileSwitch, TempTarget |
| `entries` | 15 | SGV with direction, noise, filtered/unfiltered |
| `devicestatus` | 20+ | Pump, OpenAPS (suggested/enacted), Configuration |

#### EventType Enum (25 types)
Site management, CGM, Glucose, Bolus, Carbs, Targets, Profile, Basal, Notes

#### Unit Conventions Documented
- `duration`: minutes (Nightscout) vs milliseconds (AAPS internal)
- `utcOffset`: minutes
- `durationInMilliseconds`: AAPS-specific field

---

### Workspace Expansion (2026-01-28)

Added 4 new repositories from live backlog requests. Workspace now has 20 repos.

| Repo | URL | Branch | Purpose |
|------|-----|--------|---------|
| `nocturne` | nightscout/nocturne | main | Nightscout client app |
| `Trio-dev` | nightscout/Trio | dev | Trio development branch |
| `share2nightscout-bridge` | nightscout/share2nightscout-bridge | dev | Dexcom Share bridge |
| `cgm-remote-monitor-official` | nightscout/cgm-remote-monitor | dev | Official NS server |

---

### Cross-Project Test Harness Tooling (2026-01-28)

Implemented new tooling for cross-project integration testing and unit conversion validation.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Unit Conversion Tests** | `tools/test_conversions.py` | 20 test cases for time/glucose/insulin conversions |
| **Conversion Fixtures** | `conformance/unit-conversions/conversions.yaml` | GAP-TREAT validated conversions |
| **Mock Nightscout Server** | `tools/mock_nightscout.py` | In-memory API v1/v3 mock |
| **Makefile Targets** | `Makefile` | `make conversions`, `make mock-nightscout` |
| **Tooling Backlog** | `docs/sdqctl-proposals/backlogs/tooling.md` | Updated with harness roadmap |

#### Key Features

| Tool | Capability |
|------|------------|
| `test_conversions.py` | Validates time (s/ms/min), glucose (mg/dL↔mmol/L), insulin precision |
| `mock_nightscout.py` | POST/GET/PUT/DELETE for entries, treatments, devicestatus |

#### Conversions Tested

- Loop `absorptionTime` (seconds) → Nightscout (minutes)
- AAPS `duration` (milliseconds) → Nightscout (minutes)
- Glucose mg/dL ↔ mmol/L (factor: 18.0182)
- Insulin/carb precision preservation

---

### Timezone/DST Handling Deep Dive (2026-01-28)

Comprehensive cross-project analysis of timezone and DST handling across the Nightscout ecosystem. Documented how each system stores, interprets, and synchronizes timezone information.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Terminology Matrix Update** | `mapping/cross-project/terminology-matrix.md` | Expanded Timezone Handling section with 7 detailed tables |
| **New Gaps (4)** | `traceability/gaps.md` | GAP-TZ-004 through GAP-TZ-007 |

#### Key Findings

| System | TZ Storage | DST Aware | Key Issue |
|--------|-----------|-----------|-----------|
| **Nightscout** | IANA string in profile | ✅ Yes (moment-tz) | Recalculates utcOffset from dateString |
| **Loop** | `TimeZone` object (fixed offset) | ✅ Yes (Foundation) | Uses non-standard `ETC/GMT` format |
| **AAPS** | `utcOffset: Long` (ms) | ❌ No (fixed at capture) | Cannot reconstruct DST status historically |
| **Trio** | From NS profile | ✅ Yes (via NS) | Inherits NS timezone |
| **oref0** | Uses `moment-timezone` | ✅ Yes | N/A (no profile storage) |

#### Pump DST Support

| Status | Pumps |
|--------|-------|
| **✅ Can handle DST** | Medtrum, Combo v2 |
| **❌ Cannot handle DST** | Medtronic, Omnipod DASH/Eros, Dana RS/R, Equil |

#### New Gaps Documented

| Gap ID | Description |
|--------|-------------|
| **GAP-TZ-004** | utcOffset unit mismatch: Nightscout uses minutes, AAPS uses milliseconds |
| **GAP-TZ-005** | AAPS fixed offset storage breaks historical DST analysis |
| **GAP-TZ-006** | Loop uploads non-standard `ETC/GMT` timezone format (and NS workaround is buggy) |
| **GAP-TZ-007** | Missing timezone fallback uses server local time |

**Source Files Analyzed**:
- `externals/AndroidAPS/database/entities/interfaces/DBEntryWithTime.kt`
- `externals/AndroidAPS/core/data/pump/defs/TimeChangeType.kt`
- `externals/LoopWorkspace/LoopKit/LoopKit/DailyValueSchedule.swift`
- `externals/LoopWorkspace/RileyLinkKit/Common/TimeZone.swift`
- `externals/cgm-remote-monitor/lib/profilefunctions.js`
- `externals/cgm-remote-monitor/lib/api3/generic/collection.js`
- `externals/AndroidAPS/pump/medtrum/src/main/kotlin/.../SetTimeZonePacket.kt`

---

