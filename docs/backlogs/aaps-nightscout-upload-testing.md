# AAPS → Nightscout Upload Testing Backlog

> **Goal**: Develop comprehensive tests for cgm-remote-monitor that faithfully simulate all ways AAPS uploads data to Nightscout.
> **Test Location**: `/home/bewest/src/worktrees/nightscout/cgm-pr-8447/tests/`
> **Created**: 2026-03-10

## IDs.kt Analysis (AAPS-SRC-004, AAPS-ID-001)

### Key Finding: AAPS Uses Server-Assigned IDs (Opposite of Loop)

**File**: `core/data/model/IDs.kt`

```kotlin
data class IDs(
    var nightscoutSystemId: String? = null,  // System-level ID
    var nightscoutId: String? = null,        // Server-assigned _id (stored after upload)
    var pumpType: PumpType? = null,          // Pump model enum
    var pumpSerial: String? = null,          // Pump serial number
    var temporaryId: Long? = null,           // Temp ID before sync
    var pumpId: Long? = null,                // Pump event sequence number
    var startId: Long? = null,               // Extended bolus start
    var endId: Long? = null                  // Extended bolus end
)
```

### Identity Field Flow

```
AAPS Local          →  Nightscout API v3    →  AAPS Response Handler
─────────────────────────────────────────────────────────────────────
pumpId + pumpSerial    identifier (optional)    nightscoutId = response._id
                       pumpId, pumpType,
                       pumpSerial (sent)
```

### BolusExtension.kt Mapping (line 26-41)

```kotlin
fun BS.toNSBolus(): NSBolus =
    NSBolus(
        identifier = ids.nightscoutId,      // Previously assigned server ID
        pumpId = ids.pumpId,                // Pump event number
        pumpType = ids.pumpType?.name,      // "OMNIPOD_DASH", "DANA_I", etc.
        pumpSerial = ids.pumpSerial,        // Unique pump serial
        ...
    )
```

### AAPS vs Loop Identity Pattern Comparison

| Aspect | AAPS | Loop |
|--------|------|------|
| **Who assigns `_id`** | Server | Client (UUID) |
| **Local storage** | `nightscoutId` in Room DB | `ObjectIdCache` (24hr memory) |
| **Dedup key** | `pumpId + pumpType + pumpSerial` | `syncIdentifier` |
| **API version** | v3 (REST with `identifier`) | v1 (POST only) |
| **GAP-TREAT-012 impact** | ❌ Not affected | ✅ Overrides affected |

### Why AAPS Doesn't Trigger GAP-TREAT-012

1. **Create**: `identifier: null` - server generates ObjectId `_id`
2. **Response**: AAPS stores `_id` as `nightscoutId` in Room DB
3. **Update**: Sends `identifier: nightscoutId` (valid ObjectId)
4. **Delete**: Uses `identifier` (valid ObjectId)

AAPS never sends client-generated UUID as `_id`.

---

## BolusExtension.kt Analysis (AAPS-SRC-010)

### Bolus JSON Mapping

**File**: `plugins/sync/.../nsclientV3/extensions/BolusExtension.kt`

```kotlin
fun BS.toNSBolus(): NSBolus =
    NSBolus(
        eventType = if (type == BS.Type.SMB) EventType.CORRECTION_BOLUS 
                    else EventType.MEAL_BOLUS,
        isValid = isValid,
        date = timestamp,
        insulin = amount,
        type = type.toBolusType(),          // NORMAL, SMB, PRIMING
        notes = notes,
        isBasalInsulin = isBasalInsulin,
        identifier = ids.nightscoutId,      // Server ObjectId (from previous response)
        pumpId = ids.pumpId,                // Pump sequence number
        pumpType = ids.pumpType?.name,      // "DANA_I", "OMNIPOD_DASH", etc.
        pumpSerial = ids.pumpSerial,        // Unique pump serial
        endId = ids.endId                   // Extended bolus end marker
    )
```

### Existing Test Coverage (BolusExtensionKtTest.kt)

