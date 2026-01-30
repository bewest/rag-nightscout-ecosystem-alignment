# Nocturne vs cgm-remote-monitor Profile Sync Comparison

> **OQ-010 Item #7**: Comparison of profile collection sync behavior between Nocturne and cgm-remote-monitor.

## Summary

| Aspect | Nocturne | cgm-remote-monitor |
|--------|----------|-------------------|
| **Database** | PostgreSQL | MongoDB |
| **Dedup Primary** | `Id` (GUID) or `OriginalId` | `identifier` field |
| **Dedup Fallback** | None (strict ID match) | `created_at` field |
| **srvModified** | Not on Profile model | Explicit field, auto-updated |
| **defaultProfile** | `"Default"` (default value) | `"Default"` (convention) |
| **Sort Order** | `Mills` descending | `startDate` descending |

## Deduplication Logic

### cgm-remote-monitor

**Source**: `lib/api3/generic/setup.js:65-73`, `lib/api3/storage/mongoCollection/utils.js:130-169`

Profile collection uses:
1. **Primary**: `identifier` field (V3 API standard)
2. **Fallback**: `created_at` field (for V1 API compatibility)

```javascript
// lib/api3/generic/setup.js:65-73
cols.profile = new Collection({
  colName: 'profile',
  storageColName: env.profile_collection || 'profile',
  fallbackGetDate: fallbackCreatedAt,
  dedupFallbackFields: ['created_at'],  // Fallback deduplication
  fallbackDateField: 'created_at'
});
```

The deduplication filter (`identifyingFilter`) creates an `$or` query:
1. Match by `identifier`
2. OR match by `_id` (if identifier looks like MongoDB ObjectId)
3. OR match by `created_at` (if `identifier` not present and API3_DEDUP_FALLBACK_ENABLED)

### Nocturne

**Source**: `src/Infrastructure/Nocturne.Infrastructure.Data/Repositories/ProfileRepository.cs:147-186`

Profile deduplication uses strict ID matching:
1. **Primary**: `Id` (GUID v7)
2. **Secondary**: `OriginalId` (preserved MongoDB ObjectId for migration)

```csharp
// ProfileRepository.cs:159-167
var existingEntity = await _context.Profiles.FirstOrDefaultAsync(
    p => p.Id == entity.Id
    || (!string.IsNullOrEmpty(entity.OriginalId) && p.OriginalId == entity.OriginalId),
    cancellationToken
);
```

**No fallback deduplication** - if neither `Id` nor `OriginalId` matches, a new profile is created.

### Divergence Impact

| Scenario | cgm-remote-monitor | Nocturne |
|----------|-------------------|----------|
| Upload without identifier | Creates, dedup by `created_at` | Creates new (no dedup) |
| Upload with same `created_at` | Updates existing (if no identifier) | Creates duplicate |
| MongoDB migration | N/A | Matches by `OriginalId` |

**GAP**: Nocturne lacks `created_at` fallback deduplication, potentially creating duplicates for V1 API uploads.

## srvModified Behavior

### cgm-remote-monitor

**Source**: `lib/api3/generic/collection.js:98-116`, `lib/api3/generic/update/replace.js:28-29`

`srvModified` is:
- Automatically set on create/update/delete
- Used for sync tracking (clients poll for changes since last `srvModified`)
- Stored as Unix timestamp (milliseconds)

```javascript
// lib/api3/generic/update/replace.js:28-29
doc.srvModified = now.getTime();
doc.srvCreated = storageDoc.srvCreated || doc.srvModified;
```

For profiles, if `srvModified` not present, falls back to `created_at` field.

### Nocturne

**Source**: `src/Core/Nocturne.Core.Models/Profile.cs`

Profile model does **not** have `srvModified` or `srvCreated` properties. Instead:
- Uses `Mills` field as timestamp
- Uses `CreatedAt` (ISO string) for creation time

For V3 API responses, Nocturne's entries/treatments compute `srvModified` from `Mills`, but Profile model lacks this.

### Divergence Impact

| Scenario | cgm-remote-monitor | Nocturne |
|----------|-------------------|----------|
| Profile update | `srvModified` updated | No `srvModified` field |
| Sync polling | Can filter by `srvModified$gt` | Must use `mills` or `startDate` |
| V3 history endpoint | Returns profiles by `srvModified` | May need different logic |

**GAP**: Nocturne Profile model lacks explicit `srvModified`, complicating sync workflows that rely on this field.

## defaultProfile Field

### Both Implementations

Both use `"Default"` as the conventional default profile name:

| Implementation | Default Value | Source |
|---------------|---------------|--------|
| cgm-remote-monitor | Convention (no default) | Document structure |
| Nocturne | `"Default"` | `Profile.cs:23` |

Nocturne explicitly defaults to `"Default"`:
```csharp
public string DefaultProfile { get; set; } = "Default";
```

