# Nightscout devicestatus Schema Audit

**Date:** 2026-01-29  
**Status:** Complete  
**Type:** Cross-controller analysis

## Overview

The Nightscout `devicestatus` collection stores real-time status information from AID controllers. This document audits the schema differences between Loop (`status.loop`) and oref0-based systems (`status.openaps`) used by AAPS and Trio.

## Schema Comparison

### Top-Level Structure

| Field | Loop | oref0/AAPS | Description |
|-------|------|------------|-------------|
| `device` | `loop://{device_name}` | `openaps://{device_name}` | Controller identifier |
| `created_at` | ISO timestamp | ISO timestamp | Record creation time |
| `date` | Epoch ms | Epoch ms | Timestamp |
| `uploaderBattery` | Integer | Integer | Phone battery % |
| `pump` | ✅ | ✅ | Pump status object |
| `uploader` | ✅ | ✅ | Uploader status |
| **`loop`** | ✅ | ❌ | Loop-specific status |
| **`openaps`** | ❌ | ✅ | oref0-specific status |
| `override` | ✅ | ❌ | Loop override status |
| `configuration` | ❌ | ✅ | AAPS configuration |

---

## Loop Status Structure (`status.loop`)

**Source:** `externals/LoopWorkspace/NightscoutService/NightscoutServiceKit/Extensions/StoredDosingDecision.swift:145-161`

```swift
DeviceStatus(
    device: "loop://\(UIDevice.current.name)",
    timestamp: date,
    pumpStatus: pumpStatus,
    uploaderStatus: uploaderStatus,
    loopStatus: LoopStatus(
        name: Bundle.main.bundleDisplayName,
        version: Bundle.main.fullVersionString,
        timestamp: date,
        iob: loopStatusIOB,
        cob: loopStatusCOB,
        predicted: loopStatusPredicted,          // Single prediction array
        automaticDoseRecommendation: ...,
        recommendedBolus: ...,
        enacted: ...,
        failureReason: ...
    ),
    overrideStatus: overrideStatus
)
```

### Loop Prediction Structure

```json
{
  "loop": {
    "predicted": {
      "startDate": "2026-01-29T12:00:00Z",
      "values": [120, 118, 115, 112, 110, ...]  // Single combined array
    },
    "enacted": {
      "timestamp": "2026-01-29T12:00:00Z",
      "rate": 0.5,
      "duration": 30,
      "received": true
    },
    "iob": {
      "iob": 2.5,
      "timestamp": "2026-01-29T12:00:00Z"
    },
    "cob": {
      "cob": 25,
      "timestamp": "2026-01-29T12:00:00Z"
    }
  }
}
```

### Key Characteristics
- **Single prediction curve** - Combined algorithm output
- **No separate curves** - IOB/COB/UAM not split
- **Override support** - `status.override` field

---

## oref0/AAPS Status Structure (`status.openaps`)

**Source:** `externals/AndroidAPS/core/nssdk/src/main/kotlin/app/aaps/core/nssdk/localmodel/devicestatus/NSDeviceStatus.kt:54-58`

```kotlin
@Serializable data class OpenAps(
    @SerializedName("suggested") val suggested: JSONObject?,  // Suggested action
    @SerializedName("enacted") val enacted: JSONObject?,      // Enacted action
    @SerializedName("iob") val iob: JSONObject?               // IOB data
)
```

### oref0 Prediction Structure

**Source:** `externals/cgm-remote-monitor/lib/report_plugins/daytoday.js:349-357`

```json
{
  "openaps": {
    "suggested": {
      "timestamp": "2026-01-29T12:00:00Z",
      "bg": 120,
      "reason": "COB: 25g, Dev: 15, BGI: -2.5, ...",
      "predBGs": {
        "IOB": [120, 115, 110, 105, ...],     // IOB-only prediction
        "COB": [120, 118, 116, 114, ...],     // With carb absorption
        "UAM": [120, 122, 124, 120, ...],     // Unannounced meal
        "ZT": [120, 110, 100, 90, ...]        // Zero-temp prediction
      },
      "COB": 25,
      "IOB": 2.5,
      "eventualBG": 95,
      "sensitivityRatio": 1.0,
      "mealAssist": "..."
    },
    "enacted": {
      "timestamp": "2026-01-29T12:00:00Z",
      "rate": 0.5,
      "duration": 30,
      "received": true,
      "predBGs": { ... }
    },
    "iob": {
      "iob": 2.5,
      "basaliob": 1.0,
      "bolusiob": 1.5,
      "timestamp": "2026-01-29T12:00:00Z"
    }
  }
}
```

### Key Characteristics
- **Four prediction curves** - IOB, COB, UAM, ZT (zero-temp)
- **Detailed reasoning** - `reason` field explains decisions
- **eventualBG** - Target endpoint prediction
- **sensitivityRatio** - Autosens factor

---

## Prediction Array Comparison

| Aspect | Loop | oref0/AAPS |
|--------|------|------------|
| **Number of curves** | 1 | 4 (IOB, COB, UAM, ZT) |
| **Array location** | `loop.predicted.values` | `openaps.suggested.predBGs.*` |
| **Start date** | `loop.predicted.startDate` | `openaps.suggested.timestamp` |
| **Interval** | 5 min | 5 min |
| **Units** | mg/dL | mg/dL |
| **Curve selection** | Algorithm internal | Displayed individually |

