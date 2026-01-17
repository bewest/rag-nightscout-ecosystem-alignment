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

**Description**: Loop remote commands (override, carb, bolus) track `remoteAddress` but there's no verification of sender authority.

**Loop-Specific Evidence**: Remote commands set `enactTrigger = .remote(address)` and `enteredBy = "Loop (via remote command)"` but no permission check.

**Source**: [Loop Nightscout Sync](../mapping/loop/nightscout-sync.md#gap-remote-001-remote-command-authorization)

**Impact**:
- Anyone with Nightscout API access can issue commands
- No authority hierarchy for remote vs local commands
- Related to GAP-AUTH-001 (unverified enteredBy)

**Possible Solutions**:
1. OTP verification for remote commands (Loop already has `OTPManager`)
2. OIDC-based command authorization
3. Gateway-level command filtering (NRG)

**Status**: Under discussion

**Related**:
- [GAP-AUTH-001](#gap-auth-001-enteredby-field-is-unverified)
- [Authority Model](../docs/10-domain/authority-model.md)

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
