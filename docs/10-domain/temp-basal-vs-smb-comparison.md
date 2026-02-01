# Temp Basal vs SMB Dosing Comparison

> **Status**: Complete  
> **Last Updated**: 2026-01-30  
> **Task**: Compare temp basal adjustments vs SMB micro-dosing

## Executive Summary

Loop and oref0/AAPS use fundamentally different approaches to automatic insulin dosing:

| Aspect | Loop | oref0/AAPS |
|--------|------|------------|
| **Primary mechanism** | Temp basal adjustments | SMB (Super Micro Bolus) |
| **Delivery speed** | Slow (basal rate change) | Fast (immediate bolus) |
| **Dosing frequency** | Every 5 min (temp update) | Every 3 min (SMB default) |
| **Correction approach** | Rate above/below scheduled | Micro-bolus + low temp |
| **Max single dose** | N/A (rate-based) | maxSMBBasalMinutes worth |

## Loop Dosing Architecture

### Source Files
- `externals/LoopWorkspace/LoopKit/LoopKit/LoopAlgorithm/DoseMath.swift:40-576`

### Temp Basal Only Mode

Loop historically uses **temp basal adjustments only** for automatic dosing:

```swift
// DoseMath.swift:42-64
fileprivate func asTempBasal(
    scheduledBasalRate: Double,
    maxBasalRate: Double,
    duration: TimeInterval,
    rateRounder: ((Double) -> Double)?
) -> TempBasalRecommendation {
    var rate = units / (duration / TimeInterval(hours: 1))  // units/hour
    switch self {
    case .aboveRange, .inRange, .entirelyBelowRange:
        rate += scheduledBasalRate
    case .suspend:
        break
    }
    rate = Swift.min(maxBasalRate, Swift.max(0, rate))
    return TempBasalRecommendation(unitsPerHour: rate, duration: duration)
}
```

### Automatic Dose Recommendation (Hybrid)

Loop now supports **automatic boluses** via `recommendedAutomaticDose()`:

```swift
// DoseMath.swift:464-525
public func recommendedAutomaticDose(
    to correctionRange: GlucoseRangeSchedule,
    maxAutomaticBolus: Double,
    partialApplicationFactor: Double,
    ...
) -> AutomaticDoseRecommendation? {
    // Calculate temp basal
    var temp: TempBasalRecommendation? = correction.asTempBasal(...)
    
    // Calculate automatic bolus (partial application)
    let bolusUnits = correction.asPartialBolus(
        partialApplicationFactor: partialApplicationFactor,
        maxBolusUnits: maxAutomaticBolus,
        volumeRounder: volumeRounder
    )
    
    return AutomaticDoseRecommendation(basalAdjustment: temp, bolusUnits: bolusUnits)
}
```

### Partial Application Factor

Loop's automatic boluses use a **partial application factor** (typically 40%):

```swift
// DoseMath.swift:114-123
fileprivate func asPartialBolus(
    partialApplicationFactor: Double,
    maxBolusUnits: Double,
    volumeRounder: ((Double) -> Double)?
) -> Double {
    let partialDose = units * partialApplicationFactor
    return Swift.min(Swift.max(0, volumeRounder?(partialDose) ?? partialDose), maxBolusUnits)
}
```

### Key Differences from SMB
- Loop uses `partialApplicationFactor` (fraction of needed insulin)
- oref0 SMB uses `insulinReq/2` (always half)
- Loop auto-bolus is newer, SMB is established

## oref0/AAPS SMB Architecture

### Source Files
- `externals/oref0/lib/determine-basal/determine-basal.js:53-160, 1070-1160`
- `externals/AndroidAPS/core/keys/src/main/kotlin/app/aaps/core/keys/BooleanKey.kt:50-54`

### SMB Enable Conditions

SMB requires meeting one of several conditions (determine-basal.js:59-124):

```javascript
// SMB enable conditions
if (profile.enableSMB_always === true) {
    enableSMB = true;
}
if (profile.enableSMB_with_COB === true && meal_data.mealCOB) {
    enableSMB = true;
}
if (profile.enableSMB_after_carbs === true && meal_data.carbs) {
    enableSMB = true;  // 6h after carb entry
}
if (profile.enableSMB_with_temptarget === true && target_bg < 100) {
    enableSMB = true;  // Low temp target
}
if (profile.enableSMB_high_bg === true && bg >= high_bg) {
    enableSMB = true;  // High BG detected
}
```

