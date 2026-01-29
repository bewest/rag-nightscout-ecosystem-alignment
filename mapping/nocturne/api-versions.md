# Nocturne API Versions

> **Source**: `externals/nocturne/src/API/Nocturne.API/Controllers/`  
> **Last Updated**: 2026-01-29

Nocturne implements full v1/v2/v3 Nightscout API compatibility plus v4 Nocturne-native extensions.

---

## Version Overview

| Version | Status | Purpose |
|---------|--------|---------|
| **v1** | ✅ Full parity | Legacy compatibility (Loop, xDrip+) |
| **v2** | ✅ Full parity | Extended endpoints (DData) |
| **v3** | ✅ Full parity | Modern REST API |
| **v4** | 🆕 Nocturne-native | Extensions (not cross-project) |

---

## V1 Endpoints

**Base**: `/api/v1/`

| Endpoint | Controller | Purpose | Clients |
|----------|------------|---------|---------|
| `/entries` | EntriesController | SGV/MBG data | All |
| `/treatments` | TreatmentsController | Treatment CRUD | All |
| `/devicestatus` | DeviceStatusController | Loop/AAPS status | AID apps |
| `/food` | FoodController | Food database | AAPS |
| `/notifications` | NotificationsController | Push notifications | Caregivers |
| `/profile` | ProfileController | Therapy profiles | All |

### V1 Authentication

```
Authorization: Bearer <api_secret_sha1>
```

Or query parameter: `?token=<api_secret_sha1>` (deprecated)

---

## V2 Endpoints

**Base**: `/api/v2/`

| Endpoint | Controller | Purpose | Clients |
|----------|------------|---------|---------|
| `/ddata` | DDataController | Combined data payload | Nightscout web |
| `/loop` | LoopController | Loop-specific data | Loop iOS |
| `/properties` | PropertiesController | Server properties | All |
| `/summary` | SummaryController | Quick summary | Widgets |

### DData Response Structure

```json
{
  "entries": [...],
  "treatments": [...],
  "devicestatus": [...],
  "profiles": [...],
  "mbgs": [...],
  "cals": [...],
  "foods": [...]
}
```

---

## V3 Endpoints

**Base**: `/api/v3/`

| Endpoint | Controller | Methods | Notes |
|----------|------------|---------|-------|
| `/entries` | EntriesController | GET, POST, PUT, PATCH, DELETE | Full CRUD |
| `/treatments` | TreatmentsController | GET, POST, PUT, PATCH, DELETE | Full CRUD |
| `/devicestatus` | DeviceStatusController | GET, POST, PUT, PATCH, DELETE | Full CRUD |
| `/food` | FoodController | GET, POST, PUT, PATCH, DELETE | Full CRUD |
| `/profile` | ProfileController | GET, POST, PUT, PATCH, DELETE | Full CRUD |
| `/settings` | SettingsController | GET, PUT | Server settings |
| `/status` | StatusController | GET | Server status |
| `/version` | VersionController | GET | API version info |

### V3 Query Parameters

| Parameter | Type | Example | Notes |
|-----------|------|---------|-------|
| `limit` | int | `?limit=100` | Max records |
| `skip` | int | `?skip=50` | Pagination offset |
| `sort` | string | `?sort=date$desc` | Field sorting |
| `fields` | string | `?fields=sgv,date` | Field selection |
| `date$gte` | long | `?date$gte=1704067200000` | Date range filter |
| `date$lte` | long | `?date$lte=1704153600000` | Date range filter |

### V3 Authentication

```
Authorization: Bearer <jwt_token>
```

JWT obtained via `/api/v3/auth/token` with subject credentials.

---

## V4 Endpoints (Nocturne-Native)

**Base**: `/api/v4/`

⚠️ **Note**: V4 endpoints are Nocturne-specific extensions. No cross-project standard exists (GAP-NOCTURNE-001).

| Endpoint | Purpose | Notes |
|----------|---------|-------|
| `/treatments/aggregate` | Aggregated treatment stats | IOB, COB summaries |
| `/statespans` | Time-in-range segments | Pre-computed TIR |
| `/chartdata` | Optimized chart data | Downsampled for performance |
| `/processing` | Background job status | Connector sync status |
| `/oref/calculate` | Algorithm calculation | Rust oref via FFI |
| `/analytics` | Advanced analytics | A1c estimation, patterns |

### V4 Example: Aggregate Treatments

```http
GET /api/v4/treatments/aggregate?from=1704067200000&to=1704153600000

{
  "iob": 2.5,
  "cob": 30,
  "totalInsulin": 45.2,
  "totalCarbs": 180,
  "bolusCount": 6,
  "tempBasalMinutes": 120
}
```

---

## Endpoint Mapping: Nocturne vs cgm-remote-monitor

| Endpoint | Nocturne | cgm-remote-monitor | Notes |
|----------|----------|-------------------|-------|
| `/api/v1/entries` | ✅ | ✅ | Full parity |
| `/api/v1/treatments` | ✅ | ✅ | Full parity |
| `/api/v1/devicestatus` | ✅ | ✅ | Full parity |
| `/api/v2/ddata` | ✅ | ✅ | Full parity |
| `/api/v3/entries` | ✅ | ✅ | Full parity |
| `/api/v3/treatments` | ✅ | ✅ | Full parity |
| `/api/v4/*` | ✅ | ❌ | Nocturne only |

---

## Client Compatibility Matrix

| Client | v1 | v2 | v3 | v4 | Notes |
|--------|----|----|----|----|-------|
| Loop | ✅ | ❌ | ❌ | ❌ | Uses v1 only |
| AAPS | ✅ | ❌ | ✅ | ❌ | Prefers v3 |
| Trio | ✅ | ❌ | ❌ | ❌ | Uses v1 |
| xDrip+ | ✅ | ❌ | ✅ | ❌ | Can use either |
| Nightscout web | ✅ | ✅ | ✅ | ❌ | Uses all |
| Nocturne web | ✅ | ✅ | ✅ | ✅ | Uses all |

---

## Real-Time Updates

### cgm-remote-monitor: Socket.IO

```javascript
socket.on('dataUpdate', (data) => { ... });
```

### Nocturne: SignalR

```javascript
connection.on('DataUpdate', (data) => { ... });
```

### Bridge Compatibility

Nocturne includes a SignalR → Socket.IO bridge for legacy client compatibility:

**Source**: `src/Web/packages/bridge/`

```
Client (Socket.IO) → Bridge → SignalR Hub → Nocturne
```

See GAP-NOCTURNE-003 for latency implications.

---

## Gaps

| Gap ID | Description | Impact |
|--------|-------------|--------|
| GAP-NOCTURNE-001 | V4 endpoints not standardized | Apps can't use V4 features |
| GAP-API-001 | No V4 in cgm-remote-monitor | Feature parity gap |

---

## Cross-References

- [cgm-remote-monitor API Versions](../cgm-remote-monitor/api-versions.md)
- [Nightscout API Requirements](../../traceability/nightscout-api-requirements.md)
- [OpenAPI Specs](../../specs/openapi/)
