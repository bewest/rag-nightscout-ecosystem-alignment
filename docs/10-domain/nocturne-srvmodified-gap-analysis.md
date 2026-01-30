# Nocturne srvModified Field Gap Analysis

> **OQ-010 Extended Item #17**: Analyze impact of missing srvModified in Nocturne

## Executive Summary

Nocturne implements `srvModified` differently than cgm-remote-monitor:
- **cgm-remote-monitor**: `srvModified` = server timestamp when record was last modified
- **Nocturne**: `srvModified` = alias for `Mills` (event timestamp, not modification time)

This difference has **limited practical impact** because:
1. Nocturne uses `SysUpdatedAt` for the `/api/v3/lastModified` endpoint
2. AAPS/Loop use the endpoint response, not per-record `srvModified`, for sync cursors
3. The per-record `srvModified` is primarily for individual record inspection

## Background

### V3 API srvModified Semantics

cgm-remote-monitor defines `srvModified` as:
> "The server's timestamp of the last document modification in the database (Unix epoch in ms)"

This field is used for:
1. **Incremental sync**: Clients poll `/api/v3/lastModified` to get collection timestamps
2. **Per-record tracking**: Each record includes when it was last modified server-side
3. **Conflict detection**: Compare srvModified to detect concurrent edits

### cgm-remote-monitor Implementation

**On Insert** (`lib/api3/generic/create/insert.js:25-26`):
```javascript
const now = new Date;
doc.srvModified = now.getTime();
doc.srvCreated = doc.srvModified;
```

**On Update** (`lib/api3/generic/update/replace.js:27-29`):
```javascript
const now = new Date;
doc.srvModified = now.getTime();
doc.srvCreated = storageDoc.srvCreated || doc.srvModified;
```

**LastModified Endpoint** (`lib/api3/specific/lastModified.js:16`):
```javascript
const lastModified = await col.storage.getLastModified('srvModified');
```

Key behavior: `srvModified` is updated to server current time on every modification.

## Nocturne Implementation Analysis

### Per-Record srvModified

Nocturne returns `srvModified` as an alias for `Mills`:

**Treatment.cs:30-31**:
```csharp
[JsonPropertyName("srvModified")]
public long? SrvModified => Mills > 0 ? Mills : null;
```

**EntryV3Response.cs:192-194**:
```csharp
[JsonPropertyName("srvModified")]
public long? SrvModified => _entry.Mills > 0 ? _entry.Mills : null;
```

**Impact**: Per-record `srvModified` reflects event time, not modification time.

### LastModified Endpoint

Nocturne's `/api/v3/lastModified` uses **`SysUpdatedAt`** not per-record `srvModified`:

**StatusService.cs:479-483**:
```csharp
var entriesTask = _dbContext
    .Entries.AsNoTracking()
    .OrderByDescending(e => e.SysUpdatedAt)
    .Select(e => (DateTime?)e.SysUpdatedAt)
    .FirstOrDefaultAsync();
```

`SysUpdatedAt` is a PostgreSQL system column that tracks actual modification time:

**EntryEntity.cs:214-215**:
```csharp
[Column("sys_updated_at")]
public DateTime SysUpdatedAt { get; set; } = DateTime.UtcNow;
```

**Impact**: The `/api/v3/lastModified` endpoint correctly returns server modification times.

## AAPS Sync Behavior

AAPS uses srvModified for incremental sync via the lastModified endpoint:

**LoadBgWorker.kt:48**:
```kotlin
else max(nsClientV3Plugin.lastLoadedSrvModified.collections.entries, dateUtil.now() - nsClientV3Plugin.maxAge)
```

**LoadLastModificationWorker.kt:25**:
```kotlin
val lm = nsAndroidClient.getLastModified()
```

AAPS stores and compares `lastLoadedSrvModified` to determine what to fetch. Since Nocturne's `/api/v3/lastModified` returns correct `SysUpdatedAt` values, incremental sync works correctly.

## Gap Impact Assessment

### What Works ✅

| Feature | Status | Reason |
|---------|--------|--------|
| Incremental sync | ✅ Works | `/lastModified` uses `SysUpdatedAt` |
| AAPS polling | ✅ Works | Uses endpoint, not per-record field |
| Loop polling | ✅ Works | Uses endpoint, not per-record field |
| New record detection | ✅ Works | `SysUpdatedAt` updated on insert |
| Updated record detection | ✅ Works | `SysUpdatedAt` updated on update |

### What's Different ⚠️

