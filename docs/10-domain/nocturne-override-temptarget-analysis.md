# Nocturne Override/Temporary Target Representation

> **OQ-010 Item #8**: How Nocturne stores and serves Override vs Temporary Target events.

## Summary

| Aspect | Loop Override | AAPS Temporary Target |
|--------|--------------|----------------------|
| **eventType** | `Temporary Override` | `Temporary Target` |
| **Storage** | treatments collection | treatments collection |
| **Target Field** | None (uses insulinNeedsScaleFactor) | `targetTop`, `targetBottom` |
| **Insulin Adjustment** | `insulinNeedsScaleFactor` (e.g., 0.9 = 90%) | None |
| **Reason Field** | `reason` (preset name) | `reason` (enum value) |
| **Duration Unit** | minutes | minutes (stored as minutes) |
| **Cancel eventType** | `Temporary Override Cancel` | `Temporary Target` with `duration=0` |

## Key Finding

**Nocturne stores both Loop Override and AAPS Temporary Target as treatment documents with different eventTypes.** They are NOT unified or mapped - each system's representation is preserved as-is.

## EventType Handling

### Loop Override Events

Nocturne handles Loop overrides via the LoopService for remote commands:

```csharp
// LoopService.cs:310-327
case "Temporary Override":
    payload["override-name"] = data.Reason ?? string.Empty;
    if (!string.IsNullOrEmpty(data.Duration) && int.TryParse(data.Duration, out var duration))
    {
        payload["override-duration-minutes"] = duration;
    }
    alert = $"{data.ReasonDisplay ?? data.Reason} Temporary Override";
    break;

case "Temporary Override Cancel":
    payload["cancel-temporary-override"] = "true";
    alert = "Cancel Temporary Override";
    break;
```

### AAPS Temporary Target Events

OpenAPS plugin defines Temporary Target eventTypes:

```csharp
// OpenApsService.cs:287-314
new
{
    val = "Temporary Target",
    name = "Temporary Target",
    duration = true,
    targets = true,
    reasons = reasonconf,  // Eating Soon, Activity, Manual
}
new
{
    val = "Temporary Target Cancel",
    name = "Temporary Target Cancel",
    duration = false,
}
```

## Treatment Model Fields

### Fields for Loop Override

| Field | Type | Description | Source |
|-------|------|-------------|--------|
| `eventType` | string | `"Temporary Override"` or `"Temporary Override Cancel"` | Treatment.cs:43 |
| `reason` | string | Preset name (e.g., "🏃 Running") | Treatment.cs:50 |
| `reasonDisplay` | string | Display name for reason | Treatment.cs:549 |
| `duration` | double? | Duration in minutes | Treatment.cs:182 |
| `insulinNeedsScaleFactor` | double? | Insulin scaling (0.9 = 90%) | Treatment.cs:429 |

### Fields for AAPS Temporary Target

| Field | Type | Description | Source |
|-------|------|-------------|--------|
| `eventType` | string | `"Temporary Target"` | Treatment.cs:43 |
| `targetTop` | double? | Upper target in mg/dL | Treatment.cs:243 |
| `targetBottom` | double? | Lower target in mg/dL | Treatment.cs:249 |
| `duration` | double? | Duration in minutes | Treatment.cs:182 |
| `reason` | string | Enum value (Eating Soon, Activity, etc.) | Treatment.cs:50 |

## V4 State Spans

Nocturne provides a V4 abstraction layer for time-ranged states:

```csharp
// StateSpansController.cs:72-80
[HttpGet("overrides")]
public async Task<ActionResult<IEnumerable<StateSpan>>> GetOverrides(
    [FromQuery] long? from = null,
    [FromQuery] long? to = null,
    CancellationToken cancellationToken = default)
{
    var spans = await _stateSpanService.GetStateSpansAsync(
        StateSpanCategory.Override, from: from, to: to, cancellationToken: cancellationToken);
    return Ok(spans);
}
```

### StateSpan Categories

| Category | Description |
|----------|-------------|
| `PumpMode` | Automatic, Manual, Boost, EaseOff, Sleep, Exercise |
| `PumpConnectivity` | Connected, Disconnected, Removed, BluetoothOff |
| `Override` | Custom (user-defined override) |
| `Profile` | Active profile name |
| `TempBasal` | Active or Cancelled |

### Override State Enum

```csharp
// StateSpanEnums.cs:139-151
public enum OverrideState
{
    None,   // No override active
    Custom  // User-defined override (details in metadata)
}
```

**Note**: The V4 StateSpan abstraction provides a unified view of overrides, but does NOT distinguish between Loop Override and AAPS Temporary Target - both would be represented as `OverrideState.Custom`.

## Supersession Tracking

### Current State

**No explicit supersession tracking exists in Nocturne for Override or Temporary Target events.**

When a new override is activated:
1. Old override treatment remains unchanged in database
2. New override treatment is inserted
3. No `supersededBy` or `status` update on old treatment

### V4 StateSpan Approach

StateSpans provide implicit supersession through time ranges:
- Each span has `startMs` and `endMs`
- Overlapping spans are NOT automatically resolved
- Client must query active span for current state

### Gap Impact

Without supersession tracking:
- Cannot determine why an override ended
- Cannot build override history chain
- Different from proposed REQ-OVERRIDE-001 through REQ-OVERRIDE-005

## Comparison with cgm-remote-monitor

