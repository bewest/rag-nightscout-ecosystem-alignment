# Loop Upload Source Analysis Sub-Backlog

> **Parent**: [loop-nightscout-upload-testing.md](loop-nightscout-upload-testing.md)
> **Goal**: Extract exact upload patterns from Loop source code
> **Created**: 2026-03-10

## Priority Order

Analyze in order of impact on GAP-TREAT-012 (UUID _id issue):

1. **OverrideTreament.swift** - The problem code (uses `_id = syncIdentifier`)
2. **SyncCarbObject.swift** - The "correct" pattern (uses `id` + `syncIdentifier`)
3. **ObjectIdCache.swift** - How Loop tracks server IDs
4. **NightscoutUploader.swift** - HTTP methods and endpoints

---

## LOOP-SRC-010: OverrideTreament.swift

**File**: `externals/LoopWorkspace/NightscoutService/NightscoutServiceKit/Extensions/OverrideTreament.swift`

### Questions to Answer

- [ ] What fields does `asNightscoutTreatment()` return?
- [ ] Does it use `_id` or `id` or both?
- [ ] Does it include a separate `syncIdentifier` field?
- [ ] What is `eventType` set to?
- [ ] What override-specific fields are included?

### Expected Output

```json
{
  "_id": "UUID-STRING",
  "eventType": "Temporary Override",
  "created_at": "ISO-8601",
  "reason": "...",
  "duration": 60,
  "correctionRange": [90, 110],
  "insulinNeedsScaleFactor": 1.2,
  // Does it have syncIdentifier? enteredBy?
}
```

### Status: ⬜ Not Started

---

## LOOP-SRC-011: SyncCarbObject.swift

**File**: `externals/LoopWorkspace/NightscoutService/NightscoutServiceKit/Extensions/SyncCarbObject.swift`

### Questions to Answer

- [ ] Does it use `_id` or `id` or both?
- [ ] Does it include `syncIdentifier` as separate field?
- [ ] How is `id` populated (from ObjectIdCache)?
- [ ] What is `eventType` set to?
- [ ] What carb-specific fields are included?

### Expected Output

```json
{
  "id": "ObjectId-from-cache-or-null",
  "syncIdentifier": "UUID-STRING",
  "eventType": "Carb Correction",
  "carbs": 30,
  "absorptionTime": 180,
  "created_at": "ISO-8601",
  "enteredBy": "loop://iPhone"
}
```

### Status: ⬜ Not Started

---

## LOOP-SRC-003: ObjectIdCache.swift

**File**: `externals/LoopWorkspace/NightscoutService/NightscoutServiceKit/ObjectIdCache.swift`

### Questions to Answer

- [ ] What is the cache data structure?
- [ ] How is syncIdentifier → objectId mapping stored?
- [ ] What is the expiry time (24 hours)?
- [ ] When is the cache populated (after POST response)?
- [ ] When is the cache consulted (before PUT/DELETE)?
- [ ] What happens on cache miss?

### Key Methods to Document

```swift
// Expected methods:
func findObjectIdBySyncIdentifier(_ syncIdentifier: String) -> String?
func addMapping(syncIdentifier: String, objectId: String)
func purgeOldEntries()
```

### Status: ⬜ Not Started

---

## LOOP-SRC-002: NightscoutUploader.swift

**File**: `externals/LoopWorkspace/NightscoutService/NightscoutServiceKit/Extensions/NightscoutUploader.swift`

### Questions to Answer

- [ ] What HTTP methods are used (POST, PUT, DELETE)?
- [ ] What endpoints are called (`/api/v1/treatments`, etc.)?
- [ ] How are batch uploads handled?
- [ ] How is the response parsed for `_id`?
- [ ] How does it update ObjectIdCache from response?

### Key Methods to Document

```swift
// Expected methods:
func uploadTreatments(_ treatments: [NightscoutTreatment]) async throws -> [String]
func uploadEntries(_ entries: [NightscoutEntry]) async throws
func deleteTreatment(id: String) async throws
func updateTreatment(_ treatment: NightscoutTreatment) async throws
```

### Status: ⬜ Not Started

---

## LOOP-SRC-012: Dose Upload (Multiple Files)

**Files**:
- `LoopKit/LoopKit/InsulinKit/DoseEntry.swift` - syncIdentifier definition
- `NightscoutServiceKit/Extensions/DoseEntry+Nightscout.swift` - JSON conversion (if exists)

### Questions to Answer

- [ ] Where is DoseEntry converted to Nightscout JSON?
- [ ] Does it use `_id` or `id` or `syncIdentifier`?
- [ ] Is `syncIdentifier` the hex of pump raw data?
- [ ] What `eventType` values are used (Bolus, Temp Basal)?

### Status: ⬜ Not Started

---

## LOOP-SRC-013: Glucose Entry Upload

**Files**:
- `NightscoutServiceKit/Extensions/StoredGlucoseSample.swift`

### Questions to Answer

- [ ] What fields are sent for SGV entries?
- [ ] Is `identifier` or `syncIdentifier` used?
- [ ] What deduplication fields are set?

### Status: ⬜ Not Started

---

## LOOP-SRC-014: DeviceStatus Upload

**Files**:
- `NightscoutServiceKit/Extensions/StoredDosingDecision.swift`

### Questions to Answer

- [ ] What is the `loop` object structure?
- [ ] Are overrides included in deviceStatus?
- [ ] What IOB/COB/predicted structure?

### Status: ⬜ Not Started

---

## Analysis Template

For each source file, document:

```markdown
### [Filename]

**Full Path**: `externals/LoopWorkspace/...`

**Key Methods**:
| Method | Purpose |
|--------|---------|
| `methodName()` | Description |

**JSON Output**:
```json
{
  "field": "value"
}
```

**Identity Fields**:
| Field | Value Source | Used For |
|-------|--------------|----------|
| `_id` | syncIdentifier.uuidString | Override only |
| `id` | ObjectIdCache lookup | Carbs, doses |
| `syncIdentifier` | Entry.syncIdentifier | Dedup |

**Code References**:
- Line XX: Key logic
- Line YY: Field assignment
```

---

## Completion Criteria

Phase 1 is complete when:
- [ ] All 7 source files analyzed
- [ ] JSON payloads extracted for each treatment type
- [ ] Identity field usage documented in table
- [ ] Differences between override and carbs/doses documented
- [ ] ObjectIdCache lifecycle fully understood
