# Nightscout Reporter Behavior Documentation

This directory contains documentation extracted from Nightscout Reporter, a Dart/AngularDart web application that consumes Nightscout API data and generates PDF reports. This provides a **consumer's perspective** on the Nightscout data model—how a client application interprets, validates, and uses the data from cgm-remote-monitor.

## Source Repository

- **Repository**: [zreptil/nightscout-reporter](https://github.com/zreptil/nightscout-reporter)
- **Language**: Dart (AngularDart, web)
- **Analysis Date**: 2026-01-16
- **Note**: This repository is deprecated in favor of nightscout-reporter-angular

## Purpose & Value

While cgm-remote-monitor defines the authoritative data model, Nightscout Reporter reveals:

1. **How clients parse and validate data** - Edge case handling, type coercion, defaults
2. **Uploader detection patterns** - How to identify data sources (OpenAPS, AAPS, xDrip, etc.)
3. **Treatment classification** - Practical categorization of event types
4. **Unit conversion** - mg/dL ↔ mmol/L handling in client code
5. **Statistical calculations** - How to compute TIR, averages, COB from raw data
6. **Profile interpretation** - Timezone handling, time-based settings resolution

## Documentation Index

| Document | Description |
|----------|-------------|
| [data-models.md](data-models.md) | Mapping of Reporter data classes to NS collections |
| [uploader-detection.md](uploader-detection.md) | Identifying data sources from enteredBy field |
| [treatment-classification.md](treatment-classification.md) | Event type classification and edge cases |
| [profile-handling.md](profile-handling.md) | Timezone, time-based settings, profile mixing |
| [calculations.md](calculations.md) | COB, IOB, TIR, statistical aggregations |
| [unit-conversion.md](unit-conversion.md) | mg/dL vs mmol/L handling patterns |

## Key Source Files

| File | Purpose |
|------|---------|
| `lib/src/json_data.dart` | Core data models (~2869 lines) - EntryData, TreatmentData, ProfileData, etc. |
| `lib/src/globals.dart` | Application state, settings, user preferences |
| `lib/src/forms/base-print.dart` | Base class for PDF report generation |
| `lib/src/forms/print-daily-*.dart` | Daily report implementations |
| `lib/src/forms/print-analysis.dart` | Statistical analysis report |

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Nightscout Reporter Data Flow                     │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  Nightscout API                                                      │
│  ├── /api/v1/entries.json     → EntryData[]                        │
│  ├── /api/v1/treatments.json  → TreatmentData[]                    │
│  ├── /api/v1/profile.json     → ProfileData                        │
│  ├── /api/v1/devicestatus.json → DeviceStatusData[]                │
│  └── /api/v1/status.json      → StatusData                         │
│                                                                      │
│  ┌─────────────────┐                                                │
│  │ JSON Parsing    │  JsonData.fromJson() methods                   │
│  │ & Validation    │  Type coercion, defaults, edge cases           │
│  └────────┬────────┘                                                │
│           │                                                          │
│  ┌────────▼────────┐                                                │
│  │ Data Classes    │  Typed Dart objects with computed properties   │
│  │ (json_data.dart)│  - EntryData.gluc (handles gaps, units)        │
│  │                 │  - TreatmentData.from (detects uploader)       │
│  │                 │  - ProfileStoreData.ieBasalSum (totals)        │
│  └────────┬────────┘                                                │
│           │                                                          │
│  ┌────────▼────────┐                                                │
│  │ Aggregation     │  DayData, StatisticData, ReportData            │
│  │ & Statistics    │  TIR, averages, variance, COB/IOB              │
│  └────────┬────────┘                                                │
│           │                                                          │
│  ┌────────▼────────┐                                                │
│  │ PDF Generation  │  pdfmake integration                           │
│  │ (print-*.dart)  │  Charts, tables, summaries                     │
│  └─────────────────┘                                                │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

## Key Data Class Hierarchy

```
JsonData (base class with utility methods)
├── EntryData           → entries collection (SGV, MBG, calibrations)
├── TreatmentData       → treatments collection (bolus, carbs, temp basal, etc.)
├── ProfileData         → profile collection (therapy settings)
│   └── ProfileStoreData → Individual named profile
│       └── ProfileEntryData → Time-based setting entry
├── DeviceStatusData    → devicestatus collection
│   ├── LoopData        → Loop/OpenAPS status
│   ├── PumpData        → Pump state
│   ├── UploaderData    → Uploader battery
│   └── XDripJSData     → xDrip-js transmitter status
├── StatusData          → Server status and settings
│   ├── SettingsData    → NS site settings
│   └── ThresholdData   → BG thresholds
├── BoluscalcData       → Bolus wizard calculation details
├── ActivityData        → Activity/steps data
└── DayData             → Daily aggregation container
```

## Uploader Detection

Reporter detects the data source from `enteredBy` field:

| Uploader Enum | Detection Pattern | Notes |
|---------------|------------------|-------|
| `OpenAPS` | `enteredBy == "openaps"` | oref0/oref1 systems |
| `AndroidAPS` | `enteredBy.contains("androidaps")` | AAPS |
| `XDrip` | `enteredBy.startsWith("xdrip")` | xDrip+ |
| `Spike` | `enteredBy == "spike"` | Spike iOS app |
| `Tidepool` | `enteredBy == "tidepool"` | Tidepool uploader |
| `Minimed600` | Special handling | Medtronic 600 series |
| `Unknown` | Default | Fallback |

See [uploader-detection.md](uploader-detection.md) for details.

## Treatment Type Classification

Reporter classifies treatments by `eventType`:

| Property | Event Types | Purpose |
|----------|------------|---------|
| `isSiteChange` | "site change" | Infusion set change |
| `isInsulinChange` | "insulin change" | Cartridge/reservoir change |
| `isSensorChange` | "sensor change", "sensor start" | CGM sensor |
| `isProfileSwitch` | "profile switch" | Profile activation |
| `isTempTarget` | "temporary target" | Temp target |
| `isTempBasal` | "temp basal" | Temporary basal rate |
| `isTempOverride` | "temporary override" | Loop override |
| `isMealBolus` | "meal bolus" | Bolus with carbs |
| `isBolusWizard` | "bolus wizard" | Calculator-assisted bolus |
| `isBGCheck` | "bg check" | Fingerstick BG |
| `isExercise` | "exercise" | Activity record |
| `isSMB` | `isSMB` flag | Super Micro Bolus |

See [treatment-classification.md](treatment-classification.md) for details.

## NS-First Alignment Insights

Reporter's implementation reveals practical interpretations that inform our alignment model:

### Duration Conversion
- **Critical**: NS stores duration in **minutes**, Reporter converts to **seconds** (`* 60`)
- See `TreatmentData.fromJson` line ~1319

### Glucose Gaps
- SGV < 20 or > 1000 treated as gap (`isGap = true`)
- Invalid readings flagged via `isInvalidOrGluc0`

### Timestamp Handling
- Uses `date` field (epoch ms) primarily
- `created_at` parsed via ISO 8601
- Timezone-aware profile resolution

### Deduplication
- Tracks `duplicates` count on TreatmentData
- Uses `pumpId` for pump-sourced dedup

### Bolus Classification
- `isCarbBolus` = isMealBolus OR (isBolusWizard AND carbs > 0)
- Microbolus tracked via `microbolus` field separate from `insulin`

## Code Citation Format

Throughout this documentation, code references use:
```
nr:lib/src/file.dart#L123-L456
```

This maps to files in `externals/nightscout-reporter/`.

## Cross-References

- [Nightscout Data Model](../../docs/10-domain/nightscout-data-model.md) - Authoritative NS schema
- [mapping/nightscout/](../nightscout/) - Core NS collection mappings
- [mapping/loop/nightscout-sync.md](../loop/nightscout-sync.md) - Loop's NS upload patterns

---

## Revision History

| Date | Author | Changes |
|------|--------|---------|
| 2026-01-16 | Agent | Initial extraction from nightscout-reporter source |
