# nightscout-connect: Nightscout Sync Implementation

**Source**: `externals/nightscout-connect`  
**Verified**: 2026-01-20

## API Endpoints Used

### Reading (Source)

| Endpoint | Purpose | File:Line |
|----------|---------|-----------|
| `/api/v1/verifyauth` | Verify read permissions | `lib/sources/nightscout.js:40` |
| `/api/v2/authorization/subjects` | Create reader token | `lib/sources/nightscout.js:55` |
| `/api/v2/authorization/request/<token>` | Get JWT session | `lib/sources/nightscout.js:92` |
| `/api/v1/entries.json` | Fetch glucose entries | `lib/sources/nightscout.js:133` |

### Writing (Output)

| Endpoint | Purpose | File:Line |
|----------|---------|-----------|
| `POST /api/v1/entries.json` | Upload glucose entries | `lib/outputs/nightscout.js:35` |
| `POST /api/v1/treatments.json` | Upload treatments | `lib/outputs/nightscout.js:48` |

## Data Types Synced

Per `lib/outputs/nightscout.js:67-71`:

- `entries` (CGM glucose readings)
- `treatments`
- `profiles`
- `devicestatus`

## Sync Strategy

### Bookmark Tracking

The system tracks the last successful sync point:

```javascript
// lib/outputs/nightscout.js:56-62
bookmark.entries = timestamp  // Last known entry
```

### Gap Detection

- Uses two-day lookback window as fallback (`lib/sources/nightscout.js:127`)
- Query filter: `dateString: { $gt: last_glucose_at.toISOString() }`
- Only fetches newer data since last known entry

### Batch Processing

```javascript
// lib/outputs/nightscout.js:65-84
// Processes entries, treatments, profiles, devicestatus
// Uses Promise.all() for parallel glucose & treatment recording
```

## Deduplication

**No explicit client-side deduplication** - relies on:

1. Bookmark-based cursor prevents re-reading
2. Server-side duplicate detection
3. Timestamp-based filtering on queries

## Session Refresh

- TTL calculated from JWT: `(exp - iat) * 1000` milliseconds
- 28.8-hour refresh cycle (`lib/sources/nightscout.js:161-164`)

## Requirements Derived

| ID | Requirement | Source |
|----|-------------|--------|
| REQ-NC-001 | Must support API v1 for data access | Verified in code |
| REQ-NC-002 | Must support API v2 for token auth | Verified in code |
| REQ-NC-003 | Must track sync bookmark for incremental sync | Verified in code |
| REQ-NC-004 | Must handle JWT session refresh | Verified in code |

## Gaps Identified

| ID | Gap | Impact |
|----|-----|--------|
| GAP-NC-001 | No client-side deduplication | May upload duplicates if server dedup fails |
| GAP-NC-002 | No PUT/upsert support | Cannot update existing records |
