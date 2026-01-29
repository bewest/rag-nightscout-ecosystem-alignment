# share2nightscout-bridge Field Mappings

> **Source**: `externals/share2nightscout-bridge/`  
> **Deep Dive**: [share2nightscout-bridge-deep-dive.md](../../docs/10-domain/share2nightscout-bridge-deep-dive.md)  
> **Last Updated**: 2026-01-29

share2nightscout-bridge copies CGM data from Dexcom Share web services to Nightscout.

---

## Documents

| Document | Purpose |
|----------|---------|
| [api.md](api.md) | Dexcom Share API endpoints and authentication |
| [entries.md](entries.md) | Dexcom → Nightscout entry field mappings |

---

## Architecture Overview

```
Dexcom Share API ──► share2nightscout-bridge ──► Nightscout (API v1)
       │                      │
       │                      ├── SGV → entries
       │                      └── Battery → devicestatus
       │
       └── US: share2.dexcom.com
           EU: shareous1.dexcom.com
```

---

## Key Characteristics

| Aspect | Details |
|--------|---------|
| Language | JavaScript (Node.js) |
| Main File | `index.js` (447 lines) |
| Dependencies | `request` only |
| Poll Interval | 2.5 minutes (default) |
| NS API | v1 only (no v3 support) |
| Device ID | Always `"share2"` |

---

## Data Flow

1. **Authenticate** with Dexcom Share (accountId → sessionId)
2. **Poll** glucose values every 2.5 minutes
3. **Transform** Dexcom format to Nightscout entry
4. **Upload** via `POST /api/v1/entries.json`

---

## Gaps

| Gap ID | Description | Status |
|--------|-------------|--------|
| GAP-SHARE-001 | No Nightscout API v3 support | Documented |
| GAP-SHARE-002 | No backfill/gap detection logic | Documented |
| GAP-SHARE-003 | Hardcoded application ID may break | Documented |

---

## Cross-References

- [Nocturne Dexcom Connector](../nocturne/connectors.md)
- [Nightscout Entries Schema](../nightscout/)
- [Cross-Project Terminology](../cross-project/terminology-matrix.md)
