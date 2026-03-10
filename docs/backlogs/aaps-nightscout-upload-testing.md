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

## DeviceStatusExtension.kt Analysis (AAPS-SRC-015) ✅

**File**: `plugins/sync/src/main/kotlin/app/aaps/plugins/sync/nsclientV3/extensions/DeviceStatusExtension.kt`

### JSON Mapping

```kotlin
fun DS.toNSDeviceStatus(): NSDeviceStatus =
    NSDeviceStatus(
        date = timestamp,
        device = device,                          // "openaps://samsung SM-G970F"
        pump = pump,                              // Pump object with battery, reservoir
        openaps = NSDeviceStatus.OpenAps(
            suggested = suggested?.let { JSONObject(it) },
            enacted = enacted?.let { JSONObject(it) },
            iob = iob?.let { JSONObject(it) }
        ),
        uploaderBattery = uploaderBattery,
        isCharging = isCharging,
        configuration = configuration
    )
```

### NSDeviceStatus Structure

```kotlin
data class NSDeviceStatus(
    val identifier: String?,      // Server-assigned (not client-generated)
    val date: Long?,              // Timestamp in milliseconds
    val device: String?,          // "openaps://phone-name"
    val uploaderBattery: Int?,    // Phone battery %
    val isCharging: Boolean?,
    val pump: Pump?,              // Pump status object
    val openaps: OpenAps?,        // Algorithm data
    val uploader: Uploader?,
    val configuration: Configuration?
)
```

### OpenAps Object (oref0/oref1 format)

```json
{
  "openaps": {
    "suggested": {
      "bg": 173,
      "temp": "absolute",
      "predBGs": {
        "IOB": [173, 178, 183, ...],
        "COB": [...],
        "UAM": [...],
        "ZT": [...]
      },
      "reason": "COB: 0, Dev: 46, BGI: -1.92...",
      "eventualBG": 194,
      "IOB": 0.309,
      "COB": 0
    },
    "enacted": {
      "rate": 2.25,
      "duration": 30,
      "timestamp": "2016-06-24T09:19:06.000Z",
      "received": true
    },
    "iob": [{
      "iob": 0.309,
      "basaliob": 0.078,
      "bolussnooze": 0,
      "activity": 0.0048,
      "time": "2016-06-24T09:26:16.000Z"
    }]
  }
}
```

### Loop vs AAPS DeviceStatus Comparison

| Field | Loop | AAPS (oref0) |
|-------|------|--------------|
| **Namespace** | `loop` | `openaps` |
| **Prediction** | Single `predicted.values[]` | 4 curves: `IOB`, `COB`, `UAM`, `ZT` |
| **IOB format** | `{iob: 2.5, timestamp: ...}` | Array with activity, basaliob |
| **Enacted** | `{rate, duration, received, bolusVolume}` | `{rate, duration, timestamp, received}` |
| **Reason** | Not included | Detailed string with Dev, BGI, ISF |

### Key Insight: 4 Prediction Curves (oref0)

AAPS/oref0 sends 4 separate prediction arrays in `predBGs`:
- **IOB**: Insulin-only prediction
- **COB**: Carb absorption prediction  
- **UAM**: Unannounced meal detection
- **ZT**: Zero-temp (safety) prediction

Loop sends a single combined curve.

---

## GlucoseValueExtension.kt Analysis (AAPS-SRC-016) ✅

**File**: `plugins/sync/src/main/kotlin/app/aaps/plugins/sync/nsclientV3/extensions/GlucoseValueExtension.kt`

### JSON Mapping

```kotlin
fun GV.toNSSvgV3(): NSSgvV3 =
    NSSgvV3(
        isValid = isValid,
        date = timestamp,
        utcOffset = T.msecs(utcOffset).mins(),
        filtered = raw,
        unfiltered = 0.0,
        sgv = value,
        units = NsUnits.MG_DL,
        direction = Direction.fromString(trendArrow.text),
        noise = noise,
        device = sourceSensor.text,
        identifier = ids.nightscoutId    // Server-assigned
    )
```