```kotlin
bolus = BS(
    timestamp = 10000,
    amount = 1.0,
    type = BS.Type.SMB,
    ids = IDs(
        nightscoutId = "nightscoutId",    // Server-assigned ObjectId
        pumpId = 11000,                    // Pump event number
        pumpType = PumpType.DANA_I,
        pumpSerial = "bbbb"
    )
)
// Round-trip test: toNSBolus() → convertToRemoteAndBack() → toBolus()
assertThat(bolus.contentEqualsTo(bolus2)).isTrue()
```

### Deduplication: pumpId + pumpType + pumpSerial

AAPS uses pump event correlation for dedup:
- **pumpId**: Sequential event number from pump history
- **pumpType**: Pump model enum (DANA_I, OMNIPOD_DASH, etc.)
- **pumpSerial**: Unique pump serial number

This triple uniquely identifies a pump event across reinstalls/resets.

---

## CarbsExtension.kt Analysis (AAPS-SRC-011) ✅

**File**: `plugins/sync/src/main/kotlin/app/aaps/plugins/sync/nsclientV3/extensions/CarbsExtension.kt`

### JSON Mapping

```kotlin
fun CA.toNSCarbs(): NSCarbs =
    NSCarbs(
        eventType = if (amount < 12) EventType.CARBS_CORRECTION else EventType.MEAL_BOLUS,
        isValid = isValid,
        date = timestamp,
        utcOffset = T.msecs(utcOffset).mins(),
        carbs = amount,
        notes = notes,
        duration = if (duration != 0L) duration else null,
        identifier = ids.nightscoutId,    // Server-assigned ObjectId
        pumpId = ids.pumpId,
        pumpType = ids.pumpType?.name,
        pumpSerial = ids.pumpSerial,
        endId = ids.endId
    )
```

### Actual JSON Payload

```json
{
  "eventType": "Meal Bolus",
  "isValid": true,
  "date": 1708135216000,
  "utcOffset": -300,
  "carbs": 45.0,
  "notes": "Pizza",
  "duration": 14400000,
  "identifier": "507f1f77bcf86cd799439011",
  "pumpId": 11000,
  "pumpType": "DANA_I",
  "pumpSerial": "bbbb"
}
```

### Key Findings

- **eventType selection**: `< 12g` → `CARBS_CORRECTION`, `≥ 12g` → `MEAL_BOLUS`
- **Hard limits enforced**: `min(carbs, MAX_CARBS)` and `min(duration, MAX_CARBS_DURATION_HOURS)`
- **Duration optional**: Only sent if non-zero (extended carb absorption)
- **identifier**: Server ObjectId from `nightscoutId` - never client UUID

---

## TemporaryTargetExtension.kt Analysis (AAPS-SRC-013) ✅

**File**: `plugins/sync/src/main/kotlin/app/aaps/plugins/sync/nsclientV3/extensions/TemporaryTargetExtension.kt`

### JSON Mapping

```kotlin
fun TT.toNSTemporaryTarget(): NSTemporaryTarget =
    NSTemporaryTarget(
        eventType = EventType.TEMPORARY_TARGET,
        isValid = isValid,
        date = timestamp,
        utcOffset = T.msecs(utcOffset).mins(),
        reason = reason.toReason(),        // ACTIVITY, EATING_SOON, HYPO, etc.
        targetTop = highTarget,
        targetBottom = lowTarget,
        units = NsUnits.MG_DL,
        duration = duration,
        identifier = ids.nightscoutId,     // Server-assigned ObjectId
        pumpId = ids.pumpId,
        pumpType = ids.pumpType?.name,
        pumpSerial = ids.pumpSerial,
        endId = ids.endId
    )
```

### Actual JSON Payload

```json
{
  "eventType": "Temporary Target",
  "isValid": true,
  "date": 1708135216000,
  "utcOffset": -300,
  "reason": "Activity",
  "targetTop": 140.0,
  "targetBottom": 120.0,
  "units": "mg/dl",
  "duration": 3600000,
  "identifier": "507f1f77bcf86cd799439011",
  "pumpId": 11000,
  "pumpType": "DANA_I",
  "pumpSerial": "bbbb"
}
```

### Reason Enum Values

