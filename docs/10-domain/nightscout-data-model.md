# Nightscout Data Model

This document describes the core data model used in Nightscout (cgm-remote-monitor), forming the foundation for alignment work across AID systems.

---

## Collections Overview

Nightscout stores data in MongoDB collections. Each collection serves a specific purpose in the diabetes management workflow.

| Collection | Purpose | Key Fields |
|------------|---------|------------|
| **entries** | Glucose readings from CGM | `sgv`, `direction`, `date`, `device` |
| **treatments** | User interventions and events | `eventType`, `insulin`, `carbs`, `duration` |
| **profile** | Therapy settings | `store`, `basal`, `sens`, `carbratio` |
| **devicestatus** | Controller/loop state | `loop`, `openaps`, `pump`, `uploader` |
| **food** | Food database entries | `name`, `carbs`, `protein`, `fat` |
| **activity** | Activity data | Various activity metrics |

---

## Entries Collection

Glucose readings from CGM devices.

### Core Fields

| Field | Type | Description |
|-------|------|-------------|
| `sgv` | Number | Sensor glucose value (mg/dL or mmol/L) |
| `direction` | String | Trend arrow direction |
| `date` | Number | Epoch milliseconds |
| `dateString` | String | ISO 8601 timestamp |
| `device` | String | Device identifier |
| `type` | String | Entry type (`sgv`, `cal`, `mbg`) |
| `noise` | Number | Signal noise level |
| `filtered` | Number | Filtered raw value |
| `unfiltered` | Number | Unfiltered raw value |

### Direction Values

Trend directions indicate glucose rate of change:

| Direction | Meaning | Rate (mg/dL/min) |
|-----------|---------|------------------|
| `DoubleUp` | Rising rapidly | > 3 |
| `SingleUp` | Rising | 2-3 |
| `FortyFiveUp` | Rising slowly | 1-2 |
| `Flat` | Stable | -1 to 1 |
| `FortyFiveDown` | Falling slowly | -1 to -2 |
| `SingleDown` | Falling | -2 to -3 |
| `DoubleDown` | Falling rapidly | < -3 |
| `NOT COMPUTABLE` | Insufficient data | N/A |

---

## Treatments Collection

All user interventions, therapy adjustments, and system events.

### Core Event Types

| eventType | Description | Key Fields |
|-----------|-------------|------------|
| `BG Check` | Blood glucose finger stick | `glucose`, `glucoseType` |
| `Meal Bolus` | Insulin for meal | `insulin`, `carbs` |
| `Correction Bolus` | Insulin for high BG | `insulin` |
| `Snack Bolus` | Insulin for snack | `insulin`, `carbs` |
| `Carb Correction` | Carbs for low BG | `carbs` |
| `Combo Bolus` | Split immediate/extended bolus | `insulin`, `duration`, `splitNow`, `splitExt` |
| `Temp Basal Start` | Temporary basal rate | `duration`, `percent` or `absolute` |
| `Temp Basal End` | End of temp basal | - |
| `Profile Switch` | Change active profile | `profile`, `duration` |
| `Temporary Target` | Temporary glucose target | `targetTop`, `targetBottom`, `duration` |
| `Temporary Override` | Loop override activation | `duration`, `insulinNeedsScaleFactor` |
| `Sensor Start` | CGM sensor insertion | `sensorCode` |
| `Sensor Change` | CGM sensor change | `sensorCode` |
| `Site Change` | Pump infusion site change | - |
| `Insulin Change` | Insulin cartridge change | - |
| `Note` | Free-form note | `notes` |
| `Announcement` | Broadcast message | `notes` |
| `Exercise` | Activity record | `duration` |

### Insulin Fields

| Field | Type | Description |
|-------|------|-------------|
| `insulin` | Number | Units delivered |
| `splitNow` | Number | % delivered immediately (combo bolus) |
| `splitExt` | Number | % delivered extended (combo bolus) |

### Carbohydrate Fields

| Field | Type | Description |
|-------|------|-------------|
| `carbs` | Number | Grams of carbohydrates |
| `protein` | Number | Grams of protein |
| `fat` | Number | Grams of fat |
| `absorptionTime` | Number | Expected absorption time (minutes) |

### Basal Modification Fields

| Field | Type | Description |
|-------|------|-------------|
| `duration` | Number | Duration in minutes |
| `percent` | Number | Basal rate as % of scheduled (can be negative) |
| `absolute` | Number | Absolute basal rate (U/hr) |