### NSSgvV3 Structure (entries collection)

```kotlin
data class NSSgvV3(
    val date: Long?,              // Timestamp in milliseconds
    val device: String?,          // Source sensor name
    val identifier: String?,      // Server-assigned ObjectId
    val sgv: Double,              // Sensor glucose value (mg/dL)
    val units: NsUnits,           // MG_DL or MMOL_L
    val direction: Direction?,    // Trend arrow
    val noise: Double?,           // Signal noise level
    val filtered: Double?,        // Filtered raw value
    val unfiltered: Double?       // Unfiltered raw value
)
```

### Actual JSON Payload

```json
{
  "date": 1708135216000,
  "dateString": "2026-02-17T02:00:16.000Z",
  "device": "Dexcom G6",
  "sgv": 125,
  "units": "mg/dl",
  "direction": "Flat",
  "noise": 1,
  "filtered": 125000,
  "unfiltered": 0,
  "identifier": "507f1f77bcf86cd799439011"
}
```

### Loop vs AAPS SGV Comparison

| Field | Loop | AAPS |
|-------|------|------|
| **Identity** | None (server dedup) | `identifier` (server ObjectId) |
| **Trend** | `trend` (1-9) + `direction` | `direction` only |
| **Type field** | `type: "sgv"` or `"mbg"` | Separate collections |
| **Raw values** | `trendRate` | `filtered`, `unfiltered`, `noise` |

### Key Insight: AAPS Uses API v3 for Entries

AAPS uploads SGV to `/api/v3/entries` with:
- `identifier`: Server-assigned ObjectId (not client UUID)
- `device`: Source sensor text (e.g., "Dexcom G6", "Libre 2")
- No `type` field needed (v3 uses separate endpoints)

---

## TemporaryBasalExtension.kt Analysis (AAPS-SRC-012) ✅

**File**: `plugins/sync/src/main/kotlin/app/aaps/plugins/sync/nsclientV3/extensions/TemporaryBasalExtension.kt`

### JSON Mapping

```kotlin
fun TB.toNSTemporaryBasal(profile: Profile): NSTemporaryBasal =
    NSTemporaryBasal(
        eventType = EventType.TEMPORARY_BASAL,
        isValid = isValid,
        date = timestamp,
        type = type.toType(),                    // NORMAL, PUMP_SUSPEND, etc.
        rate = convertedToAbsolute(timestamp, profile),
        isAbsolute = isAbsolute,
        absolute = if (isAbsolute) rate else null,
        percent = if (!isAbsolute) rate - 100 else null,
        duration = duration,
        identifier = ids.nightscoutId,
        pumpId = ids.pumpId,
        pumpType = ids.pumpType?.name,
        pumpSerial = ids.pumpSerial
    )
```

### NSTemporaryBasal Structure

```kotlin
data class NSTemporaryBasal(
    val eventType: EventType,     // TEMPORARY_BASAL
    val duration: Long,           // Duration in milliseconds
    val rate: Double,             // Absolute rate (U/hr)
    val isAbsolute: Boolean,      // true = absolute, false = percent
    val type: Type,               // NORMAL, PUMP_SUSPEND, SUPERBOLUS
    val percent: Double?,         // Percent change (if !isAbsolute)
    val absolute: Double?,        // Absolute rate (if isAbsolute)
    val identifier: String?,      // Server-assigned ObjectId
    ...pump IDs...
)
```

### Type Enum Values

| Type | Description |
|------|-------------|
| `NORMAL` | Standard temp basal |
| `PUMP_SUSPEND` | Pump suspension |
| `EMULATED_PUMP_SUSPEND` | Emulated via 0% temp |
| `SUPERBOLUS` | Superbolus temp (oref0) |
| `FAKE_EXTENDED` | Memory-only, not synced |

### Actual JSON Payload

