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

### Phase 1: Client-Side (Prevent at source)

Add to `G7CGMManager.swift` after line 311:
```swift
// Validate activatedAt is not in the future
guard activatedAt <= Date() else {
    log.error("Future-dated sensor activation detected: %{public}@", 
              String(describing: activatedAt))
    // Don't create or report the event
    return false
}
```

### Phase 2: Server-Side (Defense in depth)

Add to `validateCommon()` with **warning only** initially:
```javascript
const MAX_FUTURE_MS = 24 * 60 * 60 * 1000;
if (doc.date > Date.now() + MAX_FUTURE_MS) {
    console.warn('Future-dated document:', doc.identifier, new Date(doc.date));
    // Phase 2a: Log only
    // Phase 2b: Return HTTP 400 after clients are fixed
}
```

### Phase 3: Message Auditing

Create comprehensive test coverage for all G6/G7 message types:
- EGV (0x4E) - already well tested
- Backfill (0x59) - tested
- Session Start/Stop - need more coverage
- Error conditions and malformed messages

## Test Plan

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

### Well-Documented Messages

| Opcode | Name | File | Test Coverage |
|--------|------|------|---------------|
| 0x4E | EGV (Glucose) | `G7GlucoseMessage.swift` | ✅ Extensive (14 tests) |
| 0x59 | Backfill | `G7BackfillMessage.swift` | ✅ Good (4 tests) |
| 0x31 | GlucoseRx (G6) | `GlucoseRxMessage.swift` | ✅ Good |

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
