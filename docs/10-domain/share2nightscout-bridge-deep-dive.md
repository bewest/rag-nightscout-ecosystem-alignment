# share2nightscout-bridge Deep Dive

> **Source**: `externals/share2nightscout-bridge/`  
> **Version**: dev @ a40d6a4 (v0.2.10)  
> **Last Updated**: 2026-01-28

The share2nightscout-bridge copies CGM data from Dexcom Share web services to a Nightscout website. It's a simple Node.js daemon that polls Dexcom's API and uploads entries to Nightscout.

---

## Overview

| Metric | Value |
|--------|-------|
| **Language** | JavaScript (Node.js) |
| **Main File** | `index.js` (447 lines) |
| **Dependencies** | `request` only |
| **License** | GPL-3.0 |
| **Deployment** | Heroku, Azure, standalone |

---

## Architecture

```
┌─────────────────┐     ┌────────────────────┐     ┌─────────────────┐
│  Dexcom Share   │────▶│ share2nightscout   │────▶│   Nightscout    │
│  Web Services   │     │     bridge         │     │   REST API      │
└─────────────────┘     └────────────────────┘     └─────────────────┘
        │                        │                         │
   Share API               Poll loop                  POST entries
  (auth + fetch)         (2.5 min default)          /api/v1/entries
```

---

## Dexcom Share API

### Endpoints

| Purpose | URL | Method |
|---------|-----|--------|
| **Auth** | `https://share2.dexcom.com/ShareWebServices/Services/General/AuthenticatePublisherAccount` | POST |
| **Login** | `https://share2.dexcom.com/ShareWebServices/Services/General/LoginPublisherAccountById` | POST |
| **Fetch** | `https://share2.dexcom.com/ShareWebServices/Services/Publisher/ReadPublisherLatestGlucoseValues` | POST |

### Servers

| Region | Server |
|--------|--------|
| **US** | `share2.dexcom.com` |
| **EU** | `shareous1.dexcom.com` |

**Source**: `index.js:30-38`

### Application ID

```javascript
applicationId: "d89443d2-327c-4a6f-89e5-496bbb0317db"
```

This is a hardcoded Dexcom application identifier used for all auth requests.

---

## Authentication Flow

**Source**: `index.js:116-175`

```
1. AuthenticatePublisherAccount
   Request: { accountName, password, applicationId }
   Response: accountId (GUID)

2. LoginPublisherAccountById
   Request: { accountId, password, applicationId }
   Response: sessionID (GUID)

3. Use sessionID for subsequent fetch requests
   - Reused until expiration
   - Auto-refresh on 401/failure
```

### Auth Payload

```javascript
{
  "password": opts.password,
  "applicationId": "d89443d2-327c-4a6f-89e5-496bbb0317db",
  "accountName": opts.accountName
}
```

### Session Management

- Session ID reused every poll cycle
- Auto-refresh on expiration
- `maxFailures` (default: 3) consecutive failures before exit

---

## Data Fetch

**Source**: `index.js:177-198`

### Request

```
POST /ShareWebServices/Services/Publisher/ReadPublisherLatestGlucoseValues
    ?sessionID={guid}&minutes=1440&maxCount=1
```

### Response (Dexcom Format)

```javascript
[{
  DT: '/Date(1426292016000-0700)/',  // Display Time (local)
  ST: '/Date(1426295616000)/',       // System Time (UTC)
  Trend: 4,                          // Direction enum
  Value: 101,                        // mg/dL
  WT: '/Date(1426292039000)/'        // Wall Time (used for entry date)
}]
```

### Trend Mapping

**Source**: `index.js:56-66`

| Dexcom Trend | Value | Nightscout Direction |
|--------------|-------|---------------------|
| NONE | 0 | None |
| DoubleUp | 1 | DoubleUp |
| SingleUp | 2 | SingleUp |
| FortyFiveUp | 3 | FortyFiveUp |
| Flat | 4 | Flat |
| FortyFiveDown | 5 | FortyFiveDown |
| SingleDown | 6 | SingleDown |
| DoubleDown | 7 | DoubleDown |
| NOT COMPUTABLE | 8 | NOT COMPUTABLE |
| RATE OUT OF RANGE | 9 | RATE OUT OF RANGE |

---

## Data Transformation

**Source**: `index.js:226-247`

### Dexcom → Nightscout Entry

