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