**No divergence** - both treat `"Default"` as the standard profile name.

## Sort Order

### cgm-remote-monitor

Sorts by `startDate` descending:
```javascript
// lib/server/profile.js:37
return api().find({}).limit(limit).sort({startDate: -1}).toArray(fn);
```

### Nocturne

Sorts by `Mills` descending:
```csharp
// ProfileRepository.cs:33-35
var entities = await _context.Profiles
    .OrderByDescending(p => p.Mills)
    .ToListAsync(cancellationToken);
```

**Potential divergence**: If `startDate` and `Mills` represent different moments (e.g., `startDate` is future-dated), sort order could differ.

## V3 API Compatibility

### Endpoints

| Endpoint | cgm-remote-monitor | Nocturne |
|----------|-------------------|----------|
| `GET /api/v3/profile` | ✅ Implemented | ✅ Implemented |
| `GET /api/v3/profile/{id}` | ✅ Implemented | ✅ Implemented |
| `POST /api/v3/profile` | ✅ Implemented | ✅ Implemented |
| `PUT /api/v3/profile/{id}` | ✅ Implemented | ✅ Implemented |
| `DELETE /api/v3/profile/{id}` | ✅ Soft delete (isValid=false) | ✅ Hard delete |

### Delete Behavior

- **cgm-remote-monitor**: Soft delete - sets `isValid: false`, `srvModified: now`
- **Nocturne**: Hard delete - removes from database

**GAP**: Different delete semantics may affect sync clients expecting soft deletes.

## Gaps Identified

### GAP-SYNC-038: Profile Deduplication Fallback Missing

**Description**: Nocturne lacks `created_at` fallback deduplication for profiles, potentially creating duplicates for V1 API uploads without identifiers.

**Affected Systems**: Controllers uploading profiles via V1 API to Nocturne.

**Impact**: Duplicate profiles may accumulate.

**Remediation**: Add `created_at` fallback matching to Nocturne's `CreateProfilesAsync`.

### GAP-SYNC-039: Profile srvModified Field Missing

**Description**: Nocturne's Profile model lacks `srvModified` field, complicating V3 sync polling.

**Affected Systems**: Clients using `srvModified$gt` filter for profile sync.

**Impact**: Cannot efficiently poll for profile changes.

**Remediation**: Add `srvModified` property to Profile model, auto-update on save.

### GAP-SYNC-040: Profile Delete Semantics Differ

**Description**: cgm-remote-monitor uses soft delete (isValid=false); Nocturne uses hard delete.

**Affected Systems**: Sync clients expecting deleted profiles to remain visible with isValid=false.

**Impact**: Clients may not detect profile deletions.

**Remediation**: Implement soft delete in Nocturne with isValid field.

## Source Files Analyzed

| File | Description |
|------|-------------|
| `externals/cgm-remote-monitor/lib/server/profile.js` | V1 Profile storage |
| `externals/cgm-remote-monitor/lib/api3/generic/setup.js:65-73` | V3 Profile collection config |
| `externals/cgm-remote-monitor/lib/api3/storage/mongoCollection/utils.js:130-169` | Dedup logic |
| `externals/cgm-remote-monitor/lib/api3/generic/collection.js:98-116` | srvModified handling |
| `externals/nocturne/src/Core/Nocturne.Core.Models/Profile.cs` | Profile model |
| `externals/nocturne/src/Infrastructure/Nocturne.Infrastructure.Data/Repositories/ProfileRepository.cs` | Profile repository |
| `externals/nocturne/src/API/Nocturne.API/Controllers/V3/ProfileController.cs` | V3 API |

## Requirements

### REQ-SYNC-059: Profile Deduplication Consistency

**Statement**: Servers SHOULD implement consistent profile deduplication using both `identifier` and `created_at` fallback fields.

**Rationale**: Ensures V1 and V3 API uploads are deduplicated consistently across implementations.

**Verification**: Upload profile without identifier twice with same `created_at`; verify single profile exists.

**Gap**: GAP-SYNC-038

### REQ-SYNC-060: Profile srvModified Support

**Statement**: Servers SHOULD track `srvModified` timestamp on Profile documents for sync polling.

**Rationale**: Enables efficient incremental sync by clients.

**Verification**: Update profile; verify `srvModified` changes; query with `srvModified$gt` filter.

**Gap**: GAP-SYNC-039

### REQ-SYNC-061: Profile Soft Delete

**Statement**: Servers SHOULD implement soft delete for profiles (set `isValid: false`) rather than hard delete.

**Rationale**: Allows sync clients to detect deletions and remove local copies.

**Verification**: Delete profile; verify `isValid: false` and `srvModified` updated; verify still queryable.

**Gap**: GAP-SYNC-040

---

*Analysis Date: 2026-01-30*
*OQ-010 Research Queue: Item #7 of 7*
