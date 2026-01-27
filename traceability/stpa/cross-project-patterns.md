# Cross-Project STPA Patterns

> **Version**: 1.0  
> **Created**: 2026-01-27  
> **Work Package**: WP-005 step 3  
> **Source**: UCA analysis across Loop, AAPS, Trio

---

## Executive Summary

Analysis of Unsafe Control Actions (UCAs) across the Nightscout AID ecosystem reveals **3 cross-project pattern categories** affecting all Tier 1 controllers (Loop, AAPS, Trio). These patterns represent shared safety concerns that should be addressed with standardized safety constraints.

| Pattern Category | UCAs | Affected Projects | Priority |
|-----------------|------|-------------------|----------|
| Sync/Deduplication | 3 | Loop, AAPS, Trio, Nightscout | P0 - Critical |
| Remote Command Safety | 2 | Loop, LoopCaregiver, Nightscout | P1 - High |
| Algorithm Override | 2 | Loop, AAPS, Trio | P2 - Medium |

---

## Pattern 1: Sync-Related UCAs (P0 Critical)

**Problem**: Data synchronization failures can cause double dosing or missed treatments.

### UCAs in This Pattern

| UCA ID | Description | Severity | Source Gap |
|--------|-------------|----------|------------|
| UCA-BOLUS-003 | Double bolus due to sync failure | S4 (Critical) | GAP-003, GAP-SYNC-001 |
| UCA-CARB-001 | Duplicate carb entry causes over-bolusing | S3 (Serious) | GAP-003 |
| UCA-SYNC-001 | Data loss during sync causes algorithm to use stale data | S2 (Moderate) | GAP-SYNC-005 |

### Cross-Project Analysis

| Aspect | Loop | AAPS | Trio |
|--------|------|------|------|
| **Sync ID Strategy** | `syncIdentifier` (UUID) | `identifier` + pump composite | `enteredBy` filtering |
| **Upload Method** | POST only (no PUT) | POST with client dedup | POST (server dedup) |
| **Duplicate Risk** | HIGH - POST without upsert | LOW - client-side checks | MEDIUM - timestamp-based |
| **Download Dedup** | Not documented | `nightscoutId` matching | `enteredBy != "Trio"` |

### Root Cause: GAP-003

All controllers use different identity strategies with no unified sync identity field:
- Loop: `syncIdentifier` (not always recognized by Nightscout v1)
- AAPS: `identifier` (explicit, works with v3)
- Trio: `enteredBy` (weak, not per-record)

**Evidence**: Loop source code explicitly notes:
```swift
/* id: objectId, */ /// Specifying _id only works when doing a put (modify);
/// all dose uploads are currently posting
```

### Shared Safety Constraints

| SC ID | Requirement | Applies To |
|-------|-------------|------------|
| SC-SYNC-001 | System SHALL use idempotent upload (PUT/upsert) for doses | Loop, Trio |
| SC-SYNC-002 | System SHALL validate server acknowledgment before local commit | All |
| SC-SYNC-003 | System SHALL implement client-side deduplication by `identifier` | All |
| SC-SYNC-004 | Nightscout SHALL support upsert on client-provided sync ID | Nightscout |

---

## Pattern 2: Remote Command Safety (P1 High)

**Problem**: Remote commands (bolus, carbs, overrides) from caregivers can conflict with local user actions or execute without proper validation.

### UCAs in This Pattern

| UCA ID | Description | Severity | Related Gap |
|--------|-------------|----------|-------------|
| UCA-REMOTE-001 | Remote bolus executed while local bolus in progress | S4 (Critical) | GAP-REMOTE-001 |
| UCA-REMOTE-002 | Remote command executed on wrong device (multi-device family) | S3 (Serious) | GAP-REMOTE-003 |

### Cross-Project Analysis

| Aspect | Loop + LoopCaregiver | Nightscout Remote |
|--------|----------------------|-------------------|
| **Command Flow** | Push notification → Loop processes | Nightscout treatment → Controller polls |
| **Authentication** | Apple Push + per-device auth | API secret (shared) |
| **Rate Limiting** | Not documented | Not implemented |
| **Confirmation** | User must confirm on device | Depends on controller |

### Root Cause: Authority Hierarchy Gap

No unified authority hierarchy exists (GAP-AUTH-002):
- Controllers treat all authenticated writes equally
- No concept of human > agent > controller priority
- Remote commands can override local user decisions

**Evidence**: From `aid-controller-sync-patterns.md`:
> "Nightscout treats all authenticated writes equally. There is no concept of authority levels."

### Shared Safety Constraints

| SC ID | Requirement | Applies To |
|-------|-------------|------------|
| SC-REMOTE-001 | Remote bolus SHALL require local confirmation within 60 seconds | All controllers |
| SC-REMOTE-002 | System SHALL reject remote command if local action in last 5 minutes | All |
| SC-REMOTE-003 | Remote commands SHALL use per-user authentication (not shared secret) | Nightscout |
| SC-REMOTE-004 | System SHALL log remote command source with verified identity | All |

---

## Pattern 3: Override/Algorithm Conflicts (P2 Medium)

**Problem**: Overrides (temp targets, suspend, etc.) can conflict with each other or with algorithm safety limits.

### UCAs in This Pattern

| UCA ID | Description | Severity | Related Gap |
|--------|-------------|----------|-------------|
| UCA-OVERRIDE-001 | Multiple overrides active simultaneously | S2 (Moderate) | GAP-001 |
| UCA-OVERRIDE-002 | Override accepted when loop suspended | S3 (Serious) | — |

### Cross-Project Analysis

