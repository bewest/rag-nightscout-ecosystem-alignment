# Future-Dated Entries Analysis

**Created**: 2026-03-15
**Issue References**: 
- [LoopKit/Loop#2087](https://github.com/LoopKit/Loop/issues/2087)
- [nightscout/cgm-remote-monitor#8453](https://github.com/nightscout/cgm-remote-monitor/issues/8453)
**Gap**: GAP-API-021

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

1. [ ] Find where Trio generates `Sensor Start` treatments
2. [ ] Trace date flow from G7Sensor → NightscoutTreatment
3. [ ] Check if AAPS/xDrip+ have similar issues
4. [ ] Review date format handling in Trio's ISO8601 serializer
5. [ ] Check for similar issues in other treatment types

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

**Loop/Trio (G7SensorKit)**:
- `G7SensorKit/G7CGMManager/G7Sensor.swift` - activation date calc
- `NightscoutService/NightscoutServiceKit/Extensions/PersistedCgmEvent.swift` - treatment creation

**Trio**:
- `Trio/Sources/Models/NightscoutTreatment.swift` - created_at field
- `Trio/Sources/Models/PumpHistoryEvent.swift` - Sensor Start event type

## References

- GAP-API-021 in `traceability/nightscout-api-gaps.md`
- REQ-TS-001 in `traceability/nightscout-api-requirements.md`
