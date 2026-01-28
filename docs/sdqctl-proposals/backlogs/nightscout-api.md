# Nightscout API Backlog

> **Domain**: Nightscout collections, API v3, authentication  
> **Parent**: [ECOSYSTEM-BACKLOG.md](../ECOSYSTEM-BACKLOG.md)  
> **Last Updated**: 2026-01-28

Covers: cgm-remote-monitor, entries, treatments, devicestatus, profile

---

## Active Items

| # | Item | Priority | Effort | Notes |
|---|------|----------|--------|-------|
| 1 | Extract Nightscout v3 treatments schema | P1 | Medium | All supported fields and eventTypes |
| 2 | Full audit: cgm-remote-monitor | P0 | High | API v3, sync, auth, plugin system |
| 3 | Deep dive: Authentication flows | P2 | Medium | API secret vs tokens vs JWT |
| 4 | Compare remote bolus command handling | P1 | Medium | Validation, execution, safety |
| 5 | **Audit: Nocturne architecture** | P1 | Medium | OQ-020 - modernization path analysis |
| 6 | **Interoperability spec draft** | P1 | Medium | OQ-021 - minimal viable spec |

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
