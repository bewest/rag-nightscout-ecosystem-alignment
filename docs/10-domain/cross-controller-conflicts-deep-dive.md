# Cross-Controller Conflict Detection Deep Dive

> **Date**: 2026-01-29  
> **Status**: Analysis Complete  
> **Focus**: Behavior when Loop + Trio sync to same Nightscout

---

## Executive Summary

| Aspect | Finding |
|--------|---------|
| **Conflict Risk** | Medium - distinct namespaces prevent data collision |
| **deviceStatus** | Separate plugins (loop vs openaps) - no conflict |
| **treatments** | Deduplication by identifier - potential duplicates |
| **enteredBy** | Loop: `loop://{device}`, Trio: `Trio` - distinguishable |
| **Recommendation** | Safe for read-only; caution for bidirectional sync |

---

## Controller Identification

### Loop

| Field | Value | Source |
|-------|-------|--------|
| `enteredBy` | `loop://{UIDevice.current.name}` | `NightscoutService.swift:335` |
| `source` | `loop://{device}` | Same pattern |
| `syncIdentifier` | UUID-based | `ObjectIdCache.swift` |
| deviceStatus key | `loop` | Nightscout convention |

### Trio

| Field | Value | Source |
|-------|-------|--------|
| `enteredBy` | `Trio` | `NightscoutTreatment.swift:27` |
| `device` | `NightscoutTreatment.local` → `Trio` | Same |
| deviceStatus key | `openaps` | Uses oref0 format |

### AAPS (for reference)

| Field | Value |
|-------|-------|
| `enteredBy` | `AndroidAPS` or `openaps://{device}` |
| deviceStatus key | `openaps` |

---

## Nightscout Plugin Handling

### deviceStatus Namespace Separation

```
deviceStatus: {
  loop: { ... }      ← Loop plugin reads this
  openaps: { ... }   ← OpenAPS plugin reads this (Trio, AAPS)
}
```

**Finding**: Loop and Trio use **different deviceStatus namespaces**. No conflict.

### Plugin Detection

| Plugin | Detection Logic | Source |
|--------|-----------------|--------|
| `loop.js` | `status.loop && status.loop.timestamp` | Line 135 |
| `openaps.js` | `status.openaps && status.openaps.iob` | Line 87 |

Both plugins can be active simultaneously. Nightscout displays whichever has more recent data.

---

## Treatment Deduplication

### Nightscout Dedup Strategy

```javascript
// websocket.js:364-366
if (data.data.NSCLIENT_ID) {
  query = { NSCLIENT_ID: data.data.NSCLIENT_ID };
}
```

### API v3 Dedup

```javascript
// api3/storage/mongoCollection/utils.js:130
identifyingFilter(identifier, doc, dedupFallbackFields)
```

Primary key: `identifier`  
Fallback: `created_at` + `eventType` + collection-specific fields

### Conflict Scenarios

| Scenario | Risk | Mitigation |
|----------|------|------------|
| Same bolus from both controllers | Low | Different identifiers, timestamps |
| Carb entry entered on one, synced to both | Medium | identifier dedup if present |
| Override from Loop, Trio reads | Low | enteredBy distinguishes |
| Manual entry via Nightscout | Medium | No controller identifier |

---

## Potential Conflict Cases

### Case 1: Duplicate Treatments

**Scenario**: User enters carbs in both Loop and Trio.

| Controller | Created | identifier | enteredBy |
|------------|---------|------------|-----------|
| Loop | 2026-01-29T10:00:00Z | `abc-123` | `loop://iPhone` |
| Trio | 2026-01-29T10:00:30Z | `def-456` | `Trio` |

**Result**: Both stored - **duplicate carbs in Nightscout**

**Risk**: Double-counting in COB calculations

### Case 2: Conflicting deviceStatus

**Scenario**: Both controllers upload simultaneously.

```json
{
  "device": "loop://iPhone",
  "loop": { "iob": { "iob": 2.5 } }
}
{
  "device": "Trio",
  "openaps": { "iob": { "iob": 2.3 } }
}
```

**Result**: Both stored. Nightscout shows **most recent** in UI.

