# Swift Integration Testing Proposal

> **Goal**: Use Loop's actual Swift code to test cgm-remote-monitor, ensuring faithful simulation
> **Created**: 2026-03-10

## Rationale

### Current Approach (JavaScript Tests)
```
Loop uploads → [Simulated in JS] → cgm-remote-monitor
                    ↑
            We guess what Loop sends
```

### Proposed Approach (Swift Integration)
```
Loop's actual Swift code → HTTP → cgm-remote-monitor (test instance)
                    ↑
            Uses real NightscoutServiceKit
```

**Key Benefit**: If Loop's code changes, our tests automatically use the new behavior.

---

## Feasibility Assessment

### ✅ Available Resources

| Resource | Status |
|----------|--------|
| Swift 6.2.3 | Installed via Swiftly |
| LoopWorkspace | Cloned in externals/ |
| NightscoutServiceKit source | Available |
| Existing Loop tests | 5 XCTest files |
| cgm-remote-monitor | Available for local testing |

### ⚠️ Challenges

| Challenge | Mitigation |
|-----------|------------|
| SPM package incomplete | Create minimal package for testing |
| iOS platform target | Use Linux-compatible subset |
| LoopKit dependencies | Mock or extract needed types |
| Network mocking | Point at real local Nightscout |

---

## Architecture Options

### Option A: Extract Upload Code (Recommended)

Create minimal Swift package with just the upload code:

```
tools/swift-nightscout-tests/
├── Package.swift
├── Sources/
│   └── LoopNightscoutClient/
│       ├── NightscoutUploader.swift      # Extracted from Loop
│       ├── ObjectIdCache.swift           # Extracted from Loop
│       ├── TreatmentPayloads.swift       # JSON serialization
│       └── Models/
│           ├── OverrideTreatment.swift
│           ├── CarbTreatment.swift
│           └── DoseTreatment.swift
└── Tests/
    └── IntegrationTests/
        ├── OverrideUploadTests.swift
        ├── CarbUploadTests.swift
        ├── ObjectIdCacheTests.swift
        └── TestNightscoutServer.swift    # Manages test NS instance
```

**Pros**: Clean, focused, no iOS dependencies
**Cons**: Manual extraction, may drift from Loop

### Option B: Full LoopKit Dependency

Use LoopKit as SPM dependency with test-only targets:

```swift
// Package.swift
dependencies: [
    .package(path: "../externals/LoopWorkspace/LoopKit")
],
targets: [
    .testTarget(
        name: "NightscoutIntegrationTests",
        dependencies: ["LoopKit"]
    )
]
```

**Pros**: Uses actual Loop code
**Cons**: iOS dependencies, complex setup

### Option C: Hybrid - Symlink Source Files

Symlink the specific Swift files we need:

```
tools/swift-nightscout-tests/
├── Package.swift
├── Sources/
│   └── LoopNightscoutClient/
│       ├── ObjectIdCache.swift → externals/.../ObjectIdCache.swift
│       ├── OverrideTreament.swift → externals/.../OverrideTreament.swift
│       └── SyncCarbObject.swift → externals/.../SyncCarbObject.swift
```

**Pros**: Always current with Loop code
**Cons**: May break if dependencies change

---

## Test Architecture

### Integration Test Flow

```
┌─────────────────┐     ┌─────────────────────┐     ┌────────────────────┐
│  Swift Test     │────▶│  cgm-remote-monitor │────▶│     MongoDB        │
│                 │     │  (localhost:1337)   │     │  (test database)   │
│ Uses Loop's     │◀────│                     │◀────│                    │
│ actual upload   │     │  Real API handling  │     │  Real storage      │
│ code            │     │                     │     │                    │
└─────────────────┘     └─────────────────────┘     └────────────────────┘
```

### Test Lifecycle

