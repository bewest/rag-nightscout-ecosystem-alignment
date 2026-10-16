# Trio iOS App: `_id` Field Quick Reference

> **Correction (2026-10-16, `SPEC-REG-AMEND`; source read at Trio `e41c9db37`, corpus measured
> with `make schema-quirks`).** The statement that Trio's `id` maps to `_id` holds for the carbs
> and temporary-target models, not for `NightscoutTreatment`: `CarbsEntry.swift:29` and
> `TempTarget.swift:50` encode `case id = "_id"`, while `NightscoutTreatment.swift:62` encodes
> `case id` with no key, so a treatment built as `NightscoutTreatment` is sent with its UUID in the
> member `id`, not `_id`. cgm-remote-monitor does not read `id`: it matches such a treatment by
> `created_at` + `eventType` (write contract `treatment-fallback-key`; `lib/server/treatments.js:383-405`
> at `crm-write` `239f8c25`). Measured over the 2026-04-01 and 2026-04-26 snapshots: 55,939 stored
> treatments on one site carry a UUID `id`, each with `enteredBy: Trio`, a server-assigned 24-hex
> `_id` and no `identifier` (registry entry `QUIRK-TREATMENTS-007`). At the same commit
> `BloodGlucose`'s coding keys hold both `_id` (`legacyId`) and `id` (`BloodGlucose.swift:60-62`);
> the glucose statements were not re-checked. The text below is kept as written.

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

*Corrected 2026-10-16: `NightscoutTreatment`'s `id` is encoded as `id`, not `_id` (`NightscoutTreatment.swift:62` at `e41c9db37`); see the note at the top.*

### Upload Endpoints
```
POST /api/v1/entries.json         ← Glucose (with _id)
POST /api/v1/treatments.json      ← Treatments (with _id via id)
POST /api/v1/devicestatus.json    ← Device status (no _id)
```

*Corrected 2026-10-16: treatments built as `NightscoutTreatment` carry the UUID as `id`, with no `_id`; carbs and temporary targets carry `_id`.*

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

