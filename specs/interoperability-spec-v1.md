# Nightscout Ecosystem Interoperability Specification

**Version**: 1.0-draft
**Date**: 2026-01-29
**Status**: Draft for Review

This specification defines the minimal requirements for interoperability between applications in the Nightscout ecosystem. It synthesizes findings from comprehensive audits of cgm-remote-monitor and cross-project analysis.

---

## 1. Scope

This specification applies to:
- AID controllers uploading data (Loop, AAPS, Trio, OpenAPS)
- CGM data sources (xDrip+, xDrip4iOS, Dexcom Share bridge)
- Follower applications (Nightguard, LoopFollow, Nightwatch)
- Third-party integrations

### 1.1 Conformance Levels

| Level | Description | Requirements |
|-------|-------------|--------------|
| **Reader** | Read-only data access | Sections 2, 3, 4 |
| **Uploader** | Write glucose/treatments | Sections 2-6 |
| **Controller** | Full AID integration | All sections |

---

## 2. Data Collections

### 2.1 Core Collections

| Collection | Purpose | Required Fields |
|------------|---------|-----------------|
| `entries` | Glucose readings | `type`, `sgv`/`mbg`, `date`, `dateString` |
| `treatments` | Boluses, carbs, events | `eventType`, `created_at` |
| `devicestatus` | Controller state | `device`, `created_at` |
| `profile` | Therapy settings | `defaultProfile`, `store` |

### 2.2 Entries Schema

