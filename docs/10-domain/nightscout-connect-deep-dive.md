# nightscout-connect Deep Dive

> **Repository**: `externals/nightscout-connect/`  
> **Version**: 0.0.12  
> **Purpose**: Connect common cloud platforms to Nightscout  
> **License**: AGPL-3.0-or-later

---

## Executive Summary

nightscout-connect is a bridge application that fetches CGM/pump data from vendor cloud platforms and uploads to Nightscout. It uses XState state machines for robust session management, retry logic, and polling cycles. The architecture separates concerns into **sources** (vendor API clients), **machines** (state management), and **outputs** (data persistence).

### Key Findings

| Finding | Impact |
|---------|--------|
| XState-based architecture | Testable, well-structured state management |
| 5 vendor sources | Dexcom Share, LibreLinkUp, Nightscout, Glooko, Minimed CareLink |
| 3 output modes | REST API, internal DB, filesystem |
| v1 API only | No v3 API support for output |
| Variable data coverage | Only Minimed uploads all 3 collections |

---

## Architecture Overview

**Conformance Assertions**: [`conformance/assertions/bridge-connector.yaml`](../../conformance/assertions/bridge-connector.yaml) — 17 assertions covering REQ-BRIDGE-001-003, REQ-CONNECT-001-003

### Design Philosophy

The project follows a modular design documented in `machines.md`:

```
Input (Source) → Transform → Output
```

- **Sources**: Vendor-specific API clients (`lib/sources/`)
- **Machines**: XState state machines for orchestration (`lib/machines/`)
- **Outputs**: Nightscout persistence drivers (`lib/outputs/`)

### Core Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| xstate | ^4.37.1 | State machine engine |
| axios | ^1.3.4 | HTTP client |
| tough-cookie | ^4.1.3 | Cookie jar for sessions |
| yargs | ^17.7.1 | CLI parsing |

> **Source**: `package.json:36-43`

---

## State Machine Architecture

### Machine Hierarchy

```
Poller (Bus)
├── Session Machine
│   ├── Authenticating
│   ├── Authorizing
│   ├── Active
│   └── Expired
└── Cycle Machine(s)
    └── Fetch Machine
        ├── Waiting
        ├── Auth
        ├── DetermineGaps
        ├── Fetching
        ├── Transforming
        ├── Persisting
        └── Done
```

### Fetch Machine States

> **Source**: `lib/machines/fetch.js:104-349`

| State | Purpose |
|-------|---------|
| **Idle** | Technical initial state |
| **Waiting** | Delay injection for shared infrastructure |
| **Auth** | Wait for SESSION_RESOLVED from parent |
| **DetermineGaps** | Query last known data via GAP_ANALYSIS event |
| **Fetching** | Execute vendor API promise |
| **Transforming** | Convert vendor format to Nightscout |
| **Persisting** | Write to configured output |
| **Success** | Increment counters, align schedule |
| **Error** | Retry logic with exponential backoff |
| **Done** | Terminal state |

### Session Machine States

> **Source**: `lib/machines/session.js:82-260`

| State | Purpose |
|-------|---------|
| **Inactive** | Initial state |
| **Fresh.Authenticating** | Resolve credentials to auth info |
| **Fresh.Authorizing** | Resolve auth to session token |
| **Fresh.Established** | Session ready |
| **Active** | Reuse existing session |
| **Refreshing** | Optional token refresh |
| **Expired** | Session no longer valid |

### Event Flow

| Event | Direction | Purpose |
|-------|-----------|---------|
| `SESSION_REQUIRED` | fetch → session | Request active session |
| `SESSION_RESOLVED` | session → fetch | Provide session token |
| `SESSION_EXPIRED` | session → poller | Force re-authentication |
| `GAP_ANALYSIS` | fetch → source | Determine query window |
| `DATA_RECEIVED` | fetch → transform | Raw vendor data |
| `STORE` | fetch → output | Persist transformed data |

---

## Source Drivers

### Overview

