# Swift Nightscout Integration Tests

Simulate Loop's upload behavior against a local cgm-remote-monitor instance.

## ⚠️ IMPORTANT: Nightscout Server Available

**A Nightscout server is already set up and ready to use:**

```
Location: /home/bewest/src/worktrees/nightscout/cgm-pr-8447
```

**To start the server:**
```bash
cd /home/bewest/src/worktrees/nightscout/cgm-pr-8447
source my.test.env   # Sets INSECURE_USE_HTTP=true, API_SECRET, MONGO_CONNECTION
npm start            # Starts on localhost:1337
```

**Verify it's running:**
```bash
curl http://localhost:1337/api/v1/status.json
```

> ⚠️ **`INSECURE_USE_HTTP=true` is required** - without it, the server redirects to HTTPS which breaks localhost testing.

See [Integration Test Harness](../../docs/backlogs/integration-test-harness.md) for full setup details.

---

## Purpose

Test REQ-SYNC-072 (Server-Controlled ID) by faithfully reproducing how Loop uploads:
- Temporary Overrides (UUID as `_id`)
- Carbs (with `syncIdentifier`)
- Doses (with `syncIdentifier`)
- ObjectIdCache workflow

## Setup

```bash
# Ensure Swift is available
export PATH="/home/bewest/.local/share/swiftly/bin:$PATH"
swift --version  # Should show 6.x

# Build
swift build

# Test (requires cgm-remote-monitor running on localhost:1337)
swift test
```

## Configuration

Set environment variables or edit `Tests/TestConfig.swift`:

```bash
export NIGHTSCOUT_URL="http://localhost:1337"
export API_SECRET="test-api-secret-12345"
```

## Key Tests to Implement

| Test File | What It Simulates |
|-----------|-------------------|
| `OverrideUploadTests.swift` | Loop override with UUID `_id` |
| `CarbUploadTests.swift` | Loop carbs with `syncIdentifier` |
| `ObjectIdCacheTests.swift` | Cache hit/miss/expiry workflow |
| `BatchOrderingTests.swift` | Response position mapping |

## Related Documentation

- [Integration Test Harness](../../docs/backlogs/integration-test-harness.md)
- [Loop Source Analysis](../../docs/backlogs/loop-source-analysis.md)
- [REQ-SYNC-072](../../traceability/sync-identity-requirements.md#req-sync-072)
- [Swift Integration Proposal](../../docs/backlogs/swift-integration-testing-proposal.md)

## Directory Structure

```
swift-nightscout-tests/
├── Package.swift           # SPM manifest
├── Sources/
│   └── NightscoutTestKit/
│       ├── NightscoutClient.swift    # HTTP client wrapper
│       ├── ObjectIdCache.swift       # Extracted from LoopKit
│       └── Models/                   # Treatment models
└── Tests/
    └── NightscoutTestKitTests/
        ├── TestConfig.swift          # Server URL, API secret
        ├── OverrideUploadTests.swift # UUID _id workflow
        └── CarbUploadTests.swift     # syncIdentifier workflow
```
