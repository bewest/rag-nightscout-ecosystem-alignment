# CGM Trend Arrow Standardization

**Date:** 2026-01-29  
**Status:** Complete  
**Type:** Cross-project mapping

## Overview

CGM systems display trend arrows to indicate the rate of glucose change. Each project in the ecosystem uses different representations, enums, and thresholds. This document maps all 7 major projects to a unified standard.

## Unified Trend Arrow Enum

Based on Dexcom's standard (used by Nightscout), the canonical trend arrow values are:

| ID | Name | Symbol | Description | Rate (mg/dL/min) |
|----|------|--------|-------------|------------------|
| 1 | DoubleUp | ⇈ | Rising very rapidly | > +3.5 |
| 2 | SingleUp | ↑ | Rising rapidly | +2 to +3.5 |
| 3 | FortyFiveUp | ↗ | Rising | +1 to +2 |
| 4 | Flat | → | Stable | -1 to +1 |
| 5 | FortyFiveDown | ↘ | Falling | -1 to -2 |
| 6 | SingleDown | ↓ | Falling rapidly | -2 to -3.5 |
| 7 | DoubleDown | ⇊ | Falling very rapidly | < -3.5 |
| 8 | NotComputable | - | Cannot calculate | N/A |
| 9 | RateOutOfRange | - | Rate exceeds limits | N/A |
| 0 | None | - | Unknown/missing | N/A |

## Project Mapping Matrix

### Nightscout (cgm-remote-monitor)

**Source:** `lib/server/pebble.js:8-19`

```javascript
var DIRECTIONS = {
  NONE: 0,
  DoubleUp: 1,
  SingleUp: 2,
  FortyFiveUp: 3,
  Flat: 4,
  FortyFiveDown: 5,
  SingleDown: 6,
  DoubleDown: 7,
  'NOT COMPUTABLE': 8,
  'RATE OUT OF RANGE': 9
};
```

**Status:** ✅ Canonical - All other projects map to this

---

### xDrip+ (Android)

**Source:** `app/src/main/java/com/eveningoutpost/dexdrip/importedlibraries/dexcom/Dex_Constants.java:86-96`

```java
public enum TREND_ARROW_VALUES {
    NONE(0),
    DOUBLE_UP(1, "⇈", "DoubleUp", 40d),      // > 40 mg/dL in 15 min
    SINGLE_UP(2, "↑", "SingleUp", 3.5d),
    UP_45(3, "↗", "FortyFiveUp", 2d),
    FLAT(4, "→", "Flat", 1d),
    DOWN_45(5, "↘", "FortyFiveDown", -1d),
    SINGLE_DOWN(6, "↓", "SingleDown", -2d),
    DOUBLE_DOWN(7, "⇊", "DoubleDown", -3.5d),
    NOT_COMPUTABLE(8, "", "NotComputable"),
    OUT_OF_RANGE(9, "", "RateOutOfRange")
}
```

**Mapping:** ✅ Direct 1:1 with Nightscout

| xDrip+ | Nightscout | Notes |
|--------|------------|-------|
| DOUBLE_UP | DoubleUp | Threshold: 40 mg/dL/15min |
| SINGLE_UP | SingleUp | Threshold: 3.5 mg/dL/min |
| UP_45 | FortyFiveUp | Threshold: 2 mg/dL/min |
| FLAT | Flat | Threshold: 1 mg/dL/min |
| DOWN_45 | FortyFiveDown | |
| SINGLE_DOWN | SingleDown | |
| DOUBLE_DOWN | DoubleDown | |
| NOT_COMPUTABLE | NOT COMPUTABLE | |
| OUT_OF_RANGE | RATE OUT OF RANGE | |

---

### xDrip4iOS (xdripswift)

**Source:** `xdrip/Core Data/classes/BgReading+CoreDataClass.swift:64-81`

Uses slope-based calculation, returns Unicode symbols directly:

```swift
func slopeArrow() -> String {
    let slope_by_minute = calculatedValueSlope * 60000
    if (slope_by_minute <= (-3.5)) { return "↓↓" }      // DoubleDown
    else if (slope_by_minute <= (-2)) { return "↓" }    // SingleDown
    else if (slope_by_minute <= (-1)) { return "↘" }    // FortyFiveDown
    else if (slope_by_minute <= (1)) { return "→" }     // Flat
    else if (slope_by_minute <= (2)) { return "↗" }     // FortyFiveUp
    else if (slope_by_minute <= (3.5)) { return "↑" }   // SingleUp
    else { return "↑↑" }                                 // DoubleUp
}
```

