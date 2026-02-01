# cgm-remote-monitor V4 Feature Adoption Proposal

> **Date**: 2026-02-01  
> **Status**: Draft  
> **Target**: cgm-remote-monitor maintainers  
> **Related**: [nightscout-v4-integration-proposal.md](nightscout-v4-integration-proposal.md)

---

## Executive Summary

This proposal identifies V4 features from Nocturne that cgm-remote-monitor could adopt to improve interoperability, user experience, and developer ergonomics—without requiring a full rewrite or breaking existing clients.

### Key Constraint

Nocturne author prefers StateSpan as V4-only. This proposal focuses on features that:
1. Are **independently valuable** to cgm-remote-monitor
2. Don't require StateSpan infrastructure
3. Have **clear migration paths** from existing V3 patterns
4. Improve **ecosystem interoperability**

### Recommendation Summary

| Priority | Feature | Benefit | Effort | Breaking |
|----------|---------|---------|--------|----------|
| P1 | Chart Data Endpoint | Reduce client load | Medium | No |
| P1 | Processing Status Endpoint | Debug data flow | Low | No |
| P2 | Device Health Endpoint | User dashboard | Medium | No |
| P2 | Battery Tracking | Proactive alerts | Low | No |
| P2 | Deduplication Service | Sync reliability | Medium | No |
| P3 | System Events Log | Debugging | Low | No |
| P3 | Retrospective Analysis | Time-in-range | High | No |

---

## V4 Feature Analysis

### Features Suitable for Adoption

Based on analysis of Nocturne's V4 controllers (`src/API/Nocturne.API/Controllers/V4/`):

#### 1. ChartDataController (15.7KB)

**What it does**: Pre-aggregates data for chart rendering with configurable resolution.

**cgm-remote-monitor equivalent**: None - clients fetch raw entries and aggregate.

**Adoption value**: HIGH
- Reduces client CPU/memory for long-range charts
- Enables mobile optimization (less data transfer)
- Standardizes aggregation logic server-side

**Proposed endpoint**:
```
GET /api/v3/chart-data?range=7d&resolution=5m
```

**Implementation sketch**:
```javascript
// lib/api3/specific/chartData.js
function chartDataOperation (ctx, env, app) {
  return async function chartData(req, res) {
    const { range, resolution } = req.query;
    const from = parseRange(range);
    const bucketMs = parseResolution(resolution); // 5m = 300000
    
    const pipeline = [
      { $match: { date: { $gte: from } } },
      { $group: {
          _id: { $subtract: ['$date', { $mod: ['$date', bucketMs] }] },
          avg: { $avg: '$sgv' },
          min: { $min: '$sgv' },
          max: { $max: '$sgv' },
          count: { $sum: 1 }
        }
      },
      { $sort: { _id: 1 } }
    ];
    
    const result = await entries.aggregate(pipeline);
    res.json({ result, status: 200 });
  };
}
```

---

#### 2. ProcessingController (9.7KB)

**What it does**: Exposes data processing pipeline status.

**cgm-remote-monitor equivalent**: None - processing is opaque.

**Adoption value**: MEDIUM
- Helps debug "where's my data?" issues
- Shows connector status (Share, Libre, etc.)
- Enables monitoring dashboards

**Proposed endpoint**:
```
GET /api/v3/processing/status
```

**Response example**:
```json
{
  "status": 200,
  "result": {
    "lastRun": 1706832000000,
    "sources": {
      "dexcom-share": { "last": 1706831700000, "count": 288, "status": "ok" },
      "libre-linkup": { "last": 1706831400000, "count": 96, "status": "ok" }
    },
    "queue": { "pending": 0, "failed": 0 }
  }
}
```

---

#### 3. DeviceHealthController (9.9KB)

**What it does**: Tracks CGM transmitter/sensor health metrics.

**cgm-remote-monitor equivalent**: Partial - transmitter battery in devicestatus.

**Adoption value**: MEDIUM
- Proactive sensor expiry warnings
- Transmitter battery trending
- Device lifecycle tracking

**Proposed enhancement**:
```
GET /api/v3/device-health
```

**Implementation**: Aggregate from devicestatus collection:
```javascript
const health = await devicestatus.aggregate([
  { $match: { 'uploader.battery': { $exists: true } } },
  { $sort: { created_at: -1 } },
  { $limit: 100 },
  { $group: {
      _id: '$device',
      battery: { $first: '$uploader.battery' },
      lastSeen: { $first: '$created_at' },
      sensorAge: { $first: '$sensor.sensorAge' }
    }
  }
]);
```

---

#### 4. BatteryController (7.5KB)

**What it does**: Dedicated battery tracking with trend analysis.

**cgm-remote-monitor equivalent**: Raw devicestatus only.

**Adoption value**: LOW-MEDIUM
- Critical for pump/phone battery alerts
- Trend projection ("low in 2 hours")
- Simpler than full devicestatus parse

---

#### 5. DeduplicationController (10.7KB)

**What it does**: Exposes and manages deduplication state.

**cgm-remote-monitor equivalent**: Internal only (identifier field).

**Adoption value**: MEDIUM
- Debug sync conflicts
- Manual duplicate resolution
- Audit trail for data quality

