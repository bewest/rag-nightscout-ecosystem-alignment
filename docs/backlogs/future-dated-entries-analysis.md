# Future-Dated Entries Analysis

**Created**: 2026-03-15
**Updated**: 2026-03-15
**Issue References**: 
- [LoopKit/Loop#2087](https://github.com/LoopKit/Loop/issues/2087)
- [nightscout/cgm-remote-monitor#8453](https://github.com/nightscout/cgm-remote-monitor/issues/8453)
- [LoopKit/CGMBLEKit#191](https://github.com/LoopKit/CGMBLEKit/pull/191) - G6 partial stopgap fix
**Gap**: GAP-API-021

## ⚠️ ROOT CAUSE CONFIRMED (2026-03-15)

**The bug is in G6 (CGMBLEKit), NOT G7!** Sensor ID "89N9W6" is a G6 transmitter ID format.

### The Exact Bug Path

```
1. G6 transmitter returns sessionStartTime = 0xFFFFFFFF (no active session sentinel)
   └── TransmitterTimeRxMessage.sessionStartTime = 4,294,967,295

2. Glucose.swift:52 calculates corrupt sessionStartDate:
   └── sessionStartDate = activationDate + 4,294,967,295 seconds = 136 YEARS FUTURE

3. CGMBLEKit PR #191 stopgap ONLY filters PersistedCgmEvent objects
   └── Does NOT fix Glucose.sessionStartDate property!

4. PluginSource.swift:226 reads corrupt date (NO VALIDATION):
   └── sensorStartDate = latestReading?.sessionStartDate  // Still corrupt!

5. BloodGlucose stores corrupt sessionStartDate
   └── sessionStartDate: sensorStartDate

6. GlucoseStorage creates NightscoutTreatment with corrupt date:
   └── createdAt: sessionStartDate  // 2161-07-12!

7. Uploaded to Nightscout → SAGE/CAGE broken
```

### Math Verification

```python
notes (activationDate):     "2025-06-04 19:56:03"
created_at (sessionStartDate): "2161-07-12T02:24:18"

Difference = 4,294,967,295 seconds = 0xFFFFFFFF EXACTLY!
```

### Why the Existing Stopgap Doesn't Work

The PR #191 fix filters `PersistedCgmEvent` objects AFTER they're created:

```swift
// TransmitterManager.swift:338-346 - THIS ONLY FILTERS EVENTS
events = events.filter { event in
    if event.date > Date() {
        log.error("Future-dated event detected: %{public}@", String(describing: event))
        return false
    }
    return true
}
```

But `Glucose.sessionStartDate` is a PUBLIC PROPERTY that other code reads directly:

```swift
// PluginSource.swift:226 - READS CORRUPT VALUE DIRECTLY
sensorStartDate = latestReading?.sessionStartDate  // No validation!
```

### Required Fix Locations

| Location | Current State | Required Fix |
|----------|---------------|--------------|
| `CGMBLEKit/Glucose.swift:52` | Blindly adds sessionStartTime | Check for `0xFFFFFFFF` sentinel |
| `PluginSource.swift:221,226` | Reads sessionStartDate without validation | Add future date check |
| `GlucoseStorage.swift:241` | Uses sessionStartDate directly | Add validation before creating treatment |

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
6. [x] ~~Create PR for G7SensorKit stopgap fix~~ → **WRONG TARGET - issue is G6/CGMBLEKit**
7. [x] Document all G6/G7 message types that affect timestamps → See xDrip formats below
8. [ ] Fix PluginSource.swift to validate sessionStartDate before use
9. [ ] Fix Glucose.swift to detect 0xFFFFFFFF sentinel and use nil instead
10. [x] **CRITICAL: Analyze 2^32 overflow pattern** - ROOT CAUSE CONFIRMED!

## Root Cause Deep Dive

### ✅ ROOT CAUSE CONFIRMED: G6 sessionStartTime = 0xFFFFFFFF Sentinel

**The bug is in CGMBLEKit (G6), NOT G7SensorKit!**

Sensor ID "89N9W6" is a G6 transmitter ID format (6 alphanumeric characters). G7 uses 4-digit pairing codes.

Analyzing the actual bad data from Issue #8453:
```
notes: "89N9W6 activated on 2025-06-04 19:56:03 +0000"  (CORRECT - activationDate)
created_at: "2161-07-12T02:24:18.577Z"                   (WRONG - sessionStartDate)
```

The difference is **EXACTLY 0xFFFFFFFF seconds** (4,294,967,295):

```python
correct_epoch = 1749092163  # 2025-06-04 19:56:03 (activationDate)
wrong_epoch   = 6044059458  # 2161-07-12 02:24:18 (sessionStartDate)
difference    = 4294967295  # = 0xFFFFFFFF EXACTLY!
```

### The Bug Mechanism

When a G6 transmitter has **no active sensor session**, it returns `sessionStartTime = 0xFFFFFFFF` as a sentinel value:

```swift
// TransmitterTimeRxMessage.swift - test shows sentinel
XCTAssertEqual(0xffffffff, message.sessionStartTime)  // No session active
```

This value flows directly into `Glucose.sessionStartDate`:

```swift
// CGMBLEKit/Glucose.swift:52 - THE BUG
sessionStartDate = activationDate.addingTimeInterval(TimeInterval(timeMessage.sessionStartTime))
// When sessionStartTime = 0xFFFFFFFF:
// sessionStartDate = 2025-06-04 + 4,294,967,295 seconds = 2161-07-12 !!!
```

### Why the PR #191 Stopgap Doesn't Fix This

PR #191 added filtering for `PersistedCgmEvent` objects:

```swift
// TransmitterManager.swift:340-345 - Only filters EVENTS
events = events.filter { event in
    if event.date > Date() { return false }
    return true
}
```

But `Glucose.sessionStartDate` is a **public property** that other code reads directly:

```swift
// PluginSource.swift:226 - BYPASSES THE FILTER
sensorStartDate = latestReading?.sessionStartDate  // Still corrupt!
```

### Correct Fix Required

**Option A: Fix at source (Glucose.swift)**
```swift
// Check for sentinel value before calculation
if timeMessage.sessionStartTime == UInt32.max {
    sessionStartDate = activationDate  // Use activationDate as fallback
} else {
    sessionStartDate = activationDate.addingTimeInterval(TimeInterval(timeMessage.sessionStartTime))
}
```

**Option B: Fix at consumer (PluginSource.swift)**
```swift
// Validate sessionStartDate before use
if let sessionStart = latestReading?.sessionStartDate,
   sessionStart <= Date().addingTimeInterval(86400) {  // Max 24h future
    sensorStartDate = sessionStart
} else {
    sensorStartDate = latestReading?.activationDate  // Fallback
}
```

**Option C: Fix at storage (GlucoseStorage.swift)**
```swift
// In storeCGMState()
guard let sessionStartDate = x.sessionStartDate,
      sessionStartDate <= Date().addingTimeInterval(86400) else { continue }
```

### Previous Wrong Hypotheses (Ruled Out)

| Candidate | Why Ruled Out |
|-----------|---------------|
| G7SensorKit issue | Sensor ID "89N9W6" is G6 format, not G7 |
| BLE message parsing | `notes` (activationDate) is CORRECT |
| State persistence corruption | The corruption is deterministic (0xFFFFFFFF sentinel) |
| JSON encoding issue | Corruption happens before encoding |
| Server-side MongoDB | Data arrives corrupt from client |


### Diagnostic Investigation Matrix (UPDATED)

| Priority | Location | What to Check | Status |
|----------|----------|---------------|--------|
| ✅ | CGMBLEKit/Glucose.swift:52 | `sessionStartTime = 0xFFFFFFFF` sentinel | **ROOT CAUSE CONFIRMED** |
| ✅ | PluginSource.swift:226 | Reads corrupt `sessionStartDate` without validation | **BYPASS IDENTIFIED** |
| ✅ | GlucoseStorage.swift:241 | Uses corrupt `sessionStartDate` as `createdAt` | **FLOW CONFIRMED** |
| - | G7SensorKit | Not applicable - this is a G6 issue | ~~Ruled Out~~ |

### Required Code Changes

**Fix 1: CGMBLEKit/Glucose.swift (Best - fix at source)**

```swift
// Line 52 - current bug:
sessionStartDate = activationDate.addingTimeInterval(TimeInterval(timeMessage.sessionStartTime))

// Fixed version:
if timeMessage.sessionStartTime == UInt32.max {
    // 0xFFFFFFFF means no active session - use activationDate as fallback
    sessionStartDate = activationDate
} else {
    sessionStartDate = activationDate.addingTimeInterval(TimeInterval(timeMessage.sessionStartTime))
}
```

**Fix 2: Trio/PluginSource.swift (Defense in depth)**

```swift
// Lines 221, 226 - add validation:
if let sessionStart = latestReading?.sessionStartDate,
   sessionStart > Date().addingTimeInterval(-86400 * 365),  // Not > 1 year past
   sessionStart <= Date().addingTimeInterval(86400) {       // Not > 1 day future
    sensorStartDate = sessionStart
} else {
    sensorStartDate = latestReading?.activationDate  // Fallback to correct date
}
```

**Fix 3: GlucoseStorage.swift (Final safety net)**

```swift
// Line 230 - add guard:
guard let sessionStartDate = x.sessionStartDate,
      sessionStartDate <= Date().addingTimeInterval(86400) else {
    debug(.deviceManager, "Skipping CGM state with invalid sessionStartDate: \(String(describing: x.sessionStartDate))")
    continue
}
```

### Existing iOS Logging Analysis

**Current logging IS available but NOT sufficient for diagnosis:**

| Code Path | Existing Logging | What's Logged | What's Missing |
|-----------|------------------|---------------|----------------|
| CGMBLEKit TransmitterManager | ✅ `log.error()` | Future events filtered | Only logs filtered events, not the corrupt sessionStartDate |
| PluginSource | ❌ None | - | No logging when reading sessionStartDate |
| GlucoseStorage.storeCGMState() | ✅ `debug(.deviceManager, ...)` | `"CGM sensor change \(treatment)"` | Treatment description, not dates |
| NightscoutManager | ✅ `debug(.nightscout, ...)` | `"Treatments uploaded"` | **No treatment content logged!** |

**Key Logging Gaps:**

1. **No logging of actual JSON payload** being sent to Nightscout
2. **No logging of `created_at` ISO8601 string** after encoding
3. **No comparison of Date object vs encoded string**

### Enhanced Logging Proposal

To diagnose the 2^32 issue, add these logs to `NightscoutManager.swift`:

```swift
private func uploadNonCoreDataTreatments(_ treatments: [NightscoutTreatment]) async {
    guard !treatments.isEmpty, let nightscout = nightscoutAPI, isUploadEnabled else {
        return
    }
    
    // DIAGNOSTIC: Log Sensor Start treatments specifically
    for treatment in treatments {
        if treatment.eventType == .nsSensorChange {
            let dateObj = treatment.createdAt
            let json = treatment.rawJSON
            debug(.nightscout, "SENSOR_CHANGE_DEBUG: Date object = \(String(describing: dateObj))")
            debug(.nightscout, "SENSOR_CHANGE_DEBUG: timeIntervalSince1970 = \(dateObj?.timeIntervalSince1970 ?? -1)")
            debug(.nightscout, "SENSOR_CHANGE_DEBUG: rawJSON = \(json)")
            
            // Check for future date
            if let date = dateObj, date > Date().addingTimeInterval(86400) {
                warning(.nightscout, "FUTURE_DATE_DETECTED: \(json)")
            }
        }
    }
    // ... existing code
}
```

**Add to GlucoseStorage.swift:**

```swift
private func createCGMStateTreatment(sessionStartDate: Date, notes: String) -> NightscoutTreatment {
    // DIAGNOSTIC: Log raw date values
    debug(.deviceManager, "CGM_TREATMENT_DEBUG: sessionStartDate = \(sessionStartDate)")
    debug(.deviceManager, "CGM_TREATMENT_DEBUG: epoch = \(sessionStartDate.timeIntervalSince1970)")
    
    return NightscoutTreatment(
        // ...
        createdAt: sessionStartDate,
        // ...
    )
}
```

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