**Ordinal mapping:** `slopeOrdinal()` at line 83-100 returns values 1-7.

**Mapping:** ✅ Compatible thresholds with Nightscout

| xdripswift Symbol | Ordinal | Nightscout |
|-------------------|---------|------------|
| ↑↑ | 1 | DoubleUp |
| ↑ | 2 | SingleUp |
| ↗ | 3 | FortyFiveUp |
| → | 4 | Flat |
| ↘ | 5 | FortyFiveDown |
| ↓ | 6 | SingleDown |
| ↓↓ | 7 | DoubleDown |

---

### Loop (LoopKit)

**Source:** `LoopKit/LoopKit/GlucoseKit/GlucoseTrend.swift:12-37`

```swift
public enum GlucoseTrend: Int, CaseIterable {
    case upUpUp       = 1   // ⇈
    case upUp         = 2   // ↑
    case up           = 3   // ↗︎
    case flat         = 4   // →
    case down         = 5   // ↘︎
    case downDown     = 6   // ↓
    case downDownDown = 7   // ⇊
}
```

**Mapping:** ✅ Direct 1:1 with Nightscout

| Loop | Nightscout | Symbol |
|------|------------|--------|
| upUpUp (1) | DoubleUp | ⇈ |
| upUp (2) | SingleUp | ↑ |
| up (3) | FortyFiveUp | ↗ |
| flat (4) | Flat | → |
| down (5) | FortyFiveDown | ↘ |
| downDown (6) | SingleDown | ↓ |
| downDownDown (7) | DoubleDown | ⇊ |

**Note:** Loop uses LoopKit which stores in Nightscout via NightscoutServiceKit.

---

### AAPS (AndroidAPS)

**Source:** `core/data/src/main/kotlin/app/aaps/core/data/model/TrendArrow.kt:3-14`

```kotlin
enum class TrendArrow(val text: String, val symbol: String) {
    NONE("NONE", "??"),
    TRIPLE_UP("TripleUp", "X"),
    DOUBLE_UP("DoubleUp", "⇈"),
    SINGLE_UP("SingleUp", "↑"),
    FORTY_FIVE_UP("FortyFiveUp", "↗"),
    FLAT("Flat", "→"),
    FORTY_FIVE_DOWN("FortyFiveDown", "↘"),
    SINGLE_DOWN("SingleDown", "↓"),
    DOUBLE_DOWN("DoubleDown", "⇊"),
    TRIPLE_DOWN("TripleDown", "X")
}
```

**Mapping:** ⚠️ AAPS has TRIPLE_UP and TRIPLE_DOWN not in Nightscout standard

| AAPS | Nightscout | Notes |
|------|------------|-------|
| NONE | NONE | |
| TRIPLE_UP | ❌ Not mapped | Displayed as "X" |
| DOUBLE_UP | DoubleUp | |
| SINGLE_UP | SingleUp | |
| FORTY_FIVE_UP | FortyFiveUp | |
| FLAT | Flat | |
| FORTY_FIVE_DOWN | FortyFiveDown | |
| SINGLE_DOWN | SingleDown | |
| DOUBLE_DOWN | DoubleDown | |
| TRIPLE_DOWN | ❌ Not mapped | Displayed as "X" |

**GAP:** AAPS supports TRIPLE_UP/TRIPLE_DOWN but Nightscout does not persist these.

---

### Trio

**Source:** `LoopKit/LoopKit/GlucoseKit/GlucoseTrend.swift:12` (same as Loop)

Trio inherits LoopKit and uses identical `GlucoseTrend` enum.

**Mapping:** ✅ Direct 1:1 with Nightscout (same as Loop)

---

### DiaBLE

**Source:** `DiaBLE/App.swift:94-112`

```swift
enum TrendArrow: Int, CustomStringConvertible, CaseIterable, Codable {
    case unknown        = -1
    case notDetermined  = 0
    case fallingQuickly = 1
    case falling        = 2
    case stable         = 3
    case rising         = 4
    case risingQuickly  = 5
}
```

