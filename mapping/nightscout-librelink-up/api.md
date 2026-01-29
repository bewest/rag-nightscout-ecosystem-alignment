# LibreLink Up API

> **Source**: `externals/nightscout-librelink-up/src/`  
> **Base URL**: `https://api-{region}.libreview.io`

## Overview

LibreLink Up is Abbott's cloud service for sharing CGM data. nightscout-librelink-up uses the unofficial API to fetch glucose readings.

---

## API Regions

| Region Code | Base URL | Coverage |
|-------------|----------|----------|
| `EU` | `api-eu.libreview.io` | Europe (default) |
| `EU2` | `api-eu2.libreview.io` | Europe (alternate) |
| `US` | `api-us.libreview.io` | United States |
| `AU` | `api-au.libreview.io` | Australia |
| `DE` | `api-de.libreview.io` | Germany |
| `FR` | `api-fr.libreview.io` | France |
| `JP` | `api-jp.libreview.io` | Japan |
| `AP` | `api-ap.libreview.io` | Asia Pacific |

**Source**: `src/constants/regions.ts`

---

## Authentication

### Login Endpoint

**Endpoint**: `POST /llu/auth/login`

**Headers**:
```
Content-Type: application/json
product: llu.android
version: 4.7.0
Accept-Encoding: gzip
```

**Request**:
```json
{
  "email": "user@example.com",
  "password": "password"
}
```

**Response** (`LoginResponse`):
```typescript
interface LoginResponse {
  status: number;
  data: {
    user: User;
    authTicket: AuthTicket;
    messages: any;
    notifications: any;
  };
}

interface AuthTicket {
  token: string;      // JWT token
  expires: number;    // Unix timestamp
  duration: number;   // Validity in seconds
}
```

**Source**: `src/interfaces/librelink/login-response.ts`

### Stealth Mode

The client uses techniques to avoid Cloudflare blocking:

| Technique | Implementation |
|-----------|----------------|
| **SSL Ciphers** | Custom cipher suite ordering |
| **Headers** | SHA-256 hashed account-id |
| **User-Agent** | Mimics official Android app |
| **Cookies** | Automatic cookie handling |

---

## Endpoints

### Get Connections (Patients)

**Endpoint**: `GET /llu/connections`

**Headers**:
```
Authorization: Bearer {token}
```

**Response** (`ConnectionsResponse`):
```typescript
interface ConnectionsResponse {
  status: number;
  data: Connection[];
}

interface Connection {
  id: string;
  patientId: string;
  firstName: string;
  lastName: string;
  targetLow: number;
  targetHigh: number;
  glucoseMeasurement: GlucoseMeasurement;
  glucoseItem: GlucoseItem;
  sensor: Sensor;
  patientDevice: PatientDevice;
  alarmRules: AlarmRules;
}
```

**Source**: `src/interfaces/librelink/connections-response.ts`

### Get Graph Data

**Endpoint**: `GET /llu/connections/{patientId}/graph`

**Headers**:
```
Authorization: Bearer {token}
```

**Response** (`GraphResponse`):
```typescript
interface GraphResponse {
  status: number;
  data: {
    connection: Connection;
    graphData: GlucoseItem[];
    activeSensors: Sensor[];
  };
}
```

**Source**: `src/interfaces/librelink/graph-response.ts`

---

## Data Types

### GlucoseItem

```typescript
interface GlucoseItem {
  FactoryTimestamp: string;    // ISO 8601 timestamp (sensor time)
  Timestamp: string;           // Local timestamp (phone time)
  ValueInMgPerDl: number;      // Glucose value in mg/dL
  TrendArrow?: number;         // Trend indicator (1-5)
  TrendMessage?: string;       // Localized trend text
  MeasurementColor: number;    // Color coding (in-range, high, low)
  GlucoseUnits: number;        // 0 = mg/dL, 1 = mmol/L
  Value: number;               // Value in native units
}
```

**Source**: `src/interfaces/librelink/common.ts`

### GlucoseMeasurement

Current reading (extends GlucoseItem):

```typescript
interface GlucoseMeasurement extends GlucoseItem {
  TrendArrow: number;  // Required (not optional)
}
```

### Sensor

```typescript
interface Sensor {
  deviceId: string;
  sn: string;         // Serial number
  a: number;
  w: number;
  pt: number;
  s: boolean;
}
```

---

## Trend Arrow Values

| Value | Meaning | Nightscout Direction |
|-------|---------|---------------------|
| 1 | Falling fast | `SingleDown` |
| 2 | Falling | `FortyFiveDown` |
| 3 | Stable | `Flat` |
| 4 | Rising | `FortyFiveUp` |
| 5 | Rising fast | `SingleUp` |

**Gap**: LibreLink provides only 5 trend values vs Nightscout's 9 (no DoubleUp/DoubleDown). See GAP-LIBRELINK-003.

---

## Error Handling

### HTTP Status Codes

| Code | Meaning | Action |
|------|---------|--------|
| 200 | Success | Process response |
| 401 | Unauthorized | Re-authenticate |
| 403 | Forbidden | Check region, credentials |
| 429 | Rate limited | Increase polling interval |
| 5xx | Server error | Retry with backoff |

### Response Status Codes

| Status | Meaning |
|--------|---------|
| 0 | Success |
| 2 | Authentication error |
| 4 | Bad request |

---

## Rate Limits

| Limit | Value | Notes |
|-------|-------|-------|
| Polling interval | 5 min (default) | Configurable via `LINK_UP_TIME_INTERVAL` |
| Token lifetime | ~12 hours | Refresh on expiry |
| Requests per day | Unknown | No documented limit |

---

## Configuration

### Environment Variables

| Variable | Purpose | Required |
|----------|---------|----------|
| `LINK_UP_USERNAME` | LibreLink Up email | Yes |
| `LINK_UP_PASSWORD` | LibreLink Up password | Yes |
| `LINK_UP_REGION` | API region code | No (default: EU) |
| `LINK_UP_CONNECTION` | Patient ID for multi-patient | No |
| `LINK_UP_TIME_INTERVAL` | Polling interval (minutes) | No (default: 5) |

---

## Comparison with Other APIs

| Aspect | LibreLink Up | Dexcom Share | Tandem t:connect |
|--------|--------------|--------------|------------------|
| **Auth** | Email/password | Email/password | OAuth2 / credentials |
| **Token** | JWT | Session ID | OAuth tokens |
| **Regions** | 8 regions | 2 (US, OUS) | US only |
| **Multi-patient** | Yes | No | No |
| **Historical** | Via graph endpoint | Via minutes param | Full export |
| **Rate limit** | Unknown | Unknown | Unknown |