### Nightscout Display Logic

**Source:** `externals/cgm-remote-monitor/lib/report_plugins/daytoday.js:347-357`

```javascript
if (data.devicestatus[i].loop && data.devicestatus[i].loop.predicted) {
    predictions.push(data.devicestatus[i].loop.predicted);
} else if (data.devicestatus[i].openaps && 
           data.devicestatus[i].openaps.suggested && 
           data.devicestatus[i].openaps.suggested.predBGs) {
    // Select one curve: COB > UAM > IOB
    if (predBGs.COB) {
        entry.values = predBGs.COB;
    } else if (predBGs.UAM) {
        entry.values = predBGs.UAM;
    } else {
        entry.values = predBGs.IOB;
    }
}
```

---

## IOB Structure Differences

| Field | Loop | oref0/AAPS |
|-------|------|------------|
| `iob` | Total IOB | Total IOB |
| `basaliob` | ❌ | ✅ Basal component |
| `bolusiob` | ❌ | ✅ Bolus component |
| `activity` | ❌ | ✅ Insulin activity |
| `lastBolusTime` | ❌ | ✅ Last bolus timestamp |

---

## Trio Compatibility

**Source:** `externals/Trio/` (uses oref1)

Trio sends `status.openaps` format because it uses oref1 algorithm:

```swift
// NightscoutAPI.swift uses devicestatus.json endpoint
static let statusPath = "/api/v1/devicestatus.json"
```

Trio is **compatible** with oref0/AAPS devicestatus parsing in Nightscout.

---

## Gaps Identified

### GAP-DS-001: Incompatible Prediction Formats

**Description:** Loop uses single `predicted.values` array while oref0 uses four separate `predBGs.*` curves. Nightscout must handle both formats.

**Source:** 
- `externals/cgm-remote-monitor/lib/report_plugins/daytoday.js:347-357`
- `externals/LoopWorkspace/.../StoredDosingDecision.swift:155`

**Impact:** 
- Reports must conditionally parse either format
- No unified prediction visualization API
- Third-party tools must implement both parsers

**Remediation:** Define unified prediction schema with optional curve decomposition.

### GAP-DS-002: Missing Basal/Bolus IOB Split in Loop

**Description:** Loop reports only total IOB, while oref0 provides `basaliob` and `bolusiob` components.

**Source:** `externals/AndroidAPS/.../NSDeviceStatus.kt:57`

**Impact:** Nightscout displays can't show IOB breakdown for Loop users.

**Remediation:** Loop could add optional `basaliob`/`bolusiob` fields.

### GAP-DS-003: No Override Status in oref0

**Description:** Loop has `status.override` for temporary target overrides, but oref0 uses different mechanism.

**Source:** `externals/LoopWorkspace/.../StoredDosingDecision.swift:160`

**Impact:** Override visualization only works for Loop.

**Remediation:** AAPS could add equivalent override reporting.

### GAP-DS-004: Different eventualBG Reporting

**Description:** oref0 explicitly reports `eventualBG` prediction endpoint, Loop does not.

**Source:** `externals/cgm-remote-monitor/lib/plugins/openaps.js`

**Impact:** Loop users don't see eventual BG in Nightscout.

**Remediation:** Loop could add `eventualBG` field.

---

## OpenAPI Specification Gap

The current `aid-devicestatus-2025.yaml` spec should be updated to:

1. Document both `status.loop` and `status.openaps` schemas
2. Mark prediction format as polymorphic (oneOf)
3. Add x-aid-controller annotations for each field
4. Include examples for both controller types

---

## Recommendations

### For Nightscout Server

1. **Unified prediction endpoint** - Normalize both formats to common structure
2. **Document both schemas** - OpenAPI spec for each controller type
3. **Add controller detection** - Identify source from `device` field prefix

### For Loop Team

1. **Add prediction curve options** - Consider splitting IOB/COB/UAM
2. **Add eventualBG** - Match oref0 for consistency
3. **Add IOB breakdown** - `basaliob`/`bolusiob` fields

### For Third-Party Tools

1. **Check device prefix** - `loop://` vs `openaps://`
2. **Parse accordingly** - Use appropriate schema
3. **Handle missing fields** - Graceful degradation

---

## Source File References

| Project | File | Lines |
|---------|------|-------|
| Nightscout | `lib/plugins/loop.js` | 97-145 |
| Nightscout | `lib/plugins/openaps.js` | 214-238 |
| Nightscout | `lib/report_plugins/daytoday.js` | 347-357 |
| Loop | `StoredDosingDecision.swift` | 145-161 |
| AAPS | `NSDeviceStatus.kt` | 13-60 |
| Trio | `NightscoutAPI.swift` | 17 |

---

## Related Documents

- `docs/10-domain/algorithm-comparison-deep-dive.md` - Algorithm differences
- `specs/openapi/aid-devicestatus-2025.yaml` - OpenAPI spec
- `mapping/nightscout/devicestatus-fields.md` - Field mapping
