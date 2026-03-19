# Trio iOS App: `_id` Field Quick Reference

## TL;DR

| Question | Answer |
|----------|--------|
| What goes in `_id`? | **UUID strings** (`"550e8400-e29b-41d4-a716-446655440000"`) |
| Is it always sent? | **Yes** for entries/treatments; **No** for devicestatus |
| How is it generated? | `UUID().uuidString` at record creation |
| What is `syncIdentifier`? | LoopKit's dedup identifier; reuses `_id` value |
| Different by collection? | No; all use UUIDs, but field presence varies |
| MongoDB UUID quirk impact? | **Minimal** - Trio sends strings, not binary |
| Loop pattern match? | Partial - similar concepts, different implementation |

---

## Code Locations - Quick Links

### `_id` Generation & Assignment
```
BloodGlucose.swift:117     → _id: String = UUID().uuidString
GlucoseStorage.swift:416   → _id: result.id?.uuidString ?? UUID().uuidString
CarbsStorage.swift:383     → id: result.id?.uuidString
NightscoutTreatment.swift  → var id: String?  [maps to "_id" in JSON]
```

### Upload Endpoints
```
POST /api/v1/entries.json         ← Glucose (with _id)
POST /api/v1/treatments.json      ← Treatments (with _id via id)
POST /api/v1/devicestatus.json    ← Device status (no _id)
```

### CoreData Models
```
CarbEntryStored:    @NSManaged var id: UUID?
GlucoseStored:      @NSManaged var id: UUID?
PumpEventStored:    @NSManaged var id: String?
```

### Deduplication
```
isUploadedToNS: Bool          ← Upload flag (primary dedup)
UUID string _id               ← Document identifier
syncIdentifier (LoopKit)      ← Cross-system dedup
```

---

## Payload Examples

### Glucose Entry
```json
{
  "_id": "550e8400-e29b-41d4-a716-446655440000",
  "type": "sgv",
  "sgv": 145,
  "dateString": "2023-11-15T10:00:00.000Z"
}
```

### Carb Correction (via NightscoutTreatment)
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440001",
  "eventType": "Carb Correction",
  "carbs": 30,
  "timestamp": "2023-11-15T10:00:00.000Z"
}
```

### Device Status (NO `_id`)
```json
{
  "device": "Trio",
  "openaps": {...},
  "pump": {...},
  "uploader": {...}
}
```

---

## Key Files Reference

| File | Purpose | Key Line |
|------|---------|----------|
| `BloodGlucose.swift` | Glucose model | 117 (UUID init), 283 (syncIdentifier) |
| `NightscoutTreatment.swift` | Treatment model | 24 (id field), 41-65 (CodingKeys) |
| `CarbsEntry.swift` | Carb model | 30 (CodingKeys mapping) |
| `GlucoseStorage.swift` | Glucose fetch | 416 (UUID conversion) |
| `CarbsStorage.swift` | Carb fetch | 383 (UUID conversion) |
| `PumpHistoryStorage.swift` | Treatment fetch | 339, 359 (id usage) |
| `NightscoutAPI.swift` | Upload API | 320, 356, 393 (upload methods) |
| `NightscoutManager.swift` | Upload orchestration | 1024 (dedup flag update) |
| `JSON.swift` | Encoder config | 84-89 (UUID→string encoding) |

---

## Upload Flow (Simplified)

```
[CoreData: id = UUID?]
        ↓
[Map: UUID → String]
        ↓
[Create: NightscoutTreatment.id or BloodGlucose._id]
        ↓
[Encode: JSONEncoder → "_id": "550e8400..."]
        ↓
[POST to Nightscout API]
        ↓
[Mark: isUploadedToNS = true]
```

---

## Comparison: Trio vs Loop/NightscoutKit

| Aspect | Trio | Loop |
|--------|------|------|
| _id type | UUID string | Optional string |
| Always sent? | Yes | Only if set |
| syncIdentifier field | Implicit (via conversion) | Explicit in dictionary |
| Model structure | Flat NightscoutTreatment | Polymorphic hierarchy |
| Upload method | Standard JSONEncoder | DictionaryRepresentable |

---

## Common Gotchas

1. **DeviceStatus has no `_id`** - MongoDB auto-generates it; can't deduplicate by ID
2. **PumpEventStored uses String ID** - Other CoreData models use UUID; watch the types!
3. **syncIdentifier ≠ Nightscout _id** - Used by LoopKit, not sent to Nightscout
4. **Fallback UUID generation** - If CoreData id is nil, new UUID created at upload time

---

## Testing Checklist

- [ ] Verify UUID strings are valid (RFC 4122)
- [ ] Check that `isUploadedToNS` flag prevents re-uploads
- [ ] Confirm syncIdentifier matches `_id` value for LoopKit
- [ ] Verify DeviceStatus uploads succeed without `_id`
- [ ] Test UUID uniqueness across multiple uploads
- [ ] Confirm deduplication across Trio ↔ Nightscout ↔ LoopKit

