# V4 API Client Implementation Guide

> **Cycle**: 69  
> **Date**: 2026-01-31  
> **Status**: Complete  
> **Backlog Item**: nightscout-api.md #25 (Phase 1: Documentation)

## Overview

This guide documents how clients should implement support for the Nocturne V4 API extension while maintaining compatibility with cgm-remote-monitor.

## Key Constraint

**V4 is Nocturne-only.** The cgm-remote-monitor Node.js implementation does NOT support V4 endpoints. Clients MUST:

1. Feature-detect V4 availability
2. Gracefully fallback to V3 when V4 is unavailable
3. NOT require V4 for core functionality

## Feature Detection

### Recommended Pattern

```swift
// Swift example (NightscoutKit)
func detectApiVersion() async -> ApiVersion {
    // Check V4 first
    if let v4 = try? await GET("/api/v4/version") {
        return .v4(server: v4.server)
    }
    
    // Check V3
    if let v3 = try? await GET("/api/v3/version") {
        return .v3
    }
    
    // Fallback to V1
    return .v1
}

enum ApiVersion {
    case v1
    case v3
    case v4(server: String)
    
    var supportsStateSpans: Bool {
        if case .v4 = self { return true }
        return false
    }
}
```

### HTTP Request

```http
GET /api/v4/version HTTP/1.1
Host: {nightscout-site}
api-secret: {sha1-hash}
```

**Responses:**

| Status | Meaning | Server |
|--------|---------|--------|
| 200 | V4 available | Nocturne |
| 404 | V4 not available | cgm-remote-monitor |
| 401 | Unauthorized | Either |

## StateSpan Integration

### When to Use StateSpans

StateSpans provide time-ranged state queries that are not available in V3:

| Use Case | V4 Endpoint | V3 Workaround |
|----------|-------------|---------------|
| Profile at time T | `GET /api/v4/state-spans/profiles?from=T` | Query treatments for Profile Switch |
| Override history | `GET /api/v4/state-spans/overrides` | Query treatments eventType=Override |
| Pump mode history | `GET /api/v4/state-spans?category=PumpMode` | Parse devicestatus loop.enacted |

### Query Examples

**Get active profile at specific time:**
```http
GET /api/v4/state-spans/profiles?from=2026-01-31T10:00:00Z&to=2026-01-31T10:01:00Z
```

**Get all overrides in date range:**
```http
GET /api/v4/state-spans/overrides?from=2026-01-01&to=2026-01-31&limit=100
```

### StateSpan Data Model

```typescript
interface StateSpan {
  id: string;           // UUID
  category: StateSpanCategory;
  startTime: string;    // ISO 8601
  endTime?: string;     // null if ongoing
  state: object;        // Category-specific
  source?: string;      // Loop, AAPS, Trio, etc.
  srvCreated: string;
  srvModified: string;
}

type StateSpanCategory = 
  | 'Profile'
  | 'Override'
  | 'TempBasal'
  | 'PumpMode'
  | 'PumpConnectivity'
  | 'Sleep'
  | 'Exercise'
  | 'Illness'
  | 'Travel';
```

## ChartData Integration

### When to Use ChartData

Use `/api/v4/chart-data` for visualization when:
- Displaying glucose/IOB/COB charts
- Need pre-aggregated data (reduces client processing)
- Want consistent resolution across data types

### V3 Alternative

For cgm-remote-monitor, aggregate client-side from:
- `GET /api/v3/entries?find[date][$gte]=...`
- `GET /api/v3/devicestatus?find[created_at][$gte]=...`

## Sync Compatibility

### Soft Delete Handling

**Problem:** Nocturne uses hard delete; cgm-remote-monitor uses soft delete.

**Client Pattern:**
```swift
func syncDeletions(since: Date) async {
    if apiVersion.supportsV3History {
        // cgm-remote-monitor: use history endpoint
        let deleted = await GET("/api/v3/treatments/history/\(since.epochMs)")
        for item in deleted where item.isDeactivated {
            localDb.markDeleted(item.identifier)
        }
    } else {
        // Nocturne: full sync required for deletions
        // Compare local vs remote, mark missing as deleted
    }
}
```

### srvModified Semantics

| Server | srvModified Behavior |
|--------|---------------------|
| cgm-remote-monitor | Server timestamp when modified |
| Nocturne | Alias for `date` field (client timestamp) |

**Recommendation:** Use `srvCreated` for sync when targeting both servers.

## Authentication

Both V3 and V4 use identical authentication:

| Method | Header/Query | Value |
|--------|--------------|-------|
| API Secret | `api-secret` header | SHA1 hash of secret |
| JWT Token | `Authorization: Bearer` | JWT from /api/v2/authorization/request |
| Access Token | `?token=` query | `{name}-{hash}` format |

## Implementation Checklist

### Required (All Clients)

- [ ] Feature-detect V4 via `/api/v4/version`
- [ ] Fallback gracefully to V3 when V4 unavailable
- [ ] Use V3 for core CRUD operations (guaranteed available)

### Optional (V4-Aware Clients)

- [ ] Use StateSpans for profile/override history when available
- [ ] Use ChartData for optimized visualization when available
- [ ] Handle soft delete differences in sync logic

### Testing Matrix

| Test | cgm-remote-monitor | Nocturne |
|------|-------------------|----------|
| V4 detection returns false/true | ✅ 404 | ✅ 200 |
| V3 CRUD works | ✅ | ✅ |
| StateSpan query | ❌ Skip | ✅ Test |
| Fallback on V4 failure | ✅ Test | N/A |

## Gap References

| Gap ID | Description | Status |
|--------|-------------|--------|
| GAP-V4-001 | StateSpan API not standardized | Documented as extension |
| GAP-V4-002 | Profile activation history | Available in V4 |
| GAP-SYNC-040 | Delete semantics differ | Document workaround |
| GAP-SYNC-041 | History endpoint missing in Nocturne | Document workaround |

## Related Documents

- `specs/openapi/nocturne-v4-extension.yaml` - OpenAPI spec
- `docs/sdqctl-proposals/nightscout-v4-integration-proposal.md` - Full proposal
- `docs/sdqctl-proposals/statespan-standardization-proposal.md` - StateSpan design
- `mapping/nightscout/data-collections.md` - V4 mapping section