### AAPS SMB Settings

```kotlin
// BooleanKey.kt:50-54
ApsUseSmbWithHighTt("enableSMB_with_high_temptarget", false),
ApsUseSmbAlways("enableSMB_always", true),      // Changed from default false
ApsUseSmbWithCob("enableSMB_with_COB", true),   // Changed from default false
ApsUseSmbWithLowTt("enableSMB_with_temptarget", true),
ApsUseSmbAfterCarbs("enableSMB_after_carbs", true),
```

### SMB Calculation (determine-basal.js:1076-1160)

```javascript
if (microBolusAllowed && enableSMB && bg > threshold) {
    // Calculate max bolus from maxSMBBasalMinutes
    var mealInsulinReq = round(meal_data.mealCOB / profile.carb_ratio, 3);
    
    if (iob_data.iob > mealInsulinReq) {
        // IOB > COB: use maxUAMSMBBasalMinutes (default 30)
        maxBolus = round(profile.current_basal * profile.maxUAMSMBBasalMinutes / 60, 1);
    } else {
        // Use maxSMBBasalMinutes (default 30)
        maxBolus = round(profile.current_basal * profile.maxSMBBasalMinutes / 60, 1);
    }
    
    // Bolus 1/2 the insulinReq, up to maxBolus
    var microBolus = Math.floor(Math.min(insulinReq/2, maxBolus) * roundSMBTo) / roundSMBTo;
    
    // Set accompanying zero/low temp
    var smbLowTempReq = round(basal * durationReq/30, 2);
    
    if (lastBolusAge > SMBInterval) {  // Default 3 min
        rT.units = microBolus;
        rT.reason += "Microbolusing " + microBolus + "U. ";
    }
}
```

### SMB Safety Limits

| Parameter | Default | Description |
|-----------|---------|-------------|
| `maxSMBBasalMinutes` | 30 | Max SMB = basal × minutes / 60 |
| `maxUAMSMBBasalMinutes` | 30 | UAM SMB limit when IOB > COB |
| `SMBInterval` | 3 min | Minimum time between SMBs |
| `bolus_increment` | 0.1 U | Rounding increment |

### SMB + Zero Temp Pattern

oref0 pairs SMB with a low/zero temp basal for safety:

```javascript
// Calculate zero temp duration
worstCaseInsulinReq = (smbTarget - (naive_eventualBG + minIOBPredBG)/2) / sens;
durationReq = round(60 * worstCaseInsulinReq / profile.current_basal);

// Set low temp alongside SMB
rT.rate = smbLowTempReq;
rT.duration = durationReq;
```

## Comparison Matrix

| Feature | Loop Temp Basal | Loop Auto Bolus | oref0 SMB |
|---------|-----------------|-----------------|-----------|
| **Delivery method** | Rate change | Small bolus | Micro bolus |
| **Fraction of need** | N/A | partialApplicationFactor (40%) | 50% (insulinReq/2) |
| **Max limit** | maxBasalRate | maxAutomaticBolus | maxSMBBasalMinutes × basal |
| **Frequency** | Every 5 min | Every 5 min | Every 3 min |
| **Safety net** | Low temp | Low temp | Zero temp paired |
| **Enable conditions** | Always | User setting | Multiple conditions |

## Dosing Speed Comparison

### Loop Temp Basal (Traditional)
- **Time to deliver 0.5U extra**: ~30 minutes (at 1 U/hr above basal)
- **Precision**: Limited by basal rate resolution
- **Safety**: Slow delivery is inherently safer

### oref0 SMB
- **Time to deliver 0.5U extra**: ~3 minutes (immediate bolus)
- **Precision**: Bolus increment (typically 0.05-0.1U)
- **Safety**: Zero temp provides safety net

### Loop Auto Bolus (Hybrid)
- **Time to deliver 0.5U extra**: ~5 minutes (next loop cycle)
- **Precision**: Bolus increment
- **Safety**: Partial application limits each dose

## Example Scenarios

### Scenario: BG Rising, Need 1U Correction

**Loop Temp Basal Only:**
- Set temp of scheduled + 2 U/hr
- Over 30 min, delivers 1U extra
- Slow but steady correction

