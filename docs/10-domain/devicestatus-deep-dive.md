# DeviceStatus Structure Deep Dive

This document provides a comprehensive field mapping of the Nightscout `devicestatus` collection across different AID (Automated Insulin Delivery) systems. It enables cross-system analytics, debugging tools, and unified data interpretation.

---

## Overview

The `devicestatus` collection stores controller state, pump status, and uploader information. However, **the structure varies significantly** between systems:

| System | Top-Level Object | Structure Type | Prediction Format |
|--------|------------------|----------------|-------------------|
| **Loop** (iOS) | `loop` | Flat | Single combined array |
| **Trio** (iOS, oref0-based) | `openaps` | Nested | 4 curves (IOB, COB, UAM, ZT) |
| **AAPS** (Android, oref0-based) | `openaps` | Nested | 4 curves (IOB, COB, UAM, ZT) |
| **OpenAPS** (rig-based) | `openaps` | Nested | 4 curves (IOB, COB, UAM, ZT) |

### Key Structural Difference

```
Loop (Flat):                          oref0-based (Nested):
─────────────                         ────────────────────
devicestatus: {                       devicestatus: {
  device: "loop://iPhone",              device: "Trio",
  loop: {                               openaps: {
    iob: { iob: 2.35, ... },              iob: { iob: 1.5, basaliob: 0.8, ... },
    cob: { cob: 45, ... },                suggested: {
    predicted: { values: [...] },           bg: 120,
    enacted: { rate: 1.2, ... }             eventualBG: 95,
  },                                        COB: 20,      // COB/IOB as values
  pump: { ... },                            IOB: 1.5,
  uploader: { ... },                        predBGs: {    // prediction arrays
  override: { ... }                           IOB: [...],
}                                             COB: [...],
                                              UAM: [...],
                                              ZT: [...]
                                            },
                                            rate: 0.9,
                                            duration: 30
                                          },
                                          enacted: { ... }  // null when open loop
                                        },
                                        pump: { ... },
                                        uploader: { ... }
                                      }
```

**Note on predBGs location**: In oref0 systems, `predBGs` can appear under either `suggested` or `enacted`. Trio strips predictions from whichever object is older to reduce upload size. Always check both locations when extracting predictions.

---

## Complete Field Mapping

### Root-Level Fields

| Field | Loop | Trio | AAPS | Optional | Description |
|-------|------|------|------|----------|-------------|
| `_id` | ✓ | ✓ | ✓ | No | MongoDB document ID |
| `device` | `"loop://{deviceName}"` | `"Trio"` | `"openaps://{model}"` | No | Device identifier |
| `created_at` | ✓ | ✓ | ✓ | No | ISO 8601 timestamp |
| `mills` | ✓ | ✓ | ✓ | No | Epoch milliseconds |
| `loop` | ✓ | ✗ | ✗ | No | Loop-specific status |
| `openaps` | ✗ | ✓ | ✓ | No | OpenAPS/oref0 status |
| `pump` | ✓ | ✓ | ✓ | Yes | Pump status (may be absent if pump disconnected) |
| `uploader` | ✓ | ✓ | ✓ | Yes | Uploader device status |
| `override` | ✓ | ✗ | ✗ | Yes | Active override status (Loop only) |
| `configuration` | ✗ | ✗ | ✓ | Yes | Algorithm configuration snapshot (AAPS only) |
| `uploaderBattery` | ✗ | ✗ | ✓ | Yes | Alternate battery field (AAPS) |
| `isCharging` | ✗ | ✗ | ✓ | Yes | Charging status (AAPS) |

### Optionality Notes

- **`openaps.enacted`**: NULL when loop is running in **open loop mode** (suggestions only, no automatic enactment)
- **`openaps.suggested.predBGs`**: May be **stripped/trimmed** to save bandwidth; Trio includes predictions only in the most recent of `suggested` or `enacted`
- **`loop.failureReason`**: Only present when loop cycle failed
- **`pump`**: May be absent if pump communication failed

---

## Loop `loop` Object

Loop uses a **flat structure** where IOB, COB, predictions, and enacted status are direct children of the `loop` object.