### Sync Identity Fields

Different AID controllers use different fields for deduplication:

| Controller | Identity Field | Notes |
|------------|----------------|-------|
| AAPS | `identifier` | Custom UUID |
| Loop | `pumpId`, `pumpType`, `pumpSerial` | Pump-centric |
| xDrip | `uuid` | Standard UUID |

---

## Profile Collection

Therapy settings that define dosing parameters.

### Store Structure

Profiles are stored in a `store` object with named profiles:

```javascript
{
  "defaultProfile": "Default",
  "store": {
    "Default": { /* settings */ },
    "Weekend": { /* alternative */ }
  }
}
```

### Profile Settings

| Setting | Type | Description |
|---------|------|-------------|
| `basal` | Array | Basal rates by time of day |
| `sens` | Array | Insulin sensitivity factors |
| `carbratio` | Array | Carb ratios (grams per unit) |
| `target_low` | Array | Low target bound |
| `target_high` | Array | High target bound |
| `dia` | Number | Duration of insulin action (hours) |
| `timezone` | String | IANA timezone identifier |
| `units` | String | `mg/dL` or `mmol/L` |

### Time-Value Format

Settings that vary by time of day use this structure:

```javascript
{ "time": "05:30", "timeAsSeconds": 19800, "value": 1.7 }
```

### Loop-Specific Extensions

Loop adds `loopSettings` for controller configuration:

| Field | Description |
|-------|-------------|
| `maximumBasalRatePerHour` | Max temp basal (U/hr) |
| `maximumBolus` | Max bolus recommendation (U) |
| `dosingStrategy` | `tempBasalOnly` or `automaticBolus` |
| `overridePresets` | Predefined override configurations |

---

## DeviceStatus Collection

Current state of controllers, pumps, and uploaders.

### Controller Status Objects

| Field | Source | Description |
|-------|--------|-------------|
| `loop` | Loop (iOS) | Loop controller state |
| `openaps` | OpenAPS/AAPS | OpenAPS algorithm state |
| `pump` | Various | Pump status and reservoir |
| `uploader` | Various | Uploader device status |

### Common Fields

| Field | Type | Description |
|-------|------|-------------|
| `device` | String | Device identifier |
| `created_at` | String | ISO 8601 timestamp |
| `mills` | Number | Epoch milliseconds |

---

## Data Timestamps

### Timestamp Fields

| Field | Meaning | Set By |
|-------|---------|--------|
| `created_at` | When event was observed/occurred | Client or Server |
| `date` | Event time (epoch ms) | Client |
| `dateString` | Event time (ISO 8601) | Client |
| `srvCreated` | When server first received record | Server |
| `srvModified` | When server last modified record | Server |
| `mills` | Computed epoch ms | Server |

### `created_at` vs `srvCreated`

- `created_at`: When the **event happened** (e.g., insulin given at 8:00 AM)
- `srvCreated`: When the **server learned about it** (e.g., synced at 8:15 AM)

This distinction is critical for offline-first sync patterns used by AAPS and Loop.

---

## Data Authority

### Who Is Authoritative?

| Data Type | Authority | Notes |
|-----------|-----------|-------|
| Glucose readings | CGM device | Via entries collection |
| Delivered insulin | Pump | Confirmed by pump |
| Carb entry | User | Manual entry |
| Profile settings | User | Configured in app |
| Algorithm decisions | Controller | Loop/AAPS/Trio |

### Authority Hierarchy (for Conflict Resolution)

| Level | Actor | Examples |
|-------|-------|----------|
| 100 | Human (Primary) | PWD activating override |
| 80 | Human (Caregiver) | Parent adjusting settings |
| 50 | Agent | AI assistant suggesting changes |
| 30 | Controller | AID algorithm (Loop/AAPS) |
| 10 | System | Automated processes |

---

## Consumer Insights (from Nightscout Reporter)

Analysis of Nightscout Reporter (a Dart/AngularDart reporting client) reveals practical implementation patterns for consuming this data model.

### Entry Validation

| Condition | Interpretation |
|-----------|----------------|
| `sgv < 20` | Gap/sensor error - treat as missing data |
| `sgv > 1000` | Invalid reading - treat as missing data |
| `type == null && sgv > 0` | Infer `type = "sgv"` |
| `type == null && mbg > 0` | Infer `type = "mbg"` |

### Uploader Detection

The `enteredBy` field can identify the data source:

