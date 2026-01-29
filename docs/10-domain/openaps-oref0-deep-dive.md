# OpenAPS and oref0 Deep Dive

> **Sources**: openaps, oref0  
> **Last Updated**: 2026-01-29

## Overview

OpenAPS (Open Artificial Pancreas System) is the foundational DIY closed-loop ecosystem. It consists of two key repositories:

| Repo | Purpose | Language |
|------|---------|----------|
| **openaps** | Device toolkit (pump/CGM drivers) | Python |
| **oref0** | Reference algorithm implementation | JavaScript/Node.js |

Together they form the **monitor-predict-control** framework that AAPS and Trio later adopted.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      OpenAPS Rig                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐     │
│  │   openaps   │    │    oref0    │    │ Nightscout  │     │
│  │   (Python)  │    │    (JS)     │    │   (sync)    │     │
│  └──────┬──────┘    └──────┬──────┘    └──────┬──────┘     │
│         │                  │                  │             │
│         ▼                  ▼                  ▼             │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐     │
│  │   Vendors   │    │ Algorithm   │    │   Upload    │     │
│  │ (Medtronic, │    │ (determine  │    │  (entries,  │     │
│  │  Dexcom)    │    │   basal)    │    │ devicestat) │     │
│  └─────────────┘    └─────────────┘    └─────────────┘     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## openaps Package (Python)

**Source**: `externals/openaps/`

### Purpose

A modular toolkit for building artificial pancreas systems by:
- Collecting data from medical devices (pumps, CGMs)
- Making predictions about therapy needs
- Enacting control decisions

### Key Modules

| Module | Path | Purpose |
|--------|------|---------|
| **vendors** | `openaps/vendors/` | Device drivers |
| └─ medtronic.py | Medtronic pump commands | 
| └─ dexcom.py | Dexcom CGM with `oref0_glucose` formatting |
| **cli** | `openaps/cli/` | Command-line interface |
| **devices** | `openaps/devices/` | Device registration |
| **uses** | `openaps/uses/` | Command registry |
| **reports** | `openaps/reports/` | Report generation |
| **glucose** | `openaps/glucose/` | Glucose data conversion |

### oref0-Compatible Data Sources

The openaps drivers format data specifically for oref0 consumption:

**From Medtronic pump** (`openaps/vendors/medtronic.py`):
- `read_clock` - Pump time
- `read_settings` - Pump settings
- `read_temp_basal` - Current temp basal
- `read_basal_profile_std` - Scheduled basal rates
- `read_carb_ratios` - Carb ratios
- `read_bg_targets` - BG targets
- `read_insulin_sensitivities` - ISF values
- `reservoir` - Insulin remaining

**From Dexcom CGM** (`openaps/vendors/dexcom.py`):
- `oref0_glucose` - Glucose readings in oref0 format
- Calibration data reformatting

---

## oref0 Package (JavaScript)

**Source**: `externals/oref0/`

### Purpose

The **OpenAPS Reference Design** - the core algorithm that calculates insulin dosing decisions based on:
- Current glucose and trend
- Insulin on board (IOB)
- Carbs on board (COB)
- Profile settings

### Directory Structure

```
oref0/
├── bin/           # Executable scripts (~80 files)
├── lib/           # Core algorithm modules
│   ├── determine-basal/   # Main dosing algorithm
│   ├── iob/               # Insulin on board
│   ├── meal/              # Meal detection
│   ├── profile/           # Profile management
│   └── autotune/          # Parameter auto-tuning
├── tests/         # Test suite
└── www/           # Web interface files
```

---

## Core Algorithm Files

### determine-basal (Main Engine)

**Path**: `lib/determine-basal/determine-basal.js` (1192 lines)

The heart of oref0 - calculates temporary basal rates and SMB recommendations.

**Key inputs**:
- `glucose_status` - Current glucose, delta, trend
- `currenttemp` - Active temp basal
- `iob_data` - Insulin on board
- `profile` - Therapy settings
- `autosens_data` - Sensitivity adjustments
- `meal_data` - COB and meal info

