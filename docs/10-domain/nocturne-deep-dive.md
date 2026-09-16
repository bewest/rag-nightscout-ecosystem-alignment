# Nocturne Deep Dive

> **Source**: `externals/nocturne/`  
> **Version**: main @ 0fe4f7b  
> **Last Updated**: 2026-01-28

Nocturne is a complete .NET 10 rewrite of the Nightscout API with full v1/v2/v3 endpoint compatibility, modern cloud-native architecture, and native data connectors.

---

## Overview

| Metric | Value |
|--------|-------|
| **Language** | C# (.NET 10), Rust (oref), TypeScript (SvelteKit) |
| **C# Files** | 927 |
| **Svelte Components** | 438 |
| **Total C# LOC** | ~334,000 |
| **Database** | PostgreSQL (EF Core) |
| **Cache** | Redis |
| **Orchestration** | .NET Aspire |

---

## Architecture

```
src/
├── API/Nocturne.API           # REST API (Nightscout-compatible)
│   ├── Controllers/V1/        # Legacy v1 endpoints
│   ├── Controllers/V2/        # v2 endpoints (Loop, DData)
│   ├── Controllers/V3/        # Full v3 API implementation
│   └── Controllers/V4/        # Nocturne-native extensions
├── Connectors/                # Data source integrations
│   ├── Dexcom/                # Dexcom Share
│   ├── FreeStyle/             # LibreLinkUp
│   ├── Glooko/                # Glooko platform
│   ├── MiniMed/               # CareLink
│   ├── MyFitnessPal/          # Food logging
│   ├── Nightscout/            # NS-to-NS sync
│   ├── TConnectSync/          # Tandem t:connect
│   └── Tidepool/              # Tidepool platform
├── Core/
│   ├── Nocturne.Core.Models/  # Domain models (Entry, Treatment, etc.)
│   ├── Nocturne.Core.Contracts/ # Service interfaces
│   ├── Nocturne.Core.Oref/    # Rust FFI bindings
│   └── oref/                  # Rust oref implementation
├── Infrastructure/            # Data access, caching
├── Services/                  # Background services
└── Web/                       # SvelteKit frontend
    └── packages/
        ├── app/               # Main SvelteKit app
        └── bridge/            # SignalR→Socket.IO bridge
```

---

## API Compatibility

### Endpoint Coverage

| API Version | Controllers | Status |
|-------------|-------------|--------|
| **v1** | `EntriesController`, `TreatmentsController`, `DeviceStatusController`, `FoodController`, `NotificationsController`, `TimeQueryController` | ✅ Full parity |
| **v2** | `DDataController`, `LoopController`, `PropertiesController`, `SummaryController` | ✅ Full parity |
| **v3** | `EntriesController`, `TreatmentsController`, `DeviceStatusController`, `FoodController`, `ProfileController`, `SettingsController`, `StatusController`, `VersionController` | ✅ Full parity |
| **v4** | `TreatmentsController`, `StateSpansController`, `ChartDataController`, `ProcessingController`, etc. | 🆕 Nocturne-native |

### V3 Entries Example

**Source**: `src/API/Nocturne.API/Controllers/V3/EntriesController.cs:1-70`

```csharp
[ApiController]
[Route("api/v3/[controller]")]
public class EntriesController : BaseV3Controller<Entry>
{
    [HttpGet]
    [NightscoutEndpoint("/api/v3/entries")]
    public async Task<ActionResult> GetEntries(CancellationToken cancellationToken = default)
    {
        var parameters = ParseV3QueryParameters();
        // V3 filter parsing, pagination, field selection, ETag support
        ...
    }
}
```

---

## Core Models

### Entry Model

**Source**: `src/Core/Nocturne.Core.Models/Entry.cs`

