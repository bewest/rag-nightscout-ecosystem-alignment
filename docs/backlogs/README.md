# Backlogs

Active work streams for the Nightscout ecosystem alignment project.

## Active Backlogs

| Backlog | Focus | Work Items | Status |
|---------|-------|------------|--------|
| [Loop Upload Testing](loop-nightscout-upload-testing.md) | Test cgm-remote-monitor with faithful Loop simulation | 50 | 🟡 In Progress |
| [Loop Source Analysis](loop-source-analysis.md) | Understand Loop's upload code | 7 | ⬜ Ready |
| [Swift Integration Testing](swift-integration-testing-proposal.md) | Use real Swift code for tests | Proposal | 📋 Planning |

---

## Quick Reference: Ready Work Items

Work items with no blockers that can be started immediately:

### Loop Source Analysis (Priority: HIGH)

These must complete before test development:

| ID | Task | File |
|----|------|------|
| `loop-src-override` | Analyze OverrideTreament.swift | `NightscoutServiceKit/Extensions/OverrideTreament.swift` |
| `loop-src-carb` | Analyze SyncCarbObject.swift | `NightscoutServiceKit/Extensions/SyncCarbObject.swift` |
| `loop-src-cache` | Analyze ObjectIdCache.swift | `NightscoutServiceKit/ObjectIdCache.swift` |
| `loop-src-uploader` | Analyze NightscoutUploader.swift | `NightscoutServiceKit/Extensions/NightscoutUploader.swift` |

### Swift Test Setup (Priority: MEDIUM)

Can be done in parallel with source analysis:

| ID | Task | Deliverable |
|----|------|-------------|
| `swift-pkg-setup` | Create Swift test package | `tools/swift-nightscout-tests/Package.swift` |

### Infrastructure (Priority: LOW)

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