```json
{
  "eventType": "Temp Basal",
  "isValid": true,
  "date": 1708135216000,
  "duration": 1800000,
  "rate": 1.5,
  "isAbsolute": true,
  "absolute": 1.5,
  "percent": null,
  "type": "NORMAL",
  "identifier": "507f1f77bcf86cd799439011",
  "pumpId": 11000,
  "pumpType": "OMNIPOD_DASH",
  "pumpSerial": "abc123"
}
```

### Key Insight: Absolute vs Percent

AAPS sends BOTH representations:
- `rate`: Always absolute (after profile conversion)
- `absolute`: Set if `isAbsolute = true`
- `percent`: Set if `isAbsolute = false` (rate - 100)

Loop sends similar via `TempBasalNightscoutTreatment` with `rate` and `temp: "absolute"`.

---

## TherapyEventExtension.kt Analysis (AAPS-SRC-017) ✅

**File**: `plugins/sync/src/main/kotlin/app/aaps/plugins/sync/nsclientV3/extensions/TherapyEventExtension.kt`

### JSON Mapping

```kotlin
fun TE.toNSTherapyEvent(): NSTherapyEvent =
    NSTherapyEvent(
        eventType = type.toType(),          // Maps TE.Type → EventType
        isValid = isValid,
        date = timestamp,
        units = glucoseUnit.toUnits(),
        notes = note,
        enteredBy = enteredBy,
        glucose = glucose,                  // Optional BG value
        glucoseType = glucoseType,          // Finger, Sensor, Manual
        duration = duration,
        location = location?.text,          // Body location for sites
        arrow = arrow?.text,                // Trend arrow
        identifier = ids.nightscoutId,
        pumpId = ids.pumpId,
        pumpType = ids.pumpType?.name,
        pumpSerial = ids.pumpSerial
    )
```

### NSTherapyEvent Structure

```kotlin
data class NSTherapyEvent(
    val eventType: EventType,       // Note, Site Change, Sensor Start, etc.
    val duration: Long,             // Duration in milliseconds
    val notes: String?,             // User notes
    val enteredBy: String?,         // Source app
    val glucose: Double?,           // BG value at event time
    val glucoseType: MeterType?,    // Finger, Sensor, Manual
    val location: String?,          // Body site location
    val arrow: String?,             // Trend direction
    val identifier: String?,        // Server-assigned ObjectId
    ...pump IDs...
)
```

### Common EventType Values

| EventType | Description |
|-----------|-------------|
| `NOTE` | General note |
| `SITE_CHANGE` | Infusion site change |
| `SENSOR_START` | CGM sensor inserted |
| `SENSOR_CHANGE` | CGM sensor replaced |
| `INSULIN_CHANGE` | Reservoir/cartridge change |
| `PUMP_BATTERY_CHANGE` | Pump battery replaced |
| `EXERCISE` | Physical activity |
| `ANNOUNCEMENT` | User announcement |
| `QUESTION` | User question |

### Actual JSON Payload

```json
{
  "eventType": "Site Change",
  "isValid": true,
  "date": 1708135216000,
  "duration": 0,
  "notes": "Left abdomen",
  "enteredBy": "AAPS",
  "glucose": 125,
  "glucoseType": "Sensor",
  "location": "abdomen",
  "identifier": "507f1f77bcf86cd799439011",
  "pumpId": 11000,
  "pumpType": "OMNIPOD_DASH",
  "pumpSerial": "abc123"
}
```

### Key Insight: Flexible Event Container

TherapyEvent is a flexible container for non-treatment events:
- Site changes, sensor events, notes
- Optional glucose reading at time of event
- Location field for body site tracking
- Maps to Nightscout's "careportal" entries

---

## AAPS-SRC-014: ProfileSwitchExtension.kt Analysis

**File:** `plugins/sync/src/main/kotlin/app/aaps/plugins/sync/nsclientV3/extensions/ProfileSwitchExtension.kt`

### NSProfileSwitch Model

