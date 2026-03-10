# Backlogs

Active work streams for the Nightscout ecosystem alignment project.

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
| **Start** | `cd /home/bewest/src/worktrees/nightscout/cgm-pr-8447 && source my.test.env && npm start` |

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
| [Loop Upload Testing](loop-nightscout-upload-testing.md) | Loop (iOS) | Swift | 50 | 🟡 In Progress |
| [Loop Source Analysis](loop-source-analysis.md) | Loop | Swift | 7 | ⬜ Ready |
| [AAPS Upload Testing](aaps-nightscout-upload-testing.md) | AAPS (Android) | Kotlin | 39 | ⬜ Ready |

### Integration Testing Proposals

| Proposal | Approach | Tooling | Status |
|----------|----------|---------|--------|
| [Swift Integration](swift-integration-testing-proposal.md) | Use Loop's Swift code | Swift 6.2 + SPM | 📋 Planning |
| [Kotlin Integration](aaps-nightscout-upload-testing.md#phase-4-kotlinandroid-testing-options) | Use AAPS's Kotlin code | Gradle + JVM | 📋 Planning |

---

## Quick Reference: Ready Work Items

### 🔴 P0: Implement Option G Fix

| ID | Task | Priority |
|----|------|----------|
| `impl-option-g` | Implement REQ-SYNC-072 in treatments.js | **P0** |
| `test-option-g` | Verify with existing tests | **P0** |

### 🟠 P1: Loop Source Analysis

These must complete before test development:

| ID | Task | File |
|----|------|------|
| `loop-src-override` | Analyze OverrideTreament.swift | `NightscoutServiceKit/Extensions/OverrideTreament.swift` |
| `loop-src-carb` | Analyze SyncCarbObject.swift | `NightscoutServiceKit/Extensions/SyncCarbObject.swift` |
| `loop-src-cache` | Analyze ObjectIdCache.swift | `NightscoutServiceKit/ObjectIdCache.swift` |
| `loop-src-uploader` | Analyze NightscoutUploader.swift | `NightscoutServiceKit/Extensions/NightscoutUploader.swift` |

### 🟠 P1: AAPS Source Analysis

Can run in parallel with Loop analysis:

| ID | Task | File |
|----|------|------|
| `aaps-src-ids` | Analyze IDs.kt | `core/data/model/IDs.kt` |
| `aaps-src-bolus` | Analyze BolusExtension.kt | `nsclientV3/extensions/BolusExtension.kt` |
| `aaps-src-sdk` | Analyze NSAndroidClient | `core/nssdk/interfaces/NSAndroidClient.kt` |
| `aaps-run-tests` | Run existing AAPS tests | `./gradlew :plugins:sync:test` |

### 🟡 P2: Swift/Kotlin Test Setup

| ID | Task | Deliverable |
|----|------|-------------|
| `swift-pkg-setup` | Create Swift test package | ✅ `tools/swift-nightscout-tests/` |
| `kotlin-pkg-setup` | Create Kotlin test package | ✅ `tools/kotlin-nightscout-tests/` |

### 🟢 P3: Infrastructure

| ID | Task |
|----|------|
| `lock-update` | Update workspace.lock.json with minimed-connect-to-nightscout |

---

## Blocked Work Items

These require prior work to complete:

| ID | Blocked By | Unblocks |
|----|------------|----------|
| `loop-test-identity-matrix` | loop-src-override, loop-src-carb, loop-src-cache | Test development |
| `loop-test-cache-workflow` | loop-src-cache, loop-src-carb | JS tests in cgm-pr-8447 |
| `swift-extract-cache` | swift-pkg-setup | swift-first-test |
| `swift-http-client` | swift-pkg-setup | swift-first-test |
| `swift-first-test` | swift-extract-cache, swift-http-client | Full Swift test suite |
| `coordinate-merge` | review-pr8357 | v15.0.7 release |

---

## Context Documents

### Issue Being Addressed

- **GitHub Issue**: [nightscout/cgm-remote-monitor#8450](https://github.com/nightscout/cgm-remote-monitor/issues/8450)
- **Fix PR**: [#8447](https://github.com/nightscout/cgm-remote-monitor/pull/8447)

### Gap Documentation

- [GAP-TREAT-012](../../traceability/treatments-gaps.md#gap-treat-012-v1-api-incorrectly-coerces-uuid-_id-to-objectid) - UUID _id coercion issue
- [GAP-SYNC-005](../../traceability/sync-identity-gaps.md#gap-sync-005-loop-objectidcache-not-persistent) - ObjectIdCache not persistent

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

2026-03-10
