# Nocturne Deletion Semantics Analysis

> **OQ-010 Extended Item #18**: Document soft-delete vs hard-delete behavior differences

## Executive Summary

Nocturne uses **hard delete** (removes records from database) while cgm-remote-monitor uses **soft delete** (sets `isValid: false`). This difference affects:

1. **Sync detection**: Clients can't detect deletions via `isValid` filtering
2. **Audit trail**: No record of what was deleted
3. **Undo capability**: Deleted data cannot be recovered

**Impact Assessment**: Moderate for sync clients that rely on `isValid=false` pattern.

## Background

### cgm-remote-monitor Delete Behavior

cgm-remote-monitor supports two delete modes via V3 API:

**Soft Delete (Default)** - `DELETE /api/v3/treatments/:id`

```javascript
// lib/api3/generic/delete/operation.js:75-86
async function markAsDeleted (opCtx) {
  const setFields = { 'isValid': false, 'srvModified': (new Date).getTime() };
  if (auth && auth.subject && auth.subject.name) {
    setFields.modifiedBy = auth.subject.name;
  }
  const result = await col.storage.updateOne(identifier, setFields);
  // ...
}
```

**Permanent Delete** - `DELETE /api/v3/treatments/:id?permanent=true`

```javascript
// lib/api3/generic/delete/operation.js:54-72
async function deletePermanently (opCtx) {
  const result = await col.storage.deleteOne(identifier);
  // ...
}
```

### Key Behaviors

| Aspect | Soft Delete | Permanent Delete |
|--------|-------------|------------------|
| Record exists | Yes | No |
| `isValid` | `false` | N/A |
| `srvModified` | Updated to now | N/A |
| History endpoint | Visible | Not visible |
| Recoverable | Yes (set isValid=true) | No |

### History Endpoint for Sync

cgm-remote-monitor's history endpoint includes soft-deleted records:

```javascript
// lib/api3/generic/history/operation.js:24-36
let onlyValid = false  // Include isValid=false records
const result = await col.storage.findMany({
  filter, sort, limit, skip, projection,
  onlyValid,  // Critical for sync clients
  logicalOperator
});
```

This allows sync clients to:
1. Fetch all changes since last sync (including deletions)
2. Detect `isValid=false` records
3. Remove corresponding local records

## Nocturne Implementation

### Hard Delete Only

Nocturne always performs hard delete:

```csharp
// TreatmentRepository.cs:256-258
_context.Treatments.Remove(entity);
var result = await _context.SaveChangesAsync(cancellationToken);
return result > 0;
```

### No isValid Field

Nocturne's Treatment model lacks `isValid`:

```csharp
// Treatment.cs - No isValid property defined
public class Treatment : ProcessableDocumentBase
{
    public string? Id { get; set; }
    public string? Identifier => Id;
    public long? SrvModified => Mills > 0 ? Mills : null;
    // ... no isValid
}
```

### No History Endpoint

Nocturne doesn't implement the `/api/v3/{collection}/history` endpoint for deleted record tracking.

## AAPS Sync Behavior

AAPS expects `isValid` field from Nightscout V3:

```kotlin
// RemoteTreatment.kt:30
@SerializedName("isValid") val isValid: Boolean? = null,
// boolean A flag set by the server only for deleted documents.
// This field appears only within history operation and for 
// documents which were deleted by API v3 (and they always have false value)
```

### How AAPS Handles Deletions

1. Polls `/api/v3/treatments/history` with `lastModified` header
2. Receives records with `isValid: false`
3. Marks corresponding local records as invalid/deleted
4. Removes from active treatment list

### Impact on AAPS ↔ Nocturne Sync

| Scenario | cgm-remote-monitor | Nocturne |
|----------|-------------------|----------|
| Treatment deleted on server | AAPS sees `isValid=false`, removes locally | AAPS doesn't detect deletion |
| Treatment deleted locally by AAPS | Server soft-deletes | Server hard-deletes |
| Historical deletions query | Works via history endpoint | No history endpoint |

## Gap Impact Assessment

### What Breaks ❌

1. **Deletion propagation**: Clients can't detect server-side deletions
2. **Audit trail**: No record of who deleted what when
3. **Undo/recovery**: Accidentally deleted data is lost
4. **Compliance**: May not meet data retention requirements

### What Works ✅

