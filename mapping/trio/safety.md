# Trio Safety Constraints

This document details Trio's safety mechanisms, including maximum limits, autosens bounds, and algorithm constraints.

## Source Files

| File | Purpose |
|------|---------|
| `trio:FreeAPS/Sources/Models/Preferences.swift` | Safety preferences |
| `trio:trio-oref/lib/determine-basal/determine-basal.js` | Algorithm limits |

---

## Maximum IOB

### Configuration

```swift
// trio:Preferences.swift#L4
var maxIOB: Decimal = 0  // Default: disabled (0)
```

**JSON key**: `max_iob`

### Algorithm Enforcement

In determine-basal.js, IOB is checked against max_iob:
- If IOB >= max_iob, no additional insulin is delivered
- SMBs are blocked when IOB approaches limit

---

## Maximum Basal Rate

### Configuration

Multiple safety multipliers limit basal rate:

```swift
// trio:Preferences.swift#L5-L6
var maxDailySafetyMultiplier: Decimal = 3    // max_daily_safety_multiplier
var currentBasalSafetyMultiplier: Decimal = 4  // current_basal_safety_multiplier
```

### Effective Max Basal Calculation

```javascript
// In determine-basal.js
max_basal = min(
    profile.max_basal,
    profile.max_daily_safety_multiplier * max_daily_basal,
    profile.current_basal_safety_multiplier * current_basal
)
```

---

## SMB Limits

### Maximum SMB Size

SMB size is limited by basal minutes:

```swift
// trio:Preferences.swift#L33-L34
var maxSMBBasalMinutes: Decimal = 30         // maxSMBBasalMinutes
var maxUAMSMBBasalMinutes: Decimal = 30      // maxUAMSMBBasalMinutes
```

### SMB Calculation

```javascript
// In determine-basal.js
maxBolus = profile.current_basal * profile.maxSMBBasalMinutes / 60;

// For UAM (higher risk)
if (enableUAM) {
    maxBolus = profile.current_basal * profile.maxUAMSMBBasalMinutes / 60;
}
```

### SMB Delivery Ratio

```swift
// trio:Preferences.swift#L9
var smbDeliveryRatio: Decimal = 0.5  // smb_delivery_ratio
```

Limits SMB to a fraction of the calculated insulin need.

### SMB Interval

```swift
// trio:Preferences.swift#L35
var smbInterval: Decimal = 3  // SMBInterval (minutes)
```

Minimum time between SMBs.

---

## Autosens Bounds

### Configuration

```swift
// trio:Preferences.swift#L7-L8
var autosensMax: Decimal = 1.2   // autosens_max (120%)
var autosensMin: Decimal = 0.7   // autosens_min (70%)
```

### Effect

Autosens ratio is clamped:
- **autosens_max = 1.2**: Sensitivity can be detected as high as 120% of normal
- **autosens_min = 0.7**: Sensitivity can be detected as low as 70% of normal

This prevents extreme adjustments based on noisy data.

---

## COB Limits

```swift
// trio:Preferences.swift#L18
var maxCOB: Decimal = 120  // maxCOB (grams)
```

Maximum carbs on board considered by the algorithm.

---

## Low Glucose Safety

### Suspend Threshold

The suspend threshold is managed through the profile's `min_bg` and preferences:

```swift
// trio:Preferences.swift#L55
var threshold_setting: Decimal = 65  // threshold_setting
```

When BG is predicted to go below threshold:
1. Suspend basal delivery
2. Block SMBs
3. Set zero temp basal

### Algorithm Protection

```javascript
// In determine-basal.js
if (minPredBG < profile.min_bg) {
    // Reduce or suspend insulin delivery
    reason += "minPredBG " + minPredBG + " < " + profile.min_bg;
}
```

---

## High Glucose Safety

### High BG SMB Enable

```swift
// trio:Preferences.swift#L53-L54
var enableSMB_high_bg: Bool = false
var enableSMB_high_bg_target: Decimal = 110  // enableSMB_high_bg_target
```

When enabled, SMBs can be delivered when BG is above this threshold, even without other SMB conditions met.

---

## Bolus Wizard Safety

```swift
// trio:Preferences.swift#L27
var a52RiskEnable: Bool = false  // A52_risk_enable
```

When `false`, SMBs are disabled for 6 hours after Bolus Wizard activity to prevent insulin stacking.

---

## Carb Impact Minimum

```swift
// trio:Preferences.swift#L22
var min5mCarbimpact: Decimal = 8  // min_5m_carbimpact (mg/dL per 5 min)
```

