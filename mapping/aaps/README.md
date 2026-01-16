# AAPS Behavior Documentation

This directory contains detailed documentation of AndroidAPS (AAPS) behavior as extracted from the source code (Kotlin/Android). This serves as the authoritative reference for aligning AAPS with Nightscout and other AID systems.

## Source Repository

- **Repository**: [nightscout/AndroidAPS](https://github.com/nightscout/AndroidAPS)
- **Language**: Kotlin (Android)
- **Analysis Date**: 2026-01-16

## Documentation Index

| Document | Description |
|----------|-------------|
| [nightscout-models.md](nightscout-models.md) | NSSDK local models and Nightscout API mapping |
| [nightscout-sync.md](nightscout-sync.md) | NSClientV3 sync flow, upload/download logic |
| [algorithm.md](algorithm.md) | OpenAPSSMB algorithm, predictions, dynamic ISF |
| [insulin-math.md](insulin-math.md) | IOB calculation, insulin models (oref curves) |
| [carb-math.md](carb-math.md) | COB calculation, meal detection, UAM |
| [profile-switch.md](profile-switch.md) | ProfileSwitch semantics vs Nightscout |
| [safety.md](safety.md) | Constraints, max IOB, max basal, SMB limits |
| [data-models.md](data-models.md) | Database entities and field mappings |

## Key Source Files

| File | Location | Purpose |
|------|----------|---------|
| `OpenAPSSMBPlugin.kt` | `plugins/aps/openAPSSMB/` | SMB algorithm plugin entry point |
| `DetermineBasalSMB.kt` | `plugins/aps/openAPSSMB/` | Core algorithm logic (Kotlin port of oref0) |
| `NSClientV3Plugin.kt` | `plugins/sync/nsclientV3/` | Nightscout V3 API sync |
| `NSTreatment.kt` | `core/nssdk/localmodel/treatment/` | Base NS treatment interface |
| `NSBolus.kt` | `core/nssdk/localmodel/treatment/` | Bolus NS model |
| `NSProfileSwitch.kt` | `core/nssdk/localmodel/treatment/` | Profile switch NS model |
| `NSDeviceStatus.kt` | `core/nssdk/localmodel/devicestatus/` | Device status NS model |
| `Bolus.kt` | `database/entities/` | Local bolus entity |
| `ProfileSwitch.kt` | `database/entities/` | Local profile switch entity |
| `TemporaryBasal.kt` | `database/entities/` | Local temp basal entity |
| `InsulinOrefBasePlugin.kt` | `plugins/insulin/` | Insulin model base (oref curves) |
| `ConstraintsCheckerImpl.kt` | `plugins/constraints/` | Safety constraint aggregator |

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    AAPS Architecture Overview                           │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐                 │
│  │   Plugins   │    │    Core     │    │  Database   │                 │
│  └──────┬──────┘    └──────┬──────┘    └──────┬──────┘                 │
│         │                  │                  │                         │
│  ┌──────▼──────────────────▼──────────────────▼──────┐                 │
│  │                                                    │                 │
│  │  plugins/aps/        - OpenAPS algorithm plugins   │                 │
│  │    ├─ openAPSAMA/    - Advanced Meal Assist        │                 │
│  │    ├─ openAPSSMB/    - Super Micro Bolus (primary) │                 │
│  │    ├─ openAPSAutoISF/- Dynamic ISF variant         │                 │
│  │    ├─ autotune/      - Profile autotune            │                 │
│  │    └─ loop/          - Loop controller             │                 │
│  │                                                    │                 │
│  │  plugins/sync/       - Synchronization             │                 │
│  │    ├─ nsclientV3/    - Nightscout V3 API           │                 │
│  │    ├─ nsclient/      - Legacy NS API               │                 │
│  │    └─ garmin/        - Garmin watch sync           │                 │
│  │                                                    │                 │
│  │  plugins/insulin/    - Insulin models              │                 │
│  │    ├─ Rapid-Acting   - peak: 75 min                │                 │
│  │    ├─ Ultra-Rapid    - peak: 55 min                │                 │
│  │    └─ Lyumjev        - peak: 45 min                │                 │
│  │                                                    │                 │
│  │  plugins/constraints/- Safety limits               │                 │
│  │                                                    │                 │
│  │  core/nssdk/         - Nightscout SDK              │                 │
│  │    └─ localmodel/    - NS data models              │                 │
│  │                                                    │                 │
│  │  database/entities/  - Room database entities      │                 │
│  │                                                    │                 │
│  └───────────────────────────────────────────────────┘                 │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Algorithm Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    OpenAPSSMB Algorithm Flow                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Input Data                                                             │
│  ├── Glucose Status (CGM readings, delta, noise)                       │
│  ├── IOB Array (calculated from dose history)                          │
│  ├── Meal Data (COB, carbs, last carb time)                            │
│  ├── Profile (basal, ISF, CR, targets)                                 │
│  └── Current Temp Basal                                                │
│                                                                         │
│  ┌─────────────────────┐                                               │
│  │ Autosens / DynISF   │  Calculate sensitivity ratio                 │
│  │                     │  TDD-based or autosens                        │
│  └──────────┬──────────┘                                               │
│             │                                                           │
│  ┌──────────▼──────────┐                                               │
│  │ Calculate BGI       │  Blood Glucose Impact from insulin activity  │
│  │ bgi = -activity *   │                                               │
│  │       sens * 5      │                                               │
│  └──────────┬──────────┘                                               │
│             │                                                           │
│  ┌──────────▼──────────┐                                               │
│  │ Calculate Deviation │  deviation = (minDelta - bgi) * 6            │
│  │ (30 min projection) │                                               │
│  └──────────┬──────────┘                                               │
│             │                                                           │
│  ┌──────────▼──────────┐                                               │
│  │ Calculate EventualBG│  eventualBG = BG - (IOB * sens) + deviation  │
│  │ (naive + deviation) │                                               │
│  └──────────┬──────────┘                                               │
│             │                                                           │
│  ┌──────────▼──────────┐                                               │
│  │ Generate Predictions│  IOBpredBG, COBpredBG, UAMpredBG, ZTpredBG   │
│  └──────────┬──────────┘                                               │
│             │                                                           │
│  ┌──────────▼──────────┐                                               │
│  │ Determine Action    │  Temp Basal and/or SMB                       │
│  └─────────────────────┘                                               │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Key Differences from Loop

| Aspect | AAPS | Loop |
|--------|------|------|
| Algorithm | oref0/oref1 (ported to Kotlin) | Custom prediction-based |
| SMB | Super Micro Bolus (explicit) | Automatic Dose (microboluses) |
| UAM | Yes (Unannounced Meal detection) | No explicit UAM |
| Sensitivity | Autosens or TDD-based DynISF | Retrospective Correction |
| Carb Absorption | Linear decay (assumed rate) | PiecewiseLinear (dynamic) |
| ProfileSwitch | Percentage + timeshift modifiers | N/A (settings-based) |
| Override | Via ProfileSwitch percentage | TemporaryScheduleOverride |

## Nightscout Integration

AAPS has a dedicated Nightscout SDK (`core/nssdk/`) with local model classes that mirror Nightscout's data structures:

| AAPS NSSDK Class | Nightscout Collection | Purpose |
|------------------|----------------------|---------|
| `NSSgvV3` | `entries` | CGM glucose values |
| `NSBolus` | `treatments` | Bolus events |
| `NSCarbs` | `treatments` | Carb entries |
| `NSTemporaryBasal` | `treatments` | Temp basal events |
| `NSProfileSwitch` | `treatments` | Profile switch events |
| `NSTemporaryTarget` | `treatments` | Temp target events |
| `NSDeviceStatus` | `devicestatus` | Loop status, pump, IOB |
| `NSTherapyEvent` | `treatments` | Site changes, notes, etc. |

## Code Citation Format

Throughout this documentation, code references use the format:
```
aaps:path/to/File.kt#L123-L456
```

This maps to files in the `externals/AndroidAPS/` directory.

## Known Gaps

### GAP-002: ProfileSwitch Semantic Mismatch

AAPS's `ProfileSwitch` can represent:
1. Complete profile change (new profile name)
2. Percentage adjustment (e.g., 110% insulin)
3. Time shift (shift profile schedule)

Nightscout treats all as "Profile Switch" events without distinguishing these semantically different operations. See [profile-switch.md](profile-switch.md) for details.

### GAP-003: Sync Identity

AAPS generates `identifier` (UUID) for entities but Nightscout uses `_id`. The NSSDK provides `identifier` field for client-side identification, while `srvModified`/`srvCreated` track server timestamps. See [nightscout-sync.md](nightscout-sync.md) for details.