```kotlin
data class NSProfileSwitch(
    override val identifier: String?,      // Server-assigned ObjectId
    override var date: Long?,              // Timestamp ms
    override var utcOffset: Long?,         // UTC offset minutes
    override val eventType: EventType,     // PROFILE_SWITCH
    override val isValid: Boolean,
    override val pumpId: Long?,
    override val pumpType: String?,
    override val pumpSerial: String?,
    override val endId: Long?,
    // Profile-specific fields:
    val profileJson: JSONObject?,          // Full profile definition
    val profile: String,                   // Customized profile name
    val originalProfileName: String?,      // Base profile name
    val timeShift: Long?,                  // Time shift in minutes
    val percentage: Int?,                  // Profile percentage (default 100)
    val duration: Long?,                   // Duration in milliseconds
    val originalDuration: Long?
) : NSTreatment
```

### Conversion: PS → NSProfileSwitch

```kotlin
fun PS.toNSProfileSwitch(dateUtil, decimalFormatter): NSProfileSwitch {
    val unmodifiedCustomizedName = getCustomizedName(decimalFormatter)
    // Reset customizations to get pure profile JSON
    val notCustomized = this.copy()
    notCustomized.timeshift = 0
    notCustomized.percentage = 100

    return NSProfileSwitch(
        eventType = EventType.PROFILE_SWITCH,
        isValid = isValid,
        date = timestamp,
        utcOffset = T.msecs(utcOffset).mins(),
        timeShift = timeshift,
        percentage = percentage,
        duration = duration,
        profile = unmodifiedCustomizedName,        // "Default 90%"
        originalProfileName = profileName,          // "Default"
        originalDuration = duration,
        profileJson = ProfileSealed.PS(...).toPureNsJson(dateUtil),  // Full blocks
        identifier = ids.nightscoutId,              // Server-assigned
        pumpId = ids.pumpId,
        pumpType = ids.pumpType?.name,
        pumpSerial = ids.pumpSerial,
        endId = ids.endId
    )
}
```

### Example Nightscout JSON

```json
{
  "eventType": "Profile Switch",
  "date": 1710120000000,
  "utcOffset": -300,
  "profile": "Workout 80%",
  "originalProfileName": "Default",
  "timeShift": 0,
  "percentage": 80,
  "duration": 7200000,
  "profileJson": {
    "dia": 5,
    "carbratio": [{"time": "00:00", "value": 10}],
    "sens": [{"time": "00:00", "value": 50}],
    "basal": [{"time": "00:00", "value": 1.0}],
    "target_low": [{"time": "00:00", "value": 100}],
    "target_high": [{"time": "00:00", "value": 120}],
    "units": "mg/dl"
  },
  "identifier": null,
  "pumpId": 12345,
  "pumpType": "OMNIPOD_DASH",
  "pumpSerial": "ABC123"
}
```

### Key Insight: Profile Storage vs Switch

| Field | Purpose |
|-------|---------|
| `profileJson` | Full profile definition (blocks for basal, ISF, CR, targets) |
| `profile` | Customized name with percentage ("Default 80%") |
| `originalProfileName` | Base profile name without modifications |
| `percentage` | Scaling factor (100 = no change) |
| `timeShift` | Shift schedule by N minutes |
| `duration` | 0 = permanent, >0 = temporary switch |

### Loop vs AAPS Profile Comparison

| Aspect | Loop | AAPS |
|--------|------|------|
| Storage | Profile stored in settings | Profile stored in NS + local |
| Switch | Override with `correctionRange` | ProfileSwitch with `percentage` |
| Scaling | `insulinNeedsScaleFactor` | `percentage` field |
| Time Shift | Not supported | `timeShift` field |
| Profile JSON | Not sent in switch | Full profile in `profileJson` |

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

## NSAndroidClient SDK Analysis (AAPS-SRC-001) ✅

**File**: `core/nssdk/src/main/kotlin/app/aaps/core/nssdk/interfaces/NSAndroidClient.kt`

### Interface Methods

