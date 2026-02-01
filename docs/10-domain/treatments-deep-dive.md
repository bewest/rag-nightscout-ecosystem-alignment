# Treatments Collection Deep Dive

This document provides comprehensive field-by-field mapping of treatment events across AID systems (Loop, AAPS, Trio) and data uploaders (xDrip+) to the Nightscout `treatments` collection.

**Traceability Matrix**: [`traceability/domain-matrices/treatments-matrix.md`](../../traceability/domain-matrices/treatments-matrix.md) — 35 REQs, 9 GAPs, 20% assertion coverage

---

## Overview

The Nightscout `treatments` collection stores all user interventions and therapy events:
- **Boluses**: Manual and automatic insulin deliveries
- **Carb entries**: Carbohydrate consumption records
- **Temp basals**: Temporary basal rate modifications
- **Device events**: Sensor starts, site changes, pump events

Each AID system has its own internal data model that must be translated to/from Nightscout's format.

---

## Bolus Events

### Field Mapping

| Field | Nightscout | Loop | AAPS | Trio | xDrip+ |
|-------|------------|------|------|------|--------|
| **Insulin amount** | `insulin` | `deliveredUnits` / `programmedUnits` | `amount` | via LoopKit `DoseEntry` | `insulin` |
| **Timestamp** | `created_at` | `startDate` | `timestamp` | `startDate` | `timestamp` |
| **Event type** | `eventType` | Inferred from context | `type` enum | Inferred | `eventType` |
| **Sync identity** | `identifier` / `syncIdentifier` | `syncIdentifier` | `interfaceIDs.nightscoutId` | `syncIdentifier` | `uuid` |
| **Automatic flag** | `automatic` | `automatic` | N/A (via `type`) | `automatic` | N/A |
| **Notes** | `notes` | `description` | `notes` | N/A | `notes` |
| **Insulin type** | `insulinType` | `insulinType?.brandName` | `insulinConfiguration` | N/A | `insulinJSON` (multi-insulin) |

### Bolus Types Comparison

| System | Type Field | Values | NS eventType Mapping |
|--------|------------|--------|---------------------|
| **Loop** | `DoseType` | `.bolus` (single type) | `Meal Bolus` or `Correction Bolus` |
| **AAPS** | `Bolus.Type` | `NORMAL`, `SMB`, `PRIMING` | `Meal Bolus`, `Correction Bolus`, `SMB`, `Prime` |
| **Trio** | `DoseType` | `.bolus` (inherited from LoopKit) | Same as Loop |
| **xDrip+** | `eventType` | Free string | `<none>` default |

### SMB (Super Micro Bolus) Representation

| System | SMB Handling |
|--------|-------------|
| **Loop** | No SMB support (temp basal only) |
| **AAPS** | `Bolus.Type.SMB` → `eventType: "Correction Bolus"` with `type: "SMB"` field |
| **Trio** | oref1 SMBs uploaded as regular boluses with `automatic: true` |
| **Nightscout** | No explicit SMB eventType; relies on `type: "SMB"` field from AAPS or inference from `automatic: true` + small amount |

**Important**: AAPS uploads SMBs with `eventType: Correction Bolus` (not a dedicated SMB eventType), but includes a `type: "SMB"` field that enables identification. Systems must check the `type` field, not just `eventType`, to reliably identify SMBs.

### Manual vs Automatic Distinction

| System | Mechanism | Field |
|--------|-----------|-------|
| **Loop** | `automatic` boolean | `true` = auto-bolus, `false` = manual |
| **AAPS** | `Type` enum | `SMB` = automatic, `NORMAL` = manual |
| **Trio** | `automatic` boolean (from DoseEntry) | Same as Loop |
| **xDrip+** | N/A | No automatic boluses (CGM only) |

### Loop DoseEntry → Nightscout Bolus

```swift
// Source: NightscoutServiceKit/Extensions/DoseEntry.swift
case .bolus:
    return BolusNightscoutTreatment(
        timestamp: startDate,
        enteredBy: source,
        bolusType: duration >= TimeInterval(minutes: 30) ? .Square : .Normal,
        amount: deliveredUnits ?? programmedUnits,
        programmed: programmedUnits,
        unabsorbed: 0,
        duration: duration,
        automatic: automatic ?? false,
        syncIdentifier: syncIdentifier,
        insulinType: insulinType?.brandName
    )
```

**Key observations**:
- Square bolus inferred from `duration >= 30 minutes`
- `deliveredUnits` preferred over `programmedUnits` (accounts for cancellation)
- `automatic` defaults to `false` if not set

### AAPS Bolus → NSBolus

