# LibreLink Up → Nightscout Entry Mapping

> **Source**: `externals/nightscout-librelink-up/src/nightscout/`  
> **Transform**: `GlucoseItem` → Nightscout Entry

## Overview

nightscout-librelink-up transforms LibreLink Up `GlucoseItem` objects into Nightscout SGV entries for upload via the v1 API.

---

## Field Mapping

### Core Fields

| LibreLink Field | Type | Nightscout Field | Type | Notes |
|-----------------|------|------------------|------|-------|
| `ValueInMgPerDl` | number | `sgv` | number | Always mg/dL (converted if needed) |
| `FactoryTimestamp` | string | `date` | number | Epoch milliseconds |
| `FactoryTimestamp` | string | `dateString` | string | ISO 8601 |
| `TrendArrow` | number | `direction` | string | Mapped via enum (see below) |
| - | - | `type` | string | Always `"sgv"` |
| - | - | `device` | string | `"nightscout-librelink-up"` |

### Unmapped LibreLink Fields

| Field | Type | Purpose | Why Not Mapped |
|-------|------|---------|----------------|
| `Timestamp` | string | Local phone time | Factory time used instead |
| `TrendMessage` | string | Localized trend | Direction enum preferred |
| `MeasurementColor` | number | In-range indicator | Nightscout calculates own |
| `GlucoseUnits` | number | Display unit | Always use mg/dL |
| `Value` | number | Native unit value | Use ValueInMgPerDl |

---

## Transform Function

**Source**: `src/nightscout/apiv1.ts`

```typescript
// Internal Entry interface
interface Entry {
  date: Date;
  sgv: number;
  direction?: Direction;
}

// Transform for v1 upload
const entriesV1 = entries.map((e) => ({
  type: "sgv",
  sgv: e.sgv,
  direction: e.direction?.toString(),
  device: "nightscout-librelink-up",
  date: e.date.getTime(),
  dateString: e.date.toISOString(),
}));
```

---

## Trend Arrow Mapping

### LibreLink → Nightscout Direction

| LibreLink Value | LibreLink Meaning | Nightscout Direction |
|-----------------|-------------------|---------------------|
| 1 | Falling fast | `SingleDown` |
| 2 | Falling | `FortyFiveDown` |
| 3 | Stable | `Flat` |
| 4 | Rising | `FortyFiveUp` |
| 5 | Rising fast | `SingleUp` |
| null/undefined | No trend data | `NOT COMPUTABLE` |

**Source**: `src/nightscout/interface.ts`

```typescript
enum Direction {
  SingleDown = "SingleDown",
  FortyFiveDown = "FortyFiveDown",
  Flat = "Flat",
  FortyFiveUp = "FortyFiveUp",
  SingleUp = "SingleUp",
  NOT_COMPUTABLE = "NOT COMPUTABLE"
}
```

### Missing Directions

Nightscout supports 9 direction values, but LibreLink only provides 5:

| Nightscout Direction | LibreLink Support |
|---------------------|-------------------|
| `DoubleUp` | ❌ Not available |
| `SingleUp` | ✅ TrendArrow=5 |
| `FortyFiveUp` | ✅ TrendArrow=4 |
| `Flat` | ✅ TrendArrow=3 |
| `FortyFiveDown` | ✅ TrendArrow=2 |
| `SingleDown` | ✅ TrendArrow=1 |
| `DoubleDown` | ❌ Not available |
| `NOT COMPUTABLE` | ✅ null/undefined |
| `RATE OUT OF RANGE` | ❌ Not available |

**Gap Reference**: GAP-LIBRELINK-003

---

## Timestamp Handling

### FactoryTimestamp vs Timestamp

| Field | Source | Use |
|-------|--------|-----|
| `FactoryTimestamp` | Sensor (factory calibrated) | **Used for Nightscout** |
| `Timestamp` | Phone local time | Not used |