| AAPS Reason | Nightscout `reason` |
|-------------|---------------------|
| `CUSTOM` | "Custom" |
| `HYPOGLYCEMIA` | "Hypo" |
| `ACTIVITY` | "Activity" |
| `EATING_SOON` | "Eating Soon" |
| `AUTOMATION` | "Automation" |
| `WEAR` | "Wear" |

### Loop vs AAPS Override Comparison

| Aspect | Loop `Temporary Override` | AAPS `Temporary Target` |
|--------|---------------------------|-------------------------|
| **eventType** | `"Temporary Override"` | `"Temporary Target"` |
| **`_id` handling** | UUID string (client) | ObjectId (server) |
| **Target field** | `correctionRange: [min, max]` | `targetBottom`, `targetTop` |
| **Scaling** | `insulinNeedsScaleFactor` | Not supported |
| **GAP-TREAT-012** | ✅ Affected | ❌ Not affected |

### Why AAPS TT Doesn't Trigger GAP-TREAT-012

1. AAPS uses `identifier` field (not `_id`)
2. `identifier` is populated from `nightscoutId` (server-assigned ObjectId)
3. On first create, `identifier: null` → server generates ObjectId
4. AAPS never sends client-generated UUID as identity

---

## Test Infrastructure (AAPS-RUN-TESTS)

### Test Inventory

| Category | Files | @Test Count |
|----------|-------|-------------|
| **sync plugin total** | 45 | ~100+ |
| **nsclientV3 tests** | 24 | ~50+ |
| **Extension tests** | 13 | 13 |

### Key Test Files

```
plugins/sync/src/test/kotlin/app/aaps/plugins/sync/nsclientV3/
├── extensions/
│   ├── BolusExtensionKtTest.kt          # Round-trip JSON test
│   ├── CarbsExtensionKtTest.kt
│   ├── TemporaryTargetExtensionKtTest.kt
│   ├── TemporaryBasalExtensionKtTest.kt
│   └── ... (13 extension tests)
├── workers/
│   ├── DataSyncWorkerTest.kt
│   ├── LoadTreatmentsWorkerTest.kt
│   └── ... (8 worker tests)
├── DataSyncSelectorV3Test.kt
└── NSClientV3PluginTest.kt
```

### Running Tests

**Requires**: Android SDK (`ANDROID_HOME` environment variable)

```bash
# Full test suite
./gradlew :plugins:sync:testFullDebugUnitTest

# Or use Android Studio
# Open externals/AndroidAPS, run tests from IDE
```

### Test Pattern: Round-Trip Serialization

All extension tests use `convertToRemoteAndBack()` pattern:
```kotlin
val bolus2 = (bolus.toNSBolus().convertToRemoteAndBack() as NSBolus).toBolus()
assertThat(bolus.contentEqualsTo(bolus2)).isTrue()
```

This verifies JSON serialization matches Nightscout API expectations.

---

## Overview

AAPS (AndroidAPS) uses a sophisticated sync architecture with two API versions:
- **NSClient (v1)**: Legacy Socket.IO-based sync
- **NSClientV3**: Modern REST API with `identifier` field

AAPS is **different from Loop** in several key ways:
- Uses server-assigned `_id` (stored as `nightscoutId`)
- Sends `identifier` field for v3 API
- Includes `pumpId`, `pumpType`, `pumpSerial` for pump event correlation
- Has extensive existing test coverage we can learn from

---

## Phase 1: AAPS Source Code Analysis

### 1.1 Core SDK Structure

| Item | Source File | Status |
|------|-------------|--------|
| AAPS-SRC-001 | `core/nssdk/interfaces/NSAndroidClient.kt` | ⬜ |
| AAPS-SRC-002 | `core/nssdk/NSAndroidClientImpl.kt` | ⬜ |
| AAPS-SRC-003 | `core/nssdk/networking/` | ⬜ |
| AAPS-SRC-004 | `core/data/model/IDs.kt` | ✅ |

**Deliverable**: Document SDK methods, HTTP calls, and identity handling.

### 1.2 Treatment Extensions (JSON Serialization)