| Method | HTTP | Purpose |
|--------|------|---------|
| `createTreatment(nsTreatment)` | POST | Create new treatment |
| `updateTreatment(nsTreatment)` | PUT/DELETE | Update or soft-delete |
| `getTreatmentsNewerThan(createdAt, limit)` | GET | Fetch recent treatments |
| `getTreatmentsModifiedSince(from, limit)` | GET | Incremental sync |
| `createSgv(nsSgvV3)` | POST | Create SGV entry |
| `createDeviceStatus(nsDeviceStatus)` | POST | Upload device status |

### CreateUpdateResponse Structure

```kotlin
class CreateUpdateResponse(
    val response: Int,              // HTTP status code (200, 201)
    val identifier: String?,        // Server-assigned ObjectId
    val isDeduplication: Boolean?,  // Server found duplicate
    val deduplicatedIdentifier: String?, // Existing record's ID
    val lastModified: Long?,        // srvModified timestamp
    val errorResponse: String?      // Error message if failed
)
```

### Identity Flow (from NSAndroidClientImpl.kt)

**Create treatment (lines 293-328)**:
```kotlin
override suspend fun createTreatment(nsTreatment: NSTreatment): CreateUpdateResponse {
    val remoteTreatment = nsTreatment.toRemoteTreatment()
    remoteTreatment.app = "AAPS"
    val response = api.createTreatment(remoteTreatment)
    
    if (response.code() == 200 || response.code() == 201) {
        return CreateUpdateResponse(
            response = response.code(),
            identifier = response.body()?.identifier,  // ← Server ObjectId
            isDeduplication = response.body()?.isDeduplication,
            deduplicatedIdentifier = response.body()?.deduplicatedIdentifier
        )
    }
}
```

**Update treatment (lines 330-350)**:
```kotlin
override suspend fun updateTreatment(nsTreatment: NSTreatment): CreateUpdateResponse {
    val identifier = remoteTreatment.identifier  // ← Required for update
        ?: throw InvalidFormatNightscoutException("Invalid format")
    
    val response = if (nsTreatment.isValid) 
        api.updateTreatment(remoteTreatment, identifier)  // PUT
    else 
        api.deleteTreatment(identifier)                    // DELETE (soft)
}
```

### Key Insight: Server-Controlled Identity

1. **Create**: `identifier: null` → server generates ObjectId
2. **Response**: AAPS extracts `response.body()?.identifier` (server ObjectId)
3. **Store**: AAPS saves as `nightscoutId` in Room database
4. **Update/Delete**: AAPS sends `identifier` (the stored ObjectId)

This is the **opposite of Loop** which sends client UUID as `_id`.

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
| AAPS-SRC-001 | `core/nssdk/interfaces/NSAndroidClient.kt` | ✅ |
| AAPS-SRC-002 | `core/nssdk/NSAndroidClientImpl.kt` | ✅ |
| AAPS-SRC-003 | `core/nssdk/networking/` | ✅ |
| AAPS-SRC-004 | `core/data/model/IDs.kt` | ✅ |

**Deliverable**: Document SDK methods, HTTP calls, and identity handling.

---

## AAPS-SRC-003: Networking Layer Analysis ✅

**Location**: `core/nssdk/src/main/kotlin/app/aaps/core/nssdk/networking/`

### Files Analyzed

| File | Purpose |
|------|---------|
| `NightscoutRemoteService.kt` | Retrofit interface - all v3 API endpoints |
| `NSAuthInterceptor.kt` | JWT bearer token refresh interceptor |
| `NetworkStackBuilder.kt` | OkHttp/Retrofit configuration |

### Key Endpoints (NightscoutRemoteService.kt)

**Treatments CRUD** - uses `identifier` in URL path:
```kotlin
@POST("v3/treatments")
suspend fun createTreatment(@Body remoteTreatment: RemoteTreatment)

@PATCH("v3/treatments/{identifier}")
suspend fun updateTreatment(@Body remoteTreatment: RemoteTreatment, @Path("identifier") identifier: String)

@DELETE("v3/treatments/{identifier}")
suspend fun deleteTreatment(@Path("identifier") identifier: String)
```

