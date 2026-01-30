# Nocturne eventType Handling Analysis

> **OQ-010 Extended API #7**  
> **Date**: 2026-01-30  
> **Purpose**: Compare eventType normalization between cgm-remote-monitor and Nocturne

## Executive Summary

| Aspect | cgm-remote-monitor | Nocturne | Parity |
|--------|-------------------|----------|--------|
| Storage Type | String | String | ✅ |
| Case-Sensitive | Yes | Yes | ✅ |
| Validation | None | None (enum advisory) | ✅ |
| Unknown Types | Accepted | Accepted | ✅ |
| Immutability | Immutable after create | Not enforced | ⚠️ Different |
| Defined Types | ~25 documented | 28 in enum | ✅ Similar |

**Overall Parity: HIGH** - Both systems accept any string value without validation.

---

## cgm-remote-monitor Behavior

### Storage

- **Type**: String (no constraints)
- **Database**: MongoDB document field
- **No validation on insert/update**

### Case Sensitivity

**Yes, case-sensitive.** Exact string matching used throughout:

```javascript
// lib/server/treatments.js:239
if (obj.eventType === 'Announcement')
```

### Immutability

eventType is **immutable** after creation:

```javascript
// lib/api3/generic/update/validate.js:21
const immutable = ['identifier', 'date', 'utcOffset', 'eventType', 'device', 'app', ...
```

Attempting to change eventType on an existing treatment returns an error.

### Unknown Types

**Accepted without validation.** No whitelist checking - any string value stored as-is.

### Deduplication Role

eventType is part of document identity calculation:

```javascript
// lib/api3/shared/operationTools.js:102
key += '_' + doc.eventType
```

### Known eventTypes

Documented in swagger.yaml and careportal.js:

| eventType | Description |
|-----------|-------------|
| `BG Check` | Blood glucose check |
| `Snack Bolus` | Snack bolus |
| `Meal Bolus` | Meal bolus |
| `Correction Bolus` | Correction bolus |
| `Carb Correction` | Carb correction |
| `Combo Bolus` | Extended/dual-wave bolus |
| `Announcement` | Announcement |
| `Note` | Note |
| `Question` | Question |
| `Exercise` | Exercise event |
| `Site Change` | Pump site change |
| `Sensor Start` | CGM sensor start |
| `Sensor Change` | CGM sensor insert |
| `Sensor Stop` | CGM sensor stop |
| `Pump Battery Change` | Pump battery change |
| `Insulin Change` | Insulin cartridge change |
| `Temp Basal Start` | Temp basal start |
| `Temp Basal End` | Temp basal end |
| `Temp Basal` | Generic temp basal |
| `Profile Switch` | Profile switch |
| `D.A.D. Alert` | Diabetes Alert Dog |
| `Temporary Target` | Temporary target |
| `OpenAPS Offline` | OpenAPS offline |
| `Bolus Wizard` | Bolus wizard |

---

## Nocturne Behavior

### Storage

- **Type**: String (nullable, max 255 chars)
- **Database**: PostgreSQL `varchar(255)` column
- **No database-level validation**

```csharp
// TreatmentEntity.cs:29-31
[Column("eventType")]
[MaxLength(255)]
public string? EventType { get; set; }
```

### TreatmentEventType Enum

Nocturne defines an **advisory enum** with 28 types:

```csharp
// TreatmentEventType.cs
[JsonConverter(typeof(JsonStringEnumConverter))]
public enum TreatmentEventType
{
    [EnumMember(Value = "<none>")] None,
    [EnumMember(Value = "BG Check")] BgCheck,
    [EnumMember(Value = "Snack Bolus")] SnackBolus,
    [EnumMember(Value = "Meal Bolus")] MealBolus,
    [EnumMember(Value = "Correction Bolus")] CorrectionBolus,
    [EnumMember(Value = "Carb Correction")] CarbCorrection,
    [EnumMember(Value = "Combo Bolus")] ComboBolus,
    [EnumMember(Value = "Announcement")] Announcement,
    [EnumMember(Value = "Note")] Note,
    [EnumMember(Value = "Question")] Question,
    [EnumMember(Value = "Site Change")] SiteChange,
    [EnumMember(Value = "Sensor Start")] SensorStart,
    [EnumMember(Value = "Sensor Change")] SensorChange,
    [EnumMember(Value = "Sensor Stop")] SensorStop,
    [EnumMember(Value = "Pump Battery Change")] PumpBatteryChange,
    [EnumMember(Value = "Insulin Change")] InsulinChange,
    [EnumMember(Value = "Temp Basal Start")] TempBasalStart,
    [EnumMember(Value = "Temp Basal End")] TempBasalEnd,
    [EnumMember(Value = "Profile Switch")] ProfileSwitch,
    [EnumMember(Value = "D.A.D. Alert")] DadAlert,
    [EnumMember(Value = "Temp Basal")] TempBasal,
    [EnumMember(Value = "Exercise")] Exercise,
    [EnumMember(Value = "OpenAPS Offline")] OpenApsOffline,
    [EnumMember(Value = "Suspend Pump")] SuspendPump,
    [EnumMember(Value = "Resume Pump")] ResumePump,
    [EnumMember(Value = "Bolus Wizard")] BolusWizard,
    [EnumMember(Value = "Calibration")] Calibration,
    [EnumMember(Value = "Transmitter Sensor Insert")] TransmitterSensorInsert,
    [EnumMember(Value = "Pod Change")] PodChange
}
```