| Field | Type | Notes |
|-------|------|-------|
| `Id` | string? | MongoDB ObjectId format |
| `Mills` | long | **Canonical timestamp** (Unix ms) |
| `Date` | DateTime? | Computed from Mills |
| `DateString` | string? | ISO-8601, computed |
| `Sgv` | int? | Sensor glucose value |
| `Direction` | string? | Trend arrow |
| `Noise` | int? | Signal noise level |
| `Device` | string? | Source device |
| `Type` | string? | Entry type (sgv, mbg, cal) |

**Key Pattern**: Mills-first timestamp handling - `Mills` is source of truth, `Date`/`DateString` are computed properties.

### Treatment Model

**Source**: `src/Core/Nocturne.Core.Models/Treatment.cs`

| Field | Type | Notes |
|-------|------|-------|
| `Id` | string? | MongoDB ObjectId |
| `Identifier` | string? | V3 alias for Id |
| `SrvModified` | long? | V3 server timestamp |
| `EventType` | string? | Treatment type |
| `Carbs` | double? | Carbohydrates (g) |
| `Insulin` | double? | Insulin (units) |
| `Duration` | double? | Duration (minutes) |
| `Glucose` | double? | BG value |
| `GlucoseType` | string? | Finger/Sensor |

---

## Data Connectors

| Connector | Source | Auth Method | Data Types |
|-----------|--------|-------------|------------|
| **Dexcom** | Dexcom Share | Username/password | SGV, calibrations |
| **FreeStyle** | LibreLinkUp | OAuth | SGV |
| **Glooko** | Glooko API | OAuth | SGV, treatments |
| **MiniMed** | CareLink | Username/password | SGV, pump data |
| **MyFitnessPal** | MFP API | OAuth | Food entries |
| **Nightscout** | NS API v1/v3 | API_SECRET | All collections |
| **TConnectSync** | t:connect | OAuth | Pump data |
| **Tidepool** | Tidepool API | OAuth | All data types |

### Connector Pattern

**Source**: `src/Connectors/Nocturne.Connectors.Core/`

```csharp
public interface IConnectorService<TConfig> where TConfig : IConnectorConfiguration
{
    Task<bool> AuthenticateAsync();
    Task<IEnumerable<Entry>> FetchGlucoseDataAsync(DateTime since);
    Task<IEnumerable<Treatment>> FetchTreatmentsAsync(DateTime since);
}
```

---

## Oref Implementation (Rust)

**Source**: `src/Core/oref/` (Rust crate)

Nocturne includes a native Rust implementation of the OpenAPS reference algorithms:

| Feature | Status | Notes |
|---------|--------|-------|
| **IOB Calculation** | ✅ | Insulin on Board |
| **COB Calculation** | ✅ | Carbs on Board |
| **Dosing Algorithms** | ✅ | oref0/oref1 logic |
| **FFI Bindings** | ✅ | C# interop via `Nocturne.Core.Oref` |
| **WASM Support** | ✅ | Browser-side calculations |

**Cargo.toml** features:
- `std`, `serde` (default)
- `ffi` - C bindings for .NET
- `wasm` - WebAssembly via wasm-bindgen

---

## Web Frontend

**Stack**: SvelteKit 2 + Svelte 5 (runes) + Tailwind CSS 4 + shadcn-svelte

| Package | Purpose |
|---------|---------|
| `@nocturne/app` | Main SvelteKit application |
| `@nocturne/bridge` | SignalR → Socket.IO bridge |

### Key Patterns

1. **NSwag client** - API types generated from OpenAPI
2. **Remote functions** - Type-safe API wrappers (never raw fetch)
3. **Backend as truth** - No frontend-only models
4. **No frontend calculations** - All math on backend/oref

---

## Database Schema

| Table | Entity | Notes |
|-------|--------|-------|
| `entries` | `EntryEntity` | SGV data |
| `treatments` | `TreatmentEntity` | All treatment types |
| `device_status` | `DeviceStatusEntity` | Loop/AAPS status |
| `profiles` | `ProfileEntity` | Therapy settings |
| `food` | `FoodEntity` | Food database |

**ID Strategy**: UUID v7 for new records, preserve `OriginalId` for MongoDB migration.

---

## Comparison: Nocturne vs cgm-remote-monitor