**Auth** - JWT Bearer with auto-refresh:
```kotlin
// NSAuthInterceptor.kt
.addHeader("Authorization", "Bearer $jwtToken")
// Auto-refresh on 401/403
```

### AAPS vs Loop Networking

| Aspect | AAPS (v3) | Loop (v1) |
|--------|-----------|-----------|
| API | v3 REST | v1 REST |
| ID in URL | `/{identifier}` | `/{_id}` (UUID or ObjectId) |
| Auth | JWT Bearer | api-secret SHA1 |
| Create | Server assigns ID | Client can send UUID |

---

### 1.2 Treatment Extensions (JSON Serialization)

| Item | Source File | Purpose | Status |
|------|-------------|---------|--------|
| AAPS-SRC-010 | `extensions/BolusExtension.kt` | Bolus → NSBolus JSON | ✅ |
| AAPS-SRC-011 | `extensions/CarbsExtension.kt` | Carbs → NSCarbs JSON | ✅ |
| AAPS-SRC-012 | `extensions/TemporaryBasalExtension.kt` | Temp Basal → JSON | ✅ |
| AAPS-SRC-013 | `extensions/TemporaryTargetExtension.kt` | Temp Target → JSON | ✅ |
| AAPS-SRC-014 | `extensions/ProfileSwitchExtension.kt` | Profile Switch → JSON | ✅ |
| AAPS-SRC-015 | `extensions/DeviceStatusExtension.kt` | DeviceStatus → JSON | ✅ |
| AAPS-SRC-016 | `extensions/GlucoseValueExtension.kt` | SGV → Entry JSON | ✅ |
| AAPS-SRC-017 | `extensions/TherapyEventExtension.kt` | Events → JSON | ✅ |

### 1.3 Identity Field Usage (CRITICAL)

| Item | Question | Source | Status |
|------|----------|--------|--------|
| AAPS-ID-001 | How does IDs.kt structure work? | `core/data/model/IDs.kt` | ✅ |
| AAPS-ID-002 | When is `nightscoutId` populated? | Extensions, Sync workers | ✅ |
| AAPS-ID-003 | How is `identifier` used in v3? | `nssdk/localmodel/` | ✅ |
| AAPS-ID-004 | How do `pumpId`/`pumpSerial` correlate? | Extensions | ⬜ |
| AAPS-ID-005 | Difference between v1 and v3 sync? | `nsclient/` vs `nsclientV3/` | ⬜ |

---

## AAPS-ID-003: identifier in v3 localmodel ✅

### v3 Model Architecture

All v3 treatment models implement `NSTreatment` interface which defines `identifier`:

```kotlin
// core/nssdk/localmodel/treatment/NSTreatment.kt:8
interface NSTreatment {
    val identifier: String?    // Server-assigned, nullable on CREATE
    val pumpId: Long?
    val pumpSerial: String?
    // ... other fields
}
```

### identifier Assignment Flow

**Extension converts local model → v3 model:**
```kotlin
// BolusExtension.kt:36
fun Bolus.toNSBolus(): NSBolus =
    NSBolus(
        identifier = ids.nightscoutId,    // Local nightscoutId → v3 identifier
        pumpId = ids.pumpId,
        pumpSerial = ids.pumpSerial,
        // ...
    )
```

**Key insight:** `identifier` in v3 JSON == `ids.nightscoutId` in local DB

### Server Response Handling

```kotlin
// CreateUpdateResponse.kt
class CreateUpdateResponse(
    val response: Int,           // HTTP status
    val identifier: String?,     // Server-assigned ID
    val isDeduplication: Boolean? = false,
    val deduplicatedIdentifier: String? = null,  // If deduplicated
    val lastModified: Long? = null,
    val errorResponse: String? = null
)
```

### v3 Model Files

