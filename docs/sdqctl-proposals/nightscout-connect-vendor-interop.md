# nightscout-connect Vendor Interoperability Proposal

> **Status**: Draft  
> **Author**: Ecosystem Alignment Workspace  
> **Date**: 2026-01-29  
> **Based On**: nightscout-connect audit, tconnectsync deep dive, nightscout-librelink-up deep dive

---

## Executive Summary

This proposal recommends enhancements to nightscout-connect to improve vendor data coverage, API compatibility, and deduplication. The recommendations are derived from analyzing tconnectsync and nightscout-librelink-up, which demonstrate more complete implementations that nightscout-connect can adopt.

### Key Recommendations

| Priority | Recommendation | Addresses |
|----------|---------------|-----------|
| P0 | Add v3 API output driver | GAP-CONNECT-001 |
| P1 | Extend LibreLinkUp to fetch treatments | GAP-CONNECT-002 |
| P1 | Implement client-side sync identity | GAP-CONNECT-003 |
| P2 | Add Tandem/Control-IQ source | New capability |
| P2 | Add test suite using XState testing utilities | Quality |

---

## Current State Analysis

### nightscout-connect Gaps

| Gap | Issue | Impact |
|-----|-------|--------|
| GAP-CONNECT-001 | v1 API only | No UPSERT, duplicates on re-run |
| GAP-CONNECT-002 | Inconsistent coverage | Only Minimed uploads all 3 collections |
| GAP-CONNECT-003 | No dedup strategy | Relies on server-side dedup |

### Current Source Coverage

| Source | entries | treatments | devicestatus |
|--------|---------|------------|--------------|
| Dexcom Share | ✅ | ❌ | ❌ |
| LibreLinkUp | ✅ | ❌ | ❌ |
| Nightscout | ✅ | ❌ | ❌ |
| Glooko | ❌ | ✅ | ❌ |
| Minimed CareLink | ✅ | ✅ | ✅ |

### Comparison with Peer Projects

| Feature | nightscout-connect | tconnectsync | nightscout-librelink-up |
|---------|-------------------|--------------|------------------------|
| **Language** | JavaScript | Python | TypeScript |
| **Architecture** | XState machines | SQLite + processors | Polling loop |
| **API Version** | v1 only | v1 (treatments) | v1 + v3 stub |
| **Dedup Strategy** | None | SQLite tracking | Timestamp-based |
| **Test Suite** | None | pytest | Jest |
| **Treatments** | Minimed only | Full (bolus, basal, IOB) | None |
| **DeviceStatus** | Minimed only | Full (pump, IOB, reservoir) | None |

---

## Recommendation 1: Add v3 API Output Driver

### Priority: P0

### Problem

The current REST output driver (`lib/outputs/nightscout.js`) only supports API v1:
- `POST /api/v1/entries.json`
- `POST /api/v1/treatments.json`

This means:
- Duplicate records on re-runs (no UPSERT)
- No identifier-based sync
- No server-side validation

### Solution

Create `lib/outputs/nightscout-v3.js` with v3 API support:

```javascript
// lib/outputs/nightscout-v3.js
const ENDPOINTS = {
  entries: '/api/v3/entries',
  treatments: '/api/v3/treatments',
  devicestatus: '/api/v3/devicestatus'
};

async function upsert(collection, records, session) {
  // v3 uses PUT with identifier for UPSERT
  for (const record of records) {
    await axios.put(
      `${session.url}${ENDPOINTS[collection]}`,
      record,
      { headers: { 'Authorization': `Bearer ${session.token}` } }
    );
  }
}
```

### Implementation Steps

1. Copy `lib/outputs/nightscout.js` to `nightscout-v3.js`
2. Change endpoints to v3 paths
3. Add JWT token authentication (vs API-SECRET hash)
4. Implement PUT for UPSERT semantics
5. Add `identifier` field generation (see Recommendation 3)
6. Add configuration option: `CONNECT_API_VERSION=v3`

### Reference

nightscout-librelink-up has a v3 stub at `src/nightscout/apiv3.ts` that can serve as a TypeScript reference.

---