| Aspect | Nocturne | cgm-remote-monitor |
|--------|----------|-------------------|
| **Language** | C# (.NET 10) | JavaScript (Node.js) |
| **Database** | PostgreSQL | MongoDB |
| **Cache** | Redis | In-memory |
| **Algorithm** | Native Rust oref | JavaScript oref |
| **Orchestration** | .NET Aspire | PM2/Docker |
| **Connectors** | 8 native | Via share2nightscout-bridge |
| **API Parity** | v1/v2/v3 ✅ | v1/v2/v3 (origin) |
| **Frontend** | SvelteKit | Backbone.js |
| **Real-time** | SignalR | Socket.IO |
| **Type Safety** | Full (C#/TypeScript) | Partial |

---

## Ecosystem Implications

### Interoperability

1. **Full API compatibility** - AID apps (Loop, AAPS, Trio) can connect without changes
2. **Data migration path** - MongoDB → PostgreSQL migration tool included
3. **Dual-mode operation** - Can sync FROM existing Nightscout via connector

### Gaps Identified

| Gap ID | Description |
|--------|-------------|
| GAP-NOCTURNE-001 | V4 endpoints are Nocturne-specific, no cross-project standard |
| GAP-NOCTURNE-002 | Rust oref implementation may diverge from JS oref0/oref1 |
| GAP-NOCTURNE-003 | SignalR→Socket.IO bridge adds latency (5-10ms measured) |
| GAP-NOCTURNE-004 | ProfileSwitch percentage/timeshift applied internally (cgm-remote-monitor doesn't) |
| GAP-NOCTURNE-005 | Profile API returns raw values despite active ProfileSwitch |
| GAP-BRIDGE-001 | Bridge missing `clients` event |
| GAP-BRIDGE-002 | Bridge lacks compression |

See also:
- [SignalR Bridge Analysis](nocturne-signalr-bridge-analysis.md) - Event parity and latency
- [ProfileSwitch Analysis](nocturne-profileswitch-analysis.md) - Treatment model handling
- [Percentage/Timeshift Handling](nocturne-percentage-timeshift-handling.md) - API vs internal scaling

### Opportunities

1. **Performance baseline** - Use Nocturne parity tests as conformance suite
2. **Type definitions** - NSwag-generated types could become canonical
3. **oref validation** - Cross-validate Rust vs JS algorithm outputs

---

## Key Source Files

| Purpose | Path |
|---------|------|
| Architecture overview | `AGENTS.md` |
| Entry model | `src/Core/Nocturne.Core.Models/Entry.cs` |
| Treatment model | `src/Core/Nocturne.Core.Models/Treatment.cs` |
| V3 Entries API | `src/API/Nocturne.API/Controllers/V3/EntriesController.cs` |
| Connector interface | `src/Connectors/Nocturne.Connectors.Core/Interfaces/IConnectorService.cs` |
| Oref Rust lib | `src/Core/oref/src/lib.rs` |
| Frontend app | `src/Web/packages/app/` |

---

## Cross-References

- [AAPS NSClient Schema](../../mapping/aaps/nsclient-schema.md) - Field comparison
- [Terminology Matrix](../../mapping/cross-project/terminology-matrix.md) - Term mappings
- [Nightscout API Spec](../../specs/openapi) - OpenAPI schemas
- [cgm-remote-monitor](../../mapping/nightscout) - Original NS server

---

## Next Steps

1. **Compare oref implementations** - Rust vs JavaScript algorithm outputs
2. **Extract V4 endpoint schema** - Document Nocturne-specific extensions
3. **Run parity tests** - Use Nocturne's test suite against cgm-remote-monitor
4. ~~**Profile sync analysis** - Compare profile format handling~~ ✅ Complete - see [ProfileSwitch Analysis](nocturne-profileswitch-analysis.md)
5. **Override/Temporary Target representation** - How Nocturne distinguishes these
6. **Percentage/timeshift when Loop/Trio fetch** - Cross-controller behavior
