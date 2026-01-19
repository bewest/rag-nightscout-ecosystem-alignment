# CGM Remote Monitor Analysis - January 18, 2026

**Document Version:** 1.2  
**Last Updated:** 2026-01-19  
**Branch Analyzed:** `wip/replit/with-mongodb-update`  
**Source:** Shallow clone from `https://github.com/bewest/cgm-remote-monitor-1.git`

---

## Executive Summary

> **Attribution Notice:** This analysis summarizes claims from the cgm-remote-monitor repository's documentation files. Test pass rates and behavioral validations are reported by the team in their `mongodb-modernization-implementation-plan.md` document and have not been independently verified.

The cgm-remote-monitor team reports significant progress on **Phase 1 of MongoDB Modernization** per their documentation. Key items found in their repository:

1. **Test Infrastructure** - 3 new test files with 1,229 lines of test code (line count verified)
2. **Client Pattern Testing** - Team documents testing of AAPS, Loop, and Trio deduplication patterns
3. **Flaky Test Detection Tooling** - New `scripts/flaky-test-runner.js` (513 lines verified)
4. **Documentation Restructuring** - Reorganized into taxonomic structure with centralized `docs/INDEX.md`
5. **WebSocket Analysis** - `websocket-array-deduplication-issue.md` documents team's analysis

### January 19, 2026 Update

**Test Stability Verification Complete:** Comprehensive stress testing performed across 19 key test files shows **100% pass rate** with no flaky behavior detected. Key improvements since January 18:

1. **Flaky Test Fixes** - Three critical fixes applied (floating-point precision, boot optimization, timeout improvements)
2. **MongoDB Pool Optimization** - Test environment uses `MONGO_POOL_SIZE=2` for determinism
3. **Timing Instrumentation** - New test helper module with anti-pattern detection
4. **Test Infrastructure Improvements** - Prediction array truncation (288 elements default)

---

## Test Coverage Analysis

> **Source:** Test file existence and line counts are verified from file scans. Test pass rates and behavior claims are from `mongodb-modernization-implementation-plan.md`.

### New Test Files Created (Verified Line Counts)

| Test File | Lines | Focus |
|-----------|-------|-------|
| `api.partial-failures.test.js` | 456 | Batch failures, response ordering, v1 API format |
| `api.deduplication.test.js` | 398 | AAPS/Loop/Trio deduplication patterns |
| `api.aaps-client.test.js` | 375 | AAPS-specific document formats and metadata |
| **Total** | **1,229** | |

### Test Results Summary (From Team's Documentation)

**Reported Status:** 29/30 PASSING (96.7%) - *per mongodb-modernization-implementation-plan.md*

*Note: These results are from the cgm-remote-monitor team's documentation, not independently verified by this analysis.*

**Critical Behaviors Documented as Tested** (per `mongodb-modernization-implementation-plan.md`):
- Loop response ordering (response[i] matches request[i])
- AAPS pumpId+pumpType+pumpSerial deduplication
- Loop syncIdentifier deduplication
- Trio id field deduplication
- Cross-client duplicate isolation
- v1 API response format (`[{_id, ok: 1, n: 1}, ...]`)
- Batch with deduplicated items returns correct IDs
- Client-provided _id handling

**Reported Known Issue** (per team documentation):
- 1 test reportedly times out (large devicestatus with 500+ prediction values)
- Team attributes this to infrastructure, not code

---

## Documentation Restructuring

> **Source:** Directory structure observed from file system scan of `externals/cgm-remote-monitor/docs/`. File counts are verified.

### New Directory Structure

