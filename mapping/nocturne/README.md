# Nocturne Field Mappings

> **Source**: `externals/nocturne/`  
> **Deep Dive**: [nocturne-deep-dive.md](../../docs/10-domain/nocturne-deep-dive.md)  
> **Last Updated**: 2026-01-30

Nocturne is a .NET 10 rewrite of the Nightscout API with full v1/v2/v3 compatibility and native data connectors.

---

## Documents

| Document | Purpose |
|----------|---------|
| [models.md](models.md) | Core model field mappings (Entry, Treatment, DeviceStatus) |
| [connectors.md](connectors.md) | Data source connector field mappings |
| [api-versions.md](api-versions.md) | API version endpoint coverage |

---

## Architecture Overview

```
Nocturne (.NET 10)
├── API (v1/v2/v3/v4 controllers)
├── Core Models (C# entities)
├── Connectors (8 native data sources)
├── oref (Rust FFI + WASM)
├── Infrastructure (PostgreSQL + Redis)
└── Web (SvelteKit frontend)
```

---

## Key Differences from cgm-remote-monitor

| Aspect | Nocturne | cgm-remote-monitor |
|--------|----------|-------------------|
| Language | C# (.NET 10) | JavaScript (Node.js) |
| Database | PostgreSQL (EF Core) | MongoDB |
| Cache | Redis | In-memory |
| Real-time | SignalR | Socket.IO |
| Connectors | 8 native | External bridges |
| Algorithm | Rust oref (FFI/WASM) | JavaScript oref |
| Type Safety | Full (C#/TypeScript) | Partial |

---

## Gaps

| Gap ID | Description | Status |
|--------|-------------|--------|
| GAP-NOCTURNE-001 | V4 endpoints are Nocturne-specific | Documented |
| GAP-NOCTURNE-002 | Rust oref may diverge from JS oref | Monitoring |
| GAP-NOCTURNE-003 | SignalR→Socket.IO bridge adds latency | Documented |
| GAP-NOCTURNE-004 | ProfileSwitch percentage/timeshift applied (cgm-remote-monitor doesn't) | Documented |
| GAP-NOCTURNE-005 | Profile API returns raw values despite active ProfileSwitch | Documented |
| GAP-SYNC-038 | Profile deduplication fallback missing (no created_at) | Documented |
| GAP-SYNC-039 | Profile srvModified field missing | Documented |
| GAP-SYNC-040 | Profile uses hard delete (cgm-remote-monitor uses soft) | Documented |
| GAP-OREF-001 | PredictionService bypasses ProfileService | Documented |
| GAP-OREF-002 | OrefProfile lacks full schedule support | Documented |
| GAP-OREF-003 | No timeshift propagation to Rust | Documented |
| GAP-OVRD-005 | No unified Override/TempTarget representation | Documented |
| GAP-OVRD-006 | Override supersession not tracked | Documented |
| GAP-OVRD-007 | Duration unit mismatch (preset seconds, treatment minutes) | Documented |
| GAP-V4-001 | V4 StateSpan API not standardized (Nocturne-specific) | Documented |
| GAP-V4-002 | Profile activation history not in V3 | Documented |

---

## Deep Dives

| Document | Focus |
|----------|-------|
| [nocturne-deep-dive.md](../../docs/10-domain/nocturne-deep-dive.md) | Architecture overview |
| [nocturne-profileswitch-analysis.md](../../docs/10-domain/nocturne-profileswitch-analysis.md) | ProfileSwitch treatment handling |
| [nocturne-percentage-timeshift-handling.md](../../docs/10-domain/nocturne-percentage-timeshift-handling.md) | API vs internal scaling behavior |
| [nocturne-cgm-remote-monitor-profile-sync.md](../../docs/10-domain/nocturne-cgm-remote-monitor-profile-sync.md) | Profile sync comparison |
| [nocturne-override-temptarget-analysis.md](../../docs/10-domain/nocturne-override-temptarget-analysis.md) | Override vs TempTarget handling |
| [nocturne-v4-profile-extensions.md](../../docs/10-domain/nocturne-v4-profile-extensions.md) | V4 StateSpan profile endpoints |

---

## Cross-References

- [cgm-remote-monitor mapping](../cgm-remote-monitor/)
- [AAPS NSClient Schema](../aaps/nsclient-schema.md)
- [Cross-Project Terminology](../cross-project/terminology-matrix.md)
- [OpenAPI Specs](../../specs/openapi/)
