# nightscout-librelink-up Field Mapping

> **Project**: nightscout-librelink-up  
> **Type**: Data bridge (LibreLink Up → Nightscout)  
> **Language**: TypeScript/Node.js  
> **Deep Dive**: [nightscout-librelink-up-deep-dive.md](../../docs/10-domain/nightscout-librelink-up-deep-dive.md)

## Overview

nightscout-librelink-up syncs glucose data from Abbott's LibreLink Up cloud service to Nightscout. It enables Libre CGM users (Libre 2, Libre 3) to aggregate their data without additional hardware.

## Architecture

```
LibreLink Up Cloud          nightscout-librelink-up           Nightscout
(api-*.libreview.io)        (polling bridge)                  (api/v1/entries)
       │                            │                              │
       │  ┌──────────────────────┐  │                              │
       │  │ 1. Auth (login)      │  │                              │
       │◄─┤ 2. Get connections   │  │                              │
       │  │ 3. Get measurements  │  │                              │
       │  └──────────────────────┘  │                              │
       │                            │                              │
       │     GlucoseItem            │     Entry (v1)               │
       │     - ValueInMgPerDl ─────►│───► sgv                      │
       │     - FactoryTimestamp ───►│───► date, dateString         │
       │     - TrendArrow ─────────►│───► direction                │
       └────────────────────────────┼──────────────────────────────►
                                    │
                              5-min poll
```

## Data Flow

| Step | Source | Action | Destination |
|------|--------|--------|-------------|
| 1 | LibreLink Up | Auth (email/password) | AuthTicket |
| 2 | LibreLink Up | GET /llu/connections | Patient list |
| 3 | LibreLink Up | GET /llu/connections/:id/graph | GlucoseItem |
| 4 | Bridge | Transform fields | Entry |
| 5 | Nightscout | POST /api/v1/entries | SGV entry |

## Documents

| Document | Purpose |
|----------|---------|
| [api.md](api.md) | LibreLink Up API endpoints and authentication |
| [entries.md](entries.md) | LibreLink → Nightscout entry field mapping |

## Key Characteristics

| Aspect | Value |
|--------|-------|
| **Polling interval** | 5 minutes (configurable) |
| **API version** | v1 only (v3 stub exists) |
| **Data types** | Entries only (no treatments) |
| **Multi-patient** | Supported via `LINK_UP_CONNECTION` |
| **Regions** | 8 (EU, EU2, US, AU, DE, FR, JP, AP) |
| **Device ID** | `"nightscout-librelink-up"` |

## Gaps

| ID | Description |
|----|-------------|
| GAP-LIBRELINK-001 | No Nightscout API v3 support |
| GAP-LIBRELINK-002 | No historical backfill |
| GAP-LIBRELINK-003 | Trend arrow limited to 5 values |

## Source Files

| File | Purpose |
|------|---------|
| `src/index.ts` | Main polling loop |
| `src/nightscout/apiv1.ts` | Nightscout v1 client |
| `src/nightscout/interface.ts` | Entry interface |
| `src/interfaces/librelink/common.ts` | GlucoseItem type |
