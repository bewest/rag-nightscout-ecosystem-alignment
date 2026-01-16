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
| [remote-commands.md](remote-commands.md) | Announcements, remote bolus/carbs/temp basals |
| [overrides.md](overrides.md) | Override implementation, temp targets, presets |
| [safety.md](safety.md) | Max IOB/SMB limits, autosens bounds, constraints |
| [data-models.md](data-models.md) | Swift model fields → Nightscout field mappings |

## Key Source Files

| File | Location | Purpose |
|------|----------|---------|
| `APSManager.swift` | `FreeAPS/Sources/APS/` | Main loop controller |
| `OpenAPS.swift` | `FreeAPS/Sources/APS/OpenAPS/` | JavaScript algorithm bridge |
| `JavaScriptWorker.swift` | `FreeAPS/Sources/APS/OpenAPS/` | JS execution engine |
| `NightscoutManager.swift` | `FreeAPS/Sources/Services/Network/` | NS sync orchestration |
| `NightscoutAPI.swift` | `FreeAPS/Sources/Services/Network/` | NS HTTP client |
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
│  ├── fetchTempTargets() ← eventType=Temporary+Target                   │
│  └── fetchAnnouncements() ← eventType=Announcement, enteredBy=remote   │
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
| Remote Commands | Via Announcements | Via Remote Overrides | Via NS commands |
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

## Revision History

| Date | Author | Changes |
|------|--------|---------|
| 2026-01-16 | Agent | Initial Trio behavior documentation from source analysis |
