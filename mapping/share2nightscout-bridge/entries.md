# Dexcom → Nightscout Entry Mapping

> **Source**: `externals/share2nightscout-bridge/index.js:226-247`  
> **Last Updated**: 2026-01-29

Field mappings for transforming Dexcom Share glucose data to Nightscout entries.

---

## Transformation Function

**Source**: `index.js:226-247`

```javascript
function dex_to_entry(d) {
  var regex = /\((.*)\)/;
  var wall = parseInt(d.WT.match(regex)[1]);  // Extract timestamp from WT
  var date = new Date(wall);
  var trend = matchTrend(d.Trend);
  
  return {
    sgv: d.Value,
    date: wall,
    dateString: date.toISOString(),
    trend: trend,
    direction: trendToDirection(trend),
    device: 'share2',
    type: 'sgv'
  };
}
```

---

## Field Mapping

| Dexcom Field | Nightscout Field | Type | Transform |
|--------------|------------------|------|-----------|
| `Value` | `sgv` | number | Direct (mg/dL) |
| `WT` | `date` | number | Extract epoch ms from `/Date(X)/` |
| `WT` | `dateString` | string | Convert to ISO-8601 |
| `Trend` | `trend` | number | Direct (0-9) |
| `Trend` | `direction` | string | Map to arrow name |
| - | `device` | string | Fixed: `"share2"` |
| - | `type` | string | Fixed: `"sgv"` |

### Fields NOT Mapped

| Dexcom Field | Reason |
|--------------|--------|
| `DT` | Display time (local) - not used |
| `ST` | System time (UTC) - WT preferred |

---

## Trend Mapping

**Source**: `index.js:56-66`

| Dexcom Trend | Nightscout Direction | Arrow |
|--------------|---------------------|-------|
| 0 | `None` | - |
| 1 | `DoubleUp` | ⇈ |
| 2 | `SingleUp` | ↑ |
| 3 | `FortyFiveUp` | ↗ |
| 4 | `Flat` | → |
| 5 | `FortyFiveDown` | ↘ |
| 6 | `SingleDown` | ↓ |
| 7 | `DoubleDown` | ⇊ |
| 8 | `NOT COMPUTABLE` | ? |
| 9 | `RATE OUT OF RANGE` | ⚠ |

---

## Output Example

**Dexcom Response**:
```json
{
  "DT": "/Date(1426292016000-0700)/",
  "ST": "/Date(1426295616000)/",
  "Trend": 4,
  "Value": 101,
  "WT": "/Date(1426292039000)/"
}
```

**Nightscout Entry**:
```json
{
  "sgv": 101,
  "date": 1426292039000,
  "dateString": "2015-03-13T23:00:39.000Z",
  "trend": 4,
  "direction": "Flat",
  "device": "share2",
  "type": "sgv"
}
```

---

## Nightscout Upload

### Entries Endpoint

**Endpoint**: `POST /api/v1/entries.json`

**Headers**:
```
Content-Type: application/json
api-secret: <sha1-hash-of-API_SECRET>
```

**Body**: Array of entry objects

### Device Status (Battery)

Also sends a devicestatus to hide battery indicator:

**Endpoint**: `POST /api/v1/devicestatus.json`

**Body**:
```json
{
  "uploaderBattery": false
}
```

---

## Comparison with Other CGM Bridges

| Feature | share2nightscout-bridge | nightscout-librelink-up | Nocturne Dexcom |
|---------|------------------------|-------------------------|-----------------|
| Glucose field | `sgv` | `sgv` | `Sgv` (C#) |
| Timestamp | `WT` (epoch ms) | ISO-8601 parsed | `Mills` |
| Trend | Numeric + string | Numeric only | Enum |
| Device ID | `"share2"` | `"nightscout-librelink-up"` | `"nocturne-dexcom"` |
| API version | v1 only | v1 only | v1/v3 |

---

## Unit Conventions

| Data Type | Dexcom Unit | Nightscout Unit | Conversion |
|-----------|-------------|-----------------|------------|
| Glucose | mg/dL | mg/dL | None |
| Timestamp | Epoch ms | Epoch ms | Extract from `/Date(X)/` |
| Trend | 0-9 enum | 0-9 enum + string | Map to direction |

---

## Gaps

### GAP-SHARE-001: No API v3 Support

The bridge uses Nightscout API v1 only. Does not set:
- `identifier` (for deduplication)
- `srvModified` (for sync tracking)

**Impact**: Duplicates possible on restart or overlap.

### GAP-SHARE-002: No Backfill Logic

No gap detection. If bridge is offline, missed readings are not backfilled.

**Impact**: Data gaps during downtime.

---

## Cross-References

- [Nightscout Entries Schema](../../specs/openapi/aid-entries-2025.yaml)
- [Duration/utcOffset Analysis](../../docs/10-domain/duration-utcoffset-unit-analysis.md)
- [nightscout-librelink-up Mapping](../nightscout-librelink-up/) (if exists)