1. **Delete operation**: Records are removed as expected
2. **API compatibility**: DELETE endpoint returns 204 as expected
3. **Normal sync**: New/updated records sync correctly
4. **Local deletions**: AAPS can still delete from Nocturne

### Edge Cases 🔍

1. **Conflicting edits**: User A edits while User B deletes
   - cgm-remote-monitor: Edit wins (isValid=false ignored)
   - Nocturne: Delete wins (record gone)

2. **Sync gap**: Client offline during deletion
   - cgm-remote-monitor: Client detects on next sync via history
   - Nocturne: Client never learns about deletion

3. **Multi-device sync**: Delete on one device
   - cgm-remote-monitor: Other devices see isValid=false
   - Nocturne: Other devices keep stale local copy

## Remediation Options

### Option A: Add isValid Field (Recommended)

Implement soft delete pattern:

```csharp
// TreatmentEntity.cs
[Column("is_valid")]
public bool IsValid { get; set; } = true;

// TreatmentRepository.cs - Change delete to soft delete
public async Task<bool> DeleteTreatmentAsync(string id, ...)
{
    entity.IsValid = false;
    entity.SysUpdatedAt = DateTime.UtcNow;
    await _context.SaveChangesAsync(cancellationToken);
    return true;
}
```

**Pros**:
- Full V3 API compatibility
- Audit trail preserved
- Undo possible
- AAPS sync works correctly

**Cons**:
- Schema migration required
- Query complexity (filter isValid=true)
- Storage grows (deleted records retained)

### Option B: Implement History Endpoint

Add `/api/v3/{collection}/history` that tracks deletions:

```csharp
// Create deletion_log table
CREATE TABLE deletion_log (
    id UUID PRIMARY KEY,
    collection VARCHAR(50),
    original_id VARCHAR(100),
    deleted_at TIMESTAMP,
    deleted_by VARCHAR(200)
);
```

**Pros**:
- Tracks deletions without soft delete overhead
- Can be pruned periodically
- Less query complexity

**Cons**:
- Additional table to maintain
- Doesn't support undo
- History endpoint implementation effort

### Option C: Document Limitation

Accept hard delete behavior and document:

1. Add to API documentation
2. Update sync clients to handle missing records
3. Recommend periodic full sync for deletion detection

**Pros**:
- No code changes
- Simple

**Cons**:
- AAPS sync may have stale data
- Poor user experience for multi-device scenarios

## Recommendation

**Option A (Soft Delete)** is recommended because:

1. **V3 parity**: Matches cgm-remote-monitor behavior
2. **AAPS compatibility**: Sync works as expected
3. **Audit trail**: Important for medical data
4. **Undo support**: Users can recover mistakes

### Migration Path

1. Add `is_valid` column with default `true`
2. Modify delete operations to set `is_valid = false`
3. Add `is_valid = true` filter to normal queries
4. Implement history endpoint for deleted records
5. Optional: Add prune job to hard-delete old soft-deleted records

## Related Documentation

- **GAP-SYNC-040**: Profile delete semantics differ
- [Profile Sync Comparison](./nocturne-cgm-remote-monitor-profile-sync.md)
- [srvModified Gap Analysis](./nocturne-srvmodified-gap-analysis.md)

## Source Files Analyzed

### cgm-remote-monitor
- `lib/api3/generic/delete/operation.js` - Soft/permanent delete logic
- `lib/api3/generic/history/operation.js` - History with isValid=false
- `lib/api3/storage/mongoCollection/utils.js` - isValid filtering

### Nocturne
- `src/Infrastructure/Nocturne.Infrastructure.Data/Repositories/TreatmentRepository.cs:234-259`
- `src/API/Nocturne.API/Controllers/V3/TreatmentsController.cs:359-398`
- `src/Core/Nocturne.Core.Models/Treatment.cs` - No isValid field

### AAPS
- `core/nssdk/src/main/kotlin/app/aaps/core/nssdk/remotemodel/RemoteTreatment.kt:30`

## Conclusion

Nocturne's hard delete behavior is a **functional gap** that affects sync clients relying on V3's `isValid` pattern. While delete operations work correctly, the inability to detect deletions during incremental sync can cause data inconsistencies across devices.

**Recommended action**: Implement soft delete with `isValid` field to achieve V3 parity.

**Status**: Gap confirmed, remediation recommended.
