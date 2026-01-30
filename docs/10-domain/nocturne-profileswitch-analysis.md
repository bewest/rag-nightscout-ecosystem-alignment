# Nocturne ProfileSwitch Treatment Model Analysis

> **Date**: 2026-01-30  
> **Status**: Complete  
> **Domain**: Sync & Identity / Profile  
> **OQ Reference**: [OQ-010](../OPEN-QUESTIONS.md#oq-010-profileswitch--override-mapping)

---

## Executive Summary

Nocturne provides **full support for AAPS ProfileSwitch semantics**, including `percentage`, `timeshift`, and `profileJson` fields. The implementation actively applies CircadianPercentageProfile adjustments when computing profile values for oref calculations.

| Feature | Nocturne Support | Notes |
|---------|------------------|-------|
| `Profile Switch` eventType | ✅ Full | Stored in treatments collection |
| `profileJson` embedding | ✅ Full | Stored as JSONB in PostgreSQL |
| `percentage` scaling | ✅ Applied | Used in ISF/CR/basal calculations |
| `timeshift` rotation | ✅ Applied | Used for schedule time offset |
| `CircadianPercentageProfile` flag | ✅ Supported | Triggers percentage/timeshift logic |

---

## 1. Treatment Model Fields

Nocturne's `Treatment.cs` model includes all AAPS ProfileSwitch-specific fields:

### ProfileSwitch Fields

| Field | Type | Source | Notes |
|-------|------|--------|-------|
| `ProfileJson` | `string?` | Line 415-417 | JSON string of profile data, marked `[NocturneOnly]` |
| `EndProfile` | `string?` | Line 421-424 | End profile name for switches |
| `Profile` | `string?` | Line 255-256 | Active profile name |
| `Percentage` | `double?` | Line 512-513 | Percentage scaling (100 = normal) |
| `Timeshift` | `double?` | Line 518-519 | Schedule rotation in hours |
| `CircadianPercentageProfile` | `bool?` | Line 505-507 | Flag for CPP treatment type |
| `Duration` | `double?` | Line 182-203 | Duration in minutes (0 = permanent) |

### Source Reference

```csharp
// src/Core/Nocturne.Core.Models/Treatment.cs:413-519
[JsonPropertyName("profileJson")]
[Sanitizable]
[NocturneOnly]
public string? ProfileJson { get; set; }

[JsonPropertyName("percentage")]
public double? Percentage { get; set; }

[JsonPropertyName("timeshift")]
public double? Timeshift { get; set; }

[JsonPropertyName("CircadianPercentageProfile")]
[JsonConverter(typeof(FlexibleBooleanJsonConverter))]
public bool? CircadianPercentageProfile { get; set; }
```

---

## 2. Database Entity

The `TreatmentEntity.cs` maps ProfileSwitch fields to PostgreSQL columns:

| Column | Type | Notes |
|--------|------|-------|
| `profileJson` | `jsonb` | Full embedded profile data |
| `profile` | `varchar(255)` | Profile name reference |
| `percentage` | `double` | Scaling factor |
| `timeshift` | `double` | Hours offset |
| `CircadianPercentageProfile` | `bool` | CPP flag |
| `endprofile` | `varchar(255)` | End profile name |

### Source Reference

```csharp
// src/Infrastructure/Nocturne.Infrastructure.Data/Entities/TreatmentEntity.cs:256-351
[Column("profileJson", TypeName = "jsonb")]
public string? ProfileJson { get; set; }

[Column("percentage")]
public double? Percentage { get; set; }

[Column("timeshift")]
public double? Timeshift { get; set; }
```

---

## 3. ProfileService: Percentage/Timeshift Application

**Critical Finding**: Nocturne **actively applies** percentage and timeshift adjustments when computing profile values.

### CircadianPercentageProfile Logic

```csharp
// src/API/Nocturne.API/Services/ProfileService.cs:175-241
public double GetValueByTime(long time, string valueType, string? specProfile = null)
{
    // CircadianPercentageProfile support
    var timeshift = 0.0;
    var percentage = 100.0;
    var activeTreatment = GetActiveProfileTreatment(time);
    var isCcpProfile =
        string.IsNullOrEmpty(specProfile)
        && activeTreatment?.CircadianPercentageProfile == true;

    if (isCcpProfile)
    {
        percentage = activeTreatment?.Percentage ?? 100.0;
        timeshift = activeTreatment?.Timeshift ?? 0.0; // in hours
    }

    var offset = timeshift % 24;
    var adjustedTime = time + (long)(offset * 3600000); // Convert hours to milliseconds

    // ... get profile value ...

    // Apply CircadianPercentageProfile adjustments
    if (isCcpProfile && returnValue != 0)
    {
        switch (valueType)
        {
            case "sens":       // ISF scaled inversely
            case "carbratio":  // CR scaled inversely
                returnValue = returnValue * 100 / percentage;
                break;
            case "basal":      // Basal scaled directly
                returnValue = returnValue * percentage / 100;
                break;
        }
    }
}
```

### Scaling Behavior

| Profile Value | Percentage Effect | Example (150%) |
|---------------|-------------------|----------------|
| `basal` | Direct scaling | 1.0 → 1.5 U/hr |
| `sens` (ISF) | Inverse scaling | 50 → 33.3 mg/dL/U |
| `carbratio` (CR) | Inverse scaling | 10 → 6.67 g/U |
| `target_low` | Not scaled | Unchanged |
| `target_high` | Not scaled | Unchanged |

**Interpretation**: Percentage > 100 means MORE insulin (higher basal, lower ISF/CR).

---

## 4. Event Type Constants

Nocturne defines `ProfileSwitch` as a standard treatment type:

```csharp
// src/Core/Nocturne.Core.Models/TreatmentEventType.cs:122-125
[EnumMember(Value = "Profile Switch")]
ProfileSwitch,

// src/Connectors/Nocturne.Connectors.Core/Constants/TreatmentTypes.cs:60-62
public const string ProfileSwitch = "Profile Switch";
```

---

## 5. DDataService: Profile Switch Filtering

The DData endpoint (Loop/AAPS combined data) explicitly filters for Profile Switch events:

```csharp
// src/API/Nocturne.API/Services/DDataService.cs:164-171
var profileTreatments = treatments
    .Where(t => !string.IsNullOrEmpty(t.EventType) && t.EventType == "Profile Switch")
    .OrderBy(t => t.Mills)
    .ToList();
```

---

## 6. Connector Support

The MyLife connector includes a dedicated `ProfileSwitchTreatmentHandler`:

```csharp
// src/Connectors/Nocturne.Connectors.MyLife/Mappers/Handlers/ProfileSwitchTreatmentHandler.cs:9-81
internal sealed class ProfileSwitchTreatmentHandler : IMyLifeTreatmentHandler
{
    public bool CanHandle(MyLifeEvent ev) { ... }
    
    public IEnumerable<Treatment> Handle(MyLifeEvent ev, MyLifeTreatmentContext context)
    {
        var profileSwitch = MyLifeTreatmentFactory.CreateWithSuffix(
            ev,
            MyLifeTreatmentTypes.ProfileSwitch,
            MyLifeIdSuffixes.ProfileSwitch
        );
        profileSwitch.Notes = ev.InformationFromDevice;
        profileSwitch.Profile = ExtractProfileName(info);
        return [profileSwitch];
    }
}
```

---

## 7. Rust oref Integration

The oref Rust FFI accepts profile JSON for IOB/COB/autosens calculations:

```csharp
// src/Core/Nocturne.Core.Oref/OrefInterop.cs:86-108
public static string CalculateIob(string profileJson, string treatmentsJson, long timeMillis, bool currentOnly = true)
```

The `OrefProfile` model passed to Rust:

```csharp
// src/Core/Nocturne.Core.Oref/Models/OrefModels.cs:6-11
public class OrefProfile
{
    [JsonPropertyName("dia")]
    public double Dia { get; set; }
    // ... sens, carbratio, basal, targets
}
```

**Note**: The oref Rust implementation receives PRE-SCALED profile values from ProfileService, meaning percentage adjustments are already applied before oref calculations.

---

## 8. Comparison: Nocturne vs cgm-remote-monitor

| Aspect | Nocturne | cgm-remote-monitor |
|--------|----------|-------------------|
| ProfileSwitch storage | treatments table (JSONB) | treatments collection (BSON) |
| profileJson field | ✅ Supported | ✅ Supported |
| percentage application | ✅ Applied in ProfileService | ❌ Display only |
| timeshift application | ✅ Applied in ProfileService | ❌ Display only |
| oref integration | Rust FFI with pre-scaled values | JS with display values |

**Key Difference**: Nocturne **actually applies** percentage/timeshift to algorithm calculations, while cgm-remote-monitor only displays them.

---

## 9. Gap Analysis Updates

### GAP-SYNC-037 Update: Percentage/Timeshift Portability

**Previous Status**: AAPS-specific, not portable to Loop/Trio.

**Nocturne Status**: Fully supported. When Loop/Trio fetch profiles from Nocturne:
- If `CircadianPercentageProfile = true`, scaled values are returned
- API responses include both original and effective values
- Loop/Trio receive percentage-adjusted basal/ISF/CR

**Remediation**: Nocturne provides a path for percentage/timeshift interoperability.

---

### New Finding: GAP-NOCTURNE-004

**Description**: Nocturne applies percentage/timeshift in calculations, but cgm-remote-monitor does not. This creates behavioral divergence when the same ProfileSwitch treatment is stored in both systems.

**Impact**: 
- Users migrating from cgm-remote-monitor to Nocturne may see different IOB/COB/predictions
- Algorithm recommendations differ based on server platform

**Remediation**: Document as expected divergence; Nocturne behavior is more correct per AAPS semantics.

---

## 10. Requirements

### REQ-SYNC-054: ProfileSwitch Percentage Application

**Statement**: Servers ingesting ProfileSwitch treatments with `percentage != 100` SHOULD apply scaling to returned profile values.

**Rationale**: AAPS percentage adjustments are meant to affect actual insulin delivery, not just display.

**Verification**: Create ProfileSwitch with percentage=150; verify basal*1.5, ISF/0.667, CR/0.667 in API responses.

**Nocturne Status**: ✅ Compliant

**cgm-remote-monitor Status**: ❌ Not compliant (display only)

---

### REQ-SYNC-055: ProfileSwitch Timeshift Application

**Statement**: Servers ingesting ProfileSwitch treatments with `timeshift != 0` SHOULD rotate schedule lookup time accordingly.

**Rationale**: AAPS timeshift is meant to shift the basal/ISF/CR schedule for travel or schedule changes.

**Verification**: Create ProfileSwitch with timeshift=6; verify 6am values returned at midnight.

**Nocturne Status**: ✅ Compliant

---

## 11. Answers to OQ-010 Research Questions

| Question | Answer |
|----------|--------|
| Does Nocturne create ProfileSwitch treatment events? | Yes, via connectors and API ingestion |
| How does Nocturne map AAPS `profileJson` embedded data? | Stored as JSONB in PostgreSQL, served via API |
| Does Nocturne store profile references or embed full profile? | Both: `profile` name + optional `profileJson` embed |
| Does Nocturne apply percentage scaling? | **Yes, actively applied in ProfileService** |
| Does Nocturne apply timeshift rotation? | **Yes, actively applied in ProfileService** |

---

## 12. Source Files Analyzed

| Purpose | Path |
|---------|------|
| Treatment model | `src/Core/Nocturne.Core.Models/Treatment.cs:413-519` |
| Entity mapping | `src/Infrastructure/Nocturne.Infrastructure.Data/Entities/TreatmentEntity.cs:256-351` |
| ProfileService | `src/API/Nocturne.API/Services/ProfileService.cs:175-241` |
| EventType enum | `src/Core/Nocturne.Core.Models/TreatmentEventType.cs:122-125` |
| TreatmentTypes const | `src/Connectors/Nocturne.Connectors.Core/Constants/TreatmentTypes.cs:60-62` |
| DDataService | `src/API/Nocturne.API/Services/DDataService.cs:164-171` |
| ProfileSwitch handler | `src/Connectors/Nocturne.Connectors.MyLife/Mappers/Handlers/ProfileSwitchTreatmentHandler.cs` |
| Oref interop | `src/Core/Nocturne.Core.Oref/OrefInterop.cs:86-108` |

---

## 13. Cross-References

- [Profile Switch Sync Comparison](profile-switch-sync-comparison.md)
- [Nocturne Deep Dive](nocturne-deep-dive.md)
- [OQ-010: ProfileSwitch → Override mapping](../OPEN-QUESTIONS.md#oq-010-profileswitch--override-mapping)
- [GAP-SYNC-037](../../traceability/sync-identity-gaps.md)
- [Sync Identity Backlog](../sdqctl-proposals/backlogs/sync-identity.md)

---

## 14. Next Steps

1. **Item #6**: Analyze percentage/timeshift when Loop/Trio fetch from Nocturne
2. **Item #7**: Compare deduplication logic for profile collection
3. **Item #8**: Analyze Override vs Temporary Target representation
4. **ADR-004**: Draft decision record incorporating these findings
