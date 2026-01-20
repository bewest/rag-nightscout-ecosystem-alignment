# cgm-remote-monitor: API Versions

**Source**: `externals/cgm-remote-monitor` (wip/bewest/mongodb-5x)  
**Verified**: 2026-01-20

## API Version Comparison

| Feature | v1 | v2 | v3 |
|---------|----|----|-----|
| **Data Access** | ✅ | ❌ | ✅ |
| **Authorization** | ✅ | ✅ | ✅ |
| **Identifier Field** | `_id` | N/A | `identifier` |
| **History Endpoint** | ❌ | ❌ | ✅ |
| **srvModified Tracking** | ❌ | ❌ | ✅ |
| **Dedup Fields** | created_at+eventType | N/A | identifier (fallback to v1) |

## v1 API Endpoints

### Entries
| Method | Endpoint | Purpose | File:Line |
|--------|----------|---------|-----------|
| GET | `/api/v1/entries.json` | Fetch entries | `lib/api/entries/index.js` |
| POST | `/api/v1/entries.json` | Create entries | `lib/api/entries/index.js:268` |

### Treatments
| Method | Endpoint | Purpose | File:Line |
|--------|----------|---------|-----------|
| GET | `/api/v1/treatments.json` | Fetch treatments | `lib/api/treatments/index.js` |
| POST | `/api/v1/treatments.json` | Create treatments | `lib/api/treatments/index.js:142` |
| PUT | `/api/v1/treatments.json` | Update treatment | `lib/api/treatments/index.js` |
| DELETE | `/api/v1/treatments/:id` | Delete treatment | `lib/api/treatments/index.js` |

### Other Collections
- `/api/v1/devicestatus.json` - Device status
- `/api/v1/profile.json` - Profiles
- `/api/v1/status.json` - Server status

## v2 API (Authorization Only)

| Method | Endpoint | Purpose | File:Line |
|--------|----------|---------|-----------|
| GET | `/api/v2/authorization/request/:accessToken` | Get JWT | `lib/authorization/endpoints.js:21-29` |
| GET | `/api/v2/authorization/subjects` | List subjects | `lib/authorization/endpoints.js:39-43` |
| POST | `/api/v2/authorization/subjects` | Create subject | `lib/authorization/endpoints.js:45-53` |
| PUT | `/api/v2/authorization/subjects` | Update subject | `lib/authorization/endpoints.js:55-63` |
| DELETE | `/api/v2/authorization/subjects/:_id` | Delete subject | `lib/authorization/endpoints.js:65-73` |

## v3 API Endpoints

Per `lib/api3/generic/collection.js:42-72`:

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/v3/{collection}` | Search |
| POST | `/api/v3/{collection}` | Create (upsert) |
| GET | `/api/v3/{collection}/history` | Sync history |
| GET | `/api/v3/{collection}/{identifier}` | Read one |
| PUT | `/api/v3/{collection}/{identifier}` | Update (upsert) |
| PATCH | `/api/v3/{collection}/{identifier}` | Patch (no upsert) |
| DELETE | `/api/v3/{collection}/{identifier}` | Soft delete |

### v3 Key Differences

1. **Identifier vs _id**: v3 uses `identifier` field (UUID), with fallback to MongoDB `_id`
2. **srvModified**: Server-side timestamp for sync tracking
3. **History endpoint**: Returns changes since last sync point
4. **Soft deletes**: `isValid: false` instead of hard delete

## Deduplication by API Version

### v1 Deduplication

Per `lib/server/entries.js:111-120`:
```javascript
// Entries: sysTime + type
var query = { sysTime: doc.sysTime, type: doc.type };
updateOne: { filter: query, update: { $set: doc }, upsert: true }
```

Per `lib/server/treatments.js:54-58`:
```javascript
// Treatments: created_at + eventType
replaceOne: { filter: { created_at, eventType }, replacement: obj, upsert: true }
```

### v3 Deduplication

Per `lib/api3/storage/mongoCollection/utils.js:130-169`:

**Priority Order:**
1. Match exact `identifier` field
2. Fallback to `_id` if identifier looks like ObjectId
3. Fallback to collection-specific fields (if enabled)

**Fallback Fields per Collection** (`lib/api3/generic/setup.js`):
- `devicestatus`: `created_at`, `device`
- `entries`: `date`, `type`
- `treatments`: `created_at`, `eventType`
- `profile`: `created_at`

## Requirements Derived

| ID | Requirement | Source |
|----|-------------|--------|
| REQ-NS-API-001 | v1 API must remain stable for legacy clients | All clients use v1 |
| REQ-NS-API-002 | v3 must support identifier-based dedup | AAPS uses v3 |
| REQ-NS-API-003 | v3 must fallback to v1 dedup fields | Backward compat |
| REQ-NS-API-004 | History endpoint must track srvModified | Sync efficiency |