```kotlin
// Source: nsclientV3/extensions/BolusExtension.kt
fun BS.toNSBolus(): NSBolus =
    NSBolus(
        eventType = if (type == BS.Type.SMB) EventType.CORRECTION_BOLUS else EventType.MEAL_BOLUS,
        isValid = isValid,
        date = timestamp,
        utcOffset = T.msecs(utcOffset).mins(),
        insulin = amount,
        type = type.toBolusType(),
        notes = notes,
        isBasalInsulin = isBasalInsulin,
        identifier = ids.nightscoutId,
        pumpId = ids.pumpId,
        pumpType = ids.pumpType?.name,
        pumpSerial = ids.pumpSerial,
        endId = ids.endId
    )
```

**Key observations**:
- SMB → `EventType.CORRECTION_BOLUS`, NORMAL → `EventType.MEAL_BOLUS`
- Uses composite identity: `nightscoutId` + `pumpId` + `pumpType` + `pumpSerial`
- `isBasalInsulin` for MDI basal injection tracking
- `utcOffset` in minutes (converted from ms)

---

## Carb Entry Events

### Field Mapping

| Field | Nightscout | Loop | AAPS | Trio | xDrip+ |
|-------|------------|------|------|------|--------|
| **Carbs amount** | `carbs` | `quantity` (HKQuantity) | `amount` | via CarbsEntry | `carbs` |
| **Absorption time** | `absorptionTime` | `absorptionTime` (TimeInterval) | N/A (derived) | `absorptionTime` | N/A |
| **Duration (eCarbs)** | `duration` | N/A | `duration` (ms) | N/A | N/A |
| **Timestamp** | `created_at` | `startDate` | `timestamp` | `startDate` | `timestamp` |
| **Food type** | `foodType` | `foodType` | N/A | `foodType` | N/A |
| **Sync identity** | `identifier` | `syncIdentifier` | `interfaceIDs.nightscoutId` | `syncIdentifier` | `uuid` |
| **Notes** | `notes` | N/A | `notes` | N/A | `notes` |

### Absorption Time Handling

| System | Absorption Time | Storage |
|--------|-----------------|---------|
| **Loop** | Explicit user selection | `absorptionTime` (seconds) |
| **AAPS** | Not stored; uses profile default | N/A |
| **Trio** | Explicit (inherited from LoopKit) | `absorptionTime` (seconds) |
| **Nightscout** | Optional field | `absorptionTime` (minutes) |

**GAP-TREAT-001**: Absorption time units differ (Loop/Trio use seconds, Nightscout uses minutes). Translation required.

### Extended Carbs (eCarbs)

| System | eCarbs Support | Representation |
|--------|----------------|----------------|
| **Loop** | No | Single carb entry only |
| **AAPS** | Yes | `duration > 0` (milliseconds) |
| **Trio** | Yes | FPU (Fat Protein Units) support |
| **Nightscout** | Yes | `duration` field (minutes) |

**AAPS eCarbs logic**:
```kotlin
// Source: CarbsExtension.kt
fun CA.toNSCarbs(): NSCarbs =
    NSCarbs(
        eventType = if (amount < 12) EventType.CARBS_CORRECTION else EventType.MEAL_BOLUS,
        // ...
        duration = if (duration != 0L) duration else null,
    )
```

- `eventType` inferred from carb amount: `< 12g` → `CARBS_CORRECTION`, otherwise `MEAL_BOLUS`
- `duration` only included if non-zero (eCarbs)

### Loop StoredCarbEntry Structure

```swift
// Source: LoopKit/CarbKit/StoredCarbEntry.swift
public struct StoredCarbEntry: CarbEntry, Equatable {
    public let uuid: UUID?
    public let provenanceIdentifier: String
    public let syncIdentifier: String?
    public let syncVersion: Int?
    public let startDate: Date
    public let quantity: HKQuantity  // grams
    public let foodType: String?
    public let absorptionTime: TimeInterval?
    public let createdByCurrentApp: Bool
    public let userCreatedDate: Date?
    public let userUpdatedDate: Date?
}
```

**Key observations**:
- `provenanceIdentifier` tracks which app created the entry
- `syncVersion` enables optimistic concurrency
- `createdByCurrentApp` for deduplication on download
- User dates track edit history

---

## Temp Basal Events

### Field Mapping

| Field | Nightscout | Loop | AAPS | Trio | xDrip+ |
|-------|------------|------|------|------|--------|
| **Rate** | `rate` / `absolute` | `unitsPerHour` | `rate` | via LoopKit | N/A |
| **Percent** | `percent` | N/A (always absolute) | `rate - 100` if relative | N/A | N/A |
| **Is absolute** | `temp: "absolute"` | Always true | `isAbsolute` | Always true | N/A |
| **Duration** | `duration` (minutes) | `endDate - startDate` (seconds) | `duration` (ms) | Seconds | N/A |
| **Timestamp** | `created_at` | `startDate` | `timestamp` | `startDate` | N/A |
| **Sync identity** | `identifier` | `syncIdentifier` | `interfaceIDs` composite | `syncIdentifier` | N/A |
| **Automatic** | `automatic` | `automatic ?? true` | N/A | `automatic` | N/A |

