# nightscout-librelink-up Deep Dive

> **Source**: `externals/nightscout-librelink-up/`  
> **Last Updated**: 2026-01-29  
> **Version**: 3.0.0

## Overview

nightscout-librelink-up is a TypeScript bridge that syncs glucose data from Abbott's LibreLink Up cloud service to Nightscout. It enables Libre CGM users (Libre 2, Libre 3) to aggregate their data in Nightscout without additional hardware.

| Aspect | Details |
|--------|---------|
| **Language** | TypeScript/Node.js |
| **Author** | timoschlueter |
| **License** | MIT |
| **CGM Support** | FreeStyle Libre 2, Libre 3 |
| **Data Source** | LibreLink Up cloud API |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                  nightscout-librelink-up                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐     │
│  │   Config    │    │  Interfaces │    │  Nightscout │     │
│  │   (env)     │    │  (models)   │    │  (upload)   │     │
│  └──────┬──────┘    └──────┬──────┘    └──────┬──────┘     │
│         │                  │                  │             │
│         ▼                  ▼                  ▼             │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐     │
│  │  Regions    │    │ GlucoseItem │    │  API v1     │     │
│  │  Intervals  │    │ Connection  │    │  Entries    │     │
│  │  Patients   │    │ AuthTicket  │    │  (v3 stub)  │     │
│  └─────────────┘    └─────────────┘    └─────────────┘     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
         │                                       │
         ▼                                       ▼
    LibreLink Up Cloud                      Nightscout
    (api.libreview.io)                      (api/v1/entries)
```

---

## Directory Structure

```
nightscout-librelink-up/
├── src/
│   ├── index.ts          # Main application, polling loop
│   ├── config.ts         # Environment configuration
│   ├── constants/        # API regions, endpoints
│   ├── helpers/          # Utility functions
│   ├── interfaces/       # TypeScript type definitions
│   │   └── librelink/    # LibreLink API response types
│   └── nightscout/       # Nightscout upload clients
│       ├── interface.ts  # Entry interface
│       ├── apiv1.ts      # API v1 client
│       └── apiv3.ts      # API v3 client (stub)
├── tests/                # Jest test suite
├── Dockerfile            # Container deployment
└── package.json
```

---

## LibreLink Up API

### Authentication

**Endpoint**: `POST https://<REGION>/llu/auth/login`

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
  user: User;
  authTicket: AuthTicket;
  messages: any;
  notifications: any;
}

interface AuthTicket {
  token: string;
  expires: number;     // Unix timestamp
  duration: number;    // Token validity duration
}
```

### Stealth Mode

The client uses custom SSL ciphers and cookie handling to bypass Cloudflare fingerprinting:
- Custom cipher suite ordering
- SHA-256 hashed account-id header
- User-Agent mimicking official app

### API Regions

| Region | Base URL |
|--------|----------|
| EU | `api-eu.libreview.io` |
| EU2 | `api-eu2.libreview.io` |
| US | `api-us.libreview.io` |
| AU | `api-au.libreview.io` |
| DE | `api-de.libreview.io` |
| FR | `api-fr.libreview.io` |
| JP | `api-jp.libreview.io` |
| AP | `api-ap.libreview.io` |

---

## Data Interfaces

### GlucoseItem

**Source**: `src/interfaces/librelink/common.ts`

```typescript
interface GlucoseItem {
  FactoryTimestamp: string;    // ISO timestamp
  Timestamp: string;           // Local timestamp
  ValueInMgPerDl: number;      // Glucose value
  TrendArrow?: number;         // Trend indicator (1-5)
  TrendMessage?: string;       // Trend description
  MeasurementColor: number;    // Color coding
  GlucoseUnits: number;        // 0=mg/dL, 1=mmol/L
  Value: number;               // Value in native units
}
```

### GlucoseMeasurement

```typescript
interface GlucoseMeasurement extends GlucoseItem {
  TrendArrow: number;  // Required, not optional
}
```

### Connection (Patient)

```typescript
interface Connection {
  id: string;
  patientId: string;
  firstName: string;
  lastName: string;
  glucoseMeasurement: GlucoseMeasurement;
  glucoseItem: GlucoseItem;
  sensor: Sensor;
  patientDevice: PatientDevice;
  alarmRules: AlarmRules;
}
```

---

## Nightscout Integration

### Entry Interface

**Source**: `src/nightscout/interface.ts`

```typescript
interface Entry {
  date: Date;
  sgv: number;
  direction?: Direction;
}