### Source Reference
- **File**: `loop:NightscoutService/NightscoutServiceKit/Extensions/StoredDosingDecision.swift`
- **Model**: `NightscoutKit.LoopStatus`

### Loop Status Fields

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `loop.name` | String | App bundle name | `"Loop"` |
| `loop.version` | String | App version | `"3.4.0"` |
| `loop.timestamp` | ISO 8601 | Status timestamp | `"2026-01-17T12:00:00Z"` |
| `loop.failureReason` | String? | Error if loop failed | `"Pump communication timeout"` |

### Loop IOB Status

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `loop.iob.timestamp` | ISO 8601 | IOB calculation time | `"2026-01-17T12:00:00Z"` |
| `loop.iob.iob` | Number | Total insulin on board (U) | `2.35` |

```json
{
  "loop": {
    "iob": {
      "timestamp": "2026-01-17T12:00:00Z",
      "iob": 2.35
    }
  }
}
```

### Loop COB Status

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `loop.cob.timestamp` | ISO 8601 | COB calculation time | `"2026-01-17T12:00:00Z"` |
| `loop.cob.cob` | Number | Carbs on board (g) | `45.5` |

```json
{
  "loop": {
    "cob": {
      "timestamp": "2026-01-17T12:00:00Z",
      "cob": 45.5
    }
  }
}
```

### Loop Predictions

**Critical Difference**: Loop uploads prediction data that represents the combined expected BG trajectory, unlike oref0 systems which provide four separate scenario curves.

| Field | Type | Description |
|-------|------|-------------|
| `loop.predicted.startDate` | ISO 8601 | First prediction timestamp |
| `loop.predicted.values` | Number[] | Predicted BG values (mg/dL or mmol/L based on user units), 5-min intervals |

```json
{
  "loop": {
    "predicted": {
      "startDate": "2026-01-17T12:00:00Z",
      "values": [120, 125, 130, 128, 122, 115, 108, 102, 98, 95, 93, 92]
    }
  }
}
```

**Note**: Loop's prediction is the final combined result after effect calculation. The individual effect contributions (insulin, carbs, momentum, retrospective correction) are computed internally but are not uploaded to Nightscout in Loop's current implementation (as of v3.4.x). See GAP-DS-001 for a proposal to optionally include effect timelines.

**Unit Warning**: Prediction values follow the user's configured glucose units. See [Determining Glucose Units](#determining-glucose-units) below for how to identify the unit context.

### Loop Automatic Dose Recommendation

| Field | Type | Description |
|-------|------|-------------|
| `loop.automaticDoseRecommendation.timestamp` | ISO 8601 | Recommendation time |
| `loop.automaticDoseRecommendation.tempBasalAdjustment.rate` | Number | Recommended temp basal (U/hr) |
| `loop.automaticDoseRecommendation.tempBasalAdjustment.duration` | Number | Duration (seconds) |
| `loop.automaticDoseRecommendation.bolusVolume` | Number | Recommended bolus (U) |

### Loop Enacted

| Field | Type | Description |
|-------|------|-------------|
| `loop.enacted.timestamp` | ISO 8601 | Enactment time |
| `loop.enacted.rate` | Number | Enacted temp basal rate (U/hr) |
| `loop.enacted.duration` | Number | Duration (seconds) |
| `loop.enacted.received` | Boolean | Whether pump confirmed |
| `loop.enacted.bolusVolume` | Number | Enacted bolus (U) |

### Loop Recommended Bolus

| Field | Type | Description |
|-------|------|-------------|
| `loop.recommendedBolus` | Number? | Manual bolus recommendation (U) |

---

## oref0-Based `openaps` Object (Trio, AAPS, OpenAPS)

oref0-based systems use a **nested structure** where the algorithm's `suggested` and `enacted` objects contain detailed decision data including **four separate prediction curves**.

### Source References
- **Trio**: `trio:Trio/Sources/Models/NightscoutStatus.swift`
- **AAPS**: `aaps:core/nssdk/src/main/kotlin/app/aaps/core/nssdk/localmodel/devicestatus/NSDeviceStatus.kt`
- **oref0**: `oref0:lib/determine-basal/determine-basal.js`

