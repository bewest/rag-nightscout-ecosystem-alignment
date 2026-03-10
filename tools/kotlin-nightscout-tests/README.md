# Kotlin Nightscout Integration Tests

Simulate AAPS's upload behavior against a local cgm-remote-monitor instance.

## Status: ✅ Working

**5 tests passing** - validates PR #8447 (Option G) behavior for AAPS patterns:
- `identifier` field preserved
- Server assigns ObjectId to `_id`
- Deduplication by `identifier`
- Pump correlation fields (`pumpId`, `pumpSerial`)
- Batch upload with order preservation

## Quick Start

```bash
# Start Nightscout server (if not running)
cd /home/bewest/src/worktrees/nightscout/cgm-pr-8447
export $(cat my.test.env | xargs) && node server.js &

# Run tests
cd tools/kotlin-nightscout-tests
./gradlew test
```

## Test Results

```
5 tests, 0 failures (0.259s)

- testPostBolusWithIdentifier: PASSED
- testReuploadBolusDeduplicates: PASSED
- testBolusWithPumpCorrelation: PASSED
- testTempTargetWithIdentifier: PASSED
- testBatchUploadWithIdentifiers: PASSED
```

## What These Tests Validate

| Test | AAPS Behavior | Server Behavior (Option G) |
|------|---------------|---------------------------|
| `testPostBolusWithIdentifier` | Sends `identifier` field | Preserved, ObjectId→`_id` |
| `testReuploadBolusDeduplicates` | Retries same `identifier` | Upserts via `identifier` match |
| `testBolusWithPumpCorrelation` | Includes pumpId/pumpSerial | All pump fields preserved |
| `testTempTargetWithIdentifier` | Temp Target (like override) | Works same as bolus |
| `testBatchUploadWithIdentifiers` | Batch with multiple identifiers | All preserved, order maintained |

## Configuration

Tests auto-connect to `http://localhost:1337` with secret `test_api_secret_12_chars`.

Override via environment:
```bash
export NIGHTSCOUT_URL="http://localhost:1337"
export API_SECRET="test_api_secret_12_chars"
```

## Related Documentation

- [Integration Test Harness](../../docs/backlogs/integration-test-harness.md)
- [REQ-SYNC-072](../../traceability/sync-identity-requirements.md#req-sync-072) - Option G spec
- [AAPS Upload Testing](../../docs/backlogs/aaps-nightscout-upload-testing.md)