```
docs/
├── INDEX.md                    # Central navigation hub (75 lines)
├── audits/                     # System analysis docs (7 files)
│   ├── api-layer-audit.md
│   ├── data-layer-audit.md
│   ├── security-audit.md
│   ├── realtime-systems-audit.md
│   ├── messaging-subsystem-audit.md
│   ├── plugin-architecture-audit.md
│   └── dashboard-ui-audit.md
├── meta/                       # Project-level docs (3 files)
│   ├── architecture-overview.md
│   ├── modernization-roadmap.md
│   └── DOCUMENTATION-PROGRESS.md
├── requirements/               # Formal requirements (3 files)
│   ├── data-shape-requirements.md
│   ├── authorization-security-requirements.md
│   └── api-v1-compatibility-requirements.md
├── test-specs/                 # Test specifications (4 files)
│   ├── shape-handling-tests.md
│   ├── authorization-tests.md
│   ├── coverage-gaps.md
│   └── flaky-tests.md
├── data-schemas/               # Collection documentation (2 files)
│   ├── treatments-schema.md
│   └── profiles-schema.md
└── proposals/                  # RFC-style proposals (9 files)
    ├── mongodb-modernization-implementation-plan.md  # 940 lines
    ├── websocket-array-deduplication-issue.md        # 262 lines
    ├── oidc-actor-identity-proposal.md
    ├── agent-control-plane-rfc.md
    ├── testing-modernization-proposal.md
    └── (+ 4 more)
```

### Documentation Taxonomy (observed from repository structure)

| Folder | Purpose | When to Use |
|--------|---------|-------------|
| `audits/` | System analysis and current state | Understanding existing architecture |
| `meta/` | Project-level navigation | High-level orientation, roadmaps |
| `requirements/` | Formal requirements specifications | Defining correctness criteria |
| `test-specs/` | Test specifications with tracking | Writing tests, tracking coverage |
| `proposals/` | RFC-style proposals | Proposing changes, reviewing designs |
| `data-schemas/` | Collection field documentation | Understanding data structures |

---

## Flaky Test Detection Tooling

> **Source:** Script existence and line count verified from file scan. Feature descriptions observed from file contents.

### New Script: `scripts/flaky-test-runner.js`

**Purpose:** Run tests multiple times to identify inconsistent test behavior

**Features** (observed from script code):
- Configurable iterations (default 10, quick mode 3, thorough mode 25)
- JSON result capture with robust parsing
- Markdown report generation
- Pass/fail rate analysis per test
- Automatic flaky test identification

**Usage:**
```bash
npm run test:flaky          # Standard mode (10 iterations)
npm run test:flaky:quick    # Quick mode (3 iterations)
npm run test:flaky:thorough # Thorough mode (25 iterations)
```

**Output:**
- `flaky-test-results/flaky-test-report-<timestamp>.md` - Human-readable report
- `flaky-test-results/flaky-test-data-<timestamp>.json` - Raw data
- `flaky-test-results/iteration-N-results.json` - Per-iteration results

---

## Test Stability Improvements (January 19, 2026)

> **Source:** This section is based on direct observation of `docs/test-specs/flaky-tests.md` and related test infrastructure files.

### Stress Test Results

**Overall Status:** ✅ **TESTS STABLE - VERIFICATION COMPLETE**

Comprehensive stress testing was performed across 19 key test files. All completed runs showed 100% pass rates with no flaky behavior detected.

| Test File | Iterations | Pass Rate | Status |
|-----------|------------|-----------|--------|
| api.entries.test.js | 3 | 100% | ✅ Stable |
| api3.socket.test.js | 3 | 100% | ✅ Stable |
| api.partial-failures.test.js | 3 | 100% | ✅ Stable |
| api.deduplication.test.js | 5 | 100% | ✅ Fixed |
| api3.renderer.test.js | 3 | 100% | ✅ Stable |
| boluswizardpreview.test.js | 3 | 100% | ✅ Stable |
| api.treatments.test.js | 5 | 100% | ✅ Stable |
| api3.create.test.js | 5 | 100% | ✅ Stable |
| api.aaps-client.test.js | 5 | 100% | ✅ Stable |
| api.v1-batch-operations.test.js | 5 | 100% | ✅ Stable |
| websocket.shape-handling.test.js | 5 | 100% | ✅ Stable |
| concurrent-writes.test.js | 5 | 100% | ✅ Stable |
| security.test.js | 5 | 100% | ✅ Stable |
| storage.shape-handling.test.js | 5 | 100% | ✅ Stable |
| verifyauth.test.js | 5 | 100% | ✅ Stable |
| api3.security.test.js | 5 | 100% | ✅ Stable |
| api3.generic.workflow.test.js | 3 | 100% | ✅ Stable |
| api.devicestatus.test.js | 3 | 100% | ✅ Stable |
| api.shape-handling.test.js | 5 | 100% | ✅ Fixed (boot optimization) |