| Driver | Auth Method | Data Types | Session TTL |
|--------|-------------|------------|-------------|
| **Dexcom Share** | Username/Password + Account ID | Entries only | 24h |
| **LibreLinkUp** | Email/Password + Bearer | Entries only | 1h |
| **Nightscout** | API Secret OR Token | Entries only | 8h |
| **Glooko** | Email/Password + Cookie | Treatments | 24h |
| **Minimed CareLink** | Multi-step OAuth | All 3 collections | 7m |

### Dexcom Share

> **Source**: `lib/sources/dexcomshare.js`

**Authentication Flow**:
1. `AuthenticatePublisherAccount` with username/password → Account ID
2. `LoginPublisherAccountById` → Session token

**API Endpoints**:
- `/ShareWebServices/Services/General/AuthenticatePublisherAccount` (line 16)
- `/ShareWebServices/Services/General/LoginPublisherAccountById` (line 17)
- `/ShareWebServices/Services/Publisher/ReadPublisherLatestGlucoseValues` (line 21)

**Transform** (`dex_to_entry()` lines 35-58):
```javascript
{
  type: 'sgv',
  date: extractTime(item.WT),  // "Date(1234567890000)"
  sgv: item.Value,
  direction: trendToDirection(item.Trend),
  device: 'nightscout-connect'
}
```

**Polling**: 5-minute cycle, 2-day lookback window

### LibreLinkUp

> **Source**: `lib/sources/librelinkup.js`

**Authentication Flow**:
1. POST `/llu/auth/login` with email/password
2. Bearer token in Authorization header

**API Endpoints**:
- `/llu/auth/login` (line 19)
- `/llu/connections` (line 20)
- `/llu/connections/{patientId}/graph` (line 21)

**Transform** (`to_ns_sgv()` lines 130-142):
- Maps `FactoryTimestamp` → ISO date
- Maps `TrendArrow` → direction via lookup
- Extracts `ValueInMgPerDl`

**Session**: Refresh every 1 hour

### Nightscout (as Source)

> **Source**: `lib/sources/nightscout.js`

Enables Nightscout-to-Nightscout sync for:
- Follower instances
- Backup/migration
- Data aggregation

**Authentication**:
- SHA1 hash of API_SECRET
- Optional: Token-based via `/api/v2/authorization/request`
- Creates "nightscout-connect-reader" subject with readable role

**API Endpoints**:
- `/api/v1/verifyauth` (line 40)
- `/api/v2/authorization/subjects` (line 55)
- `/api/v1/entries.json` (line 133)

**Session TTL**: 8 hours (matching Nightscout JWT)

### Glooko

> **Source**: `lib/sources/glooko/index.js` + `convert.js`

**Authentication**: Cookie-based session after email/password login

**API Endpoints**:
- `/api/v2/users/sign_in` (line 26)
- `/api/v2/cgm/readings` (line 32)
- `/api/v2/pumps/normal_boluses` (line 31)
- `/api/v2/pumps/scheduled_basals` (line 30)

**Transform** (`generate_nightscout_treatments()` in convert.js):
| Glooko Type | Nightscout eventType |
|-------------|---------------------|
| Foods | Meal/Carb Correction |
| Insulins | Correction Bolus |
| Pump Boluses | Meal Bolus |
| Scheduled Basals | Temp Basal |

**Unique**: Only source focused on treatments (not CGM)

### Minimed CareLink

> **Source**: `lib/sources/minimedcarelink/index.js`

**Most Complex Driver** - Multi-step OAuth with consent flow.

**Authentication Flow**:
1. POST `/patient/sso/login` → HTML form with sessionID
2. Parse HTML, submit consent
3. Extract Bearer token from cookies

**API Endpoints**:
- `/patient/sso/login` (line 23)
- `/patient/sso/reauth` (line 24)
- `/patient/monitor/data` (line 29)
- `/patient/m2m/connect/data/gc/patients/{username}` (line 32)