**Risk**: Confusion if IOB differs significantly.

### Case 3: Profile Conflicts

**Scenario**: Different basal profiles active.

| Controller | Profile | Active |
|------------|---------|--------|
| Loop | `Default` | Basal: 1.0 U/hr |
| Trio | `Exercise` | Basal: 0.7 U/hr |

**Result**: Nightscout receives both profiles. Display depends on timestamp.

**Risk**: Caregiver confusion about which profile is active.

---

## Safeguards in Place

### 1. enteredBy Filtering

```javascript
// treatmentnotify.js:28
if (enteredBy.indexOf('openaps://') === 0 || enteredBy.indexOf('loop://') === 0) {
  // Skip notification for automated treatments
}
```

### 2. Namespace Isolation

- Loop → `deviceStatus.loop`
- Trio/AAPS → `deviceStatus.openaps`

### 3. Timestamp-Based Display

Nightscout shows most recent deviceStatus in pill display.

---

## Gaps Identified

### GAP-SYNC-020: No Cross-Controller Deduplication

**Description**: Nightscout does not detect when the same treatment is entered in multiple controllers.

**Impact**: Duplicate treatments, incorrect IOB/COB.

**Remediation**: Add deduplication based on timestamp + amount + eventType within tolerance window.

### GAP-SYNC-030: No Controller Conflict Warning

**Description**: Nightscout does not warn when multiple controllers upload to same instance.

**Impact**: User may not realize both controllers are active.

**Remediation**: Add warning when deviceStatus from different controllers received within 5 minutes.

### GAP-SYNC-031: Profile Sync Ambiguity

**Description**: When multiple controllers upload profiles, no indication which is authoritative.

**Impact**: Caregiver may see wrong profile.

**Remediation**: Add `sourceController` field to profile display.

---

## Recommendations

### For Users

1. **Avoid running multiple controllers** with same Nightscout URL
2. If testing, use **read-only mode** on secondary controller
3. Monitor for duplicate treatments in Nightscout

### For Developers

1. Add controller collision detection in Nightscout
2. Add `x-controller-id` header to API requests
3. Display active controller prominently in UI

### For Ecosystem

1. Document multi-controller risks in user guides
2. Add conformance test for controller identification
3. Consider `controller` field in deviceStatus spec

---

## Source Code References

| Component | File | Line | Purpose |
|-----------|------|------|---------|
| Loop source | `NightscoutService.swift` | 335 | `loop://{device}` pattern |
| Trio enteredBy | `NightscoutTreatment.swift` | 27 | `static let local = "Trio"` |
| Trio carbs | `CarbsEntry.swift` | 16 | `static let local = "Trio"` |
| NS loop plugin | `loop.js` | 135 | `status.loop` detection |
| NS openaps plugin | `openaps.js` | 87 | `status.openaps` detection |
| NS dedup | `websocket.js` | 364 | NSCLIENT_ID dedup |
| API v3 dedup | `utils.js` | 130 | identifier-based dedup |

---

## Test Scenarios

### Scenario 1: Concurrent Upload

```yaml
given: Loop and Trio configured with same Nightscout URL
when: Both upload deviceStatus within 1 minute
then: Both deviceStatus records stored
  and: UI shows most recent
  and: No error or warning displayed
```

### Scenario 2: Duplicate Treatment Detection

```yaml
given: Carb entry in Loop at 10:00:00
  and: Same carbs in Trio at 10:00:30
when: Both sync to Nightscout
then: Two treatment records created
  and: COB shows doubled carbs (BUG)
```

### Scenario 3: Read-Only Secondary

```yaml
given: Loop as primary (read-write)
  and: Trio as secondary (read-only, upload=false)
when: User monitors via Trio
then: No duplicate treatments
  and: Trio displays Loop data correctly
```

---

## Cross-References

- [Sync & Identity Gaps](../../traceability/sync-identity-gaps.md)
- [Treatment Sync Scenarios](../../conformance/scenarios/treatment-sync.yaml)
- [DeviceStatus Deep Dive](devicestatus-deep-dive.md)
- [Gaps Index](../../traceability/gaps.md)
