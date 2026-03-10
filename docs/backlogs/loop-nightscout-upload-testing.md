# Loop → Nightscout Upload Testing Backlog

> **Goal**: Develop comprehensive tests for cgm-remote-monitor that faithfully simulate all ways Loop uploads data to Nightscout.
> **Test Location**: `/home/bewest/src/worktrees/nightscout/cgm-pr-8447/tests/`
> **Created**: 2026-03-10

## Override Upload Analysis (LOOP-SRC-010)

### Key Finding: Overrides Use UUID as `_id` Directly

**File**: `NightscoutServiceKit/Extensions/OverrideTreament.swift:59`

```swift
self.init(..., id: override.syncIdentifier.uuidString)
```

Unlike carbs/doses which use `ObjectIdCache`, overrides:
1. Set `id` field directly to `syncIdentifier.uuidString`
2. **Do NOT use ObjectIdCache** for mapping
3. Delete by `syncIdentifier.uuidString` directly

### Upload Flow

**File**: `NightscoutService.swift:157-186`

```swift
public func uploadTemporaryOverrideData(updated: [...], deleted: [...], ...) {
    let updates = updated.map { OverrideTreatment(override: $0) }
    let deletions = deleted.map { $0.syncIdentifier.uuidString }
    
    uploader.deleteTreatmentsById(deletions, ...)  // Delete by UUID string
    uploader.upload(updates) { ... }                // POST with id=UUID
}
```

### JSON Payload Structure

| Field | Value | Source |
|-------|-------|--------|
| `id` | `"A1B2C3D4-..."` (UUID string) | `override.syncIdentifier.uuidString` |
| `eventType` | `"Temporary Override"` | NightscoutKit |
| `created_at` | ISO8601 date | `override.startDate` |
| `enteredBy` | `"Loop"` or `"Loop (via remote command)"` | trigger type |
| `reason` | `"Custom Override"`, `"Workout"`, preset name | `override.context` |
| `duration` | minutes or -1 (indefinite) | `override.duration` |
| `correctionRange` | `[low, high]` mg/dL | `override.settings.targetRange` |
| `insulinNeedsScaleFactor` | 0.5 - 2.0 | override settings |

### Why This Causes GAP-TREAT-012

Nightscout's `lib/server/treatments.js:normalizeTreatmentId()` tries to convert the `id` field to MongoDB ObjectId:

```javascript
// Current behavior (broken):
_id: new ObjectId(id)  // FAILS for UUID strings like "A1B2C3D4-..."
```

PR #8447 / Option G fixes this by detecting UUID format and handling differently.

---

## Phase 1: Loop Source Code Analysis

### 1.1 Core Upload Infrastructure

| Item | Source File | Status |
|------|-------------|--------|
| LOOP-SRC-001 | `NightscoutService/NightscoutServiceKit/NightscoutService.swift` | ⬜ |
| LOOP-SRC-002 | `NightscoutService/NightscoutServiceKit/Extensions/NightscoutUploader.swift` | ⬜ |
| LOOP-SRC-003 | `NightscoutService/NightscoutServiceKit/ObjectIdCache.swift` | ⬜ |

**Deliverable**: Document upload methods, HTTP verbs, endpoints, and payload structure.

### 1.2 Treatment Upload Extensions

| Item | Source File | Purpose | Status |
|------|-------------|---------|--------|
| LOOP-SRC-010 | `Extensions/OverrideTreament.swift` | Override → Treatment JSON | ✅ |
| LOOP-SRC-011 | `Extensions/SyncCarbObject.swift` | Carb → Treatment JSON | ⬜ |
| LOOP-SRC-012 | `Extensions/DoseEntry+Nightscout.swift` | Dose → Treatment JSON | ⬜ |
| LOOP-SRC-013 | `Extensions/StoredGlucoseSample.swift` | Glucose → Entry JSON | ⬜ |
| LOOP-SRC-014 | `Extensions/StoredDosingDecision.swift` | Decision → DeviceStatus JSON | ⬜ |

**Deliverable**: Extract exact JSON payloads for each treatment type.

### 1.3 Identity Field Usage

| Item | Question | Source | Status |
|------|----------|--------|--------|
| LOOP-ID-001 | When does Loop use `_id` vs `id`? | NightscoutUploader | ✅ |
| LOOP-ID-002 | When does Loop use `syncIdentifier`? | All Extensions | ⬜ |
| LOOP-ID-003 | How does ObjectIdCache map syncIdentifier → _id? | ObjectIdCache | ⬜ |
| LOOP-ID-004 | What happens when ObjectIdCache expires (24hr)? | ObjectIdCache | ⬜ |
| LOOP-ID-005 | Does Loop send `identifier` field (v3 style)? | All Extensions | ⬜ |

