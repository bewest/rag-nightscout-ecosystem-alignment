# oref0/openaps Documentation Inventory

**Repositories**: 
- [openaps/oref0](https://github.com/openaps/oref0) - Reference algorithm
- [openaps/openaps](https://github.com/openaps/openaps) - Toolkit and device interface

**Aliases**: `oref0`, `openaps`  
**Language**: JavaScript (Node.js), Python  
**Last Updated**: 2026-01-16

---

The OpenAPS project provides the reference dosing algorithms (oref0/oref1) used by AAPS, Trio, and other closed-loop systems. This is the "source of truth" for algorithm behavior.

---

## oref0 Repository Structure

### Core Algorithm

| File | Path | Description | Integration Priority |
|------|------|-------------|---------------------|
| determine-basal.js | `lib/determine-basal/determine-basal.js` | **THE** core algorithm (61KB) | **Critical** |
| autosens.js | `lib/determine-basal/autosens.js` | Autosensitivity calculation | **Critical** |
| cob.js | `lib/determine-basal/cob.js` | Carbs on board calculation | **Critical** |

### Supporting Libraries

| Directory | Path | Description |
|-----------|------|-------------|
| iob | `lib/iob/` | Insulin on board calculations |
| meal | `lib/meal/` | Meal detection and absorption |
| profile | `lib/profile/` | Profile handling |
| autotune | `lib/autotune/` | Autotune algorithm |
| autotune-prep | `lib/autotune-prep/` | Autotune data preparation |

### Command-Line Tools

| Tool | Path | Purpose |
|------|------|---------|
| oref0-determine-basal.js | `bin/` | Run algorithm standalone |
| oref0-calculate-iob.js | `bin/` | Calculate IOB |
| oref0-detect-sensitivity.js | `bin/` | Run autosens |
| oref0-meal.js | `bin/` | Meal calculations |
| oref0-autotune.py | `bin/` | Run autotune |
| oref0-get-profile.js | `bin/` | Generate profile |

---

## Algorithm Inputs

### Profile Object

```javascript
{
  "max_iob": 0,                    // Maximum IOB for algorithm
  "max_daily_safety_multiplier": 3,
  "current_basal_safety_multiplier": 4,
  "autosens_max": 1.2,
  "autosens_min": 0.7,
  "autosens_adjust_targets": true,
  "override_high_target_with_low": false,
  "skip_neutral_temps": false,
  "bolussnooze_dia_divisor": 2,
  "min_5m_carbimpact": 8,          // mg/dL/5min
  "carbratio_adjustmentratio": 1,
  "dia": 6,                         // Duration of insulin action
  "model": {},                      // Insulin curve model
  "current_basal": 0.8,
  "max_daily_basal": 1.2,
  "max_basal": 3.5,
  "min_bg": 100,
  "max_bg": 120,
  "target_bg": 110,
  "sens": 50,                       // ISF
  "carb_ratio": 10                  // CR
}
```

### Glucose History

```javascript
[
  { "glucose": 120, "date": 1234567890000, "dateString": "2024-01-15T10:00:00Z" },
  { "glucose": 125, "date": 1234567590000, "dateString": "2024-01-15T09:55:00Z" }
]
```

### IOB Data

```javascript
{
  "iob": 1.5,
  "basaliob": 0.8,
  "bolussnooze": 0.2,
  "activity": 0.01,
  "lastBolusTime": 1234567890000,
  "lastTemp": { "rate": 1.0, "timestamp": "..." }
}
```

### Meal Data

```javascript
{
  "carbs": 30,
  "mealCOB": 20,
  "slopeFromMaxDeviation": 0,
  "slopeFromMinDeviation": 0,
  "lastCarbTime": 1234567890000
}
```

---

## Algorithm Outputs

### Basal Recommendation

```javascript
{
  "temp": "absolute",
  "bg": 120,
  "tick": "+5",
  "eventualBG": 150,
  "snoozeBG": 140,
  "predBGs": {
    "IOB": [120, 125, 130, 135, 140, 145, 150],
    "COB": [120, 125, 128, 130, 132, 134, 135],
    "UAM": [120, 125, 130, 135, 140, 145, 150]
  },
  "sensitivityRatio": 1.0,
  "COB": 20,
  "IOB": 1.5,
  "reason": "Eventual BG 150 > 120, setting temp basal",
  "rate": 1.5,
  "duration": 30,
  "deliverAt": "2024-01-15T10:05:00Z"
}
```

### SMB Recommendation (oref1)

```javascript
{
  "units": 0.5,
  "reason": "BG 150, inserting 0.5U SMB",
  "microBolusAllowed": true,
  "SMBbgOffset": 30
}
```

---

## Key Algorithm Concepts

### Prediction Types

| Prediction | Description |
|------------|-------------|
| IOB | Glucose prediction based on insulin only |
| COB | Glucose prediction including announced carbs |
| UAM | Unannounced Meal - predicts based on observed glucose rise |
| ZT | Zero Temp - prediction if insulin was stopped |

### Safety Limits

| Parameter | Purpose |
|-----------|---------|
| `max_iob` | Maximum total IOB allowed |
| `max_basal` | Maximum temp basal rate |
| `max_daily_basal` | Maximum scheduled basal |
| `autosens_max` / `autosens_min` | Autosens bounds |
| `min_5m_carbimpact` | Minimum carb absorption rate |

### Autosens

Calculates dynamic sensitivity ratio based on:
- Observed vs expected glucose changes
- Deviation from predicted values
- Historical patterns

Output: `sensitivityRatio` (0.7 - 1.2 typical range)

---

## openaps Repository Structure

The `openaps` repository is the toolkit for building OpenAPS rigs:

| Component | Description |
|-----------|-------------|
| Device drivers | Medtronic pump, Dexcom CGM |
| Report generation | Data collection and formatting |
| Loop orchestration | Cron-based control loop |
| Vendor plugins | Extensible device support |

---

## Integration with Other Systems

### AAPS Integration

AAPS embeds `determine-basal.js` and calls via JavaScript bridge:
- `DetermineBasalAdapterSMBJS.kt` loads the JS
- Kotlin objects serialized to JSON inputs
- JS output parsed back to Kotlin

### Trio Integration

Trio similarly embeds the algorithm:
- `JavaScriptWorker.swift` executes the JS
- Swift models converted to algorithm inputs
- `Suggestion` model captures output

### Loop Comparison

Loop does NOT use oref0. It has its own algorithm in:
- `LoopCore/LoopMath.swift` - Prediction
- `LoopCore/DoseRecommendation.swift` - Dosing

This creates semantic differences in:
- Prediction methodology
- Safety constraint handling
- Autosens implementation

---

## Terminology Mapping

| oref0 Term | Nightscout | Loop | AAPS |
|------------|------------|------|------|
| `profile` | `profile` store | `TherapySettings` | `Profile` |
| `iob.iob` | - | `insulinOnBoard` | `iobTotal.iob` |
| `mealCOB` | - | `carbsOnBoard` | `mealData.mealCOB` |
| `rate` (temp) | `treatments.rate` | `tempBasal.value` | `temporaryBasal.rate` |
| `units` (SMB) | `treatments.insulin` | N/A (no SMB) | `bolus.amount` |
| `sensitivityRatio` | - | `insulinSensitivity` | `autosensData.ratio` |

---

## Alignment Implications

1. **Algorithm Source**: oref0 is the reference - AAPS and Trio should produce identical outputs given identical inputs
2. **Loop Divergence**: Loop's different algorithm means semantic alignment, not algorithmic alignment
3. **Profile Format**: oref0's profile format is embedded in AAPS/Trio but differs from Nightscout's profile structure
4. **Prediction Format**: `predBGs` structure is oref0-specific, need to map to other systems