```javascript
function dex_to_entry(d) {
  var regex = /\((.*)\)/;
  var wall = parseInt(d.WT.match(regex)[1]);  // Extract timestamp
  var date = new Date(wall);
  var trend = matchTrend(d.Trend);
  
  return {
    sgv: d.Value,                    // Sensor glucose value
    date: wall,                      // Unix timestamp (ms)
    dateString: date.toISOString(),  // ISO-8601
    trend: trend,                    // Numeric trend
    direction: trendToDirection(trend), // String direction
    device: 'share2',                // Device identifier
    type: 'sgv'                      // Entry type
  };
}
```

### Output Schema

| Field | Type | Description |
|-------|------|-------------|
| `sgv` | number | Glucose value (mg/dL) |
| `date` | number | Unix timestamp (ms) |
| `dateString` | string | ISO-8601 timestamp |
| `trend` | number | Numeric trend (0-9) |
| `direction` | string | Trend arrow name |
| `device` | string | Always `"share2"` |
| `type` | string | Always `"sgv"` |

---

## Nightscout Upload

**Source**: `index.js:249-263`

### Endpoint

```
POST /api/v1/entries.json
```

### Authentication

Uses SHA1 hash of `API_SECRET`:

```javascript
var shasum = crypto.createHash('sha1');
shasum.update(opts.API_SECRET);
headers['api-secret'] = shasum.digest('hex');
```

### Battery Status

Also sends device status to hide battery indicator:

```
POST /api/v1/devicestatus.json
Body: { uploaderBattery: false }
```

---

## Configuration

### Required Environment Variables

| Variable | Description |
|----------|-------------|
| `API_SECRET` | Nightscout API secret (min 12 chars) |
| `DEXCOM_ACCOUNT_NAME` | Dexcom Share username |
| `DEXCOM_PASSWORD` | Dexcom Share password |
| `WEBSITE_HOSTNAME` | Nightscout hostname |

### Optional Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SHARE_INTERVAL` | 150000 | Poll interval (ms) - 2.5 min |
| `maxCount` | 1 | Records per fetch |
| `minutes` | 1440 | Time window (24 hours) |
| `firstFetchCount` | 3 | Records on first fetch |
| `maxFailures` | 3 | Max consecutive failures |
| `NS` | from hostname | Full Nightscout URL |
| `BRIDGE_SERVER` | share2.dexcom.com | Dexcom server (or `EU`) |

---

## Engine Loop

**Source**: `index.js:291-350`

```javascript
function engine(opts) {
  function my() {
    if (my.sessionID) {
      fetch(fetch_opts, function(err, res, glucose) {
        if (res.statusCode < 400) {
          to_nightscout(glucose);
        } else {
          refresh_token();
        }
      });
    } else {
      refresh_token();
    }
  }
  // ...
  return my;
}

// Run every SHARE_INTERVAL ms
setInterval(engine(meta), interval);
```

---

## Comparison: share2nightscout-bridge vs Nocturne Dexcom Connector

| Aspect | share2nightscout-bridge | Nocturne Dexcom |
|--------|------------------------|-----------------|
| **Language** | JavaScript | C# |
| **Auth** | Share API (publisher) | Share API (likely similar) |
| **Database** | Via Nightscout API | Direct PostgreSQL |
| **Deployment** | Standalone daemon | Aspire-managed service |
| **Trend Handling** | Manual mapping | Native enum |
| **Error Handling** | Simple retry + exit | Health checks, Aspire restart |

---

## Ecosystem Implications

### Integration Points

1. **Nightscout API v1** - Uses `/api/v1/entries.json` only
2. **No v3 support** - Does not use identifier, srvModified, etc.
3. **Device identifier** - Always `"share2"` (useful for filtering)

### Gaps Identified

| Gap ID | Description |
|--------|-------------|
| GAP-SHARE-001 | No Nightscout API v3 support |
| GAP-SHARE-002 | No backfill/gap detection logic |
| GAP-SHARE-003 | Hardcoded application ID may break |

### Opportunities

1. **API v3 migration** - Add identifier, use v3 endpoints
2. **Gap detection** - Check for missing readings, backfill
3. **Multi-sensor** - Support multiple Dexcom accounts

---

## Key Source Files

| Purpose | Path |
|---------|------|
| Main code | `index.js` |
| Auth test | `tests/authorize.test.js` |
| Fetch test | `tests/fetch.test.js` |
| Package | `package.json` |

---

## Cross-References

- [Nocturne Deep Dive](nocturne-deep-dive.md) - Native Dexcom connector comparison
- [Entries Deep Dive](entries-deep-dive.md) - Entry schema details
- [CGM Data Sources](cgm-data-sources-deep-dive.md) - All CGM sources

---

## Next Steps

1. **Compare with xDrip+ Dexcom Share** - Similar functionality in Java
2. **API v3 migration proposal** - Modern Nightscout integration
3. **Gap detection design** - Handle missed readings
