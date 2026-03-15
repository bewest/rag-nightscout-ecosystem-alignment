# Future-Dated Entries Analysis

**Created**: 2026-03-15
**Updated**: 2026-03-15
**Issue References**: 
- [LoopKit/Loop#2087](https://github.com/LoopKit/Loop/issues/2087)
- [nightscout/cgm-remote-monitor#8453](https://github.com/nightscout/cgm-remote-monitor/issues/8453)
- [LoopKit/CGMBLEKit#191](https://github.com/LoopKit/CGMBLEKit/pull/191) - G6 stopgap fix
**Gap**: GAP-API-021

## Key Finding (2026-03-15)

The stopgap fix from PR #191 was applied to **CGMBLEKit (G6)** but **NOT to G7SensorKit**.

| Path | Stopgap Fix | Location |
|------|-------------|----------|
| G6 (CGMBLEKit) | ✅ Applied | `CGMBLEKit/TransmitterManager.swift:342` |
| G7 (G7SensorKit) | ❌ Missing | `G7SensorKit/G7CGMManager/G7CGMManager.swift:311` |

Both Loop and Trio use the same G7SensorKit code that creates `PersistedCgmEvent` with `date: activatedAt` without any validation.

## Problem Statement

Users are experiencing future-dated entries appearing in Nightscout, causing:
- SAGE/CAGE pills to show incorrect sensor age
- Incorrect time-in-range calculations
- Confusing treatment displays

Example from NS #8453:
```json
{
  "_id": "68c338e81b3b8de57b9e89d7",
  "notes": "89N9W6 activated on 2025-06-04 19:56:03 +0000",
  "enteredBy": "Trio",
  "created_at": "2161-07-12T02:24:18.577Z",  // 135 years in the future!
  "eventType": "Sensor Start",
  "utcOffset": 0
}
```

## Root Cause Analysis

### Server-Side (No Validation)

**Current State**: `lib/api3/shared/operationTools.js:validateCommon()`

```javascript
if (doc.date <= apiConst.MIN_TIMESTAMP) {  // 2000-01-01
  return sendJSONStatus(res, HTTP.BAD_REQUEST, MSG.HTTP_400_BAD_FIELD_DATE);
}
// NO MAXIMUM DATE CHECK!
```

The API v3 rejects dates before 2000-01-01 but accepts **any future date**.

### Client-Side (Bug Sources)

#### 1. CGM Activation Date Calculation

**Trio/Loop (G7SensorKit)**:
```swift
// G7SensorKit/G7CGMManager/G7Sensor.swift
activationDate = Date().addingTimeInterval(-TimeInterval(message.messageTimestamp))
```

If `messageTimestamp` is:
- Corrupted (overflow) → large negative number → future date
- Zero → activationDate = now (reasonable)
- Negative (bug) → activationDate in future

#### 2. Date Serialization Roundtrip

**Trio NightscoutTreatment**:
```swift
case createdAt = "created_at"
```

Date → String → Date conversion can fail if:
- Timezone handling incorrect
- Format string mismatch
- Server locale different from client

#### 3. Device Clock Issues

If device clock is wrong + relative timestamps calculated:
- "Sensor age = 5 days" + wrong device clock = wrong absolute date

### Why Trio Specifically?

The NS #8453 issue shows `enteredBy: "Trio"`. Looking at Trio's upload code:

```swift
// Trio/Sources/APS/OpenAPS/OpenAPS.swift
"created_at": formattedDate,
```

Need to trace where `formattedDate` comes from for Sensor Start events.

## Current Workaround

Nightscout has an admin plugin: `lib/admin_plugins/futureitems.js`

```javascript
// Find and remove treatments in the future
$.ajax('/api/v1/treatments.json?&find[created_at][$gte]=' + nowiso)
```

This allows manual cleanup but doesn't prevent the issue.

## Proposed Solutions

### Option 1: Server-Side Validation (Recommended)

Add to `validateCommon()`:

```javascript
const MAX_FUTURE_MS = 24 * 60 * 60 * 1000; // 24 hours

if (doc.date > Date.now() + MAX_FUTURE_MS) {
  return sendJSONStatus(res, HTTP.BAD_REQUEST, MSG.HTTP_400_FUTURE_DATE);
}
```

**Pros**: 
- Catches all clients
- Single fix point
- Prevents data corruption

**Cons**:
- May break legitimate use cases (scheduled events?)
- Need migration path for existing bad data

### Option 2: Client Hardening

Add validation in Loop/Trio/AAPS before upload:

```swift
guard treatment.date < Date().addingTimeInterval(86400) else {
  log.error("Refusing to upload future-dated treatment: \(treatment)")
  return
}
```

**Pros**:
- Defense in depth
- Can log/alert user

**Cons**:
- Requires updates to each client
- Doesn't protect against other clients

### Option 3: Warning Mode First

Add server-side logging without rejection:

```javascript
if (doc.date > Date.now() + MAX_FUTURE_MS) {
  console.warn('Future-dated document detected:', doc.identifier, doc.date);
  // Don't reject yet, just log
}
```

**Pros**:
- Gather data on frequency
- No breaking changes
- Can escalate to rejection later

### Option 4: Auto-Quarantine

Create a separate collection for suspicious data:

```javascript
if (doc.date > Date.now() + MAX_FUTURE_MS) {
  await quarantineCollection.insertOne(doc);
  // Return success to client but don't add to main collection
}
```

**Pros**:
- Preserves data for analysis
- Doesn't break clients
- Admin can review and decide

## Investigation Tasks

1. [x] Find where Trio generates `Sensor Start` treatments → `G7SensorKit/G7CGMManager.swift:311`
2. [x] Trace date flow from G7Sensor → NightscoutTreatment → G7Sensor calculates `activatedAt` from `messageTimestamp`
3. [x] Check if AAPS/xDrip+ have similar issues → xDrip+ has validation, iOS ports lack it
4. [x] Review date format handling in Trio's ISO8601 serializer → Not the issue
5. [x] Compare Loop vs Trio CGMBLEKit/G7SensorKit implementations
6. [ ] **Create PR for G7SensorKit stopgap fix** (similar to CGMBLEKit PR #191)
7. [x] Document all G6/G7 message types that affect timestamps → See xDrip formats below
8. [ ] Add message logging for unknown/malformed messages
9. [ ] **NEW: Implement message inventory logging** to detect firmware format changes
10. [ ] **NEW: Add firmware version registry** (similar to xDrip+ FirmwareCapability.java)
11. [ ] **NEW: Collect raw BLE samples** from users experiencing future-dated events
12. [x] **NEW: Analyze 2^32 overflow pattern** - CRITICAL FINDING!

## Root Cause Deep Dive

### ⚠️ CRITICAL FINDING: 2^32 Overflow Pattern

Analyzing the actual bad data from Issue #8453:
```
notes: "89N9W6 activated on 2025-06-04 19:56:03 +0000"  (CORRECT)
created_at: "2161-07-12T02:24:18.577Z"                   (WRONG)
```

The difference between wrong and correct dates is **EXACTLY 2^32 seconds**:

```python
correct_epoch = 1749092163  # 2025-06-04 19:56:03
wrong_epoch   = 6044059459  # 2161-07-12 02:24:19
difference    = 4294967296  # = 2^32 EXACTLY!
```

**This proves the bug is NOT in BLE message parsing!**

The `activationDate` is calculated correctly (as shown in the `notes` field), but somewhere in the serialization/upload chain, **2^32 seconds is being added to the epoch timestamp**.

### Hypothesis: Integer Type Confusion

Possible causes:
1. **iOS Date → TimeInterval → Int conversion** treats a signed 32-bit as unsigned
2. **JSON encoding** of epoch timestamp with incorrect type handling
3. **Network layer** sign extension issue when converting to 64-bit
4. **Nightscout API** or MongoDB driver issue with timestamp handling

### Diagnostic Investigation Matrix

| Location | What to Check | How to Verify | Status |
|----------|---------------|---------------|--------|
| G7Sensor.activationDate calculation | `Date() - TimeInterval(messageTimestamp)` | notes field shows CORRECT | ✅ Ruled Out |
| G7CGMManager.state.activatedAt | Stored in `[String: Any]` dict | Add logging at state save/load | ⬜ Unknown |
| PluginSource.sensorStartDate | Copied from `cgmTransmitterManager.sensorActivatedAt` | Add logging | ⬜ Unknown |
| BloodGlucose.sessionStartDate | JSON-encoded via `Codable` | Check ISO8601 output | ⬜ Unknown |
| GlucoseStorage.createCGMStateTreatment | Uses `sessionStartDate` as `createdAt` | Add logging | ⬜ Unknown |
| NightscoutTreatment JSON encoding | `JSONEncoder.dateEncodingStrategy = .customISO8601` | Print encoded JSON | 🔍 **Primary Suspect** |
| Nightscout API parseDate | Uses `moment.parseZone()` for ISO8601 | Server logs | ⬜ Unknown |
| MongoDB driver | Stores `Date` as BSON Date | Check DB directly | ⬜ Unknown |

### Diagnostic Tests to Add

**Test 1: Log the exact ISO8601 string being sent**

Add to `Trio/Sources/Services/Network/Nightscout/NightscoutManager.swift`:
```swift
private func uploadNonCoreDataTreatments(_ treatments: [NightscoutTreatment]) async {
    // DEBUG: Log exact JSON being sent
    for treatment in treatments {
        if treatment.eventType == .nsSensorChange {
            let json = treatment.rawJSON
            print("DEBUG_FUTURE_DATE: Sensor change treatment JSON: \(json)")
            print("DEBUG_FUTURE_DATE: createdAt Date object: \(String(describing: treatment.createdAt))")
        }
    }
    // ... rest of function
}
```

**Test 2: Verify ISO8601DateFormatter output**

```swift
let testDate = Date()
let formatter = ISO8601DateFormatter()
formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
let encoded = formatter.string(from: testDate)
let decoded = formatter.date(from: encoded)
print("Original: \(testDate.timeIntervalSince1970)")
print("Encoded: \(encoded)")
print("Decoded: \(decoded?.timeIntervalSince1970 ?? -1)")
// These should match exactly
```

**Test 3: Check state persistence round-trip**

Add to G7CGMManager:
```swift
func debugStateRoundTrip() {
    let original = state.activatedAt
    let rawValue = state.rawValue
    let restored = G7CGMManagerState(rawValue: rawValue)
    print("DEBUG_STATE: Original activatedAt: \(String(describing: original))")
    print("DEBUG_STATE: RawValue activatedAt: \(rawValue["activatedAt"] ?? "nil")")
    print("DEBUG_STATE: Restored activatedAt: \(String(describing: restored.activatedAt))")
}
```

### Data Collection Request

To diagnose this issue, we need users experiencing the bug to provide:

1. **Exact error case**: The full JSON of the bad treatment
2. **Device info**: iOS version, device model
3. **Timing**: When the sensor was actually started vs when the bug occurred
4. **Console logs**: Any DEBUG output from the diagnostic tests above
5. **Multiple samples**: Is the +2^32 offset consistent?

### Narrowed Suspicion List

Based on code analysis:

1. **Most Likely: JSON Encoding Path**
   - `NightscoutTreatment.rawJSON` uses `JSONCoding.encoder.encode()`
   - Encoder uses `.customISO8601` date strategy
   - The ISO8601 string itself might be generated incorrectly

2. **Possible: State Persistence Issue**
   - `G7CGMManagerState` stores `activatedAt` as `Date` in `[String: Any]`
   - When restored, `rawValue["activatedAt"] as? Date` might fail unexpectedly
   - Could default to wrong value

3. **Less Likely: Server-Side**
   - Server uses standard `moment.js` ISO8601 parsing
   - MIN_TIMESTAMP check exists but no MAX check

### Investigation Steps

```swift
// Where does the bug actually occur?
// 1. PersistedCgmEvent.date is set correctly (activatedAt)
// 2. During serialization to NightscoutTreatment...
// 3. Or during JSON encoding of created_at...
// 4. Or during upload to Nightscout API...

// Key: Find where epoch seconds are converted between 32-bit and 64-bit
```

### Why `activationDate` calculation is NOT the bug

In `G7Sensor.swift`:
```swift
// Line in handleGlucoseMessage()
activationDate = Date().addingTimeInterval(-TimeInterval(message.messageTimestamp))
```

`messageTimestamp` is parsed from EGV message bytes 2-5:
```swift
// G7GlucoseMessage.swift:91
messageTimestamp = data[2..<6].toInt()  // UInt32, always positive
```

**Possible corruption scenarios:**
1. BLE packet corruption → wrong bytes parsed
2. Partial message received → truncated data
3. Wrong opcode handling → different message format
4. Sensor firmware bug → incorrect timestamp in payload

### G6 vs G7 Stopgap Comparison

**G6 (CGMBLEKit) - Fixed:**
```swift
// CGMBLEKit/TransmitterManager.swift:340-347
events = events.filter { event in
    if event.date > Date() {
        log.error("Future-dated event detected: %{public}@", String(describing: event))
        return false
    }
    return true
}
```

**G7 (G7SensorKit) - Missing fix:**
```swift
// G7SensorKit/G7CGMManager/G7CGMManager.swift:311-315
let event = PersistedCgmEvent(
    date: activatedAt,  // NO VALIDATION
    type: .sensorStart,
    ...
)
delegate.notify { delegate in
    delegate?.cgmManager(self, hasNew: [event])  // Sent directly
}
```

### Infinite Loop Concern

The cgm-remote-monitor issue raised a valid concern:

1. Client (Trio) creates event with future date
2. Trio uploads to Nightscout
3. If Nightscout rejects → Trio retries (it thinks upload failed)
4. Loop continues indefinitely

**This is why server-side rejection must be paired with client-side validation.**

## Recommended Fix Strategy

### Phase 1: G7SensorKit Stopgap (Highest Priority)

**File**: `G7SensorKit/G7SensorKit/G7CGMManager/G7CGMManager.swift`
**Location**: Around line 305-320, in `sensor(_:didDiscoverNewSensor:activatedAt:)`

**Current Code** (lines 305-320):
```swift
if shouldSwitchToNewSensor {
    mutateState { state in
        state.sensorID = name
        state.activatedAt = activatedAt
    }
    let event = PersistedCgmEvent(
        date: activatedAt,
        type: .sensorStart,
        deviceIdentifier: name,
        expectedLifetime: lifetime + G7Sensor.gracePeriod,
        warmupPeriod: warmupDuration
    )
    delegate.notify { delegate in
        delegate?.cgmManager(self, hasNew: [event])
    }
}
```

**Proposed Fix** (add validation before creating event):
```swift
if shouldSwitchToNewSensor {
    // Stopgap: Reject future-dated sensor activations
    // See: https://github.com/LoopKit/Loop/issues/2087
    // See: https://github.com/nightscout/cgm-remote-monitor/issues/8453
    guard activatedAt <= Date() else {
        log.error("Future-dated sensor activation detected, not uploading: %{public}@", 
                  String(describing: activatedAt))
        return false
    }
    
    mutateState { state in
        state.sensorID = name
        state.activatedAt = activatedAt
    }
    // ... rest unchanged
}
```

**Reference**: This mirrors the fix in CGMBLEKit PR #191:
- `CGMBLEKit/CGMBLEKit/TransmitterManager.swift` lines 340-347

### Phase 2: LibreTransmitter Audit (Medium Priority)

**File**: `LibreTransmitter/LibreTransmitter/LibreTransmitterManager+Transmitters.swift`
**Concern**: Same pattern - `Date() - TimeInterval(minutes: minutesSinceStart)`

```swift
// Current code
verifySensorChange(for: sensorData.uuid, 
    activatedAt: Date() - TimeInterval(minutes: Double(sensorData.minutesSinceStart)))
```

If `minutesSinceStart` is negative (corrupt), this produces a future date.

**Proposed**: Add validation in `verifySensorChange()` or before calling it.

### Phase 3: Server-Side Warning (Defense in Depth)

**File**: `cgm-remote-monitor/lib/api3/shared/operationTools.js`
**Function**: `validateCommon()`

Add after MIN_TIMESTAMP check:
```javascript
const MAX_FUTURE_MS = 24 * 60 * 60 * 1000; // 24 hours
if (doc.date > Date.now() + MAX_FUTURE_MS) {
    console.warn('Future-dated document detected:', 
        doc.identifier, new Date(doc.date), doc.app);
    // Phase 3a: Log only (don't reject yet - causes infinite retry)
    // Phase 3b: After client fixes deployed, add rejection
}
```

**Warning**: Do NOT reject until client fixes are deployed - causes infinite retry loops.

### Phase 4: Enhanced Logging for R&D (Message Inventory)

The future-dated timestamps may indicate **message format changes between CGM firmware versions**. Rather than parsing incorrect byte fields, we need comprehensive logging to build an inventory of actual message formats seen in the wild.

#### Hypothesis: Format Drift

| Possibility | Evidence | Implication |
|-------------|----------|-------------|
| Firmware version changed field layout | G7 has multiple firmware releases | Parsing offset wrong for new versions |
| Different transmitter models send different formats | G7 ONE vs G7 Pro variants | Need model-specific parsing |
| Sensor vs transmitter messages confused | Both emit on same characteristic | Opcode disambiguation needed |

#### Proposed Logging Strategy

**Step 1: Log ALL messages with opcode inventory**

Add to G7Sensor.swift around line 129:
```swift
activationDate = Date().addingTimeInterval(-TimeInterval(message.messageTimestamp))

// R&D: Log raw message for format inventory
let rawHex = message.data.hexadecimalString
let parsedTimestamp = message.messageTimestamp
let calculatedDate = activationDate

log.default("G7_MSG_INVENTORY: opcode=0x%02X len=%d raw=%@ parsed_ts=%u calc_date=%@",
            message.opcode, message.data.count, rawHex, parsedTimestamp, 
            String(describing: calculatedDate))

// Alert on anomaly for investigation
if let activationDate = activationDate, activationDate > Date() {
    log.error("FUTURE_DATE_ANOMALY: messageTimestamp=%u raw=%@ calculated=%@",
              parsedTimestamp, rawHex, String(describing: activationDate))
}
```

**Step 2: Log transmitter identification**

```swift
// On connection, log transmitter firmware version for correlation
log.default("G7_TRANSMITTER_ID: serial=%@ firmware=%@ hardware=%@",
            transmitterID, firmwareVersion ?? "unknown", hardwareVersion ?? "unknown")
```

**Step 3: Create server-side message collection**

Add to Nightscout `devicestatus` uploads:
```javascript
{
  "device": "G7SensorKit",
  "pump": { /* existing */ },
  "cgm": {
    "messageInventory": [
      { "opcode": "0x4E", "len": 19, "raw": "4e00d5070000...", "parsedTs": 2005 }
    ]
  }
}
```

This enables:
1. Cross-device comparison of message formats
2. Correlation of anomalies with specific firmware versions
3. Detection of format changes over time

#### xDrip+ Reference: Firmware Version Registry

xDrip+ maintains a **known firmware registry** in `FirmwareCapability.java`:

```java
// Known firmware versions with different capabilities
private static final ImmutableSet<String> KNOWN_G5_FIRMWARES = 
    ImmutableSet.of("1.0.0.13", "1.0.0.17", "1.0.4.10", "1.0.4.12");
private static final ImmutableSet<String> KNOWN_G6_FIRMWARES = 
    ImmutableSet.of("1.6.5.23", "1.6.5.25", "1.6.5.27");
private static final ImmutableSet<String> KNOWN_G6_REV2_FIRMWARES = 
    ImmutableSet.of("2.18.2.67", "2.18.2.88", "2.27.2.98", "2.27.2.103");
private static final ImmutableSet<String> KNOWN_ONE_FIRMWARES = 
    ImmutableSet.of("30.192.103.34");
private static final ImmutableSet<String> KNOWN_ALT_FIRMWARES = 
    ImmutableSet.of("29.192.104.59", "32.192.104.82", "44.192.105.72");
```

This allows xDrip+ to:
- Detect firmware version changes
- Apply version-specific parsing rules
- Log unknown firmware versions for investigation

**iOS ports should consider similar versioning** to handle format drift gracefully.

#### Expected Outcomes

After collecting sufficient inventory data:
1. Identify which firmware versions produce future-dated events
2. Discover if byte layout changed (offset drift)
3. Create firmware-version-specific parsers if needed
4. Document confirmed message formats by version

This captures the raw BLE hex when anomalies occur, enabling root cause analysis of potential format drift.

## Test Plan

### Unit Tests (Swift - requires Xcode)

Add to `G7SensorKitTests/G7GlucoseMessageTests.swift`:

```swift
func testFutureDateDetection() {
    // Construct a message with messageTimestamp that would produce future date
    // messageTimestamp = UInt32.max would mean activationDate = Date() - 136 years = far past
    // So future dates must come from somewhere else...
    
    // Test: Normal 10-day sensor (864000 seconds)
    let normalData = Data(hexadecimalString: "4e0000320d00...")!  // 864000 = 0x000D3200
    let normalMsg = G7GlucoseMessage(data: normalData)!
    XCTAssertEqual(864000, normalMsg.messageTimestamp)
    
    // Test: Edge case - messageTimestamp = 0 (brand new sensor)
    // activationDate = Date() - 0 = now (valid)
    
    // Test: Large messageTimestamp (sensor expired)
    // activationDate = Date() - large = past (valid)
}

func testBackfillTimestampEdgeCases() {
    // Test 24-bit timestamp overflow scenarios
    // Max 24-bit = 16,777,215 seconds = ~194 days (within sensor lifetime)
}
```

### Integration Tests (requires actual sensor or mock)

1. Simulate BLE packet with corrupted timestamp bytes
2. Verify G7CGMManager rejects future-dated events
3. Verify logging captures raw hex for analysis

### Nightscout API Tests (can run on Linux)

Add to `tests/api.treatments.test.js`:
```javascript
it('should warn on future-dated treatments', async () => {
    const futureDate = new Date(Date.now() + 48 * 60 * 60 * 1000); // +48h
    const treatment = {
        eventType: 'Sensor Start',
        created_at: futureDate.toISOString(),
        enteredBy: 'test'
    };
    
    // For now: should succeed but log warning
    // After client fixes: should reject with HTTP 400
    const res = await request.post('/api/v1/treatments')
        .send(treatment);
    
    // Check server logs for warning
});
```

1. Create test treatments with:
   - `created_at` = now + 1 day (should pass?)
   - `created_at` = now + 1 week (should warn?)
   - `created_at` = now + 1 year (should reject?)
   
2. Verify `futureitems.js` admin plugin continues working

3. Check time-range query behavior with future items

## Related Files

**Nightscout**:
- `lib/api3/shared/operationTools.js:validateCommon()`
- `lib/api3/const.json` - MIN_TIMESTAMP constant
- `lib/admin_plugins/futureitems.js` - cleanup admin

**Loop (LoopWorkspace)**:
- `G7SensorKit/G7SensorKit/G7CGMManager/G7Sensor.swift` - activation date calc
- `G7SensorKit/G7SensorKit/G7CGMManager/G7CGMManager.swift:311` - event creation (NO FILTER)
- `G7SensorKit/G7SensorKit/Messages/G7GlucoseMessage.swift` - message parsing
- `CGMBLEKit/CGMBLEKit/TransmitterManager.swift:340-347` - G6 stopgap (HAS FILTER)
- `NightscoutService/NightscoutServiceKit/Extensions/PersistedCgmEvent.swift` - NS upload

**Trio**:
- `G7SensorKit/G7SensorKit/G7CGMManager/G7CGMManager.swift:311` - same as Loop (NO FILTER)
- `CGMBLEKit/CGMBLEKit/TransmitterManager.swift:342` - G6 stopgap (HAS FILTER)
- `Trio/Sources/Models/NightscoutTreatment.swift` - created_at field
- `Trio/Sources/Models/PumpHistoryEvent.swift` - Sensor Start event type

## G6/G7 Message Parsing Documentation

### xDrip+ as Reference Implementation

xDrip+ (Android) has the most complete G6/G7 message parsing with **built-in future-date protection**.

**Location**: `externals/xDrip/app/src/main/java/com/eveningoutpost/dexdrip/g5model/`

#### Key Time Validation in xDrip+

**File**: `DexTimeKeeper.java:49-53`
```java
if (activation_time > JoH.tsl()) {
    UserError.Log.wtf(TAG, "Transmitter activation time is in the future. Not possible to update: " + dexTimeStamp);
    return;
}
```

**File**: `StartNewSensor.java:224-226`
```java
if (new Date().getTime() + 15 * 60000 < startTime) {
    Toast.makeText(this, gs(R.string.error_sensor_start_time_in_future), Toast.LENGTH_LONG).show();
    return;
}
```

xDrip+ allows max **15 minutes** future time for sensor start.

### Cross-Codebase Parsing Comparison (G7 EGV 0x4E)

**All codebases agree on byte layout:**
```
 0  1  2 3 4 5  6 7  8  9 10 11 12 13 14 15 16 17 18
       TTTTTTTT SQSQ       AGAG  BGBG  SS TR PRPR  C
4e 00 d5070000 0900 00 01 0500  6100  06 01 ffff 0e
```

| Field | Bytes | G7SensorKit | DiaBLE | xDrip+ | xDrip4iOS |
|-------|-------|-------------|--------|--------|-----------|
| opcode | 0 | ✅ 0x4E | ✅ 0x4E | ✅ 0x4E | ✅ 0x4E |
| status | 1 | ✅ check=0 | ✅ check | ✅ read | ✅ check=0 |
| **messageTimestamp** | 2-5 | ✅ UInt32 | ✅ UInt32 | ✅ getUnsignedInt | ✅ UInt32 |
| sequence | 6-7 | ✅ UInt16 | ✅ UInt16 | ✅ getUnsignedShort | ✅ UInt16 |
| reserved | 8-9 | skip | skip | ✅ "bogus" | skip |
| **age** | 10-11 | ✅ UInt16 | ✅ UInt16 | ✅ getUnsignedShort | ⚠️ **data[10] only!** |
| glucose | 12-13 | ✅ mask 0xfff | ✅ mask 0xfff | ✅ mask 0xfff | ✅ mask 0xfff |
| state | 14 | ✅ byte | ✅ byte | ✅ byte | ✅ byte |
| trend | 15 | ✅ signed/10 | ✅ signed/10 | ✅ signed/10 | ✅ signed/10 |
| predicted | 16-17 | ✅ mask 0xfff | ✅ mask 0xfff | ✅ mask 0x3ff | ✅ mask 0xfff |
| calibration | 18 | ✅ displayOnly | ✅ displayOnly | read | ✅ displayOnly |

### ⚠️ Parsing Discrepancy Found!

**xDrip4iOS reads `age` as 1 byte instead of 2!**

| Codebase | Age Parsing | Result |
|----------|-------------|--------|
| G7SensorKit | `data[10..<12].to(UInt16.self)` | **2 bytes (correct)** |
| DiaBLE | `UInt16(data[10..<12])` | **2 bytes (correct)** |
| xDrip+ (Android) | `getUnsignedShort(data)` | **2 bytes (correct)** |
| **xDrip4iOS** | `data[10]` | **1 byte (WRONG!)** |

**Impact**: If `age` field uses byte 11 (high byte of UInt16), xDrip4iOS would misparse the age value.

**File**: `externals/xdripswift/xdrip/BluetoothTransmitter/CGM/Dexcom/Generic/DexcomG7GlucoseDataRxMessage.swift:59`
```swift
// xDrip4iOS (POTENTIALLY WRONG)
let messageAge = data[10]  // Only reads 1 byte!

// Should be:
let messageAge = data[10..<12].to(UInt16.self)  // 2 bytes like others
```

### How Dates are Calculated

| Codebase | Activation Date Calculation | Glucose Timestamp |
|----------|----------------------------|-------------------|
| **G7SensorKit** | Not calculated in message | `messageTimestamp - age` → `glucoseTimestamp` |
| **DiaBLE** | `Date.now - TimeInterval(txTime)` | `activationDate + TimeInterval(timestamp)` |
| **xDrip+** | Uses DexTimeKeeper | `JoH.tsl() - (age * SECOND_IN_MS)` |
| **xDrip4iOS** | Not calculated | `Date() - TimeInterval(messageAge)` |

**Key Insight**: The date calculation approaches differ:

1. **G7SensorKit** (Loop/Trio): Calculates `activationDate` from `messageTimestamp`, then uses it for events
2. **DiaBLE**: Same approach, calculates activation date fresh each message
3. **xDrip+**: Uses stored `DexTimeKeeper.fromDexTime()` with validation
4. **xDrip4iOS**: **Simpler - just uses `now - age`** (avoids activation date issues)

### Well-Documented Messages

| Opcode | Name | File | Test Coverage |
|--------|------|------|---------------|
| 0x4E | EGV (Glucose) | `G7GlucoseMessage.swift` | ✅ Extensive (14 tests) |
| 0x59 | Backfill | `G7BackfillMessage.swift` | ✅ Good (4 tests) |
| 0x31 | GlucoseRx (G6) | `GlucoseRxMessage.swift` | ✅ Good |

### xDrip G6 Message Formats (Reference)

**EGlucoseRxMessage.java (opcode 0x4F - G6)**
```java
// Offset  Size  Field
// 0       1     opcode (0x4F)
// 1       1     status
// 2-5     4     sequence (UInt32)
// 6-9     4     timestamp (UInt32 - seconds since transmitter start)
// 10-11   2     glucose (bits 0-11 = glucose, bit 12+ = displayOnly)
// 12      1     state (calibration state)
// 13      1     trend (signed, ÷10 for mg/dL/min)
// 14-15   2     predicted_glucose (masked)
```

**EGlucoseRxMessage.java (opcode 0x4E - G7)**
```java
// Offset  Size  Field
// 0       1     opcode (0x4E)
// 1       1     status_raw
// 2-5     4     clock (UInt32 - seconds since sensor start)
// 6-7     2     sequence
// 8-9     2     bogus (padding?)
// 10-11   2     age (seconds since reading was taken)
// 12-13   2     glucose (bits 0-11 = glucose, bit 12+ = displayOnly)
// 14      1     state
// 15      1     trend
// 16-17   2     predicted_glucose
```

**Key Difference**: G7 uses `age` field to compute `timestamp = now - age`.

**SessionStartRxMessage.java (opcode 0x27)**
```java
// Offset  Size  Field
// 0       1     opcode (0x27)
// 1       1     status
// 2       1     info (session state: 0x01=OK, 0x02=AlreadyStarted, 0x04=ClockNotSynced)
// 3-6     4     requestedStartTime (DexTime - seconds since transmitter activation)
// 7-10    4     sessionStartTime (DexTime)
// 11-14   4     transmitterTime (DexTime - current clock)
// 15-16   2     CRC
// Length: 17 bytes

// Session start is computed as: DexTimeKeeper.fromDexTime(transmitterId, sessionStartTime)
// DexTimeKeeper stores transmitter activation time, then adds sessionStartTime seconds
```

**TransmitterTimeRxMessage.java (opcode 0x25)**
```java
// Offset  Size  Field
// 0       1     opcode (0x25)
// 1       1     status (battery level)
// 2-5     4     currentTime (DexTime - seconds since transmitter activation)
// 6-9     4     sessionStartTime (DexTime - when current session started, -1 if none)
// Length: 10+ bytes (may have more)

// Real session start computed as: now - ((currentTime - sessionStartTime) * 1000L)
// If currentTime == sessionStartTime, no session in progress
```

### Needs Investigation

| Opcode | Name | Concern |
|--------|------|---------|
| 0x4A | TransmitterVersion | Contains session start info? |
| 0x28 | SessionStop | Timestamp handling? |
| 0x22 | BatteryStatus | Runtime calculations? |

## References

- GAP-API-021 in `traceability/nightscout-api-gaps.md`
- REQ-TS-001 in `traceability/nightscout-api-requirements.md`
- [G7 Protocol Specification](../10-domain/g7-protocol-specification.md)
