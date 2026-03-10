# Treatments Gaps

Domain-specific gaps extracted from gaps.md.
See [gaps.md](gaps.md) for the index.

> **Traceability Matrix**: [`domain-matrices/treatments-matrix.md`](domain-matrices/treatments-matrix.md) - REQ↔GAP↔Assertion coverage

---

### GAP-OVERRIDE-001: No unified override/profile-switch model

**Scenario**: Cross-system therapy adjustment tracking

**Description**: Loop uses `Temporary Override` eventType, AAPS uses `Profile Switch`, and they have different semantics. No unified schema to translate between them.

**Evidence**:
- Loop: `externals/LoopWorkspace/LoopKit/LoopKit/TemporaryScheduleOverride.swift`
- AAPS: `externals/AndroidAPS/database/impl/src/main/kotlin/app/aaps/database/entities/ProfileSwitch.kt`

**Impact**:
- Cannot query "what therapy adjustment was active at time T" across systems
- Follower apps must handle multiple eventTypes with different semantics
- Analytics tools cannot aggregate override usage across AID systems

**Possible Solutions**:
1. Define abstract `TherapyAdjustment` schema that both map to
2. Add cross-reference fields linking equivalent concepts
3. Accept as fundamental design difference

**Status**: Under discussion

**Related**:
- [Override/Profile Switch Comparison](../docs/10-domain/override-profile-switch-comparison.md)
- GAP-002

---

---

### GAP-OVERRIDE-002: AAPS percentage vs Loop insulinNeedsScaleFactor inversion

**Scenario**: Cross-system data interpretation

**Description**: Loop and AAPS use inverted semantics for insulin scaling:
- Loop: `insulinNeedsScaleFactor = 0.5` means 50% less insulin need
- AAPS: `percentage = 50` means 50% of normal insulin

Mathematically equivalent but semantically confusing.

**Evidence**:
- Loop: `TemporaryScheduleOverrideSettings.insulinNeedsScaleFactor`
- AAPS: `ProfileSwitch.percentage`

**Impact**:
- Follower apps must invert the value when displaying
- Easy to misinterpret without documentation

**Possible Solutions**:
1. Document mapping: `aaps.percentage = loop.insulinNeedsScaleFactor * 100`
2. Add standardized field in Nightscout schema

**Status**: Documented

**Related**:
- [Override/Profile Switch Comparison](../docs/10-domain/override-profile-switch-comparison.md)

---

---

### GAP-OVERRIDE-003: TempTarget vs Override separation inconsistent

**Scenario**: Cross-system therapy adjustment modeling

**Description**: Systems handle target range overrides differently:
- Loop: Target is part of override (`targetRange` in settings)
- AAPS/Trio: TempTarget is a separate entity from ProfileSwitch/Override

**Impact**:
- May have active TempTarget AND ProfileSwitch simultaneously in AAPS
- Combining target + insulin adjustment requires different logic per system
- Analytics must join multiple eventTypes in AAPS

**Possible Solutions**:
1. Accept as fundamental design difference
2. Document in terminology matrix
3. Create virtual "combined adjustment" view in Nightscout

**Status**: Documented

**Related**:
- [Override/Profile Switch Comparison](../docs/10-domain/override-profile-switch-comparison.md)

---

---

### GAP-OVERRIDE-004: Trio advanced override settings not in Nightscout

**Scenario**: Trio override visibility in followers

**Description**: Trio's advanced override fields have no Nightscout representation:
- `smbIsOff` (disable SMB)
- `isfAndCr` (apply to ISF and CR)
- `smbMinutes`, `uamMinutes` (timing overrides)

**Evidence**: `externals/Trio/Trio/Sources/Models/Override.swift`

**Impact**:
- Following a Trio user, cannot see full override configuration
- Cannot analyze SMB behavior during overrides

**Possible Solutions**:
1. Add extension fields to Nightscout treatment schema
2. Include in devicestatus instead
3. Accept as Trio-specific detail

**Status**: Under discussion

**Related**:
- [Override/Profile Switch Comparison](../docs/10-domain/override-profile-switch-comparison.md)

---

## Sync Identity Gaps

---

### GAP-OVERRIDE-005: Trio uses Exercise eventType for overrides

**Scenario**: Cross-system override visualization

**Description**: Trio uploads overrides as `Exercise` eventType to Nightscout, not `Temporary Override` like Loop. This makes Trio overrides invisible in Loop-focused Nightscout views and vice versa.

**Evidence**:
```swift
// OverrideStored+helper.swift:34-36
enum EventType: String, JSON {
    case nsExercise = "Exercise"
}
```

**Impact**:
- Trio overrides appear as "Exercise" events in Nightscout
- Loop/Trio override data not interchangeable
- Followers using Loop-compatible apps don't see Trio overrides correctly

**Possible Solutions**:
1. Trio could adopt `Temporary Override` eventType (breaking change)
2. Nightscout could normalize both to standard `Override` type
3. Add cross-system mapping layer

**Status**: Documented

**Related**:
- [Override Comparison](../docs/10-domain/override-profile-switch-comparison.md)
- GAP-OVERRIDE-001

---

---

### GAP-OVERRIDE-006: Three incompatible eventTypes for therapy adjustments