### OpenAPS Status Fields

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `openaps.version` | String | oref0 algorithm version | `"0.7.1"` |

### OpenAPS IOB

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `openaps.iob.iob` | Number | Total IOB (U) | `1.5` |
| `openaps.iob.basaliob` | Number | Basal-only IOB (U) | `0.8` |
| `openaps.iob.activity` | Number | Insulin activity (U/min) | `0.02` |
| `openaps.iob.time` | ISO 8601 | Calculation timestamp | `"2026-01-17T12:00:00Z"` |
| `openaps.iob.lastBolusTime` | Number? | Last bolus epoch (ms) | `1705492800000` |
| `openaps.iob.lastTemp` | Object? | Last temp basal info | See below |

```json
{
  "openaps": {
    "iob": {
      "iob": 1.5,
      "basaliob": 0.8,
      "activity": 0.02,
      "time": "2026-01-17T12:00:00Z"
    }
  }
}
```

### OpenAPS Suggested (Algorithm Decision)

The `suggested` object contains the full algorithm output from `determine-basal.js`:

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `openaps.suggested.temp` | String | Temp type | `"absolute"` |
| `openaps.suggested.bg` | Number | Current BG (mg/dL) | `120` |
| `openaps.suggested.tick` | String/Number | BG delta indicator | `"+5"` |
| `openaps.suggested.eventualBG` | Number | Predicted eventual BG | `95` |
| `openaps.suggested.sensitivityRatio` | Number | Autosens ratio | `1.0` |
| `openaps.suggested.insulinReq` | Number | Insulin required (U) | `0.5` |
| `openaps.suggested.COB` | Number | Carbs on board (g) | `20` |
| `openaps.suggested.IOB` | Number | Insulin on board (U) | `1.5` |
| `openaps.suggested.BGI` | Number | BG impact from insulin | `-2.5` |
| `openaps.suggested.deviation` | Number | Unexplained BG change | `-15` |
| `openaps.suggested.ISF` | Number | Insulin sensitivity | `50` |
| `openaps.suggested.CR` | Number | Carb ratio | `10` |
| `openaps.suggested.target_bg` | Number | Target BG | `100` |
| `openaps.suggested.reason` | String | Human-readable explanation | `"COB: 20g; Dev: -15; ..."` |
| `openaps.suggested.rate` | Number | Recommended temp rate (U/hr) | `1.2` |
| `openaps.suggested.duration` | Number | Recommended duration (min) | `30` |
| `openaps.suggested.units` | Number? | SMB size if applicable (U) | `0.3` |
| `openaps.suggested.deliverAt` | ISO 8601 | Suggestion timestamp | `"2026-01-17T12:00:00Z"` |
| `openaps.suggested.predBGs` | Object | **Four prediction curves** | See below |

### OpenAPS Prediction Curves (predBGs)

**Critical Difference**: oref0 provides **four separate prediction arrays**, each representing a different scenario:

| Curve | Description | Use Case |
|-------|-------------|----------|
| `predBGs.IOB` | Prediction considering only insulin on board | Worst-case low if no carbs active |
| `predBGs.COB` | Prediction including carb absorption | Expected path with announced carbs |
| `predBGs.UAM` | Unannounced Meal prediction | Handles unannounced food/rises |
| `predBGs.ZT` | Zero Temp prediction | What happens if insulin stops now |

```json
{
  "openaps": {
    "suggested": {
      "predBGs": {
        "IOB": [115, 110, 105, 102, 100, 99, 98, 97, 96, 95],
        "COB": [120, 125, 130, 128, 122, 115, 108, 102, 98, 95],
        "UAM": [115, 108, 102, 98, 95, 93, 92, 91, 90, 90],
        "ZT": [100, 95, 90, 88, 87, 86, 85, 84, 83, 82]
      }
    }
  }
}
```

**Values**: Each array contains predicted BG values (mg/dL) at 5-minute intervals starting from the current time.

### OpenAPS Enacted

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `openaps.enacted.rate` | Number | Enacted temp rate (U/hr) | `1.2` |
| `openaps.enacted.duration` | Number | Duration (min) | `30` |
| `openaps.enacted.recieved` | Boolean | Pump confirmed | `true` |
| `openaps.enacted.timestamp` | ISO 8601 | Enactment time | `"2026-01-17T12:00:00Z"` |