### Flaky Test Fixes Applied

#### Fix 1: boluswizardpreview.test.js - Floating-Point Precision (January 19, 2026)

**Problem:** Test `set a pill to the BWP with infos` intermittently failed, expecting `'0.50U'` but receiving `'0.51U'`.

**Root Cause:** The `roundInsulinForDisplayFormat()` function used `Math.floor(insulin / 0.01) * 0.01`. Floating-point precision errors caused values like `0.50499999...` to sometimes produce either `0.50` or `0.51` non-deterministically.

**Fix Applied:** Added epsilon (`1e-9`) before floor operation: `Math.floor(insulin * 100 + 1e-9) / 100`

#### Fix 2: api.shape-handling.test.js - Boot Optimization (January 19, 2026)

**Problem:** Test file was slow (~80s boot overhead) and occasionally timed out during stress testing.

**Root Cause:** Used `beforeEach()` for server boot, causing 26 boots (one per test) at 2-3 seconds each.

**Fix Applied:** Changed `beforeEach()` to `before()` for one-time server boot; kept data cleanup in nested `beforeEach()` hooks.

**Result:** Test execution time reduced from ~80s to ~6s (172ms/test avg) - **93% improvement**

#### Fix 3: api.deduplication.test.js - Timeout and Cleanup (January 2026)

**Problem:** Test `duplicate entry with same date+device+type is detected` intermittently timed out.

**Root Cause:** Server boot overhead (~20s on first test) plus slow database cleanup.

**Fix Applied:** 
- Increased timeout from 15000ms to 30000ms
- Changed entries cleanup to use `deleteMany({})` for faster full-collection purge
- Added devicestatus cleanup to reduce database load

### MongoDB Pool Optimization

**Configuration Changes:**
- Test environment: `MONGO_POOL_SIZE=2` (configured in `my.test.env`)
- Production default: `5` for headroom
- Pool size 1 caused timeouts due to request queuing on concurrent operations
- Pool size 2 is minimum that handles `concurrent-writes.test.js` (5 parallel requests)

### Timing Instrumentation

New test helper module `tests/lib/test-helpers.js` provides:

| Function | Description |
|----------|-------------|
| `waitForConditionWithWarning(options)` | Callback-based polling with warnings |
| `waitForConditionAsync(options)` | Promise-based polling with warnings |
| `instrumentedSetTimeout(fn, delay, context)` | setTimeout wrapper with logging |
| `trackedDelay(ms, reason)` | Promise delay with timing logs |
| `enableSetTimeoutWarnings(options)` | Enable global setTimeout monitoring |

**Anti-pattern Detection:** Tests can now detect `setTimeout` calls with delays ≥100ms that may cause flakiness.

---

## WebSocket Array Deduplication Issue

> **Source:** This section summarizes the team's analysis from `websocket-array-deduplication-issue.md`.

### Summary (per team documentation)

According to the team's analysis, when an array of treatments is sent via WebSocket `dbAdd`, items 2+ may be deduplicated against item 1 due to the 2-second deduplication window.

### Root Cause (per team documentation)

Per the team's analysis, the deduplication logic uses a 2-second window for similar treatments. When processing arrays sequentially:
1. Item 1: Inserted successfully
2. Item 2: Matches Item 1 (same eventType, within 2s) → Deduplicated
3. Item 3: Matches Item 1 (same eventType, within 2s) → Deduplicated

### Team's Resolution (per `websocket-array-deduplication-issue.md`)

The cgm-remote-monitor team's analysis concludes this is expected behavior:
- Deduplication prevents duplicate uploads from clients
- 2-second window accounts for clock drift and retry logic
- Real clients use unique identifiers (NSCLIENT_ID, syncIdentifier, id)
- Test scenario was artificial (same eventType within 2 seconds)