**Mapping:** ⚠️ DiaBLE uses Libre convention (6 values vs Dexcom's 9)

| DiaBLE | Nightscout | Notes |
|--------|------------|-------|
| unknown (-1) | NONE | |
| notDetermined (0) | NOT COMPUTABLE | |
| fallingQuickly (1) | DoubleDown | Libre: falling > 2 mg/dL/min |
| falling (2) | SingleDown or FortyFiveDown | Libre: falling 1-2 mg/dL/min |
| stable (3) | Flat | Libre: -1 to +1 mg/dL/min |
| rising (4) | SingleUp or FortyFiveUp | Libre: rising 1-2 mg/dL/min |
| risingQuickly (5) | DoubleUp | Libre: rising > 2 mg/dL/min |

**GAP:** Libre sensors provide fewer trend arrow levels than Dexcom.

---

## Threshold Comparison

| Rate (mg/dL/min) | Dexcom/xDrip+ | Libre/DiaBLE | Nightscout |
|------------------|---------------|--------------|------------|
| > +3.5 | DoubleUp | risingQuickly | DoubleUp |
| +2 to +3.5 | SingleUp | rising | SingleUp |
| +1 to +2 | FortyFiveUp | rising | FortyFiveUp |
| -1 to +1 | Flat | stable | Flat |
| -1 to -2 | FortyFiveDown | falling | FortyFiveDown |
| -2 to -3.5 | SingleDown | falling | SingleDown |
| < -3.5 | DoubleDown | fallingQuickly | DoubleDown |

---

## Gaps Identified

### GAP-CGM-033: AAPS Triple Arrow Support

**Description:** AAPS supports TRIPLE_UP and TRIPLE_DOWN trend arrows, but Nightscout has no equivalent. These are displayed as "X" in AAPS.

**Impact:** Extreme rate of change data may be lost when syncing to Nightscout.

**Remediation:** Consider adding optional TRIPLE_UP (0) and TRIPLE_DOWN (10) to Nightscout DIRECTIONS.

### GAP-CGM-034: Libre Trend Arrow Granularity

**Description:** Libre sensors provide only 6 trend levels vs Dexcom's 9. DiaBLE uses Libre's native enum, which doesn't distinguish between SingleUp/FortyFiveUp or SingleDown/FortyFiveDown.

**Impact:** Trend precision is reduced when using Libre sensors through DiaBLE.

**Remediation:** When syncing Libre data to Nightscout, map `rising` to `FortyFiveUp` and `falling` to `FortyFiveDown` for conservative display.

---

## Recommendations

### For Nightscout Clients

1. **Parse by string name, not ID** - Some systems (AAPS) send text like "DoubleUp", others send numeric IDs
2. **Handle unknown values gracefully** - Display "?" or hide arrow rather than crash
3. **Store original sensor value** - Keep raw trend data for audit purposes

### For CGM Data Sources

1. **Map to Nightscout DIRECTIONS** - Use the canonical string names
2. **Include slope value** - Store `delta` field with actual mg/dL/min for precision
3. **Document thresholds** - Different sensors use different mg/dL/min cutoffs

### For Display Applications

1. **Use Unicode symbols consistently** - See symbol column in unified enum
2. **Support both ID and string lookup** - Handle legacy and modern data
3. **Apply colorization** - Red for down arrows, green/blue for up arrows

---

## Source File References

| Project | File | Line |
|---------|------|------|
| Nightscout | `lib/server/pebble.js` | 8-19 |
| xDrip+ | `importedlibraries/dexcom/Dex_Constants.java` | 86-96 |
| xdripswift | `Core Data/classes/BgReading+CoreDataClass.swift` | 64-81 |
| Loop | `LoopKit/GlucoseKit/GlucoseTrend.swift` | 12-37 |
| AAPS | `core/data/src/main/kotlin/.../TrendArrow.kt` | 3-14 |
| Trio | `LoopKit/GlucoseKit/GlucoseTrend.swift` | 12 |
| DiaBLE | `DiaBLE/App.swift` | 94-112 |

---

## Related Documents

- `mapping/cross-project/terminology-matrix.md` - Term definitions
- `traceability/cgm-sources-gaps.md` - CGM-related gaps
- `specs/openapi/aid-entries-2025.yaml` - Entries schema with direction field