**Deliverable**: Identity field mapping table per treatment type.

---

## Phase 2: Test Development Pipeline

### 2.1 Override Upload Tests (CRITICAL - GAP-TREAT-012)

| Test ID | Scenario | HTTP | Payload Key Fields | Status |
|---------|----------|------|-------------------|--------|
| TEST-OVR-001 | Create override (UUID _id) | POST | `_id`, `eventType`, `created_at`, `reason` | ✅ Exists |
| TEST-OVR-002 | Update override (UUID _id) | PUT | `_id`, `duration`, `created_at` | ✅ Exists |
| TEST-OVR-003 | Delete override (UUID _id) | DELETE | URL param: `_id` | ✅ Exists |
| TEST-OVR-004 | Repost override (upsert) | POST | Same `_id`, different `created_at` | ✅ Exists |
| TEST-OVR-005 | Override without `syncIdentifier` field | POST | Verify no separate sync field | ⬜ |
| TEST-OVR-006 | Cancel indefinite override | DELETE | `durationType: indefinite` first | ⬜ |

### 2.2 Carb Upload Tests

| Test ID | Scenario | HTTP | Payload Key Fields | Status |
|---------|----------|------|-------------------|--------|
| TEST-CARB-001 | Create carb entry | POST | `syncIdentifier`, `carbs`, `absorptionTime` | ⬜ |
| TEST-CARB-002 | Create carb with `id` (from cache) | POST | `id`, `syncIdentifier` | ⬜ |
| TEST-CARB-003 | Update carb via cached `id` | PUT | `id`, updated `carbs` | ⬜ |
| TEST-CARB-004 | Delete carb via cached `id` | DELETE | URL param: `id` | ⬜ |
| TEST-CARB-005 | Carb batch upload | POST | Array of carbs | ✅ Exists |
| TEST-CARB-006 | Duplicate syncIdentifier handling | POST | Same `syncIdentifier` twice | ✅ Exists |

### 2.3 Dose Upload Tests (Bolus, Temp Basal)

| Test ID | Scenario | HTTP | Payload Key Fields | Status |
|---------|----------|------|-------------------|--------|
| TEST-DOSE-001 | Bolus with syncIdentifier | POST | `syncIdentifier`, `insulin`, `eventType` | ⬜ |
| TEST-DOSE-002 | Temp basal with syncIdentifier | POST | `syncIdentifier`, `rate`, `duration` | ⬜ |
| TEST-DOSE-003 | Update dose via cached id | PUT | `id` (from cache) | ⬜ |
| TEST-DOSE-004 | Dose batch upload | POST | Array of doses | ✅ Exists |
| TEST-DOSE-005 | Dose hex string syncIdentifier | POST | `syncIdentifier` = hex(pumpRaw) | ⬜ |

### 2.4 Glucose Entry Upload Tests

| Test ID | Scenario | HTTP | Payload Key Fields | Status |
|---------|----------|------|-------------------|--------|
| TEST-SGV-001 | Single SGV entry | POST | `sgv`, `date`, `direction` | ⬜ |
| TEST-SGV-002 | SGV batch (typical) | POST | 3-12 entries | ✅ Exists |
| TEST-SGV-003 | SGV batch (max 1000) | POST | 1000 entries | ✅ Exists |
| TEST-SGV-004 | SGV with device field | POST | `device: "loop://iPhone"` | ⬜ |
| TEST-SGV-005 | SGV deduplication | POST | Same `date` + `device` | ⬜ |

### 2.5 DeviceStatus Upload Tests

| Test ID | Scenario | HTTP | Payload Key Fields | Status |
|---------|----------|------|-------------------|--------|
| TEST-DS-001 | Loop status with IOB/COB | POST | `loop.iob`, `loop.cob` | ⬜ |
| TEST-DS-002 | Loop status with predicted | POST | `loop.predicted.values` | ⬜ |
| TEST-DS-003 | Loop status with enacted | POST | `loop.enacted.rate`, `duration` | ⬜ |
| TEST-DS-004 | Pump status | POST | `pump.reservoir`, `pump.battery` | ⬜ |
| TEST-DS-005 | Override in deviceStatus | POST | `loop.override.*` | ⬜ |

### 2.6 ObjectIdCache Workflow Tests (CRITICAL)

| Test ID | Scenario | Status |
|---------|----------|--------|
| TEST-CACHE-001 | POST carb → cache syncIdentifier → PUT with id | ⬜ |
| TEST-CACHE-002 | POST dose → cache syncIdentifier → DELETE with id | ⬜ |
| TEST-CACHE-003 | Cache miss (24hr expiry) → POST same syncIdentifier | ⬜ |
| TEST-CACHE-004 | App restart (cache empty) → POST existing syncIdentifier | ⬜ |
| TEST-CACHE-005 | Batch POST → verify response order → cache mapping | ⬜ |