### Team's Impact Assessment

Per the team's documentation, this behavior is unrelated to MongoDB driver version.

---

## MongoDB Modernization Status

> **Source:** All status and phase information in this section is from `mongodb-modernization-implementation-plan.md`.

### Phase 1: Test Infrastructure & Baseline
**Team-reported status:** Complete (per `mongodb-modernization-implementation-plan.md`)
- All fixtures created (AAPS, Loop, Trio, deduplication, edge cases)
- Comprehensive test suite (29/30 passing)
- Baseline established
- Critical behaviors documented

### Phase 2: Storage Layer Analysis
**Team-reported status:** Next (per `mongodb-modernization-implementation-plan.md`)
- Audit current MongoDB usage
- Map insert operations
- Identify v1 vs v3 API data flow differences

### Write Result Format Compatibility

> **Source:** Observed from `mongodb-modernization-implementation-plan.md`

**Critical for driver upgrade:**

| Format | MongoDB Driver 3.x | MongoDB Driver 4.x+ |
|--------|-------------------|---------------------|
| insertedIds | `{ '0': id1, '1': id2 }` | `[id1, id2]` |

**v1 API Expected Format:**
```javascript
[{ _id: 'id1', ok: 1, n: 1 }, { _id: 'id2', ok: 1, n: 1 }]
```

Per team documentation, API layer must translate driver response to v1 expected format.

---

## Client Deduplication Patterns

> **Source:** These patterns are documented in `mongodb-modernization-implementation-plan.md` and test file contents.

### AAPS (AndroidAPS) - per team documentation
- **Treatments:** `pumpId + pumpType + pumpSerial`
- **Entries:** `date + device + type`
- **Metadata:** Must preserve `isValid`, `isSMB`, `pumpId`, `pumpType`, `pumpSerial`

### Loop - per team documentation
- **Deduplication:** `syncIdentifier` (UUID)
- **Response Ordering:** Team describes as critical - array index must match request index
- **Batch Behavior:** Expects N responses for N requests

### Trio - per team documentation
- **Deduplication:** `id` field (UUID, separate from MongoDB `_id`)
- **Field Isolation:** `id` must not interfere with MongoDB `_id`

---

## Recommendations

### Recommended Next Steps (per team documentation)
1. Continue with Phase 2 (Storage Layer Analysis)
2. Monitor large document performance in production
3. Consider adding unique constraint on client deduplication fields

### Suggested Documentation Actions (from `websocket-array-deduplication-issue.md`)
The team's documentation suggests:
- Update test to use unique identifiers (NSCLIENT_ID)
- Rename WebSocket test to reflect actual behavior
- Add explicit deduplication test

### Future Work (per team's `mongodb-modernization-implementation-plan.md`)
- Phase 3: Core Implementation (Write Result Translator)
- Phase 4: Testing & Validation with real client patterns
- Phase 5: Driver Upgrade Execution

---

## Modernization Roadmap Summary

> **Source:** This section summarizes the 5-phase modernization plan from `docs/meta/modernization-roadmap.md`.

The cgm-remote-monitor team has documented a comprehensive modernization roadmap addressing technical debt and architecture improvements.

### Phase Overview

| Phase | Focus | Effort | Complexity |
|-------|-------|--------|------------|
| **Phase 1** | Security Foundation | Low-Medium | Straightforward |
| **Phase 2** | Developer Experience | High | Moderate to Complicated |
| **Phase 3** | Performance & UX | Medium | Moderate |
| **Phase 4** | Architecture Improvements | High | Complicated |
| **Phase 5** | UI Modernization | Very High | Complicated |

### Technical Debt Inventory

**Critical Debt (Immediate Action Required):**

| Item | Location | Risk |
|------|----------|------|
| Deprecated `request` library | Multiple files | Security |
| No input validation | API endpoints | Security |
| No rate limiting | Server | DoS vulnerability |
| Outdated Node.js support | package.json | Security |

**High Priority Debt:**