Minimum assumed carb impact used when absorption is slower than expected.

---

## Temp Target Safety

### High Temp Target

```swift
// trio:Preferences.swift#L11
var highTemptargetRaisesSensitivity: Bool = false
```

When high temp target is set:
- Sensitivity is increased (more conservative dosing)
- SMBs may be disabled (unless `allowSMB_with_high_temptarget`)

### Low Temp Target

```swift
// trio:Preferences.swift#L12
var lowTemptargetLowersSensitivity: Bool = false
```

When low temp target is set (e.g., for exercise):
- Sensitivity is decreased (more aggressive dosing)

---

## Exercise Mode

```swift
// trio:Preferences.swift#L16-L17
var exerciseMode: Bool = false
var halfBasalExerciseTarget: Decimal = 160  // half_basal_exercise_target
```

When enabled with temp target above `halfBasalExerciseTarget`:
- Basal is halved
- More conservative dosing

---

## Insulin Curves

```swift
// trio:Preferences.swift#L37-L39
var curve: InsulinCurve = .rapidActing
var useCustomPeakTime: Bool = false
var insulinPeakTime: Decimal = 75  // insulinPeakTime (minutes)
```

### Available Curves

```swift
// trio:Preferences.swift#L116-L122
enum InsulinCurve: String, JSON {
    case rapidActing = "rapid-acting"   // Peak ~75 min
    case ultraRapid = "ultra-rapid"     // Peak ~55 min
    case bilinear                       // Linear decay
}
```

---

## CGM Noise Handling

```swift
// trio:Preferences.swift#L41
var noisyCGMTargetMultiplier: Decimal = 1.3  // noisyCGMTargetMultiplier
```

When CGM noise is detected:
- Target is multiplied by this factor
- More conservative dosing

---

## Suspend Behavior

```swift
// trio:Preferences.swift#L42
var suspendZerosIOB: Bool = false  // suspend_zeros_iob
```

When enabled, IOB is zeroed during pump suspend (affects predictions).

---

## Override Safety

Overrides can modify safety parameters:

```swift
// trio:Oref2_variables.swift
var smbIsOff: Bool           // Disable SMBs during override
var smbIsScheduledOff: Bool  // SMB disabled for time window
var start: Decimal           // Schedule start hour
var end: Decimal             // Schedule end hour
```

### Scheduled SMB Disable

```javascript
// trio:trio-oref/lib/determine-basal/determine-basal.js#L48-L70
if (oref_variables.smbIsScheduledOff) {
    let currentHour = new Date(time.getHours());
    let startTime = oref_variables.start;
    let endTime = oref_variables.end;
    
    if (startTime < endTime && (currentHour >= startTime && currentHour < endTime)) {
        console.error("SMB disabled: current time is in SMB disabled scheduled");
        return false;
    }
}
```

---

## Dynamic ISF Limits

```swift
// trio:Preferences.swift#L44-L45
var maxDeltaBGthreshold: Decimal = 0.2  // maxDelta_bg_threshold
var adjustmentFactor: Decimal = 0.8     // adjustmentFactor
```

Limits how aggressively Dynamic ISF can adjust sensitivity based on glucose trends.

---

## Complete Preferences Reference

| Setting | Key | Default | Purpose |
|---------|-----|---------|---------|
| Max IOB | `max_iob` | 0 | Maximum insulin on board |
| Max Daily Safety Mult | `max_daily_safety_multiplier` | 3 | Max basal vs max daily |
| Current Basal Safety Mult | `current_basal_safety_multiplier` | 4 | Max basal vs current |
| Autosens Max | `autosens_max` | 1.2 | Max sensitivity ratio |
| Autosens Min | `autosens_min` | 0.7 | Min sensitivity ratio |
| SMB Delivery Ratio | `smb_delivery_ratio` | 0.5 | SMB fraction of need |
| Max SMB Basal Minutes | `maxSMBBasalMinutes` | 30 | SMB size limit |
| Max UAM SMB Minutes | `maxUAMSMBBasalMinutes` | 30 | UAM SMB size limit |
| SMB Interval | `SMBInterval` | 3 | Min minutes between SMBs |
| Max COB | `maxCOB` | 120 | Max carbs on board |
| Threshold | `threshold_setting` | 65 | Low glucose threshold |

---

## Revision History

| Date | Author | Changes |
|------|--------|---------|
| 2026-01-16 | Agent | Initial safety documentation from source analysis |