**oref0 SMB:**
- Calculate insulinReq = 1U
- Microbolus = min(0.5U, maxBolus)
- Immediate 0.5U delivery
- Set 30-60 min zero temp
- Repeat in 3 min if still needed

**Loop Auto Bolus:**
- Calculate correction = 1U
- Partial = 1U × 0.4 = 0.4U
- Deliver 0.4U now
- Set low temp
- Repeat in 5 min

## Gaps Identified

### GAP-DOSE-001: SMB Not Available in Loop

**Description**: Loop does not have equivalent to oref0 SMB with 3-minute frequency and 50% dosing.

**Affected Systems**: Loop vs oref0/AAPS/Trio

**Evidence**:
- oref0: `determine-basal.js:1100` - `microBolus = Math.min(insulinReq/2, maxBolus)`
- Loop: Uses `partialApplicationFactor` with 5-min cycles

**Impact**: Faster meal response possible with SMB.

**Remediation**: Loop Auto Bolus provides similar capability; document differences.

### GAP-DOSE-002: Different Safety Mechanisms

**Description**: SMB pairs with zero temp; Loop uses IOB limits and partial application.

**Affected Systems**: Loop vs oref0/AAPS

**Evidence**:
- oref0: `determine-basal.js:1120` - `smbLowTempReq` calculation
- Loop: `DoseMath.swift:425-428` - `additionalActiveInsulinClamp`

**Impact**: Different fallback behavior if pump disconnects.

**Remediation**: Document safety models for each system.

### GAP-DOSE-003: Enable Conditions Mismatch

**Description**: oref0 has multiple SMB enable conditions; Loop auto bolus is simpler on/off.

**Affected Systems**: Loop vs oref0/AAPS

**Evidence**:
- oref0: 6 enable conditions (`enableSMB_always`, `_with_COB`, etc.)
- Loop: Single `automaticBolusEnabled` setting

**Impact**: Different behavior in different contexts.

**Remediation**: Document condition differences.

### GAP-DOSE-004: Dosing Frequency Difference

**Description**: SMB can run every 3 min; Loop cycles every 5 min.

**Affected Systems**: Loop vs oref0/AAPS

**Evidence**:
- oref0: `determine-basal.js:1133-1136` - `SMBInterval = 3`
- Loop: 5-minute loop cycle

**Impact**: Faster response possible with SMB.

**Remediation**: Design difference - document for users.

## Requirements

### REQ-DOSE-001: Dosing Mechanism Documentation

**Statement**: AID systems MUST document their primary automatic dosing mechanism.

**Rationale**: Users need to understand how insulin is delivered automatically.

**Verification**: Documentation review.

### REQ-DOSE-002: Safety Net Documentation

**Statement**: Systems using automatic boluses MUST document safety mechanisms.

**Rationale**: Users need to understand fallback behavior if issues occur.

**Verification**: Safety documentation audit.

### REQ-DOSE-003: Enable Condition Transparency

**Statement**: Systems with conditional SMB/auto-bolus SHOULD clearly display active conditions.

**Rationale**: Users need to know when automatic boluses are enabled.

**Verification**: UI review for condition display.

## References

- [OpenAPS SMB Documentation](https://openaps.readthedocs.io/en/latest/docs/Customize-Iterate/oref1.html)
- [LoopDocs Automatic Bolus](https://loopkit.github.io/loopdocs/operation/features/dosing/)
- [AndroidAPS SMB Overview](https://androidaps.readthedocs.io/en/latest/Usage/SMBs.html)

---

## Conformance Assertions

The following conformance assertions cover dosing mechanism documentation requirements:

| Assertion File | Requirements | Assertions |
|----------------|--------------|------------|
| `conformance/assertions/algorithm-docs.yaml` | REQ-DOSE-001, REQ-DOSE-002, REQ-DOSE-003 | 7 |

**Key Assertions**:
- `doc-dose-001`: Loop temp basal dosing documentation
- `doc-dose-002`: AAPS SMB dosing documentation
- `doc-dose-004`: Loop zero temp basal safety net
- `doc-dose-005`: AAPS SMB IOB limit documentation

See `traceability/domain-matrices/aid-algorithms-matrix.md` for full coverage matrix.
