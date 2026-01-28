# Batch Operation Ordering Deep Dive

> **Sources**: Loop, AAPS, Trio, Nightscout  
> **Last Updated**: 2026-01-28

## Overview

This document analyzes how batch operations (uploads, responses, deduplication) are handled across the Nightscout ecosystem, with focus on order preservation requirements critical for sync identity mapping.

## The Core Problem

Loop (and similar clients) rely on **positional response matching** to map local sync identifiers to Nightscout object IDs:

```swift
// Loop's ObjectIdCache population
for (syncIdentifier, objectId) in zip(syncIdentifiers, createdObjectIds) {
    self.objectIdCache.add(syncIdentifier: syncIdentifier, objectId: objectId)
}
```

**If response order differs from request order, the cache maps wrong IDs.**

---

## System-by-System Analysis

### Loop: ObjectIdCache Architecture

**Source**: `NightscoutServiceKit/ObjectIdCache.swift`

```swift
public struct ObjectIdCache: RawRepresentable, Equatable {
    var storageBySyncIdentifier: [String: ObjectIDMapping]
    
    mutating func add(syncIdentifier: String, objectId: String) {
        let mapping = ObjectIDMapping(
            loopSyncIdentifier: syncIdentifier, 
            nightscoutObjectId: objectId
        )
        storageBySyncIdentifier[syncIdentifier] = mapping
    }
    
    func findObjectIdBySyncIdentifier(_ syncIdentifier: String) -> String? {
        return storageBySyncIdentifier[syncIdentifier]?.nightscoutObjectId
    }
    
    mutating func purge(before date: Date) {
        storageBySyncIdentifier = storageBySyncIdentifier.filter { 
            $0.value.createdAt >= date 
        }
    }
}
```

#### Upload Flow

**Source**: `NightscoutServiceKit/NightscoutService.swift`

1. **Create**: Batch upload → receive objectId array → `zip()` with syncIdentifiers → cache
2. **Update**: Lookup objectId by syncIdentifier → PUT to Nightscout
3. **Delete**: Lookup objectId by syncIdentifier → DELETE from Nightscout

```swift
uploader.createCarbData(syncCarbObjects) { result in
    switch result {
    case .success(let createdObjectIds):
        for (syncIdentifier, objectId) in zip(syncIdentifiers, createdObjectIds) {
            if let syncIdentifier = syncIdentifier {
                self.objectIdCache.add(syncIdentifier: syncIdentifier, objectId: objectId)
            }
        }
        // Then proceed to updates...
    }
}
```

#### Order Dependency

| Assumption | Consequence if Violated |
|------------|------------------------|
| Response order = request order | Wrong ID mappings |
| N responses for N requests | Cache corruption |
| Deduplicated items in response | Missing mappings |

---

### AAPS: Sequential Processing

**Source**: `plugins/sync/src/main/kotlin/app/aaps/plugins/sync/nsclientV3/DataSyncSelectorV3.kt`

AAPS uses **sequential single-document uploads** rather than true batching:

```kotlin
// Each data type processed sequentially
while (cont) {
    val pair = dataSyncSelector.getLastBolusesToSync()
    if (pair == null) {
        cont = false
    } else {
        nsAdd(pair)  // Single document upload
    }
}
```

#### Response Handling

**Source**: `NSClientV3Plugin.kt:654-710`

```kotlin
result.identifier?.let { 
    dataPair.value.ids.nightscoutId = it 
}
```

| Feature | Implementation |
|---------|----------------|
| Batch size | 1 (sequential) |
| ID mapping | Direct assignment from response |
| Order dependency | None (single-doc) |
| Dedup handling | Server returns existing ID |

#### LastSyncedId Tracking

```kotlin
// Preferences track last synced database ID per type
sp.getLong(R.string.key_ns_bolus_last_synced_id, 0)
sp.getLong(R.string.key_ns_carbs_last_synced_id, 0)
// etc.
```

---

### Nightscout: API v3 Create Operation

**Source**: `lib/api3/generic/create/operation.js`

```javascript
async function create (opCtx) {
    const doc = req.body;
    
    // Generate or validate identifier
    opTools.resolveIdentifier(doc);
    
    // Check for existing document (deduplication)
    const identifyingFilter = col.storage.identifyingFilter(
        doc.identifier, doc, col.dedupFallbackFields
    );
    const result = await col.storage.findOneFilter(identifyingFilter, {});
    
    if (result.length > 0) {
        // Duplicate found - update instead
        await replace(opCtx, doc, result[0], { isDeduplication: true });
    } else {
        // New document - insert
        await insert(opCtx, doc);
    }
}
```

#### Deduplication Response

**Source**: `lib/api3/generic/update/replace.js`

```javascript
if (storageDoc.identifier !== doc.identifier || isDeduplication) {
    fields.isDeduplication = true;
    if (storageDoc.identifier !== doc.identifier) {
        fields.deduplicatedIdentifier = storageDoc.identifier;
    }
}
```

Response includes:
- `identifier`: The document's identifier
- `isDeduplication`: `true` if this was a dedup match
- `deduplicatedIdentifier`: Original identifier if different

---

## Batch Behavior Matrix

### Request Scenarios