**Note**: The field is spelled `recieved` (typo preserved from original oref0).

---

## Pump Status

Both Loop and oref0 systems upload pump status, but field availability varies by pump type.

### Common Pump Fields

| Field | Loop | Trio | AAPS | Description |
|-------|------|------|------|-------------|
| `pump.clock` | ✓ | ✓ | ✓ | Pump clock time |
| `pump.reservoir` | ✓ | ✓ | ✓ | Reservoir level (U) |
| `pump.battery` | ✓ | ✓ | ✓ | Battery status object |
| `pump.status.suspended` | ✓ | ✓ | ✓ | Pump suspended flag |
| `pump.status.bolusing` | ✓ | ✗ | ✗ | Currently bolusing |

### Pump Battery Object

| Field | Type | Description |
|-------|------|-------------|
| `pump.battery.percent` | Number | Battery percentage (0-100) |
| `pump.battery.voltage` | Number? | Battery voltage (some pumps) |
| `pump.battery.status` | String? | `"normal"`, `"low"` |

### Loop-Specific Pump Fields

| Field | Type | Description |
|-------|------|-------------|
| `pump.pumpID` | String | Pump identifier |
| `pump.manufacturer` | String | Pump manufacturer |
| `pump.model` | String | Pump model |
| `pump.secondsFromGMT` | Number | Pump timezone offset |

```json
{
  "pump": {
    "clock": "2026-01-17T12:00:00Z",
    "pumpID": "123456",
    "manufacturer": "Insulet",
    "model": "Omnipod DASH",
    "reservoir": 150.5,
    "battery": { "percent": 75 },
    "status": { "suspended": false, "bolusing": false }
  }
}
```

---

## Uploader Status

| Field | Loop | Trio | AAPS | Description |
|-------|------|------|------|-------------|
| `uploader.battery` | ✓ | ✓ | ✓ | Phone/rig battery % |
| `uploaderBattery` | ✗ | ✗ | ✓ | AAPS alternate field |
| `isCharging` | ✗ | ✗ | ✓ | AAPS charging status |

```json
{
  "uploader": {
    "battery": 85
  }
}
```

---

## Loop Override Status

Loop includes override information in devicestatus. oref0 systems handle overrides differently (typically as treatments).

| Field | Type | Description |
|-------|------|-------------|
| `override.name` | String | Override preset name |
| `override.timestamp` | ISO 8601 | Override start time |
| `override.active` | Boolean | Currently active |
| `override.currentCorrectionRange` | Object | Modified target range |
| `override.duration` | Number | Remaining duration (seconds) |
| `override.multiplier` | Number | Insulin needs scale factor |

```json
{
  "override": {
    "name": "Exercise",
    "timestamp": "2026-01-17T11:00:00Z",
    "active": true,
    "currentCorrectionRange": {
      "minValue": 140,
      "maxValue": 160
    },
    "duration": 3600,
    "multiplier": 0.8
  }
}
```

---

## AAPS Configuration Object

AAPS includes detailed configuration snapshots for debugging and analysis.

| Field | Type | Description |
|-------|------|-------------|
| `configuration.pump` | String | Pump driver name |
| `configuration.version` | String | AAPS version |
| `configuration.aps` | String | APS algorithm name |
| `configuration.sensitivity` | String | Sensitivity plugin |
| `configuration.smoothing` | String | BG smoothing algorithm |
| `configuration.insulinConfiguration` | Object | Insulin model settings |
| `configuration.apsConfiguration` | Object | APS settings snapshot |
| `configuration.sensitivityConfiguration` | Object | Sensitivity settings |
| `configuration.safetyConfiguration` | Object | Safety limits |

---

## Cross-System Field Equivalence

### IOB Mapping

| Concept | Loop | oref0 (Trio/AAPS) | Notes |
|---------|------|-------------------|-------|
| Total IOB | `loop.iob.iob` | `openaps.iob.iob` | Equivalent |
| Basal IOB | Not exposed | `openaps.iob.basaliob` | oref0 only |
| Insulin Activity | Not exposed | `openaps.iob.activity` | oref0 only |
| IOB Timestamp | `loop.iob.timestamp` | `openaps.iob.time` | Equivalent |

