# CGM Remote Monitor Documentation Inventory

**Generated:** 2026-01-18  
**Source:** `externals/cgm-remote-monitor/docs/`  
**Branch:** `wip/replit/with-mongodb-update`

---

## Summary (Verified Counts from Repository Scan)

| Category | Count |
|----------|-------|
| Total Documentation Files | 35 |
| Index Files | 1 |
| Audits | 7 |
| Meta Documents | 3 |
| Requirements | 3 |
| Test Specs | 3 |
| Proposals | 9 |
| Data Schemas | 2 |
| Scripts | 1 (513 lines) |
| Test Files | 88 |
| API Test Files | 15 |

---

## Documentation Structure

> **Note:** This inventory lists files found in the cgm-remote-monitor repository. Line counts are verified from file scans.

### Index (Navigation Hub) - 1 file
- `docs/INDEX.md` - Central navigation for all documentation (75 lines)

### Audits (System Analysis) - 7 files
- `docs/audits/api-layer-audit.md` - REST endpoints (v1, v2, v3)
- `docs/audits/data-layer-audit.md` - MongoDB collections and storage
- `docs/audits/security-audit.md` - Authentication, authorization
- `docs/audits/realtime-systems-audit.md` - Socket.IO, WebSocket
- `docs/audits/messaging-subsystem-audit.md` - Notifications, alerts
- `docs/audits/plugin-architecture-audit.md` - Plugin system design
- `docs/audits/dashboard-ui-audit.md` - Frontend components

### Meta (Project-Level) - 3 files
- `docs/meta/architecture-overview.md` - System design and components
- `docs/meta/modernization-roadmap.md` - Future direction
- `docs/meta/DOCUMENTATION-PROGRESS.md` - Documentation status

### Requirements - 3 files
- `docs/requirements/data-shape-requirements.md` - Input/output handling
- `docs/requirements/authorization-security-requirements.md` - Auth system
- `docs/requirements/api-v1-compatibility-requirements.md` - Client compatibility

### Test Specifications - 3 files
- `docs/test-specs/shape-handling-tests.md` - Array/object normalization
- `docs/test-specs/authorization-tests.md` - Security and auth
- `docs/test-specs/coverage-gaps.md` - Aggregated test gaps

### Proposals (RFC-Style) - 9 files
- `docs/proposals/mongodb-modernization-implementation-plan.md` - Driver upgrade plan (940 lines)
- `docs/proposals/websocket-array-deduplication-issue.md` - Root cause analysis (262 lines)
- `docs/proposals/oidc-actor-identity-proposal.md` - Actor identity proposal
- `docs/proposals/agent-control-plane-rfc.md` - AI agent collaboration
- `docs/proposals/testing-modernization-proposal.md` - Test framework updates
- `docs/proposals/api-query-normalization.md` - Query handling
- `docs/proposals/bridge-rules.md` - Integration rules
- `docs/proposals/conflict-resolution.md` - Conflict handling
- `docs/proposals/integration-questionnaire.md` - Integration guide

*Note: `docs/proposals/schemas/` is a subdirectory, not counted above.*

### Data Schemas - 2 files
- `docs/data-schemas/treatments-schema.md` - Treatment collection fields
- `docs/data-schemas/profiles-schema.md` - Profile structure

---

## New Test Files (MongoDB Modernization)

> **Note:** Line counts are verified from file scans. Test descriptions are from file contents.

### Client Pattern Test Files (Verified Line Counts)
- `tests/api.deduplication.test.js` - 398 lines
  - AAPS pumpId+pumpType+pumpSerial deduplication
  - Loop syncIdentifier deduplication
  - Trio id field deduplication
  - Cross-client duplicate isolation

- `tests/api.partial-failures.test.js` - 456 lines
  - Batch with duplicate key handling
  - Response ordering preservation
  - Client-provided _id handling
  - Write result format translation
  - Large batch processing

