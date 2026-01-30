# Nocturne V4 ProfileSwitch Extensions Discovery

> **OQ-010 Item #9**: Identify V4-specific profile/override endpoints beyond V3.

## Summary

Nocturne's V4 API provides significant extensions beyond V3 for profile and override tracking through the **StateSpan** abstraction. This is a Nocturne-specific feature not present in cgm-remote-monitor.

| Feature | V3 API | V4 API (Nocturne) |
|---------|--------|-------------------|
| Profile CRUD | ✅ `/api/v3/profile` | ✅ Same |
| Profile history query | ❌ | ✅ `/api/v4/state-spans/profiles` |
| Override history query | ❌ | ✅ `/api/v4/state-spans/overrides` |
| Time-range state query | ❌ | ✅ `/api/v4/state-spans?category=...` |
| Activity tracking | ❌ | ✅ Sleep, Exercise, Illness, Travel |

## V4 StateSpan API

### Endpoint: `/api/v4/state-spans`

The V4 StateSpan API provides time-ranged state tracking for various system categories.

### Profile-Specific Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v4/state-spans/profiles` | GET | Query profile state spans |
| `/api/v4/state-spans` | GET | Generic query with `?category=Profile` |
| `/api/v4/state-spans/{id}` | GET | Get specific span by ID |
| `/api/v4/state-spans` | POST | Create manual state span |
| `/api/v4/state-spans/{id}` | PUT | Update state span |
| `/api/v4/state-spans/{id}` | DELETE | Delete state span |

### Query Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `category` | enum | Filter by category (Profile, Override, etc.) |
| `state` | string | Filter by state value |
| `from` | long | Start time (epoch ms) |
| `to` | long | End time (epoch ms) |
| `source` | string | Filter by data source |
| `active` | bool | Filter for active spans only |
| `count` | int | Limit results (default 100) |
| `skip` | int | Pagination offset |

## StateSpan Categories

| Category | States | Description |
|----------|--------|-------------|
| `Profile` | Active | Active profile name in metadata |
| `Override` | None, Custom | Override status (details in metadata) |
| `TempBasal` | Active, Cancelled | Temporary basal rate |
| `PumpMode` | Automatic, Limited, Manual, Boost, EaseOff, Sleep, Exercise, Suspended, Off | Pump operational mode |
| `PumpConnectivity` | Connected, Disconnected, Removed, BluetoothOff | Pump connection status |
| `Sleep` | (user-defined) | User-annotated sleep periods |
| `Exercise` | (user-defined) | User-annotated activity periods |
| `Illness` | (user-defined) | Illness periods (affects insulin sensitivity) |
| `Travel` | (user-defined) | Travel/timezone change periods |

## StateSpan Model

```csharp
public class StateSpan
{
    public string? Id { get; set; }
    public StateSpanCategory Category { get; set; }
    public string? State { get; set; }
    public long StartMills { get; set; }
    public long? EndMills { get; set; }        // null = active
    public string? Source { get; set; }
    public Dictionary<string, object>? Metadata { get; set; }
    public string? OriginalId { get; set; }
    public Guid? CanonicalId { get; set; }     // For deduplication
    public string[]? Sources { get; set; }     // Multi-source merge
    public DateTime? CreatedAt { get; set; }
    public DateTime? UpdatedAt { get; set; }
    public bool IsActive => !EndMills.HasValue;
}
```

## Profile StateSpan Usage

### ChartDataController Integration

Profile state spans are integrated into chart data responses:

```csharp
// ChartDataController.cs:171-172
var profileSpans = await _stateSpanRepository.GetByCategory(
    StateSpanCategory.Profile, startTime, endTime, cancellationToken);

// Returned in ChartDataResponse:
ProfileSpans = profileSpans.ToList()
```

This provides profile change history alongside glucose/basal data for visualization.

### ProfileSwitch Treatment Processing

```csharp
// ChartDataController.cs:237-242
var profileSwitchTreatments = treatments
    .Where(t => t.EventType == "Profile Switch")
    .ToList();

_profileService.UpdateTreatments(
    profileSwitchTreatments,
    tempBasalTreatments
);
```

## Answers to Research Questions

### 1. Does V4 API have profile-specific endpoints beyond V3?

