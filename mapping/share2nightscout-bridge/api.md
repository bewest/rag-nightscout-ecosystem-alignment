# Dexcom Share API Reference

> **Source**: `externals/share2nightscout-bridge/index.js`  
> **Last Updated**: 2026-01-29

Documentation of Dexcom Share API endpoints used by share2nightscout-bridge.

---

## Server Endpoints

| Region | Server | Usage |
|--------|--------|-------|
| **US** | `share2.dexcom.com` | North America |
| **EU** | `shareous1.dexcom.com` | Europe, International |

**Configuration**: Set `BRIDGE_SERVER=EU` for European accounts.

---

## Authentication Flow

### Step 1: Authenticate Publisher Account

**Endpoint**: `POST /ShareWebServices/Services/General/AuthenticatePublisherAccount`

**Request**:
```json
{
  "accountName": "user@example.com",
  "password": "secret",
  "applicationId": "d89443d2-327c-4a6f-89e5-496bbb0317db"
}
```

**Response**: `"account-guid-here"` (string)

**Notes**:
- Returns `accountId` GUID
- Application ID is hardcoded (GAP-SHARE-003)

### Step 2: Login by Account ID

**Endpoint**: `POST /ShareWebServices/Services/General/LoginPublisherAccountById`

**Request**:
```json
{
  "accountId": "account-guid-here",
  "password": "secret",
  "applicationId": "d89443d2-327c-4a6f-89e5-496bbb0317db"
}
```

**Response**: `"session-guid-here"` (string)

**Notes**:
- Returns `sessionId` GUID
- Session reused until expiration
- Auto-refresh on 401 response

---

## Data Fetch

### Read Latest Glucose Values

**Endpoint**: `POST /ShareWebServices/Services/Publisher/ReadPublisherLatestGlucoseValues`

**Query Parameters**:
| Parameter | Default | Description |
|-----------|---------|-------------|
| `sessionID` | (required) | Session GUID from login |
| `minutes` | 1440 | Time window (24 hours) |
| `maxCount` | 1 | Maximum records to return |

**Response**:
```json
[
  {
    "DT": "/Date(1426292016000-0700)/",
    "ST": "/Date(1426295616000)/",
    "Trend": 4,
    "Value": 101,
    "WT": "/Date(1426292039000)/"
  }
]
```

---

## Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `DT` | string | Display Time (local timezone) |
| `ST` | string | System Time (UTC) |
| `WT` | string | Wall Time (used for entry date) |
| `Value` | number | Glucose value (mg/dL) |
| `Trend` | number | Trend direction (0-9) |

### Timestamp Format

Dexcom uses a proprietary date format:
```
/Date(milliseconds-offset)/
```

Examples:
- `/Date(1426292016000-0700)/` = Epoch ms with Pacific timezone offset
- `/Date(1426295616000)/` = Epoch ms (UTC, no offset)

**Parsing**:
```javascript
var regex = /\((.*)\)/;
var timestamp = parseInt(dateString.match(regex)[1]);
```

---

## Trend Values

| Trend | Value | Description |
|-------|-------|-------------|
| NONE | 0 | No trend data |
| DoubleUp | 1 | Rising quickly (>3 mg/dL/min) |
| SingleUp | 2 | Rising (2-3 mg/dL/min) |
| FortyFiveUp | 3 | Rising slowly (1-2 mg/dL/min) |
| Flat | 4 | Stable (<1 mg/dL/min) |
| FortyFiveDown | 5 | Falling slowly |
| SingleDown | 6 | Falling |
| DoubleDown | 7 | Falling quickly |
| NOT COMPUTABLE | 8 | Cannot calculate |
| RATE OUT OF RANGE | 9 | Rate exceeds limits |

---

## Error Handling

| HTTP Code | Meaning | Action |
|-----------|---------|--------|
| 200 | Success | Process data |
| 400 | Bad Request | Check parameters |
| 401 | Unauthorized | Refresh session |
| 500 | Server Error | Retry with backoff |

**Retry Logic**:
- `maxFailures` (default: 3) consecutive failures before exit
- Auto-refresh session on 401

---

## Application ID

```javascript
applicationId: "d89443d2-327c-4a6f-89e5-496bbb0317db"
```

⚠️ **GAP-SHARE-003**: This is a hardcoded Dexcom application ID. If Dexcom revokes or changes this ID, the bridge will break.

---

## Comparison: share2nightscout-bridge vs Nocturne

| Aspect | share2nightscout-bridge | Nocturne Dexcom |
|--------|------------------------|-----------------|
| Auth | Share API (publisher) | Share API |
| Language | JavaScript | C# |
| Session Management | Simple retry | Polly policies |
| Error Handling | Exit after maxFailures | Aspire restart |
| Multi-account | ❌ No | ✅ Yes |

---

## Cross-References

- [Nocturne Dexcom Connector](../nocturne/connectors.md)
- [share2nightscout-bridge Deep Dive](../../docs/10-domain/share2nightscout-bridge-deep-dive.md)
