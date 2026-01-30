# Nocturne Connector Polling Coordination

> **Date**: 2026-01-30  
> **OQ-010 Extended Item #16**  
> **Status**: Analysis Complete

This document analyzes how Nocturne coordinates multiple connector polling operations.

---

## Executive Summary

| Question | Answer |
|----------|--------|
| **Are polls staggered?** | No - each connector has independent timer |
| **Rate-limit protection** | Per-connector retry with exponential backoff |
| **Loop-back prevention** | DataSource tagging (`data_source` field) |
| **Multi-source dedup** | Server-side via identifier/timestamp matching |

**Architecture**: Sidecar pattern - each connector runs as independent background service with its own polling loop.

---

## Connector Architecture

### Sidecar Pattern

Nocturne uses a sidecar architecture where each connector runs as an independent hosted service:

```
┌─────────────────────────────────────────────────────────┐
│                     Nocturne API                         │
│  ┌─────────────────────────────────────────────────────┐ │
│  │              ConnectorSyncService                   │ │
│  │  - Queries connector health                         │ │
│  │  - Triggers manual sync via HTTP POST               │ │
│  └─────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
         │              │              │              │
         ▼              ▼              ▼              ▼
    ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐
    │ Dexcom  │   │  Libre  │   │MiniMed  │   │Nightscout│
    │Connector│   │Connector│   │Connector│   │Connector │
    │ :5001   │   │ :5002   │   │ :5003   │   │ :5004    │
    └─────────┘   └─────────┘   └─────────┘   └─────────┘
         │              │              │              │
         ▼              ▼              ▼              ▼
    [Dexcom API]  [LibreLinkUp]  [CareLink]   [Upstream NS]
```

### Background Service Hierarchy

```
BackgroundService (dotnet)
    └── ResilientPollingHostedService<TConnector, TConfig>
            └── DexcomHostedService
            └── LibreHostedService
            └── NightscoutHostedService
            └── etc.
```

**Source**: `src/Connectors/Nocturne.Connectors.Core/Services/ResilientPollingHostedService.cs`

---

## Polling Coordination

### Independent Timers (Not Staggered)

Each connector has its own `PeriodicTimer` with configurable `SyncIntervalMinutes`:

```csharp
// ConnectorBackgroundService.cs:60-62
var syncInterval = TimeSpan.FromMinutes(Config.SyncIntervalMinutes);
using var timer = new PeriodicTimer(syncInterval);
```

**No coordination** between connectors - they poll independently based on their configured interval.

### Default Intervals

| Connector | Default Interval | Source |
|-----------|------------------|--------|
| All connectors | 5 minutes | `BaseConnectorConfiguration.cs:86` |
| Nightscout | 1 minute minimum | `NightscoutHostedService.cs:30` |

### Concurrent Execution

Multiple connectors can poll simultaneously. No mutex or semaphore prevents overlapping operations.

**Implication**: Peak load occurs when multiple connectors poll at the same moment.

---

## Rate Limit Protection

### Per-Connector Retry Strategy

Each connector uses `ConnectorRetryPolicy` with exponential backoff:

```csharp
// ConnectorRetryPolicy.cs:45-47
var waitTime = TimeSpan.FromMilliseconds(
    delay.TotalMilliseconds * Math.Pow(2, attempt - 1)
);
```

| Parameter | Default | Notes |
|-----------|---------|-------|
| Max Attempts | 3 | `ExecuteWithRetryAsync` |
| Base Delay | 2 seconds | `ConnectorRetryPolicy.cs:33` |
| Backoff Factor | 2x | Exponential |

### Retriable Errors

```csharp
// ConnectorRetryPolicy.cs:83-89
return exception switch
{
    HttpRequestException => true,
    TaskCanceledException => true,
    TimeoutException => true,
    SocketException => true,
    _ => false,
};
```

### Resilient Polling Mode

`ResilientPollingHostedService` adds adaptive polling:

| State | Polling Interval | Trigger |
|-------|------------------|---------|
| **Healthy** | `NormalPollingInterval` (5 min) | Successful sync |
| **Disconnected** | 10 seconds | First failure |
| **Extended Outage** | Exponential backoff to 5 min | 30+ consecutive failures |

```csharp
// ResilientPollingHostedService.cs:38-49
protected virtual TimeSpan DisconnectedPollingInterval => TimeSpan.FromSeconds(10);
protected virtual int MaxFastPollAttempts => 30; // 5 minutes of fast polling
protected virtual TimeSpan MaxBackoffInterval => TimeSpan.FromMinutes(5);
```

**Feature**: Automatic backfill when connection is restored after disruption.

---

## Loop-Back Prevention

### Question: How does Nightscout→Nocturne connector handle data that came from Nocturne?

**Answer**: DataSource tagging with `data_source` field.

### DataSource Constants

Every record is tagged with its origin:

```csharp
// DataSources.cs:56
public const string NightscoutConnector = "nightscout-connector";
```

| Connector | DataSource Tag |
|-----------|----------------|
| Dexcom | `dexcom-connector` |
| Libre | `libre-connector` |
| MiniMed | `minimed-connector` |
| Glooko | `glooko-connector` |
| Nightscout | `nightscout-connector` |
| Tidepool | `tidepool-connector` |

### Prevention Mechanism

**Gap Identified**: No explicit loop-back filtering visible in `NightscoutConnectorService`.

When syncing from upstream Nightscout to Nocturne:
1. Data fetched from upstream is tagged with `data_source: "nightscout-connector"`
2. If that data is then uploaded to yet another Nightscout... **no filtering occurs**