enum Direction {
  SingleDown = "SingleDown",
  FortyFiveDown = "FortyFiveDown", 
  Flat = "Flat",
  FortyFiveUp = "FortyFiveUp",
  SingleUp = "SingleUp",
  NOT_COMPUTABLE = "NOT COMPUTABLE"
}
```

### API v1 Upload

**Source**: `src/nightscout/apiv1.ts`

**Endpoint**: `POST /api/v1/entries`

**Payload**:
```typescript
const entriesV1 = entries.map((e) => ({
  type: "sgv",
  sgv: e.sgv,
  direction: e.direction?.toString(),
  device: "nightscout-librelink-up",
  date: e.date.getTime(),
  dateString: e.date.toISOString(),
}));
```

**Authentication**: `api-secret` header (SHA1 hashed)

### API v3 Status

**Source**: `src/nightscout/apiv3.ts`

```typescript
// Not implemented - throws error
throw Error("Not implemented");
```

---

## Field Mappings

### LibreLink → Nightscout

| LibreLink Field | Nightscout Field | Notes |
|-----------------|------------------|-------|
| `ValueInMgPerDl` | `sgv` | Glucose value |
| `FactoryTimestamp` | `date` | Epoch ms |
| `FactoryTimestamp` | `dateString` | ISO 8601 |
| `TrendArrow` | `direction` | Mapped via enum |
| - | `type` | Always `"sgv"` |
| - | `device` | `"nightscout-librelink-up"` |

### Trend Arrow Mapping

| LibreLink Value | Nightscout Direction |
|-----------------|---------------------|
| 1 | `SingleDown` |
| 2 | `FortyFiveDown` |
| 3 | `Flat` |
| 4 | `FortyFiveUp` |
| 5 | `SingleUp` |
| null/undefined | `NOT COMPUTABLE` |

---

## Configuration

### Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `LINK_UP_USERNAME` | LibreLink Up email | Required |
| `LINK_UP_PASSWORD` | LibreLink Up password | Required |
| `LINK_UP_REGION` | API region | `EU` |
| `LINK_UP_CONNECTION` | Patient ID (multi-patient) | First patient |
| `LINK_UP_TIME_INTERVAL` | Polling interval (minutes) | `5` |
| `NIGHTSCOUT_URL` | Nightscout URL | Required |
| `NIGHTSCOUT_API_TOKEN` | API secret | Required |
| `NIGHTSCOUT_API_V3` | Use API v3 | `false` |
| `SINGLE_SHOT` | Run once and exit | `false` |

### Polling Interval

Default: 5 minutes (`LINK_UP_TIME_INTERVAL`)

Cron schedule: `*/{interval} * * * *`

---

## Multi-Patient Support

LibreLink Up allows following multiple patients. Selection logic:

1. **Single patient**: Use automatically
2. **Multiple patients** + `LINK_UP_CONNECTION` set: Match by `patientId`
3. **Multiple patients** + no selection: Use first, log warning

**API**: `GET /llu/connections`

---

## Deployment Options

| Platform | File |
|----------|------|
| **Docker** | `Dockerfile` |
| **Heroku** | `app.json`, `Procfile` |
| **Render** | `render.yaml` |
| **DigitalOcean** | `.do/` directory |

---

## Gaps Identified

### GAP-LIBRELINK-001: API v3 Not Implemented

**Description**: The v3 client exists but throws "Not implemented". Only v1 API is functional.

**Source**: `src/nightscout/apiv3.ts`

**Impact**:
- No automatic deduplication
- Missing `identifier` field for sync tracking
- Same limitation as tconnectsync

**Remediation**: Implement v3 client with proper identifiers.

### GAP-LIBRELINK-002: No Historical Backfill

**Description**: While `GraphResponse` interface exists for historical data, only current readings are uploaded by default.

**Source**: `src/interfaces/librelink/graph-response.ts`

**Impact**:
- Gaps in data if service is down
- No catch-up mechanism

**Remediation**: Add optional historical fetch and backfill.

### GAP-LIBRELINK-003: Trend Arrow Limited to 5 Values

**Description**: LibreLink Up provides only 5 trend values vs Nightscout's 9. No DoubleUp/DoubleDown mapping.

**Source**: `src/nightscout/interface.ts`

**Impact**:
- Loss of precision for rapid glucose changes
- Libre sensors may not report extreme trends

**Remediation**: Document as sensor limitation; map to closest available.

---

## Comparison with Other Bridges

| Aspect | share2nightscout-bridge | tconnectsync | nightscout-librelink-up |
|--------|------------------------|--------------|------------------------|
| **CGM** | Dexcom | Tandem (G6/G7) | Libre 2/3 |
| **Language** | JavaScript | Python | TypeScript |
| **API** | v1 only | v1 only | v1 only (v3 stub) |
| **Treatments** | No | Yes (10+) | No (entries only) |
| **Real-time** | Polling | Batch | Polling |
| **Multi-patient** | No | No | Yes |

---

## Source File Reference

### Core Files
- `externals/nightscout-librelink-up/src/index.ts` - Main application, polling loop
- `externals/nightscout-librelink-up/src/config.ts` - Environment configuration

### LibreLink Interfaces
- `externals/nightscout-librelink-up/src/interfaces/librelink/common.ts` - GlucoseItem, Connection
- `externals/nightscout-librelink-up/src/interfaces/librelink/login-response.ts` - Auth response
- `externals/nightscout-librelink-up/src/interfaces/librelink/connections-response.ts` - Patient list
- `externals/nightscout-librelink-up/src/interfaces/librelink/graph-response.ts` - Historical data

### Nightscout Clients
- `externals/nightscout-librelink-up/src/nightscout/interface.ts` - Entry interface
- `externals/nightscout-librelink-up/src/nightscout/apiv1.ts` - v1 upload client
- `externals/nightscout-librelink-up/src/nightscout/apiv3.ts` - v3 stub

---

## Summary

| Aspect | Details |
|--------|---------|
| **Purpose** | Sync LibreLink Up → Nightscout |
| **Data Flow** | 5-min polling from cloud, upload to NS v1 |
| **Data Types** | Entries only (SGV, trend) |
| **Multi-patient** | Supported via `LINK_UP_CONNECTION` |
| **Limitations** | No v3, no treatments, no backfill |

nightscout-librelink-up is a well-structured bridge for Libre CGM users, offering multi-region and multi-patient support with simple deployment options.
