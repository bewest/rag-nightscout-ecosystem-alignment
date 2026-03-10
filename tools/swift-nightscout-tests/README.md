# Swift Nightscout Integration Tests

Simulate Loop's upload behavior against a local cgm-remote-monitor instance.

## Status: ✅ Working

**5 tests passing** - validates PR #8447 (Option G) behavior:
- UUID `_id` promoted to `identifier`
- Server assigns ObjectId to `_id`
- Deduplication by `identifier`
- Batch upload with order preservation
- ObjectIdCache workflow

## Quick Start

```bash
# Start Nightscout server (if not running)
cd /home/bewest/src/worktrees/nightscout/cgm-pr-8447
export $(cat my.test.env | xargs) && node server.js &

# Run tests
cd tools/swift-nightscout-tests
swift test
```

## Test Results

```
Test Case 'OverrideUploadTests.testPostOverrideWithUUID' passed
Test Case 'OverrideUploadTests.testReuploadOverrideDeduplicates' passed
Test Case 'OverrideUploadTests.testDeleteOverrideByObjectId' passed
Test Case 'OverrideUploadTests.testBatchUploadWithUUIDs' passed
Test Case 'OverrideUploadTests.testObjectIdCacheWorkflow' passed
```

## What These Tests Validate

| Test | Loop Behavior | Server Behavior (Option G) |
|------|---------------|---------------------------|
| `testPostOverrideWithUUID` | Sends UUID as `_id` | UUID→`identifier`, ObjectId→`_id` |
| `testReuploadOverrideDeduplicates` | Re-sends same UUID | Upserts via `identifier` match |
| `testDeleteOverrideByObjectId` | Deletes using cached ObjectId | Standard delete by `_id` |
| `testBatchUploadWithUUIDs` | Batch with multiple UUIDs | All promoted, order preserved |
| `testObjectIdCacheWorkflow` | Caches ObjectId for updates | ObjectId works for subsequent ops |

## Configuration

Tests auto-connect to `http://localhost:1337` with secret `test_api_secret_12_chars`.

Override via environment:
```bash
export NIGHTSCOUT_URL="http://localhost:1337"
export API_SECRET="test_api_secret_12_chars"
```

## Server Setup

```bash
cd /home/bewest/src/worktrees/nightscout/cgm-pr-8447
source my.test.env   # Sets INSECURE_USE_HTTP=true
npm start            # Starts on localhost:1337
```

## Related Documentation

- [Integration Test Harness](../../docs/backlogs/integration-test-harness.md)
- [REQ-SYNC-072](../../traceability/sync-identity-requirements.md#req-sync-072) - Option G spec
- [Loop Source Analysis](../../docs/backlogs/loop-source-analysis.md)
