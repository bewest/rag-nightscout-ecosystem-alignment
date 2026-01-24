# LoopFollow Behavior Documentation

This directory contains documentation extracted from LoopFollow, an iOS/watchOS monitoring app for caregivers and parents of Type 1 Diabetes Loop users. LoopFollow provides a **follower/caregiver perspective** on monitoring and interacting with AID systems via Nightscout.

## Source Repository

- **Repository**: [loopandlearn/LoopFollow](https://github.com/loopandlearn/LoopFollow)
- **Language**: Swift (native iOS/watchOS)
- **License**: AGPL-3.0
- **Analysis Date**: 2026-01-17
- **Codebase Size**: ~432 Swift files
- **Status**: Discovery Phase

## Purpose & Value

LoopFollow is a **follower/caregiver monitoring app** that consolidates T1D management information:

1. **Caregiver perspective** - How a follower app monitors and interacts with AID systems
2. **Multi-source data aggregation** - Supports Loop, Trio, and iAPS via Nightscout
3. **Comprehensive alarm system** - High/low BG, fast rise/drop, IOB, COB, battery, missed readings
4. **Apple ecosystem integration** - iOS app with watchOS support, widgets
5. **Remote override/temp target** - Can send remote commands via Nightscout
6. **Multi-Looper support** - Follow up to 3 Loopers using separate app builds

## Discovery Cycle Status

| Phase | Status | Notes |
|-------|--------|-------|
| Repository Cloned | Complete | externals/LoopFollow |
| Key Files Identified | Complete | Alarm/, Remote/, Controllers/Nightscout/ |
| Data Models Extracted | Complete | Alarm, AlarmData, CommandPayload |
| API Paths Documented | Partial | Nightscout v1 API only |
| Alarm Logic Analyzed | Complete | 20 alarm types documented |
| Remote Commands Analyzed | Complete | 3 protocols (APNS, TRC, NS) |
| Cross-References Updated | Complete | Terminology matrix, requirements, gaps |

## Documentation Index

| Document | Description | Status |
|----------|-------------|--------|
| [README.md](README.md) | Overview and discovery status | Complete |
| [alarm-system.md](alarm-system.md) | All 20 alarm types, conditions, day/night scheduling, snooze | Complete |
| [remote-commands.md](remote-commands.md) | Loop APNS, TRC, Nightscout remote protocols | Complete |
| nightscout-sync.md | Nightscout API integration patterns | Future |
| data-models.md | Core data structures | Future |

## Key Source Files (To Analyze)

| Path | Purpose |
|------|---------|
| `LoopFollow/Alarm/` | Alarm system core |
| `LoopFollow/Alarm/AlarmCondition/` | Individual alarm condition types |
| `LoopFollow/Controllers/` | Main app UI controllers |
| `LoopFollow/Controllers/Nightscout/` | Nightscout API integration |
| `LoopFollow/Nightscout/` | Nightscout data models |
| `LoopFollow/Remote/` | Remote command functionality |
| `LoopFollow/Remote/LoopAPNS/` | Apple Push Notification support |

## Preliminary Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    LoopFollow Data Architecture (Discovery)                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                        DATA SOURCES                                      ││
│  │                                                                          ││
│  │  Nightscout Integration:                                                 ││
│  │  ├── GET entries.json        → Blood glucose readings                   ││
│  │  ├── GET devicestatus.json   → Loop/Trio/iAPS status, IOB, COB         ││
│  │  ├── GET treatments          → Boluses, carbs, overrides, temp targets ││
│  │  ├── GET profile             → Therapy settings                         ││
│  │  └── POST treatments         → Remote overrides/temp targets            ││
│  │                                                                          ││
│  │  Dexcom Share (Optional):                                                ││
│  │  └── Dexcom Share API        → Direct glucose data (no Nightscout)     ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                        ALARM SYSTEM                                      ││
│  │                                                                          ││
│  │  Alarm Conditions (LoopFollow/Alarm/AlarmCondition/):                   ││
│  │  ├── HighBGCondition       - Blood glucose above threshold              ││
│  │  ├── LowBGCondition        - Blood glucose below threshold              ││
│  │  ├── FastRiseCondition     - Rapid glucose increase                     ││
│  │  ├── FastDropCondition     - Rapid glucose decrease                     ││
│  │  ├── IOBCondition          - Insulin on board threshold                 ││
│  │  ├── COBCondition          - Carbs on board threshold                   ││
│  │  ├── BatteryCondition      - Pump/phone battery threshold               ││
│  │  ├── BatteryDropCondition  - Rapid battery decrease                     ││
│  │  ├── MissedReadingCondition - No CGM data received                      ││
│  │  ├── NotLoopingCondition   - Loop not closing (stale data)              ││
│  │  ├── MissedBolusCondition  - Expected bolus not delivered               ││
│  │  ├── OverrideStartCondition - Override activated                        ││
│  │  ├── OverrideEndCondition  - Override ended                             ││
│  │  └── BuildExpireCondition  - App build expiring soon                    ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                     PRESENTATION LAYER                                   ││
│  │                                                                          ││
│  │  iOS App:                                                                ││
│  │  ├── Main dashboard with BG, IOB, COB, predictions                      ││
│  │  ├── BG chart with historical data                                      ││
│  │  ├── Loop/Trio/iAPS status display                                      ││
│  │  └── Remote override/temp target controls                               ││
│  │                                                                          ││
│  │  watchOS App:                                                            ││
│  │  └── BG display and status on Apple Watch                               ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Expected API Paths

| Path | Method | Purpose |
|------|--------|---------|
| `/api/v1/entries.json` | GET | Historical BG readings |
| `/api/v1/devicestatus.json` | GET | Loop/Trio/iAPS status (IOB, COB, predictions) |
| `/api/v1/treatments` | GET | Boluses, carbs, overrides |
| `/api/v1/treatments` | POST | Remote overrides, temp targets |
| `/api/v1/profile.json` | GET | User therapy profile |
| `/api/v2/properties` | GET | Current status (alternative) |

## Roles in Ecosystem

| Role | Description |
|------|-------------|
| **Consumer** | Reads glucose, devicestatus, treatments from Nightscout |
| **Remote Controller** | Can send remote overrides/temp targets to Nightscout |
| **Alarm Provider** | Sophisticated alarm system for caregivers |
| **Multi-System Support** | Works with Loop, Trio, iAPS, and standalone Nightscout |

## Comparison with Similar Apps

| Aspect | LoopFollow | Nightguard | LoopCaregiver |
|--------|------------|------------|---------------|
| **Primary Role** | Monitor + Remote | Monitor only | Monitor + Remote Commands |
| **Remote Bolus** | No | No | Yes |
| **Remote Carbs** | No | No | Yes |
| **Remote Override** | Yes | No | Yes |
| **Alarm System** | Comprehensive | Full | Basic |
| **Multi-Looper** | Yes (3) | No | Yes |
| **Dexcom Share** | Yes | No | No |

## Cross-References

- [mapping/nightguard/](../nightguard/) - Consumer-only iOS app for comparison
- [mapping/loopcaregiver/](../loopcaregiver/) - Full remote control companion app
- [mapping/loop/](../loop/) - Loop AID system documentation
- [Nightscout Data Model](../../docs/10-domain/nightscout-data-model.md) - Authoritative NS schema
- [Controller Registration Protocol](../../docs/60-research/controller-registration-protocol-proposal.md) - Remote command protocol proposal

---

## Code Citation Format

Throughout this documentation, code references use the format:
```
loopfollow:LoopFollow/LoopFollow/Models/File.swift#L123-L456
```

This maps to files in `externals/LoopFollow/`.

---

## Revision History

| Date | Author | Changes |
|------|--------|---------|
| 2026-01-17 | Agent | Completed alarm-system.md with 20 alarm types, conditions, day/night, snooze |
| 2026-01-17 | Agent | Completed remote-commands.md with 3 protocols (Loop APNS, TRC, Nightscout) |
| 2026-01-17 | Agent | Updated cross-references: terminology matrix, requirements, gaps |
| 2026-01-17 | Agent | Initial discovery stub created |
