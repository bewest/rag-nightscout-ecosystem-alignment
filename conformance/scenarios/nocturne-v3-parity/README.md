# Nocturne V3 API Behavioral Parity Test Scenarios

> **OQ-010 Extended API #6**  
> **Date**: 2026-01-30  
> **Purpose**: Compare V3 API behavior between cgm-remote-monitor and Nocturne

## Executive Summary

This analysis compares the V3 API implementations between cgm-remote-monitor (reference)
and Nocturne (alternative). Key findings:

| Feature | cgm-remote-monitor | Nocturne | Parity |
|---------|-------------------|----------|--------|
| Query Parameters | ✅ Full | ✅ Full | ✅ |
| Filter Operators | 9 operators | 9 operators | ✅ |
| History Endpoint | ✅ `/history/{ts}` | ❌ Missing | ⚠️ **GAP** |
| ETag (search) | Disabled | SHA256 hash | ⚠️ Different |
| ETag (history) | `W/"srvModified"` | N/A | ⚠️ **GAP** |
| 304 Not Modified | ✅ If-Modified-Since | ✅ Both headers | ✅ |
| Pagination Headers | None | X-Total-Count, Link | ✅ Enhanced |
| Error Format | `{status, message}` | `{status, message}` | ✅ |
| Soft Delete (410 GONE) | ✅ isValid=false | ❌ Hard delete | ⚠️ **GAP** |

## Critical Gap: Missing History Endpoint

### cgm-remote-monitor

```
GET /api/v3/{collection}/history/{lastModified}
GET /api/v3/{collection}/history (with Last-Modified header)
```

Returns all records modified since `lastModified` timestamp, sorted by `srvModified`.
Essential for incremental sync by AAPS, Loop, and other clients.

**Response Headers:**
- `Last-Modified`: UTC timestamp of max srvModified
- `ETag`: `W/"srvModified"` weak ETag

### Nocturne

**No equivalent endpoint exists.**

Clients must use standard search with `srvModified$gte` filter, which lacks:
- Automatic `srvModified` sorting
- Proper weak ETag generation
- Inclusion of soft-deleted records (`isValid=false`)

**Impact**: High - AAPS/Loop sync relies on this endpoint

**Related Gap**: GAP-SYNC-041 (new)

---

## Query Parameter Comparison

### Supported Parameters

| Parameter | cgm-remote-monitor | Nocturne | Notes |
|-----------|-------------------|----------|-------|
| `limit` | Default 10, max 1000 | Default 100, max 1000 | Different defaults |
| `skip` | Offset alias | Offset alias | ✅ Identical |
| `offset` | ❌ Not supported | ✅ Supported | Nocturne adds |
| `sort` | Ascending | Ascending | ✅ Identical |
| `sort$desc` | Descending | Descending | ✅ Identical |
| `fields` | Field projection | Field projection | ✅ Identical |
| `token` | Auth token | Auth token | ✅ Identical |

### Filter Operators

Both support identical operators:

| Operator | Meaning | Example |
|----------|---------|---------|
| `eq` | Equals (default) | `type=sgv` |
| `ne` | Not equals | `type$ne=mbg` |
| `gt` | Greater than | `date$gt=1234567890` |
| `gte` | Greater or equal | `date$gte=1234567890` |
| `lt` | Less than | `date$lt=1234567890` |
| `lte` | Less or equal | `date$lte=1234567890` |
| `in` | In array | `type$in=sgv,mbg` |
| `nin` | Not in array | `type$nin=cal` |
| `re` | Regex match | `device$re=dexcom` |

### Date Field Parsing

Both auto-convert date fields to milliseconds:
- `date`
- `srvModified`
- `srvCreated`
- `created_at`

**Source References:**
- cgm-remote-monitor: `lib/api3/generic/search/input.js:31-43`
- Nocturne: `Controllers/V3/BaseV3Controller.cs:195-198`

---

## ETag and Conditional Request Handling

### cgm-remote-monitor

**Search Endpoint:**
- ETag disabled at app level: `app.set('etag', false)`
- No ETag header on search responses

**Read Endpoint:**
- `Last-Modified` header set from `srvModified`
- Checks `If-Modified-Since` only
- Returns 304 if document unchanged

**History Endpoint:**
- `ETag: W/"<maxSrvModified>"` (weak ETag)
- `Last-Modified` from max srvModified in result set

### Nocturne

**All V3 Endpoints:**
- `ETag: "<SHA256-16-chars>"` (strong ETag from response hash)
- Checks both `If-None-Match` and `If-Modified-Since`
- Additional headers: `Cache-Control`, `Vary`

**Behavioral Difference:**
- cgm-remote-monitor uses timestamp-based weak ETags
- Nocturne uses content-hash strong ETags
- Both support 304 responses but with different mechanisms

