# API v3 Pagination Compliance

**Date:** 2026-01-29  
**Status:** Complete  
**Type:** Cross-project analysis

## Overview

Nightscout API v3 introduced `srvModified`-based pagination for efficient incremental sync. This document analyzes which clients implement API v3 pagination and identifies compliance gaps.

## Nightscout API v3 Pagination Mechanism

### Server Implementation

**Source:** `externals/cgm-remote-monitor/lib/api3/generic/history/operation.js`

The `/api/v3/{collection}/history` endpoint enables incremental sync:

1. Client sends `Last-Modified` header with timestamp of last sync
2. Server queries: `{ srvModified: { $gte: lastModified } }`
3. Server returns documents sorted by `srvModified` ascending
4. Response includes `Last-Modified` and `ETag` headers with max `srvModified`
5. Client stores this for next request

```javascript
// Server query (line 106)
{ field: 'srvModified', operator: 'gte', value: lastModified.getTime() }

// Response headers (lines 53-54)
res.setHeader('Last-Modified', (new Date(maxSrvModified)).toUTCString());
res.setHeader('ETag', 'W/"' + maxSrvModified + '"');
```

### Key Fields

| Field | Type | Description |
|-------|------|-------------|
| `srvModified` | Number | Server timestamp when record was last modified |
| `srvCreated` | Number | Server timestamp when record was created |
| `identifier` | String | Client-provided unique ID for deduplication |

### Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v3/entries/history` | GET | Incremental entries sync |
| `/api/v3/treatments/history` | GET | Incremental treatments sync |
| `/api/v3/devicestatus/history` | GET | Incremental devicestatus sync |
| `/api/v3/profile/history` | GET | Incremental profile sync |
| `/api/v3/lastModified` | GET | Get last modification times per collection |

---

## Client Compliance Matrix

| Client | API Version | Pagination Method | srvModified Support |
|--------|-------------|-------------------|---------------------|
| **AAPS** | v3 ✅ | srvModified | ✅ Full |
| **Loop** | v1 ❌ | None/count | ❌ Not implemented |
| **Trio** | v1 ❌ | count param | ❌ Not implemented |
| **xDrip+** | v1 ❌ | Last-Modified header | ⚠️ Partial (v1 style) |

---

## AAPS (Full v3 Compliance)

**Source:** `externals/AndroidAPS/plugins/sync/src/main/kotlin/app/aaps/plugins/sync/nsclientV3/`

AAPS is the **only** client with full API v3 support.

### Implementation Details

**NSClientV3Plugin** maintains `lastLoadedSrvModified` per collection:

```kotlin
// LoadBgWorker.kt:48
val lastLoaded = max(nsClientV3Plugin.lastLoadedSrvModified.collections.entries, 
                     dateUtil.now() - nsClientV3Plugin.maxAge)

// LoadBgWorker.kt:56
response.lastServerModified?.let { 
    nsClientV3Plugin.lastLoadedSrvModified.collections.entries = it 
}
```

### Workers

| Worker | Collection | Source |
|--------|------------|--------|
| `LoadBgWorker` | entries | `workers/LoadBgWorker.kt:48-79` |
| `LoadTreatmentsWorker` | treatments | `workers/LoadTreatmentsWorker.kt:42-75` |
| `LoadProfileStoreWorker` | profile | `workers/LoadProfileStoreWorker.kt:39-51` |
| `LoadDeviceStatusWorker` | devicestatus | `workers/LoadDeviceStatusWorker.kt` |

### Features
- ✅ Stores `srvModified` per collection
- ✅ Uses `/history` endpoint
- ✅ Respects `maxAge` setting
- ✅ Handles `lastServerModified` response header
- ✅ Fallback to `created_at` when `srvModified` missing

---

## Loop (No v3 Support)

**Source:** `externals/LoopWorkspace/NightscoutService/`

Loop uses API v1 exclusively.

### Current Implementation

```swift
// No API v3 endpoints used
// Uses /api/v1/entries.json, /api/v1/treatments.json
```

### Pagination
- Uses `count` parameter to limit results
- No incremental sync based on timestamps
- Re-fetches same data repeatedly

### GAP-API-010: Loop Missing API v3 Support

**Impact:** Increased server load, redundant data transfer, potential sync delays.

---

## Trio (No v3 Support)

**Source:** `externals/Trio/Trio/Sources/Services/Network/Nightscout/NightscoutAPI.swift:14-18`

```swift
private enum Config {
    static let entriesPath = "/api/v1/entries/sgv.json"
    static let uploadEntriesPath = "/api/v1/entries.json"
    static let treatmentsPath = "/api/v1/treatments.json"
    static let statusPath = "/api/v1/devicestatus.json"
    static let profilePath = "/api/v1/profile.json"
}
```

### Pagination
- Uses `count` parameter (line 74: `count=1600`)
- Uses `find[dateString][$gte]` for date filtering (line 77-79)
- No `srvModified` tracking

### GAP-API-011: Trio Missing API v3 Support

**Impact:** Same as Loop - no incremental sync capability.

---

## xDrip+ (Partial v1 Compliance)

