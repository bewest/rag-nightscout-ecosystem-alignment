# Trio Behavior Documentation

This directory contains detailed documentation of Trio's actual behavior as extracted from the Trio source code (Swift/iOS with embedded oref0 JavaScript). This serves as the authoritative reference for aligning Trio with Nightscout and other AID systems.

## Source Repository

- **Repository**: [nightscout/Trio](https://github.com/nightscout/Trio)
- **Language**: Swift (iOS) + JavaScript (oref0 algorithm)
- **Analysis Date**: 2026-01-16

## Documentation Index

| Document | Description |
|----------|-------------|
| [nightscout-sync.md](nightscout-sync.md) | Nightscout upload/download, treatment mappings, devicestatus format |
| [algorithm.md](algorithm.md) | OpenAPS.swift bridge, determine-basal flow, suggestion parsing |
| [insulin-math.md](insulin-math.md) | IOB calculation via oref0 iob module, insulin models |
| [carb-math.md](carb-math.md) | COB calculation, UAM detection, meal module |
| [remote-commands.md](remote-commands.md) | TrioRemoteControl via APNS, encrypted commands, remote bolus/meal/overrides |
| [overrides.md](overrides.md) | Override implementation, temp targets, presets |
| [safety.md](safety.md) | Max IOB/SMB limits, autosens bounds, constraints |
| [data-models.md](data-models.md) | Swift model fields → Nightscout field mappings |

## Key Source Files

| File | Location | Purpose |
|------|----------|---------|
| `APSManager.swift` | `Trio/Sources/APS/` | Main loop controller |
| `OpenAPS.swift` | `Trio/Sources/APS/OpenAPS/` | JavaScript algorithm bridge |
| `JavaScriptWorker.swift` | `Trio/Sources/APS/OpenAPS/` | JS execution engine |
| `NightscoutManager.swift` | `Trio/Sources/Services/Network/` | NS sync orchestration |
| `NightscoutAPI.swift` | `Trio/Sources/Services/Network/` | NS HTTP client |
| `TrioRemoteControl.swift` | `Trio/Sources/Services/RemoteControl/` | Secure remote command handling |
| `TrioSettings.swift` | `Trio/Sources/Models/` | App settings model |
| `determine-basal.js` | `trio-oref/lib/determine-basal/` | Core oref algorithm |
| `iob/index.js` | `trio-oref/lib/iob/` | IOB calculation |
| `meal/index.js` | `trio-oref/lib/meal/` | COB and meal detection |

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Trio Algorithm Flow                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Input Data                                                             │
│  ├── Glucose History (CGM readings via CGM sources)                   │
│  ├── Pump History (boluses, temp basals from pump)                    │
│  ├── Carb Entries (from user or Nightscout)                           │
│  └── Settings (profile, preferences, pump settings)                   │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                     APSManager.swift                             │   │
│  │  Orchestrates loop cycle every 5 minutes                         │   │
│  └─────────────────────┬───────────────────────────────────────────┘   │
│                        │                                                │
│  ┌─────────────────────▼───────────────────────────────────────────┐   │
│  │                     OpenAPS.swift                                │   │
│  │  Prepares data, calls JavaScript, parses results                 │   │
│  │                                                                   │   │
│  │  1. makeProfiles() → profile.json                                │   │
│  │  2. autosense() → autosens.json                                  │   │
│  │  3. determineBasal() → suggested.json                            │   │
│  └─────────────────────┬───────────────────────────────────────────┘   │
│                        │                                                │
│  ┌─────────────────────▼───────────────────────────────────────────┐   │
│  │                  JavaScriptWorker.swift                          │   │
│  │  Executes oref0 JavaScript in JSContext                          │   │
│  │                                                                   │   │
│  │  Scripts loaded:                                                  │   │
│  │  ├── iob/index.js → IOB calculation                              │   │
│  │  ├── meal/index.js → COB/meal calculation                        │   │
│  │  ├── determine-basal/determine-basal.js → Algorithm              │   │
│  │  └── autosens.js → Autosensitivity                               │   │
│  └─────────────────────┬───────────────────────────────────────────┘   │
│                        │                                                │
│  ┌─────────────────────▼───────────────────────────────────────────┐   │
│  │                     Suggestion                                   │   │
│  │  Algorithm output: rate, duration, units (SMB), reason           │   │
│  └─────────────────────┬───────────────────────────────────────────┘   │
│                        │                                                │
│  ┌─────────────────────▼───────────────────────────────────────────┐   │
│  │                  DeviceDataManager.swift                         │   │
│  │  Sends commands to pump (temp basal, SMB bolus)                  │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Nightscout Integration Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     Nightscout Sync Architecture                        │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  UPLOAD FLOW (Trio → Nightscout)                                       │
│  ├── uploadStatus() → /api/v1/devicestatus.json                        │
│  │   └── OpenAPSStatus { iob, suggested, enacted, version }            │
│  │   └── NSPumpStatus { clock, battery, reservoir, status }            │
│  ├── uploadTreatments() → /api/v1/treatments.json                      │
│  │   └── Boluses, Temp Basals, Carbs, Temp Targets, Site Changes       │
│  ├── uploadGlucose() → /api/v1/entries.json                            │
│  │   └── BloodGlucose readings                                         │
│  └── uploadProfile() → /api/v1/profile.json                            │
│      └── NightscoutProfileStore (basal, ISF, CR, targets)              │
│                                                                         │
│  DOWNLOAD FLOW (Nightscout → Trio)                                     │
│  ├── fetchGlucose() ← /api/v1/entries/sgv.json                         │
│  ├── fetchCarbs() ← /api/v1/treatments.json?find[carbs][$exists]=true  │
│  └── fetchTempTargets() ← eventType=Temporary+Target                   │
│                                                                         │
│  REMOTE CONTROL (via APNS)                                              │
│  └── TrioRemoteControl.handleRemoteNotification()                      │
│      └── Encrypted commands: bolus, meal, tempTarget, override         │
│                                                                         │
│  IDENTITY                                                               │
│  └── enteredBy: "Trio" (static identifier for all uploads)             │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Key Differences from Other Systems

| Aspect | Trio | Loop | AAPS |
|--------|------|------|------|
| Algorithm | oref0/oref1 (JavaScript) | Custom Swift | oref0 ported to Kotlin |
| SMB Support | Yes | Automatic doses (similar) | Yes |
| UAM Detection | Yes | No | Yes |
| Autosens | Yes | Retrospective Correction | Yes |
| Dynamic ISF | Yes (TDD-based) | No | Yes (DynISF) |
| Autotune | Yes | No | Yes |
| Remote Commands | Via encrypted APNS (TrioRemoteControl) | Via Remote Overrides | Via NS commands |
| Profile Sync | Uploads profile store | N/A | Full ProfileSwitch sync |

## oref0 Integration

Trio embeds the oref0 JavaScript algorithm (from `trio-oref/lib/`):

### Algorithm Components

| Component | JavaScript File | Purpose |
|-----------|----------------|---------|
| IOB | `iob/index.js` | Insulin on board calculation |
| Meal/COB | `meal/index.js` | Carb on board, meal detection |
| Autosens | `determine-basal/autosens.js` | Sensitivity adjustment |
| Determine Basal | `determine-basal/determine-basal.js` | Main algorithm |
| Autotune | `autotune/` + `autotune-prep/` | Profile optimization |

### oref2 Variables

Trio extends oref0 with additional variables tracked in CoreData:

| Variable | Purpose |
|----------|---------|
| `average_total_data` | 10-day TDD average |
| `weightedAverage` | Weighted 2h/10d TDD |
| `past2hoursAverage` | Recent TDD (2 hours) |
| `overridePercentage` | Active override % |
| `useOverride` | Override active flag |
| `hbt` | Half-basal exercise target |
| `smbIsOff` | Override disables SMB |
| `smbIsScheduledOff` | Scheduled SMB disable |

## Code Citation Format

Throughout this documentation, code references use the format:
```
trio:Path/To/File.swift#L123-L456
```

This maps to files in the `externals/Trio/` directory.

## CGM Support

### Supported CGM Sources (as of dev branch 0.6.0)

| CGM | Module | Notes |
|-----|--------|-------|
| Dexcom G6 | `CGMBLEKit` | Direct Bluetooth connection |
| Dexcom G7 | `G7SensorKit` | Includes 15-day sensor support |
| Libre 1/2/3 | `LibreTransmitter` | Via transmitter hardware |
| Medtronic Guardian | `MinimedKit` | Via RileyLink |
| Nightscout | Built-in | Remote CGM source |
| xDrip | Built-in | Local glucose source (port 8080) |

### Recent CGM Updates (2026-01)

- **G7 15-day sensor support** added via G7SensorKit update
- LibreTransmitter: Reduced logging, improved stability
- CGMBLEKit: SHA alignment with LoopKit

## iOS Features

### Live Activity

Trio supports iOS Live Activities for lock screen glucose display:

```swift
// trio:Trio/Sources/Models/TrioSettings.swift
var useLiveActivity: Bool = false
var lockScreenView: LockScreenView = .simple
var smartStackView: LockScreenView = .simple
```

Live Activity views are defined in `LiveActivity/` module.

### Siri Shortcuts

Bolus shortcuts with safety limits:

```swift
enum BolusShortcutLimit: String {
    case notAllowed       // Shortcuts cannot trigger bolus
    case limitBolusMax    // Limited to max bolus setting
}
```

## Revision History

| Date | Author | Changes |
|------|--------|---------|
| 2026-01-16 | Agent | Updated paths from FreeAPS to Trio, added CGM/iOS features, updated remote commands |
| 2026-01-16 | Agent | Initial Trio behavior documentation from source analysis |
