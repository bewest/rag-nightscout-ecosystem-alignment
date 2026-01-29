# Nocturne Data Connectors

> **Source**: `externals/nocturne/src/Connectors/`  
> **Last Updated**: 2026-01-29

Nocturne provides 8 native data connectors, each implementing a common interface pattern.

---

## Connector Overview

| Connector | Data Source | Auth Method | Data Types |
|-----------|-------------|-------------|------------|
| **Dexcom** | Dexcom Share | Username/password | SGV, calibrations |
| **FreeStyle** | LibreLinkUp | OAuth | SGV |
| **Glooko** | Glooko API | OAuth | SGV, treatments |
| **MiniMed** | CareLink | Username/password | SGV, pump data |
| **MyFitnessPal** | MFP API | OAuth | Food entries |
| **Nightscout** | NS API v1/v3 | API_SECRET | All collections |
| **TConnectSync** | t:connect | OAuth | Pump data, treatments |
| **Tidepool** | Tidepool API | OAuth | All data types |

---

## Common Interface

**Source**: `src/Connectors/Nocturne.Connectors.Core/Interfaces/IConnectorService.cs`

```csharp
public interface IConnectorService<TConfig> where TConfig : IConnectorConfiguration
{
    Task<bool> AuthenticateAsync();
    Task<IEnumerable<Entry>> FetchGlucoseDataAsync(DateTime since);
    Task<IEnumerable<Treatment>> FetchTreatmentsAsync(DateTime since);
}
```

All connectors:
1. Implement this interface
2. Return Nocturne domain models
3. Handle authentication internally
4. Support incremental sync via `since` parameter

---

## Dexcom Connector

**Source**: `src/Connectors/Nocturne.Connectors.Dexcom/`

### Configuration

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `Username` | string | ✅ | Dexcom account email |
| `Password` | string | ✅ | Dexcom account password |
| `Region` | string | ✅ | us, eu, jp, au |
| `ApplicationId` | string | ❌ | OAuth app ID (defaults to Share) |

### Field Mapping (Dexcom → Nocturne)

| Dexcom Field | Nocturne Field | Notes |
|--------------|----------------|-------|
| `WT` | `Mills` | Dexcom timestamp format |
| `Value` | `Sgv` | Glucose value (mg/dL) |
| `Trend` | `Direction` | Numeric → arrow conversion |

### Trend Mapping

| Dexcom Trend | Direction |
|--------------|-----------|
| 1 | DoubleUp |
| 2 | SingleUp |
| 3 | FortyFiveUp |
| 4 | Flat |
| 5 | FortyFiveDown |
| 6 | SingleDown |
| 7 | DoubleDown |

---

## FreeStyle (LibreLinkUp) Connector

**Source**: `src/Connectors/Nocturne.Connectors.FreeStyle/`

### Configuration

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `Email` | string | ✅ | LibreLinkUp email |
| `Password` | string | ✅ | LibreLinkUp password |
| `Region` | string | ✅ | ae, ap, au, ca, de, eu, fr, jp, us |
| `PatientId` | string | ❌ | For multi-patient accounts |

### Field Mapping (LibreLinkUp → Nocturne)

| LibreLinkUp Field | Nocturne Field | Notes |
|-------------------|----------------|-------|
| `Timestamp` | `Mills` | ISO 8601 parsed |
| `ValueInMgPerDl` | `Sgv` | Already mg/dL |
| `TrendArrow` | `Direction` | Numeric → arrow |
| `MeasurementColor` | N/A | Not mapped |

---

## Glooko Connector

**Source**: `src/Connectors/Nocturne.Connectors.Glooko/`

### Configuration

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `Email` | string | ✅ | Glooko email |
| `Password` | string | ✅ | Glooko password |

### Data Types Fetched

| Glooko Type | Nocturne Type | Notes |
|-------------|---------------|-------|
| `glucose` | Entry (sgv) | CGM readings |
| `bloodGlucose` | Entry (mbg) | Fingerstick |
| `meal` | Treatment (Meal Bolus) | With carbs |
| `insulin` | Treatment (Bolus) | Insulin doses |

