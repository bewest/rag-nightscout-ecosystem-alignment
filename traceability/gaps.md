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