```json
{
  "type": "sgv",
  "sgv": 120,
  "direction": "Flat",
  "date": 1706500000000,
  "dateString": "2026-01-29T01:00:00.000Z",
  "device": "xDrip-DexcomG6"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | ✓ | `sgv`, `mbg`, `cal` |
| `sgv` | integer | ✓ (if sgv) | Sensor glucose (mg/dL) |
| `mbg` | integer | ✓ (if mbg) | Meter glucose (mg/dL) |
| `date` | integer | ✓ | Unix timestamp (ms) |
| `dateString` | string | ✓ | ISO 8601 timestamp |
| `direction` | string | | Trend arrow code |
| `device` | string | | Source device identifier |

### 2.3 Treatments Schema

```json
{
  "eventType": "Correction Bolus",
  "insulin": 2.5,
  "created_at": "2026-01-29T01:00:00.000Z",
  "enteredBy": "Loop",
  "notes": ""
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `eventType` | string | ✓ | Treatment type (see §2.4) |
| `created_at` | string | ✓ | ISO 8601 timestamp |
| `insulin` | number | | Units delivered |
| `carbs` | number | | Grams consumed |
| `duration` | number | | Duration in minutes |
| `enteredBy` | string | | Source identifier |

### 2.4 Standard eventTypes

| eventType | Purpose | Key Fields |
|-----------|---------|------------|
| `Correction Bolus` | Correction insulin | `insulin` |
| `Meal Bolus` | Meal insulin | `insulin`, `carbs` |
| `Carb Correction` | Carbs only | `carbs` |
| `Temp Basal` | Temporary rate | `percent` or `absolute`, `duration` |
| `Temporary Target` | BG target override | `targetTop`, `targetBottom`, `duration` |
| `Profile Switch` | Profile change | `profile`, `duration` |
| `Note` | Annotation | `notes` |
| `Exercise` | Activity | `duration` |
| `Site Change` | Infusion site | - |
| `Sensor Start` | CGM sensor | - |

### 2.5 DeviceStatus Schema

DeviceStatus structure varies by controller. Applications MUST handle both formats.

**Loop Format:**
```json
{
  "device": "loop://iPhone",
  "created_at": "2026-01-29T01:00:00.000Z",
  "loop": {
    "iob": { "iob": 2.5 },
    "cob": { "cob": 25 },
    "predicted": { "values": [120, 118, 115, ...] },
    "enacted": { "rate": 0.5, "duration": 30 }
  }
}
```

**OpenAPS/AAPS Format:**
```json
{
  "device": "openaps://phone",
  "created_at": "2026-01-29T01:00:00.000Z",
  "openaps": {
    "iob": [{ "iob": 2.5 }],
    "suggested": { "bg": 120, "COB": 25 },
    "enacted": { "rate": 0.5, "duration": 30, "received": true }
  },
  "pump": { "reservoir": 150, "battery": { "percent": 80 } }
}
```

---

## 3. API Compatibility

### 3.1 Supported API Versions

| Version | Status | Use Case |
|---------|--------|----------|
| v1 | Active | Loop, Trio, xDrip+, most clients |
| v3 | Active | AAPS, new integrations |

### 3.2 Endpoint Patterns

**API v1:**
```
GET  /api/v1/entries.json?count=10&find[date][$gte]=...
POST /api/v1/entries
GET  /api/v1/treatments.json
POST /api/v1/treatments
```

**API v3:**
```
GET  /api/v3/entries?limit=10&date$gte=...
POST /api/v3/entries
GET  /api/v3/treatments
POST /api/v3/treatments
GET  /api/v3/entries/history/{lastModified}
```

### 3.3 Content Types

- Request: `application/json`
- Response: `application/json` (default), `text/csv`, `text/tab-separated-values`

---

## 4. Authentication

### 4.1 Methods

| Method | Header/Param | Grants | API Version |
|--------|--------------|--------|-------------|
| API Secret | `api-secret` header | Full admin | v1, v2 |
| JWT Token | `Authorization: Bearer` | Per-role | v3 |
| Access Token | `?token=` query | Per-role | v3 |

### 4.2 Permission Strings

Format: `domain:resource:action`

| Permission | Description |
|------------|-------------|
| `api:entries:read` | Read glucose data |
| `api:entries:create` | Upload glucose data |
| `api:treatments:read` | Read treatments |
| `api:treatments:create` | Create treatments |
| `api:devicestatus:create` | Upload controller status |
| `*` | Full admin access |

### 4.3 Default Roles

| Role | Permissions | Use Case |
|------|-------------|----------|
| `readable` | `*:*:read` | Read-only follower |
| `devicestatus-upload` | `api:devicestatus:create` | CGM uploader |
| `careportal` | `api:treatments:create` | Treatment entry |

---

## 5. Sync Identity

### 5.1 Identifier Generation

API v3 clients MUST generate identifiers using UUID v5:

```
identifier = uuidv5(NIGHTSCOUT_NAMESPACE, "${device}|${date}|${eventType}")
```

### 5.2 Deduplication Keys

| Collection | Primary Key | Fallback Keys |
|------------|-------------|---------------|
| entries | `identifier` | `date` + `type` |
| treatments | `identifier` | `created_at` + `eventType` |
| devicestatus | `identifier` | `created_at` + `device` |

### 5.3 UPSERT Semantics

- Matching identifier: Document replaced (not rejected)
- No identifier match: New document inserted
- Conflict resolution: Last-write-wins

---

## 6. Real-Time Updates

### 6.1 Socket.IO Connection

```javascript
const socket = io.connect(nightscoutUrl, {
  transports: ["polling", "websocket"]
});

socket.on('connect', () => {
  socket.emit('authorize', { secret: apiSecret }, (response) => {
    if (response.success) {
      // Authorized - will receive dataUpdate events
    }
  });
});
```

### 6.2 Events

| Event | Direction | Payload |
|-------|-----------|---------|
| `authorize` | Client→Server | `{ secret }` or `{ token }` |
| `dataUpdate` | Server→Client | Delta with sgvs, treatments, etc. |
| `connected` | Server→Client | Authorization success |

### 6.3 Namespaces

| Namespace | Purpose |
|-----------|---------|
| `/` | Main data updates |
| `/alarm` | Alarm notifications |
| `/storage` | Collection CRUD events |

---

## 7. Compatibility Requirements

### 7.1 MUST Requirements

1. **Timestamps**: Use ISO 8601 format for string dates, Unix ms for numeric
2. **eventType**: Use standard eventType values from §2.4
3. **device**: Include device identifier for source tracking
4. **created_at**: Always provide on treatments and devicestatus
5. **Error handling**: Handle 401 (unauthorized), 422 (validation), 5xx (server error)

### 7.2 SHOULD Requirements

1. **Sync identity**: Generate UUID v5 identifiers for v3 API
2. **Delta updates**: Use Socket.IO for real-time instead of polling
3. **Rate limiting**: Respect 429 responses, implement exponential backoff
4. **Compression**: Accept gzip/deflate responses

### 7.3 MAY Requirements

1. **Offline caching**: Cache recent data for offline viewing
2. **Background sync**: Sync data when connectivity returns
3. **Conflict detection**: Detect and report sync conflicts

---

## 8. Gap Summary

Known interoperability gaps to address:

| ID | Issue | Impact |
|----|-------|--------|
| GAP-API-006 | No OpenAPI spec for v1 | Integration difficulty |
| GAP-SYNC-008 | No conflict resolution | Data loss risk |
| GAP-SYNC-009 | v1 lacks identifier | Duplicate risk |
| GAP-AUTH-003 | API_SECRET = full admin | Security concern |
| GAP-PLUGIN-002 | Prediction format mismatch | Display inconsistency |

---

## 9. Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0-draft | 2026-01-29 | Initial draft from audit synthesis |

---

## References

- [Nightscout Integration Guide](../30-design/nightscout-integration-guide.md)
- [API Deep Dive](../10-domain/cgm-remote-monitor-api-deep-dive.md)
- [Sync Deep Dive](../10-domain/cgm-remote-monitor-sync-deep-dive.md)
- [Auth Deep Dive](../10-domain/cgm-remote-monitor-auth-deep-dive.md)
- [OpenAPI Specs](../../specs/openapi/)
