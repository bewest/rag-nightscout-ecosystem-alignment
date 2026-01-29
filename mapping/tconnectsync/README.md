# tconnectsync Field Mappings

> **Source**: `externals/tconnectsync/`  
> **Deep Dive**: [tconnectsync-deep-dive.md](../../docs/10-domain/tconnectsync-deep-dive.md)  
> **Last Updated**: 2026-01-29

tconnectsync is a Python tool that synchronizes data from Tandem t:connect cloud to Nightscout.

---

## Documents

| Document | Purpose |
|----------|---------|
| [models.md](models.md) | Domain model field mappings (Bolus, TherapyEvent, Profile) |
| [api.md](api.md) | t:connect API endpoints and authentication |
| [treatments.md](treatments.md) | Nightscout treatment type mappings |

---

## Architecture Overview

```
t:connect Cloud ──► tconnectsync ──► Nightscout (API v1)
      │                  │
      │                  ├── Bolus → Combo Bolus
      │                  ├── Basal → Temp Basal
      │                  ├── CGM → entries (sgv)
      │                  └── Profile → profiles
      │
      └── Control-IQ, Therapy Events, Settings
```

---

## Key Characteristics

| Aspect | Details |
|--------|---------|
| Language | Python 3.8+ |
| Pump Support | Tandem t:slim X2 with Control-IQ |
| CGM Support | Dexcom G6/G7 (via pump) |
| Sync Mode | Batch (no real-time) |
| NS API | v1 only (no v3 support) |
| Authentication | OIDC/OAuth2, Android credentials, web form |

---

## Supported Treatment Types

| t:connect Event | NS eventType | Processor |
|-----------------|--------------|-----------|
| Bolus | `Combo Bolus` | `process_bolus.py` |
| Temp Basal | `Temp Basal` | `process_basal.py` |
| Basal Suspension | `Basal Suspension` | `process_basal_suspension.py` |
| Site Change | `Site Change` | `process_cartridge.py` |
| Pump Alarm | `Announcement` | `process_alarm.py` |
| CGM Alert | `Announcement` | `process_cgm_alert.py` |
| Sensor Start | `Sensor Start` | `process_cgm_start_join_stop.py` |
| Exercise Mode | `Exercise` | `process_user_mode.py` |
| Sleep Mode | `Sleep` | `process_user_mode.py` |

---

## Gaps

| Gap ID | Description | Status |
|--------|-------------|--------|
| GAP-TCONNECT-001 | No API v3 support | Documented |
| GAP-TCONNECT-002 | Limited Control-IQ algorithm data | Documented |
| GAP-TCONNECT-003 | No real-time sync (batch only) | Documented |

---

## Cross-References

- [Nocturne TConnectSync Connector](../nocturne/connectors.md)
- [Nightscout Treatments Schema](../nightscout/v3-treatments-schema.md)
- [Cross-Project Terminology](../cross-project/terminology-matrix.md)
