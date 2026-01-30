# Nocturne V2 DData Endpoint Analysis

> **OQ-010 Extended API #8**  
> **Date**: 2026-01-30  
> **Purpose**: Verify DData combined response matches Loop/AAPS expectations

## Executive Summary

| Aspect | cgm-remote-monitor | Nocturne | Parity |
|--------|-------------------|----------|--------|
| Endpoint exists | ✅ `/api/v2/ddata` | ✅ `/api/v2/ddata` | ✅ |
| Core collections | ✅ All 8 | ✅ All 8 | ✅ |
| `lastProfileFromSwitch` | ✅ Populated | ❌ **Missing** | ⚠️ **GAP** |
| `devicestatus.loop` | ✅ Raw storage | ✅ Typed model | ✅ |
| `devicestatus.openaps` | ✅ Raw storage | ✅ Typed model | ✅ |
| Filtered treatment lists | ✅ Computed | ✅ Computed | ✅ |

**Overall Parity: HIGH** - One missing field (`lastProfileFromSwitch`).

---

## Endpoint Comparison

### cgm-remote-monitor

**Location:** `lib/data/endpoints.js`, `lib/api2/index.js`

**Routes:**
- `GET /api/v2/ddata` - Current data
- `GET /api/v2/ddata/at/:at` - Data at specific timestamp

### Nocturne

**Location:** `Controllers/V2/DDataController.cs`

**Routes:**
- `GET /api/v2/ddata` - Current data
- `GET /api/v2/ddata/at/{timestamp}` - Data at specific timestamp
- `GET /api/v2/ddata/raw` - Raw data without filtering

---

## Response Field Comparison

### Core Collections

| Field | cgm-remote-monitor | Nocturne | Notes |
|-------|-------------------|----------|-------|
| `sgvs` | ✅ Array | ✅ `List<Entry>` | Glucose values |
| `treatments` | ✅ Array | ✅ `List<Treatment>` | All treatments |
| `mbgs` | ✅ Array | ✅ `List<Entry>` | Meter BG |
| `cals` | ✅ Array | ✅ `List<Entry>` | Calibrations |
| `profiles` | ✅ Array | ✅ `List<Profile>` | Profile documents |
| `devicestatus` | ✅ Array | ✅ `List<DeviceStatus>` | Device status |
| `food` | ✅ Array | ✅ `List<Food>` | Food database |
| `activity` | ✅ Array | ✅ `List<Activity>` | Activity records |
| `dbstats` | ✅ Object | ✅ `DbStats` | DB statistics |
| `lastUpdated` | ✅ Number | ✅ `long` | Timestamp |

### Additional Fields

| Field | cgm-remote-monitor | Nocturne | Notes |
|-------|-------------------|----------|-------|
| `lastProfileFromSwitch` | ✅ Profile object | ❌ **Missing** | **GAP-API-012** |
| `cal` | ✅ Latest cal | ✅ `Entry?` | Latest calibration |
| `inRetroMode` | ❌ | ✅ `bool?` | Nocturne addition |
| `sitechangeTreatments` | ❌ | ✅ Filtered list | Nocturne addition |
| `insulinchangeTreatments` | ❌ | ✅ Filtered list | Nocturne addition |
| `batteryTreatments` | ❌ | ✅ Filtered list | Nocturne addition |
| `sensorTreatments` | ❌ | ✅ Filtered list | Nocturne addition |
| `combobolusTreatments` | ❌ | ✅ Filtered list | Nocturne addition |
| `profileTreatments` | ❌ | ✅ Filtered list | Nocturne addition |
| `tempbasalTreatments` | ❌ | ✅ Filtered list | Nocturne addition |
| `tempTargetTreatments` | ❌ | ✅ Filtered list | Nocturne addition |

**Note:** Nocturne includes additional pre-filtered treatment lists for convenience.

---

## lastProfileFromSwitch Gap

### cgm-remote-monitor Behavior

```javascript
// lib/data/dataloader.js:364-374
ddata.lastProfileFromSwitch = null;
var now = new Date().getTime();
for (var p = 0; p < results.length; p++) {
    var pdate = new Date(results[p].created_at).getTime();
    if (pdate < now) {
        ddata.lastProfileFromSwitch = results[p].profile;
        break;
    }
}
```

**Logic:**
1. Load Profile Switch treatments (eventType: 'Profile Switch', duration: 0)
2. Find the latest one before current time
3. Extract the `profile` field from that treatment
4. Assign to `ddata.lastProfileFromSwitch`

### Nocturne Behavior

**Field not present in DData.cs model.**

`profileTreatments` is populated but `lastProfileFromSwitch` is not computed.

### Impact

- Loop uses `lastProfileFromSwitch` for active profile determination
- Without it, clients must compute from `profileTreatments` themselves
- Low impact since `profileTreatments` provides the source data

### GAP-API-012: lastProfileFromSwitch Missing

**Remediation:**
1. Add `lastProfileFromSwitch` field to `DData.cs`
2. In DDataService, find latest Profile Switch before request time
3. Extract `profile` field from that treatment

---

## DeviceStatus Structure Comparison

### Loop Status (`devicestatus.loop`)

