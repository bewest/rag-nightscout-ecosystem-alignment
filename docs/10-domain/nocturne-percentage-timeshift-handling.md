# Nocturne Percentage/Timeshift Handling

> **OQ-010 Item #6**: Analysis of how Nocturne applies AAPS-specific `percentage` and `timeshift` fields from ProfileSwitch treatments.

## Summary

**Key Finding**: Nocturne applies percentage/timeshift scaling **only internally** for its own calculations (IOB, COB, bolus wizard). The Profile API endpoints (V1/V3) return **raw, unscaled** profile data. This means Loop and Trio, which fetch profiles via these APIs, do not receive scaled values.

| Context | Percentage Applied? | Timeshift Applied? |
|---------|--------------------|--------------------|
| **Profile API (V1/V3)** | ❌ No | ❌ No |
| **Nocturne IOB calculations** | ✅ Yes | ✅ Yes |
| **Nocturne COB calculations** | ✅ Yes | ✅ Yes |
| **Nocturne Bolus Wizard** | ✅ Yes | ✅ Yes |
| **Nocturne Chart/Stats** | ✅ Yes | ✅ Yes |

## Architecture

### Profile API Endpoints (No Scaling)

The Profile API controllers serve raw profile data directly from storage:

```
V1: GET /api/v1/profile       → Returns Profile[] from PostgreSQL
V3: GET /api/v3/profile       → Returns Profile[] from PostgreSQL (with pagination)
V1: GET /api/v1/profile/current → Returns single active Profile
```

**Source Reference**: 
- `externals/nocturne/src/API/Nocturne.API/Controllers/V1/ProfileController.cs:38-106`
- `externals/nocturne/src/API/Nocturne.API/Controllers/V3/ProfileController.cs:36-97`

These controllers:
1. Fetch profiles from `IProfileDataService` or `IPostgreSqlService`
2. Return the Profile model directly
3. Do NOT consult ProfileSwitch treatments
4. Do NOT apply percentage or timeshift transformations

### Internal Calculations (Scaling Applied)

The scaling happens in `ProfileService.GetValueByTime()`:

```csharp
// externals/nocturne/src/API/Nocturne.API/Services/ProfileService.cs:164-245
public double GetValueByTime(long time, string valueType, string? specProfile = null)
{
    // Check for active ProfileSwitch treatment
    var activeTreatment = GetActiveProfileTreatment(time);
    var isCcpProfile = activeTreatment?.CircadianPercentageProfile == true;

    if (isCcpProfile)
    {
        percentage = activeTreatment?.Percentage ?? 100.0;
        timeshift = activeTreatment?.Timeshift ?? 0.0;
    }

    // Apply timeshift to time lookup
    var adjustedTime = time + (long)(offset * 3600000);

    // Get base value from profile
    var returnValue = GetValueFromContainer(valueContainer, timeAsSecondsFromMidnight, valueType);

    // Apply percentage scaling
    switch (valueType)
    {
        case "sens":
        case "carbratio":
            returnValue = returnValue * 100 / percentage;  // Inverse scaling
            break;
        case "basal":
            returnValue = returnValue * percentage / 100;  // Direct scaling
            break;
    }

    return returnValue;
}
```

### Consumers of Scaled Values

Services that call `GetValueByTime()` and receive scaled values:

| Service | File | Usage |
|---------|------|-------|
| **IobService** | `Services/IobService.cs` | IOB decay calculations |
| **CobService** | `Services/CobService.cs` | COB absorption calculations |
| **BolusWizardService** | `Services/BolusWizardService.cs` | Bolus recommendations |
| **PropertiesService** | `Services/PropertiesService.cs` | Properties endpoint |
| **CachedCalculationService** | `Infrastructure.Cache/Services/CachedCalculationService.cs` | Cached IOB/COB |
| **ChartDataController** | `Controllers/V4/ChartDataController.cs` | V4 chart data |
| **RetrospectiveController** | `Controllers/V4/RetrospectiveController.cs` | Retrospective analysis |
| **StatisticsController** | `Controllers/StatisticsController.cs` | Statistics endpoints |

## Cross-Controller Implications

### What Loop/Trio See

When Loop or Trio fetch from Nocturne:

1. **Profile fetch**: `GET /api/v1/profile/current` returns raw profile
2. **No awareness of ProfileSwitch**: Loop doesn't fetch treatments to check for active ProfileSwitch
3. **Uses raw values**: basal, ISF, CR used as-is for algorithm

**Source Reference**:
- `externals/LoopWorkspace/NightscoutService/NightscoutServiceKit/Extensions/ProfileSet.swift:34-95`
- Loop's `ProfileSet.therapySettings` extension extracts values directly from Nightscout profile

