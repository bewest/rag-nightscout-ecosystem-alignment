# MongoDB Update Readiness Report for Nightscout Core

**Document Version:** 1.0  
**Date:** 2026-01-19  
**Prepared for:** Nightscout Core Development Team  
**Related Document:** [MongoDB Modernization Impact Assessment](./mongodb-modernization-impact-assessment.md)

---

## Executive Summary

This report assesses the MongoDB modernization readiness of the `cgm-remote-monitor` project based on analysis of the `wip/replit/with-mongodb-update` branch and ecosystem-wide client patterns.

### Overall Readiness: Phase 1 Complete, Ready for Phase 2

| Phase | Status | Confidence |
|-------|--------|------------|
| Phase 1: Test Infrastructure & Baseline | ✅ Complete | High |
| Phase 2: Storage Layer Analysis | 🔄 Next | - |
| Phase 3: Core Implementation | ⏳ Pending | - |
| Phase 4: Testing & Validation | ⏳ Pending | - |
| Phase 5: Driver Upgrade Execution | ⏳ Pending | - |

---

## Current State Assessment

### Branch Status

| Item | Value |
|------|-------|
| Repository | `bewest/cgm-remote-monitor-1` |
| Branch | `wip/replit/with-mongodb-update` |
| Nightscout Version | 15.0.4 |
| Current MongoDB Driver | `mongodb-legacy: ^5.0.0` |
| Node.js Support | ^16.x or ^14.x |

### Phase 1 Deliverables (Verified)

| Deliverable | Status | Evidence |
|-------------|--------|----------|
| Test Infrastructure | ✅ | 3 new test files, 1,229 lines of test code |
| Client Pattern Fixtures | ✅ | AAPS, Loop, Trio fixtures documented |
| Flaky Test Tooling | ✅ | `scripts/flaky-test-runner.js` (513 lines) |
| Deduplication Testing | ✅ | 29/30 tests passing (96.7%) |
| Documentation Restructure | ✅ | Taxonomic docs/ structure with INDEX.md |

### Known Issue

One test times out with large devicestatus documents (500+ prediction values). Team attributes this to infrastructure rather than code logic.

---

## Risk Assessment Matrix

### Critical Risks (Must Address Before Driver Upgrade)

| Risk | Impact | Affected Clients | Mitigation |
|------|--------|------------------|------------|
| Response format breaking change | **HIGH** | Loop, Trio | Implement Write Result Translator |
| `insertedIds` format change (3.x→4.x+) | **HIGH** | Loop, Trio | API layer must translate to stable v1 format |
| Batch response ordering loss | **HIGH** | Loop | Explicit ordering tests required |
| v1 API `insertOne` used for arrays | **MEDIUM** | Loop, Trio | Audit all v1 endpoints |

### Driver Format Changes

| Format | MongoDB Driver 3.x | MongoDB Driver 4.x+ |
|--------|-------------------|---------------------|
| insertedIds | `{ '0': id1, '1': id2 }` | `[id1, id2]` |

**v1 API Expected Response:**
```javascript
[{ _id: 'id1', ok: 1, n: 1 }, { _id: 'id2', ok: 1, n: 1 }]
```

### Client-Specific Risk Levels

| Client | API | Upload Pattern | Risk Level | Key Concern |
|--------|-----|----------------|------------|-------------|
| **AAPS** | v3 | Single docs | Low | Response schema (`isDeduplication` field) |
| **Loop** | v1 | Batch arrays (up to 1000) | **HIGH** | Response ordering must match request order |
| **Trio** | v1 | Throttled batches (2s window) | **HIGH** | Same concerns as Loop |

---

## Recommended Next Steps

### Phase 2: Storage Layer Analysis (Recommended Now)

1. **Audit MongoDB Usage**
   - Map all `insertOne`/`insertMany` call sites in `lib/storage/`
   - Document which endpoints use which methods
   - Identify any places where arrays are passed to `insertOne`

