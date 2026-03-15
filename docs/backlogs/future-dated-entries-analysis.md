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
3. [x] Check if AAPS/xDrip+ have similar issues → Need investigation
4. [x] Review date format handling in Trio's ISO8601 serializer → Not the issue
5. [x] Compare Loop vs Trio CGMBLEKit/G7SensorKit implementations
6. [ ] **Create PR for G7SensorKit stopgap fix** (similar to CGMBLEKit PR #191)
7. [ ] Document all G6/G7 message types that affect timestamps
8. [ ] Add message logging for unknown/malformed messages

## Root Cause Deep Dive

### Why `activationDate` can be wrong

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

### Phase 4: Enhanced Logging for R&D

Add to G7Sensor.swift around line 129:
```swift
activationDate = Date().addingTimeInterval(-TimeInterval(message.messageTimestamp))

// Debug logging for future date investigation
if let activationDate = activationDate, activationDate > Date() {
    log.error("FUTURE_DATE_DEBUG: messageTimestamp=%u, raw=%@, calculated=%@",
              message.messageTimestamp,
              message.data.hexadecimalString,
              String(describing: activationDate))
}
```

This captures the raw BLE hex when corruption occurs, enabling root cause analysis.

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
