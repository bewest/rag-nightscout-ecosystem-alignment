# Nightscout Integration Guide for App Developers

This guide provides practical guidance for developers building applications that integrate with Nightscout—whether consuming data, uploading from AID controllers, or building companion apps.

---

## Overview

Nightscout is an open-source remote CGM monitoring system that serves as a central data hub for diabetes management. It stores glucose readings, treatments (boluses, carbs, temp basals), device status from AID controllers, and therapy profiles.

**Key Insight:** Nightscout has evolved organically with contributions from multiple AID projects. This means conventions vary, and understanding these patterns is essential for reliable integration.

---

## API Versions: v1 vs v3

Nightscout maintains two parallel API versions. Your choice affects authentication, sync patterns, and feature availability.

| Aspect | API v1 | API v3 |
|--------|--------|--------|
| **Base Path** | `/api/v1/` | `/api/v3/` |
| **Current Users** | Loop, Trio, xDrip+, OpenAPS | AAPS (exclusive) |
| **Authentication** | SHA1-hashed API_SECRET header | JWT Bearer token |
| **Document Identity** | `_id` (MongoDB ObjectId) | `identifier` (client-provided) |
| **Sync Method** | Poll with date filters | Incremental history endpoint |
| **Deletion Detection** | Not supported | Supported via `isValid: false` |
| **Specification** | Informal, convention-based | OpenAPI 3.0 documented |

### Recommendation

