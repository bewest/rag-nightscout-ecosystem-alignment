# Nocturne Core Models

> **Source**: `externals/nocturne/src/Core/Nocturne.Core.Models/`  
> **Last Updated**: 2026-01-29

Field mappings for Nocturne's core domain models compared to cgm-remote-monitor and Nightscout API specs.

---

## Entry Model

**Source**: `src/Core/Nocturne.Core.Models/Entry.cs`

### Field Mapping

| Nocturne Field | Type | NS Equivalent | Notes |
|----------------|------|---------------|-------|
| `Id` | string? | `_id` | MongoDB ObjectId format preserved |
| `Identifier` | string? | `identifier` | V3 alias for Id |
| `Mills` | long | `date` | **Canonical timestamp** (Unix ms) |
| `Date` | DateTime? | N/A | Computed from Mills |
| `DateString` | string? | `dateString` | ISO-8601, computed |
| `Sgv` | int? | `sgv` | Sensor glucose value (mg/dL) |
| `Mbg` | double? | `mbg` | Manual blood glucose |
| `Direction` | string? | `direction` | Trend arrow |
| `Noise` | int? | `noise` | Signal noise level (0-4) |
| `Device` | string? | `device` | Source device identifier |
| `Type` | string? | `type` | Entry type (sgv, mbg, cal) |
| `SrvModified` | long? | `srvModified` | V3 server timestamp |
| `SrvCreated` | long? | `srvCreated` | V3 created timestamp |
| `Subject` | string? | `subject` | V3 owner subject |
| `UtcOffset` | int? | `utcOffset` | Timezone offset (minutes) |

### Key Patterns

1. **Mills-first**: `Mills` is the source of truth; `Date`/`DateString` are computed
2. **V3 compatibility**: `Identifier`, `SrvModified`, `Subject` for V3 API
3. **Original ID preservation**: Keeps MongoDB `_id` format for migration

---

## Treatment Model

**Source**: `src/Core/Nocturne.Core.Models/Treatment.cs`

### Field Mapping

| Nocturne Field | Type | NS Equivalent | Notes |
|----------------|------|---------------|-------|
| `Id` | string? | `_id` | MongoDB ObjectId format |
| `Identifier` | string? | `identifier` | V3 alias for Id |
| `SrvModified` | long? | `srvModified` | V3 server timestamp |
| `Mills` | long | `date`/`mills` | Unix ms timestamp |
| `EventType` | string? | `eventType` | Treatment type |
| `Carbs` | double? | `carbs` | Carbohydrates (g) |
| `Insulin` | double? | `insulin` | Insulin (units) |
| `Duration` | double? | `duration` | Duration (**minutes**) |
| `Glucose` | double? | `glucose` | BG value at time of entry |
| `GlucoseType` | string? | `glucoseType` | Finger/Sensor |
| `Notes` | string? | `notes` | Free-text notes |
| `EnteredBy` | string? | `enteredBy` | Source app/user |
| `Reason` | string? | `reason` | Override/profile switch reason |
| `TargetTop` | double? | `targetTop` | Override target ceiling |
| `TargetBottom` | double? | `targetBottom` | Override target floor |
| `Percent` | double? | `percent` | Temp basal/override percent |
| `Absolute` | double? | `absolute` | Temp basal absolute rate |
| `Rate` | double? | `rate` | Alias for absolute |
| `PumpId` | string? | `pumpId` | Pump-assigned ID |
| `UtcOffset` | int? | `utcOffset` | Timezone offset (minutes) |

### EventType Mappings

| eventType | Nocturne | cgm-remote-monitor | Loop | AAPS |
|-----------|----------|-------------------|------|------|
| `Correction Bolus` | ✅ | ✅ | ✅ | ✅ |
| `Meal Bolus` | ✅ | ✅ | ✅ | ✅ |
| `Carb Correction` | ✅ | ✅ | ❌ | ✅ |
| `Temp Basal` | ✅ | ✅ | ✅ | ✅ |
| `Temporary Override` | ✅ | ✅ | ✅ | ❌ |
| `Profile Switch` | ✅ | ✅ | ❌ | ✅ |
| `Exercise` | ✅ | ✅ | ❌ | ✅ (via Trio) |
| `Site Change` | ✅ | ✅ | ❌ | ✅ |
| `Sensor Start` | ✅ | ✅ | ❌ | ✅ |
| `Note` | ✅ | ✅ | ✅ | ✅ |
| `Announcement` | ✅ | ✅ | ❌ | ✅ |