**Key outputs**:
- `rate` - Recommended temp basal rate
- `duration` - Temp basal duration
- `units` - SMB bolus amount (if enabled)
- `reason` - Human-readable explanation
- `predBGs` - Prediction curves (IOB, COB, UAM, ZT)

### autosens (Sensitivity Detection)

**Path**: `lib/determine-basal/autosens.js` (454 lines)

Detects insulin sensitivity variations by analyzing:
- Glucose deviations from expected
- Recent insulin delivery history
- Carb absorption patterns

**Output**: `ratio` multiplier (e.g., 1.1 = 10% more resistant)

### IOB Calculation

**Path**: `lib/iob/`

| File | Lines | Purpose |
|------|-------|---------|
| `calculate.js` | 146 | Core IOB calculation |
| `history.js` | 572 | Dosing history processing |
| `total.js` | ~50 | IOB aggregation |
| `index.js` | ~30 | Module interface |

Uses exponential insulin activity curves (bilinear or exponential model).

### COB Calculation

**Path**: `lib/determine-basal/cob.js` (211 lines)

Calculates carbs on board using:
- Carb entries with timestamps
- Absorption rate (from carb type or default)
- Deviation-based absorption adjustment

### Profile Management

**Path**: `lib/profile/`

| File | Purpose |
|------|---------|
| `basal.js` | Scheduled basal rates |
| `isf.js` | Insulin sensitivity factor |
| `carbs.js` | Carb ratio |
| `targets.js` | Glucose targets |
| `index.js` | Profile loader |

### Autotune

**Path**: `lib/autotune/`

Automatically adjusts profile parameters based on historical data:
- Basal rates
- ISF
- Carb ratio

**Files**:
- `oref0-autotune-prep.js` - Prepare input data
- `oref0-autotune-core.js` - Core tuning algorithm

---

## Executable Scripts (bin/)

### Setup Scripts

| Script | Purpose |
|--------|---------|
| `oref0-setup.sh` | Main installation wizard |
| `oref0-upgrade.sh` | Upgrade installation |
| `openaps-install.sh` | OpenAPS bootstrap |

### Runtime Loop Scripts

| Script | Purpose |
|--------|---------|
| `oref0-pump-loop.sh` | Main loop - syncs pump, enacts temp basals/SMB |
| `oref0-ns-loop.sh` | Nightscout sync loop |
| `oref0-cron-every-minute.sh` | Minute-level tasks |
| `oref0-cron-nightly.sh` | Nightly maintenance |

### Algorithm Invocation

| Script | lib/ Module |
|--------|-------------|
| `oref0-determine-basal.js` | `lib/determine-basal/determine-basal` |
| `oref0-calculate-iob.js` | `lib/iob` |
| `oref0-detect-sensitivity.js` | `lib/determine-basal/autosens` |
| `oref0-meal.js` | `lib/meal` |
| `oref0-get-profile.js` | `lib/profile/` |
| `oref0-autotune-core.js` | `lib/autotune` |

### Nightscout Integration

| Script | Purpose |
|--------|---------|
| `ns-upload.sh` | Upload data to Nightscout |
| `ns-upload-entries.sh` | Upload glucose entries |
| `ns-get.sh` | Fetch from Nightscout |
| `ns-status.js` | Upload devicestatus |
| `ns-dedupe-treatments.sh` | Deduplicate treatments |
| `oref0-get-ns-entries.js` | Fetch NS entries |

---

## Prediction Curves (predBGs)

oref0 generates 4-5 prediction scenarios:

| Curve | Description |
|-------|-------------|
| **IOB** | Insulin-only prediction (no carbs) |
| **ZT** | Zero-temp: what happens if we stop insulin |
| **COB** | Carbs on board prediction |
| **UAM** | Unannounced Meal detection |
| **aCOB** | AMA (Advanced Meal Assist) COB variant |

**Format**: Integer arrays, 5-minute intervals, mg/dL

**Nightscout upload**: `devicestatus.openaps.suggested.predBGs`

---

## Relationship to AAPS and Trio

