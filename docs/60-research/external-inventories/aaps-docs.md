# AndroidAPS (AAPS) Documentation Inventory

**Repository**: [nightscout/AndroidAPS](https://github.com/nightscout/AndroidAPS)  
**Alias**: `aaps`  
**Language**: Kotlin (Android)  
**Last Updated**: 2026-01-16

---

AndroidAPS is an Android-based closed-loop insulin delivery system that implements multiple algorithm variants including OpenAPS AMA, SMB, and AutoISF.

**Architecture**: Plugin-based modular system

---

## Repository Structure

### Core Modules

| Module | Path | Description | Integration Priority |
|--------|------|-------------|---------------------|
| app | `app/` | Main application | **Critical** |
| core | `core/` | Shared interfaces and utilities | **Critical** |
| database | `database/` | Room database implementation | **Critical** |
| plugins | `plugins/` | All plugin implementations | **Critical** |

### Algorithm Plugins

| Plugin | Path | Description | Integration Priority |
|--------|------|-------------|---------------------|
| openAPSAMA | `plugins/aps/src/main/kotlin/.../openAPSAMA/` | Advanced Meal Assist algorithm | High |
| openAPSSMB | `plugins/aps/src/main/kotlin/.../openAPSSMB/` | Super Micro Bolus algorithm | **Critical** |
| openAPSAutoISF | `plugins/aps/src/main/kotlin/.../openAPSAutoISF/` | AutoISF variant | High |
| loop | `plugins/aps/src/main/kotlin/.../loop/` | Loop controller | **Critical** |

### APS Plugin Files

| File | Path | Purpose |
|------|------|---------|
| `DetermineBasalAdapterSMBJS.kt` | `openAPSSMB/` | JavaScript bridge for oref0/oref1 |
| `DetermineBasalResultSMBFromJS.kt` | `openAPSSMB/` | Parse algorithm output |
| `OpenAPSSMBPlugin.kt` | `openAPSSMB/` | Plugin lifecycle |
| `OpenAPSFragment.kt` | `aps/` | UI for algorithm status |

---

## Key Data Entities

### Profile & Settings

| Entity | Location | Description |
|--------|----------|-------------|
| `Profile` | `core/interfaces/profile/` | Active therapy settings |
| `ProfileSwitch` | `database/entities/` | Profile change event |
| `EffectiveProfileSwitch` | `database/entities/` | Computed active profile |
| `ProfileStore` | `core/` | Profile collection |

### Dosing & Events

| Entity | Location | Description |
|--------|----------|-------------|
| `TemporaryBasal` | `database/entities/` | Temp basal record |
| `Bolus` | `database/entities/` | Bolus record |
| `Carbs` | `database/entities/` | Carb entry |
| `TemporaryTarget` | `database/entities/` | Temp target record |
| `OfflineEvent` | `database/entities/` | Loop suspension/disconnect |

### Algorithm State

| Entity | Location | Description |
|--------|----------|-------------|
| `GlucoseValue` | `database/entities/` | CGM glucose reading |
| `APSResult` | `plugins/aps/` | Algorithm decision output |
| `IobTotal` | `core/` | Calculated IOB |
| `MealData` | `core/` | COB and meal info |
| `AutosensData` | `core/` | Autosens calculation |

---

## Algorithm Architecture

AAPS embeds the oref0/oref1 JavaScript algorithm and calls it via a JS bridge:

1. **Profile Preparation** - Converts AAPS Profile to oref format
2. **Glucose History** - Passes recent BG values
3. **IOB Calculation** - Native Kotlin calculation passed to JS
4. **Meal Detection** - COB and UAM (unannounced meal) detection
5. **determine-basal** - JS algorithm execution
6. **Result Parsing** - Parse JS output to Kotlin objects
7. **Enactment** - Send commands to pump driver

### Algorithm Variants

| Algorithm | Description | Key Features |
|-----------|-------------|--------------|
| AMA | Advanced Meal Assist | Temporary basals only, meal detection |
| SMB | Super Micro Bolus | Automatic micro-boluses, UAM |
| AutoISF | Auto Insulin Sensitivity Factor | Dynamic ISF adjustment |

---

## Safety Constraints

| Parameter | Database Field | Description |
|-----------|----------------|-------------|
| Max IOB | `preferences.maxIOB` | Maximum IOB limit |
| Max Basal | `preferences.maxBasal` | Maximum basal rate |
| Max SMB | `preferences.maxSMB` | Maximum SMB size |
| DIA | `profile.dia` | Duration of insulin action |
| Bolus Speed | `pump.bolusSpeed` | Pump bolus delivery rate |

---

## Nightscout Sync

AAPS uses NSClient plugin for bidirectional Nightscout sync:

| AAPS Entity | Nightscout Collection | Event Type |
|-------------|----------------------|------------|
| `Bolus` | `treatments` | `SMB`, `Meal Bolus`, `Correction Bolus` |
| `TemporaryBasal` | `treatments` | `Temp Basal` |
| `Carbs` | `treatments` | `Carb Correction` |
| `ProfileSwitch` | `treatments` | `Profile Switch` |
| `TemporaryTarget` | `treatments` | `Temporary Target` |
| `GlucoseValue` | `entries` | - |
| Loop Status | `devicestatus` | `openaps` object |

---

## Alignment Gaps

### GAP-002: ProfileSwitch Semantic Mismatch

AAPS's `ProfileSwitch` can represent:
1. Complete profile change
2. Percentage adjustment (e.g., 110%)
3. Time shift

Nightscout treats all as "Profile Switch" events without distinguishing these semantically different operations.

### GAP-003: Sync Identity

AAPS generates UUIDs for entities but Nightscout uses `_id`. Mapping between systems requires careful identity management.

### Additional Gaps

- **Algorithm State**: AAPS autosens/autoISF state not fully represented in Nightscout
- **Predictions**: AAPS predictions differ in format from Loop predictions
- **Offline Events**: AAPS offline/suspend events map imperfectly to Nightscout