| Feature | cgm-remote-monitor | Nocturne | Impact |
|---------|-------------------|----------|--------|
| Per-record srvModified | Server modification time | Event time (Mills) | Low - rarely inspected directly |
| srvCreated | First modification time | Event time (Mills) | Low - informational only |
| Record inspection | Shows when server received edit | Shows when event occurred | Debugging only |

### Edge Cases 🔍

1. **Backdated entries**: If an entry is inserted with past `Mills`, cgm-remote-monitor's `srvModified` would be "now" while Nocturne's would be the past timestamp. This affects only per-record inspection, not sync.

2. **Edited records**: After editing, cgm-remote-monitor's `srvModified` updates; Nocturne's stays at original `Mills`. Again, sync works because `SysUpdatedAt` updates.

3. **Audit/debugging**: Nocturne lacks per-record "when was this actually modified" visibility.

## Remediation Options

### Option A: No Change (Recommended)

**Rationale**: Current implementation works for all sync use cases. The per-record `srvModified` semantic difference has minimal practical impact.

**Pros**:
- No code changes
- No migration complexity
- Sync already works correctly

**Cons**:
- Per-record audit trail different from cgm-remote-monitor

### Option B: Add Stored srvModified

Add actual `srv_modified` columns to entities:

```csharp
[Column("srv_modified")]
public DateTimeOffset? SrvModified { get; set; }
```

Update on every save:
```csharp
entity.SrvModified = DateTimeOffset.UtcNow;
```

Return in API:
```csharp
[JsonPropertyName("srvModified")]
public long? SrvModified => _srvModified?.ToUnixTimeMilliseconds();
```

**Pros**:
- Full V3 API compatibility
- Per-record audit trail

**Cons**:
- Schema migration
- Storage overhead (8 bytes per record × millions of records)
- Increases complexity

### Option C: Use SysUpdatedAt for srvModified

Return `SysUpdatedAt` as `srvModified`:

```csharp
[JsonPropertyName("srvModified")]
public long? SrvModified => SysUpdatedAt.ToUnixTimeMilliseconds();
```

**Pros**:
- Correct semantics
- No schema change
- Already tracked

**Cons**:
- Requires entity access in DTO layer
- May need mapper changes

## Recommendation

**Option A: No Change** is recommended because:

1. **Sync works correctly**: The `/api/v3/lastModified` endpoint returns proper modification times
2. **Low impact**: Per-record `srvModified` is rarely used directly by clients
3. **AAPS/Loop compatible**: Both use the endpoint, not per-record inspection
4. **Implementation overhead**: Options B/C add complexity for marginal benefit

If per-record audit is later required, Option C provides the cleanest path forward.

## Related Documentation

- **GAP-MIGRATION-001**: srvModified computed from Mills, not stored independently
- **GAP-SYNC-039**: Profile srvModified behavior differences

## Source Files Analyzed

### cgm-remote-monitor
- `lib/api3/generic/create/insert.js:25-26` - Insert sets srvModified
- `lib/api3/generic/update/replace.js:27-29` - Update sets srvModified
- `lib/api3/specific/lastModified.js` - LastModified endpoint

### Nocturne
- `src/Core/Nocturne.Core.Models/Treatment.cs:30-31` - srvModified = Mills
- `src/Core/Nocturne.Core.Models/Extensions/EntryResponseExtensions.cs:192-194`
- `src/API/Nocturne.API/Services/StatusService.cs:479-523` - lastModified uses SysUpdatedAt
- `src/Infrastructure/Nocturne.Infrastructure.Data/Entities/EntryEntity.cs:214-215`

### AAPS
- `plugins/sync/src/main/kotlin/app/aaps/plugins/sync/nsclientV3/workers/LoadBgWorker.kt:48`
- `plugins/sync/src/main/kotlin/app/aaps/plugins/sync/nsclientV3/workers/LoadLastModificationWorker.kt:25`
- `core/nssdk/src/main/kotlin/app/aaps/core/nssdk/localmodel/devicestatus/NSDeviceStatus.kt:19-20`

## Conclusion

Nocturne's `srvModified` implementation differs semantically from cgm-remote-monitor, but **the difference has no impact on sync functionality**. The `/api/v3/lastModified` endpoint correctly uses `SysUpdatedAt` for modification tracking, which is what AAPS and Loop rely on for incremental sync.

The per-record `srvModified` being an alias for `Mills` is a documentation/visibility difference, not a functional gap.

**Status**: Gap acknowledged, no remediation required.