---

## MiniMed (CareLink) Connector

**Source**: `src/Connectors/Nocturne.Connectors.MiniMed/`

### Configuration

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `Username` | string | ✅ | CareLink username |
| `Password` | string | ✅ | CareLink password |
| `Country` | string | ✅ | Country code |
| `Language` | string | ❌ | Language preference |

### Field Mapping (CareLink → Nocturne)

| CareLink Field | Nocturne Field | Notes |
|----------------|----------------|-------|
| `sg` | `Sgv` | Sensor glucose |
| `datetime` | `Mills` | Parsed to Unix ms |
| `sensorState` | `Noise` | Mapped to noise level |

---

## Nightscout Connector

**Source**: `src/Connectors/Nocturne.Connectors.Nightscout/`

### Configuration

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `Url` | string | ✅ | Nightscout instance URL |
| `ApiSecret` | string | ✅ | API_SECRET |
| `UseV3` | bool | ❌ | Prefer v3 API (default: true) |

### Sync Behavior

1. Uses v3 API by default (incremental sync via `srvModified`)
2. Falls back to v1 for older servers
3. Syncs: entries, treatments, devicestatus, profiles
4. Preserves original `_id` for deduplication

---

## TConnectSync Connector

**Source**: `src/Connectors/Nocturne.Connectors.TConnectSync/`

### Configuration

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `Email` | string | ✅ | t:connect email |
| `Password` | string | ✅ | t:connect password |

### Field Mapping (t:connect → Nocturne)

| t:connect Field | Nocturne Field | EventType |
|-----------------|----------------|-----------|
| `Bolus` | Treatment | `Correction Bolus` / `Meal Bolus` |
| `BasalRate` | Treatment | `Temp Basal` |
| `CartridgeChange` | Treatment | `Insulin Change` |
| `SiteChange` | Treatment | `Site Change` |

---

## Tidepool Connector

**Source**: `src/Connectors/Nocturne.Connectors.Tidepool/`

### Configuration

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `Email` | string | ✅ | Tidepool email |
| `Password` | string | ✅ | Tidepool password |
| `UserId` | string | ❌ | Target user (for shared access) |

### Data Types Fetched

| Tidepool Type | Nocturne Type | Notes |
|---------------|---------------|-------|
| `cbg` | Entry (sgv) | CGM readings |
| `smbg` | Entry (mbg) | Fingerstick |
| `bolus` | Treatment | Bolus events |
| `basal` | Treatment | Basal rate changes |
| `food` | Treatment | Carb entries |

---

## Comparison: Nocturne vs Bridge Projects

| Feature | Nocturne Connectors | share2nightscout-bridge | nightscout-librelink-up |
|---------|---------------------|------------------------|-------------------------|
| Architecture | Native integration | Standalone bridge | Standalone bridge |
| Auth storage | Secure vault | Environment vars | Environment vars |
| Multi-source | ✅ 8 sources | ❌ Dexcom only | ❌ Libre only |
| Scheduling | Built-in | Cron/systemd | Cron/systemd |
| Retry logic | Polly policies | Basic retry | Basic retry |
| Historical sync | ✅ Backfill | Limited | ❌ No backfill |

---

## Gaps

| Gap ID | Description | Notes |
|--------|-------------|-------|
| GAP-CONNECTOR-001 | No xDrip+ connector | Would need local API |
| GAP-CONNECTOR-002 | No Eversense connector | Limited API availability |
| GAP-CONNECTOR-003 | Medtronic requires web scraping | No official API |

---

## Cross-References

- [nightscout-librelink-up Deep Dive](../../docs/10-domain/nightscout-librelink-up-deep-dive.md)
- [share2nightscout-bridge Deep Dive](../../docs/10-domain/share2nightscout-bridge-deep-dive.md)
- [tconnectsync Deep Dive](../../docs/10-domain/tconnectsync-deep-dive.md)