**Transform** (`transformPayload()` lines 677-763):
- `sgs_to_sgv()`: Carelink glucose → Nightscout SGV
- `markers_to_treatment()`: Meals + insulin → treatments
- `deviceStatusEntry()`: Pump battery, reservoir, IOB, sensor state

**Unique Features**:
- Only source that uploads **all 3 collections** (entries, treatments, devicestatus)
- Timezone adjustment for conduit devices
- Care partner mode support

**Session**: Very short 7-minute refresh cycle

---

## Output Drivers

### REST API Output

> **Source**: `lib/outputs/nightscout.js`

**API Version**: v1 only

**Endpoints**:
- `POST /api/v1/entries.json` (line 35)
- `POST /api/v1/treatments.json` (line 48)

**Authentication**: SHA1-hashed API secret in `API-SECRET` header

**Collections**: entries, treatments (parallel writes via `Promise.all`)

### Internal Output

> **Source**: `lib/outputs/internal.js`

For running as Nightscout plugin - direct database writes.

**Method**: `ctx.{collection}.create()` calls

**Collections**: entries, treatments, devicestatus, profile

**Sync**: Waits for `data-processed` event before resolving

### Filesystem Output

> **Source**: `lib/outputs/filesystem.js`

Debug/logging mode - writes JSON to local files.

**Path**: `logs/{timestamp}ns-connect-out.log`

**Format**: Single JSON blob with all collections

---

## Gap Analysis

### GAP-CONNECT-001: v1 API Only

**Description**: Output driver only supports Nightscout API v1, missing v3 benefits.

**Impact**:
- No UPSERT semantics (duplicates not merged)
- No identifier-based sync identity
- No server-side validation

**Affected Code**: `lib/outputs/nightscout.js:35,48`

**Remediation**: Add v3 output driver using `/api/v3/entries` etc.

### GAP-CONNECT-002: Inconsistent Data Coverage

**Description**: Only Minimed source uploads all 3 collections.

| Source | entries | treatments | devicestatus |
|--------|---------|------------|--------------|
| Dexcom Share | ✅ | ❌ | ❌ |
| LibreLinkUp | ✅ | ❌ | ❌ |
| Nightscout | ✅ | ❌ | ❌ |
| Glooko | ❌ | ✅ | ❌ |
| Minimed | ✅ | ✅ | ✅ |

**Impact**: Incomplete data for most sources

**Remediation**: Extend sources to fetch available collections

### GAP-CONNECT-003: No Deduplication Strategy

**Description**: No sync identity or dedup logic in output drivers.

**Impact**:
- Re-runs create duplicates
- No idempotent uploads
- Relies on server-side dedup which varies by API version

**Affected Code**: `lib/outputs/nightscout.js:77-79`

**Remediation**: Generate UUIDs client-side, use v3 UPSERT

---

## Builder Pattern

> **Source**: `lib/builder.js`

The builder decouples vendor code from XState:

```javascript
builder.support_session({
  authenticate: impl.authFromCredentials,
  authorize: impl.sessionFromAuth,
  delays: {
    REFRESH_AFTER_SESSSION_DELAY: 28800000,
    EXPIRE_SESSION_DELAY: 28800000
  }
});

builder.register_loop('EntriesLoop', {
  frame: {
    impl: impl.dataFromSession,
    transform: impl.transformGlucose,
    maxRetries: 3
  },
  expected_data_interval_ms: 5 * 60 * 1000
});
```

### Key Builder Methods

| Method | Purpose |
|--------|---------|
| `support_session()` | Register auth/authorize promises |
| `register_loop()` | Create polling cycle for data type |
| `tracker_for()` | Gap analysis / last-known tracking |

---

## Configuration

### Environment Variables

Prefix: `CONNECT_`

| Variable | Purpose |
|----------|---------|
| `CONNECT_SOURCE` | Source driver name |
| `CONNECT_NIGHTSCOUT_URL` | Target Nightscout instance |
| `CONNECT_NIGHTSCOUT_API_SECRET` | API secret for output |
| `CONNECT_{SOURCE}_*` | Source-specific credentials |

### Example: Dexcom Share

