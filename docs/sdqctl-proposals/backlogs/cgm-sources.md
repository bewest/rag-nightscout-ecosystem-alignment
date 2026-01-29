# CGM Sources Backlog

> **Domain**: CGM data sources, protocols, sensor handling  
> **Parent**: [ECOSYSTEM-BACKLOG.md](../ECOSYSTEM-BACKLOG.md)  
> **Last Updated**: 2026-01-29

Covers: xDrip+, xDrip4iOS, DiaBLE, Dexcom G6/G7, Libre 2/3, Medtronic CGM

---

## Active Items

| # | Item | Priority | Effort | Notes |
|---|------|----------|--------|-------|
| 1 | Deep dive: xdrip-js | P3 | Medium | Node.js Dexcom G5/G6 BLE for RPi |
| 2 | CGM trend arrow standardization | P3 | Low | Map all 7 projects to unified enum |
| 3 | Libre 3 protocol gap analysis | P2 | High | Currently "eavesdrop only" - document limits |

---

## Completed

| Item | Date | Notes |
|------|------|-------|
| Extract xDrip+ Nightscout fields | 2026-01-29 | 370 lines, GAP-XDRIP-001..003 |
| Compare CGM sensor session handling | 2026-01-29 | 407 lines deep dive, GAP-SESSION-001..004 |
| Full audit: DiaBLE Libre protocol | 2026-01-29 | 487 lines deep dive, GAP-DIABLE-002/003 |
| Full audit: nightscout-librelink-up | 2026-01-29 | 378 lines, LibreView integration |
| Full audit: tconnectsync | 2026-01-29 | 368 lines, Tandem Control-IQ bridge |
| Dexcom G7 BLE protocol analysis | 2026-01-26 | Deep dive, GAP-G7-001..003 |
| CGM data source terminology | 2026-01-25 | 20+ terms mapped |

---

## References

- [mapping/xdrip/nightscout-fields.md](../../../mapping/xdrip/nightscout-fields.md)
- [docs/10-domain/cgm-session-handling-deep-dive.md](../../10-domain/cgm-session-handling-deep-dive.md)
- [docs/10-domain/nightscout-librelink-up-deep-dive.md](../../10-domain/nightscout-librelink-up-deep-dive.md)
- [docs/10-domain/tconnectsync-deep-dive.md](../../10-domain/tconnectsync-deep-dive.md)
- [docs/10-domain/cgm-data-sources-deep-dive.md](../../10-domain/cgm-data-sources-deep-dive.md)
