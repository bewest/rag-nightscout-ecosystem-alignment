# Nightscout API Backlog

> **Domain**: Nightscout collections, API v3, authentication  
> **Parent**: [ECOSYSTEM-BACKLOG.md](../ECOSYSTEM-BACKLOG.md)  
> **Last Updated**: 2026-01-28

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
| 11 | Interoperability spec draft | P1 | Medium | → Ready Queue #1 |

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