| Item | Source File | Purpose | Status |
|------|-------------|---------|--------|
| AAPS-SRC-010 | `extensions/BolusExtension.kt` | Bolus → NSBolus JSON | ✅ |
| AAPS-SRC-011 | `extensions/CarbsExtension.kt` | Carbs → NSCarbs JSON | ✅ |
| AAPS-SRC-012 | `extensions/TemporaryBasalExtension.kt` | Temp Basal → JSON | ⬜ |
| AAPS-SRC-013 | `extensions/TemporaryTargetExtension.kt` | Temp Target → JSON | ✅ |
| AAPS-SRC-014 | `extensions/ProfileSwitchExtension.kt` | Profile Switch → JSON | ⬜ |
| AAPS-SRC-015 | `extensions/DeviceStatusExtension.kt` | DeviceStatus → JSON | ⬜ |
| AAPS-SRC-016 | `extensions/GlucoseValueExtension.kt` | SGV → Entry JSON | ⬜ |
| AAPS-SRC-017 | `extensions/TherapyEventExtension.kt` | Events → JSON | ⬜ |

### 1.3 Identity Field Usage (CRITICAL)

| Item | Question | Source | Status |
|------|----------|--------|--------|
| AAPS-ID-001 | How does IDs.kt structure work? | `core/data/model/IDs.kt` | ✅ |
| AAPS-ID-002 | When is `nightscoutId` populated? | Extensions, Sync workers | ⬜ |
| AAPS-ID-003 | How is `identifier` used in v3? | `nssdk/localmodel/` | ⬜ |
| AAPS-ID-004 | How do `pumpId`/`pumpSerial` correlate? | Extensions | ⬜ |
| AAPS-ID-005 | Difference between v1 and v3 sync? | `nsclient/` vs `nsclientV3/` | ⬜ |

---

## Phase 2: Key Differences from Loop

| Aspect | Loop | AAPS |
|--------|------|------|
| **ID strategy** | Client generates UUID | Server assigns `_id` |
| **Sync identity** | `syncIdentifier` (client) | `identifier` (v3), `nightscoutId` (v1) |
| **Override handling** | UUID in `_id` field | Uses `TemporaryTarget` eventType |
| **Pump correlation** | N/A | `pumpId` + `pumpType` + `pumpSerial` |
| **API version** | v1 only | v1 (Socket.IO) + v3 (REST) |
| **Local cache** | `ObjectIdCache` (in-memory) | Room database |

---

## Phase 3: Test Development Pipeline

### 3.1 Bolus Upload Tests

| Test ID | Scenario | HTTP | Payload Key Fields | Status |
|---------|----------|------|-------------------|--------|
| TEST-AAPS-BOLUS-001 | SMB bolus (v3) | POST | `identifier`, `insulin`, `type: SMB` | ⬜ |
| TEST-AAPS-BOLUS-002 | Meal bolus (v3) | POST | `identifier`, `insulin`, `type: NORMAL` | ⬜ |
| TEST-AAPS-BOLUS-003 | Bolus with pump IDs | POST | `pumpId`, `pumpType`, `pumpSerial` | ⬜ |
| TEST-AAPS-BOLUS-004 | Update bolus (v3) | PUT | `identifier`, updated fields | ⬜ |
| TEST-AAPS-BOLUS-005 | Delete bolus (v3) | DELETE | `identifier` | ⬜ |

### 3.2 Carbs Upload Tests

| Test ID | Scenario | HTTP | Payload Key Fields | Status |
|---------|----------|------|-------------------|--------|
| TEST-AAPS-CARB-001 | Carb entry (v3) | POST | `identifier`, `carbs`, `duration` | ⬜ |
| TEST-AAPS-CARB-002 | Carb update (v3) | PUT | `identifier`, modified `carbs` | ⬜ |
| TEST-AAPS-CARB-003 | Carb batch | POST | Array with identifiers | ⬜ |

### 3.3 Temporary Target Tests (AAPS "Override")

| Test ID | Scenario | HTTP | Payload Key Fields | Status |
|---------|----------|------|-------------------|--------|
| TEST-AAPS-TT-001 | Create temp target | POST | `identifier`, `targetTop`, `targetBottom` | ⬜ |
| TEST-AAPS-TT-002 | Cancel temp target | PUT | `isValid: false` | ⬜ |
| TEST-AAPS-TT-003 | Activity mode | POST | `reason: "Activity"` | ⬜ |

