# Nightscout API Backlog

> **Domain**: Nightscout collections, API v3, authentication  
> **Parent**: [ECOSYSTEM-BACKLOG.md](../ECOSYSTEM-BACKLOG.md)  
> **Last Updated**: 2026-01-29

Covers: cgm-remote-monitor, entries, treatments, devicestatus, profile

---

## Active Items

| # | Item | Priority | Effort | Notes |
|---|------|----------|--------|-------|
| 1 | Extract Nightscout v3 treatments schema | P1 | Medium | → Ready Queue (ECOSYSTEM-BACKLOG) |
| 2 | cgm-remote-monitor: Database layer audit | P0 | Medium | → Ready Queue #2, mongo-5x branch |
| 3 | cgm-remote-monitor: API layer audit | P0 | Medium | Queued after DB layer |
| 4 | cgm-remote-monitor: Plugin system audit | P0 | Medium | Queued |
| 5 | cgm-remote-monitor: Sync/upload audit | P0 | Medium | Queued |
| 6 | cgm-remote-monitor: Authentication audit | P0 | Medium | Queued |
| 7 | Compare remote bolus handling | P1 | Medium | → Ready Queue |
| 8 | Deep dive: Authentication flows | P2 | Medium | After chunked audit |
| 9 | Playwright adoption proposal | P1 | Low | → Ready Queue #5 |
| 10 | Audit: Nocturne architecture | P1 | Medium | OQ-020 modernization path |
| 11 | **Minimal Interop Spec v1** | P1 | Medium | OQ-021 - fields identified, need formal spec |

### Minimal Interop Spec v1 Details (OQ-021)

**Status**: Fields identified via code analysis (2026-01-29), formal spec creation pending.

**Treatment Fields (Common Ground)**:
| Field | Type | Description |
|-------|------|-------------|
| `created_at` | ISO 8601 | When treatment occurred |
| `eventType` | string | Classification |
| `enteredBy` | string | Source identifier |
| `insulin` | number | Bolus units (for bolus) |
| `carbs` | number | Grams (for carb events) |

**DeviceStatus Fields (Common Ground)**:
| Field | Type | Description |
|-------|------|-------------|
| `device` | string | APS system ID |
| `date`/`mills` | timestamp | When generated |
| `openaps.iob` | number | Insulin on board |
| `pump.battery.percent` | number | Pump battery % |
| `pump.reservoir` | number | Reservoir units |
| `uploader.battery` | number | Phone battery % |

**Behaviors**:
- Timestamp: ISO 8601 UTC (REQ-010)
- Batch order: Preserved (REQ-036)
- Deduplication: `created_at` + `eventType` + `device`

**Next Step**: Create `specs/minimal-interop-v1.yaml` (OpenAPI 3.0 format)

---

## Completed

| Item | Date | Notes |
|------|------|-------|
| DeviceStatus deep dive | 2026-01-21 | Loop vs oref0 structure documented |
| Treatments collection analysis | 2026-01-20 | eventTypes catalog |

---

## References

- [docs/10-domain/devicestatus-deep-dive.md](../../10-domain/devicestatus-deep-dive.md)
- [specs/openapi/aid-treatments-2025.yaml](../../../specs/openapi/aid-treatments-2025.yaml)
- [specs/openapi/aid-devicestatus-2025.yaml](../../../specs/openapi/aid-devicestatus-2025.yaml)
- [mapping/nightscout/README.md](../../../mapping/nightscout/README.md)