### Scenario: AAPS User with 150% ProfileSwitch

1. AAPS user activates ProfileSwitch with `percentage: 150`
2. AAPS uploads treatment to Nocturne with `CircadianPercentageProfile: true`
3. **Nocturne internal calculations**:
   - Basal × 1.5 (e.g., 1.0 U/hr → 1.5 U/hr)
   - ISF ÷ 1.5 (e.g., 50 mg/dL/U → 33 mg/dL/U)
   - CR ÷ 1.5 (e.g., 10 g/U → 6.67 g/U)
4. **Loop/Trio fetch profile**:
   - Receive raw values (1.0 U/hr, 50 mg/dL/U, 10 g/U)
   - Unaware that AAPS intended 150% scaling

### Impact Assessment

| Aspect | Impact |
|--------|--------|
| **IOB display** | Nocturne shows IOB based on scaled basal; Loop shows based on raw |
| **COB display** | Nocturne shows COB based on scaled CR; Loop shows based on raw |
| **Bolus suggestions** | Would differ if both calculated (Nocturne uses scaled, Loop uses raw) |
| **Algorithm decisions** | Loop/Trio algorithms use raw profiles, ignoring AAPS intent |

## Comparison with cgm-remote-monitor

| Behavior | Nocturne | cgm-remote-monitor |
|----------|----------|-------------------|
| **Stores ProfileSwitch treatment** | ✅ Yes | ✅ Yes |
| **Applies percentage in calculations** | ✅ Yes (internal) | ❌ No |
| **Applies timeshift in calculations** | ✅ Yes (internal) | ❌ No |
| **Profile API returns scaled values** | ❌ No | ❌ No |
| **CircadianPercentageProfile handling** | ✅ Implemented | ⚠️ Display only |

**Result**: Both servers return raw profiles via API. However, Nocturne's internal calculations (IOB, COB, bolus wizard) use scaled values while cgm-remote-monitor does not apply scaling anywhere.

## Related Gaps

| Gap ID | Description |
|--------|-------------|
| GAP-NOCTURNE-004 | ProfileSwitch percentage/timeshift application divergence |
| GAP-SYNC-037 | ProfileSwitch percentage field interpretation varies |

## Recommendations

### Short-term (Documentation)

1. Document that Loop/Trio ignore AAPS ProfileSwitch percentage/timeshift
2. Add warning to AAPS documentation about multi-controller scenarios
3. Update Nocturne API docs to clarify internal-only scaling

### Medium-term (API Enhancement)

Consider a new endpoint that returns **effective** profile values at a given time:

```
GET /api/v4/profile/effective?time=1706600400000
```

Response would include scaled values based on active ProfileSwitch treatment.

### Long-term (Standardization)

REQ-SYNC-055 proposes: Servers SHOULD provide API endpoint returning effective profile after applying active ProfileSwitch percentage/timeshift.

## Source Files Analyzed

| File | Purpose |
|------|---------|
| `externals/nocturne/src/API/Nocturne.API/Controllers/V1/ProfileController.cs` | V1 Profile API |
| `externals/nocturne/src/API/Nocturne.API/Controllers/V3/ProfileController.cs` | V3 Profile API |
| `externals/nocturne/src/API/Nocturne.API/Services/ProfileService.cs:164-245` | GetValueByTime with scaling |
| `externals/nocturne/src/API/Nocturne.API/Services/IobService.cs` | IOB using scaled values |
| `externals/nocturne/src/API/Nocturne.API/Services/CobService.cs` | COB using scaled values |
| `externals/nocturne/src/API/Nocturne.API/Services/BolusWizardService.cs` | Bolus wizard using scaled values |
| `externals/LoopWorkspace/NightscoutService/NightscoutServiceKit/Extensions/ProfileSet.swift` | Loop profile parsing |

## Questions Answered

### Q1: Does Nocturne apply percentage scaling when serving profiles?

**No.** Profile API (V1/V3) returns raw profile data. Scaling only applied internally.

### Q2: Is timeshift rotation applied or stored as metadata?

**Both.** Timeshift is stored in the ProfileSwitch treatment and applied when `GetValueByTime()` is called for internal calculations. Not applied for API responses.

### Q3: What happens when Loop/Trio fetch AAPS ProfileSwitch with percentage!=100?

**They see raw values.** Loop/Trio:
1. Fetch from Profile API (raw, unscaled)
2. Do not check for ProfileSwitch treatments
3. Use raw values in their algorithms

The AAPS user's intent (e.g., 150% increased needs) is **not communicated** to Loop/Trio.

---

*Analysis Date: 2026-01-30*
*OQ-010 Research Queue: Item #6 of 7*