### COB Mapping

| Concept | Loop | oref0 (Trio/AAPS) | Notes |
|---------|------|-------------------|-------|
| Carbs on Board | `loop.cob.cob` | `openaps.suggested.COB` | Different location |
| COB Timestamp | `loop.cob.timestamp` | (via suggested timestamp) | Different approach |

### Prediction Mapping

| Concept | Loop | oref0 (Trio/AAPS) | Notes |
|---------|------|-------------------|-------|
| Primary Prediction | `loop.predicted.values` | N/A | Loop only |
| IOB-only Prediction | Not exposed | `openaps.suggested.predBGs.IOB` | oref0 only |
| COB Prediction | Not exposed | `openaps.suggested.predBGs.COB` | oref0 only |
| UAM Prediction | Not exposed | `openaps.suggested.predBGs.UAM` | oref0 only |
| Zero-Temp Prediction | Not exposed | `openaps.suggested.predBGs.ZT` | oref0 only |
| Prediction Start | `loop.predicted.startDate` | `openaps.suggested.deliverAt` | Equivalent |

### Enacted Action Mapping

| Concept | Loop | oref0 (Trio/AAPS) | Notes |
|---------|------|-------------------|-------|
| Temp Basal Rate | `loop.enacted.rate` | `openaps.enacted.rate` | Equivalent |
| Temp Basal Duration | `loop.enacted.duration` (sec) | `openaps.enacted.duration` (min) | **Different units!** |
| Pump Confirmed | `loop.enacted.received` | `openaps.enacted.recieved` | Different spelling |
| SMB Amount | `loop.enacted.bolusVolume` | `openaps.suggested.units` | Different location |

### Algorithm Metadata Mapping

| Concept | Loop | oref0 (Trio/AAPS) | Notes |
|---------|------|-------------------|-------|
| App Version | `loop.version` | `openaps.version` | Equivalent |
| Current BG | Not in devicestatus | `openaps.suggested.bg` | oref0 only |
| Eventual BG | Not exposed | `openaps.suggested.eventualBG` | oref0 only |
| Sensitivity | Not exposed | `openaps.suggested.sensitivityRatio` | oref0 only |
| Target BG | Not exposed | `openaps.suggested.target_bg` | oref0 only |
| Decision Reason | Not exposed | `openaps.suggested.reason` | oref0 only |

---

## Analytics Normalization Guide

For cross-system analytics tools, normalize DeviceStatus data using these patterns.

### Important Edge Cases

Before using these functions, be aware of:

1. **Missing/Trimmed Data**: `openaps.enacted`, `openaps.suggested.predBGs`, and `loop.predicted` may be null/absent
2. **Unit Differences**: 
   - Duration: Loop uses **seconds**, oref0 uses **minutes**
   - Glucose: May be **mg/dL or mmol/L** based on user configuration
3. **Open Loop Mode**: `openaps.enacted` is null when not auto-enacting
4. **Prediction Trimming**: Trio strips predictions from whichever of `suggested`/`enacted` is older

### Determining Glucose Units

To correctly interpret glucose values in devicestatus, you need to know the user's configured units. Sources for unit information (in priority order):

1. **Profile Store**: Check `profile.store[profileName].units` → `"mg/dL"` or `"mmol/L"`
2. **Loop Settings**: In Loop devicestatus, units may be in `loopSettings.glucoseTargetRangeSchedule.unit`
3. **AAPS Configuration**: Check `configuration.sensitivityConfiguration` or related objects
4. **Heuristic Detection**: If BG values are typically < 30, assume mmol/L; if > 50, assume mg/dL

**Recommended**: Always fetch the active profile alongside devicestatus to ensure correct unit interpretation.

### Unit Conversion Helpers

