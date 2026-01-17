# LoopCaregiver Behavior Documentation

This directory contains documentation extracted from LoopCaregiver, an iOS/watchOS companion app for caregivers of Loop users. LoopCaregiver provides a **full remote control perspective** enabling remote boluses, carb entries, and override management via Nightscout.

## Source Repository

- **Repository**: [LoopKit/LoopCaregiver](https://github.com/LoopKit/LoopCaregiver)
- **Language**: Swift (native iOS/watchOS)
- **License**: MIT
- **Analysis Date**: 2026-01-17
- **Codebase Size**: ~138 Swift files
- **Status**: Discovery Phase

## Purpose & Value

LoopCaregiver is a **full-featured remote control app** for Loop caregivers:

1. **Remote Commands** - Send boluses, carb entries, and overrides remotely
2. **Loop-like Interface** - Familiar UI matching the Loop app experience
3. **OTP Authentication** - Handles one-time-password authentication for remote commands
4. **Nightscout Integration** - Full integration via QR code from Loop Settings
5. **Multi-Looper Support** - Monitor and control multiple Loop users
6. **Real-time Status** - View glucose, IOB, COB, predictions in real-time

## Safety Warnings

LoopCaregiver includes explicit safety warnings:

- **Experimental code** - May cause serious risks to health/life
- **Remote insulin delivery** - Anyone with access can remotely deliver insulin
- **Data delays** - Nightscout may not reflect all treatments due to network delays
- **Security** - QR code and API key must be secured; reset if phone lost/stolen

## Discovery Cycle Status

| Phase | Status | Notes |
|-------|--------|-------|
| Repository Cloned | Complete | externals/LoopCaregiver |
| Key Files Identified | Pending | |
| Data Models Extracted | Pending | |
| Remote Command Protocol Documented | Pending | |
| Authentication Flow Analyzed | Pending | |
| Cross-References Updated | Pending | |

## Documentation Index

| Document | Description | Status |
|----------|-------------|--------|
| [README.md](README.md) | Overview and discovery status | Complete |
| remote-commands.md | Remote bolus/carb/override protocol | Pending |
| authentication.md | OTP and QR code linking flow | Pending |
| nightscout-sync.md | Nightscout API integration | Pending |
| data-models.md | Core data structures | Pending |

## Key Source Files (To Analyze)

| Path | Purpose |
|------|---------|
| `LoopCaregiver/LoopCaregiver/` | Main iOS app (Xcode project and sources) |
| `LoopCaregiverKit/` | Shared logic and models library |
| `LoopCaregiver/LoopCaregiver/Views/Actions/` | Remote action views (bolus, carbs, override) |
| `LoopCaregiver/LoopCaregiver/Views/Charts/` | Glucose and status charts |
| `LoopCaregiver/LoopCaregiver/Diagnostics/` | Build details and debugging |

## Preliminary Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                   LoopCaregiver Data Architecture (Discovery)                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                        NIGHTSCOUT INTEGRATION                            ││
│  │                                                                          ││
│  │  Read Operations:                                                        ││
│  │  ├── GET entries.json        → Blood glucose readings                   ││
│  │  ├── GET devicestatus.json   → Loop status, IOB, COB, predictions       ││
│  │  ├── GET treatments          → Boluses, carbs, overrides                ││
│  │  └── GET profile             → Therapy settings                         ││
│  │                                                                          ││
│  │  Remote 2.0 Commands (Write):                                           ││
│  │  ├── POST remote bolus       → Remote insulin delivery                  ││
│  │  ├── POST remote carbs       → Remote carb entry                        ││
│  │  ├── POST remote override    → Activate/cancel overrides                ││
│  │  ├── POST autobolus toggle   → Enable/disable autobolus                 ││
│  │  └── POST closed loop toggle → Enable/disable closed loop               ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                        AUTHENTICATION                                    ││
│  │                                                                          ││
│  │  QR Code Linking:                                                        ││
│  │  └── Scan from Loop app: Settings → Services → Nightscout               ││
│  │                                                                          ││
│  │  OTP (One-Time Password):                                                ││
│  │  └── Automatic handling for remote command authentication               ││
│  │                                                                          ││
│  │  Apple Push Notifications:                                               ││
│  │  └── Used for remote command delivery to Loop app                       ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                     PRESENTATION LAYER                                   ││
│  │                                                                          ││
│  │  iOS App Views (LoopCaregiver/Views/):                                  ││
│  │                                                                          ││
│  │  Action Views:                                                           ││
│  │  ├── BolusInputView          - Remote bolus entry                       ││
│  │  ├── CarbInputView           - Remote carb entry                        ││
│  │  ├── OverrideView            - Override selection and activation        ││
│  │  ├── OverrideInsulinNeedsView - Custom insulin needs adjustment         ││
│  │  └── PresetEditView          - Override preset management               ││
│  │                                                                          ││
│  │  Chart Views:                                                            ││
│  │  ├── PredictedGlucoseChartView - BG with predictions                    ││
│  │  ├── IOBChartView            - Insulin on board chart                   ││
│  │  ├── COBChartView            - Carbs on board chart                     ││
│  │  ├── DoseChartView           - Insulin delivery chart                   ││
│  │  └── ChartsListView          - Combined chart display                   ││
│  │                                                                          ││
│  │  watchOS App:                                                            ││
│  │  └── Quick status and remote actions from Apple Watch                   ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Remote Command Protocol

LoopCaregiver uses Nightscout's Remote 2.0 API for commands:

| Command | Description | Risk Level |
|---------|-------------|------------|
| Remote Bolus | Deliver insulin remotely | HIGH |
| Remote Carbs | Enter carbs remotely | MEDIUM |
| Override Activate | Start a preset override | LOW |
| Override Cancel | Cancel active override | LOW |
| Autobolus Toggle | Enable/disable autobolus | HIGH |
| Closed Loop Toggle | Enable/disable closed loop | HIGH |

## Minimum Requirements

- iOS 16+
- watchOS 10+
- Loop 3+ (for remote bolus/carb commands; older versions support overrides only)
- Nightscout with Remote 2.0 API support

## Roles in Ecosystem

| Role | Description |
|------|-------------|
| **Consumer** | Reads glucose, devicestatus, treatments from Nightscout |
| **Remote Controller** | Full remote command capability (bolus, carbs, overrides) |
| **Authenticated Client** | Uses OTP for secure remote command delivery |
| **Loop Companion** | Designed specifically for Loop, shares LoopKit submodules |

## Comparison with Similar Apps

| Aspect | LoopCaregiver | LoopFollow | Nightguard |
|--------|---------------|------------|------------|
| **Primary Role** | Full Remote Control | Monitor + Limited Remote | Monitor only |
| **Remote Bolus** | Yes | No | No |
| **Remote Carbs** | Yes | No | No |
| **Remote Override** | Yes | Yes | No |
| **OTP Auth** | Yes (automatic) | Manual | No |
| **Loop 3 Required** | For full features | No | No |
| **UI Style** | Loop-like | Custom dashboard | Minimal |

## Cross-References

- [mapping/loopfollow/](../loopfollow/) - Monitoring app with limited remote
- [mapping/nightguard/](../nightguard/) - Consumer-only iOS app
- [mapping/loop/](../loop/) - Loop AID system documentation
- [Nightscout Data Model](../../docs/10-domain/nightscout-data-model.md) - Authoritative NS schema
- [Controller Registration Protocol](../../docs/60-research/controller-registration-protocol-proposal.md) - Remote command protocol proposal

---

## Code Citation Format

Throughout this documentation, code references use:
```
loopcaregiver:LoopCaregiver/path/to/file.swift#L123-L456
```

This maps to files in `externals/LoopCaregiver/`.

---

## Revision History

| Date | Author | Changes |
|------|--------|---------|
| 2026-01-17 | Agent | Initial discovery stub created |
