# CGM Sources Backlog

> **Domain**: CGM data sources, protocols, sensor handling  
> **Parent**: [ECOSYSTEM-BACKLOG.md](../ECOSYSTEM-BACKLOG.md)  
> **Last Updated**: 2026-01-29

Covers: xDrip+, xDrip4iOS, DiaBLE, Dexcom G6/G7, Libre 2/3, Medtronic CGM

---

## Active Items

| # | Item | Priority | Effort | Notes |
|---|------|----------|--------|-------|
| 1 | Compare CGM sensor session handling | P3 | Medium | Start, stop, calibration across systems |
| 2 | Extract xDrip+ Nightscout fields | P3 | Medium | What xDrip+ uploads to NS |
| 3 | Full audit: DiaBLE Libre protocol | P2 | High | BLE traces, calibration |

---

## Completed

| Item | Date | Notes |
|------|------|-------|
| Full audit: nightscout-librelink-up | 2026-01-29 | 378 lines, LibreView integration |
| Full audit: tconnectsync | 2026-01-29 | 368 lines, Tandem Control-IQ bridge |
| Dexcom G7 BLE protocol analysis | 2026-01-26 | Deep dive, GAP-G7-001..003 |
| CGM data source terminology | 2026-01-25 | 20+ terms mapped |

---

## References

- [docs/10-domain/nightscout-librelink-up-deep-dive.md](../../10-domain/nightscout-librelink-up-deep-dive.md)
- [docs/10-domain/tconnectsync-deep-dive.md](../../10-domain/tconnectsync-deep-dive.md)
- [docs/10-domain/cgm-data-sources-deep-dive.md](../../10-domain/cgm-data-sources-deep-dive.md)