---

## Phase 3: Payload Extraction

### 3.1 Real Loop Payloads to Capture

| Payload ID | Source | Method | Status |
|------------|--------|--------|--------|
| PAYLOAD-001 | OverrideTreament.swift | `asNightscoutTreatment()` | ⬜ |
| PAYLOAD-002 | SyncCarbObject.swift | `asNightscoutTreatment()` | ⬜ |
| PAYLOAD-003 | DoseEntry+Nightscout.swift | `asNightscoutTreatment()` | ⬜ |
| PAYLOAD-004 | StoredGlucoseSample.swift | `asNightscoutEntry()` | ⬜ |
| PAYLOAD-005 | StoredDosingDecision.swift | `asDeviceStatus()` | ⬜ |

**Method**: Extract from Swift code or capture from real Loop device.

---

## Phase 4: Gap Coverage

### Tests That Cover Documented Gaps

| Gap ID | Description | Test Coverage |
|--------|-------------|---------------|
| GAP-TREAT-012 | UUID _id coercion | TEST-OVR-001 through TEST-OVR-006 |
| GAP-SYNC-005 | ObjectIdCache not persistent | TEST-CACHE-003, TEST-CACHE-004 |
| GAP-BATCH-002 | Response order for cache | TEST-CACHE-005 |
| GAP-TREAT-005 | Loop POST-only duplicates | TEST-CARB-006, TEST-DOSE-005 |

---

## Source File Index

### NightscoutServiceKit Core
```
externals/LoopWorkspace/NightscoutService/NightscoutServiceKit/
├── NightscoutService.swift          # Main service class
├── ObjectIdCache.swift              # syncIdentifier → objectId mapping
├── Extensions/
│   ├── NightscoutUploader.swift     # HTTP upload methods
│   ├── OverrideTreament.swift       # Override → JSON (uses _id = syncIdentifier)
│   ├── SyncCarbObject.swift         # Carb → JSON (uses id + syncIdentifier)
│   ├── DoseEntry+Nightscout.swift   # Dose → JSON
│   ├── StoredGlucoseSample.swift    # SGV → JSON
│   ├── StoredDosingDecision.swift   # DeviceStatus → JSON
│   └── TemporaryScheduleOverride.swift
└── RemoteCommands/
    └── V1/Notifications/            # Remote bolus/carb/override
```

### LoopKit Core Types
```
externals/LoopWorkspace/LoopKit/LoopKit/
├── InsulinKit/DoseEntry.swift       # syncIdentifier definition
├── CarbKit/SyncCarbObject.swift     # syncIdentifier definition
├── CarbKit/StoredCarbEntry.swift    # syncIdentifier definition
└── GlucoseKit/StoredGlucoseSample.swift  # syncIdentifier definition
```

---

## Work Items Summary

| Phase | Items | Completed | Blocked |
|-------|-------|-----------|---------|
| 1. Source Analysis | 13 | 2 | 0 |
| 2. Test Development | 28 | 8 | 0 |
| 3. Payload Extraction | 5 | 0 | 0 |
| 4. Gap Coverage | 4 | 1 | 0 |
| **Total** | **50** | **11** | **0** |

---

## Next Actions

1. [x] Analyze `OverrideTreament.swift` - extract exact JSON structure ✅
2. [ ] Analyze `SyncCarbObject.swift` - compare id vs syncIdentifier usage
3. [ ] Analyze `ObjectIdCache.swift` - understand cache lifecycle
4. [ ] Create test fixtures from real Loop payloads
5. [ ] Implement TEST-CACHE-* tests for ObjectIdCache workflow

---

## Related Documents

- [GAP-TREAT-012](../../traceability/treatments-gaps.md#gap-treat-012-v1-api-incorrectly-coerces-uuid-_id-to-objectid) - Issue analysis and fix options
- [REQ-SYNC-072](../../traceability/sync-identity-requirements.md#req-sync-072-transparent-uuid-promotion-option-g) - **Option G (Recommended)**: Transparent UUID promotion
- [REQ-SYNC-071](../../traceability/sync-identity-requirements.md#req-sync-071-server-controlled-id-with-client-identity-preservation) - Long-term: Server-Controlled ID
- [Loop Sync Identity Fields](../../mapping/loop/sync-identity-fields.md)
- [Integration Test Harness](integration-test-harness.md) - How to run tests
- [cgm-remote-monitor issue #8450](https://github.com/nightscout/cgm-remote-monitor/issues/8450)
