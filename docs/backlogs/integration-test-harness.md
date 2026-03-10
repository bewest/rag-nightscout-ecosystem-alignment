# Integration Test Harness

> **Goal**: Run cgm-remote-monitor locally and test with Swift, Kotlin, and JavaScript clients to validate proposed fixes.
> **Server Location**: `/home/bewest/src/worktrees/nightscout/cgm-pr-8447`
> **Created**: 2026-03-10

## Overview

This document describes how to set up integration testing across all three client ecosystems (Loop/Swift, AAPS/Kotlin, JavaScript) against a local cgm-remote-monitor instance.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Integration Test Harness                         │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐                │
│  │   Swift      │   │   Kotlin     │   │  JavaScript  │                │
│  │   (Loop)     │   │   (AAPS)     │   │  (Native)    │                │
│  │              │   │              │   │              │                │
│  │ tools/swift- │   │ tools/kotlin-│   │ tests/*.js   │                │
│  │ nightscout-  │   │ nightscout-  │   │              │                │
│  │ tests/       │   │ tests/       │   │              │                │
│  └──────┬───────┘   └──────┬───────┘   └──────┬───────┘                │
│         │                  │                  │                         │
│         │    HTTP (localhost:1337)            │                         │
│         └──────────────────┼──────────────────┘                         │
│                            ▼                                            │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │              cgm-remote-monitor (cgm-pr-8447)                   │   │
│  │                                                                 │   │
│  │  Location: /home/bewest/src/worktrees/nightscout/cgm-pr-8447    │   │
│  │  Config:   my.test.env                                          │   │
│  │  Branch:   pr-8447 (UUID _id fix)                               │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                            │                                            │
│                            ▼                                            │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                        MongoDB                                  │   │
│  │              (test database, cleared between runs)              │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Server Setup

### Start cgm-remote-monitor Locally

```bash
cd /home/bewest/src/worktrees/nightscout/cgm-pr-8447

# Load test environment
source my.test.env

# Start server (foreground for debugging)
node server.js

# Or start in background
npm start &
```

### Test Environment Variables (my.test.env)

The actual `my.test.env` file in cgm-pr-8447:

```bash
# Required - must match your local MongoDB
API_SECRET=test_api_secret_12_chars
MONGO_CONNECTION=mongodb://localhost:27017/nightscout_test

# Required for HTTP testing (no SSL)
INSECURE_USE_HTTP=true

# Server binding
HOSTNAME=localhost
PORT=1337

# Optional - faster test failures
AUTH_FAIL_DELAY=50
```

**⚠️ INSECURE_USE_HTTP=true is required** - without it, the server redirects to HTTPS which breaks localhost testing.

### Verify Server Running

```bash
curl http://localhost:1337/api/v1/status.json
# Should return: {"status":"ok","version":"15.0.7-dev",...}
```

---

## Proposals Under Test

The integration tests validate these proposed fixes:

| Proposal | ID | Description | Primary Test | Status |
|----------|-----|-------------|--------------|--------|
| **Option G: Transparent Promotion** | REQ-SYNC-072 | UUID `_id` → `identifier` + server ObjectId | Loop override CRUD | ⭐ **Recommended** |
| Accept UUID _id | PR #8447 | Allow non-ObjectId _id values (as-is) | Loop override CRUD | Superseded by G |
| Identifier-First | REQ-SYNC-070 | Use `identifier` as primary key | All clients | Long-term |
| Server-Controlled ID | REQ-SYNC-071 | Server generates `_id`, client provides `identifier` | All clients | Long-term |

### Option G Summary

**Key insight**: Same code complexity as PR #8447, but keeps DB clean:

```
PR #8447 (Option A):    { "_id": "UUID-..." }        ← Mixed _id formats (permanent)
Option G:               { "_id": ObjectId, "identifier": "UUID-..." }  ← Clean!
```

**Implementation**:
1. On POST: If `_id` is non-ObjectId, move to `identifier` + generate ObjectId
2. On lookup: Check `identifier` first, then `_id`
3. On response: Return both fields

See [REQ-SYNC-072](../../traceability/sync-identity-requirements.md#req-sync-072-transparent-uuid-promotion-option-g) for full specification.

### Testing Matrix

| Scenario | Loop/Swift | AAPS/Kotlin | JS Native |
|----------|------------|-------------|-----------|
| POST with UUID `_id` | ✅ Critical | N/A | ✅ |
| POST with `identifier` | ⬜ | ✅ Critical | ✅ |
| PUT/DELETE by `_id` | ✅ Critical | ⬜ | ✅ |
| PUT/DELETE by `identifier` | ⬜ | ✅ | ✅ |
| Batch with response order | ✅ | ✅ | ✅ |
| Deduplication | ✅ | ✅ | ✅ |

---

## JavaScript Tests (Native)

**Location**: `/home/bewest/src/worktrees/nightscout/cgm-pr-8447/tests/`

### Run All Tests

```bash
cd /home/bewest/src/worktrees/nightscout/cgm-pr-8447
npm test
```

### Key Test Files

| File | Coverage |
|------|----------|
| `api.treatments.test.js:250-357` | UUID _id CRUD (Loop override) |
| `api.deduplication.test.js` | syncIdentifier, pumpId dedup |
| `api.partial-failures.test.js` | Response ordering |
| `api.v1-batch-operations.test.js` | Batch semantics |
| `api3.aaps-patterns.test.js` | AAPS v3 patterns |

### Run Specific Test

```bash
npm test -- --grep "UUID treatment ids"
```

---

## Swift Tests (Loop Simulation)

**Location**: `tools/swift-nightscout-tests/` (to be created)

### Setup

```bash
# Ensure Swift is available
export PATH="/home/bewest/.local/share/swiftly/bin:$PATH"
swift --version  # Should show 6.2.3

# Build and test
cd tools/swift-nightscout-tests
swift build
swift test
```

### Test Configuration

```swift
// Tests/Config.swift
struct TestConfig {
    static let nightscoutURL = "http://localhost:1337"
    static let apiSecret = "test-api-secret-12345"
}
```

### Key Tests to Implement

| Test | Simulates |
|------|-----------|
| `OverrideUploadTests` | Loop override with UUID _id |
| `CarbUploadTests` | Loop carb with syncIdentifier |
| `ObjectIdCacheTests` | Cache workflow |
| `BatchOrderingTests` | Response position mapping |

---

## Kotlin Tests (AAPS Simulation)

**Location**: `tools/kotlin-nightscout-tests/` (to be created) or `externals/AndroidAPS/`

### Option 1: Run Existing AAPS Tests

```bash
cd externals/AndroidAPS
./gradlew :plugins:sync:testDebugUnitTest
```

### Option 2: Create Standalone JVM Tests

```bash
cd tools/kotlin-nightscout-tests
./gradlew test
```

### Test Configuration

```kotlin
// src/test/kotlin/TestConfig.kt
object TestConfig {
    const val NIGHTSCOUT_URL = "http://localhost:1337"
    const val API_SECRET = "test-api-secret-12345"
}
```

### Key Tests to Implement

| Test | Simulates |
|------|-----------|
| `BolusUploadTest` | AAPS bolus with identifier |
| `TempTargetTest` | AAPS temp target (like Loop override) |
| `V3ApiTest` | identifier-based CRUD |
| `PumpIdCorrelationTest` | pumpId/pumpSerial handling |

---

## Test Workflow

### 1. Baseline (Current Behavior)

```bash
# Start server with current code (before any fix)
cd /home/bewest/src/worktrees/nightscout/cgm-pr-8447
git stash  # or checkout clean state
source my.test.env && npm test

# Document failures with UUID _id
```

### 2. Test Option G (Recommended)

```bash
# Create experimental branch for Option G
git checkout -b experiment/option-g

# Apply Option G changes (see REQ-SYNC-072):
# - normalizeTreatmentId: UUID → identifier + ObjectId
# - upsertQueryFor: check identifier first
# - indexedFields: add 'identifier'

# Run tests
npm test -- --grep "UUID"
# Expected: UUID _id CRUD works, _id is ObjectId in DB
```

### 3. Verify Option G Semantics

```bash
# Key verification points:
# 1. POST with UUID _id → stored _id is ObjectId, identifier = UUID
# 2. Re-POST same UUID → upsert (no duplicate)
# 3. Response includes both _id and identifier
# 4. DB inspection: db.treatments.find({identifier: /UUID/})
```

### 4. Test Alternative Proposals (if needed)

```bash
# Create experimental branch
git checkout -b experiment/identifier-first

# Apply changes per REQ-SYNC-071
# ... edit code ...

# Run all client tests
npm test
cd tools/swift-nightscout-tests && swift test
cd tools/kotlin-nightscout-tests && ./gradlew test
```

---

## Directory Structure

```
/home/bewest/src/
├── worktrees/nightscout/
│   └── cgm-pr-8447/              # Server under test
│       ├── my.test.env           # Test configuration
│       └── tests/                # JavaScript tests
│
├── rag-nightscout-ecosystem-alignment/
│   ├── tools/
│   │   ├── swift-nightscout-tests/    # Swift test package
│   │   │   ├── Package.swift
│   │   │   ├── Sources/
│   │   │   └── Tests/
│   │   │
│   │   └── kotlin-nightscout-tests/   # Kotlin test package
│   │       ├── build.gradle.kts
│   │       └── src/test/kotlin/
│   │
│   └── docs/backlogs/            # This documentation
│
└── externals/
    ├── LoopWorkspace/            # Loop source (reference)
    └── AndroidAPS/               # AAPS source (reference + tests)
```

---

## Work Items

### Infrastructure Setup

| ID | Task | Status |
|----|------|--------|
| `harness-server-setup` | Document server startup with my.test.env | ✅ This doc |
| `harness-swift-pkg` | Create tools/swift-nightscout-tests Package.swift | ✅ |
| `harness-kotlin-pkg` | Create tools/kotlin-nightscout-tests | ✅ |
| `harness-ci-script` | Script to run all three test suites | ✅ |

### Test Implementation

| ID | Language | Coverage | Status |
|----|----------|----------|--------|
| `test-js-uuid` | JavaScript | UUID _id CRUD | ✅ Exists |
| `test-js-identifier` | JavaScript | identifier field | ✅ |
| `test-swift-override` | Swift | Loop override flow | ✅ |
| `test-swift-cache` | Swift | ObjectIdCache workflow | ✅ |
| `test-kotlin-bolus` | Kotlin | AAPS bolus flow | ✅ |
| `test-kotlin-identifier` | Kotlin | v3 identifier CRUD | ✅ |

---

## Related Documents

- [Loop Upload Testing](loop-nightscout-upload-testing.md) - Loop-specific backlog
- [AAPS Upload Testing](aaps-nightscout-upload-testing.md) - AAPS-specific backlog
- [Swift Integration Proposal](swift-integration-testing-proposal.md) - Swift architecture
- [GAP-TREAT-012](../../traceability/treatments-gaps.md#gap-treat-012) - UUID _id issue
- [REQ-SYNC-070](../../traceability/sync-identity-requirements.md#req-sync-070) - Identifier-first
- [REQ-SYNC-071](../../traceability/sync-identity-requirements.md#req-sync-071) - Server-controlled ID
