# Trio (FreeAPS) Documentation Inventory

**Repository**: [nightscout/Trio](https://github.com/nightscout/Trio)  
**Alias**: `trio`  
**Language**: Swift (iOS)  
**Last Updated**: 2026-01-16

---

Trio (formerly FreeAPS X) is an iOS closed-loop system that implements the oref0/oref1 algorithm. It bridges the OpenAPS algorithm philosophy with iOS and modern pump integrations.

**Total Swift Files**: 312

---

## Repository Structure

### Core Application

| Directory | Path | Description | Integration Priority |
|-----------|------|-------------|---------------------|
| APS | `FreeAPS/Sources/APS/` | Core algorithm manager | **Critical** |
| Models | `FreeAPS/Sources/Models/` | Data models | **Critical** |
| Services | `FreeAPS/Sources/Services/` | Background services | High |
| Modules | `FreeAPS/Sources/Modules/` | UI modules | Medium |

### APS Subsystem

| Component | Path | Description |
|-----------|------|-------------|
| APSManager | `APS/APSManager.swift` | Main loop controller |
| OpenAPS | `APS/OpenAPS/` | JavaScript algorithm bridge |
| Storage | `APS/Storage/` | Persistent data storage |
| CGM | `APS/CGM/` | CGM source management |

### CGM Sources

| Source | Path | Description |
|--------|------|-------------|
| AppGroupSource | `APS/CGM/AppGroupSource.swift` | Shared app group CGM |
| GlucoseSimulator | `APS/CGM/GlucoseSimulatorSource.swift` | Testing simulator |
| BluetoothTransmitter | `APS/CGM/BluetoothTransmitter.swift` | Direct BLE CGM |
| PluginSource | `APS/CGM/PluginSource.swift` | CGM plugins |

---

## Key Data Models

### Profile & Settings

| Model | File | Description |
|-------|------|-------------|
| `FreeAPSSettings` | `FreeAPSSettings.swift` | App-wide settings |
| `Preferences` | `Preferences.swift` | Algorithm preferences |
| `BasalProfileEntry` | `BasalProfileEntry.swift` | Basal schedule entry |
| `InsulinSensitivities` | `InsulinSensitivities.swift` | ISF schedule |
| `CarbRatios` | `CarbRatios.swift` | CR schedule |
| `BGTargets` | `BGTargets.swift` | Target glucose schedule |

### Glucose & Dosing

| Model | File | Description |
|-------|------|-------------|
| `BloodGlucose` | `BloodGlucose.swift` | CGM glucose reading |
| `Glucose` | `Glucose.swift` | Glucose value wrapper |
| `Suggestion` | `Suggestion.swift` | Algorithm recommendation |
| `IOBEntry` | `IOBEntry.swift` | Insulin on board |
| `CarbsEntry` | `CarbsEntry.swift` | Carb entry |

### Pump & Treatment

| Model | File | Description |
|-------|------|-------------|
| `TempBasal` | `TempBasal.swift` | Temporary basal |
| `TempTarget` | `TempTarget.swift` | Temporary target |
| `PumpHistoryEvent` | `PumpHistoryEvent.swift` | Pump history |
| `PumpStatus` | `PumpStatus.swift` | Pump state |
| `PumpSettings` | `PumpSettings.swift` | Pump configuration |

### Algorithm State

| Model | File | Description |
|-------|------|-------------|
| `Autosens` | `Autosens.swift` | Autosensitivity data |
| `Autotune` | `Autotune.swift` | Autotune results |
| `LoopStats` | `LoopStats.swift` | Loop statistics |
| `Oref2_variables` | `Oref2_variables.swift` | oref2 algorithm state |

---

## OpenAPS Integration

Trio embeds oref0/oref1 JavaScript:

### Key Files

| File | Purpose |
|------|---------|
| `OpenAPS/OpenAPS.swift` | Main algorithm interface |
| `OpenAPS/JavaScriptWorker.swift` | JS execution engine |
| `OpenAPS/Script.swift` | oref0 script loader |
| `OpenAPS/Constants.swift` | Algorithm constants |

### Algorithm Flow

1. **FetchGlucoseManager** - Retrieves CGM readings
2. **APSManager** - Orchestrates loop cycle
3. **OpenAPS.swift** - Prepares data for JS
4. **JavaScriptWorker** - Executes determine-basal.js
5. **Suggestion** - Parses algorithm output
6. **DeviceDataManager** - Sends commands to pump

---

## Nightscout Integration

| Component | Path | Description |
|-----------|------|-------------|
| NightscoutConfig | `Modules/NightscoutConfig/` | NS configuration UI |
| NightscoutSettings | `Models/NightscoutSettings.swift` | NS connection settings |
| NightscoutStatus | `Models/NightscoutStatus.swift` | Upload status |
| NightscoutTreatment | `Models/NightscoutTreatment.swift` | Treatment sync model |
| FetchAnnouncementsManager | `APS/FetchAnnouncementsManager.swift` | Remote commands |
| FetchTreatmentsManager | `APS/FetchTreatmentsManager.swift` | Treatment sync |

### Sync Mappings

| Trio Model | Nightscout | Event Type |
|------------|------------|------------|
| `Suggestion` (SMB) | `treatments` | `SMB` |
| `TempBasal` | `treatments` | `Temp Basal` |
| `CarbsEntry` | `treatments` | `Carb Correction` |
| `TempTarget` | `treatments` | `Temporary Target` |
| `BloodGlucose` | `entries` | - |
| Loop Status | `devicestatus` | `openaps` object |

---

## Override Implementation

Trio implements overrides via:

| Component | Location | Description |
|-----------|----------|-------------|
| OverrideProfilesConfig | `Modules/OverrideProfilesConfig/` | Override management UI |
| Override presets | `Models/` (not explicit) | Stored via FreeAPSSettings |
| Active override | `FreeAPSSettings` | Current override state |

### Override Parameters

- Target glucose adjustment
- ISF percentage adjustment
- CR percentage adjustment
- Basal percentage adjustment
- Duration

---

## Alignment Gaps

1. **Override Format**: Trio overrides stored differently than Loop or AAPS
2. **oref2 State**: `Oref2_variables` includes algorithm state not in other systems
3. **Profile Structure**: Uses separate files for basals, ISF, CR vs unified profile
4. **Announcement/Remote Commands**: Trio-specific remote bolus/carb announcement system