### Duration Unit Differences

| System | Duration Unit | Conversion to NS (minutes) |
|--------|---------------|---------------------------|
| **Loop** | Seconds | `duration / 60` |
| **AAPS** | Milliseconds | `duration / 60000` |
| **Trio** | Seconds | `duration / 60` |
| **Nightscout** | Minutes | Native |

**GAP-TREAT-002**: Duration units vary significantly across systems.

### Temp Basal Types (AAPS)

```kotlin
// Source: database/entities/TemporaryBasal.kt
enum class Type {
    NORMAL,             // Standard temp basal
    EMULATED_PUMP_SUSPEND,  // Suspend via 0% basal
    PUMP_SUSPEND,       // Actual pump suspend
    SUPERBOLUS,         // Superbolus temp basal
    FAKE_EXTENDED       // Extended bolus emulation (in memory only)
}
```

### Loop Suspend → Nightscout

Loop represents suspends as temp basals with `rate: 0`:

```swift
// Source: NightscoutServiceKit/Extensions/DoseEntry.swift
case .suspend:
    return TempBasalNightscoutTreatment(
        timestamp: startDate,
        enteredBy: source,
        temp: .Absolute,
        rate: 0,
        absolute: unitsPerHour,  // 0
        duration: endDate.timeIntervalSince(startDate),
        amount: deliveredUnits,
        automatic: automatic ?? true,
        syncIdentifier: syncIdentifier,
        insulinType: nil,
        reason: "suspend"
    )
```

**Key observation**: `.resume` type is NOT uploaded; suspend duration captures the full suspend period.

---

## Sync Identity Comparison

### Identity Fields by System

| System | Primary Identity | Secondary Identity | Server ID |
|--------|-----------------|-------------------|-----------|
| **Loop** | `syncIdentifier` (UUID string) | N/A | `_id` (MongoDB) |
| **AAPS** | `interfaceIDs.nightscoutId` | `pumpId` + `pumpType` + `pumpSerial` | `_id` |
| **Trio** | `syncIdentifier` (UUID string) | N/A | `_id` |
| **xDrip+** | `uuid` | N/A | `_id` |

### AAPS InterfaceIDs Structure

```kotlin
// Source: database/entities/embedments/InterfaceIDs.kt
data class InterfaceIDs(
    var nightscoutSystemId: String? = null,  // NS server identifier
    var nightscoutId: String? = null,        // Document _id
    var pumpType: PumpType? = null,          // Pump model enum
    var pumpSerial: String? = null,          // Pump serial number
    var temporaryId: Long? = null,           // Temp ID during sync
    var pumpId: Long? = null,                // Pump event ID
    var startId: Long? = null,               // Related start event
    var endId: Long? = null                  // Related end event
)
```

**Observation**: AAPS uses composite identity with full pump event tracking, enabling reconciliation between pump events and NS documents.

### Deduplication Strategies

| System | Upload Dedup | Download Dedup |
|--------|--------------|----------------|
| **Loop** | POST with `syncIdentifier` (may create dups) | `createdByCurrentApp` flag |
| **AAPS** | PUT with `identifier` (API v3) | `enteredBy` filter (`$ne`) |
| **Trio** | POST with `id` field | `enteredBy` filter |
| **xDrip+** | PUT upsert with `uuid` → `_id` | `enteredBy.endsWith("via Nightscout")` |

---

## xDrip+ Multi-Insulin Support

xDrip+ has unique multi-insulin tracking via `insulinInjections`:

```java
// Source: models/Treatments.java
@Expose
@Column(name = "insulinJSON")
public String insulinJSON;

// Structure: [{profile: "Humalog", units: 5.0}, {profile: "Lantus", units: 10.0}]
```

### InsulinInjection Structure

```java
// Source: models/InsulinInjection.java
public class InsulinInjection {
    private Insulin profile;  // Insulin profile with curve data
    private double units;     // Units injected
    
    public boolean isBasal() {
        return profile != null && profile.isBasal();
    }
}
```

**Unique capability**: xDrip+ can track mixed rapid-acting + basal injections in a single treatment, uploaded to Nightscout as `insulinInjections` JSON array.

---

## Nightscout Treatment Upload Comparison

### Upload Methods