**Important**: This enum is for configuration/display purposes. The Treatment model uses `string?` for actual storage.

### Case Sensitivity

**Yes, case-sensitive.** The `JsonStringEnumConverter` performs case-sensitive matching by default.

### Unknown Types

**Accepted without validation.** Treatment.EventType is a plain string - any value passes through:

```csharp
// From GlookoConnectorService - handles unknown types gracefully
EventType = mapping.EventType ?? "unknown"
```

### Immutability

**Not enforced.** Unlike cgm-remote-monitor, Nocturne does not mark eventType as immutable on update.

---

## Type Comparison Matrix

| eventType | cgm-remote-monitor | Nocturne | Notes |
|-----------|-------------------|----------|-------|
| `BG Check` | ✅ | ✅ | |
| `Snack Bolus` | ✅ | ✅ | |
| `Meal Bolus` | ✅ | ✅ | |
| `Correction Bolus` | ✅ | ✅ | |
| `Carb Correction` | ✅ | ✅ | |
| `Combo Bolus` | ✅ | ✅ | |
| `Announcement` | ✅ | ✅ | |
| `Note` | ✅ | ✅ | |
| `Question` | ✅ | ✅ | |
| `Exercise` | ✅ | ✅ | |
| `Site Change` | ✅ | ✅ | |
| `Sensor Start` | ✅ | ✅ | |
| `Sensor Change` | ✅ | ✅ | |
| `Sensor Stop` | ✅ | ✅ | |
| `Pump Battery Change` | ✅ | ✅ | |
| `Insulin Change` | ✅ | ✅ | |
| `Temp Basal Start` | ✅ | ✅ | |
| `Temp Basal End` | ✅ | ✅ | |
| `Temp Basal` | ✅ | ✅ | |
| `Profile Switch` | ✅ | ✅ | |
| `D.A.D. Alert` | ✅ | ✅ | |
| `Temporary Target` | ✅ | ❌ | Not in Nocturne enum |
| `OpenAPS Offline` | ✅ | ✅ | |
| `Bolus Wizard` | ✅ | ✅ | |
| `Suspend Pump` | ❌ | ✅ | Nocturne addition |
| `Resume Pump` | ❌ | ✅ | Nocturne addition |
| `Calibration` | ❌ | ✅ | Nocturne addition |
| `Transmitter Sensor Insert` | ❌ | ✅ | Nocturne addition |
| `Pod Change` | ❌ | ✅ | Nocturne addition |

**Note**: Missing types in enum don't prevent storage - both systems accept any string.

---

## Gaps Identified

### GAP-TREAT-010: eventType Immutability Not Enforced in Nocturne

**Description**: cgm-remote-monitor enforces eventType immutability on update, Nocturne does not.

**Impact**: Low - eventType changes are rare in practice.

**Remediation**: Add eventType to immutable fields in Nocturne update validation.

### GAP-TREAT-011: Temporary Target Type Missing from Nocturne Enum

**Description**: `Temporary Target` is used by AAPS but not defined in Nocturne's TreatmentEventType enum.

**Impact**: Low - unknown types are accepted, just not in enum.

**Remediation**: Add `TemporaryTarget` to TreatmentEventType enum.

---

## Source File References

### cgm-remote-monitor

| File | Purpose |
|------|---------|
| `lib/api3/generic/update/validate.js:21` | eventType immutability |
| `lib/api3/shared/operationTools.js:102` | Dedup key generation |
| `lib/server/treatments.js:239` | Case-sensitive matching |
| `swagger.yaml` | Documented eventTypes |

### Nocturne

| File | Purpose |
|------|---------|
| `Core/Nocturne.Core.Models/TreatmentEventType.cs` | Enum definition (28 types) |
| `Infrastructure/Data/Entities/TreatmentEntity.cs:29-31` | DB column definition |
| `Connectors/Glooko/GlookoConnectorService.cs` | Unknown type handling |

---

## Recommendations

### For Nocturne

1. **Add eventType to immutable fields** - Match cgm-remote-monitor behavior
2. **Add missing enum values** - `Temporary Target`, AAPS-specific types
3. **Consider normalization option** - Trim whitespace, handle common aliases

### For Ecosystem

1. **Document canonical eventTypes** - Create authoritative list in spec
2. **Define case handling** - Recommend case-sensitive or specify normalization
3. **Alias mapping** - Document equivalent types across systems

---

## Conclusion

**High parity achieved.** Both systems:
- Store eventType as plain string
- Accept any value without validation
- Are case-sensitive
- Support the same core 20+ eventTypes

The only behavioral difference is immutability enforcement, which has low practical impact since eventType changes are uncommon.