- **New integrations:** Consider API v3 for better sync semantics and deletion support (see [API Comparison](../10-domain/nightscout-api-comparison.md) for details on history endpoints and `isValid` deletion tracking)
- **iOS ecosystem compatibility:** Use API v1 (Loop/Trio don't support v3)
- **Android/AAPS compatibility:** API v3 works natively

**Ecosystem Note:** API v1 remains dominant in the ecosystem today. Most CGM apps, followers, and iOS AID controllers use v1. If you need broad compatibility across controllers, v1 is the safer choice despite its limitations.

---

## Core Data Collections

### entries

Glucose readings from CGM sensors.

```json
{
  "_id": "507f1f77bcf86cd799439011",
  "type": "sgv",
  "sgv": 120,
  "direction": "Flat",
  "device": "xDrip-DexcomG6",
  "dateString": "2026-01-17T10:30:00.000Z",
  "date": 1737110200000
}
```

**Key Fields:**
- `sgv`: Glucose value in mg/dL
- `direction`: Trend arrow (Flat, FortyFiveUp, SingleUp, etc.)
- `device`: Source identifier (free-form, not standardized)

### treatments

User interventions and AID controller actions.

```json
{
  "_id": "507f1f77bcf86cd799439012",
  "eventType": "Correction Bolus",
  "insulin": 2.5,
  "created_at": "2026-01-17T10:35:00.000Z",
  "enteredBy": "Loop",
  "syncIdentifier": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Common Event Types:**
- `Correction Bolus`, `Meal Bolus`, `SMB`
- `Carb Correction`, `Meal`
- `Temp Basal`, `Temp Basal Start`, `Temp Basal End`
- `Temporary Override`, `Exercise`, `Announcement`

### devicestatus

AID controller state snapshots.

```json
{
  "device": "loop://iPhone",
  "created_at": "2026-01-17T10:40:00.000Z",
  "loop": {
    "iob": { "iob": 2.35, "timestamp": "..." },
    "cob": { "cob": 45.0 },
    "predicted": { "values": [120, 125, 130, ...] },
    "enacted": { "rate": 1.2, "duration": 30 }
  }
}
```

**Note:** Structure varies by controller:
- Loop: `devicestatus.loop`
- AAPS/Trio: `devicestatus.openaps` with separate prediction arrays

### profile

Therapy settings (basal rates, ISF, carb ratios, targets).

---

## Identity and Deduplication

**Critical Issue:** No unified sync identity field exists across AID controllers.

| Controller | Identity Field | Location | Notes |
|------------|----------------|----------|-------|
| Trio | `enteredBy: "Trio"` | treatments | Simple string, not verified |
| Loop | `syncIdentifier` | treatments | UUID per record |
| AAPS | `identifier` | API v3 field | Composite key strategy |
| xDrip+ | `uuid` | treatments | Client-generated UUID |

### Deduplication Strategies

**As a Data Consumer:**
1. Track documents by `_id` (v1) or `identifier` (v3)
2. For v1: Use `srvModified` to detect updates (if available)
3. Expect duplicates—build idempotent processing

**As a Data Producer:**
1. Include a stable `syncIdentifier` or `identifier` for all uploads
2. Use PUT for updates (not POST) when possible
3. Set `enteredBy` to identify your application

### The `enteredBy` Problem

The `enteredBy` field is **unverified**—any client can claim any identity. This means:
- You cannot trust `enteredBy` for authorization decisions
- Use it for display/filtering only, not security
- Future OIDC-based identity may replace this

---

## Sync Patterns

### Polling (API v1)

```javascript
// Fetch treatments since last sync
const params = new URLSearchParams({
  'find[created_at][$gte]': lastSyncTime.toISOString(),
  'count': '1000'
});

const response = await fetch(`${baseUrl}/api/v1/treatments.json?${params}`, {
  headers: { 'api-secret': sha1(apiSecret) }
});
```

**Limitations:**
- Cannot detect deletions
- Must poll periodically (typically 1-5 minutes)
- No notification of changes

### Incremental History (API v3)

```javascript
// Fetch changes since last sync
const response = await fetch(
  `${baseUrl}/api/v3/treatments/history/${lastModified}`,
  { headers: { 'Authorization': `Bearer ${token}` } }
);

// Response includes deleted documents with isValid: false
```

**Advantages:**
- Efficient incremental sync
- Deletion detection via `isValid: false`
- Granular JWT permissions

---

## Authentication

### API v1: API_SECRET

```javascript
const crypto = require('crypto');
const apiSecretHash = crypto.createHash('sha1')
  .update(apiSecret)
  .digest('hex');

const headers = {
  'api-secret': apiSecretHash,
  'Content-Type': 'application/json'
};
```

**Security Note:** API_SECRET provides all-or-nothing access. Anyone with the secret has full read/write access.

### API v3: JWT Bearer Token

```javascript
const headers = {
  'Authorization': `Bearer ${accessToken}`,
  'Content-Type': 'application/json'
};
```

JWT tokens can include granular Shiro-style permissions:
- `api:treatments:read`
- `api:treatments:create`
- `api:entries:read`

---

## Common Pitfalls

### 1. Unit Mismatches

| Data | Loop/Trio | AAPS | Nightscout |
|------|-----------|------|------------|
| Absorption time | Seconds | Minutes | Minutes |
| Duration | Seconds | Milliseconds | Minutes |
| Glucose | mg/dL | Configurable | mg/dL (stored) |

**Always convert explicitly—don't assume units.**

### 2. POST Creates Duplicates

Loop and Trio use POST (not PUT) for uploads. Network retries can create duplicate treatments.

**Mitigation:** 
- Query for existing record by `syncIdentifier` before inserting
- Implement server-side dedup if you control the Nightscout instance

### 3. Missing Deletion Handling

API v1 cannot detect when another client deletes a record. Your cached data may become stale.

**Mitigation:**
- Periodic full resync (e.g., daily)
- Accept that deletions may not propagate

### 4. Override Lifecycle Not Tracked

When an override is superseded by a new one, Nightscout doesn't track this relationship. You cannot reliably query "what override was active at time T."

### 5. Algorithm Parameters Not Synced

AID controllers don't upload their configuration (insulin model, safety limits). You cannot determine why different systems made different decisions from Nightscout data alone.

---

## Best Practices

### For Data Consumers

1. **Build idempotent processors** — expect duplicates
2. **Track by `_id`** — this is the stable document identifier
3. **Handle missing fields gracefully** — schema is loosely enforced
4. **Cache aggressively** — but implement periodic full resync
5. **Don't trust `enteredBy`** — it's unverified

### For Data Producers

1. **Always include `syncIdentifier`** — enables deduplication
2. **Set `enteredBy` consistently** — identifies your app
3. **Use UTC timestamps** — `created_at` should be ISO 8601 UTC
4. **Prefer PUT for updates** — avoids duplicates (API v3)
5. **Upload atomically** — don't leave partial state

### For AID Controller Developers

1. **Document your sync identity strategy** — help the ecosystem understand your patterns
2. **Consider uploading lifecycle events** — override supersession, treatment edits
3. **Include algorithm metadata** — insulin model, version, key parameters
4. **Test multi-controller scenarios** — verify deduplication works

---

## Integration Checklist

- [ ] Decide on API version (v1 for broad compatibility, v3 for better sync)
- [ ] Implement authentication (API_SECRET or JWT)
- [ ] Handle unit conversions explicitly
- [ ] Design idempotent data processing
- [ ] Include sync identifiers in uploads
- [ ] Plan for missing deletion detection (v1)
- [ ] Test with real AID controller data
- [ ] Document your identity strategy

---

## Related Documentation

- [Nightscout API Comparison](../10-domain/nightscout-api-comparison.md)
- [AID Controller Sync Patterns](../../mapping/cross-project/aid-controller-sync-patterns.md)
- [Data Collections Mapping](../../mapping/nightscout/data-collections.md)
- [Known Gaps](../../traceability/gaps.md)

---

## Open Questions

1. Should new integrations adopt API v3 exclusively, or maintain v1 compatibility?
2. How should consumers handle the lack of deletion detection in v1?
3. What's the recommended approach for multi-controller environments?

---

## Next Steps

- [ ] Add code examples for common integration patterns (Python, JavaScript, Swift)
- [ ] Document WebSocket real-time subscription (API v3)
- [ ] Create troubleshooting guide for common sync issues
- [ ] Add guidance for Nightscout Roles Gateway (NRG) integration
- [ ] Gather feedback from app developers on missing topics

---

## Revision History

| Date | Author | Changes |
|------|--------|---------|
| 2026-01-17 | Agent | Initial draft based on cross-project analysis |