| Field | cgm-remote-monitor | Nocturne | Notes |
|-------|-------------------|----------|-------|
| `iob` | ✅ Object | ✅ `LoopIob` | Insulin on board |
| `cob` | ✅ Object | ✅ `LoopCob` | Carbs on board |
| `predicted` | ✅ Object | ✅ `LoopPredicted` | Predictions |
| `recommendedBolus` | ✅ Number | ✅ `double?` | Bolus recommendation |
| `enacted` | ✅ Object | ✅ `LoopEnacted` | Enacted changes |
| `failureReason` | ✅ String | ✅ `string?` | Error message |
| `rileylinks` | ✅ Array | ✅ `List<RileyLinkStatus>` | RileyLink status |
| `name` | ✅ String | ✅ `string?` | Loop name |
| `version` | ✅ String | ✅ `string?` | Loop version |
| `timestamp` | ✅ String | ✅ `string?` | ISO timestamp |
| `automaticDoseRecommendation` | ✅ Object | ✅ Typed | Auto dose |
| `currentCorrectionRange` | ✅ Object | ✅ `CorrectionRange` | Target range |

**Parity: ✅ Full** - All Loop fields present in typed model.

### OpenAPS Status (`devicestatus.openaps`)

| Field | cgm-remote-monitor | Nocturne | Notes |
|-------|-------------------|----------|-------|
| `iob` | ✅ Object | ✅ `OpenApsIob` | Insulin on board |
| `suggested` | ✅ Object | ✅ `OpenApsSuggested` | Suggested action |
| `enacted` | ✅ Object | ✅ `OpenApsEnacted` | Enacted action |
| `status` | ✅ Object | ✅ `OpenApsStatus` | Status info |

**Parity: ✅ Full** - All OpenAPS fields present in typed model.

### Device Type Fields

Both systems support the same device types:

```javascript
// cgm-remote-monitor: lib/data/ddata.js:7
var DEVICE_TYPE_FIELDS = ['uploader', 'pump', 'openaps', 'loop', 'xdripjs'];
```

```csharp
// Nocturne: DeviceStatus.cs
public UploaderStatus? Uploader { get; set; }
public PumpStatus? Pump { get; set; }
public OpenApsStatus? OpenAps { get; set; }
public LoopStatus? Loop { get; set; }
public XDripJsStatus? XDripJs { get; set; }
```

**Additional Nocturne fields:** `RadioAdapter`, `Connect`, `Override`, `Cgm`, `Meter`, `InsulinPen`, `MmTune`

---

## Filtering Behavior

### cgm-remote-monitor

- Returns last 10 devicestatus entries per device/type
- Filters by timestamp range
- Transforms `uploaderBattery` to `uploader.battery`

### Nocturne

- Returns last 10 entries per device/type combination
- Filters entries ≤ requested timestamp
- Pre-computes filtered treatment lists by eventType
- Filters out temporary profile switches (containing "@@@@@") from profiles

---

## Gap Summary

### GAP-API-012: lastProfileFromSwitch Missing in Nocturne DData

**Description**: The `lastProfileFromSwitch` field is not populated in Nocturne's DData response. This field contains the profile object from the most recent Profile Switch treatment.

**Affected Systems**: Loop, Nightguard, any client using lastProfileFromSwitch

**Evidence**:
- cgm-remote-monitor: `lib/data/dataloader.js:364-374` - Computes lastProfileFromSwitch
- Nocturne: `DData.cs` - Field not present

**Impact**: Low - Clients can compute from `profileTreatments` list

**Remediation**:
1. Add `LastProfileFromSwitch` property to `DData.cs`
2. In `DDataService.GetDData()`, find latest Profile Switch treatment
3. Extract and assign the `profile` field

**Status**: Open - Low Priority

---

## Source File References

### cgm-remote-monitor

| File | Purpose |
|------|---------|
| `lib/data/ddata.js:11-22` | DData structure initialization |
| `lib/data/ddata.js:7` | DEVICE_TYPE_FIELDS constant |
| `lib/data/dataloader.js:364-374` | lastProfileFromSwitch computation |
| `lib/api2/index.js:15` | Endpoint mount |
| `lib/data/endpoints.js` | Endpoint handler |

### Nocturne

| File | Purpose |
|------|---------|
| `Core/Models/DData.cs` | DData response model (131 lines) |
| `Core/Models/DeviceStatus.cs:349-440` | LoopStatus typed model |
| `Core/Models/DeviceStatus.cs:82-83` | OpenApsStatus property |
| `Controllers/V2/DDataController.cs` | Endpoint controller |
| `Services/DDataService.cs` | Data retrieval logic |

---

## Recommendations

### For Nocturne

1. **Add lastProfileFromSwitch** - Compute from profileTreatments for parity
2. **Document additional fields** - Pre-filtered treatment lists are useful additions

### For Clients

1. **Use profileTreatments as fallback** - If lastProfileFromSwitch missing, compute locally
2. **Handle typed models** - Nocturne returns typed objects vs raw JSON

---

## Conclusion

**High parity achieved.** The V2 DData endpoint in Nocturne provides all core collections and devicestatus structures that Loop and AAPS expect. The only missing field is `lastProfileFromSwitch`, which has low impact since clients can compute it from the available `profileTreatments` list.

Nocturne actually provides **enhanced functionality** with pre-filtered treatment lists (sitechangeTreatments, tempbasalTreatments, etc.) that reduce client-side processing.