### 3.4 DeviceStatus Tests

| Test ID | Scenario | HTTP | Payload Key Fields | Status |
|---------|----------|------|-------------------|--------|
| TEST-AAPS-DS-001 | AAPS status | POST | `openaps.*`, `pump.*` | ⬜ |
| TEST-AAPS-DS-002 | SMB prediction | POST | `openaps.suggested.*` | ⬜ |
| TEST-AAPS-DS-003 | Pump reservoir | POST | `pump.reservoir`, `pump.battery` | ⬜ |

### 3.5 v1 vs v3 API Tests

| Test ID | Scenario | Status |
|---------|----------|--------|
| TEST-AAPS-API-001 | v1 POST treatment (Socket.IO style) | ⬜ |
| TEST-AAPS-API-002 | v3 POST treatment (REST) | ⬜ |
| TEST-AAPS-API-003 | v3 identifier deduplication | ⬜ |
| TEST-AAPS-API-004 | v3 srvModified handling | ⬜ |
| TEST-AAPS-API-005 | v3 history endpoint polling | ⬜ |

---

## Phase 4: Kotlin/Android Testing Options

### Option A: Unit Test Extraction (Recommended)

Extract AAPS extension tests to run standalone:

```kotlin
// Extracted test - runs with JUnit on JVM
class BolusExtensionTest {
    @Test
    fun testBolusToNSBolus() {
        val bolus = BS(
            timestamp = 10000,
            amount = 1.0,
            type = BS.Type.SMB,
            ids = IDs(pumpId = 11000, pumpType = PumpType.DANA_I)
        )
        val nsBolus = bolus.toNSBolus()
        
        // Verify JSON structure
        assertThat(nsBolus.identifier).isNull()  // Server assigns
        assertThat(nsBolus.pumpId).isEqualTo(11000)
    }
}
```

**Pros**: Existing tests, pure JVM, no Android dependencies
**Cons**: Doesn't test HTTP layer

### Option B: Android Instrumentation Tests

Use Android Studio to run actual HTTP tests:

```kotlin
@RunWith(AndroidJUnit4::class)
class NightscoutIntegrationTest {
    @Test
    fun testUploadBolus() = runBlocking {
        val client = NSAndroidClientImpl(testUrl, testSecret)
        val result = client.uploadTreatment(testBolus)
        assertThat(result.identifier).isNotNull()
    }
}
```

**Pros**: Full integration, real HTTP
**Cons**: Requires Android emulator, slower

### Option C: Gradle JVM Tests with Mock Server

Run AAPS SDK against MockWebServer:

```kotlin
class NightscoutMockTest {
    @get:Rule
    val mockServer = MockWebServer()
    
    @Test
    fun testBolusUpload() {
        mockServer.enqueue(MockResponse().setBody("""{"identifier":"abc"}"""))
        
        val client = createTestClient(mockServer.url("/"))
        val result = client.uploadBolus(testBolus)
        
        // Verify request format
        val request = mockServer.takeRequest()
        assertThat(request.path).isEqualTo("/api/v3/treatments")
    }
}
```

**Pros**: Fast, verifies request format, no emulator
**Cons**: Doesn't test real server behavior

---

## Source File Index

### NSClientV3 Plugin
```
externals/AndroidAPS/plugins/sync/src/main/kotlin/app/aaps/plugins/sync/
├── nsclientV3/
│   ├── NSClientV3Plugin.kt          # Main plugin
│   ├── DataSyncSelectorV3.kt        # Sync logic
│   ├── extensions/                   # Treatment → NS conversion
│   │   ├── BolusExtension.kt
│   │   ├── CarbsExtension.kt
│   │   ├── TemporaryBasalExtension.kt
│   │   ├── TemporaryTargetExtension.kt
│   │   ├── ProfileSwitchExtension.kt
│   │   ├── DeviceStatusExtension.kt
│   │   └── GlucoseValueExtension.kt
│   ├── workers/                      # Background sync
│   │   ├── DataSyncWorker.kt
│   │   └── Load*Worker.kt
│   └── services/
│       └── NSClientV3Service.kt
```