| Model | File | Has identifier |
|-------|------|----------------|
| NSTreatment | `localmodel/treatment/NSTreatment.kt` | ✅ (interface) |
| NSBolus | `localmodel/treatment/NSBolus.kt` | ✅ |
| NSCarbs | `localmodel/treatment/NSCarbs.kt` | ✅ |
| NSTemporaryTarget | `localmodel/treatment/NSTemporaryTarget.kt` | ✅ |
| NSTemporaryBasal | `localmodel/treatment/NSTemporaryBasal.kt` | ✅ |
| NSProfileSwitch | `localmodel/treatment/NSProfileSwitch.kt` | ✅ |
| NSTherapyEvent | `localmodel/treatment/NSTherapyEvent.kt` | ✅ |
| NSExtendedBolus | `localmodel/treatment/NSExtendedBolus.kt` | ✅ |
| NSOfflineEvent | `localmodel/treatment/NSOfflineEvent.kt` | ✅ |
| NSSgvV3 | `localmodel/entry/NSSgvV3.kt` | ✅ |
| NSDeviceStatus | `localmodel/devicestatus/NSDeviceStatus.kt` | ✅ |

### Mapping Summary

```
┌─────────────────────────────────────────────────────────────────┐
│                    AAPS identifier Mapping                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  LOCAL DB (Room)           EXTENSION           V3 API (JSON)    │
│  ────────────────         ──────────         ────────────────   │
│                                                                 │
│  Bolus.ids.nightscoutId  →  toNSBolus()  →  identifier: "..."   │
│  Bolus.ids.pumpId        →  toNSBolus()  →  pumpId: 123         │
│  Bolus.ids.pumpSerial    →  toNSBolus()  →  pumpSerial: "..."   │
│                                                                 │
│  On CREATE: identifier = null (not set in JSON)                 │
│  On UPDATE: identifier = ids.nightscoutId (from prior CREATE)   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## AAPS-ID-002: nightscoutId Population Flow ✅

### When is nightscoutId Set?

**After successful server response** in both v1 and v3 sync:

**v3 API (NSClientV3Plugin.kt)**:
```kotlin
// Line 541-543 - After createSgv/updateSvg response
result.identifier?.let {
    dataPair.value.ids.nightscoutId = it      // Server-assigned identifier
    storeDataForDb.addToNsIdGlucoseValues(dataPair.value)
}
```

**v1 API (NSClientAddAckWorker.kt)**:
```kotlin
// Line 58-62 - In acknowledgment callback
val pair = ack.originalObject
pair.value.ids.nightscoutId = ack.id          // Server-assigned _id
pair.confirmed = true
storeDataForDb.addToNsIdTemporaryTargets(pair.value)
```

### Complete Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      AAPS nightscoutId Population Flow                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  1. CREATE RECORD (nightscoutId = null)                                     │
│     ┌──────────────────────────────────────────────────────────────────┐   │
│     │ Bolus { ids: { nightscoutId: null, pumpId: 123, ... } }          │   │
│     └────────────────────────────────────────┬─────────────────────────┘   │
│                                              │                              │
│  2. UPLOAD TO NIGHTSCOUT                     ▼                              │
│     ┌──────────────────────────────────────────────────────────────────┐   │
│     │ POST /v3/treatments                                              │   │
│     │ Body: { eventType: "Bolus", insulin: 2.5, pumpId: 123, ... }     │   │
│     │ Note: identifier is NULL on first upload                         │   │
│     └────────────────────────────────────────┬─────────────────────────┘   │
│                                              │                              │
│  3. SERVER RESPONSE                          ▼                              │
│     ┌──────────────────────────────────────────────────────────────────┐   │
│     │ { response: 201, identifier: "65a1b2c3d4e5f6789012345a" }        │   │
│     └────────────────────────────────────────┬─────────────────────────┘   │
│                                              │                              │
│  4. STORE IN LOCAL DB                        ▼                              │
│     ┌──────────────────────────────────────────────────────────────────┐   │
│     │ result.identifier?.let {                                          │   │
│     │     dataPair.value.ids.nightscoutId = it  // "65a1b2c3..."        │   │
│     │     storeDataForDb.addToNsIdBoluses(dataPair.value)               │   │
│     │ }                                                                 │   │
│     └────────────────────────────────────────┬─────────────────────────┘   │
│                                              │                              │
│  5. SUBSEQUENT UPDATE                        ▼                              │
│     ┌──────────────────────────────────────────────────────────────────┐   │
│     │ PATCH /v3/treatments/65a1b2c3d4e5f6789012345a                    │   │
│     │ Body: { identifier: "65a1b2c3...", insulin: 3.0, ... }           │   │
│     └──────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Key Code Locations

| File | Purpose |
|------|---------|
| `NSClientV3Plugin.kt:495` | DeviceStatus identifier storage |
| `NSClientV3Plugin.kt:542` | SGV/Entry identifier storage |
| `NSClientV3Plugin.kt:588` | Treatment identifier storage |
| `NSClientAddAckWorker.kt:58` | v1 ack handler for all types |
| `DataSyncSelectorV3.kt:165` | Check if nightscoutId exists |

### Decision Logic in DataSyncSelectorV3

```kotlin
// Line 165-177 - Bolus sync decision
when {
    // Same local ID and has nightscoutId → skip (already synced)
    bolus.first.id == bolus.second.id && bolus.first.ids.nightscoutId != null -> 
        cont = true
    
    // No nightscoutId → CREATE (new record)
    bolus.first.ids.nightscoutId == null ->
        toUpload = Operation.CREATE
    
    // Has nightscoutId but modified → UPDATE
    bolus.first.ids.nightscoutId != null && bolus.first.id != bolus.second.id ->
        toUpload = Operation.UPDATE
}
```

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
| 1. Source Analysis | 17 | 13 | 0 |
| 2. Difference Doc | 1 | 1 | 0 |
| 3. Test Development | 18 | 0 | 0 |
| 4. Test Harness | 3 | 0 | 0 |
| **Total** | **39** | **14** | **0** |

---

## Next Actions

1. [x] Run existing AAPS tests: `./gradlew :plugins:sync:test` ⚠️ Requires Android SDK
2. [x] Analyze `IDs.kt` - understand identity field structure ✅
3. [x] Compare `BolusExtension.kt` vs Loop's `SyncCarbObject.swift` ✅
4. [x] Analyze `CarbsExtension.kt` - carbs JSON mapping ✅
5. [x] Analyze `TemporaryTargetExtension.kt` - AAPS override equivalent ✅
6. [x] Analyze `NSAndroidClient.kt` - SDK interface ✅
7. [x] Analyze `NSAndroidClientImpl.kt` - identity flow ✅
8. [x] Analyze `DeviceStatusExtension.kt` - oref0 deviceStatus format ✅
9. [x] Analyze `GlucoseValueExtension.kt` - SGV entry format ✅
10. [x] Analyze `TemporaryBasalExtension.kt` - temp basal format ✅
11. [x] Analyze `TherapyEventExtension.kt` - careportal events ✅
12. [x] Analyze `ProfileSwitchExtension.kt` - profile handling ✅
13. [ ] Document v1 vs v3 API differences
14. [ ] Create test fixtures from AAPS payloads
15. [ ] Begin test development phase

---

## Related Documents

- [Loop Upload Testing](loop-nightscout-upload-testing.md) - Loop equivalent
- [Integration Test Harness](integration-test-harness.md) - How to run tests
- [GAP-TREAT-012](../../traceability/treatments-gaps.md#gap-treat-012) - UUID _id issue (Loop-specific)
- [AAPS Nightscout Sync](../../mapping/aaps/nightscout-sync.md) - Existing analysis
- [AAPS NSClient Schema](../../mapping/aaps/nsclient-schema.md) - Field mapping
- [REQ-SYNC-072](../../traceability/sync-identity-requirements.md#req-sync-072-transparent-uuid-promotion-option-g) - **Option G (Recommended)**: Transparent UUID promotion
- [REQ-SYNC-071](../../traceability/sync-identity-requirements.md#req-sync-071) - Long-term: Server-controlled ID proposal
