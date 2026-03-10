# Kotlin Nightscout Integration Tests

Simulate AAPS's upload behavior against a local cgm-remote-monitor instance.

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

Test REQ-SYNC-072 (Server-Controlled ID) by faithfully reproducing how AAPS uploads:
- Bolus with `identifier` field
- Temp Targets (similar to Loop overrides)
- Pump events with `pumpId`/`pumpSerial`

## Setup

```bash
# Option 1: Use Gradle wrapper (if available)
./gradlew test

# Option 2: Use system Gradle
gradle test

# Requires cgm-remote-monitor running on localhost:1337
```

## Configuration

Set environment variables or edit `src/test/kotlin/TestConfig.kt`:

```bash
export NIGHTSCOUT_URL="http://localhost:1337"
export API_SECRET="test-api-secret-12345"
```

## Key Tests to Implement

| Test File | What It Simulates |
|-----------|-------------------|
| `BolusUploadTest.kt` | AAPS bolus with `identifier` |
| `TempTargetTest.kt` | AAPS temp target |
| `PumpIdCorrelationTest.kt` | `pumpId` + `pumpSerial` handling |
| `V3ApiTest.kt` | AAPS v3 SDK patterns |

## Related Documentation

- [Integration Test Harness](../../docs/backlogs/integration-test-harness.md)
- [AAPS Upload Testing](../../docs/backlogs/aaps-nightscout-upload-testing.md)
- [REQ-SYNC-072](../../traceability/sync-identity-requirements.md#req-sync-072)

## Directory Structure

```
kotlin-nightscout-tests/
├── build.gradle.kts           # Gradle build config
├── settings.gradle.kts        # Project settings
├── src/
│   ├── main/kotlin/
│   │   └── NightscoutClient.kt    # HTTP client wrapper
│   └── test/kotlin/
│       ├── TestConfig.kt          # Server URL, API secret
│       ├── BolusUploadTest.kt     # identifier workflow
│       └── TempTargetTest.kt      # Similar to Loop override
```

## Comparison to AAPS Source

Key AAPS files to reference:
- `externals/AndroidAPS/plugins/sync/src/main/kotlin/app/aaps/plugins/sync/nsclientV3/extensions/BolusExtension.kt`
- `externals/AndroidAPS/core/interfaces/src/main/kotlin/app/aaps/core/interfaces/nsclient/IDs.kt`