**Source:** `externals/xDrip/app/src/main/java/com/eveningoutpost/dexdrip/utilitymodels/NightscoutUploader.java:410-437`

xDrip+ uses API v1 but implements `Last-Modified` header tracking:

```java
// Line 410-414
String last_modified_string = PersistentStore.getString(LAST_MODIFIED_KEY);
if (last_modified_string.equals(""))
    last_modified_string = JoH.getRFC822String(0);
r = nightscoutService.downloadTreatments(hashedSecret, last_modified_string).execute();

// Line 423
last_modified_string = r.raw().header("Last-Modified", JoH.getRFC822String(request_start));

// Line 437
PersistentStore.setString(LAST_MODIFIED_KEY, last_modified_string);
```

### Features
- ✅ Stores `Last-Modified` header
- ✅ Sends `If-Modified-Since` on subsequent requests
- ⚠️ Uses API v1 endpoints
- ❌ No `srvModified` field tracking
- ❌ No `/history` endpoint usage

### GAP-API-012: xDrip+ Using v1 Last-Modified Instead of v3 srvModified

**Impact:** Works but not optimal - v1 Last-Modified is per-request, not per-document.

---

## Gaps Identified

### GAP-API-010: Loop Missing API v3 Pagination

**Description:** Loop uses API v1 with no incremental sync. Re-fetches all data on each sync.

**Source:** `externals/LoopWorkspace/NightscoutService/`

**Impact:** 
- Higher server load
- Slower sync on poor connections
- Battery drain from redundant data transfer

**Remediation:** Migrate NightscoutServiceKit to use API v3 `/history` endpoints with `srvModified` tracking.

### GAP-API-011: Trio Missing API v3 Pagination

**Description:** Trio uses API v1 with count-based fetching. Uses date filtering but not server-side modification tracking.

**Source:** `externals/Trio/Trio/Sources/Services/Network/Nightscout/NightscoutAPI.swift:14-18`

**Impact:** Same as Loop.

**Remediation:** Add `srvModified` tracking and migrate to `/api/v3/{collection}/history` endpoints.

### GAP-API-012: xDrip+ Partial Pagination Compliance

**Description:** xDrip+ correctly uses `Last-Modified` header but with API v1 endpoints. This provides some sync efficiency but misses v3 benefits.

**Source:** `externals/xDrip/app/.../NightscoutUploader.java:410-437`

**Impact:** 
- Moderate efficiency gain over Loop/Trio
- Misses per-document `srvModified` precision
- HTTP 304 responses save bandwidth but not processing

**Remediation:** 
1. Add API v3 support as alternative
2. Track `srvModified` per document for precise sync

---

## Recommendations

### For Nightscout Server Team

1. **Document API v3 pagination** - Create migration guide for v1→v3
2. **Add deprecation notices** - Encourage clients to migrate
3. **Monitor v1 vs v3 usage** - Track adoption metrics

### For Client Teams

#### Loop/Trio (Swift)
```swift
// Recommended implementation pattern
class NightscoutV3Client {
    var lastSrvModified: [String: Int64] = [
        "entries": 0,
        "treatments": 0,
        "devicestatus": 0,
        "profile": 0
    ]
    
    func fetchHistory(collection: String) async throws -> [Document] {
        let url = baseURL.appendingPathComponent("/api/v3/\(collection)/history")
        var request = URLRequest(url: url)
        request.setValue(formatDate(lastSrvModified[collection]!), 
                        forHTTPHeaderField: "Last-Modified")
        
        let (data, response) = try await URLSession.shared.data(for: request)
        
        if let lastMod = (response as? HTTPURLResponse)?.value(forHTTPHeaderField: "Last-Modified") {
            lastSrvModified[collection] = parseDate(lastMod)
        }
        
        return try JSONDecoder().decode([Document].self, from: data)
    }
}
```

#### xDrip+ (Java)
```java
// Upgrade path: Add v3 support alongside v1
// Track srvModified per collection
private Map<String, Long> lastSrvModified = new HashMap<>();

// Use /api/v3/{collection}/history endpoints
// Parse srvModified from response documents
```

---

## Source File References

| Project | File | Lines |
|---------|------|-------|
| Nightscout | `lib/api3/generic/history/operation.js` | 1-130 |
| Nightscout | `lib/api3/generic/create/insert.js` | 25-26 |
| AAPS | `plugins/sync/.../LoadBgWorker.kt` | 48-79 |
| AAPS | `plugins/sync/.../LoadTreatmentsWorker.kt` | 42-75 |
| AAPS | `core/interfaces/.../NsClient.kt` | 49-67 |
| Trio | `Services/Network/Nightscout/NightscoutAPI.swift` | 14-18, 68-80 |
| xDrip+ | `utilitymodels/NightscoutUploader.java` | 410-437 |

---

## Related Documents

- `specs/openapi/aid-entries-2025.yaml` - Entries schema with srvModified
- `traceability/nightscout-api-gaps.md` - API-related gaps
- `docs/10-domain/sync-protocols-deep-dive.md` - Sync protocol details