## Recommendation 2: Extend Source Data Coverage

### Priority: P1

### Problem

Most sources only upload entries (glucose readings), missing:
- **treatments**: boluses, temp basals, carbs
- **devicestatus**: pump battery, reservoir, IOB

### Solution by Source

#### LibreLinkUp Enhancement

**Current**: Only fetches glucose from `/llu/connections/{id}/graph`

**Enhancement**: LibreLink Up API also provides:
- Insulin doses (if entered in app)
- Carb entries (if entered in app)
- Sensor status

```javascript
// lib/sources/librelinkup.js - Enhanced transform
function transformData(raw, session) {
  return {
    entries: raw.graphData.map(to_ns_sgv),
    treatments: raw.logbookData?.map(to_ns_treatment) || [],
    devicestatus: [{
      device: 'nightscout-connect://librelinkup',
      created_at: new Date().toISOString(),
      uploader: { battery: 100 }
    }]
  };
}
```

#### Dexcom Share Enhancement

**Current**: Only fetches glucose readings

**Enhancement**: Add devicestatus with sensor info:

```javascript
devicestatus: [{
  device: 'nightscout-connect://dexcomshare',
  created_at: new Date().toISOString(),
  uploader: { battery: 100 },
  sensor: {
    sensorAge: calculateSensorAge(session.sensorStart)
  }
}]
```

#### Glooko Enhancement

**Current**: Only fetches treatments

**Enhancement**: Also fetch CGM data from `/api/v2/cgm/readings`:

```javascript
// lib/sources/glooko/index.js
async function dataFromSession(session) {
  const [treatments, cgm] = await Promise.all([
    fetchTreatments(session),
    fetchCgmReadings(session)  // NEW
  ]);
  return { treatments, cgm };
}
```

### Reference Implementation: tconnectsync

tconnectsync demonstrates complete coverage for Tandem pumps:

| Data Type | tconnectsync Module | nightscout-connect Equivalent |
|-----------|--------------------|-----------------------------|
| Bolus | `sync/process_bolus.py` | treatments array |
| Basal | `sync/process_basal.py` | treatments array |
| IOB | `sync/process_iob.py` | devicestatus.openaps.iob |
| Pump | `sync/process_pump.py` | devicestatus.pump |
| CGM | `sync/process_cgm.py` | entries array |

---

## Recommendation 3: Implement Client-Side Sync Identity

### Priority: P1

### Problem

No deduplication strategy means:
- Re-runs create duplicate records
- No idempotent uploads
- Recovery from failures creates duplicates

### Solution

Generate deterministic UUIDs matching Nightscout's sync identity spec:

```javascript
// lib/sync-identity.js
const { v5: uuidv5 } = require('uuid');

const NAMESPACE = '4e7a4b1c-8f2d-4a9e-b3c1-5d6e7f8a9b0c';

function generateIdentifier(record, source) {
  // Match Nightscout's UUID v5 generation
  const input = `${source}|${record.date}|${record.type || record.eventType}`;
  return uuidv5(input, NAMESPACE);
}

function addIdentifiers(batch, source) {
  return {
    entries: batch.entries.map(e => ({
      ...e,
      identifier: generateIdentifier(e, source)
    })),
    treatments: batch.treatments.map(t => ({
      ...t,
      identifier: generateIdentifier(t, source)
    })),
    devicestatus: batch.devicestatus.map(d => ({
      ...d,
      identifier: generateIdentifier(d, source)
    }))
  };
}
```

### Integration Point

Add to transform pipeline in fetch machine:

```javascript
// lib/machines/fetch.js - Transforming state
onDone: {
  target: 'Persisting',
  actions: assign({
    transformed: (ctx, event) => addIdentifiers(event.data, ctx.source)
  })
}
```

---

## Recommendation 4: Add Tandem/Control-IQ Source

### Priority: P2

### Problem

Tandem t:slim X2 with Control-IQ is a popular pump with no nightscout-connect source. Users must use tconnectsync separately.

### Solution

Port tconnectsync's API client to nightscout-connect:

```javascript
// lib/sources/tandem/index.js
module.exports = function(config) {
  const impl = {
    authFromCredentials: async () => {
      // OAuth2 PKCE flow to t:connect
      // Reference: tconnectsync/api/tandemsource.py
    },
    
    sessionFromAuth: async (auth) => {
      // Exchange auth for session
    },
    
    dataFromSession: async (session) => {
      // Fetch from Control-IQ therapy timeline
      // Reference: tconnectsync/api/controliq.py
    },
    
    transformData: (raw) => {
      // Convert to Nightscout format
      // Reference: tconnectsync/sync/process_*.py
    }
  };
  
  return {
    impl,
    generate_driver: (builder) => {
      builder.support_session({
        authenticate: impl.authFromCredentials,
        authorize: impl.sessionFromAuth,
        delays: { EXPIRE_SESSION_DELAY: 3600000 }
      });
      
      builder.register_loop('TandemEntries', {
        frame: { impl: impl.dataFromSession, transform: impl.transformData },
        expected_data_interval_ms: 5 * 60 * 1000
      });
    }
  };
};
```

### Data Coverage (from tconnectsync)

| Data Type | t:connect API | Nightscout Collection |
|-----------|--------------|----------------------|
| CGM readings | therapy_timeline | entries |
| Boluses | therapy_timeline | treatments |
| Basal rates | therapy_timeline | treatments (temp basal) |
| IOB | therapy_timeline | devicestatus.openaps.iob |
| Pump status | device_status | devicestatus.pump |
| Reservoir | device_status | devicestatus.pump.reservoir |

---

## Recommendation 5: Add Test Suite

### Priority: P2

### Problem

No automated tests despite XState's excellent testing utilities.

### Solution

Use XState's `@xstate/test` for state machine testing:

```javascript
// tests/machines/fetch.test.js
const { createModel } = require('@xstate/test');
const { fetchMachine } = require('../../lib/machines/fetch');

const testModel = createModel(fetchMachine).withEvents({
  SESSION_RESOLVED: { exec: () => {} },
  DATA_RECEIVED: { exec: () => {} },
  // ... other events
});

describe('Fetch Machine', () => {
  const testPlans = testModel.getShortestPathPlans();
  
  testPlans.forEach(plan => {
    describe(plan.description, () => {
      plan.paths.forEach(path => {
        it(path.description, async () => {
          await path.test();
        });
      });
    });
  });
});
```

### Reference

tconnectsync has pytest tests in `tests/` that can serve as examples for test scenarios.

---

## Implementation Roadmap

### Phase 1: Foundation (P0)

| Task | Effort | Deliverable |
|------|--------|-------------|
| v3 output driver | 2 days | `lib/outputs/nightscout-v3.js` |
| Sync identity module | 1 day | `lib/sync-identity.js` |
| Configuration updates | 0.5 days | env var documentation |

### Phase 2: Coverage (P1)

| Task | Effort | Deliverable |
|------|--------|-------------|
| LibreLinkUp treatments | 2 days | Enhanced transform |
| Dexcom Share devicestatus | 1 day | Sensor status |
| Glooko CGM | 1 day | Entries support |

### Phase 3: Expansion (P2)

| Task | Effort | Deliverable |
|------|--------|-------------|
| Tandem source | 5 days | `lib/sources/tandem/` |
| Test suite | 3 days | `tests/` |

---

## Success Metrics

| Metric | Current | Target |
|--------|---------|--------|
| Sources with full coverage | 1/5 (20%) | 4/5 (80%) |
| API version support | v1 only | v1 + v3 |
| Dedup strategy | None | UUID v5 |
| Test coverage | 0% | 60% |
| Duplicate rate on re-run | High | 0% (with v3) |

---

## Related Documentation

- [nightscout-connect Deep Dive](../10-domain/nightscout-connect-deep-dive.md)
- [tconnectsync Deep Dive](../10-domain/tconnectsync-deep-dive.md)
- [nightscout-librelink-up Deep Dive](../10-domain/nightscout-librelink-up-deep-dive.md)
- [Interoperability Spec v1](../../specs/interoperability-spec-v1.md)

---

*Generated: 2026-01-29 | Ecosystem Alignment Workspace*