```javascript
const MMOL_TO_MGDL = 18.0182;

function toMgdl(value, units) {
  if (!value) return null;
  return units === 'mmol/L' ? value * MMOL_TO_MGDL : value;
}

function convertPredictions(values, units) {
  if (!Array.isArray(values)) return null;
  return units === 'mmol/L' 
    ? values.map(v => v * MMOL_TO_MGDL)
    : values;
}

// Heuristic unit detection (use only as fallback)
function detectUnits(bgValue) {
  if (bgValue < 30) return 'mmol/L';
  if (bgValue > 50) return 'mg/dL';
  return null; // Ambiguous range (30-50)
}
```

### Unified IOB Extraction

```javascript
function extractIOB(devicestatus) {
  if (devicestatus.loop?.iob) {
    return {
      iob: devicestatus.loop.iob.iob,
      timestamp: devicestatus.loop.iob.timestamp,
      basaliob: null,  // Not available in Loop
      activity: null   // Not available in Loop
    };
  }
  if (devicestatus.openaps?.iob) {
    return {
      iob: devicestatus.openaps.iob.iob,
      timestamp: devicestatus.openaps.iob.time,
      basaliob: devicestatus.openaps.iob.basaliob ?? null,
      activity: devicestatus.openaps.iob.activity ?? null
    };
  }
  return null;
}
```

### Unified COB Extraction

```javascript
function extractCOB(devicestatus) {
  if (devicestatus.loop?.cob) {
    return {
      cob: devicestatus.loop.cob.cob,
      timestamp: devicestatus.loop.cob.timestamp
    };
  }
  if (devicestatus.openaps?.suggested) {
    return {
      cob: devicestatus.openaps.suggested.COB,
      timestamp: devicestatus.openaps.suggested.deliverAt
    };
  }
  return null;
}
```

### Unified Prediction Extraction

```javascript
function extractPredictions(devicestatus, units = 'mg/dL') {
  // Helper to safely get and optionally convert prediction arrays
  const getPreds = (predBGs) => ({
    IOB: convertPredictions(predBGs?.IOB, units),
    COB: convertPredictions(predBGs?.COB, units),
    UAM: convertPredictions(predBGs?.UAM, units),
    ZT: convertPredictions(predBGs?.ZT, units)
  });
  
  if (devicestatus.loop?.predicted?.values) {
    // Loop: single combined prediction
    return {
      type: 'combined',
      startDate: devicestatus.loop.predicted.startDate,
      combined: convertPredictions(devicestatus.loop.predicted.values, units),
      IOB: null,
      COB: null,
      UAM: null,
      ZT: null
    };
  }
  
  // oref0: check both suggested and enacted (one may have predictions stripped)
  const suggested = devicestatus.openaps?.suggested;
  const enacted = devicestatus.openaps?.enacted;
  
  // Use whichever has predBGs (Trio strips from older one)
  const predSource = suggested?.predBGs ? suggested : 
                     (enacted?.predBGs ? enacted : null);
  
  if (predSource?.predBGs) {
    return {
      type: 'separated',
      startDate: predSource.deliverAt || predSource.timestamp,
      combined: null,
      ...getPreds(predSource.predBGs)
    };
  }
  
  return null;  // No predictions available
}
```

### Unified Enacted Extraction

```javascript
function extractEnacted(devicestatus) {
  if (devicestatus.loop?.enacted) {
    return {
      rate: devicestatus.loop.enacted.rate,
      durationMinutes: devicestatus.loop.enacted.duration / 60,  // Convert seconds to minutes
      confirmed: devicestatus.loop.enacted.received ?? false,
      smbUnits: devicestatus.loop.enacted.bolusVolume ?? 0,
      timestamp: devicestatus.loop.enacted.timestamp,
      isOpenLoop: false
    };
  }
  
  // oref0: enacted is null in open loop mode
  if (devicestatus.openaps?.enacted) {
    return {
      rate: devicestatus.openaps.enacted.rate,
      durationMinutes: devicestatus.openaps.enacted.duration,  // Already in minutes
      confirmed: devicestatus.openaps.enacted.recieved ?? false,  // Note: typo preserved
      smbUnits: devicestatus.openaps.suggested?.units ?? 0,
      timestamp: devicestatus.openaps.enacted.timestamp,
      isOpenLoop: false
    };
  }
  
  // Open loop: suggested exists but enacted is null
  if (devicestatus.openaps?.suggested && !devicestatus.openaps?.enacted) {
    return {
      rate: devicestatus.openaps.suggested.rate,
      durationMinutes: devicestatus.openaps.suggested.duration,
      confirmed: false,
      smbUnits: devicestatus.openaps.suggested.units ?? 0,
      timestamp: devicestatus.openaps.suggested.deliverAt,
      isOpenLoop: true  // Suggestion only, not enacted
    };
  }
  
  return null;
}
```