**Scenario**: Unified override visualization

**Description**: Loop uses `Temporary Override`, AAPS uses `Profile Switch`, Trio uses `Exercise`. All represent similar user intent (temporary therapy adjustment) but are incompatible.

**Evidence**:
| System | eventType |
|--------|-----------|
| Loop | `Temporary Override` |
| AAPS | `Profile Switch` |
| Trio | `Exercise` |

**Impact**:
- No unified "what adjustment was active at time T" query
- Careportal doesn't have unified override entry
- Follower apps must handle three different patterns
- Cannot aggregate override usage across systems

**Possible Solutions**:
1. Define standard `Override` eventType in Nightscout
2. Add eventType aliasing/normalization
3. Document mapping for follower apps

**Status**: Documented

**Related**:
- [Override Comparison](../docs/10-domain/override-profile-switch-comparison.md)
- GAP-001, GAP-002

**Related Requirements**: REQ-OVRD-001, REQ-OVRD-004, REQ-DS-003

---

---

### GAP-OVERRIDE-007: Trio override upload loses algorithm settings

**Scenario**: Nightscout data completeness

**Description**: Trio's override upload only includes `duration`, `notes` (name), and `eventType`. The rich algorithm settings (`smbIsOff`, `percentage`, `target`, `smbMinutes`, `uamMinutes`) are not uploaded.

**Evidence**:
```swift
// OverrideStorage.swift:261-269
return NightscoutExercise(
    duration: Int(truncating: duration),
    eventType: OverrideStored.EventType.nsExercise,
    createdAt: override.date ?? Date(),
    enteredBy: NightscoutExercise.local,
    notes: override.name ?? "Custom Override",
    id: UUID(uuidString: override.id ?? UUID().uuidString)
)
// Missing: percentage, target, smbIsOff, smbMinutes, uamMinutes
```

**Impact**:
- Nightscout doesn't reflect actual therapy adjustment
- Cannot analyze insulin percentage changes from Nightscout data
- Following a Trio user, cannot see full override configuration

**Possible Solutions**:
1. Add extension fields to Nightscout treatment schema
2. Trio uploads additional fields in `notes` or custom fields
3. Define standard override schema that includes oref1 fields

**Status**: Documented

**Related**:
- [Override Comparison](../docs/10-domain/override-profile-switch-comparison.md)
- GAP-OVERRIDE-004

**Related Requirements**: REQ-OVRD-002, REQ-PROF-003

---

---

### GAP-REMOTE-001: Remote command authorization unverified

**Scenario**: Remote control scenarios, authority hierarchy

**Description**: Loop remote commands (override, carb, bolus) track `remoteAddress` but there's no verification of sender authority. Additionally, override commands explicitly skip OTP validation while bolus/carb commands require it.

**Loop-Specific Evidence**: 
- Remote commands set `enactTrigger = .remote(address)` and `enteredBy = "Loop (via remote command)"` but no permission check
- Override commands: `otpValidationRequired() -> Bool { return false }` (OverrideRemoteNotification.swift)
- Bolus/carb commands: `otpValidationRequired() -> Bool { return true }`