**Source References:**
- cgm-remote-monitor: `lib/api3/generic/history/operation.js:53-54`
- Nocturne: `Controllers/V3/BaseV3Controller.cs:243-249`

---

## Response Format Comparison

### Success Response

Both use identical structure:
```json
{
  "status": 200,
  "result": [/* data array */]
}
```

### Nocturne Enhancements

Nocturne adds pagination metadata:
```json
{
  "status": 200,
  "result": [/* data */],
  "meta": {
    "totalCount": 150,
    "limit": 100,
    "offset": 0
  }
}
```

Plus pagination headers:
- `X-Total-Count`
- `X-Limit`
- `X-Offset`
- `Link: <url>; rel="next"`

### Error Response

Both use identical structure:
```json
{
  "status": 400,
  "message": "Error description"
}
```

---

## Soft Delete Handling

### cgm-remote-monitor

Soft delete sets `isValid: false`:
```javascript
// lib/api3/generic/delete/operation.js:75-86
const setFields = { 'isValid': false, 'srvModified': (new Date).getTime() };
```

Read endpoint returns **410 GONE** for soft-deleted documents.

History endpoint includes soft-deleted records for sync.

### Nocturne

Hard delete removes record:
```csharp
// TreatmentRepository.cs:256
_context.Treatments.Remove(entity);
```

No 410 GONE support - returns 404 NOT FOUND.

**Impact**: Clients cannot detect server-side deletions.

**Related Gap**: GAP-SYNC-040 (already documented)

---

## Test Scenarios

See individual scenario files in this directory:

| File | Scenario | Status |
|------|----------|--------|
| `query-parameters.yaml` | Parameter parsing | ⏳ |
| `filter-operators.yaml` | Filter operator behavior | ⏳ |
| `etag-handling.yaml` | ETag/304 responses | ⏳ |
| `history-endpoint.yaml` | History sync (cgm-remote-monitor only) | ⏳ |
| `error-responses.yaml` | Error format consistency | ⏳ |
| `soft-delete.yaml` | Delete behavior differences | ⏳ |

---

## Gaps Identified

### GAP-SYNC-041: Missing V3 History Endpoint in Nocturne

**Description**: Nocturne does not implement the `/api/v3/{collection}/history/{lastModified}`
endpoint that AAPS and Loop use for incremental sync.

**Impact**: High - clients must use workaround query with `srvModified$gte` filter.

**Remediation**:
1. Implement `/api/v3/{collection}/history` endpoint
2. Include soft-deleted records (`isValid=false`)
3. Set `Last-Modified` and weak `ETag` headers

### GAP-API-010: Default Limit Mismatch

**Description**: cgm-remote-monitor defaults to `limit=10`, Nocturne defaults to `limit=100`.

**Impact**: Low - clients typically specify explicit limit.

**Remediation**: Document difference, consider aligning defaults.

### GAP-API-011: ETag Generation Strategy Difference

**Description**: cgm-remote-monitor uses timestamp-based weak ETags, Nocturne uses content-hash strong ETags.

**Impact**: Low - both support conditional requests correctly.

**Remediation**: None required if behavior is consistent.

---

## Source File References

### cgm-remote-monitor

| File | Purpose |
|------|---------|
| `lib/api3/index.js` | V3 API setup and routing |
| `lib/api3/generic/search/input.js` | Query parameter parsing |
| `lib/api3/generic/search/operation.js` | Search implementation |
| `lib/api3/generic/history/operation.js` | History/sync endpoint |
| `lib/api3/generic/read/operation.js` | Single document read |
| `lib/api3/generic/delete/operation.js` | Soft delete |
| `lib/api3/specific/lastModified.js` | LastModified endpoint |
| `lib/api3/const.json` | HTTP status codes |

### Nocturne

| File | Purpose |
|------|---------|
| `Controllers/V3/BaseV3Controller.cs` | Base V3 functionality |
| `Controllers/V3/EntriesController.cs` | Entries endpoint |
| `Controllers/V3/TreatmentsController.cs` | Treatments endpoint |
| `Controllers/V3/DeviceStatusController.cs` | DeviceStatus endpoint |
| `Controllers/V3/LastModifiedController.cs` | LastModified endpoint |
| `Services/StatusService.cs` | LastModified queries |

---

## Recommendations

### High Priority

1. **Implement History Endpoint**: Critical for AAPS/Loop sync compatibility
2. **Add Soft Delete Support**: Implement `isValid` field and 410 GONE responses

### Medium Priority

3. **Document API Differences**: Create migration guide for clients
4. **Align Default Limits**: Consider standardizing on 100 or 10

### Low Priority

5. **Standardize ETag Strategy**: Document which approach is preferred