| Aspect | Loop | AAPS | Trio |
|--------|------|------|------|
| **Override Model** | `TemporaryScheduleOverride` | `ProfileSwitch` + percentage | Override similar to Loop |
| **Supersession Tracking** | Local only (not synced) | Implicit in ProfileSwitch | Not tracked |
| **Conflict Detection** | New override cancels old | New switch replaces old | Server timestamp |

### Root Cause: GAP-001 and GAP-SYNC-004

Override lifecycle information is not synced:
- Loop tracks `actualEnd` types (`.natural`, `.early`, `.deleted`) locally
- Nightscout receives only `startDate`, `duration`, settings
- No way to query "what override was active at time T"

**Evidence**: From `gaps.md`:
> "When a new override is created while another is active, Nightscout does not automatically mark the previous override as superseded."

### Shared Safety Constraints

| SC ID | Requirement | Applies To |
|-------|-------------|------------|
| SC-OVERRIDE-001 | System SHALL reject override if loop is suspended | All |
| SC-OVERRIDE-002 | System SHALL track override supersession with `superseded_by` field | All |
| SC-OVERRIDE-003 | System SHALL sync override lifecycle changes (end type, actual end) | All |
| SC-OVERRIDE-004 | At most ONE override SHALL be active at any time per controller | All |

---

## Project Coverage Matrix

### Tier 1 Controllers (Safety-Critical)

| Project | Sync UCAs | Remote UCAs | Override UCAs | Total Coverage |
|---------|-----------|-------------|---------------|----------------|
| **Loop** | 2/3 | 2/2 | 2/2 | 6/7 (86%) |
| **AAPS** | 2/3 | 0/2 | 1/2 | 3/7 (43%) |
| **Trio** | 2/3 | 0/2 | 1/2 | 3/7 (43%) |
| **Nightscout** | 1/3 | 1/2 | 1/2 | 3/7 (43%) |

*Coverage = UCAs that have linked safety constraints or mitigations*

### Gap Prioritization

| Priority | Gap | Impact | Effort | Quick Win? |
|----------|-----|--------|--------|------------|
| P0 | GAP-003 (sync identity) | All sync UCAs | High | No |
| P0 | GAP-SYNC-001 (Loop POST only) | Duplicate bolus | Medium | Yes |
| P1 | GAP-AUTH-002 (authority) | Remote command safety | High | No |
| P1 | GAP-REMOTE-001 (confirmation) | Remote bolus conflict | Medium | Yes |
| P2 | GAP-001 (supersession) | Override tracking | Medium | Yes |
| P2 | GAP-SYNC-004 (lifecycle sync) | Override history | Low | Yes |

---

## Recommendations

### Immediate Actions (Quick Wins)

1. **Loop: Switch to PUT/upsert** for dose uploads
   - Eliminates GAP-SYNC-001
   - Prevents UCA-BOLUS-003 at source
   
2. **Nightscout: Add `superseded_by` field** to overrides
   - Enables override lifecycle tracking
   - Low effort, high value

3. **All: Document sync ID expectations** in Nightscout API docs
   - Clarifies identity strategy per controller
   - Enables conformance testing

### Medium-Term (3-6 months)

1. **Unified sync identity protocol** across controllers
   - Single `identifier` field format (UUID)
   - Mandatory for v3 API adoption

2. **Remote command confirmation flow**
   - Require local acknowledgment for all remote actions
   - Rate limiting per user/device

### Long-Term (6-12 months)

1. **Authority hierarchy implementation**
   - Claim-based identity (OIDC)
   - Human > Agent > Controller precedence

2. **Full STPA coverage for Tier 2 projects**
   - xDrip+, xDrip4iOS, DiaBLE

---

## STPA Artifact Summary

### UCAs Cataloged

| ID | Description | Severity | Pattern |
|----|-------------|----------|---------|
| UCA-BOLUS-001 | Bolus not delivered when carbs entered | S2 | — |
| UCA-BOLUS-002 | Bolus delivered when BG < 70 mg/dL | S3 | — |
| UCA-BOLUS-003 | Double bolus due to sync failure | S4 | Sync |
| UCA-BOLUS-004 | Bolus delayed > 15 min after carbs | S2 | — |
| UCA-BOLUS-005 | Bolus continues after user cancel | S3 | — |
| UCA-OVERRIDE-001 | Multiple overrides active simultaneously | S2 | Override |
| UCA-OVERRIDE-002 | Override accepted when loop suspended | S3 | Override |
| UCA-CARB-001 | Duplicate carb entry causes over-bolusing | S3 | Sync |
| UCA-SYNC-001 | Stale data used in algorithm | S2 | Sync |
| UCA-REMOTE-001 | Remote bolus during local bolus | S4 | Remote |
| UCA-REMOTE-002 | Remote command on wrong device | S3 | Remote |

**Total**: 11 UCAs (6 existing + 5 new from pattern analysis)

### Safety Constraints Proposed

| Category | Count | Status |
|----------|-------|--------|
| Sync | 4 | Proposed |
| Remote | 4 | Proposed |
| Override | 4 | Proposed |
| Existing (BOLUS-003) | 2 | Complete |

**Total**: 14 SCs (2 existing + 12 proposed)

---

## References

- [STPA Audit Report](../../../sdqctl/reports/stpa-audit-2026-01-27.md)
- [Severity Scale](../../../sdqctl/docs/stpa-severity-scale.md)
- [STPA-TRACEABILITY-FRAMEWORK.md](../../docs/sdqctl-proposals/STPA-TRACEABILITY-FRAMEWORK.md)
- [AID Controller Sync Patterns](../../mapping/cross-project/aid-controller-sync-patterns.md)
- [Gaps](../gaps.md)

---

**Document Version**: 1.0  
**Last Updated**: 2026-01-27