**Source**: 
- [Loop Nightscout Sync](../mapping/loop/nightscout-sync.md#gap-remote-001-remote-command-authorization)
- [Remote Commands Comparison](../docs/10-domain/remote-commands-comparison.md)

**Impact**:
- Anyone with Nightscout API access can issue override commands without OTP
- No authority hierarchy for remote vs local commands
- Overrides can significantly affect insulin delivery via ISF/CR adjustments
- Related to GAP-AUTH-001 (unverified enteredBy)

**Possible Solutions**:
1. Require OTP for all remote commands including overrides (recommended)
2. OIDC-based command authorization
3. Gateway-level command filtering (NRG)

**Status**: Under discussion

**Related**:
- [GAP-AUTH-001](#gap-auth-001-enteredby-field-is-unverified)
- [Authority Model](../docs/10-domain/authority-model.md)
- [Remote Commands Comparison](../docs/10-domain/remote-commands-comparison.md)

---

## Pump Protocol Gaps

---

### GAP-REMOTE-002: No Command Signing Across Systems

**Scenario**: Remote command security, interoperability

**Description**: None of the systems use asymmetric cryptographic signatures to verify command origin. Trio uses symmetric encryption (AES-256-GCM), which provides integrity via authenticated encryption but requires shared secrets. Loop and AAPS send commands in plaintext (OTP provides auth but not confidentiality or integrity).

**Evidence**:
- Trio: `SecureMessenger` uses AES-GCM (symmetric)
- Loop: Commands are JSON in push notification payload (plaintext)
- AAPS: SMS text commands (plaintext)

**Impact**:
- Loop: Anyone with Nightscout API access can forge commands (OTP partially mitigates)
- AAPS: Phone number spoofing could bypass whitelist (OTP still required)
- No non-repudiation (cannot prove who sent a command)

**Possible Solutions**:
1. ECDSA signatures on command payloads
2. HMAC signing with per-command nonces
3. Mutual TLS for Nightscout command channel

**Status**: Under discussion

**Related**:
- [Remote Commands Comparison](../docs/10-domain/remote-commands-comparison.md)
- REQ-REMOTE-001

---

---

### GAP-REMOTE-003: No Key Rotation Mechanism

**Scenario**: Remote command security, key management

**Description**: None of the systems have visible mechanisms for automatic key rotation:
- Trio: Shared secret stored indefinitely in UserDefaults
- Loop: OTP secret can be reset manually but no scheduled rotation
- AAPS: OTP secret persists until manually regenerated

**Impact**:
- Long-lived secrets increase risk of compromise
- Compromised keys remain valid indefinitely
- No way to detect key compromise

**Possible Solutions**:
1. Time-limited shared secrets with automatic rotation
2. Push-based key refresh via APNS/FCM
3. OIDC-based short-lived tokens

**Status**: Under discussion

**Related**:
- [Remote Commands Comparison](../docs/10-domain/remote-commands-comparison.md)

---

---

### GAP-REMOTE-004: Inconsistent Safety Enforcement Layer

**Scenario**: Remote command safety, code architecture

**Description**: Safety limits are enforced at different layers across systems:
- Trio: Enforces max bolus, max IOB, and 20% recent bolus rule in remote command handler
- Loop: Delegates to downstream dosing logic (LoopDataManager)
- AAPS: Uses centralized ConstraintChecker

**Impact**:
- Harder to audit remote command safety
- Potential for inconsistent behavior between local and remote commands
- Different error messages and rejection reasons

**Possible Solutions**:
1. Standardize safety check layer (recommend command handler)
2. Document safety enforcement architecture per system
3. Create unified test suite for remote command limits

**Status**: Under discussion

**Related**:
- [Remote Commands Comparison](../docs/10-domain/remote-commands-comparison.md)
- REQ-REMOTE-003

---

---

### GAP-REMOTE-005: remoteAddress Field Purpose Unclear

**Scenario**: Override Remote Commands

**Description**: LoopCaregiver's `OverrideAction` and `OverrideCancelAction` include a `remoteAddress` field that is always set to empty string. The purpose of this field is undocumented in the codebase. It may be intended for APNS device tokens or notification routing, but this is speculation.

**Source**: `loopcaregiver:LoopCaregiverKit/Sources/LoopCaregiverKit/Nightscout/NightscoutDataSource.swift#L160-L162`
```swift
// TODO: remoteAddress should be optional
let action = NSRemoteAction.override(name: overrideName, durationTime: durationTime, remoteAddress: "")
```

**Impact**:
- Unclear if missing remoteAddress causes issues
- Field appears mandatory but always empty
- Potential dead code or incomplete feature

**Possible Solutions**:
1. Investigate Loop-side usage of remoteAddress
2. Make remoteAddress truly optional
3. Document intended purpose

**Status**: Under discussion

---

---

### GAP-REMOTE-006: No Command Retry Mechanism

**Scenario**: Remote Command Reliability

**Description**: LoopCaregiver has no built-in retry mechanism for failed command deliveries. If a command upload fails (network error, server error), the user must manually retry. There's also no indication if a command was partially delivered.

**Source**: `loopcaregiver:LoopCaregiverKit/Sources/LoopCaregiverKit/Nightscout/NightscoutDataSource.swift` - No retry logic present

**Impact**:
- Commands may be silently lost on network failures
- User may be unaware of failed delivery
- No idempotency handling for retries

**Possible Solutions**:
1. Implement automatic retry with exponential backoff
2. Add command queue with persistent storage
3. Implement idempotency keys to prevent duplicates on retry

**Status**: Under discussion

---

---

### GAP-REMOTE-007: OTP Secret Stored in App Data, Not Keychain

**Scenario**: Credential Security

**Description**: LoopCaregiver stores the full `otpURL` (including the Base32 secret) in the `NightscoutCredentials` struct, which is likely persisted to app data rather than the Keychain. This differs from Loop which stores OTP secrets in the Keychain.

**Source**: `loopcaregiver:LoopCaregiverKit/Sources/LoopCaregiverKit/Models/DeepLinkParser.swift#L164` - `otpURL` stored in credentials

**Impact**:
- OTP secret may be accessible via device backup
- Less secure than Keychain storage
- Inconsistent with Loop-side security model

**Possible Solutions**:
1. Move OTP secret to Keychain
2. Keep only reference ID in credentials
3. Document security implications

**Status**: Under discussion

---

## LoopFollow Gaps

---

### GAP-REMOTE-008: Nightscout has no server-side bolus limits

**Scenario**: Remote bolus safety

**Description**: Nightscout acts purely as a relay for remote bolus commands, sending them via APNs without any server-side validation of bolus amounts. The max bolus, max IOB, and other safety limits are only enforced on the receiving client (Loop/Trio).

**Evidence**:
- `externals/cgm-remote-monitor/lib/server/loop.js:95-104`: Only checks `remoteBolus > 0`, no upper limit
- No access to user's max bolus setting
- No IOB awareness

**Impact**:
- Malformed API requests could relay excessive bolus amounts
- Server cannot provide defense-in-depth
- Compromised API secret = unrestricted command access

**Possible Solutions**:
1. Add optional `maxRemoteBolus` setting to Nightscout config
2. Store max bolus from profile and validate against it
3. Accept as design (client is authoritative)

**Status**: Under discussion

**Related**:
- [Remote Bolus Comparison](../docs/10-domain/remote-bolus-comparison.md)

---

---

### GAP-REMOTE-009: No unified remote command protocol

**Scenario**: Cross-system interoperability

**Description**: Loop, AAPS, and Trio use completely different payload formats and authentication mechanisms for remote commands:
- Loop: JSON with `bolus-entry`, OTP via APNs
- AAPS: SMS text commands with passcode confirmation
- Trio: Encrypted JSON with shared secret via APNs

**Impact**:
- Caregivers need different apps/tools for different AID systems
- No single caregiver app can work across all systems
- Documentation and support burden multiplied

**Possible Solutions**:
1. Define common `RemoteCommand` schema in Nightscout API v4
2. Create universal caregiver app with system adapters
3. Accept divergence (different systems, different needs)

**Status**: Under discussion

**Related**:
- [Remote Bolus Comparison](../docs/10-domain/remote-bolus-comparison.md)
- GAP-REMOTE-004

**Related Requirements**: REQ-FOLLOW-002, REQ-REMOTE-001, REQ-LOOPCAREGIVER-003

---

---

### GAP-TREAT-001: Absorption Time Unit Mismatch

**Scenario**: [Treatment Sync Validation](../conformance/assertions/treatment-sync.yaml)

**Description**: Loop and Trio use seconds for carb absorption time; Nightscout stores in minutes. Unit conversion errors can cause significantly incorrect absorption modeling.

**Impact**: 
- Carb entries with incorrect absorption time affect IOB/COB calculations
- Cross-system data correlation may misinterpret absorption duration

**Test Coverage**: `conformance/unit-conversions/conversions.yaml` - Tests `loop-absorption-time-3hr`, `loop-absorption-time-2hr`

**Possible Solutions**:
1. Explicit unit conversion in upload/download logic
2. Standardize on ISO 8601 duration format
3. Add `absorptionTimeUnit` field to treatments

**Status**: Under discussion

**Related**:
- [Treatments Deep Dive](../docs/10-domain/treatments-deep-dive.md)

---

---

### GAP-TREAT-002: Duration Unit Inconsistency

**Scenario**: [Treatment Sync Validation](../conformance/assertions/treatment-sync.yaml)

**Description**: Duration units vary across systems:
- Loop: Seconds
- AAPS: Milliseconds  
- Nightscout: Minutes

**Impact**:
- Temp basal duration could be off by orders of magnitude
- eCarbs duration misinterpreted

**Test Coverage**: `conformance/unit-conversions/conversions.yaml` - Tests `aaps-temp-basal-duration-*`, `aaps-ecarbs-duration-4hr`

**Possible Solutions**:
1. Standardize on minutes for Nightscout interchange
2. Use ISO 8601 duration format (`PT30M`)
3. Explicit unit field on duration

**Status**: Analyzed - see [Duration/utcOffset Impact Analysis](../docs/10-domain/duration-utcoffset-unit-analysis.md)

**Requirements**: REQ-UNIT-001, REQ-UNIT-002, REQ-UNIT-004

**Related**:
- [Treatments Deep Dive](../docs/10-domain/treatments-deep-dive.md)
- [Duration/utcOffset Impact Analysis](../docs/10-domain/duration-utcoffset-unit-analysis.md)

---

---

### GAP-TREAT-003: No Explicit SMB Event Type

**Scenario**: SMB identification and analytics

**Description**: Nightscout lacks an explicit `SMB` eventType. AAPS uploads SMBs with `eventType: "Correction Bolus"` plus a separate `type: "SMB"` field, but other systems may not include this field. Systems without the `type` field must infer SMBs from `automatic: true` + small insulin amount, which is unreliable.

**Impact**:
- Cannot reliably query for SMB events across all AID systems
- Manual correction boluses may be confused with automatic SMBs
- Analytics and reporting vary by system

**Possible Solutions**:
1. All AID systems adopt AAPS convention of including `type: "SMB"` field
2. Add explicit `eventType: "SMB"` to Nightscout schema
3. Add `isSMB: true` boolean field

**Status**: Under discussion

**Related**:
- [AAPS Bolus Types](../mapping/aaps/README.md)
- [Treatments Deep Dive](../docs/10-domain/treatments-deep-dive.md)

---

---

### GAP-TREAT-004: Split/Extended Bolus Representation Mismatch

**Scenario**: Extended bolus round-trip

**Description**: 
- AAPS represents extended boluses via `FAKE_EXTENDED` temp basal type
- Loop infers square wave from `duration >= 30min`
- Nightscout has explicit `splitNow`/`splitExt` fields for combo boluses

**Impact**:
- Extended/combo boluses may not round-trip correctly between systems
- Insulin delivery interpretation differs

**Possible Solutions**:
1. Standardize on Nightscout combo bolus fields
2. Add explicit `bolusType` enum with `EXTENDED`, `COMBO`, `NORMAL`
3. Document semantic mapping rules

**Status**: Needs ADR

**Related**:
- [Treatments Deep Dive](../docs/10-domain/treatments-deep-dive.md)

---

---

### GAP-TREAT-005: Loop POST-Only Creates Duplicates

**Scenario**: Treatment sync retry scenarios

**Description**: Loop uses POST (not PUT) for treatment uploads, which may create duplicates if network request is retried.

**Source**: `NightscoutServiceKit/Extensions/DoseEntry.swift`
```swift
/* id: objectId, */ /// Specifying _id only works when doing a put (modify)
```

**Impact**:
- Duplicate treatments in Nightscout after network retries
- IOB/COB calculations may double-count insulin/carbs

**Possible Solutions**:
1. Switch to PUT with `syncIdentifier` as dedup key
2. Use API v3 with `identifier` field
3. Server-side deduplication on `syncIdentifier`

**Status**: Under discussion

**Related**:
- [GAP-003](#gap-003-no-unified-sync-identity-field-across-controllers)
- [Loop Nightscout Sync](../mapping/loop/nightscout-sync.md)

---

---

### GAP-TREAT-006: Retroactive Edit Handling

**Scenario**: Treatment edit/delete sync

**Description**: 
- Loop tracks `userUpdatedDate` but doesn't sync updates to Nightscout
- AAPS uses `isValid: false` for soft deletes
- Nightscout has no standard edit history or soft delete mechanism

**Impact**:
- Edited treatments may not sync properly
- Deleted treatments may persist in Nightscout
- No audit trail for treatment modifications

**Possible Solutions**:
1. Add `modifiedAt`, `deletedAt` fields to treatments
2. Use API v3 `isValid` field consistently
3. Sync updates via PUT with version tracking

**Status**: Under discussion

**Related**:
- [Treatments Deep Dive](../docs/10-domain/treatments-deep-dive.md)

---

---

### GAP-TREAT-007: eCarbs Not Universally Supported

**Scenario**: Extended carbs cross-system sync

**Description**: Extended carbs (eCarbs) with `duration` field are supported by AAPS and Nightscout but not by Loop.

**Impact**:
- eCarbs entered in AAPS won't be properly interpreted by Loop followers
- COB calculation differs between systems

**Possible Solutions**:
1. Loop adds eCarbs support
2. Nightscout decomposes eCarbs into multiple entries
3. Document limitation for users

**Status**: Under discussion

**Related**:
- [Treatments Deep Dive](../docs/10-domain/treatments-deep-dive.md)

---

### GAP-TREAT-010: eventType Immutability Not Enforced in Nocturne

**Scenario**: Treatment update behavior

**Description**: cgm-remote-monitor enforces eventType immutability on update operations, preventing changes to eventType after creation. Nocturne does not enforce this constraint.

**Evidence**:
- cgm-remote-monitor: `lib/api3/generic/update/validate.js:21` - eventType in immutable list
- Nocturne: No immutability check in TreatmentRepository update path

**Impact**: Low - eventType changes are rare in practice. Could cause sync issues if eventType used for deduplication key changes.

**Remediation**: Add eventType to immutable fields in Nocturne update validation.

**Source**: [eventType Handling Analysis](../docs/10-domain/nocturne-eventtype-handling.md)

**Status**: Open - Low Priority

---

### GAP-TREAT-011: Temporary Target Type Missing from Nocturne Enum

**Scenario**: AAPS treatment compatibility

**Description**: The `Temporary Target` eventType used by AAPS is not defined in Nocturne's TreatmentEventType enum, though unknown types are still accepted.

**Evidence**:
- AAPS: Uses `Temporary Target` for TT treatments
- Nocturne: `TreatmentEventType.cs` - 28 types defined, no `TemporaryTarget`

**Impact**: Low - unknown types accepted as strings, just not in typed enum for configuration.

**Remediation**: Add `TemporaryTarget` to TreatmentEventType enum for completeness.

**Source**: [eventType Handling Analysis](../docs/10-domain/nocturne-eventtype-handling.md)

**Status**: Open - Low Priority

---

### GAP-TREAT-012: v1 API Incorrectly Coerces UUID _id to ObjectId

**Scenario**: Loop Temporary Override sync via v1 API

**Description**: Nightscout v1 API accepts client-supplied string `_id` values on POST (create), but later treats those same `_id` values as if they must be MongoDB ObjectIds. This breaks UPDATE and DELETE operations for treatments with UUID-style `_id` values.

Loop uploads Temporary Override treatments with UUID `_id`:
```json
{
  "_id": "69F15FD2-8075-4DEB-AEA3-4352F455840D",
  "eventType": "Temporary Override",
  "created_at": "2026-02-17T02:00:16.000Z",
  "durationType": "indefinite",
  "correctionRange": [90, 110],
  "insulinNeedsScaleFactor": 1.2,
  "reason": "Override Name"
}
```

**Evidence**:
- Loop: `LoopKit/NightscoutKit` uses `syncIdentifier.uuidString` as `_id`
- v1 POST accepts UUID string and stores it
- v1 DELETE/PUT attempts ObjectId coercion, fails for UUID strings
- Issue: [nightscout/cgm-remote-monitor#8450](https://github.com/nightscout/cgm-remote-monitor/issues/8450)

**Source Code Analysis** (2026-03-10):

| File | Line | Code | Behavior |
|------|------|------|----------|
| `OverrideTreament.swift` | 59 | `id: override.syncIdentifier.uuidString` | UUID put directly in `id` param |
| `NightscoutTreatment.swift` | 111 | `rval["_id"] = id` | `id` param becomes `_id` in JSON |
| `NightscoutService.swift` | 165 | `deleted.map { $0.syncIdentifier.uuidString }` | Delete uses UUID as `_id` |
| `SyncCarbObject.swift` | 25 | `syncIdentifier: syncIdentifier` | Carbs send SEPARATE `syncIdentifier` |
| `DoseEntry.swift` | 31 | `syncIdentifier: syncIdentifier` | Doses send SEPARATE `syncIdentifier` |
| `ObjectIdCache.swift` | 56-58 | `add(syncIdentifier, objectId)` | Carbs/doses cache server `_id` |

**Why Override is Different**: Override calls `OverrideTreatment.init(id: syncIdentifier.uuidString)` which puts the UUID directly into the `_id` field via the base class. Carbs and doses instead pass `id: objectId` (from ObjectIdCache, or nil) and `syncIdentifier: syncIdentifier` as separate parameters.

**Impact**: Critical
- Override sync gets stuck after indefinite override
- Later override banners stop appearing on graph
- Loop retry loop blocks newer override treatments
- Graph overlay persists incorrectly (driven by treatments, not devicestatus)

**Root Cause**:
1. `_id` coercion too aggressive - assumes all `_id` must be 24-hex ObjectId
2. Upsert matching ignores client `_id` - matches by `created_at + eventType` instead
3. UUID strings like `69F15FD2-8075-4DEB-AEA3-4352F455840D` are not valid ObjectIds

**Remediation**:
1. Only convert `_id` to ObjectId when it is 24-character hex string
2. Leave UUID/string `_id` values as strings
3. Prefer `_id` as upsert key when client supplied one
4. Ensure PUT/DELETE work for both string and ObjectId ids
5. Fall back to `created_at + eventType` only for legacy callers without `_id`

**Source**:
- `lib/api/treatments/index.js` - v1 treatment API
- `lib/server/treatments.js` - treatment storage layer
- PR: [#8447](https://github.com/nightscout/cgm-remote-monitor/pull/8447) - Fix implementation

**Sync Identity Field Mapping** (verified 2026-03-10):

| System | Treatment Type | Field Sent | Used as `_id`? | Code Reference |
|--------|---------------|------------|----------------|----------------|
| **Loop** | Carbs | `syncIdentifier` | No (ObjectIdCache) | `SyncCarbObject.swift:25` |
| **Loop** | Doses (bolus/temp) | `syncIdentifier` | No (commented out) | `DoseEntry.swift:30-31` |
| **Loop** | **Overrides** | `_id = syncIdentifier.uuidString` | **YES** ← Problem | `OverrideTreament.swift:59` |
| **AAPS** | All (v3 SDK) | `identifier` | No (server assigns) | `NSClientV3Plugin.kt` |
| **AAPS** | Pump events | `pumpId` + `pumpSerial` | No | `IDs.kt:19-22` |
| **xDrip+** | Treatments | `uuid` | Sometimes | `Treatments.java` |

**Key Finding**: Loop's **override** treatment is the exception - it puts `syncIdentifier` directly into `_id`, while all other Loop treatments send `syncIdentifier` as a separate field and use ObjectIdCache to track server-assigned `_id`.

**DoseEntry Code Comment** (line 30-31):
```swift
/* id: objectId, */ /// Specifying _id only works when doing a put (modify);
                    /// all dose uploads are currently posting so they can be either create or update
syncIdentifier: syncIdentifier,
```
This explains why doses intentionally DON'T send `_id` - they let the server handle deduplication via `syncIdentifier`.

**Fix Options Analysis**:

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| A. Accept UUID `_id` | Current PR #8447 | Minimal change, backward compatible | Mixed `_id` formats in DB (permanent) |
| B. Server dedup by `syncIdentifier` | Match on `syncIdentifier` instead of `_id` | Clean separation | Overrides don't send separate `syncIdentifier` |
| C. Loop sends `syncIdentifier` field | Change override to match carbs/doses pattern | Consistent client behavior | Requires Loop release, breaking change |
| D. Strip non-ObjectId `_id` | Only accept 24-hex ObjectIds | DB consistency | **BREAKS Loop sync** - no dedup key after cache loss |
| E. Identifier-First Architecture | Use `identifier` as primary key, `_id` internal only | Clean, offline-first, v3-aligned | Migration needed, mixed `_id` formats |
| F. Server-Controlled ID | Server generates `_id`, client UUID → `identifier` | Clean, Nocturne-aligned, optimal MongoDB | Requires phased migration |
| **G. Immediate Transparent Promotion** | UUID `_id` → `identifier` + server ObjectId, immediate | **No breakage, no DB poisoning, clean from day 1** | Slightly larger change |

### Option G: Immediate Transparent Promotion (RECOMMENDED)

**Concept**: On POST, if client sends non-ObjectId `_id`, immediately:
1. Move it to `identifier` field (preserve for client)
2. Generate server ObjectId for `_id` (clean DB)
3. Return both in response (client can use either)

**On PUT/DELETE**: Accept lookup by `_id` OR `identifier`

**Implementation in `lib/server/treatments.js`**:

```javascript
function normalizeTreatmentId (obj) {
  if (!Object.prototype.hasOwnProperty.call(obj, '_id') || obj._id === null || obj._id === '') {
    return;
  }

  // Standard ObjectId string → convert to ObjectId
  if (typeof obj._id === 'string' && OBJECT_ID_HEX_RE.test(obj._id)) {
    obj._id = new ObjectID(obj._id);
    return;
  }

  // Non-ObjectId (UUID from Loop override, etc):
  // Promote to identifier, generate server ObjectId
  if (typeof obj._id === 'string') {
    // Preserve client's sync identifier
    if (!obj.identifier) {
      obj.identifier = obj._id;
    }
    // Server generates proper ObjectId
    obj._id = new ObjectID();
  }
}

function upsertQueryFor (obj, results) {
  // Lookup by identifier first (handles Loop override re-upload)
  if (obj.identifier) {
    return { identifier: obj.identifier };
  }
  // Then by _id if present
  if (Object.prototype.hasOwnProperty.call(obj, '_id') && obj._id !== null && obj._id !== '') {
    return { _id: obj._id };
  }
  // Fallback to time+type
  return {
    created_at: results.created_at,
    eventType: obj.eventType
  };
}
```

**Why This Achieves All 4 Goals**:

| Goal | How Option G Achieves It |
|------|--------------------------|
| 1. No breakage | Loop override still syncs; client receives `identifier` matching what it sent |
| 2. Special handling | UUID detection triggers promotion; ObjectId clients unaffected |
| 3. No DB poisoning | `_id` is always ObjectId; client value preserved in `identifier` |
| 4. Clean future | `identifier` field ready for v3 API, no migration debt |

**Loop Override Workflow After Option G**:

```
Loop sends:       { "_id": "69F15FD2-...", "eventType": "Temporary Override", ... }
Server stores:    { "_id": ObjectId("..."), "identifier": "69F15FD2-...", ... }
Server returns:   { "_id": "67d...", "identifier": "69F15FD2-...", ... }
Loop re-uploads:  { "_id": "69F15FD2-...", ... }  (cache lost)
Server matches:   { identifier: "69F15FD2-..." }  ← No duplicate!
```

**Index Required**:
```javascript
api.indexedFields.push('identifier');  // Add to existing indexes
```

**Backward Compatibility**:
- Clients sending ObjectId `_id`: No change in behavior
- Clients sending UUID `_id` (Loop overrides): Now works correctly with clean DB
- Clients reading `_id`: Still works (now always ObjectId)
- v3 API: `identifier` field already aligned

**Recommendation**: **Option G (Server-Controlled ID with Transparent Promotion)** because:
1. No breakage for any client
2. No "DB poisoning" - all `_id` values are proper ObjectIds
3. Clean from day 1 - no migration debt
4. Full server-controlled ID implemented immediately

**No Phasing Required**: Analysis shows no major client depends on preserving their `_id`:
- Loop (carbs/doses): Caches server's `_id` → No dependency
- Loop (overrides): UUID → promoted to `identifier` → Fixed
- AAPS: Already uses server-assigned `_id` → No dependency  
- xDrip+: Sends `uuid` field, not `_id` → No dependency

**Implementation** (all at once):

```javascript
function normalizeTreatmentId(obj) {
  // 1. Extract client sync identity from any source
  const clientIdentifier = obj.identifier 
    || obj.syncIdentifier                    // Loop carbs/doses
    || obj.uuid                              // xDrip+
    || (typeof obj._id === 'string' && !OBJECT_ID_HEX_RE.test(obj._id) ? obj._id : null);
  
  if (clientIdentifier && !obj.identifier) {
    obj.identifier = clientIdentifier;
  }
  
  // 2. Server controls _id
  if (typeof obj._id === 'string' && OBJECT_ID_HEX_RE.test(obj._id)) {
    obj._id = new ObjectID(obj._id);  // Accept ObjectId for backward compat
  } else {
    obj._id = new ObjectID();         // Generate fresh ObjectId
  }
}

function upsertQueryFor(obj, results) {
  // Priority: identifier > _id > time+type
  if (obj.identifier) return { identifier: obj.identifier };
  if (obj._id) return { _id: obj._id };
  return { created_at: results.created_at, eventType: obj.eventType };
}
```

### Comprehensive Strategy Comparison

#### Maintainability

| Aspect | Option A (Accept UUID) | Option G (Transparent Promotion) |
|--------|------------------------|----------------------------------|
| **Code complexity** | ~5 lines changed | ~20 lines changed |
| **Index requirements** | None new | `identifier` index (sparse, unique) |
| **Future migration** | Required (UUID→identifier) | None (already clean) |
| **Debt accumulation** | Grows with time | None |
| **Rollback risk** | Low | Low |

#### Database Consistency

| Aspect | Option A | Option G |
|--------|----------|----------|
| **`_id` format** | Mixed (ObjectId + UUID strings) | Always ObjectId |
| **MongoDB optimization** | Degraded (string comparison for UUID) | Optimal (native ObjectId) |
| **Sharding compatibility** | Problematic (mixed key types) | Full |
| **Query predictability** | Must handle both formats | Single format |
| **Index efficiency** | Lower (string vs ObjectId) | Optimal |
| **Existing UUID `_id` docs** | Unchanged (work as-is) | Unchanged (need separate migration) |

#### User Expectations

| Stakeholder | Option A Impact | Option G Impact |
|-------------|-----------------|-----------------|
| **Loop users (short-term)** | ✅ Overrides work | ✅ Overrides work |
| **Loop users (long-term)** | ✅ Continues working | ✅ Continues working |
| **AAPS users** | ✅ No change | ✅ No change, `identifier` aligns |
| **xDrip+ users** | ✅ No change | ✅ No change |
| **API consumers** | ⚠️ Must handle mixed `_id` | ✅ Consistent ObjectId `_id` |
| **Report authors** | ⚠️ UUID strings in queries | ✅ ObjectId everywhere |
| **DB admins** | ⚠️ Mixed formats complicate ops | ✅ Clean, predictable |

#### Long-term Strategic Alignment

| Aspect | Option A | Option G |
|--------|----------|----------|
| **v3 API alignment** | ❌ Still mixed | ✅ `identifier` ready |
| **Nocturne pattern** | ❌ Divergent | ✅ Aligned (Id/OriginalId) |
| **Mobile-first identity** | ❌ Server as client | ✅ Server controls ID |
| **Future client updates** | Required (to send identifier) | Optional (already works) |

#### Risk Assessment

| Risk | Option A | Option G |
|------|----------|----------|
| **Loop breakage** | None | None |
| **AAPS breakage** | None | None |
| **Data loss** | None | None |
| **Performance degradation** | Minor (string _id) | None |
| **Migration complexity later** | Moderate (UUID→identifier) | None |
| **Code review burden** | Low | Low-Medium |

### Test Implementation Note

**Tests should faithfully represent client behavior** - they are independent of fix choice:

```javascript
// This test is IDENTICAL for Option A and Option G:
it('should handle Loop override with UUID _id', async () => {
  const override = {
    _id: '69F15FD2-8075-4DEB-AEA3-4352F455840D',  // What Loop actually sends
    eventType: 'Temporary Override',
    duration: 60,
    reason: 'Pre-Meal'
  };
  
  const response = await POST('/api/v1/treatments', override);
  
  // Assertions differ by option:
  // Option A: expect(response._id).toBe('69F15FD2-...');
  // Option G: expect(response.identifier).toBe('69F15FD2-...');
  //           expect(response._id).toMatch(/^[0-9a-f]{24}$/);  // ObjectId
});
```

**Test harness structure is the same** - only assertions change based on which behavior we're validating.

**Related**:
- [GAP-TREAT-005](#gap-treat-005-loop-post-only-creates-duplicates)
- [GAP-SYNC-005](sync-identity-gaps.md#gap-sync-005-loop-objectidcache-not-persistent)
- [GAP-SYNC-009](sync-identity-gaps.md#gap-sync-009-v1-api-lacks-identifier-field)
- [Loop Overrides](../mapping/loop/overrides.md)
- [Loop Sync Identity Fields](../mapping/loop/sync-identity-fields.md)
- [AAPS Nightscout Sync](../mapping/aaps/nightscout-sync.md)
- [Nocturne Deep Dive](../docs/10-domain/nocturne-deep-dive.md) - Server ID strategy

**Status**: Open - Fix in PR #8447

---

## CGM Data Source Gaps

---


## Alarm Gaps

---

### GAP-ALARM-001: Cross-App Alarm Configuration Sync Not Standardized

**Scenario**: Multi-app alarm management

**Description**: When a user uses multiple caregiver apps (Nightguard, LoopFollow, xDrip+), alarm configurations must be set independently in each app. No standardized mechanism exists to sync alarm preferences across apps.

**Evidence**:
- Nightguard: Local alarm config in UserDefaults
- LoopFollow: Local alarm config in UserDefaults  
- xDrip+: Local alarm config in SQLite database
- No Nightscout collection for alarm preferences

**Impact**:
- Users must configure alarms separately in each app
- Configuration drift between apps leads to alarm fatigue or missed alerts
- No single source of truth for alarm preferences

**Possible Solutions**:
1. Define Nightscout `alarmconfig` collection for portable preferences
2. Document recommended alarm settings in profile collection
3. Accept as device-local preference (current state)

**Related Requirements**: REQ-ALARM-001 through REQ-ALARM-010

**Status**: Open - Feature Request

---

### GAP-ALARM-002: Predictive Alarm Horizon Varies by App

**Scenario**: Predictive low glucose alerting

**Description**: Each caregiver app implements predictive low alarms differently:
- LoopFollow: Uses Loop's predicted glucose array (up to 6 hours)
- xDrip+: Uses linear extrapolation from recent readings
- Nightguard: No predictive alarms

The prediction horizon and algorithm vary significantly.

**Evidence**:
- LoopFollow: Reads `loop.predicted.values` from devicestatus
- xDrip+: `PredictionServiceComponent.kt` uses linear regression
- Nightguard: Threshold-based only

**Impact**:
- Same glucose pattern may trigger alert in one app but not another
- Users cannot reliably configure predictive alarms across apps
- Inconsistent urgency for intervention timing

**Possible Solutions**:
1. Document recommended prediction horizon (15-30 min) in conformance spec
2. Standardize on AID controller predictions when available
3. Accept as implementation variation

**Related Requirements**: REQ-ALARM-004

**Status**: Open - Documentation Gap

---