| Item | Location | Impact |
|------|----------|--------|
| Callback-based async code | Throughout | Maintainability |
| No TypeScript | Throughout | Developer velocity |
| Global state (ctx object) | Server code | Testability |
| jQuery dependency | Client | Bundle size, modernization |

### Key Modernization Strategies

1. **OIDC/OAuth2 Plugin** - External identity federation via nightscout-roles-gateway
2. **Database Migration System** - migrate-mongo for proper schema migrations
3. **Event-Driven Refactoring** - Typed EventEmitter replacing Stream-based bus
4. **Strangler Fig Pattern** - Gradual migration of subsystems
5. **Feature Flags** - Safe rollout of new functionality

---

## Coverage Gaps (Prioritized)

> **Source:** This section summarizes `docs/test-specs/coverage-gaps.md`.

### High Priority Gaps (Security/Data Critical)

| Area | Gap | Recommended Action |
|------|-----|-------------------|
| Authorization | WebSocket Auth (`/storage` subscription) | Add socket.io-client tests for subscribe with/without token |
| Authorization | JWT Expiration rejection | Create JWT with past exp, verify 401 |
| Authorization | Permission Wildcards (Shiro patterns) | Test `api:*:read` vs `api:entries:read` |
| Authorization | API v3 Security model | Create separate API v3 security spec |

### Medium Priority Gaps

| Area | Gap | Recommended Action |
|------|-----|-------------------|
| Shape Handling | Response order matches input order | Add order verification tests |
| Shape Handling | WebSocket + API concurrent writes | Complex test setup needed |
| Shape Handling | Duplicate identifier handling under load | Stress test harness needed |
| Shape Handling | Cross-API consistency (v1 vs v3 storage) | Cross-read verification tests |
| Authorization | Subject CRUD operations | Add API tests for admin endpoints |
| Authorization | Role Management | Test role creation and permission assignment |

### Low Priority Gaps

| Area | Gap | Recommended Action |
|------|-----|-------------------|
| Shape Handling | Null/undefined in array handling | Define expected behavior, add tests |
| Authorization | Audit Events | Mock bus, verify admin-notify event |
| Authorization | Delay Cleanup | Fast-forward time, verify cleanup |

### Areas Not Yet Documented

| Area | Source Audit | Priority |
|------|--------------|----------|
| API v3 Security | `security-audit.md` | High |
| Core Calculations (IOB/COB) | `plugin-architecture-audit.md` | High |
| Real-time Event Bus | `realtime-systems-audit.md` | Medium |
| Plugin System | `plugin-architecture-audit.md` | Medium |
| Notification/Messaging | `messaging-subsystem-audit.md` | Medium |
| Dashboard UI | `dashboard-ui-audit.md` | Low (may be rewritten) |

---

## Repository Statistics

> **Source:** All counts in this section are verified from file system scans.

| Metric | Count |
|--------|-------|
| Total documentation files | 36 |
| Audit documents | 7 |
| Proposals | 9 |
| Total test files | 88 |
| API test files | 15 |
| New client pattern test files | 3 |
| New lines of test code | 1,229 |
| Flaky test runner script | 513 lines |
| Test helper module | `tests/lib/test-helpers.js` |
| Test specs (new) | 4 files |

---

## Related Documents

- `externals/cgm-remote-monitor/docs/proposals/mongodb-modernization-implementation-plan.md`
- `externals/cgm-remote-monitor/docs/proposals/websocket-array-deduplication-issue.md`
- `externals/cgm-remote-monitor/docs/meta/modernization-roadmap.md`
- `externals/cgm-remote-monitor/docs/meta/DOCUMENTATION-PROGRESS.md`
- `externals/cgm-remote-monitor/docs/test-specs/flaky-tests.md`
- `externals/cgm-remote-monitor/docs/test-specs/coverage-gaps.md`
- `externals/cgm-remote-monitor/docs/INDEX.md`
- `externals/cgm-remote-monitor/scripts/flaky-test-runner.js`
- `externals/cgm-remote-monitor/tests/lib/test-helpers.js`