| Scenario | Expected Response | Loop Impact |
|----------|-------------------|-------------|
| 3 new items | 3 identifiers (ordered) | ✅ Cache populated |
| 3 items, 1 dup | 3 identifiers (dup has existing ID) | ✅ If all 3 returned |
| 3 items, 1 fails | 2 identifiers | ❌ Cache misaligned |
| 3 items, reordered | 3 identifiers (wrong order) | ❌ Wrong mappings |

### API v3 Single-Document Behavior

API v3 processes **one document per request** (no batch endpoint):

| Aspect | Behavior |
|--------|----------|
| Batch endpoint | None (POST single doc) |
| Order guarantee | N/A (single doc) |
| Dedup response | `isDeduplication: true` + existing `identifier` |
| Partial failure | N/A (single doc) |

### API v1 Legacy Batch Behavior

API v1 accepts arrays but has different characteristics:

| Aspect | Behavior |
|--------|----------|
| Batch endpoint | POST accepts array |
| Order guarantee | Not documented |
| Dedup response | Returns `_id` array |
| Partial failure | Varies by implementation |

---

## Deduplication Mechanisms

### By Identifier (v3)

```javascript
// Primary dedup: exact identifier match
{ identifier: doc.identifier }
```

### Fallback Deduplication (v3)

```javascript
// Fallback when API3_DEDUP_FALLBACK_ENABLED
{ created_at: doc.created_at, eventType: doc.eventType }
```

**Configuration**: `API3_DEDUP_FALLBACK_ENABLED` environment variable

### Loop's Treatment Dedup

Loop uses `syncIdentifier` field which maps to Nightscout `identifier`:

```swift
// Loop generates UUID for each treatment
let syncIdentifier = UUID().uuidString
// Uploaded as `identifier` to Nightscout
```

---

## Order Preservation Requirements

### REQ-BATCH-001: Response Order MUST Match Request Order

For batch operations, the response array MUST maintain the same order as the request array.

**Rationale**: Clients use positional matching to correlate responses with requests.

**Verification**: Test that `response[i]` corresponds to `request[i]`.

### REQ-BATCH-002: Deduplicated Items MUST Be Included in Response

When a batch contains items that match existing documents, the response MUST include entries for those items with the existing document's identifier.

**Rationale**: Clients expect N responses for N requests.

**Verification**: Test batch with known duplicates, verify response length equals request length.

### REQ-BATCH-003: Partial Failures SHOULD Include Position Information

When some items in a batch fail validation, the response SHOULD indicate which positions failed.

**Rationale**: Clients need to know which items to retry.

**Verification**: Test batch with some invalid items, verify failure positions reported.

---

## Client Recommendations

### For Loop-style Clients

1. **Prefer single-document uploads** to avoid order issues
2. **Include `identifier` in request** for server-side dedup
3. **Parse `identifier` from response**, not positional matching
4. **Handle `isDeduplication` flag** to detect existing documents

### For AAPS-style Clients

1. **Sequential processing** already avoids batch ordering issues
2. **Store `nightscoutId` directly** from response
3. **Use `LastSyncedId` pattern** for resume after failure

---

## Existing Gap Coverage

| Gap ID | Title | Status |
|--------|-------|--------|
| GAP-BATCH-001 | Batch dedup not enforced at DB level | Documented |
| GAP-BATCH-002 | Response order critical for Loop | Documented |
| GAP-BATCH-003 | Deduplicated items must return all positions | Documented |

### Additional Observations

1. **API v3 is single-document only** - No true batch endpoint exists
2. **Loop uses v1 for batch** - May have different ordering guarantees
3. **AAPS avoids issue entirely** - Sequential single-doc uploads

---

## Source Files Reference

### Loop
- `externals/LoopWorkspace/NightscoutService/NightscoutServiceKit/ObjectIdCache.swift`
- `externals/LoopWorkspace/NightscoutService/NightscoutServiceKit/NightscoutService.swift:210-230`
- `externals/LoopWorkspace/NightscoutService/NightscoutServiceKit/Extensions/NightscoutUploader.swift`

### AAPS
- `externals/AndroidAPS/plugins/sync/src/main/kotlin/app/aaps/plugins/sync/nsclientV3/DataSyncSelectorV3.kt`
- `externals/AndroidAPS/plugins/sync/src/main/kotlin/app/aaps/plugins/sync/nsclientV3/NSClientV3Plugin.kt:654-710`
- `externals/AndroidAPS/core/nssdk/src/main/kotlin/app/aaps/core/nssdk/remotemodel/RemoteStatusResponse.kt`

### Nightscout
- `externals/cgm-remote-monitor/lib/api3/generic/create/operation.js`
- `externals/cgm-remote-monitor/lib/api3/generic/update/replace.js`
- `externals/cgm-remote-monitor/lib/api3/storage/mongoCollection/utils.js`

---

## Summary

| System | Batch Strategy | Order Sensitive | Dedup Handling |
|--------|---------------|-----------------|----------------|
| **Loop** | v1 array POST | ✅ Critical | syncIdentifier→objectId cache |
| **AAPS** | Sequential v3 | ❌ N/A | Direct ID assignment |
| **Trio** | Throttled pipeline | ⚠️ Moderate | Pipeline ordering |
| **Nightscout v3** | Single-doc only | ❌ N/A | `isDeduplication` flag |

**Key Recommendation**: Clients should parse `identifier` from response body rather than relying on positional matching. This eliminates order dependency entirely.