- `tests/api.aaps-client.test.js` - 375 lines
  - SGV entry with AAPS device metadata
  - SMB (Super Micro Bolus) format
  - Meal Bolus with carbs
  - Temp Basal with duration/rate
  - Pump metadata preservation
  - Boolean flags (isValid, isSMB)
  - utcOffset timezone handling

**Total new test code:** 1,229 lines (verified)

### Related Existing Test Files
- `tests/websocket.shape-handling.test.js` - Referenced in deduplication analysis
- `tests/api3.aaps-patterns.test.js` - AAPS v3 API patterns

---

## Scripts (New Tooling)

> **Source:** Script existence and line counts verified from file scans. Feature descriptions observed from script file contents.

### Flaky Test Detection
- `scripts/flaky-test-runner.js` - 513 lines (verified)
  - Multiple iteration test runner (observed from code)
  - JSON result capture (observed from code)
  - Markdown report generation (observed from code)
  - Pass/fail rate analysis (observed from code)
  - Automatic flaky test identification (observed from code)

---

## Test Fixtures

> **Source:** Fixture file existence verified from file scans. Descriptions observed from file contents.

### Client Pattern Fixtures
- `tests/fixtures/aaps-single-doc.js` - AAPS v3 API patterns (observed from file)
- `tests/fixtures/loop-batch.js` - Loop v1 batch operations (observed from file)
- `tests/fixtures/trio-pipeline.js` - Trio throttled pipelines (observed from file)
- `tests/fixtures/deduplication.js` - All deduplication scenarios (observed from file)
- `tests/fixtures/edge-cases.js` - Edge cases and validation (observed from file)
- `tests/fixtures/partial-failures.js` - Batch failures and response ordering (observed from file)
- `tests/fixtures/index.js` - Unified export (observed from file)

---

## Cross-References

> **Source:** All mappings in this section are derived from `mongodb-modernization-implementation-plan.md`. Status claims are team-reported, not independently verified.

### Requirements → Tests Mapping (per `mongodb-modernization-implementation-plan.md`)

| Requirement | Test File | Team-Reported Status |
|-------------|-----------|----------------------|
| Loop response ordering | `api.partial-failures.test.js` | Reported passing |
| AAPS deduplication | `api.deduplication.test.js` | Reported passing |
| Loop syncIdentifier | `api.deduplication.test.js` | Reported passing |
| Trio id field | `api.deduplication.test.js` | Reported passing |
| v1 API format | `api.partial-failures.test.js` | Reported passing |
| Cross-client isolation | `api.deduplication.test.js` | Reported passing |

### Client → Deduplication Key Mapping (per `mongodb-modernization-implementation-plan.md`)

| Client | Deduplication Key | Field Location |
|--------|-------------------|----------------|
| AAPS (treatments) | pumpId + pumpType + pumpSerial | treatments collection |
| AAPS (entries) | date + device + type | entries collection |
| Loop | syncIdentifier | treatments collection |
| Trio | id | treatments collection |

---

## MongoDB Modernization Progress

> **Source:** This section excerpts the team's plan from `mongodb-modernization-implementation-plan.md`. Status claims are team-reported, not independently verified.

### Phase 1: Test Infrastructure
**Team-reported status:** Complete (per `mongodb-modernization-implementation-plan.md`)
- Review existing fixtures
- Create comprehensive test suite
- Establish baseline (29/30 reported passing)
- Document critical behaviors

### Phase 2: Storage Layer Analysis
**Team-reported status:** Next (per `mongodb-modernization-implementation-plan.md`)
- Audit current MongoDB usage
- Map all insert operations
- Identify v1 vs v3 API data flow

### Phase 3: Core Implementation
**Team-reported status:** Planned (per `mongodb-modernization-implementation-plan.md`)
- Create write result translator
- Update lib/server/treatments.js
- Update lib/server/entries.js
- Add response format middleware

### Phase 4: Testing & Validation
**Team-reported status:** Planned (per `mongodb-modernization-implementation-plan.md`)
- Run new test suites
- Client pattern validation
- Integration testing