---

## DeviceStatus Model

**Source**: `src/Core/Nocturne.Core.Models/DeviceStatus.cs`

### Field Mapping

| Nocturne Field | Type | NS Equivalent | Notes |
|----------------|------|---------------|-------|
| `Id` | string? | `_id` | MongoDB ObjectId |
| `Mills` | long | `mills` | Unix ms timestamp |
| `Device` | string? | `device` | Device identifier |
| `Pump` | object? | `pump` | Pump status (nested) |
| `Loop` | object? | `loop` | Loop status (iOS Loop format) |
| `OpenAps` | object? | `openaps` | OpenAPS status (oref format) |
| `Uploader` | object? | `uploader` | Uploader status |
| `Uploading` | object? | `uploading` | Upload metadata |

### Controller Detection

Nocturne uses the same field-based detection as cgm-remote-monitor:

| Field Present | Controller |
|---------------|------------|
| `loop` | Loop (iOS) |
| `openaps` | AAPS/Trio/oref0 |
| `pump` only | Pump-only upload |

---

## Profile Model

**Source**: `src/Core/Nocturne.Core.Models/Profile.cs`

### Field Mapping

| Nocturne Field | Type | NS Equivalent | Notes |
|----------------|------|---------------|-------|
| `Id` | string? | `_id` | MongoDB ObjectId |
| `DefaultProfile` | string? | `defaultProfile` | Active profile name |
| `StartDate` | DateTime? | `startDate` | Profile activation time |
| `Mills` | long | `mills` | Unix ms timestamp |
| `Store` | Dictionary | `store` | Profile definitions |
| `Units` | string? | `units` | mg/dL or mmol/L |

### Profile Store Entry

| Field | Type | Notes |
|-------|------|-------|
| `Timezone` | string | IANA timezone (e.g., "America/Los_Angeles") |
| `Dia` | double | Duration of insulin action (hours) |
| `CarbRatio` | array | Time-based carb ratios |
| `Sens` | array | Time-based sensitivity factors |
| `Basal` | array | Time-based basal rates |
| `TargetLow` | array | Time-based target low |
| `TargetHigh` | array | Time-based target high |

---

## Food Model

**Source**: `src/Core/Nocturne.Core.Models/Food.cs`

### Field Mapping

| Nocturne Field | Type | NS Equivalent | Notes |
|----------------|------|---------------|-------|
| `Id` | string? | `_id` | MongoDB ObjectId |
| `Name` | string? | `name` | Food name |
| `Category` | string? | `category` | Food category |
| `Carbs` | double? | `carbs` | Carbohydrates (g) |
| `Protein` | double? | `protein` | Protein (g) |
| `Fat` | double? | `fat` | Fat (g) |
| `Calories` | double? | `calories` | Calories |
| `Gi` | double? | `gi` | Glycemic index |
| `ServingSize` | string? | `servingSize` | Serving description |

---

## Unit Conventions

| Field Type | Nocturne Unit | Notes |
|------------|---------------|-------|
| Timestamp | milliseconds | Unix epoch ms |
| Duration | minutes | Consistent with NS |
| utcOffset | minutes | Consistent with NS |
| Glucose (mg/dL) | mg/dL | Display unit varies |
| Insulin | units | Standard IU |
| Carbs | grams | Standard g |

**Note**: Nocturne follows cgm-remote-monitor conventions for units, avoiding the issues documented in GAP-TREAT-002 and GAP-TZ-004.

---

## Cross-References

- [cgm-remote-monitor Models](../cgm-remote-monitor/)
- [AAPS NSClient Schema](../aaps/nsclient-schema.md)
- [Duration/utcOffset Analysis](../../docs/10-domain/duration-utcoffset-unit-analysis.md)
- [OpenAPI Specs](../../specs/openapi/)