| Pattern | Uploader |
|---------|----------|
| `== "openaps"` (exact) | OpenAPS |
| `contains("androidaps")` | AAPS |
| `startsWith("xdrip")` | xDrip+ |
| `== "spike"` (exact) | Spike iOS |
| `== "tidepool"` (exact) | Tidepool |

**Gap**: Loop and Trio are not explicitly detected by most consumers.

### Treatment Duration Units

**Important**: Nightscout stores duration in **minutes**. Reporter converts to seconds during parsing (`duration * 60`). Always verify units when reading from different sources.

### Temp Basal Resolution Priority

When `percent`, `absolute`, and `rate` are all present:

1. Use `percent` to calculate from scheduled basal
2. Use `rate` as direct value
3. Use `absolute` as fallback (uploader-dependent behavior)

### Bolus Classification

| Classification | Logic |
|----------------|-------|
| Meal bolus | `eventType == "meal bolus"` |
| Carb bolus | `isMealBolus OR (isBolusWizard AND carbs > 0)` |
| Correction | `NOT isCarbBolus AND NOT isSMB` |
| SMB | `isSMB == true` flag |

### Blood Glucose Source

Two ways to identify fingerstick readings:

1. `glucoseType == "finger"` - Explicit field
2. `eventType == "bg check"` - Event-based

### Profile Time Resolution

1. Sort entries by `time`
2. If first entry doesn't start at midnight, wrap last entry's value
3. Calculate duration as gap to next entry
4. Handle timezone offset via `localDiff`

### Unit Conversion

| Conversion | Formula |
|------------|---------|
| mg/dL → mmol/L | `value / 18.02` |
| mmol/L → mg/dL | `value * 18.02` |

Display precision:
- mg/dL: Integer (0 decimal places)
- mmol/L: 2 decimal places

### IOB Calculation Model

Reporter uses a bilinear decay model:

| Phase | Time | Curve |
|-------|------|-------|
| Pre-peak | 0-75 min | Rising activity |
| Post-peak | 75-180 min | Declining |
| Depleted | >180 min | Zero IOB |

Default DIA: 3 hours (scaled by `3.0 / dia` factor)

### COB Calculation Model

- **Delay**: 20 minutes before absorption starts
- **Rate**: `carbs_hr` from profile (default 12g/hr)
- **Model**: Linear decay after delay period

---

## Server-Side Processing (from Source Code Analysis)

Deep analysis of the cgm-remote-monitor source code reveals important implementation details.

### Treatment Field Transformations

**Source:** `lib/server/treatments.js:prepareData()`

When treatments are saved, the server applies these transformations:

| Transformation | Details |
|----------------|---------|
| Timestamp normalization | `created_at` parsed via moment.js, converted to UTC ISO 8601 |
| UTC offset extraction | `utcOffset` auto-set from parsed timestamp |
| Numeric coercion | `glucose`, `targetTop`, `targetBottom`, `carbs`, `insulin`, `duration`, `percent`, `absolute`, `relative`, `preBolus` all cast via `Number()` |
| Empty field cleanup | Fields with value 0, empty string, or NaN are deleted (except `duration`, `absolute`) |
| Event time override | If `eventTime` is present, it overwrites `created_at`, then `eventTime` is deleted |
| Announcement flag | `eventType: "Announcement"` sets `isAnnouncement: true` |

### Pre-Bolus Handling (Undocumented Feature)

When `preBolus` field is set on a treatment:
1. Carbs are removed from the original record
2. A second treatment is created, offset by `preBolus` minutes
3. The delayed record receives the carbs
4. Both records share the same `eventType`

### WebSocket Deduplication Logic

**Source:** `lib/server/websocket.js`

Two-tier deduplication for treatments via WebSocket:

**Tier 1 - Exact Match:**
```
{ NSCLIENT_ID: value } OR { created_at, eventType }
```

**Tier 2 - Similar Match (±2 seconds):**
```
created_at within ±2000ms AND matching:
  - insulin (if present)
  - carbs (if present)
  - percent (if present)
  - absolute (if present)
  - duration (if present)
  - NSCLIENT_ID (if present)
```

### Default Values Applied by Server

**Note:** Defaults differ between ingestion paths. Be aware of which path your client uses.

| Condition | Default | Path |
|-----------|---------|------|
| Missing `eventType` | `<none>` | WebSocket (`dbAdd` only) |
| Missing `created_at` | Current server time | WebSocket (`dbAdd` only) |
| Missing `created_at` | `moment()` fallback | REST API (`treatments.js`) |

