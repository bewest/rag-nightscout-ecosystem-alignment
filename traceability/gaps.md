# Gaps

This document tracks gaps that block scenario implementation or conformance. These are not ideas or wish-list items—only concrete blockers.

## Active Gaps

### GAP-001: Nightscout lacks override supersession tracking

**Scenario**: [Override Supersede](../conformance/scenarios/override-supersede/)

**Description**: When a new override is created while another is active, Nightscout does not automatically mark the previous override as superseded. The old override simply expires based on duration.

**Loop-Specific Evidence**: Loop's `TemporaryScheduleOverrideHistory` tracks:
- `actualEnd` with types: `.natural`, `.early(Date)`, `.deleted`
- Override events with modification counters
- Supersession relationships (new override cancels old at `override.startDate.nearestPrevious`)

But `OverrideTreatment` upload only includes `startDate`, `duration`, and settings. None of the lifecycle information is synced.

**Source**: [Loop Override Documentation](../mapping/loop/overrides.md), [Nightscout Sync](../mapping/loop/nightscout-sync.md#gap-001-override-supersession-tracking-critical)

**Impact**: 
- Cannot query "what override was active at time T" reliably
- No audit trail of override changes
- Data imported from Loop/Trio loses supersession relationships
- Cannot distinguish cancelled overrides from naturally-ended ones

**Possible Solutions**:
1. Add `superseded_by`, `actualEndType`, and `actualEndDate` fields to override documents
2. Loop uploads UPDATE when override ends early or is superseded
3. Handle in API layer with timestamp-based inference

**Status**: Under discussion

**Related**: 
- [ADR-001](../docs/90-decisions/adr-001-override-supersession.md)
- [Loop Override Behavior](../mapping/loop/overrides.md)

---

### GAP-002: AAPS ProfileSwitch vs Override semantic mismatch

**Scenario**: [Override Supersede](../conformance/scenarios/override-supersede/)

**Description**: AAPS uses `ProfileSwitch` events rather than explicit overrides. A ProfileSwitch with percentage != 100 or modified targets functions like an override but has different semantics.

**Impact**:
- Mapping from AAPS data to alignment schema requires inference
- Some override patterns (like "return to normal after X hours") aren't explicit

**Possible Solutions**:
1. Define mapping rules for ProfileSwitch → Override conversion
2. Accept ProfileSwitch as a valid alternative representation
3. Create hybrid schema that accommodates both patterns

**Status**: Needs ADR

---

### GAP-003: No unified sync identity field across controllers

**Scenario**: All data synchronization scenarios

**Description**: Different AID controllers use different fields for deduplication and sync identity:
- AAPS uses `identifier`
- Loop uses `syncIdentifier` (UUID string)
- xDrip uses `uuid`

**Loop-Specific Evidence**: Loop uses `syncIdentifier` consistently across doses, carbs, and overrides. However, all uploads use POST (not PUT), which may create duplicates.

**Source**: [Loop Nightscout Sync](../mapping/loop/nightscout-sync.md#gap-sync-001-sync-identifier-idempotency)
```swift
/* id: objectId, */ /// Specifying _id only works when doing a put (modify); all dose uploads are currently posting
```

**Impact**:
- Server-side deduplication is complex
- Reconciliation logic must know controller-specific patterns
- No single field for client-provided unique ID
- POST-based uploads may create duplicates

**Possible Solutions**:
1. Define a standard `syncId` field all controllers should use
2. Controllers register their sync identity schema (inversion of control)
3. Accept current diversity and document mapping rules
4. Nightscout should support upsert on `syncIdentifier`

**Status**: Under discussion

**Related**:
- [Treatments Schema](../externals/cgm-remote-monitor/docs/data-schemas/treatments-schema.md)
- [Data Collections Mapping](../mapping/nightscout/data-collections.md)
- [Loop Nightscout Sync](../mapping/loop/nightscout-sync.md)

---

### GAP-AUTH-001: `enteredBy` field is unverified

**Scenario**: Authorization and audit scenarios

**Description**: The `enteredBy` field in treatments is a free-form nickname with no authentication verification. Anyone can claim to be anyone.

**Impact**:
- Cannot audit who actually made changes
- No accountability for data mutations
- Cannot implement authority-based conflict resolution

**Possible Solutions**:
1. OIDC Actor Identity - replace with verified claims
2. Add separate verified `actor` field alongside legacy `enteredBy`
3. Gateway-level identity injection

**Status**: Under discussion

**Related**:
- [OIDC Actor Identity Proposal](../externals/cgm-remote-monitor/docs/proposals/oidc-actor-identity-proposal.md)
- [Authorization Mapping](../mapping/nightscout/authorization.md)

---

### GAP-AUTH-002: No authority hierarchy in Nightscout

**Scenario**: Conflict resolution scenarios

**Description**: Nightscout treats all authenticated writes equally. There is no concept of authority levels (human > agent > controller).

**Impact**:
- Controllers can overwrite human-initiated overrides
- No protection for primary user decisions
- Cannot implement safe AI agent integration

**Possible Solutions**:
1. Implement authority levels in API layer
2. Add authority field to treatments
3. Handle in gateway layer (NRG)

**Status**: Proposed in conflict-resolution.md

**Related**:
- [Conflict Resolution Proposal](../externals/cgm-remote-monitor/docs/proposals/conflict-resolution.md)
- [Authority Model](../docs/10-domain/authority-model.md)

---

### GAP-SYNC-004: Override supersession not tracked in sync

**Scenario**: [Override Supersede](../conformance/scenarios/override-supersede/), [Sync Deduplication](../conformance/assertions/sync-deduplication.yaml)

**Description**: When an override is superseded by a new override, the lifecycle change is not synced to Nightscout. Loop and Trio only upload the initial override creation, not subsequent status changes.

**Source**: [AID Controller Sync Patterns - Gaps and Recommendations](../mapping/cross-project/aid-controller-sync-patterns.md)

**Impact**:
- Historical override queries unreliable
- Cannot determine why an override ended (superseded vs cancelled vs natural end)
- Related to GAP-001 (override supersession tracking)

**Possible Solutions**:
1. Upload override UPDATE when superseded
2. Add `supersededBy`, `actualEndType`, `actualEndDate` fields
3. Server-side inference from timestamps

**Status**: Under discussion

**Related**:
- [GAP-001](#gap-001-nightscout-lacks-override-supersession-tracking)
- [AID Controller Sync Patterns](../mapping/cross-project/aid-controller-sync-patterns.md)

---

### GAP-SYNC-005: Algorithm parameters not synced

**Scenario**: Cross-project algorithm comparison

**Description**: AID controllers do not upload algorithm configuration to Nightscout, making it impossible to understand why different systems make different decisions.

**Controllers affected**: Loop, AAPS, Trio

**Missing data**:
- Insulin model selection (rapid-acting adult, child, etc.)
- Retrospective correction type (Standard vs Integral)
- Carb absorption model parameters
- Safety limits configuration

**Source**: [AID Controller Sync Patterns - DeviceStatus Comparison](../mapping/cross-project/aid-controller-sync-patterns.md)

**Impact**:
- Cannot compare algorithm behavior across systems
- Debugging requires access to device settings
- Research/audit use cases blocked

**Possible Solutions**:
1. Add `algorithm` object to devicestatus
2. Create separate `configuration` collection
3. Include in profile uploads

**Status**: Under discussion

**Related**:
- [GAP-SYNC-002](#gap-sync-002-effect-timelines-not-uploaded-to-nightscout)
- [AID Controller Sync Patterns](../mapping/cross-project/aid-controller-sync-patterns.md)

---

### GAP-SYNC-002: Effect timelines not uploaded to Nightscout

**Scenario**: Cross-project algorithm comparison, debugging

**Description**: Loop computes individual effect timelines but only uploads the final combined prediction. The component effects are lost.

**Loop-Specific Evidence**: `LoopAlgorithmEffects` contains:
- `insulin[]` - Expected glucose change from insulin
- `carbs[]` - Expected glucose change from carbs  
- `momentum[]` - Short-term trajectory
- `retrospectiveCorrection[]` - Unexplained discrepancy correction
- `insulinCounteraction[]` - Observed vs expected glucose change

Only `predicted.values[]` (the combined prediction) is uploaded to `devicestatus.loop`.

**Source**: [Loop Nightscout Sync](../mapping/loop/nightscout-sync.md#gap-sync-002-effect-timelines-not-uploaded)

**Impact**:
- Cannot debug algorithm behavior from Nightscout data
- Cannot compare Loop effects to oref0's separate `predBGs.IOB[]`, `predBGs.COB[]`, etc.
- Critical for cross-project interoperability analysis

**Possible Solutions**:
1. Loop uploads `effects` object alongside `predicted`
2. Nightscout defines schema for effect timelines
3. Optional upload flag for debugging/research mode

**Status**: Under discussion

**Related**:
- [Loop Algorithm Documentation](../mapping/loop/algorithm.md)

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

### GAP-PUMP-006: Medtronic RF Protocol Lacks Encryption

**Scenario**: Pump communication security audit

**Description**: Medtronic pumps using RF communication (via RileyLink) have no encryption on the RF layer. Commands and responses are transmitted in plaintext.

**Source**: Analysis of MinimedKit and AAPS Medtronic driver

**Impact**:
- Replay attacks possible if attacker captures RF traffic
- Message tampering theoretically possible (though pump has safety limits)
- Unlike BLE pumps (DASH, Dana RS), no cryptographic protection

**Possible Solutions**:
1. Accept as known limitation (Medtronic discontinued Loop-compatible models)
2. Document security posture difference for users
3. Use as baseline for security comparison with newer protocols

**Status**: Documentation complete (inherent hardware limitation)

**Related**:
- [Pump Protocols Spec](../specs/pump-protocols-spec.md#4-cross-protocol-comparison)

---

### GAP-PUMP-007: Omnipod EAP-AKA Uses Non-Standard Milenage

**Scenario**: Cryptographic protocol analysis

**Description**: Omnipod DASH uses 3GPP Milenage algorithm for session establishment, but with non-standard operator keys (MILENAGE_OP constant) that are specific to Insulet.

**Source**: `OmniBLE/Bluetooth/Session/Milenage.swift`

**Impact**:
- Implementation requires knowledge of Insulet-specific constants
- Cannot use standard Milenage libraries without modification
- Reverse-engineering dependency for interoperability

**Possible Solutions**:
1. Document constants in protocol specification (done)
2. Accept as implementation detail

**Status**: Documented

**Related**:
- [Pump Protocols Spec - EAP-AKA](../specs/pump-protocols-spec.md#15-security-session-establishment-eap-aka)

---

### GAP-PUMP-008: Dana RS Encryption Type Detection

**Scenario**: Multi-model Dana pump support

**Description**: Dana pumps use three different encryption modes (DEFAULT, RSv3, BLE5) depending on pump model and firmware. Controllers must detect which mode to use during connection.

**Source**: `pump/danars/encryption/BleEncryption.kt`

**Impact**:
- Connection logic must handle all three modes
- CRC calculation differs by mode
- Upgrade path may require encryption mode transitions

**Possible Solutions**:
1. Document detection heuristics from AAPS implementation
2. Create mode-specific initialization sequences

**Status**: Under discussion

**Related**:
- [Pump Protocols Spec - Dana RS](../specs/pump-protocols-spec.md#2-dana-rsi-ble-protocol)

---

### GAP-PUMP-009: History Entry Size Varies by Medtronic Model

**Scenario**: Medtronic history reconciliation

**Description**: Medtronic history entry sizes vary by pump model (512, 522, 523+). A single history decoder must handle all variants using device-type-specific rules.

**Source**: `pump/medtronic/comm/history/pump/PumpHistoryEntryType.kt`

**Impact**:
- History parsing must be model-aware
- New pump models may introduce new entry formats
- Testing requires access to multiple pump models

**Possible Solutions**:
1. Document model-specific sizes in spec (done)
2. Create model detection and routing logic

**Status**: Documented

**Related**:
- [Pump Protocols Spec - Medtronic History](../specs/pump-protocols-spec.md#34-history-entry-types)

---

## Positive Findings

### FINDING-001: Shared exponential IOB formula across projects

**Discovery**: oref0 analysis revealed that the exponential insulin activity curve was directly sourced from Loop.

**Source**: `oref0:lib/iob/calculate.js#L125`
```javascript
// Formula source: https://github.com/LoopKit/Loop/issues/388#issuecomment-317938473
```

**Impact**:
- **oref0, AAPS, Trio, and Loop all use the same exponential insulin model**
- Direct IOB comparison is possible across all major AID systems
- This is a strong foundation for interoperability

**Related**:
- [oref0 Insulin Math](../mapping/oref0/insulin-math.md)
- [Loop Insulin Math](../mapping/loop/insulin-math.md)

---

### FINDING-002: oref0 outputs separate prediction curves (supports GAP-SYNC-002 resolution)

**Discovery**: oref0 (and AAPS/Trio) outputs four separate prediction curves in the algorithm output.

**Source**: `oref0:lib/determine-basal/determine-basal.js#L442-L449`
```javascript
rT.predBGs = {
    IOB: IOBpredBGs,   // Insulin-only prediction
    ZT: ZTpredBGs,     // Zero temp "what-if"
    COB: COBpredBGs,   // With carb absorption
    UAM: UAMpredBGs    // Unannounced meal
};
```

**Impact**:
- Provides reference implementation for what Loop could upload (GAP-SYNC-002)
- Enables detailed algorithm comparison across projects
- AAPS and Trio already upload these arrays to Nightscout `devicestatus.openaps`

**Related**:
- [GAP-SYNC-002](#gap-sync-002-effect-timelines-not-uploaded-to-nightscout)
- [oref0 Algorithm](../mapping/oref0/algorithm.md)

---

## Treatment Sync Gaps

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

**Status**: Under discussion

**Related**:
- [Treatments Deep Dive](../docs/10-domain/treatments-deep-dive.md)

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

## CGM Data Source Gaps

### GAP-CGM-001: Calibration Algorithm Not Tracked in Entries

**Scenario**: CGM data quality analysis

**Description**: Nightscout entries do not track which calibration algorithm produced the `sgv` value. A reading from xDrip+ using "xDrip Original" calibration is indistinguishable from one using "Native" calibration.

**Impact**:
- Cannot determine calibration quality or method
- Cannot compare readings across calibration algorithms
- Debugging calibration issues requires access to uploader settings

**Possible Solutions**:
1. Add `calibration.algorithm` field to entries schema
2. Include calibration metadata in `device` field format
3. Create separate `calibration` collection for provenance

**Status**: Under discussion

**Related**:
- [CGM Data Sources Deep Dive](../docs/10-domain/cgm-data-sources-deep-dive.md)
- [xDrip+ Calibrations](../mapping/xdrip-android/calibrations.md)

---

### GAP-CGM-002: Bridge Device Info Lost in Upload

**Scenario**: CGM hardware troubleshooting

**Description**: When using bridge devices (MiaoMiao, Bubble, etc.), the bridge type and firmware are not captured in Nightscout entries. Only a combined `device` string is stored.

**Impact**:
- Cannot identify bridge-specific issues
- Cannot correlate readings with bridge firmware versions
- Hardware recommendations require manual user reporting

**Possible Solutions**:
1. Standardize `device` field format: `{app}-{bridge}-{transmitter}`
2. Add separate `bridge` object to entries schema
3. Document bridge info in entry `notes` field

**Status**: Under discussion

**Related**:
- [xDrip+ Data Sources](../mapping/xdrip-android/data-sources.md)
- [xDrip4iOS CGM Transmitters](../mapping/xdrip4ios/cgm-transmitters.md)

---

### GAP-CGM-003: Sensor Age Not Standardized

**Scenario**: Sensor lifecycle tracking, reading reliability assessment

**Description**: Sensor age at reading time is not captured in Nightscout entries. xDrip+ local web server includes `sensor.age` but this is not uploaded to Nightscout.

**Impact**:
- Cannot assess reading reliability based on sensor age
- Cannot automatically detect sensor changes
- Cannot correlate sensor performance degradation with age

**Possible Solutions**:
1. Add `sensorAge` field to entries schema
2. Add `sensorStart` timestamp field
3. Include sensor age in extended `device` metadata

**Status**: Under discussion

**Related**:
- [xDrip+ Local Web Server](../mapping/xdrip-android/local-web-server.md)

---

### GAP-CGM-004: No Universal Source Taxonomy

**Scenario**: Multi-uploader environments, duplicate detection

**Description**: The `device` field in entries is free-form text with no standardized format. Different apps use different conventions:
- xDrip+: `"xDrip-DexcomG6"`
- AAPS: `"AAPS"`
- Spike: `"Spike"`
- Share: `"share2"`

**Impact**:
- Programmatic source identification is unreliable
- Duplicate detection across apps is complex
- Source-based filtering requires fuzzy matching

**Possible Solutions**:
1. Define standardized `device` format: `{app}:{version}:{hardware}`
2. Add separate `source` object with structured fields
3. Create device registry for canonical names

**Status**: Under discussion

**Related**:
- [Entries Deep Dive - Source Attribution](../docs/10-domain/entries-deep-dive.md#glucose-source-attribution)
- [GAP-ENTRY-003](#gap-entry-003)

---

### GAP-CGM-005: Raw Values Not Uploaded by iOS

**Scenario**: Calibration validation, algorithm comparison

**Description**: iOS systems (Loop, Trio, xDrip4iOS) typically do not upload raw sensor values (`filtered`, `unfiltered`) to Nightscout. They rely on transmitter-calibrated readings.

**Impact**:
- Cannot recalibrate iOS-sourced readings
- Cannot compare raw vs calibrated values
- Limits retrospective analysis options

**Possible Solutions**:
1. iOS apps extract and upload raw values (requires transmitter protocol changes)
2. Accept limitation and document iOS vs Android differences
3. Use companion bridges (MiaoMiao) that expose raw values

**Status**: Under discussion (likely won't fix due to iOS CGM API limitations)

**Related**:
- [xDrip4iOS CGM Transmitters](../mapping/xdrip4ios/cgm-transmitters.md)
- [GAP-ENTRY-005](../docs/10-domain/entries-deep-dive.md#gap-summary)

---

### GAP-CGM-006: Follower Source Not Distinguished

**Scenario**: Latency analysis, data freshness assessment

**Description**: When CGM data is sourced from follower mode (Nightscout, Dexcom Share, LibreLinkUp), the follower source is not consistently indicated in entries.

**Impact**:
- Cannot distinguish direct sensor data from cloud-sourced data
- Cannot assess data latency (follower modes have 1-5+ minute delays)
- Duplicate detection between direct and follower sources is complex

**Possible Solutions**:
1. Append "-follower" to `device` field when in follower mode
2. Add `sourceType` field: `direct` | `follower` | `cloud`
3. Include original source URL in metadata

**Status**: Under discussion

**Related**:
- [xDrip4iOS Follower Modes](../mapping/xdrip4ios/follower-modes.md)
- [xDrip+ Data Sources - Cloud Followers](../mapping/xdrip-android/data-sources.md#cloud-follower-sources)

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

### GAP-API-001: API v1 Cannot Detect Deletions

**Scenario**: Cross-client data synchronization

**Description**: API v1 clients (Loop, Trio, xDrip+, OpenAPS) cannot detect when documents are deleted by other clients or by API v3 soft-delete. The v1 API has no mechanism to return deleted documents.

**Impact**:
- Stale data may persist in client caches indefinitely
- Deleted treatments may continue to affect IOB calculations
- No way to sync deletion events across clients
- "Zombie" data accumulates over time

**Possible Solutions**:
1. v1 clients implement periodic full-sync to detect missing documents
2. Nightscout adds deletion tombstones to v1 responses
3. v1 clients migrate to v3 history endpoint

**Status**: Under discussion

**Related**:
- [Nightscout API Comparison](../docs/10-domain/nightscout-api-comparison.md)
- [API v1 Compatibility Spec](../externals/cgm-remote-monitor/docs/requirements/api-v1-compatibility-spec.md)

---

## Insulin Curve Gaps

### GAP-INS-001: Insulin Model Metadata Not Synced to Nightscout

**Scenario**: Historical IOB reconstruction, algorithm debugging

**Description**: When treatments are uploaded to Nightscout, no metadata about the insulin model used for IOB calculation is included. Specifically missing:
- Curve type (exponential, bilinear, linear trapezoid)
- Peak time parameter
- DIA setting at time of calculation
- Insulin brand/type

**Source Evidence**:
- Loop uploads bolus with `insulinType?.brandName` but not curve parameters
- oref0/Trio upload bolus without any model metadata
- AAPS stores `insulinConfiguration` locally but doesn't upload to Nightscout

**Impact**:
- Cannot reproduce historical IOB calculations
- Cannot determine why predictions differed from outcomes
- Algorithm debugging requires access to device settings
- Research use cases blocked

**Possible Solutions**:
1. Add `insulinModel` object to treatment schema: `{curve, peak, dia}`
2. Include model metadata in devicestatus uploads
3. Create separate `algorithmSettings` collection

**Status**: Under discussion

**Related**:
- [Insulin Curves Deep Dive](../docs/10-domain/insulin-curves-deep-dive.md)
- REQ-INS-005

---

### GAP-INS-002: No Standardized Multi-Insulin Representation

**Scenario**: MDI users tracking multiple insulin types, smart pen integration

**Description**: xDrip+ uniquely supports tracking multiple insulin types per treatment via `insulinJSON` field containing an array of `InsulinInjection` objects. This format is xDrip+-specific and not recognized by other systems or Nightscout.

**Source Evidence**:
```java
// xDrip+ Treatments.java
@Column(name = "insulinJSON")
public String insulinJSON;  // JSON array of {profileName, units}
```

Nightscout treatments only support single `insulin` field.

**Impact**:
- MDI users cannot track rapid + basal insulin in standard format
- Smart pen data (InPen, NovoPen) loses insulin type on upload
- IOB calculations must fall back to single insulin model
- Cross-system data correlation loses insulin type breakdown

**Possible Solutions**:
1. Add Nightscout schema support for multi-insulin treatments
2. Standardize xDrip+ `insulinJSON` format for adoption
3. Use separate treatment entries per insulin type

**Status**: Under discussion

**Related**:
- [xDrip+ Insulin Management](../mapping/xdrip-android/insulin-management.md)

---

### GAP-INS-003: Peak Time Customization Not Captured in Treatments

**Scenario**: Custom insulin tuning, historical analysis

**Description**: oref0 and AAPS support custom peak times via `useCustomPeakTime` and `insulinPeakTime` profile settings. However, when treatments are recorded, the peak time used for IOB calculation is not captured.

**Source Evidence**:
```javascript
// oref0:lib/iob/calculate.js
if (profile.useCustomPeakTime === true && profile.insulinPeakTime !== undefined) {
    peak = profile.insulinPeakTime;  // Custom peak, but not stored in treatment
}
```

**Impact**:
- Cannot reconstruct IOB with correct curve shape
- Profile changes retroactively affect historical analysis
- Custom tuning decisions not documented

**Possible Solutions**:
1. Include `insulinPeakAtDose` in treatment metadata
2. Capture profile snapshot at treatment time
3. Store peak time in devicestatus algorithm output

**Status**: Under discussion

**Related**:
- REQ-INS-003
- [oref0 Insulin Math](../mapping/oref0/insulin-math.md)

---

### GAP-INS-004: xDrip+ Linear Trapezoid Model Incompatible with AID Exponential

**Scenario**: Cross-system IOB comparison, data portability

**Description**: xDrip+ uses a linear trapezoid model for insulin activity, while all AID systems (Loop, oref0, AAPS, Trio) use the exponential model. These models produce different IOB decay curves from identical dose history.

**Source Evidence**:
- xDrip+: `LinearTrapezoidInsulin.java` uses onset/peak/duration with linear segments
- AID systems: Exponential decay with `tau`, `a`, `S` parameters from shared formula

**Impact**:
- xDrip+ IOB values differ from AAPS IOB for same user
- Smart pen data imported to AID system uses different curve
- Cannot directly compare IOB across CGM app vs AID controller

**Possible Solutions**:
1. xDrip+ adds exponential model option for AID compatibility
2. Document conversion factors between models
3. Accept limitation and document for users

**Status**: Under discussion (architectural difference, likely won't converge)

**Related**:
- [Insulin Curves Deep Dive](../docs/10-domain/insulin-curves-deep-dive.md)
- [xDrip+ Insulin Management](../mapping/xdrip-android/insulin-management.md)

---

## Pump Communication Gaps

### GAP-PUMP-001: No Standardized Pump Capability Exchange Format

**Scenario**: Cross-system pump compatibility, pump switching

**Description**: There is no standardized format for exchanging pump capabilities between systems. Each system defines its own `PumpDescription`, `PumpType`, or protocol-specific structures.

**Impact**:
- Cannot programmatically compare pump capabilities across systems
- No standard way to communicate pump limits to Nightscout
- Pump compatibility matrix must be maintained manually
- New pump support requires updates in each system

**Possible Solutions**:
1. Define standard JSON schema for pump capabilities
2. Add pump capabilities to Nightscout `devicestatus`
3. Create pump registry with standardized attributes

**Status**: Under discussion

**Related**:
- [Pump Communication Deep Dive](../docs/10-domain/pump-communication-deep-dive.md)
- REQ-PUMP-001

---

### GAP-PUMP-002: Extended Bolus Not Supported in Loop Ecosystem

**Scenario**: Extended/combo bolus interoperability

**Description**: Loop and Trio do not support extended (square wave) or dual wave (combo) boluses. AAPS supports extended boluses natively via `setExtendedBolus()` and can emulate via `FAKE_EXTENDED` temp basals.

**Evidence**:
- Loop `PumpManager` has no extended bolus methods
- AAPS `Pump` interface has `setExtendedBolus()` and `cancelExtendedBolus()`
- AAPS uploads extended boluses as temp basals with special type

**Impact**:
- Users switching from AAPS to Loop lose extended bolus capability
- Extended boluses from AAPS appear as temp basals in Loop/Trio
- COB calculations may differ between systems during extended bolus
- No interoperability for extended bolus commands

**Possible Solutions**:
1. Loop adds extended bolus support to PumpManager protocol
2. Define standard Nightscout representation for extended boluses
3. Document limitation for users considering system switch

**Status**: Under discussion (likely won't fix - Loop philosophy differs)

**Related**:
- [Pump Communication Deep Dive](../docs/10-domain/pump-communication-deep-dive.md)

---

### GAP-PUMP-003: TBR Duration Unit Inconsistency

**Scenario**: Temp basal interoperability, cross-system sync

**Description**: Temp basal duration units differ across systems:
- Loop: `TimeInterval` (seconds)
- AAPS: `durationInMinutes` (integer minutes)
- Nightscout: `duration` (minutes)

**Evidence**:
- Loop: `enactTempBasal(unitsPerHour: Double, for duration: TimeInterval, ...)`
- AAPS: `setTempBasalAbsolute(... durationInMinutes: Int, ...)`

**Impact**:
- Unit conversion errors possible during sync
- Off-by-one-minute errors in TBR end time
- Rounding differences may cause TBR overlap or gap

**Possible Solutions**:
1. All systems normalize to minutes for Nightscout interchange
2. Use ISO 8601 duration format (`PT30M`)
3. Explicit unit field in temp basal records

**Status**: Under discussion

**Related**:
- [Pump Communication Deep Dive](../docs/10-domain/pump-communication-deep-dive.md)
- GAP-TREAT-002 (duration unit inconsistency)

---

### GAP-PUMP-004: Pump Error Codes Not Normalized

**Scenario**: Error handling, debugging, alerting

**Description**: Each pump driver returns different error codes and messages. There is no cross-system error code taxonomy.

**Evidence**:
- Dana RS: `0x10` (max bolus), `0x20` (command error), `0x40` (speed error), `0x80` (insulin limit)
- Omnipod: `PodAlarmType` enum with pod-specific codes
- Medtronic: Hardware-specific alarm codes
- Loop: `PumpManagerError` with generic cases

**Impact**:
- Cannot create unified error handling or alerting
- Error messages vary widely across systems
- Debugging requires pump-specific knowledge
- No standard error taxonomy for Nightscout

**Possible Solutions**:
1. Define standard error categories (connectivity, delivery, reservoir, battery, etc.)
2. Map pump-specific codes to standard categories
3. Add structured error field to Nightscout treatments

**Status**: Under discussion

**Related**:
- [Pump Communication Deep Dive](../docs/10-domain/pump-communication-deep-dive.md)

---

### GAP-PUMP-005: No Standard for Delivery Uncertainty Reporting

**Scenario**: Safety, IOB accuracy, command verification

**Description**: When pump commands fail or timeout, the delivery state may be uncertain. Loop has `deliveryIsUncertain` flag, but there's no cross-system standard for reporting this state.

**Evidence**:
- Loop: `PumpManagerStatus.deliveryIsUncertain: Bool`
- AAPS: Implicit in `PumpEnactResult.success` and retry logic
- Nightscout: No field for delivery uncertainty

**Impact**:
- Uncertain deliveries may be double-counted or missed in IOB
- No way to communicate uncertainty to other clients
- Users may not understand why bolus "failed" but insulin was delivered
- Cannot audit delivery uncertainty events

**Possible Solutions**:
1. Add `deliveryUncertain` field to Nightscout treatments
2. Create `uncertainDelivery` event type
3. Standardize uncertainty resolution flow (verify with pump status)

**Status**: Under discussion

**Related**:
- [Pump Communication Deep Dive](../docs/10-domain/pump-communication-deep-dive.md)
- REQ-PUMP-002

---

### GAP-API-002: Identifier vs _id Addressing Inconsistency

**Scenario**: Cross-API document identity

**Description**: API v1 uses `_id` (MongoDB ObjectId), API v3 uses `identifier` (server-assigned). Documents may have both fields with different values, causing confusion when tracking document identity across API versions.

**Impact**:
- Clients using different APIs cannot reliably reference the same document
- Deduplication may change `identifier` for v1-created documents
- No canonical identity field across both APIs

**Possible Solutions**:
1. Use `_id` as canonical identity for v1 clients, `identifier` for v3 clients
2. Ensure `identifier` equals `_id` for new documents
3. Document clear mapping rules

**Status**: Under discussion

**Related**:
- [Nightscout API Comparison](../docs/10-domain/nightscout-api-comparison.md)

---

### GAP-API-003: No API v3 Adoption Path for iOS Clients

**Scenario**: Ecosystem fragmentation

**Description**: Loop and Trio continue to use API v1 with no apparent migration plans. AAPS is the only major v3 client. This creates ecosystem fragmentation where sync behaviors differ significantly.

**Impact**:
- iOS clients lack efficient incremental sync capabilities
- iOS clients cannot detect deletions
- Different authentication and permission models
- Bifurcated documentation and tooling

**Possible Solutions**:
1. Document v3 benefits to encourage iOS client adoption
2. Create Swift SDK for v3 API
3. Accept ecosystem bifurcation and document interoperability patterns

**Status**: Under discussion

**Related**:
- [Nightscout API Comparison](../docs/10-domain/nightscout-api-comparison.md)
- [Loop Nightscout Sync](../mapping/loop/nightscout-sync.md)
- [Trio Nightscout Sync](../mapping/trio/nightscout-sync.md)

---

### GAP-API-004: Authentication Granularity Gap Between v1 and v3

**Scenario**: Access control, follower apps

**Description**: API v1 authentication is all-or-nothing (valid secret grants full `*` permissions). Cannot grant read-only access to specific collections without making the entire site public-readable.

**Impact**:
- Follower apps receive full write access unnecessarily
- No way to create collection-specific tokens
- Cannot audit who performed which operations
- Must choose between full access or public-readable

**Possible Solutions**:
1. Migrate to v3 JWT tokens for fine-grained access control
2. Add role-based tokens to v1 API
3. Use gateway-level access control

**Status**: Under discussion

**Related**:
- [Nightscout API Comparison](../docs/10-domain/nightscout-api-comparison.md)

---

### GAP-API-005: Deduplication Behavior Differs Between API Versions

**Scenario**: Data integrity, duplicate prevention

**Description**: API v3 returns `isDeduplication: true` when a document matches existing data and provides the existing document's `identifier`. API v1 silently accepts potential duplicates without indication.

**Impact**:
- v1 clients may create duplicate documents unknowingly
- v3 clients see duplicates created by v1 clients
- Inconsistent behavior when same document uploaded via both APIs
- No way for v1 clients to know if upload was deduplicated

**Possible Solutions**:
1. Use client-side deduplication with unique `syncIdentifier`
2. Add deduplication indicator to v1 responses
3. Use PUT upsert semantics consistently

**Status**: Under discussion

**Related**:
- [Nightscout API Comparison](../docs/10-domain/nightscout-api-comparison.md)
- GAP-003 (sync identity)

---

### GAP-CGM-001: DiaBLE lacks treatment support

**Scenario**: Bi-directional treatment sync

**Description**: DiaBLE only uploads CGM entries to Nightscout and downloads server status. It cannot create, edit, or sync treatments (bolus, carbs, corrections). Users cannot log insulin or carbs directly from DiaBLE.

**Source**: [DiaBLE Nightscout Sync](../mapping/diable/nightscout-sync.md)

**Impact**:
- DiaBLE users must use another app for treatment logging
- No unified CGM + treatment workflow in DiaBLE
- Cannot use DiaBLE as standalone diabetes management app

**Possible Solutions**:
1. Add treatment API integration to DiaBLE
2. Accept DiaBLE as CGM-only producer (current behavior)
3. Integrate with iOS Shortcuts for treatment logging

**Status**: Informational (DiaBLE design choice)

**Related**:
- [DiaBLE Documentation](../mapping/diable/)
- [CGM Apps Comparison](../mapping/cross-project/cgm-apps-comparison.md)

---

### GAP-CGM-002: xdrip-js limited to Dexcom G5/G6

**Scenario**: CGM data collection for OpenAPS rigs

**Description**: xdrip-js only supports Dexcom G5 and G6 transmitters. It cannot read from Dexcom G7, Libre sensors, or bridge devices. Users with newer sensors cannot use xdrip-js-based solutions.

**Source**: [xdrip-js Documentation](../mapping/xdrip-js/)

**Impact**:
- OpenAPS rigs using Lookout/Logger limited to G5/G6
- No path for G7 users wanting DIY closed-loop on Raspberry Pi
- Libre users must use alternative solutions

**Possible Solutions**:
1. Implement G7 J-PAKE authentication in xdrip-js (complex)
2. Use alternative libraries for G7/Libre (e.g., cgm-remote-monitor bridge)
3. Accept limitation (G5/G6 still widely used)

**Status**: Informational (library scope)

**Related**:
- [xdrip-js BLE Protocol](../mapping/xdrip-js/ble-protocol.md)
- [CGM Apps Comparison](../mapping/cross-project/cgm-apps-comparison.md)

---

### GAP-CGM-003: Libre 3 encryption not fully documented

**Scenario**: Direct Libre 3 sensor reading

**Description**: DiaBLE documents partial Libre 3 support but notes that AES-128-CCM encryption with ECDH key agreement and Zimperium zShield anti-tampering are not fully cracked. DiaBLE can eavesdrop on BLE traffic but cannot independently decrypt sensor data.

**Source**: [DiaBLE CGM Transmitters](../mapping/diable/cgm-transmitters.md)

**Impact**:
- Full independent Libre 3 reading requires external decryption
- Must use trident.realm extraction from rooted devices
- DIY community lacks complete Libre 3 specification

**Possible Solutions**:
1. Continue reverse engineering efforts (Juggluco project)
2. Use LibreLinkUp cloud as alternative data source
3. Document known encryption parameters for community research

**Status**: Under investigation (community effort)

**Related**:
- [DiaBLE README](../externals/DiaBLE/README.md)
- [Libre 3 Technical Blog Post](https://frdmtoplay.com/freeing-glucose-data-from-the-freestyle-libre-3/)

---

### GAP-CGM-004: No standardized Dexcom BLE protocol specification

**Scenario**: Cross-platform CGM integration

**Description**: Dexcom BLE protocol is undocumented by the manufacturer. xdrip-js, DiaBLE, xDrip+, and xDrip4iOS each implement their own reverse-engineered versions. There are subtle differences in authentication handling, backfill parsing, and error recovery.

**Source**: [xdrip-js BLE Protocol](../mapping/xdrip-js/ble-protocol.md), [DiaBLE CGM Transmitters](../mapping/diable/cgm-transmitters.md)

**Impact**:
- Each implementation may have different bugs or limitations
- No authoritative source for protocol behavior
- G6 "Anubis" and G7 protocols add complexity

**Possible Solutions**:
1. Create community-maintained protocol specification
2. Cross-reference implementations to identify discrepancies
3. Accept implementation diversity (current state)

**Status**: Documentation effort → Partially resolved (see `docs/10-domain/dexcom-ble-protocol-deep-dive.md`)

**Related**:
- [xdrip-js BLE Protocol](../mapping/xdrip-js/ble-protocol.md)
- [DiaBLE Dexcom Support](../mapping/diable/cgm-transmitters.md)
- [Dexcom BLE Protocol Deep Dive](../docs/10-domain/dexcom-ble-protocol-deep-dive.md)

---

### GAP-BLE-001: G7 J-PAKE Full Specification Incomplete

**Scenario**: G7 Initial Pairing

**Description**: The J-PAKE (Password Authenticated Key Exchange by Juggling) protocol used by Dexcom G7 for initial pairing is not fully documented. The mathematical operations for key derivation are implemented in native libraries (keks, mbedtls) but the exact message formats and state machine are not fully understood.

**Source**: [Dexcom BLE Protocol Deep Dive](../docs/10-domain/dexcom-ble-protocol-deep-dive.md#g7-j-pake-authentication)

**Impact**:
- New G7 implementations must reverse-engineer or copy existing code
- Cannot verify correctness of implementations
- Security analysis is incomplete

**Possible Solutions**:
1. Detailed packet capture and analysis of J-PAKE phases
2. Reverse engineering of official Dexcom app
3. Collaboration with existing implementations (xDrip+, DiaBLE)

**Status**: Documentation effort

---

### GAP-BLE-002: G7 Certificate Chain Undocumented

**Scenario**: G7 Initial Pairing

**Description**: The certificate exchange (opcode 0x0B) and proof of possession (opcode 0x0C) protocols used after J-PAKE are not fully documented. These establish long-term trust between the sensor and device.

**Source**: [DiaBLE DexcomG7.swift](../externals/DiaBLE/DiaBLE Playground.swiftpm/DexcomG7.swift)

**Impact**:
- Cannot implement G7 pairing from specification alone
- Certificate validation logic is unclear
- Security implications not fully analyzed

**Possible Solutions**:
1. Packet capture of certificate exchange
2. Analysis of certificate formats (likely X.509)
3. Documentation of signature verification

**Status**: Needs investigation

---

### GAP-BLE-003: Service B Purpose Unknown

**Scenario**: BLE Protocol Completeness

**Description**: The secondary Bluetooth service (UUID: F8084532-849E-531C-C594-30F1F86A4EA5) with characteristics E (F8084533) and F (F8084534) is present on Dexcom transmitters but its purpose is unknown.

**Source**: [CGMBLEKit BluetoothServices.swift](../externals/LoopWorkspace/CGMBLEKit/CGMBLEKit/BluetoothServices.swift)

**Impact**:
- Potentially missing functionality
- May be used for firmware updates or diagnostics

**Possible Solutions**:
1. Packet capture during firmware updates
2. Reverse engineering of Dexcom app
3. Experimentation with characteristic reads/writes

**Status**: Low priority

---

### GAP-BLE-004: Anubis Transmitter Extended Commands

**Scenario**: G6 Extended Transmitters

**Description**: "Anubis" G6 transmitters (maxRuntimeDays > 120) use extended commands at opcodes 0x3B and 0xF0xx that are not fully documented. These appear related to transmitter reset/restart functionality.

**Source**: [xdrip-js transmitter.js](../externals/xdrip-js/lib/transmitter.js)

**Impact**:
- Cannot fully support Anubis transmitter features
- Reset/extend functionality limited

**Possible Solutions**:
1. Analysis of xDrip+ Android implementation
2. Documentation of 0xF080 message format

**Status**: Low priority

---

### GAP-BLE-005: G7 Encryption Info Format Unknown

**Scenario**: G7 Advanced Features

**Description**: The encryption info (opcode 0x38) and encryption status (opcode 0x0F) commands for G7 are present but the data format and purpose are unclear. May relate to encrypted data streams.

**Source**: [DiaBLE DexcomG7.swift](../externals/DiaBLE/DiaBLE Playground.swiftpm/DexcomG7.swift)

**Impact**:
- May be blocking access to additional data
- Security implications unknown

**Possible Solutions**:
1. Packet analysis of encryption commands
2. Cross-reference with official app behavior

**Status**: Needs investigation

---

## Carb Absorption Gaps

### GAP-CARB-001: Absorption Model Not Synced

**Scenario**: Cross-System COB Comparison

**Description**: No AID system syncs which carbohydrate absorption curve model is in use (Parabolic, Linear, PiecewiseLinear) to Nightscout. This information is only available locally on the device.

**Source**: [Carb Absorption Deep Dive](../docs/10-domain/carb-absorption-deep-dive.md)

**Impact**:
- Cannot accurately compare COB values between systems using different models
- Downstream analysis tools cannot reproduce COB calculations
- Research and audit use cases are blocked

**Possible Solutions**:
1. Add `absorptionModel` field to devicestatus COB object
2. Include in profile uploads
3. Document as metadata in carb treatment entries

**Status**: Under discussion

---

### GAP-CARB-002: Dynamic Absorption State Not Exported

**Scenario**: Cross-System Algorithm Analysis

**Description**: Loop's rich dynamic absorption tracking (`observedTimeline`, `AbsorbedCarbValue` with observed/clamped/remaining fields) is not synced to Nightscout. Only the final COB value appears in devicestatus.

**Source**: [Loop CarbStatus.swift](../externals/LoopWorkspace/LoopKit/LoopKit/CarbKit/CarbStatus.swift)

**Impact**:
- Cannot debug absorption discrepancies from Nightscout data
- Per-entry absorption progress is lost
- Cannot reconstruct how Loop adapted absorption rate

**Possible Solutions**:
1. Add `absorbedCarbs` array to devicestatus with per-entry breakdown
2. Create separate `carbAbsorption` collection for detailed tracking
3. Extend treatment with `observedAbsorption` field on update

**Status**: Under discussion

---

### GAP-CARB-003: eCarbs Not Supported by iOS Apps

**Scenario**: Cross-Platform Carb Entry

**Description**: AAPS supports extended carbs (eCarbs) via the `duration` field on Carbs entity, spreading absorption over time. Loop and Trio do not support this feature and treat all carbs as instant.

**Source**: 
- [AAPS Carbs.kt](../externals/AndroidAPS/database/impl/src/main/kotlin/app/aaps/database/entities/Carbs.kt)
- [Loop CarbEntry.swift](../externals/LoopWorkspace/LoopKit/LoopKit/CarbKit/CarbEntry.swift)

**Impact**:
- Carb entries created in AAPS with duration are misinterpreted by iOS apps
- Users switching between Android and iOS lose eCarb functionality
- Nightscout displays duration but importing systems may ignore it

**Possible Solutions**:
1. iOS apps add eCarbs support
2. Nightscout converts eCarbs to multiple smaller instant entries
3. Document as incompatibility for user awareness

**Status**: Needs ADR

---

### GAP-CARB-004: min_5m_carbimpact Variance

**Scenario**: COB Decay Rate Comparison

**Description**: The `min_5m_carbimpact` parameter in oref0/AAPS defaults to 3 mg/dL/5m for normal diets but 8 mg/dL/5m for low-carb diets. This significantly affects how quickly COB decays when no absorption is detected.

**Source**: [oref0 cob.js#L189-L194](../externals/oref0/lib/determine-basal/cob.js)

**Impact**:
- Same carb entry produces different COB timelines with different min_5m_carbimpact settings
- "Zombie carbs" (COB that never depletes) behavior differs
- Cross-user comparison invalid without knowing this setting

**Possible Solutions**:
1. Include `min_5m_carbimpact` in devicestatus
2. Standardize on a single default across configurations
3. Document as critical comparison caveat

**Status**: Under discussion

---

### GAP-CARB-005: COB Maximum Limits Differ

**Scenario**: Large Meal Handling

**Description**: oref0/AAPS enforce a hard `maxCOB` cap (default 120g), while Loop has no such limit. This means the same large meal (e.g., 150g carbs) produces different COB values.

**Source**: 
- [oref0 total.js#L108](../externals/oref0/lib/meal/total.js)
- Loop has no equivalent cap

**Impact**:
- Large carb entries produce different COB in different systems
- Safety implications for high-carb meals
- Users unaware of capping may be confused by COB discrepancies

**Possible Solutions**:
1. Loop adds configurable maxCOB option
2. oref0 makes maxCOB configurable with no-limit option
3. Document as known difference with safety implications

**Status**: Under discussion

---

## Libre CGM Protocol Gaps

### GAP-LIBRE-001: Libre 3 Cloud Decryption Dependency

**Scenario**: Libre 3 Direct Connection

**Description**: Libre 3 uses fully encrypted BLE communication with ECDH key exchange. Current open-source implementations (DiaBLE) can connect and receive encrypted data, but full decryption without cloud services is incomplete. Some functionality requires reverse-engineering closed-source libraries or relying on cloud-based OOP servers.

**Source**: `externals/DiaBLE/DiaBLE/Libre3.swift`

**Impact**:
- Libre 3 support is experimental/partial in open-source apps
- Users must rely on LibreLink app or patched solutions
- No offline-only Libre 3 reading capability

**Possible Solutions**:
1. Complete reverse-engineering of Libre 3 security protocol
2. Document cloud API for OOP decryption
3. Wait for community security research

**Status**: Under discussion

---

### GAP-LIBRE-002: Libre 2 Gen2 Session-Based Authentication

**Scenario**: Libre 2 Gen2 (US) NFC/BLE Access

**Description**: Libre 2 Gen2 sensors require session-based authentication that differs from EU Libre 2. The authentication involves challenge-response with proprietary key derivation functions that are only partially documented.

**Source**: `externals/DiaBLE/DiaBLE/Libre2Gen2.swift`

**Impact**:
- Gen2 support is limited on iOS (Loop, Trio)
- xDrip+ Android has better Gen2 support via native library
- Cross-platform parity is not achieved

**Possible Solutions**:
1. Port xDrip+ Gen2 implementation to Swift
2. Document session protocol completely
3. Use bridge transmitters (MiaoMiao, Bubble) for Gen2

**Status**: Under discussion

---

### GAP-LIBRE-003: Transmitter Bridge Firmware Variance

**Scenario**: MiaoMiao/Bubble Data Reliability

**Description**: Third-party transmitter bridges (MiaoMiao, Bubble, etc.) have varying firmware versions with different capabilities. Firmware differences affect:
- Libre 2 decryption support
- PatchInfo availability (older firmware may not include it)
- Battery reporting accuracy

**Source**: `externals/xdripswift/xdrip/BluetoothTransmitter/CGM/Libre/MiaoMiao/CGMMiaoMiaoTransmitter.swift`

**Impact**:
- Same transmitter may behave differently based on firmware
- Users may need firmware updates for Libre 2 support
- Documentation becomes version-dependent

**Possible Solutions**:
1. Document minimum firmware versions per feature
2. Implement firmware detection and user notification
3. Provide firmware update instructions in apps

**Status**: Documentation needed

---

### GAP-LIBRE-004: Calibration Algorithm Not Synced

**Scenario**: Cross-App Glucose Comparison

**Description**: The factory calibration parameters (i1-i6) extracted from FRAM are not synced to Nightscout. Different apps may use different OOP servers or local algorithms, producing slightly different glucose values from the same raw data.

**Source**: `externals/LoopWorkspace/LibreTransmitter/LibreSensor/SensorContents/SensorData.swift#calibrationData`

**Impact**:
- Same sensor reading may show different values in different apps
- No way to verify calibration consistency post-hoc
- Research/comparison compromised

**Possible Solutions**:
1. Add calibration info to Nightscout entries
2. Standardize on a single calibration algorithm
3. Document calibration source in devicestatus

**Status**: Under discussion

---

### GAP-LIBRE-005: Sensor Serial Number Not in Nightscout Entries

**Scenario**: Multi-Sensor Tracking

**Description**: Nightscout entries have `device` field but no dedicated sensor serial number field. The 10-character Libre serial (e.g., "3MH001ABCD") is not consistently captured, making it difficult to track readings across sensor changes.

**Impact**:
- Cannot query "all readings from sensor X"
- Sensor session boundaries unclear
- Harder to correlate sensor failures with readings

**Possible Solutions**:
1. Add `sensorSerial` field to entries
2. Use `device` field with consistent format
3. Track in separate sensor metadata collection

**Status**: Under discussion

---

### GAP-LIBRE-006: NFC vs BLE Data Latency Difference

**Scenario**: Real-Time Glucose Display

**Description**: Libre sensors update FRAM trend data every minute but history every 15 minutes. BLE streaming provides sparse trend (minutes 0, 2, 4, 6, 7, 12, 15) plus 3 history values, while NFC provides full 16 trend + 32 history. The data available via each method differs.

**Source**: `externals/DiaBLE/DiaBLE/Libre2.swift#parseBLEData`

**Impact**:
- NFC scans may fill gaps BLE misses
- Hybrid NFC+BLE strategies needed for complete data
- Backfill logic required

**Possible Solutions**:
1. Document exact data availability per method
2. Implement smart gap-filling in apps
3. Prefer NFC for historical data, BLE for real-time

**Status**: Documented

---

## Batch Operation Gaps

### GAP-BATCH-001: Batch Deduplication Not Enforced at Database Level

**Scenario**: High-throughput batch uploads

**Description**: The `id` field used by Trio and other clients for deduplication is NOT enforced as unique by MongoDB. Nightscout relies on application-level deduplication queries (checking if id exists before insert), not database-level unique constraints. This means duplicate `id` values CAN be inserted if sent in a batch, because batch inserts don't perform per-document deduplication checks.

**Source**: `cgm-remote-monitor:tests/api.partial-failures.test.js:62-107`
```javascript
// QUIRK/BEHAVIOR: The 'id' field is used by clients (Trio, etc.) for deduplication
// but is NOT enforced as unique by MongoDB unless explicitly indexed.
// This means duplicate 'id' values CAN be inserted if sent in a batch,
// because the batch insert doesn't perform per-document deduplication checks.
```

**Impact**:
- Batch operations can create duplicate documents with same `id`
- Network retries during batch uploads may create duplicates
- Trio throttled pipelines may insert duplicates under high load
- Data integrity depends on client-side dedup, not server enforcement

**Possible Solutions**:
1. Add unique index on `id` field (breaking change for existing data)
2. Implement per-document deduplication in batch insert handler
3. Document behavior and recommend client-side deduplication
4. Use `identifier` field with v3 API for server-enforced uniqueness

**Status**: Under discussion

---

### GAP-BATCH-002: Response Order Critical for Loop syncIdentifier Mapping

**Scenario**: Loop batch treatment uploads

**Description**: Loop caches syncIdentifier→objectId mappings based on response array order. If the response order doesn't match the request order, Loop maps wrong IDs which breaks update and delete operations.

**Source**: `cgm-remote-monitor:tests/api.partial-failures.test.js:138-182`
```javascript
// SPEC: Loop caches syncIdentifier→objectId mapping based on response array order
// CRITICAL: If order doesn't match, Loop maps wrong IDs and breaks update/delete
```

**Impact**:
- Wrong ID mappings cause silent data corruption
- Updates may modify wrong documents
- Deletes may remove wrong documents
- Hard to debug because no immediate error

**Possible Solutions**:
1. Server guarantees response order matches request order (current behavior, needs testing)
2. Loop should match by syncIdentifier in response, not by position
3. Server includes syncIdentifier in response for verification
4. Add test coverage to prevent regression

**Status**: Under discussion

**Related**:
- GAP-TREAT-005 (Loop POST duplicates)
- REQ-045 (Sync identity round-trip)

---

### GAP-BATCH-003: Deduplicated Items Must Return All Positions

**Scenario**: Batch upload with some duplicates

**Description**: Loop expects N responses for N requests, even if some items are deduplicated. Missing positions in the response array break the syncIdentifier cache, causing subsequent operations to fail.

**Source**: `cgm-remote-monitor:tests/api.partial-failures.test.js:186-212`
```javascript
// SPEC: Loop expects N responses for N requests, even if some are deduplicated
// CRITICAL: Missing positions in response breaks syncIdentifier cache
```

**Impact**:
- If server returns fewer items than submitted, Loop cache is corrupted
- Subsequent updates/deletes fail silently or target wrong documents
- Deduplicated items must still appear in response with their existing `_id`

**Possible Solutions**:
1. Server always returns N items for N-item batch (current expected behavior)
2. Deduplicated items return existing document's `_id`
3. Document expected response format in API specification
4. Add conformance tests

**Status**: Under discussion

---

## Prediction Data Gaps

### GAP-PRED-001: Prediction Array Truncation Behavior Undocumented

**Scenario**: OpenAPS/AAPS devicestatus uploads with large prediction arrays

**Description**: Nightscout may truncate prediction arrays based on `PREDICTIONS_MAX_SIZE` environment variable. This behavior is server-configurable and varies between installations. Clients have no way to know if their predictions were truncated.

**Source**: `cgm-remote-monitor:tests/api.partial-failures.test.js:402-550`
```javascript
// SPEC: When PREDICTIONS_MAX_SIZE env var is set, prediction arrays
// are truncated to that size
// SPEC: Setting PREDICTIONS_MAX_SIZE=0 explicitly disables truncation
```

**Impact**:
- Algorithm debugging may be impossible if predictions are truncated
- Different Nightscout installations behave differently
- No indication to clients that data was truncated
- Research and audit use cases affected

**Possible Solutions**:
1. Document `PREDICTIONS_MAX_SIZE` behavior in API spec
2. Add response header indicating truncation occurred
3. Standardize default behavior across installations
4. Add `truncated: true` flag to devicestatus when applicable

**Status**: Under discussion

**Related**:
- GAP-SYNC-002 (Effect timelines not uploaded)

---

## Timezone and DST Gaps

### GAP-TZ-001: Most Pump Drivers Cannot Handle DST

**Scenario**: DST transitions with active AID therapy

**Description**: Most AAPS pump drivers return `canHandleDST(): Boolean = false`, including Medtronic, Dana-R, Omnipod DASH, and Omnipod Eros. During DST transitions, these pumps cannot automatically adjust their internal clocks, leading to potential timing mismatches.

**Source**:
- `AndroidAPS/pump/medtronic/...MedtronicPumpPlugin.kt:259` - `canHandleDST(): Boolean = false`
- `AndroidAPS/pump/omnipod/dash/...OmnipodDashPumpPlugin.kt:987` - `canHandleDST(): Boolean = false`
- `AndroidAPS/pump/omnipod/eros/...OmnipodErosPumpPlugin.kt:769` - `canHandleDST(): Boolean = false`
- `AndroidAPS/pump/danar/...AbstractDanaRPlugin.kt:361` - `canHandleDST(): Boolean = false`

**Impact**:
- Basal schedules may be off by 1 hour during DST transitions
- IOB calculations may be affected by timestamp mismatches
- User intervention required to adjust pump time
- Potential for dosing errors during transition period

**Possible Solutions**:
1. Document DST handling limitations per pump
2. Alert users before DST transitions
3. Implement manual DST adjustment workflow
4. Note: Medtrum pump supports DST (`canHandleDST(): Boolean = true`)

**Status**: Documented (inherent hardware/firmware limitation)

---

### GAP-TZ-002: Medtrum Timezone GMT+12 Bug

**Scenario**: Users in Pacific timezones (Fiji, New Zealand)

**Description**: Medtrum pump driver has a workaround for a bug where timezone settings fail for GMT > +12. This affects users in Pacific timezones.

**Source**: `AndroidAPS/pump/medtrum/...SetTimeZonePacket.kt:29`
```kotlin
// Workaround for bug where it fails to set timezone > GMT + 12
```

**Impact**:
- Users in affected timezones may have incorrect pump time
- Basal schedules may be misaligned with local time
- Workaround behavior is undocumented

**Possible Solutions**:
1. Document affected timezones
2. Implement proper timezone mapping for high-offset zones
3. Add user notification for affected timezones

**Status**: Under discussion

---

### GAP-TZ-003: utcOffset Recalculation on Upload

**Scenario**: Cross-timezone sync

**Description**: Nightscout recalculates `utcOffset` from the `dateString`'s timezone, rather than preserving the client-provided value. This can lead to unexpected behavior when uploading data from a device in a different timezone than the dateString indicates.

**Source**: `cgm-remote-monitor:tests/api.aaps-client.test.js:337`
```javascript
// QUIRK/FEATURE: Nightscout recalculates utcOffset from the dateString's timezone
```

**Impact**:
- Client-provided utcOffset may be overwritten
- Timezone handling differs between API v1 and v3
- Historical data analysis may be affected

**Possible Solutions**:
1. Document utcOffset handling behavior
2. Preserve client-provided utcOffset when valid
3. Add configuration option for behavior

**Status**: Under discussion

---

### GAP-TZ-004: utcOffset Unit Mismatch Between Nightscout and AAPS

**Scenario**: Cross-system sync between AAPS and Nightscout

**Description**: Nightscout stores and expects `utcOffset` in **minutes** (e.g., `-480` for UTC-8), while AAPS stores `utcOffset` internally in **milliseconds** (e.g., `-28800000` for UTC-8). This unit mismatch requires careful conversion during sync.

**Source**:
- Nightscout: `cgm-remote-monitor:lib/api3/generic/collection.js:182` - `doc.utcOffset = m.utcOffset()` (moment returns minutes)
- AAPS SDK: `core/nssdk/remotemodel/RemoteTreatment.kt:23` - `utcOffset: Long?` (documented as "minutes" in comments)
- AAPS DB: `database/entities/interfaces/DBEntryWithTime.kt:6` - `var utcOffset: Long` (milliseconds internally)

**Impact**:
- Potential off-by-factor-of-60000 if units confused
- AAPS SDK correctly handles conversion, but custom clients may not
- Documentation unclear about which unit applies where

**Possible Solutions**:
1. Document unit expectations clearly in API specs
2. Add validation for reasonable offset ranges
3. Standardize on one unit (minutes) across all systems

**Status**: Documented

---

### GAP-TZ-005: AAPS Fixed Offset Storage Breaks Historical DST Analysis

**Scenario**: Analyzing historical data that spans DST transitions

**Description**: AAPS captures `utcOffset` at event creation time using `TimeZone.getDefault().getOffset(timestamp)`. This captures the offset **at that moment** including DST, but the offset is fixed and won't update when viewing historical data. This means reconstructing local time from historical events may be incorrect if DST status has changed.

**Source**: `AndroidAPS/database/entities/Bolus.kt:43`
```kotlin
override var utcOffset: Long = TimeZone.getDefault().getOffset(timestamp).toLong(),
```

**Impact**:
- Historical reports may show incorrect local times for events near DST transitions
- Cannot retroactively determine if DST was in effect for old events
- Schedule alignment analysis across DST boundaries is unreliable
- Exported data may have misleading timezone information

**Possible Solutions**:
1. Store IANA timezone identifier alongside offset
2. Use offset calculated for the event's timestamp, not current time (already done for most events)
3. Document limitation in data export documentation

**Status**: Documented (architectural limitation)

---

### GAP-TZ-006: Loop Uploads Non-Standard Timezone Format

**Scenario**: Loop profile sync to Nightscout

**Description**: Loop uploads timezone strings with non-standard casing (`ETC/GMT+8` instead of `Etc/GMT+8`). Nightscout has a workaround but it's incomplete (uses `replace` instead of case-insensitive matching).

**Source**: `cgm-remote-monitor:lib/profilefunctions.js:179-181`
```javascript
// Work around Loop uploading non-ISO compliant time zone string
if (rVal) rVal.replace('ETC','Etc');
```

**Note**: This code has a bug - it calls `replace` but doesn't assign the result.

**Impact**:
- Timezone lookup may fail with uppercase prefix
- Profile time calculations may use fallback behavior
- Inconsistent behavior between Loop and other clients

**Possible Solutions**:
1. Fix Loop to use standard IANA format (`Etc/GMT+8`)
2. Fix Nightscout to use `rVal = rVal.replace('ETC','Etc')` (assign result)
3. Use case-insensitive timezone lookup

**Status**: Bug identified

---

### GAP-TZ-007: Missing Timezone Fallback Uses Server Local Time

**Scenario**: Profile uploaded without timezone field

**Description**: When a profile is uploaded without a `timezone` field, Nightscout falls back to the server's local timezone. This can cause schedule misalignment when the server is in a different timezone than the user.

**Source**: `cgm-remote-monitor:lib/profilefunctions.js:107-110`
```javascript
// Use local time zone if profile doesn't contain a time zone
// This WILL break on the server; added warnings elsewhere that this is missing
// TODO: Better warnings to user for missing configuration
```

**Impact**:
- Basal rates may be applied at wrong times
- ISF/CR lookups return incorrect values for time of day
- User may not realize timezone is missing

**Possible Solutions**:
1. Require timezone in profile validation
2. Default to UTC instead of server local
3. Add prominent UI warning when timezone missing

**Status**: Under discussion

---

## Error Handling Gaps

### GAP-ERR-001: Empty Array Creates Empty Treatment

**Scenario**: Edge case - empty batch upload

**Description**: Sending an empty array `[]` to the treatments API does not return an error. Instead, current behavior creates an empty treatment with auto-generated `created_at`. This is surprising behavior that may mask client-side bugs.

**Source**: `cgm-remote-monitor:tests/api.v1-batch-operations.test.js:163-164`
```javascript
// SPEC: Edge case - empty array should not error (Section 4.6)
// NOTE: Current behavior creates empty treatment with auto-generated created_at
```

**Impact**:
- May create phantom treatments
- Client bugs may go undetected
- Data pollution with empty records

**Possible Solutions**:
1. Return HTTP 400 for empty array
2. Return HTTP 200 with empty array response
3. Document current behavior
4. Add validation to reject truly empty items

**Status**: Under discussion

---

### GAP-ERR-002: CRC Mismatch Ignored in Medtronic History

**Scenario**: Medtronic pump history download

**Description**: Medtronic history pages with CRC mismatches are logged as warnings but the data is processed anyway. This could lead to corrupted data being used for IOB calculations.

**Source**: `AndroidAPS/pump/medtronic/...RawHistoryPage.kt:39`
```kotlin
Locale.ENGLISH, "Stored CRC (%d) is different than calculated (%d), but ignored for now.", crcStored,
```

**Impact**:
- Corrupted pump history may be used
- IOB calculations may be incorrect
- Silent data corruption possible

**Possible Solutions**:
1. Retry history download on CRC mismatch
2. Alert user to potential data corruption
3. Exclude entries with CRC mismatch from calculations
4. Log as error instead of warning

**Status**: Under discussion

---

### GAP-ERR-003: Unknown Pump History Entries Silently Ignored

**Scenario**: New pump firmware with new entry types

**Description**: Medtronic pump history decoder silently ignores unknown entry types. Several entry types are marked with `/* TODO */` and have unknown purposes. New firmware versions may introduce entry types that are completely ignored.

**Source**: `AndroidAPS/pump/medtronic/...PumpHistoryEntryType.kt:13-17`
```kotlin
/* TODO */ EventUnknown_MM512_0x2e(0x2e, "Unknown Event 0x2e", PumpHistoryEntryGroup.Unknown, 2, 5, 100),
/* TODO */ ConfirmInsulinChange(0x3a, "Confirm Insulin Change", PumpHistoryEntryGroup.Unknown),
/* TODO */ Sensor_0x51(0x51, "Unknown Event 0x51", PumpHistoryEntryGroup.Unknown),
/* TODO */ Sensor_0x52(0x52, "Unknown Event 0x52", PumpHistoryEntryGroup.Unknown),
```

**Impact**:
- Undiscovered boluses or temp basals may be missed
- IOB calculations may be incomplete
- No visibility into unknown events

**Possible Solutions**:
1. Log unknown entries with full data for analysis
2. Surface unknown entries to user for reporting
3. Community effort to document unknown entry types
4. Add mechanism to report unknown entries

**Status**: Under discussion

---

## Specification Gaps

### GAP-SPEC-001: Remote Command eventTypes Missing from OpenAPI Spec

**Scenario**: Remote command processing

**Description**: The Nightscout server recognizes special remote command eventTypes that are not listed in the OpenAPI spec's eventType enum:
- `Temporary Override Cancel` - cancels active override
- `Remote Carbs Entry` - adds carbs remotely
- `Remote Bolus Entry` - requests bolus remotely

These are used exclusively for Loop remote commands via APNS but are undocumented in the API specification.

**Source**: `cgm-remote-monitor:lib/server/loop.js:65-106`

**Impact**:
- Clients cannot discover valid remote command eventTypes from spec
- No validation rules documented for remote command fields
- Missing required fields documentation (remoteCarbs, remoteBolus, etc.)

**Possible Solutions**:
1. Add remote command eventTypes to treatments spec with required field documentation
2. Create separate remote commands API specification
3. Document as extension to base treatments schema

**Status**: Under discussion

**Related**:
- GAP-REMOTE-001, GAP-REMOTE-002
- [Remote Commands Comparison](../docs/10-domain/remote-commands-comparison.md)

---

### GAP-SPEC-002: AAPS Treatment Fields Not in AID Spec

**Scenario**: AAPS treatment sync round-trip

**Description**: The AAPS SDK `RemoteTreatment` model includes many fields not documented in the AID treatments OpenAPI spec:

**Missing fields**:
| Field | Type | Purpose |
|-------|------|---------|
| `durationInMilliseconds` | Long | Alternative duration representation |
| `endId` | Long | ID of record that ended this treatment |
| `autoForced` | Boolean | RunningMode auto-forced flag |
| `mode` | String | RunningMode type |
| `reasons` | String | RunningMode reasons |
| `location` | String | Site management location |
| `arrow` | String | Site management arrow indicator |
| `isSMB` | Boolean | Explicit SMB identifier |
| `relative` | Double | Relative rate for extended bolus |
| `isEmulatingTempBasal` | Boolean | Extended bolus emulation flag |
| `extendedEmulated` | Object | Nested treatment for emulated extended bolus |
| `bolusCalculatorResult` | String | Full bolus wizard calculation JSON |
| `originalProfileName` | String | Effective Profile Switch original |
| `originalCustomizedName` | String | Effective Profile Switch customization |
| `originalTimeshift` | Long | Original profile timeshift |
| `originalPercentage` | Int | Original profile percentage |
| `originalDuration` | Long | Original duration before modification |
| `originalEnd` | Long | Original end timestamp |
| `enteredinsulin` | Double | Alternative insulin field for combo bolus |

**Source**: `AndroidAPS:core/nssdk/src/main/kotlin/.../RemoteTreatment.kt:41-87`

**Impact**:
- Spec consumers miss fields needed for AAPS compatibility
- Round-trip data loss for AAPS-originated treatments
- Incomplete validation rules

**Possible Solutions**:
1. Add all AAPS fields to aid-treatments-2025.yaml with x-aid-controllers annotations
2. Create AAPS-specific extension schema
3. Document as "implementation-specific" extensions

**Status**: Under discussion

**Related**:
- GAP-TREAT-003, GAP-TREAT-004
- [Treatments Deep Dive](../docs/10-domain/treatments-deep-dive.md)

---

### GAP-SPEC-003: Effective Profile Switch vs Profile Switch Distinction

**Scenario**: Profile tracking across systems

**Description**: AAPS uploads both `Profile Switch` and `Effective Profile Switch` eventTypes. The latter includes `original*` prefixed fields tracking what changed from the base profile. This distinction is not captured in the spec.

**Source**: `AndroidAPS:core/nssdk/src/main/kotlin/.../RemoteTreatment.kt:69-74`

**Evidence**:
```kotlin
@SerializedName("originalProfileName") val originalProfileName: String? = null,
@SerializedName("originalCustomizedName") val originalCustomizedName: String? = null,
@SerializedName("originalTimeshift") val originalTimeshift: Long? = null,
@SerializedName("originalPercentage") val originalPercentage: Int? = null,
@SerializedName("originalDuration") val originalDuration: Long? = null,
@SerializedName("originalEnd") val originalEnd: Long? = null,
```

**Impact**:
- Cannot distinguish calculated effective profile from user-initiated switch
- Profile history reconstruction incomplete
- Algorithm comparison missing profile context

**Possible Solutions**:
1. Add `Effective Profile Switch` to eventType enum
2. Document `original*` fields in Profile Switch schema
3. Create ProfileSwitchTreatment discriminated union

**Status**: Needs ADR

---

### GAP-SPEC-004: BolusCalculatorResult JSON Not Parsed

**Scenario**: Bolus wizard audit trail

**Description**: AAPS uploads `bolusCalculatorResult` as a JSON string containing detailed bolus calculation parameters. This is documented as a string field but the internal structure is not specified.

**Source**: `AndroidAPS:core/nssdk/src/main/kotlin/.../RemoteTreatment.kt:76`

**Sample structure**:
```json
{
  "basalIOB": -0.247,
  "bolusIOB": -1.837,
  "carbs": 45.0,
  "carbsInsulin": 9.0,
  "glucoseValue": 134.0,
  "glucoseInsulin": 0.897,
  "glucoseDifference": 44.0,
  "ic": 5.0,
  "isf": 49.0,
  "targetBGLow": 90.0,
  "targetBGHigh": 90.0,
  "totalInsulin": 7.34,
  "percentageCorrection": 90,
  "profileName": "Tuned 13/01 90%Lyum",
  ...
}
```

**Impact**:
- Bolus audit trail requires parsing embedded JSON
- No schema validation for calculator parameters
- Cannot query by calculator inputs

**Possible Solutions**:
1. Define BolusCalculatorResult as object schema in spec
2. Recommend storing as structured object instead of string
3. Document required fields for bolus wizard auditing

**Status**: Under discussion

---

### GAP-SPEC-005: FAKE_EXTENDED Temp Basal Type Undocumented

**Scenario**: Extended bolus handling

**Description**: AAPS uses `type: "FAKE_EXTENDED"` for extended boluses implemented as temp basals. This is not documented in the treatments spec.

**Source**: `AndroidAPS:core/nssdk/src/main/kotlin/.../RemoteTreatment.kt:77`
```kotlin
@SerializedName("type") val type: String? = null,  // "NORMAL", "SMB", "FAKE_EXTENDED"
```

**Impact**:
- Extended bolus treatments not identified correctly
- IOB calculation may double-count if both bolus and temp basal components exist
- Related to GAP-TREAT-004 (extended bolus representation)

**Possible Solutions**:
1. Add FAKE_EXTENDED to BolusType enum with documentation
2. Add isExtendedBolus boolean flag
3. Document relationship between extended bolus and temp basal treatments

**Status**: Under discussion

**Related**:
- GAP-TREAT-004

---

### GAP-SPEC-006: isValid Soft Delete Semantics Not Specified

**Scenario**: Treatment deletion sync

**Description**: API v3 uses `isValid: false` for soft-deleted documents, but the spec doesn't define:
- When isValid should be set to false
- Whether clients should filter by isValid
- Behavior when isValid is missing (null vs true)

**Source**: `AndroidAPS:core/nssdk/src/main/kotlin/.../RemoteTreatment.kt:30`
```kotlin
@SerializedName("isValid") val isValid: Boolean? = null,
```

**Impact**:
- Clients may display deleted treatments
- Sync logic varies by implementation
- Related to GAP-TREAT-006 (retroactive edit handling)

**Possible Solutions**:
1. Document isValid semantics in spec
2. Add isValid query filter documentation
3. Specify default value when field is missing

**Status**: Under discussion

**Related**:
- GAP-TREAT-006, GAP-API-001

---

### GAP-SPEC-007: Deduplication Key Fields Undocumented

**Scenario**: Batch upload deduplication

**Description**: The Nightscout API uses `created_at` + `eventType` as the deduplication key for treatments, but this is not explicitly documented in the OpenAPI spec. Additionally, the spec doesn't document:
- `identifier` field behavior for API v3
- `date` + `device` + `eventType` alternative key
- Priority when multiple identity fields are present

**Source**: `cgm-remote-monitor:lib/api3/swagger.yaml:1103`
```yaml
The server calculates the identifier in such a way that duplicate records are automatically merged 
(deduplicating is made by `date`, `device` and `eventType` fields).
```

**Impact**:
- Clients may not include required deduplication fields
- Duplicate detection varies between v1 and v3 APIs
- Related to GAP-003, GAP-BATCH-001

**Possible Solutions**:
1. Document deduplication algorithm per API version
2. Add x-deduplication-key extension to spec
3. Specify which fields form the composite key

**Status**: Under discussion

**Related**:
- GAP-003, GAP-BATCH-001, GAP-BATCH-002

---

## Resolved Gaps

_None yet._

---

## Template

```markdown
### GAP-XXX: [Brief title]

**Scenario**: [Link to scenario]

**Description**: [What's missing or ambiguous]

**Impact**: 
- [How this blocks progress]

**Possible Solutions**:
1. [Option A]
2. [Option B]

**Status**: [Under discussion | Needs ADR | Resolved | Won't fix]

**Related**: [Links to ADRs, issues, etc.]
```

---

## Remote Caregiver Gaps

### GAP-REMOTE-005: remoteAddress Field Purpose Unclear

**Scenario**: Override Remote Commands

**Description**: LoopCaregiver's `OverrideAction` and `OverrideCancelAction` include a `remoteAddress` field that is always set to empty string. The purpose of this field is undocumented in the codebase. It may be intended for APNS device tokens or notification routing, but this is speculation.

**Source**: `loopcaregiver:NightscoutDataSource.swift#L160-L162`
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

### GAP-REMOTE-006: No Command Retry Mechanism

**Scenario**: Remote Command Reliability

**Description**: LoopCaregiver has no built-in retry mechanism for failed command deliveries. If a command upload fails (network error, server error), the user must manually retry. There's also no indication if a command was partially delivered.

**Source**: `loopcaregiver:NightscoutDataSource.swift` - No retry logic present

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

### GAP-REMOTE-007: OTP Secret Stored in App Data, Not Keychain

**Scenario**: Credential Security

**Description**: LoopCaregiver stores the full `otpURL` (including the Base32 secret) in the `NightscoutCredentials` struct, which is likely persisted to app data rather than the Keychain. This differs from Loop which stores OTP secrets in the Keychain.

**Source**: `loopcaregiver:DeepLinkParser.swift#L164` - `otpURL` stored in credentials

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

### GAP-LF-001: Alarm Configuration Not Synced

**Scenario**: Multi-Caregiver Coordination

**Description**: LoopFollow alarm configurations are stored locally only. There is no mechanism to sync alarm settings to Nightscout or between caregiver devices. Each LoopFollow instance must be configured independently.

**Source**: `loopfollow:LoopFollow/Alarm/Alarm.swift` - Stored via `Storage.shared.alarms`

**Impact**:
- Duplicate configuration effort for multiple caregivers
- No centralized alarm management
- Alarm settings lost if device is reset

**Possible Solutions**:
1. Store alarm configuration in Nightscout profile store
2. Implement iCloud sync for alarm settings
3. Export/import configuration as JSON

**Status**: Under discussion

---

### GAP-LF-002: No Alarm History or Audit Log

**Scenario**: Alarm Effectiveness Review

**Description**: LoopFollow does not maintain a history of triggered alarms. Once an alarm is snoozed or cleared, there is no record of when it fired, what triggered it, or how it was resolved.

**Source**: `loopfollow:LoopFollow/Alarm/AlarmManager.swift` - No history persistence

**Impact**:
- Cannot analyze alarm patterns over time
- No audit trail for missed alarms
- Cannot tune alarm thresholds based on historical data

**Possible Solutions**:
1. Log alarm events to Nightscout treatments collection
2. Maintain local SQLite database of alarm history
3. Upload alarm events as announcements

**Status**: Under discussion

---

### GAP-LF-003: Prediction Data Unavailable for Trio

**Scenario**: Predictive Low Glucose Alarm

**Description**: LoopFollow's predictive low alarm relies on prediction data from deviceStatus. While Loop includes `predBgs` in deviceStatus, Trio may not include this data consistently, limiting predictive alarm effectiveness.

**Source**: `loopfollow:LoopFollow/Alarm/AlarmCondition/LowBGCondition.swift#L36-L51`

**Impact**:
- Predictive alarms only work reliably with Loop
- Trio users get delayed low alerts (reactive only)
- Feature parity gap between Loop and Trio monitoring

**Possible Solutions**:
1. Verify Trio prediction data availability
2. Document which alarms work with which AID systems
3. Implement client-side prediction from recent BG data

**Status**: Under discussion

---

### GAP-LF-004: No Multi-Caregiver Alarm Acknowledgment

**Scenario**: Caregiver Team Coordination

**Description**: When multiple caregivers use LoopFollow to monitor the same looper, there is no coordination for alarm acknowledgment. Each caregiver sees independent alarms, and snoozing on one device doesn't affect others.

**Source**: `loopfollow:LoopFollow/Alarm/AlarmManager.swift#L155-L169` - Local snooze only

**Impact**:
- Multiple caregivers may respond to same alarm
- No visibility into who acknowledged an alarm
- Risk of alarm fatigue from duplicate notifications

**Possible Solutions**:
1. Sync alarm acknowledgment via Nightscout
2. Implement shared snooze state
3. Use Nightscout announcements for alarm coordination

**Status**: Under discussion

---

### GAP-LF-005: No Command Status Tracking

**Scenario**: Remote Command Reliability

**Description**: LoopFollow remote commands (TRC, Loop APNS, Nightscout) are fire-and-forget. After sending a command, there is no mechanism to verify it was received or executed. Users must check the looper's app or Nightscout to confirm.

**Source**: 
- `loopfollow:LoopFollow/Remote/TRC/PushNotificationManager.swift` - Completion only indicates APNS delivery
- `loopfollow:LoopFollow/Remote/Nightscout/TrioNightscoutRemoteView.swift` - No status polling

**Impact**:
- Users may not know if command succeeded
- No retry mechanism for failed commands
- Commands may be sent multiple times if user is uncertain

**Possible Solutions**:
1. Implement TRC return notification fully
2. Poll Nightscout for command status (like LoopCaregiver Remote 2.0)
3. Show pending command status in UI

**Status**: Under discussion

---

### GAP-LF-006: No Command History or Audit Log

**Scenario**: Remote Command Audit

**Description**: LoopFollow does not maintain a history of commands sent. There is no log of when commands were sent, what parameters were used, or whether they succeeded.

**Source**: No command history persistence in codebase

**Impact**:
- Cannot audit who sent what command when
- No visibility for reviewing past remote actions
- Cannot diagnose command failures retroactively

**Possible Solutions**:
1. Maintain local command history database
2. Log commands to Nightscout
3. Display recent commands in UI

**Status**: Under discussion

---

### GAP-LF-007: TRC Return Notification Not Fully Implemented

**Scenario**: Command Confirmation

**Description**: TRC `CommandPayload` includes a `ReturnNotificationInfo` structure for Trio to send confirmation back to LoopFollow, but this feature does not appear to be fully implemented. The return notification fields are sent but there is no handler for incoming confirmations.

**Source**: 
- `loopfollow:LoopFollow/Remote/TRC/PushMessage.swift#L32-L48` - ReturnNotificationInfo defined
- No corresponding notification receiver implementation found

**Impact**:
- Users cannot get push confirmation of command execution
- Return notification infrastructure is unused
- Partial implementation may confuse future developers

**Possible Solutions**:
1. Implement return notification handler
2. Remove unused ReturnNotificationInfo structure
3. Document feature as planned but unimplemented

**Status**: Under discussion

---

### GAP-LF-008: Nightscout Remote Lacks OTP Security

**Scenario**: Temp Target Security

**Description**: LoopFollow's Nightscout-based temp target commands rely solely on API token authentication. Unlike Loop APNS (TOTP) or TRC (encryption), there is no additional security layer.

**Source**: `loopfollow:LoopFollow/Remote/Nightscout/TrioNightscoutRemoteView.swift#L48-L52`

**Impact**:
- Anyone with the API token can send temp targets
- No time-based protection against replay
- Inconsistent security model across remote types

**Possible Solutions**:
1. Add OTP support for Nightscout commands
2. Document security limitations
3. Recommend TRC for secure remote control

**Status**: Under discussion

---

### GAP-LF-009: No Unified Command Abstraction

**Scenario**: Multi-Protocol Remote Control

**Description**: LoopFollow implements three distinct remote protocols (Loop APNS, TRC, Nightscout) with separate codepaths, data structures, and UIs. There is no unified abstraction for sending commands.

**Source**: 
- `loopfollow:LoopFollow/Remote/RemoteViewController.swift#L33-L60` - Branched view logic
- Separate command implementations per protocol

**Impact**:
- Difficulty adding new commands requires changes in multiple places
- Inconsistent feature support across protocols
- Code duplication for similar functionality

**Possible Solutions**:
1. Create protocol-agnostic command abstraction
2. Implement command factory pattern
3. Unify UI with backend protocol selection

**Status**: Under discussion

---

## Delegation and Agent Gaps

> **See Also**: [Progressive Enhancement Framework](../docs/10-domain/progressive-enhancement-framework.md) for L7-L9 layer definitions.
> **See Also**: [Capability Layer Matrix](../mapping/cross-project/capability-layer-matrix.md) for system-by-system analysis.

### GAP-DELEGATE-001: No Standardized Authorization Scoping

**Scenario**: Remote Control Delegation (L8)

**Description**: Current remote control implementations provide all-or-nothing authorization. A caregiver either has full remote control access or none. There is no mechanism to scope permissions to specific command types (e.g., "can send temp targets but not boluses").

**Affected Systems**: Loop, AAPS, Trio, LoopCaregiver, LoopFollow

**Source**: 
- Loop: Single OTP secret grants all command permissions
- AAPS: Phone whitelist is binary (all or nothing)
- Trio: Single shared secret for all commands

**Impact**:
- Cannot implement "observer" role (view-only)
- Cannot implement "coach" role (suggestions only)
- Cannot implement "nurse" role (limited commands)
- Inappropriate for clinical care team integration

**Possible Solutions**:
1. Implement permission bitmask in authorization
2. Create role-based access control (RBAC) layer
3. Use JWT claims for scoped permissions
4. Define standard permission vocabulary

**Status**: Under discussion

---

### GAP-DELEGATE-002: No Role-Based Permission Model

**Scenario**: Care Team Coordination (L8)

**Description**: No AID system implements role-based permissions for remote control. All authorized parties have equivalent access regardless of their relationship (parent, partner, clinician, coach).

**Affected Systems**: All

**Source**: 
- No role field in command authentication
- No permission differentiation by user identity
- No concept of permission hierarchy

**Impact**:
- Cannot distinguish parent vs babysitter permissions
- Cannot limit clinician access to view-only
- Cannot implement "least privilege" security principle
- Risk of unauthorized actions by over-privileged users

**Possible Solutions**:
1. Define standard role vocabulary (primary, caregiver, clinician, observer, agent)
2. Map roles to permission sets
3. Store role in Nightscout token or authorization
4. Implement in gateway layer (NRG)

**Status**: Under discussion

**Related**:
- [GAP-AUTH-002](#gap-auth-002-no-authority-hierarchy-in-nightscout)
- [Controller Registration Protocol Proposal](../docs/60-research/controller-registration-protocol-proposal.md)

---

### GAP-DELEGATE-003: No Structured Out-of-Band Signal API

**Scenario**: Agent Context Integration (L9)

**Description**: There is no standardized API for integrating out-of-band signals (exercise, menstrual cycle, sleep, stress) into AID decision-making. Each potential signal source would require custom integration.

**Affected Systems**: All

**Source**: 
- No exercise detection integration in any open-source AID
- No hormone cycle awareness
- No wearable data integration (HR, HRV, steps) beyond CGM
- Manual overrides are the only mechanism

**Impact**:
- Agents cannot propose contextually-aware recommendations
- Users must manually detect and respond to patterns
- No path to reduced burden through automation
- Cannot leverage growing wearable ecosystem

**Possible Solutions**:
1. Define standard "context event" format for Nightscout
2. Create observer APIs for external signal sources
3. Implement signal-to-recommendation mapping framework
4. Start with exercise detection pilot (highest impact)

**Status**: Under discussion

---

### GAP-DELEGATE-004: No Agent Authorization Framework

**Scenario**: Autonomous Agent Operation (L9)

**Description**: There is no framework for authorizing software agents to act on behalf of users. Current systems assume human operators for all commands.

**Affected Systems**: All

**Source**: 
- `enteredBy` field is unverified string
- No concept of "agent" vs "human" command source
- No scoping for agent autonomy bounds
- No revocation mechanism for agent permissions

**Impact**:
- Cannot safely deploy autonomous agents
- Cannot audit human vs machine decisions
- Cannot implement "human in the loop" for agent actions
- Cannot limit agent actions to safe bounds

**Possible Solutions**:
1. Define `actorType` field (human, agent, controller)
2. Implement agent registration and authorization
3. Create audit trail for agent actions
4. Define bounded autonomy specifications

**Status**: Under discussion

**Related**:
- [GAP-AUTH-001](#gap-auth-001-enteredby-field-is-unverified)
- [GAP-AUTH-002](#gap-auth-002-no-authority-hierarchy-in-nightscout)

---

### GAP-DELEGATE-005: No Propose-Authorize-Enact Pattern

**Scenario**: Safe Agent Interaction (L9)

**Description**: Current remote command patterns assume immediate execution. There is no standardized workflow for agents to propose actions, await human authorization, and then enact approved actions.

**Affected Systems**: All

**Source**: 
- Remote commands execute immediately upon receipt
- No "pending authorization" state for commands
- No mechanism for human approval of proposed actions
- No timeout/expiry for unapproved proposals

**Impact**:
- Agents cannot operate in "propose-only" mode
- No gradual trust-building path for automation
- Users must fully trust or fully block agents
- Cannot implement "confirm to enact" safety pattern

**Possible Solutions**:
1. Add `status` field to remote commands (proposed, authorized, enacted, expired)
2. Implement proposal notification to authorized humans
3. Create authorization workflow with timeout
4. Define escalation for unacknowledged proposals

**Status**: Under discussion


---

### GAP-NOCTURNE-001: V4 endpoints are Nocturne-specific

**Scenario**: Cross-project API compatibility

**Description**: Nocturne introduces V4 API endpoints (`/api/v4/...`) that provide enhanced functionality not present in cgm-remote-monitor. These endpoints have no cross-project standard.

**Affected Systems**: Nocturne, any clients adopting V4

**Source**: `externals/nocturne/src/API/Nocturne.API/Controllers/V4/`

**Impact**:
- Clients using V4 endpoints won't work with cgm-remote-monitor
- No interoperability guarantee for V4 features
- Potential ecosystem fragmentation

**Possible Solutions**:
1. Document V4 endpoints as optional extensions
2. Propose V4 endpoints as Nightscout RFC
3. Mark V4 as Nocturne-only, maintain V3 parity

**Status**: Under discussion

---

### GAP-NOCTURNE-002: Rust oref implementation may diverge

**Scenario**: Algorithm consistency across implementations

**Description**: Nocturne contains a native Rust implementation of oref algorithms (`src/Core/oref/`). This independent implementation may produce different results than the JavaScript oref0/oref1.

**Affected Systems**: Nocturne, any system comparing algorithm outputs

**Source**: `externals/nocturne/src/Core/oref/Cargo.toml`

**Impact**:
- Potential calculation differences (IOB, COB, dosing)
- Difficult to debug cross-implementation issues
- No conformance test suite between implementations

**Possible Solutions**:
1. Create cross-implementation test vectors
2. Document any intentional algorithm differences
3. Generate reference outputs for comparison

**Status**: Under discussion

---

### GAP-NOCTURNE-003: SignalR to Socket.IO bridge adds latency

**Scenario**: Real-time data streaming

**Description**: Nocturne uses SignalR for real-time updates, with a bridge to Socket.IO for legacy client compatibility. This adds latency and complexity.

**Affected Systems**: Nocturne, Socket.IO clients (xDrip+, etc.)

**Source**: `externals/nocturne/src/Web/packages/bridge/`

**Impact**:
- Additional latency for real-time glucose updates
- Extra failure point in data pipeline
- Clients must support either SignalR or use bridge

**Possible Solutions**:
1. Maintain parallel Socket.IO and SignalR endpoints
2. Measure and document latency impact
3. Provide native SignalR clients for major platforms

**Status**: Under discussion

---

### GAP-SHARE-001: No Nightscout API v3 support

**Scenario**: Modern Nightscout integration

**Description**: share2nightscout-bridge uses only API v1 (`/api/v1/entries.json`). It does not use v3 features like `identifier`, `srvModified`, or the v3 endpoints.

**Affected Systems**: share2nightscout-bridge, Nightscout v3 clients

**Source**: `externals/share2nightscout-bridge/index.js:50-51`

**Impact**:
- No deduplication via identifier
- Cannot use v3-only features
- Entries lack server timestamps

**Possible Solutions**:
1. Add v3 endpoint support as option
2. Generate client-side identifiers
3. Use v3 upsert for deduplication

**Status**: Under discussion

---

### GAP-SHARE-002: No backfill or gap detection

**Scenario**: Reliable data continuity

**Description**: The bridge fetches the latest N readings but does not detect or fill gaps. If the bridge is down, readings are lost.

**Affected Systems**: share2nightscout-bridge

**Source**: `externals/share2nightscout-bridge/index.js:177-198`

**Impact**:
- Data gaps during bridge downtime
- No historical backfill capability
- No overlap detection with existing data

**Possible Solutions**:
1. Query Nightscout for last entry before fetch
2. Implement gap detection and backfill
3. Increase default maxCount/minutes on restart

**Status**: Under discussion

---

### GAP-SHARE-003: Hardcoded Dexcom application ID

**Scenario**: Long-term maintainability

**Description**: The bridge uses a hardcoded application ID (`d89443d2-327c-4a6f-89e5-496bbb0317db`) for Dexcom authentication. If Dexcom revokes this ID, all bridges break.

**Affected Systems**: share2nightscout-bridge, any fork using same ID

**Source**: `externals/share2nightscout-bridge/index.js:42`

**Impact**:
- Single point of failure for ecosystem
- Cannot easily rotate credentials
- Dexcom could block at any time

**Possible Solutions**:
1. Make application ID configurable
2. Register official Nightscout app with Dexcom
3. Document risk and mitigation

**Status**: Under discussion

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
