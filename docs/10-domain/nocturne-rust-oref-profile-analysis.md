# Nocturne Rust oref Profile Handling Analysis

> **OQ-010 Item #10**: How does Rust oref implementation use profile data?

## Summary

Nocturne's Rust oref implementation provides **algorithm-equivalent** profile parsing to JS oref0, but the C# integration layer has a **critical gap**: the `PredictionService` bypasses `ProfileService` and sends raw profile values to oref, ignoring active ProfileSwitch percentage/timeshift adjustments.

| Aspect | Rust oref | JS oref0 | Status |
|--------|-----------|----------|--------|
| Basal schedule parsing | ✅ Same | ✅ Same | Equivalent |
| ISF schedule parsing | ✅ Same | ✅ Same | Equivalent |
| CR schedule parsing | ✅ Same | ✅ Same | Equivalent |
| Time format | minutes from midnight | minutes from midnight | Equivalent |
| Schedule sorting | by `i` index | by `i` index | Equivalent |
| Percentage/timeshift | ❌ Not applied | ❌ Not in oref | GAP |

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      Nocturne API                               │
├─────────────────────────────────────────────────────────────────┤
│  ProfileService           │  PredictionService                  │
│  ✅ Applies percentage    │  ❌ Reads directly from DB          │
│  ✅ Applies timeshift     │  ❌ Bypasses ProfileService         │
│  → Used by chart/stats    │  → Feeds Rust oref                  │
└─────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
                    ┌─────────────────────────────────┐
                    │    OrefService (C# wrapper)     │
                    │    Serializes OrefProfile → JSON│
                    └─────────────────────────────────┘
                                      │
                                      ▼ FFI/WASM
                    ┌─────────────────────────────────┐
                    │    Rust oref (native)           │
                    │    Parses schedules, runs algo  │
                    └─────────────────────────────────┘
```

## Research Questions Answered

### 1. Does Rust oref consume percentage-scaled profiles?

**No.** The `PredictionService` that feeds Rust oref reads directly from `_postgresService.GetProfilesAsync()`, bypassing `ProfileService` which applies percentage/timeshift:

```csharp
// PredictionService.cs:165-186
var profiles = await _postgresService.GetProfilesAsync(1, 0, cancellationToken);
var dbProfile = profiles.FirstOrDefault();
// ...
return new OrefModels.OrefProfile
{
    Dia = activeStore.Dia,
    CurrentBasal = activeStore.Basal?.FirstOrDefault()?.Value ?? 1.0,  // RAW!
    Sens = activeStore.Sens?.FirstOrDefault()?.Value ?? 50.0,          // RAW!
    CarbRatio = activeStore.CarbRatio?.FirstOrDefault()?.Value ?? 10.0, // RAW!
    // ...
};
```

Meanwhile, `ProfileService.GetProfileValue()` **does** apply percentage/timeshift:

```csharp
// ProfileService.cs:228-241
if (isCcpProfile && returnValue != 0)
{
    switch (valueType)
    {
        case "sens":
        case "carbratio":
            returnValue = returnValue * 100 / percentage;
            break;
        case "basal":
            returnValue = returnValue * percentage / 100;
            break;
    }
}
```

**GAP-OREF-001**: PredictionService bypasses ProfileService, sending unscaled values to Rust oref.

### 2. Same basal/ISF/CR block parsing as JS oref?

**Yes.** The Rust implementation is algorithmically equivalent to JS oref0:

#### Basal Lookup Comparison

**Rust** (`src/Core/oref/src/profile/basal.rs:7-36`):
```rust
pub fn basal_lookup(profile: &Profile, time: DateTime<Utc>) -> f64 {
    let now_minutes = time.hour() * 60 + time.minute();
    let mut schedule: Vec<_> = profile.basal_profile.iter().collect();
    schedule.sort_by_key(|e| e.i);
    
    for i in 0..schedule.len() {
        if now_minutes >= entry.minutes && now_minutes < next_minutes {
            rate = entry.rate;
            break;
        }
    }
    (rate * 1000.0).round() / 1000.0
}
```

**JS oref0** (`lib/profile/basal.js:6-30`):
```javascript
function basalLookup(schedules, now) {
    var nowMinutes = nowDate.getHours() * 60 + nowDate.getMinutes();
    var basalprofile_data = _.sortBy(schedules, function(o) { return o.i; });
    
    for (var i = 0; i < basalprofile_data.length - 1; i++) {
        if ((nowMinutes >= basalprofile_data[i].minutes) && 
            (nowMinutes < basalprofile_data[i + 1].minutes)) {
            basalRate = basalprofile_data[i].rate;
            break;
        }
    }
    return Math.round(basalRate*1000)/1000;
}
```

Both:
- Sort by `i` index
- Use minutes from midnight
- Round to 3 decimal places
- Return last entry as fallback

#### ISF Lookup Comparison

**Rust** (`src/Core/oref/src/profile/isf.rs:13-47`):
- Uses `offset` (minutes from midnight)
- Sorts by `offset`
- Validates first entry starts at 0
- Returns `profile.sens` as fallback

**JS oref0** (`lib/profile/isf.js`):
- Uses `offset` (minutes from midnight)
- Same time-window logic
- Returns `profile.sens` as fallback

### 3. Any divergence in profile time interpretation?

**No divergence in Rust vs JS.** Both use:
- Minutes from midnight for schedule entries
- UTC time for lookups
- `i` index for sorting order

**However**, there is a divergence in **which profile is used**:
- `ProfileService` considers active ProfileSwitch treatments
- `PredictionService` ignores ProfileSwitch, uses raw profile from database

## Rust Profile Model

The Rust `Profile` struct (`src/Core/oref/src/types/profile.rs`) is comprehensive:

```rust
pub struct Profile {
    // Core values
    pub dia: f64,
    pub current_basal: f64,
    pub sens: f64,
    pub carb_ratio: f64,
    pub min_bg: f64,
    pub max_bg: f64,
    
    // Safety limits
    pub max_iob: f64,
    pub max_basal: f64,
    pub max_daily_basal: f64,
    
    // SMB settings
    pub enable_smb_always: bool,
    pub enable_smb_with_cob: bool,
    pub max_smb_basal_minutes: u32,
    
    // Schedules
    pub basal_profile: Vec<BasalScheduleEntry>,
    pub isf_profile: ISFProfile,
    pub carb_ratio_profile: Vec<CarbRatioScheduleEntry>,
    
    // ... 40+ fields total
}
```

## C# OrefProfile Model (Simplified)

The C# `OrefProfile` model (`OrefModels.cs`) is **simplified**:

```csharp
public class OrefProfile
{
    public double Dia { get; set; } = 3.0;
    public double CurrentBasal { get; set; }      // Single value, not schedule
    public double Sens { get; set; } = 50.0;      // Single value, not schedule
    public double CarbRatio { get; set; } = 10.0; // Single value, not schedule
    public double MinBg { get; set; } = 100.0;
    public double MaxBg { get; set; } = 120.0;
    // ...
}
```

**GAP-OREF-002**: C# OrefProfile only passes single current values, not full schedules. This limits algorithm accuracy for multi-rate profiles.

## Gaps Identified

### GAP-OREF-001: PredictionService Bypasses ProfileService

**Description**: `PredictionService` reads profiles directly from database, bypassing `ProfileService` which applies percentage/timeshift from active ProfileSwitch treatments.

**Affected Systems**: Nocturne predictions when AAPS ProfileSwitch is active

**Impact**: Algorithm predictions use raw profile values instead of scaled values. A 150% ProfileSwitch is ignored by predictions.

**Evidence**:
- `PredictionService.cs:165-186` - reads from `_postgresService.GetProfilesAsync()`
- `ProfileService.cs:228-241` - applies percentage/timeshift (not used by PredictionService)

**Remediation**: Inject `IProfileService` into `PredictionService`; use `GetBasalRate()`, `GetSensitivity()`, `GetCarbRatio()` methods.

### GAP-OREF-002: OrefProfile Lacks Full Schedule Support

**Description**: The C# `OrefProfile` model only passes single current values (`CurrentBasal`, `Sens`, `CarbRatio`) to Rust oref, not the full time-varying schedules that Rust oref supports.

**Affected Systems**: Nocturne algorithm accuracy

**Impact**: Multi-rate profile schedules are reduced to first/current value. Time-of-day variations ignored.

**Evidence**:
- Rust `Profile` has `basal_profile: Vec<BasalScheduleEntry>`
- C# `OrefProfile` has `CurrentBasal: double`
- `PredictionService.cs:176`: `CurrentBasal = activeStore.Basal?.FirstOrDefault()?.Value`

**Remediation**: Extend `OrefProfile` to include schedule arrays; serialize full schedules to Rust.

### GAP-OREF-003: No Timeshift Propagation to Rust

**Description**: Even if percentage is applied, timeshift rotation is not propagated to Rust oref for schedule lookups.

**Affected Systems**: Users with timeshift-based ProfileSwitch (travel, circadian adjustments)

**Impact**: Rust oref uses wrong time-of-day for schedule lookups.

**Remediation**: Either apply timeshift in C# before calling Rust, or pass timeshift parameter to Rust.

## Requirements

### REQ-OREF-001: Percentage Application for Predictions

**Statement**: Prediction calculations SHOULD apply active ProfileSwitch percentage to basal/ISF/CR values.

**Rationale**: Ensures predictions match actual insulin delivery when percentage adjustment is active.

**Verification**: Create ProfileSwitch with percentage=150; verify predictions use scaled basal.

### REQ-OREF-002: Full Schedule Propagation

**Statement**: Algorithm implementations SHOULD receive full time-varying schedules, not just current values.

**Rationale**: Enables accurate multi-hour predictions that account for scheduled rate changes.

**Verification**: Profile has 4 basal rates; verify 24-hour prediction uses correct rate per time block.

### REQ-OREF-003: Rust/JS Oref Equivalence Testing

**Statement**: Rust oref and JS oref0 SHOULD produce equivalent outputs for identical inputs.

**Rationale**: Ensures Nocturne users get same algorithm behavior as AAPS/Trio.

**Verification**: Feed identical profile/glucose/treatment data to both; compare outputs.

## Comparison Summary

| Feature | JS oref0 | Rust oref | C# Integration |
|---------|----------|-----------|----------------|
| Schedule parsing | ✅ | ✅ | ❌ Single values only |
| Time lookup | minutes | minutes | N/A |
| Sorting | by i | by i | N/A |
| Percentage | N/A (caller applies) | N/A (caller applies) | ❌ Not applied |
| Timeshift | N/A (caller applies) | N/A (caller applies) | ❌ Not applied |
| Full schedules | ✅ | ✅ | ❌ FirstOrDefault() |

## Source Files Analyzed

| File | Description |
|------|-------------|
| `src/Core/oref/src/profile/mod.rs` | Rust profile module exports |
| `src/Core/oref/src/profile/basal.rs` | Basal schedule lookup (116 lines) |
| `src/Core/oref/src/profile/isf.rs` | ISF schedule lookup (108 lines) |
| `src/Core/oref/src/types/profile.rs` | Rust Profile struct (526 lines) |
| `src/Core/Nocturne.Core.Oref/OrefService.cs` | C# wrapper (212 lines) |
| `src/Core/Nocturne.Core.Oref/Models/OrefModels.cs` | C# OrefProfile (358 lines) |
| `src/API/Nocturne.API/Services/PredictionService.cs` | Profile → oref conversion |
| `src/API/Nocturne.API/Services/ProfileService.cs` | Percentage/timeshift application |
| `externals/oref0/lib/profile/basal.js` | JS oref0 basal lookup |

---

*Analysis Date: 2026-01-30*
*OQ-010 Research Queue: Item #10 of 7*
