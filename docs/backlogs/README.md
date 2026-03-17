# Backlogs

Active work streams for the Nightscout ecosystem alignment project.

## ✅ P0: Test Database Safety (GAP-SYNC-046) - COMPLETE

**Status**: All safety checks implemented with hard failure.

[GAP-SYNC-046](../../traceability/sync-identity-gaps.md#gap-sync-046-test-suite-lacks-production-database-safeguards) | [Phase 5 Details](./pr-8421-review-analysis.md#phase-5-test-database-safety-p0p1-)

| ID | Task | Priority | Status |
|----|------|----------|--------|
| SAFETY-001 | Mandate `NODE_ENV=test` for test runs | 🔴 P0 | ✅ `tests/hooks.js` - hard `process.exit(1)` |
| SAFETY-002 | Update `ci.test.env` to `NODE_ENV=test` | 🔴 P0 | ✅ Fixed (was `production`!) |
| SAFETY-003 | Create `guardDestructiveOperation()` | 🟠 P1 | ✅ `tests/fixtures/test-guard.js` |
| SAFETY-004 | Hard fail if NODE_ENV !== 'test' | 🟠 P1 | ✅ Implemented in `e12cf3d2` |

**Worktree**: `/home/bewest/src/worktrees/nightscout/cgm-pr-8447`

**Commits**:
- `61501cac` - feat(tests): add NODE_ENV=test safety check (warn + guard module)
- `e12cf3d2` - fix(tests): make NODE_ENV=test check a hard failure
- `ee3e6af7` - ci: temporarily allow Node 20 for branch protection (tests [20, 22, 24])
- `b76fb3e1` - test: remove completed MongoDB 5.x array investigation tests

**Tests**: 729 passing, 1 pending, 0 failing

---

## ✅ P0: PR #8421 Reviewer's Guide - COMPLETE

**Status**: All 27 claims verified, 11 undocumented changes discovered.

[PR #8421](https://github.com/nightscout/cgm-remote-monitor/pull/8421) | [Reviewer's Guide](../PR-8421-reviewers-guide.md) | [Analysis Backlog](./pr-8421-review-analysis.md)

| Theme | Status |
|-------|--------|
| 1. UUID Handling | ✅ 3/3 verified |
| 2. Backwards Compat | ✅ 3/3 verified |
| 3. MongoDB 5.x | ✅ 3/3 verified |
| 4. Test Coverage | ✅ 4/4 verified |
| 5. Documentation | ✅ 1/1 verified |
| 6. Undocumented Changes | ✅ 11 discovered |
| 7. Test DB Safety | ✅ Pre-existing (GAP-SYNC-046) |

---

## ✅ P0: Fix Issue #8450 (Loop Override Sync)

**Status**: PR #8447 ready for review - all 657 tests pass.

[GitHub Issue #8450](https://github.com/nightscout/cgm-remote-monitor/issues/8450) | [PR #8447](https://github.com/nightscout/cgm-remote-monitor/pull/8447)

| Task | Status | Location |
|------|--------|----------|
| **UUID `_id` handling** | ✅ Implemented | `lib/server/treatments.js` |
| **Tests** | ✅ 657 passing | `tests/api.treatments.test.js` |
| Specification | ✅ Complete | [REQ-SYNC-072](../../traceability/sync-identity-requirements.md#req-sync-072) |
| Strategy comparison | ✅ Complete | [GAP-TREAT-012](../../traceability/treatments-gaps.md#gap-treat-012) |

**What PR #8447 does**:
- `normalizeTreatmentId()`: Only converts 24-hex to ObjectId, leaves UUIDs as strings
- `upsertQueryFor()`: Uses `_id` when provided (including UUID), falls back to `created_at + eventType`
- POST/PUT/DELETE all work with Loop's UUID `_id` values

**Follow-up (Optional)**: REQ-SYNC-072 (Option G) promotes UUID to `identifier` field for cleaner long-term design.

---

## ⚠️ Nightscout Server Available

**A cgm-remote-monitor server is ready for testing:**

| | |
|---|---|
| **Location** | `/home/bewest/src/worktrees/nightscout/cgm-pr-8447` |
| **URL** | `http://localhost:1337` |
| **Start** | See commands below |

**Start the server:**
```bash
cd /home/bewest/src/worktrees/nightscout/cgm-pr-8447
source my.test.env   # Sets INSECURE_USE_HTTP, API_SECRET, MONGO_CONNECTION
npm start
```

**Required environment** (`my.test.env` contents):
```
API_SECRET=test_api_secret_12_chars
MONGO_CONNECTION=mongodb://localhost:27017/nightscout_test
INSECURE_USE_HTTP=true   # Required for localhost testing without SSL
PORT=1337
```

**Verify running:**
```bash
curl http://localhost:1337/api/v1/status.json
```

---

## 🎯 Start Here: Integration Test Harness

**[integration-test-harness.md](integration-test-harness.md)** - Central document for running cgm-remote-monitor locally and testing with Swift, Kotlin, and JavaScript clients.

```
Swift (Loop) ──┐
               │
Kotlin (AAPS) ─┼──▶ cgm-pr-8447 (localhost:1337) ──▶ MongoDB
               │
JavaScript ────┘
```

**Proposals Under Test**: [REQ-SYNC-072](../../traceability/sync-identity-requirements.md#req-sync-072-transparent-uuid-promotion-option-g) (Option G - **Recommended**), [REQ-SYNC-070](../../traceability/sync-identity-requirements.md#req-sync-070) (Identifier-First), [REQ-SYNC-071](../../traceability/sync-identity-requirements.md#req-sync-071) (Server-Controlled ID)

---

## Active Backlogs

### AID Client Testing

| Backlog | Client | Language | Work Items | Status |
|---------|--------|----------|------------|--------|
| [Loop Upload Testing](loop-nightscout-upload-testing.md) | Loop (iOS) | Swift | 50 | ✅ Complete |
| [Loop Source Analysis](loop-source-analysis.md) | Loop | Swift | 7 | ✅ Complete |
| [AAPS Upload Testing](aaps-nightscout-upload-testing.md) | AAPS (Android) | Kotlin | 39 | ✅ Complete |
| [Trio Entries Testing](trio-entries-upload-testing.md) | Trio (iOS) | Swift | 10 | ✅ Complete |

### Integration Testing Proposals

| Proposal | Approach | Tooling | Status |
|----------|----------|---------|--------|
| [Swift Integration](swift-integration-testing-proposal.md) | Use Loop's Swift code | Swift 6.2 + SPM | 📋 Planning |
| [Kotlin Integration](aaps-nightscout-upload-testing.md#phase-4-kotlinandroid-testing-options) | Use AAPS's Kotlin code | Gradle + JVM | 📋 Planning |

### Test Reliability

| Backlog | Issue | Priority | Status |
|---------|-------|----------|--------|
| [Insulin Rounding Epsilon](insulin-rounding-epsilon-analysis.md) | `+epsilon` for floor() FP artifacts | 🟢 P2 | ✅ Complete (correct) |
| [BWP Test Timing](bwp-test-timing-determinism.md) | `Date.now()` causes flaky test | 🟠 P1 | 📋 Ready |

---

## Quick Reference: Ready Work Items

### ✅ P0: Implement Option G Fix

| ID | Task | Status |
|----|------|--------|
| `impl-option-g` | Implement REQ-SYNC-072 in treatments.js | ✅ Complete |
| `test-option-g` | Verify with existing tests | ✅ 16 tests passing |

### ✅ P1: Entries UUID Fix (GAP-SYNC-045) - **COMPLETE**

Trio uploads CGM entries with UUID `_id` values. Fix implemented matching treatments.js pattern.

**All phases complete (2026-03-11):**

| ID | Task | Status |
|----|------|--------|
| `test-entry-dedup-001` | Baseline: sysTime+type dedup test | ✅ Passing |
| `test-entry-dedup-002` | Baseline: different type at same time | ✅ Passing |
| `test-entry-dedup-003` | Baseline: different time same type | ✅ Passing |
| `test-entry-uuid-001` | POST entry with UUID _id | ✅ Passing |
| `test-entry-uuid-002` | Re-POST deduplication | ✅ Passing |
| `test-entry-uuid-003` | Different UUID same timestamp | ✅ Passing |
| `test-entry-uuid-004` | Batch upload mixed IDs | ✅ Passing |
| `test-entry-uuid-005` | Existing UUID entry updated | ✅ Passing |
| `test-entry-uuid-006` | Identifier field preserved | ✅ Passing |
| `impl-entry-normalize` | Implement `normalizeEntryId()` in entries.js | ✅ Complete |

**Implementation**: `lib/server/entries.js` now has `normalizeEntryId()` and `upsertQueryFor()` functions that:
- Extract UUID from `_id` to `identifier` field
- Strip non-ObjectId `_id` before `$set` to avoid MongoDB immutable field error
- Maintain sysTime+type dedup as primary key for CGM data integrity

**Details**: [trio-entries-upload-testing.md](trio-entries-upload-testing.md)  
**API Comparison**: [api-version-uuid-comparison.md](api-version-uuid-comparison.md) ← v1 vs v3 analysis  
**Gap**: [GAP-SYNC-045](../../traceability/sync-identity-gaps.md#gap-sync-045-trio-entries-upload-uses-uuid-as-_id)  
**Deep Dive**: [client-id-handling-deep-dive.md](../10-domain/client-id-handling-deep-dive.md)

### ✅ P1: Loop Source Analysis - COMPLETE

All Loop source files analyzed - see [loop-source-analysis.md](loop-source-analysis.md).

| ID | Task | Status |
|----|------|--------|
| `loop-src-override` | OverrideTreament.swift | ✅ LOOP-SRC-010 |
| `loop-src-carb` | SyncCarbObject.swift | ✅ LOOP-SRC-011 |
| `loop-src-cache` | ObjectIdCache.swift | ✅ LOOP-SRC-003 |
| `loop-src-uploader` | NightscoutUploader.swift | ✅ LOOP-SRC-002 |
| `loop-src-glucose` | StoredGlucoseSample.swift | ✅ LOOP-SRC-013 |
| `loop-src-devicestatus` | StoredDosingDecision.swift | ✅ LOOP-SRC-014 |

### ✅ v3 API: No Changes Needed

**Status**: v3 API already handles client identifiers correctly.

| Aspect | Status | Evidence |
|--------|--------|----------|
| Client `_id` handling | ✅ Ignored | `resolveIdentifier()` computes fresh |
| Dedup by identifier | ✅ Works | `identifyingFilter()` with fallback |
| Entries fallback | ✅ `['date', 'type']` | Matches v1's `sysTime + type` |
| Test coverage | ✅ Tested | `api3.create.test.js`, `api3.aaps-patterns.test.js` |

**Details**: [api-version-uuid-comparison.md](api-version-uuid-comparison.md)

**Note**: Trio currently uses v1 API (`/api/v1/entries.json`). If Trio switched to v3, no server fix would be needed. However, the v1 fix is simpler than client changes.

### ✅ P1: AAPS Source Analysis - COMPLETE

All source files analyzed - see [aaps-nightscout-upload-testing.md](aaps-nightscout-upload-testing.md).

| ID | Task | Status |
|----|------|--------|
| `aaps-src-ids` | IDs.kt | ✅ AAPS-SRC-004 |
| `aaps-src-bolus` | BolusExtension.kt | ✅ AAPS-SRC-010 |
| `aaps-src-carbs` | CarbsExtension.kt | ✅ AAPS-SRC-011 |
| `aaps-src-tempbasal` | TemporaryBasalExtension.kt | ✅ AAPS-SRC-012 |
| `aaps-src-tt` | TemporaryTargetExtension.kt | ✅ AAPS-SRC-013 |
| `aaps-src-profile` | ProfileSwitchExtension.kt | ✅ AAPS-SRC-014 |
| `aaps-src-devicestatus` | DeviceStatusExtension.kt | ✅ AAPS-SRC-015 |
| `aaps-src-glucose` | GlucoseValueExtension.kt | ✅ AAPS-SRC-016 |
| `aaps-src-therapy` | TherapyEventExtension.kt | ✅ AAPS-SRC-017 |
| `aaps-src-sdk` | NSAndroidClient | ✅ AAPS-SRC-001/002 |
| `aaps-run-tests` | Run AAPS tests | ⚠️ Requires Android SDK |

### ✅ P2: Swift/Kotlin Test Setup - COMPLETE

| ID | Task | Deliverable |
|----|------|-------------|
| `swift-pkg-setup` | Create Swift test package | ✅ 7 tests passing |
| `kotlin-pkg-setup` | Create Kotlin test package | ✅ BUILD SUCCESSFUL |

### ✅ P3: Infrastructure - COMPLETE

| ID | Task | Status |
|----|------|--------|
| `lock-update` | Update workspace.lock.json with minimed-connect-to-nightscout | ✅ Already present |

---

## Blocked Work Items

These require prior work to complete:

| ID | Blocked By | Unblocks |
|----|------------|----------|
| ~~`loop-test-identity-matrix`~~ | ~~loop-src-override, loop-src-carb, loop-src-cache~~ | ✅ Test development |
| ~~`loop-test-cache-workflow`~~ | ~~loop-src-cache, loop-src-carb~~ | ✅ Complete (source analysis done) |
| ~~`swift-extract-cache`~~ | ~~swift-pkg-setup~~ | ✅ Complete (`ObjectIdCache` in tests) |
| ~~`swift-http-client`~~ | ~~swift-pkg-setup~~ | ✅ Complete (`NightscoutClient` class) |
| ~~`swift-first-test`~~ | ~~swift-extract-cache, swift-http-client~~ | ✅ Complete (7 tests passing) |
| `coordinate-merge` | review-pr8357 | v15.0.7 release |

---

## Context Documents

### Issue Being Addressed

- **GitHub Issue**: [nightscout/cgm-remote-monitor#8450](https://github.com/nightscout/cgm-remote-monitor/issues/8450)
- **Fix PR**: [#8447](https://github.com/nightscout/cgm-remote-monitor/pull/8447) (treatments only)

### Gap Documentation

- [GAP-TREAT-012](../../traceability/treatments-gaps.md#gap-treat-012-v1-api-incorrectly-coerces-uuid-_id-to-objectid) - UUID _id coercion issue (treatments) ✅ Fixed
- [GAP-SYNC-045](../../traceability/sync-identity-gaps.md#gap-sync-045-trio-entries-upload-uses-uuid-as-_id) - UUID _id coercion issue (entries) ✅ Fixed
- [GAP-SYNC-005](../../traceability/sync-identity-gaps.md#gap-sync-005-loop-objectidcache-not-persistent) - ObjectIdCache not persistent
- [Client ID Handling Deep Dive](../10-domain/client-id-handling-deep-dive.md) - Comprehensive analysis

### Proposals

- [REQ-SYNC-070](../../traceability/sync-identity-requirements.md#req-sync-070-identifier-first-architecture) - Identifier-first architecture
- [REQ-SYNC-071](../../traceability/sync-identity-requirements.md#req-sync-071-server-controlled-id-with-client-identity-preservation) - Server-controlled ID (recommended)

### Existing Analysis

- [Loop Sync Identity Fields](../../mapping/loop/sync-identity-fields.md) - Detailed Loop field documentation
- [AAPS Nightscout Sync](../../mapping/aaps/nightscout-sync.md) - AAPS comparison

---

## Worktrees

Test environment at `/home/bewest/src/worktrees/nightscout/`:

| Worktree | Branch | Purpose |
|----------|--------|---------|
| `cgm-pr-8447` | pr-8447 | Test UUID _id fix |
| `cgm-dev-node22` | official/dev | Node 22 testing |
| `cgm-dev-node20` | official/dev | Baseline testing |

---

## How to Contribute

1. Pick a ready work item from the tables above
2. Read the corresponding backlog document for details
3. Update status when starting/completing work
4. Document findings in the appropriate location:
   - Source analysis → `mapping/loop/`
   - Tests → `worktrees/nightscout/cgm-pr-8447/tests/`
   - Proposals → `traceability/`

---

## Last Updated

2026-03-17