### Core SDK
```
externals/AndroidAPS/core/nssdk/src/main/kotlin/app/aaps/core/nssdk/
├── interfaces/
│   └── NSAndroidClient.kt           # Client interface
├── NSAndroidClientImpl.kt           # Implementation
├── networking/                       # HTTP layer
├── localmodel/                       # Local data types
├── remotemodel/                      # API response types
└── mapper/                           # Conversions
```

### Data Models
```
externals/AndroidAPS/core/data/src/main/kotlin/app/aaps/core/data/
├── model/
│   ├── IDs.kt                        # Identity fields
│   ├── BS.kt                         # Bolus
│   ├── CA.kt                         # Carbs
│   ├── TB.kt                         # Temp Basal
│   └── TT.kt                         # Temp Target
```

### Existing Tests (Learn From)
```
externals/AndroidAPS/plugins/sync/src/test/kotlin/app/aaps/plugins/sync/nsclientV3/
├── extensions/
│   ├── BolusExtensionKtTest.kt       # ✅ Good example
│   ├── CarbsExtensionKtTest.kt
│   ├── TemporaryTargetExtensionKtTest.kt
│   └── ...
├── workers/
│   ├── DataSyncWorkerTest.kt
│   └── LoadTreatmentsWorkerTest.kt
└── NSClientV3PluginTest.kt
```

---

## Android Studio Setup

### Requirements

| Requirement | Status |
|-------------|--------|
| Android Studio | ✅ `/opt/google/android-studio` |
| JDK 17+ | Check `java -version` |
| Kotlin 1.9+ | Via Gradle |
| Android SDK | Via Android Studio |

### Quick Start

```bash
cd externals/AndroidAPS
./gradlew :plugins:sync:testDebugUnitTest
```

---

## Comparison: Loop vs AAPS Test Strategy

| Aspect | Loop | AAPS |
|--------|------|------|
| **Language** | Swift | Kotlin |
| **Runtime** | Linux Swift SPM | JVM (Gradle) |
| **Existing tests** | Few | Many (30+ extension tests) |
| **HTTP tests** | Need to create | Use MockWebServer |
| **Android dependency** | None | Optional (unit tests work without) |

---

## Work Items Summary

| Phase | Items | Completed | Blocked |
|-------|-------|-----------|---------|
| 1. Source Analysis | 17 | 6 | 0 |
| 2. Difference Doc | 1 | 1 | 0 |
| 3. Test Development | 18 | 0 | 0 |
| 4. Test Harness | 3 | 0 | 0 |
| **Total** | **39** | **7** | **0** |

---

## Next Actions

1. [x] Run existing AAPS tests: `./gradlew :plugins:sync:test` ⚠️ Requires Android SDK
2. [x] Analyze `IDs.kt` - understand identity field structure ✅
3. [x] Compare `BolusExtension.kt` vs Loop's `SyncCarbObject.swift` ✅
4. [x] Analyze `CarbsExtension.kt` - carbs JSON mapping ✅
5. [x] Analyze `TemporaryTargetExtension.kt` - AAPS override equivalent ✅
6. [ ] Document v1 vs v3 API differences
7. [ ] Analyze remaining extensions (TempBasal, ProfileSwitch, DeviceStatus)
8. [ ] Create test fixtures from AAPS payloads

---

## Related Documents

- [Loop Upload Testing](loop-nightscout-upload-testing.md) - Loop equivalent
- [Integration Test Harness](integration-test-harness.md) - How to run tests
- [GAP-TREAT-012](../../traceability/treatments-gaps.md#gap-treat-012) - UUID _id issue (Loop-specific)
- [AAPS Nightscout Sync](../../mapping/aaps/nightscout-sync.md) - Existing analysis
- [AAPS NSClient Schema](../../mapping/aaps/nsclient-schema.md) - Field mapping
- [REQ-SYNC-072](../../traceability/sync-identity-requirements.md#req-sync-072-transparent-uuid-promotion-option-g) - **Option G (Recommended)**: Transparent UUID promotion
- [REQ-SYNC-071](../../traceability/sync-identity-requirements.md#req-sync-071) - Long-term: Server-controlled ID proposal