**Yes.** V4 provides:
- `/api/v4/state-spans/profiles` - Profile activation history
- `/api/v4/chart-data` - Returns ProfileSpans in response
- Generic StateSpan CRUD with `category=Profile`

V3 only provides `/api/v3/profile` for profile document CRUD, not activation history.

### 2. Any state-span tracking for profile activations?

**Yes.** The `StateSpanCategory.Profile` tracks:
- When each profile became active
- Which profile is currently active (`EndMills = null`)
- Profile name in metadata
- Source system that activated the profile

### 3. Any proposal for standardized profile change history?

**Partially.** Nocturne's StateSpan model provides a foundation:
- Time-ranged spans with start/end
- Metadata for profile details
- CanonicalId for deduplication across sources
- Sources array for multi-source merge

However, this is **Nocturne-specific** (GAP-NOCTURNE-001). cgm-remote-monitor has no equivalent.

## V4 vs V3 Comparison

### Profile Operations

| Operation | V3 | V4 | Notes |
|-----------|-----|-----|-------|
| Get current profile | ✅ GET `/api/v3/profile?count=1` | ✅ Same | V4 can also use StateSpan |
| Profile history | ❌ | ✅ `/state-spans/profiles` | V4 only |
| Create profile | ✅ POST `/api/v3/profile` | ✅ Same | |
| Update profile | ✅ PUT `/api/v3/profile/{id}` | ✅ Same | |
| Delete profile | ✅ DELETE `/api/v3/profile/{id}` | ✅ Same | |
| Profile activation events | ❌ | ✅ StateSpan | V4 only |

### Override Operations

| Operation | V3 | V4 | Notes |
|-----------|-----|-----|-------|
| Get treatments | ✅ `/api/v3/treatments?eventType=...` | ✅ Same | |
| Override history | ❌ | ✅ `/state-spans/overrides` | V4 only |
| Active override | Query treatments | ✅ `?active=true` | V4 simpler |

## Gaps Identified

### GAP-V4-001: StateSpan API Not Standardized

**Description**: Nocturne's V4 StateSpan API is proprietary and not part of any Nightscout standard. Other implementations cannot consume or produce compatible data.

**Affected Systems**: Loop, Trio, AAPS, cgm-remote-monitor

**Impact**: V4 features not portable across ecosystem.

**Remediation**: Propose StateSpan as RFC for Nightscout v4 API standard.

### GAP-V4-002: Profile Activation Not in V3

**Description**: V3 API has no mechanism to query profile activation history. Only profile documents can be queried, not when they were activated.

**Affected Systems**: All using V3 API

**Impact**: Cannot build profile timeline without StateSpan.

**Remediation**: Add profile activation events to V3 or migrate to V4.

## Requirements

### REQ-V4-001: StateSpan Portability

**Statement**: Future Nightscout API versions SHOULD include StateSpan-like time-range tracking for profiles and overrides.

**Rationale**: Enables profile change history and override tracking across implementations.

**Verification**: API spec includes time-ranged state tracking.

### REQ-V4-002: Profile Activation Events

**Statement**: Servers SHOULD track profile activation events with timestamps.

**Rationale**: Enables retrospective analysis of which profile was active at any point.

**Verification**: Query profile history returns activation timestamps.

## Source Files Analyzed

| File | Description |
|------|-------------|
| `Controllers/V4/StateSpansController.cs` | Full StateSpan CRUD API |
| `Core/Nocturne.Core.Models/StateSpan.cs` | StateSpan model |
| `Core/Nocturne.Core.Models/StateSpanEnums.cs` | Category and state enums |
| `Controllers/V4/ChartDataController.cs:171-172` | ProfileSpans in chart data |
| `Services/StateSpanService.cs` | StateSpan business logic |

## V4 Controller Summary

| Controller | Profile/Override Relevance |
|------------|---------------------------|
| StateSpansController | ✅ Primary profile/override state tracking |
| ChartDataController | ✅ Returns ProfileSpans in response |
| RetrospectiveController | Uses ProfileService for calculations |
| PredictionController | Takes optional profileId parameter |
| UISettingsController | Alarm profiles (different concept) |
| TreatmentsController | Standard treatment operations |

---

*Analysis Date: 2026-01-30*
*OQ-010 Research Queue: Item #9 of 7*