```bash
CONNECT_SOURCE=dexcomshare
CONNECT_DEXCOM_USERNAME=user@example.com
CONNECT_DEXCOM_PASSWORD=secret
CONNECT_NIGHTSCOUT_URL=https://my.nightscout.example
CONNECT_NIGHTSCOUT_API_SECRET=myapisecret
```

---

## CLI Interface

> **Source**: `commands/forever.js`, `commands/capture.js`

### Commands

| Command | Purpose |
|---------|---------|
| `forever` | Run continuous polling loop |
| `capture` | Single capture for testing |

### Usage

```bash
npx nightscout-connect forever --source dexcomshare
npx nightscout-connect capture --source librelinkup
```

---

## Error Handling

### Retry Strategy

> **Source**: `lib/machines/fetch.js:61-67`, `lib/backoff.js`

- **Frame Retries**: 3 attempts per fetch cycle (configurable)
- **Backoff**: Exponential delay on consecutive failures
- **Formula**: `base_interval * 2^frames_missing`

### Error Events

| Event | Handling |
|-------|----------|
| `SESSION_ERROR` | Re-authenticate |
| `FETCH_ERROR` | Retry with backoff |
| `TRANSFORM_ERROR` | Skip batch, log error |
| `PERSIST_ERROR` | Retry, then fail frame |

---

## Testing

> **Source**: `testable_driver.js`, `demo.js`, `junk.js`

No formal test suite (`package.json:13`: "Error: no test specified")

**Manual Testing Files**:
- `testable_driver.js` - Simplified driver for unit testing
- `demo.js` - Hardcoded example flow
- `junk.js` - Experimental code

**Gap**: No automated tests despite testable XState architecture

---

## Integration Points

### As Standalone CLI

```bash
npm install -g nightscout-connect
nightscout-connect forever --source dexcomshare
```

### As Nightscout Plugin

Uses `lib/outputs/internal.js` for direct database access.

```javascript
// In Nightscout env
CONNECT_ENABLED=true
CONNECT_SOURCE=minimedcarelink
```

### With Docker

```dockerfile
FROM node:18
RUN npm install -g nightscout-connect
CMD ["nightscout-connect", "forever"]
```

---

## Comparison with Similar Tools

| Feature | nightscout-connect | tconnectsync | share2nightscout-bridge |
|---------|-------------------|--------------|------------------------|
| Architecture | XState machines | SQLite + scheduled | Express + polling |
| Multi-source | ✅ 5 sources | ❌ Tandem only | ❌ Dexcom only |
| Treatments | ✅ (Minimed, Glooko) | ✅ | ❌ |
| DeviceStatus | ✅ (Minimed) | ✅ | ❌ |
| Testability | High (XState) | Medium | Low |

---

## Recommendations

### Short-term

1. **Add v3 output driver** - Enable UPSERT deduplication
2. **Extend LibreLinkUp** - Source has historical data available
3. **Add basic tests** - XState provides excellent test utilities

### Medium-term

1. **Standardize transforms** - Common utility for SGV/treatment mapping
2. **Add metrics** - Prometheus/StatsD for monitoring
3. **Improve error reporting** - Structured logging

### Long-term

1. **TypeScript migration** - Better type safety for transforms
2. **Plugin architecture** - Dynamic source loading
3. **Bidirectional sync** - Read treatments from Nightscout back to vendor

---

## Related Documentation

- [machines.md](../../externals/nightscout-connect/machines.md) - Theory of operation
- [tconnectsync Deep Dive](./tconnectsync-deep-dive.md) - Similar bridge tool
- [share2nightscout-bridge Deep Dive](./share2nightscout-bridge-deep-dive.md) - Dexcom-specific
- [nightscout-librelink-up Deep Dive](./nightscout-librelink-up-deep-dive.md) - LibreLink-specific
- [Interoperability Spec](../../specs/interoperability-spec-v1.md) - Data format requirements

---

*Generated: 2026-01-29 | Source: nightscout-connect v0.0.12*