2. **API v1 Endpoint Audit**
   - Verify `/api/v1/treatments.json` uses `insertMany` for array inputs
   - Verify `/api/v1/entries.json` uses `insertMany` for array inputs
   - Document response format generation code

3. **Response Format Analysis**
   - Locate code that constructs v1 API responses
   - Document current response format generation
   - Identify abstraction point for Write Result Translator

### Phase 3: Core Implementation (After Phase 2)

1. **Write Result Translator**
   - Create abstraction layer between MongoDB driver and API responses
   - Translate driver-specific formats to stable client-facing format
   - Maintain response ordering for batch operations

2. **Response Order Preservation**
   - Ensure batch responses maintain submission order
   - Handle partial failures gracefully (some inserted, some failed)
   - Return correct `_id` for deduplicated items

### Safe to Proceed With (Low Risk)

These optimizations don't affect client-facing behavior:
- Connection pooling improvements
- Index optimization
- Internal aggregation pipelines
- Wire protocol compression
- Read/write concern tuning (with testing)

---

## Testing Requirements

### Pre-Upgrade Test Matrix

| Test Scenario | AAPS | Loop | Trio | Priority |
|--------------|------|------|------|----------|
| Single document insert | ✅ | N/A | N/A | P1 |
| Batch array insert | N/A | ✅ | ✅ | P0 |
| Deduplication detection | ✅ | ✅ | ✅ | P0 |
| Response format validation | ✅ | ✅ | ✅ | P0 |
| Partial failure in batch | N/A | ✅ | ✅ | P1 |
| Update existing | ✅ | ✅ | ✅ | P1 |
| Delete by identifier | ✅ | ✅ | ✅ | P2 |
| Large batch (100+ docs) | N/A | ✅ | N/A | P1 |
| Batch with some deduped | N/A | ✅ | ✅ | P0 |
| Response order preservation | N/A | ✅ | ✅ | P0 |
| Rapid sequential (throttle) | N/A | N/A | ✅ | P2 |

### Required Validation Steps

1. Run existing test suite with updated driver
2. Run `storage.shape-handling.test.js` 
3. Run new client pattern tests (`api.partial-failures.test.js`, `api.deduplication.test.js`, `api.aaps-client.test.js`)
4. Test with real AAPS, Loop, and Trio clients in staging environment
5. Verify batch response ordering with deduplication scenarios
6. Test partial failure recovery (duplicate key in middle of batch)

---

## Deduplication Patterns Reference

### AAPS
- **Primary Key:** `pumpId + pumpType + pumpSerial`
- **Response Dependency:** `identifier`, `isDeduplication`, `deduplicatedIdentifier`, `lastModified`

### Loop
- **Primary Key:** `syncIdentifier` (UUID)
- **Critical Behavior:** Response array index must match request array index
- **Cache:** `ObjectIdCache` maps `syncIdentifier` → Nightscout `objectId`

### Trio
- **Primary Key:** `id` field (UUID, distinct from MongoDB `_id`)
- **Critical Behavior:** `id` field must not interfere with MongoDB `_id`

---

## Success Criteria for MongoDB Update

### Minimum Viable Upgrade

1. All existing tests pass with new driver
2. New client pattern tests pass
3. Response format unchanged for v1 and v3 APIs
4. Batch operations maintain submission order
5. Deduplication responses include all required fields

### Recommended Additional Criteria

1. Real client testing in staging (at least one of each: AAPS, Loop, Trio)
2. Load testing with realistic batch sizes
3. Large document testing (devicestatus with 500+ prediction values)
4. Partial failure recovery verified

---

## Related Documents

- [MongoDB Modernization Impact Assessment](./mongodb-modernization-impact-assessment.md) - Detailed client data patterns and test fixtures
- [CGM Remote Monitor Analysis 2026-01-18](../cgm-remote-monitor-analysis-2026-01-18.md) - Repository analysis and verification
- cgm-remote-monitor `docs/proposals/mongodb-modernization-implementation-plan.md` - Team's internal implementation plan

---

## Document History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-01-19 | Initial readiness assessment |
