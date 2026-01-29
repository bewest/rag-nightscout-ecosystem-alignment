# xDrip+ Nightscout Mapping

> **Source Repository**: `externals/xDrip/`  
> **Last Updated**: 2026-01-29

## Overview

xDrip+ is the most widely used Android CGM data management application. It supports 20+ glucose data sources and uploads to Nightscout via REST API v1.

## Mapping Documents

| Document | Description |
|----------|-------------|
| [nightscout-fields.md](nightscout-fields.md) | Complete field mapping for all collections |

## Key Features

- **Entries**: SGV + MBG (calibration) uploads
- **Treatments**: Carbs, insulin, sensor start/stop
- **DeviceStatus**: Phone/bridge/transmitter battery
- **Activity**: Heart rate, steps, motion tracking

## Data Sources Supported

| Source | Collection Method |
|--------|------------------|
| Dexcom G4/G5/G6 | `DexcomG5`, `BluetoothWixel` |
| Dexcom G7 | `DexcomG5` (OB1 collector) |
| Libre 1/2 | `Libre2`, `LibreOOP` |
| Libre 3 | `Libre2` (via broadcast) |
| Medtronic 640G/670G | `Medtronic640g` |
| Eversense | `Eversense` |
| Other | `Follower`, `NSClient` |

## Integration Pattern

```
┌─────────────────┐
│   CGM Sensor    │
└────────┬────────┘
         │ BLE
         ▼
┌─────────────────┐
│     xDrip+      │
│   (Android)     │
└────────┬────────┘
         │ REST API v1
         ▼
┌─────────────────┐
│   Nightscout    │
│    Server       │
└─────────────────┘
```

## Gaps

- **GAP-XDRIP-001**: No v3 API support
- **GAP-XDRIP-002**: Activity schema not standardized
- **GAP-XDRIP-003**: Device string not machine-parseable

## References

- [xDrip+ GitHub](https://github.com/NightscoutFoundation/xDrip)
- [CGM Session Handling Comparison](../../docs/10-domain/cgm-session-handling-deep-dive.md)