| Feature | oref0 (original) | AAPS | Trio |
|---------|------------------|------|------|
| **Language** | JavaScript | Kotlin | Swift |
| **Algorithm** | Native | Ported oref0/oref1 | Ported oref1 |
| **SMB** | ✅ (oref1) | ✅ | ✅ |
| **Autosens** | ✅ | ✅ | ✅ |
| **Autotune** | ✅ | ✅ | ✅ |
| **Dynamic ISF** | ❌ | ✅ | ✅ |
| **Platform** | Raspberry Pi | Android | iOS |

**Key Forks**:
- AAPS ported oref0/oref1 to Kotlin (`app/src/main/kotlin/app/aaps/core/oref/`)
- Trio uses oref1 via FreeAPS X lineage (`Trio/Sources/APS/OpenAPS/`)

---

## Nightscout devicestatus Format

oref0 uploads to Nightscout in this format:

```json
{
  "openaps": {
    "iob": {
      "iob": 1.5,
      "activity": 0.02,
      "basaliob": 0.8
    },
    "suggested": {
      "bg": 120,
      "temp": "absolute",
      "rate": 0.5,
      "duration": 30,
      "reason": "COB: 20g, IOB: 1.5U...",
      "predBGs": {
        "IOB": [120, 118, 115, ...],
        "COB": [120, 125, 130, ...],
        "UAM": [120, 128, 135, ...],
        "ZT": [120, 115, 110, ...]
      },
      "timestamp": "2026-01-29T00:00:00Z"
    },
    "enacted": {
      "rate": 0.5,
      "duration": 30,
      "timestamp": "2026-01-29T00:00:05Z"
    }
  },
  "pump": { ... },
  "uploader": { ... }
}
```

---

## Source File Reference

### openaps (Python)
- `externals/openaps/openaps/vendors/medtronic.py` - Medtronic pump driver
- `externals/openaps/openaps/vendors/dexcom.py` - Dexcom CGM driver
- `externals/openaps/openaps/cli/` - CLI implementation
- `externals/openaps/setup.py` - Package setup

### oref0 (JavaScript)
- `externals/oref0/lib/determine-basal/determine-basal.js` - Main algorithm (1192 lines)
- `externals/oref0/lib/determine-basal/autosens.js` - Sensitivity detection (454 lines)
- `externals/oref0/lib/determine-basal/cob.js` - COB calculation (211 lines)
- `externals/oref0/lib/iob/calculate.js` - IOB calculation (146 lines)
- `externals/oref0/lib/iob/history.js` - Dosing history (572 lines)
- `externals/oref0/lib/profile/` - Profile management
- `externals/oref0/lib/autotune/` - Auto-tuning
- `externals/oref0/bin/oref0-determine-basal.js` - CLI entry point
- `externals/oref0/bin/ns-status.js` - Nightscout status upload

---

## Gaps Identified

### GAP-OREF-001: No oref0 Package Published to npm

**Description**: oref0 is not published as an npm package. Users must clone the repo and run from source.

**Impact**: Makes integration with other Node.js projects difficult; each project (AAPS, Trio) re-implements in native language.

### GAP-OREF-002: openaps Python Package Unmaintained

**Description**: The openaps Python package hasn't been updated significantly; focus shifted to AndroidAPS and Loop ecosystems.

**Impact**: New pump/CGM support goes to AAPS first; openaps/oref0 has limited device support.

### GAP-OREF-003: oref0 vs oref1 Distinction Unclear

**Description**: oref1 added SMB support but the code is in the same repo. No clear versioning or feature flags.

**Impact**: Difficult to know which features are oref0 vs oref1 when porting to other systems.

---

## Summary

| Aspect | openaps | oref0 |
|--------|---------|-------|
| **Role** | Device toolkit | Algorithm engine |
| **Language** | Python | JavaScript |
| **Key Function** | Pump/CGM data collection | Insulin dosing calculation |
| **Output** | JSON device data | Temp basal + SMB recommendations |
| **NS Integration** | Via oref0 | devicestatus upload |
| **Successors** | - | AAPS, Trio (ported algorithm) |

OpenAPS/oref0 established the architecture and algorithms that the entire DIY AID ecosystem builds upon.