| System | API Version | Method | Endpoint |
|--------|-------------|--------|----------|
| **Loop** | v1 | POST | `/api/v1/treatments` |
| **AAPS** | v3 | POST/PUT | `/api/v3/treatments` |
| **Trio** | v1 | POST | `/api/v1/treatments` |
| **xDrip+** | v1 | POST/PUT | `/api/v1/treatments` |

### xDrip+ Treatment Upload

```java
// Source: NightscoutUploader.java
private void populateV1APITreatmentEntry(JSONArray array, Treatments treatment) {
    // Skip if originated from Nightscout
    if (treatment.enteredBy.endsWith(VIA_NIGHTSCOUT_TAG)) return;
    
    JSONObject record = new JSONObject();
    record.put("timestamp", treatment.timestamp);
    record.put("eventType", treatment.eventType);
    record.put("enteredBy", treatment.enteredBy);
    record.put("notes", treatment.notes);
    record.put("uuid", treatment.uuid);
    record.put("carbs", treatment.carbs);
    record.put("insulin", treatment.insulin);
    if (treatment.insulinJSON != null) {
        record.put("insulinInjections", treatment.insulinJSON);
    }
    record.put("created_at", treatment.created_at);
}
```

**Deduplication logic**: Converts `uuid` to MongoDB-style `_id` for upserts:
```java
item.put("_id", uuid_to_id(match_uuid));
nightscoutService.upsertTreatments(apiSecret, body).execute();
```

---

## Identified Gaps

### GAP-TREAT-001: Absorption Time Unit Mismatch

**Issue**: Loop and Trio use seconds for absorption time; Nightscout uses minutes.

**Impact**: Incorrect absorption modeling if units not converted properly.

**Solution**: Explicit conversion in upload/download logic.

### GAP-TREAT-002: Duration Unit Inconsistency

**Issue**: Duration units vary (seconds, milliseconds, minutes) across systems.

**Impact**: Temp basal duration could be off by orders of magnitude.

**Solution**: Standardize on minutes for Nightscout, with explicit conversion.

### GAP-TREAT-003: No Explicit SMB Event Type

**Issue**: Nightscout lacks an explicit `SMB` eventType. AAPS uploads SMBs with `eventType: "Correction Bolus"` plus a `type: "SMB"` field, but other systems may not include this. Systems without the `type` field must infer SMBs from `automatic: true` + small amount, which is unreliable.

**Impact**: Cannot reliably query for SMB events across all AID systems; manual correction boluses may be confused with SMBs.

**Proposed solution**: 
1. All AID systems adopt AAPS convention of including `type: "SMB"` field
2. Or add explicit `eventType: "SMB"` to Nightscout schema

### GAP-TREAT-004: Split Bolus Representation Mismatch

**Issue**: 
- AAPS can represent extended boluses via `FAKE_EXTENDED` temp basal type
- Loop uses `duration >= 30min` for square wave detection
- Nightscout has explicit `splitNow`/`splitExt` fields

**Impact**: Extended/combo boluses may not round-trip correctly.

### GAP-TREAT-005: Loop POST-Only Creates Duplicates

**Issue**: Loop uses POST (not PUT) for treatment uploads, which may create duplicates if retried.

**Source**: `NightscoutServiceKit/Extensions/DoseEntry.swift`
```swift
/* id: objectId, */ /// Specifying _id only works when doing a put (modify); all dose uploads are currently posting
```

**Impact**: Duplicate treatments in Nightscout after network retries.

**Solution**: Switch to PUT with `syncIdentifier` as dedup key, or use API v3 upsert.

### GAP-TREAT-006: Retroactive Edit Handling

**Issue**: 
- Loop tracks `userUpdatedDate` but doesn't sync updates
- AAPS uses `isValid: false` for soft deletes
- Nightscout has no standard edit history

**Impact**: Edited or deleted treatments may not sync properly.

### GAP-TREAT-007: eCarbs Not Universally Supported

**Issue**: Extended carbs (eCarbs) with duration field are supported by AAPS and Nightscout but not by Loop.

**Impact**: eCarbs entered in AAPS won't be properly interpreted by Loop followers.

---

## Cross-References

- [Loop Nightscout Sync](../../mapping/loop/nightscout-sync.md)
- [Nightscout Data Model](./nightscout-data-model.md)
- [AID Controller Sync Patterns](../../mapping/cross-project/aid-controller-sync-patterns.md)
- [Terminology Matrix - Treatments](../../mapping/cross-project/terminology-matrix.md#events-actionsobservations)
- [xDrip+ Mapping](../../mapping/xdrip-android/README.md)

---

## Revision History

| Date | Author | Changes |
|------|--------|---------|
| 2026-01-17 | Agent | Initial treatments deep dive with field mappings |
| 2026-01-17 | Agent | Added GAP-TREAT-001 through GAP-TREAT-007 |