```swift
class NightscoutIntegrationTests: XCTestCase {
    var nightscoutProcess: Process?
    var mongoProcess: Process?
    
    override func setUpWithError() throws {
        // 1. Start MongoDB (or use existing)
        // 2. Start cgm-remote-monitor with test config
        // 3. Wait for server ready
    }
    
    override func tearDownWithError() throws {
        // 1. Clear test collections
        // 2. Stop servers if started
    }
    
    func testOverrideUploadWithUUID() async throws {
        // Uses Loop's actual OverrideTreatment.asNightscoutTreatment()
        let override = TemporaryScheduleOverride(...)
        let treatment = override.asNightscoutTreatment()
        
        // Upload using Loop's actual uploader
        let uploader = NightscoutUploader(siteURL: testURL, apiSecret: testSecret)
        let objectId = try await uploader.uploadTreatment(treatment)
        
        // Verify
        XCTAssertNotNil(objectId)
        
        // Verify we can update/delete with the returned ID
        try await uploader.deleteTreatment(id: objectId)
    }
}
```

---

## Implementation Plan

### Phase 1: Minimal Extraction (1-2 days)

1. Create `tools/swift-nightscout-tests/` package
2. Extract `ObjectIdCache.swift` (no dependencies)
3. Extract treatment JSON serialization
4. Create basic HTTP client (URLSession)
5. One working test: POST override with UUID _id

### Phase 2: Full Upload Coverage (2-3 days)

1. Extract all treatment types
2. Implement ObjectIdCache tests
3. Implement batch upload tests
4. Test response ordering

### Phase 3: Integration Harness (1-2 days)

1. Script to start/stop cgm-remote-monitor
2. Test database setup/teardown
3. CI integration

---

## Test Scenarios to Implement

### Override Tests (GAP-TREAT-012)

| Test | Description |
|------|-------------|
| `testOverrideCreateWithUUID` | POST override with UUID _id |
| `testOverrideUpdateWithUUID` | PUT override with same UUID _id |
| `testOverrideDeleteWithUUID` | DELETE override by UUID _id |
| `testOverrideUpsertSameId` | POST same _id twice |
| `testOverrideCancelIndefinite` | DELETE indefinite override |

### ObjectIdCache Tests

| Test | Description |
|------|-------------|
| `testCacheMappingAfterCreate` | POST → cache stores syncId→objectId |
| `testCachedIdUsedForUpdate` | PUT uses cached objectId |
| `testCacheExpiryBehavior` | Simulate 24hr expiry |
| `testCacheMissRecovery` | POST existing syncId after cache cleared |

### Batch Tests

| Test | Description |
|------|-------------|
| `testBatchResponseOrder` | N items → N responses in order |
| `testBatchWithDuplicates` | Dedup returns existing ID |
| `testLargeBatch1000` | Max batch size |

---

## Required Dependencies

### Swift Package Dependencies

```swift
dependencies: [
    // HTTP client
    .package(url: "https://github.com/swift-server/async-http-client.git", from: "1.0.0"),
    // JSON
    .package(url: "https://github.com/apple/swift-foundation.git", from: "0.1.0")
]
```

Or use Foundation's URLSession (simpler, cross-platform in Swift 6).

---

## Decision Points

1. **Option A vs B vs C** - Which extraction approach?
2. **MongoDB** - Use existing or start fresh per test?
3. **cgm-remote-monitor** - Start per test or keep running?
4. **CI** - Run on GitHub Actions?

---

## Next Steps

- [ ] Create minimal Package.swift
- [ ] Extract ObjectIdCache.swift (test it compiles on Linux)
- [ ] Create HTTP client wrapper
- [ ] First passing test: POST treatment, verify response

---

## Related

- [loop-nightscout-upload-testing.md](loop-nightscout-upload-testing.md) - Main backlog
- [GAP-TREAT-012](../../traceability/treatments-gaps.md#gap-treat-012) - UUID _id issue
- [REQ-SYNC-071](../../traceability/sync-identity-requirements.md#req-sync-071) - Server-controlled ID proposal