**WebSocket path** (`lib/server/websocket.js:357-361`):
```javascript
if (data.collection === 'treatments' && !('eventType' in data.data)) {
  data.data.eventType = '<none>';
}
if (!('created_at' in data.data)) {
  data.data.created_at = new Date().toISOString();
}
```

**REST API path** (`lib/server/treatments.js:203`): Uses `moment()` which defaults to current time if parsing fails.

**API v3 path**: No automatic defaults for `eventType` - requires `date` field (not `created_at`). Uses `API3_CREATED_AT_FALLBACK_ENABLED` to optionally populate `created_at` from `date`.

### API v3 Immutable Fields

**Source:** `lib/api3/generic/update/validate.js`

These fields are enforced as immutable by the API v3 validation layer. Attempts to change them via UPDATE or PATCH return HTTP 400 with message "field {name} cannot be modified":

```javascript
const immutable = ['identifier', 'date', 'utcOffset', 'eventType', 'device', 'app',
  'srvCreated', 'subject', 'srvModified', 'modifiedBy', 'isValid'];
```

| Field | Set By | Notes |
|-------|--------|-------|
| `identifier` | Server (auto-generated) | Exception: allowed during deduplication for API v1 docs |
| `date` | Client on create | Immutable after creation |
| `utcOffset` | Parsed from date | Immutable after creation |
| `eventType` | Client on create | Immutable after creation (treatments) |
| `device` | Client on create | Immutable after creation |
| `app` | Client on create | Immutable after creation |
| `srvCreated` | Server | Set on first insert |
| `srvModified` | Server | Updated on each modification |
| `subject` | Server (from JWT) | Set on creation |
| `modifiedBy` | Server | Set on PATCH operations |
| `isValid` | Server | Set false on delete |

**Note:** Documents with `isReadOnly=true` (or `readOnly`/`readonly` variants) reject all modifications with HTTP 422.

### Indexed Fields (Treatments)

```javascript
['created_at', 'eventType', 'insulin', 'carbs', 'glucose', 
 'enteredBy', 'boluscalc.foods._id', 'notes', 'NSCLIENT_ID',
 'percent', 'absolute', 'duration',
 { 'eventType': 1, 'duration': 1, 'created_at': 1 }]
```

---

## API v3 Deduplication Rules

When creating documents via API v3 with `API3_DEDUP_FALLBACK_ENABLED=true`:

| Collection | Duplicate Criteria |
|------------|-------------------|
| `devicestatus` | `created_at` + `device` |
| `entries` | `date` + `type` |
| `food` | `created_at` |
| `profile` | `created_at` |
| `treatments` | `created_at` + `eventType` |

Duplicates trigger UPDATE instead of INSERT, returning 200 with `isDeduplication=true`.

---

## Known Implementation Gaps

| Gap ID | Description | Impact |
|--------|-------------|--------|
| GAP-001 | No `superseded`/`supersededBy` fields | Cannot track override chains |
| GAP-002 | Controller sync identity not standardized | Multiple dedup code paths |
| GAP-003 | No formal schema validation layer | Client-dependent validation |
| GAP-004 | `eventType` is free-form string | No enumeration enforcement |
| GAP-005 | No authority field on documents | Cannot determine writer type |

---

## Cross-References

- [Treatments Schema (detailed)](../../externals/cgm-remote-monitor/docs/data-schemas/treatments-schema.md)
- [Profiles Schema (detailed)](../../externals/cgm-remote-monitor/docs/data-schemas/profiles-schema.md)
- [Architecture Overview](../../externals/cgm-remote-monitor/docs/architecture-overview.md)
- [Source Code Synthesis](../60-research/cgm-remote-monitor-source-synthesis.md)
- [API v3 Summary](../../specs/openapi/nightscout-api3-summary.md)
- [Glossary](./glossary.md)
- [mapping/nightscout/](../../mapping/nightscout/) - Core NS collection mappings
- [mapping/nightscout-reporter/](../../mapping/nightscout-reporter/) - Consumer perspective from Reporter

---

## Revision History

| Date | Author | Changes |
|------|--------|---------|
| 2026-01-16 | Agent | Added server-side processing details from source code analysis |
| 2026-01-16 | Agent | Added implementation gaps and API v3 dedup rules |
| 2026-01-16 | Agent | Added consumer insights from Nightscout Reporter analysis |
| 2026-01-16 | Agent | Initial extraction from cgm-remote-monitor documentation |