### System Detection

```javascript
function detectSystem(devicestatus) {
  if (devicestatus.loop) {
    return {
      system: 'Loop',
      family: 'loop',
      version: devicestatus.loop.version
    };
  }
  if (devicestatus.openaps) {
    const device = devicestatus.device?.toLowerCase() || '';
    if (device.includes('trio')) {
      return { system: 'Trio', family: 'oref0', version: devicestatus.openaps.version };
    }
    if (device.includes('aaps') || device.includes('androidaps')) {
      return { system: 'AAPS', family: 'oref0', version: devicestatus.openaps.version };
    }
    return { system: 'OpenAPS', family: 'oref0', version: devicestatus.openaps.version };
  }
  return { system: 'Unknown', family: 'unknown', version: null };
}
```

---

## Example Complete DeviceStatus Documents

### Loop Example

```json
{
  "_id": "678abc123def456",
  "device": "loop://iPhone",
  "created_at": "2026-01-17T12:05:00Z",
  "mills": 1705493100000,
  "loop": {
    "name": "Loop",
    "version": "3.4.0",
    "timestamp": "2026-01-17T12:05:00Z",
    "iob": {
      "timestamp": "2026-01-17T12:05:00Z",
      "iob": 2.35
    },
    "cob": {
      "timestamp": "2026-01-17T12:05:00Z",
      "cob": 45.5
    },
    "predicted": {
      "startDate": "2026-01-17T12:05:00Z",
      "values": [120, 125, 130, 128, 122, 115, 108, 102, 98, 95, 93, 92]
    },
    "automaticDoseRecommendation": {
      "timestamp": "2026-01-17T12:05:00Z",
      "tempBasalAdjustment": {
        "rate": 1.2,
        "duration": 1800
      },
      "bolusVolume": 0
    },
    "enacted": {
      "timestamp": "2026-01-17T12:05:00Z",
      "rate": 1.2,
      "duration": 1800,
      "received": true,
      "bolusVolume": 0
    }
  },
  "pump": {
    "clock": "2026-01-17T12:05:00Z",
    "pumpID": "1234567890",
    "manufacturer": "Insulet",
    "model": "Omnipod DASH",
    "reservoir": 142.5,
    "battery": { "percent": 80 },
    "status": { "suspended": false, "bolusing": false }
  },
  "uploader": {
    "battery": 75
  },
  "override": {
    "name": "Default",
    "timestamp": "2026-01-17T12:05:00Z",
    "active": false
  }
}
```

### Trio Example

```json
{
  "_id": "789def456abc123",
  "device": "Trio",
  "created_at": "2026-01-17T12:05:00Z",
  "mills": 1705493100000,
  "openaps": {
    "iob": {
      "iob": 1.5,
      "basaliob": 0.8,
      "activity": 0.02,
      "time": "2026-01-17T12:05:00Z"
    },
    "suggested": {
      "temp": "absolute",
      "bg": 120,
      "tick": "+5",
      "eventualBG": 95,
      "sensitivityRatio": 1.0,
      "insulinReq": 0.3,
      "COB": 20,
      "IOB": 1.5,
      "BGI": -2.5,
      "deviation": -15,
      "ISF": 50,
      "CR": 10,
      "target_bg": 100,
      "reason": "COB: 20g, Dev: -15, BGI: -2.5, ISF: 50, CR: 10, Target: 100; Eventual BG 95 >= 90, no temp required",
      "rate": 0.9,
      "duration": 30,
      "deliverAt": "2026-01-17T12:05:00Z",
      "predBGs": {
        "IOB": [115, 110, 105, 102, 100, 99, 98, 97, 96, 95, 94, 93],
        "COB": [120, 125, 128, 125, 120, 115, 110, 105, 100, 97, 95, 93],
        "UAM": [115, 108, 102, 98, 95, 93, 92, 91, 90, 90, 89, 88],
        "ZT": [100, 95, 92, 90, 88, 87, 86, 85, 84, 83, 82, 81]
      }
    },
    "enacted": {
      "rate": 0.9,
      "duration": 30,
      "recieved": true,
      "timestamp": "2026-01-17T12:05:00Z"
    },
    "version": "0.7.1"
  },
  "pump": {
    "clock": "2026-01-17T12:05:00Z",
    "battery": { "percent": 75 },
    "reservoir": 150.5,
    "status": { "suspended": false }
  },
  "uploader": {
    "battery": 85
  }
}
```