**Proposed endpoint**:
```
GET /api/v3/dedupe/conflicts?collection=treatments
DELETE /api/v3/dedupe/resolve/{id}?keep={canonical}
```

---

#### 6. SystemEventsController (3.5KB)

**What it does**: Logs system events (startup, config changes, errors).

**cgm-remote-monitor equivalent**: Console logs only.

**Adoption value**: LOW
- Useful for hosted deployments
- Audit compliance
- Remote debugging

---

#### 7. RetrospectiveController (25KB)

**What it does**: Time-in-range, A1C estimates, pattern analysis.

**cgm-remote-monitor equivalent**: Reports plugin (client-side).

**Adoption value**: HIGH but complex
- Server-side compute offloads mobile
- Standardized metrics across ecosystem
- Foundation for ML/analytics

**Recommendation**: Phase 2 or later (high effort).

---

### Features NOT Recommended for Adoption

| Feature | Reason |
|---------|--------|
| StateSpansController | Author preference: V4-only |
| TrackersController | Nocturne-specific tracker abstraction |
| UISettingsController | Frontend-specific |
| ConnectorFoodEntriesController | MyFitnessPal-specific |
| ServicesController | .NET Aspire orchestration |

---

## Implementation Roadmap

### Phase 1: Quick Wins (2-4 weeks)

| Endpoint | File | Effort | PR-able |
|----------|------|--------|---------|
| `/api/v3/processing/status` | `lib/api3/specific/processing.js` | Low | Yes |
| `/api/v3/system-events` | `lib/api3/specific/systemEvents.js` | Low | Yes |

### Phase 2: Data Endpoints (4-6 weeks)

| Endpoint | File | Effort | PR-able |
|----------|------|--------|---------|
| `/api/v3/chart-data` | `lib/api3/specific/chartData.js` | Medium | Yes |
| `/api/v3/device-health` | `lib/api3/specific/deviceHealth.js` | Medium | Yes |

### Phase 3: Sync Quality (6-8 weeks)

| Endpoint | File | Effort | PR-able |
|----------|------|--------|---------|
| `/api/v3/dedupe/*` | `lib/api3/specific/deduplication.js` | Medium | Yes |
| `/api/v3/battery` | `lib/api3/specific/battery.js` | Low | Yes |

### Phase 4: Analytics (TBD)

| Endpoint | Effort | Notes |
|----------|--------|-------|
| `/api/v3/retrospective/*` | High | Depends on community interest |

---

## Gap Closure

Adoption of these features would address:

| Gap ID | Description | Resolved By |
|--------|-------------|-------------|
| GAP-API-017 | No server-side chart aggregation | chart-data endpoint |
| GAP-API-018 | Processing pipeline opaque | processing/status |
| GAP-API-019 | Device health fragmented | device-health endpoint |
| GAP-API-020 | Dedup conflicts hidden | dedupe/* endpoints |

---

## Compatibility Guarantees

All proposed endpoints:
1. Use `/api/v3/` prefix (no V4 requirement)
2. Return standard V3 response format (`{ status, result }`)
3. Are opt-in (existing clients unaffected)
4. Require no database schema changes
5. Work with existing authentication

---

## Client SDK Impact

| SDK | Update Needed |
|-----|---------------|
| NightscoutKit (Swift) | Optional convenience methods |
| NSClient (AAPS) | None (V3 compatible) |
| nightscout-js-client | Optional helpers |

---

## Decision Requested

1. **Approve Phase 1** endpoints for PR development?
2. **Chart data priority** - is mobile optimization important enough for Phase 2?
3. **Retrospective analysis** - community interest in server-side TIR?

---

## Related Documents

| Document | Relationship |
|----------|--------------|
| [nightscout-v4-integration-proposal.md](nightscout-v4-integration-proposal.md) | Broader V4 strategy |
| [nocturne-deep-dive.md](../10-domain/nocturne-deep-dive.md) | V4 source reference |
| [pr-adoption-sequencing-proposal.md](../10-domain/pr-adoption-sequencing-proposal.md) | PR pipeline |
| [statespan-standardization-proposal.md](statespan-standardization-proposal.md) | StateSpan V4-only decision |

---

## Appendix: Nocturne V4 Controller Inventory

| Controller | Lines | Adoptable | Notes |
|------------|-------|-----------|-------|
| ChartDataController.cs | 15,691 | ✅ Yes | High value |
| ProcessingController.cs | 9,718 | ✅ Yes | Quick win |
| DeviceHealthController.cs | 9,943 | ✅ Yes | Aggregation |
| BatteryController.cs | 7,526 | ✅ Yes | Simple |
| DeduplicationController.cs | 10,739 | ✅ Yes | Sync quality |
| SystemEventsController.cs | 3,536 | ✅ Yes | Logging |
| RetrospectiveController.cs | 25,086 | ⚠️ Complex | Phase 4 |
| StateSpansController.cs | 10,236 | ❌ V4-only | Author pref |
| TrackersController.cs | 30,924 | ❌ Nocturne | Too coupled |
| UISettingsController.cs | 42,073 | ❌ Frontend | SvelteKit |
| ServicesController.cs | 23,240 | ❌ Infra | .NET Aspire |
| DebugController.cs | 21,882 | ⚠️ Partial | Some useful |
| CompatibilityController.cs | 20,366 | ❌ Nocturne | Migration |