### Similarities

| Aspect | Nocturne | cgm-remote-monitor |
|--------|----------|-------------------|
| Override eventType | `Temporary Override` | `Temporary Override` |
| TempTarget eventType | `Temporary Target` | `Temporary Target` |
| Cancel Override | `Temporary Override Cancel` | `Temporary Override Cancel` |
| Cancel TempTarget | `duration=0` | `duration=0` |
| Storage | treatments collection | treatments collection |
| Supersession | None | None |

### Differences

| Aspect | Nocturne | cgm-remote-monitor |
|--------|----------|-------------------|
| V4 StateSpan API | ✅ Yes | ❌ No |
| Override presets | In profile (LoopProfileSettings) | In profile |
| Remote commands | LoopService with APNS | loop.js with APNS |

## LoopOverridePreset Model

Nocturne defines preset structure in profiles:

```csharp
// LoopModels.cs:165-197
public class LoopOverridePreset
{
    [JsonPropertyName("name")]
    public string? Name { get; set; }

    [JsonPropertyName("symbol")]
    public string? Symbol { get; set; }

    [JsonPropertyName("duration")]
    public double? Duration { get; set; }  // seconds

    [JsonPropertyName("targetRange")]
    public LoopTargetRange? TargetRange { get; set; }

    [JsonPropertyName("insulinNeedsScaleFactor")]
    public double? InsulinNeedsScaleFactor { get; set; }
}
```

**Duration unit difference**: Preset duration is in **seconds**, but treatment duration is in **minutes**.

## Gaps Identified

### GAP-OVRD-005: No Unified Override Representation

**Description**: Loop `Temporary Override` and AAPS `Temporary Target` are stored separately with different field semantics. No mapping or unification exists.

**Affected Systems**: Cross-controller queries, Nightscout UI, statistics

**Impact**: Cannot query "all active target modifications" without checking both eventTypes with different field interpretations.

**Remediation**: Define normalized schema or query helper that abstracts both types.

### GAP-OVRD-006: Override Supersession Not Tracked

**Description**: Neither Nocturne nor cgm-remote-monitor tracks override supersession. When a new override activates, the old one is not updated.

**Affected Systems**: All

**Impact**: Cannot determine override history chain or why overrides ended.

**Remediation**: Implement REQ-OVERRIDE-001 through REQ-OVERRIDE-005.

### GAP-OVRD-007: Duration Unit Mismatch in Loop Presets

**Description**: LoopOverridePreset.Duration is in seconds; Treatment.Duration is in minutes. Conversion required.

**Affected Systems**: Loop, Nocturne

**Impact**: Off-by-60x errors if units confused.

**Remediation**: Document unit expectations; add validation.

## Requirements

### REQ-OVRD-004: Cross-Type Override Query

**Statement**: The API MAY provide a unified query for all target-modifying treatments (Override and Temporary Target).

**Rationale**: Simplifies client code that needs to understand "what's affecting targets right now."

**Verification**: Query returns both Loop Override and AAPS Temporary Target in normalized format.

**Gap**: GAP-OVRD-005

### REQ-OVRD-005: Duration Unit Documentation

**Statement**: Systems MUST document duration units (seconds vs minutes) for all override-related fields.

**Rationale**: Prevents off-by-60x conversion errors.

**Verification**: Documentation review for LoopOverridePreset.Duration and Treatment.Duration.

**Gap**: GAP-OVRD-007

## Source Files Analyzed

| File | Description |
|------|-------------|
| `externals/nocturne/src/Core/Nocturne.Core.Models/Treatment.cs` | Treatment model with override fields |
| `externals/nocturne/src/Core/Nocturne.Core.Models/LoopModels.cs` | LoopOverridePreset, LoopNotificationData |
| `externals/nocturne/src/Core/Nocturne.Core.Models/StateSpanEnums.cs` | OverrideState enum |
| `externals/nocturne/src/API/Nocturne.API/Services/LoopService.cs:310-327` | Override push handling |
| `externals/nocturne/src/API/Nocturne.API/Services/OpenApsService.cs:287-314` | TempTarget eventType definition |
| `externals/nocturne/src/API/Nocturne.API/Controllers/V4/StateSpansController.cs:72-80` | V4 override spans |
| `externals/cgm-remote-monitor/lib/server/loop.js:65-71` | Override push handling |
| `externals/cgm-remote-monitor/lib/plugins/openaps.js:301-316` | TempTarget eventType definition |
| `externals/cgm-remote-monitor/lib/report_plugins/daytoday.js:860` | Override rendering |

## Answers to Research Questions

### 1. Does Nocturne distinguish Loop Override from AAPS Temporary Target?

**Yes.** They are stored with different eventTypes:
- Loop: `Temporary Override` (with `insulinNeedsScaleFactor`)
- AAPS: `Temporary Target` (with `targetTop`/`targetBottom`)

### 2. Are these stored in treatments with different eventTypes?

**Yes.** Both are in the `treatments` collection:
- `eventType: "Temporary Override"` for Loop
- `eventType: "Temporary Target"` for AAPS

### 3. What supersession tracking exists (if any)?

**None.** Neither Nocturne nor cgm-remote-monitor updates old overrides when new ones are activated. The V4 StateSpan API provides time-range queries but does NOT link superseded overrides.

---

*Analysis Date: 2026-01-30*
*OQ-010 Research Queue: Item #8 of 7*