---

## Known Gaps and Limitations

### GAP-DS-001: No Effect Timelines in Loop

Loop computes individual effect timelines (insulin, carbs, momentum, retrospective correction) internally but does NOT upload them. This limits debugging and cross-project comparison.

**Source**: Analysis of `loop:NightscoutService/NightscoutServiceKit/Extensions/StoredDosingDecision.swift` and `loop:NightscoutService/` shows effect arrays are computed but not included in the DeviceStatus upload.

**Proposal** (not yet implemented): Consider adding optional effect timeline upload:
```json
{
  "loop": {
    "effects": {
      "insulin": [...],
      "carbs": [...],
      "momentum": [...],
      "retrospectiveCorrection": [...]
    }
  }
}
```

This would align with oref0's detailed output and enable cross-system debugging.

### GAP-DS-002: Prediction Array Incompatibility

Loop's single combined prediction array cannot be directly compared to oref0's four separate curves without understanding what inputs went into Loop's prediction.

**Workaround**: When analyzing Loop data alongside oref0 data, treat Loop's `predicted.values` as the "best estimate" equivalent to oref0's scenario-blended prediction.

### GAP-DS-003: Duration Unit Inconsistency

- Loop: Duration in **seconds**
- oref0: Duration in **minutes**

Always convert to a common unit when normalizing data.

### GAP-DS-004: Missing Algorithm Transparency in Loop

oref0 exposes extensive algorithm state (`eventualBG`, `sensitivityRatio`, `ISF`, `CR`, `deviation`, `reason`). Loop uploads minimal algorithm context, making retrospective analysis difficult.

---

## Code References

| System | File | Purpose |
|--------|------|---------|
| Loop | `loop:NightscoutService/NightscoutServiceKit/Extensions/StoredDosingDecision.swift` | DeviceStatus construction |
| Loop | `loop:NightscoutService/NightscoutServiceKit/Extensions/NightscoutUploader.swift` | Upload logic |
| Trio | `trio:Trio/Sources/Models/NightscoutStatus.swift` | DeviceStatus model |
| Trio | `trio:Trio/Sources/Services/Network/Nightscout/NightscoutManager.swift` | Upload orchestration |
| AAPS | `aaps:core/nssdk/src/main/kotlin/app/aaps/core/nssdk/localmodel/devicestatus/NSDeviceStatus.kt` | DeviceStatus model |
| AAPS | `aaps:plugins/sync/src/main/kotlin/app/aaps/plugins/sync/nsclientV3/extensions/DeviceStatusExtension.kt` | Conversion logic |
| oref0 | `oref0:lib/determine-basal/determine-basal.js` | Algorithm output structure |

---

## Cross-References

- [Nightscout Data Model](./nightscout-data-model.md) - Collections overview
- [Loop Nightscout Sync](../../mapping/loop/nightscout-sync.md) - Loop sync details
- [Trio Nightscout Sync](../../mapping/trio/nightscout-sync.md) - Trio sync details  
- [AAPS Nightscout Sync](../../mapping/aaps/nightscout-sync.md) - AAPS sync details
- [AAPS Nightscout Models](../../mapping/aaps/nightscout-models.md) - AAPS SDK models
- [oref0 Algorithm](../../mapping/oref0/algorithm.md) - Algorithm output structure

---

## Revision History

| Date | Author | Changes |
|------|--------|---------|
| 2026-01-17 | Agent | Initial comprehensive deep dive synthesizing Loop, Trio, AAPS, and oref0 structures |