The bridge uses `FactoryTimestamp` because:
1. It represents actual measurement time
2. It's independent of phone timezone changes
3. It's more accurate for historical data

### Conversion

```typescript
// FactoryTimestamp is ISO 8601 string
const factoryTimestamp = "2026-01-29T12:30:00Z";

// Convert to Nightscout fields
const date = new Date(factoryTimestamp);
const entry = {
  date: date.getTime(),              // 1738153800000
  dateString: date.toISOString(),    // "2026-01-29T12:30:00.000Z"
};
```

---

## API v1 Upload

### Endpoint

`POST /api/v1/entries`

### Headers

```
api-secret: sha1({NIGHTSCOUT_API_TOKEN})
Content-Type: application/json
```

### Payload

```json
[
  {
    "type": "sgv",
    "sgv": 120,
    "direction": "Flat",
    "device": "nightscout-librelink-up",
    "date": 1738153800000,
    "dateString": "2026-01-29T12:30:00.000Z"
  }
]
```

---

## API v3 Status

**Source**: `src/nightscout/apiv3.ts`

```typescript
// Not implemented - throws error
throw Error("Not implemented");
```

The v3 client exists but is not functional. This means:

| Missing Feature | Impact |
|-----------------|--------|
| No `identifier` field | No sync tracking |
| No deduplication | Duplicates on restart |
| No `srvModified` | No update detection |

**Gap Reference**: GAP-LIBRELINK-001

---

## Deduplication

### Current Behavior

No explicit deduplication. Relies on:
1. Nightscout's timestamp-based uniqueness
2. Polling interval (5 min) matching sensor interval

### Risk Scenarios

| Scenario | Result |
|----------|--------|
| Bridge restart mid-cycle | Potential duplicate of last reading |
| Polling interval < sensor interval | Multiple uploads of same reading |
| Network retry on timeout | Potential duplicate |

**Gap Reference**: GAP-LIBRELINK-002 (no backfill, but also no dedupe)

---

## Comparison with Other Bridges

### Entry Field Coverage

| Field | share2nightscout-bridge | nightscout-librelink-up |
|-------|------------------------|------------------------|
| `type` | `"sgv"` | `"sgv"` |
| `sgv` | ✅ | ✅ |
| `direction` | ✅ (9 values) | ✅ (5 values) |
| `device` | `"share2"` | `"nightscout-librelink-up"` |
| `date` | ✅ | ✅ |
| `dateString` | ✅ | ✅ |
| `noise` | ❌ | ❌ |
| `filtered` | ❌ | ❌ |
| `unfiltered` | ❌ | ❌ |
| `rssi` | ❌ | ❌ |

### Timestamp Format

| Bridge | Source Format | Parsing |
|--------|---------------|---------|
| share2nightscout-bridge | `/Date(epoch-offset)/` | Regex |
| nightscout-librelink-up | ISO 8601 | `new Date()` |
| tconnectsync | ISO 8601 | Standard |

---

## Example Transform

### Input (GlucoseItem)

```json
{
  "FactoryTimestamp": "1/29/2026 12:30:00 PM",
  "Timestamp": "1/29/2026 7:30:00 AM",
  "ValueInMgPerDl": 120,
  "TrendArrow": 3,
  "TrendMessage": "Stable",
  "MeasurementColor": 1,
  "GlucoseUnits": 0,
  "Value": 120
}
```

### Output (Nightscout Entry)

```json
{
  "type": "sgv",
  "sgv": 120,
  "direction": "Flat",
  "device": "nightscout-librelink-up",
  "date": 1738153800000,
  "dateString": "2026-01-29T12:30:00.000Z"
}
```

---

## Gaps Summary

| Gap ID | Issue | Impact |
|--------|-------|--------|
| GAP-LIBRELINK-001 | No v3 API | No sync identity, no dedup |
| GAP-LIBRELINK-002 | No backfill | Data gaps if offline |
| GAP-LIBRELINK-003 | Only 5 trend values | No DoubleUp/DoubleDown |