**Risk**: Data could loop back if:
- Nocturne → Nightscout A (uploads with `device: "Nocturne"`)
- Nightscout A → Nocturne B (fetches, doesn't filter by device)
- Nocturne B → Nightscout A (uploads back)

**Mitigation**: Manual configuration to avoid circular topologies.

---

## Multi-Source Deduplication

### Question: Any deduplication for multi-source same-data?

**Answer**: Server-side deduplication on insert, not connector-side.

### Deduplication Fields

| Collection | Primary Dedup Field | Fallback |
|------------|---------------------|----------|
| entries | `identifier` | `date + device + type` |
| treatments | `identifier` | `created_at + eventType` |
| devicestatus | `identifier` | `created_at + device` |

### Connector Behavior

Connectors do **not** deduplicate before submission. They rely on:
1. **API deduplication**: Server rejects/merges duplicates
2. **Incremental sync**: Only fetch records newer than last sync

```csharp
// NightscoutConnectorService.cs:303-304
if (since.HasValue)
{
    urlBuilder.Append($"&{sortField ?? "date"}$gte={sinceMs}");
}
```

### Cross-Connector Same Data

If Dexcom CGM data appears in both:
- Dexcom connector (direct from Dexcom Share)
- Nightscout connector (from upstream that also uses Dexcom)

**Behavior**: Server deduplicates based on `date + sgv + device`. Same reading = same record.

**Gap**: No explicit cross-connector deduplication logic. Relies on server's general dedup.

---

## Connector Metadata Service

Central registry for all connectors:

```csharp
// ConnectorMetadataService.cs:88-91
public static IReadOnlyCollection<ConnectorDisplayInfo> GetAll()
{
    EnsureInitialized();
    return _connectorsByDataSourceId.Values.ToList().AsReadOnly();
}
```

### Registered Connectors

| Connector | Display Name | Category |
|-----------|--------------|----------|
| Dexcom | Dexcom | CGM |
| FreeStyle | FreeStyle Libre | CGM |
| MiniMed | Medtronic CareLink | CGM |
| Glooko | Glooko | Aggregator |
| Nightscout | Nightscout | Bridge |
| Tidepool | Tidepool | Aggregator |
| MyFitnessPal | MyFitnessPal | Nutrition |

---

## Gap Analysis

### GAP-CONNECT-005: No Connector Poll Staggering

**Description**: Multiple connectors may poll simultaneously, causing API load spikes.

**Impact**: 
- Burst of outbound requests at startup
- Potential rate-limiting if all connectors hit APIs simultaneously

**Remediation**: Add startup jitter or stagger connector initialization.

**Status**: Open (minor impact for typical 2-3 connectors)

---

### GAP-CONNECT-006: No Explicit Loop-Back Prevention

**Description**: Nightscout connector does not filter out data that originated from Nocturne.

**Affected Systems**: Nightscout↔Nocturne bidirectional sync

**Impact**: 
- Circular sync possible with misconfigured topology
- Data may accumulate duplicate sources

**Remediation**: 
1. Filter by `device` or `app` field on fetch
2. Add `enteredBy` exclusion (similar to AAPS `enteredBy[$ne]`)
3. Document recommended topology

**Status**: Open

---

### GAP-CONNECT-007: No Cross-Connector Deduplication

**Description**: Same CGM reading from multiple sources (e.g., Dexcom direct + via upstream Nightscout) handled by server, not connectors.

**Impact**: Relies on server-side dedup which may use different matching criteria.

**Remediation**: Document expected behavior; consider connector-side pre-dedup for known overlap scenarios.

**Status**: Documented (by design)

---

## Requirements

### REQ-CONNECT-010: DataSource Tagging

**Statement**: Connectors MUST tag all submitted data with their `data_source` identifier.

**Rationale**: Enables filtering, auditing, and cleanup by data origin.

**Verification**: Query entries by `data_source`, verify connector attribution.

**Status**: ✅ Implemented (all connectors use `ConnectorSource` property)

---

### REQ-CONNECT-011: Resilient Polling

**Statement**: Connectors SHOULD implement adaptive polling with fast reconnection and exponential backoff.

**Rationale**: Balances quick recovery with API rate-limit respect.

**Verification**: 
- Disconnect network, verify 10s polling begins
- After 30 failures, verify backoff increases

**Status**: ✅ Implemented (`ResilientPollingHostedService`)

---

### REQ-CONNECT-012: Incremental Sync

**Statement**: Connectors SHOULD track last successful sync timestamp and only fetch new data.

**Rationale**: Reduces API load and bandwidth; enables backfill on reconnection.

**Verification**: 
- Initial sync fetches all data in range
- Subsequent syncs only fetch new records

**Status**: ✅ Implemented (`_lastSuccessfulSync` tracking)

---

## Conclusion

Nocturne's connector architecture uses an **independent sidecar pattern** where each connector:

1. **Polls independently** with configurable interval (no coordination)
2. **Retries with backoff** on transient failures
3. **Tags data** with source identifier for provenance
4. **Relies on server** for deduplication

**Key gaps**:
- No poll staggering (minor)
- No explicit loop-back prevention (moderate risk)
- Cross-connector dedup delegated to server (by design)

---

## References

- `src/Connectors/Nocturne.Connectors.Core/Services/ResilientPollingHostedService.cs`
- `src/Connectors/Nocturne.Connectors.Core/Services/ConnectorRetryPolicy.cs`
- `src/Connectors/Nocturne.Connectors.Nightscout/Services/NightscoutConnectorService.cs`
- `src/Core/Nocturne.Core.Constants/DataSources.cs`
- `src/API/Nocturne.API/Services/ConnectorSyncService.cs`
