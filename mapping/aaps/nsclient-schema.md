# AAPS NSClient Upload Schema

> **Source**: `externals/AndroidAPS/core/nssdk/src/main/kotlin/app/aaps/core/nssdk/`  
> **Version**: master @ 796d36ef0df2  
> **Last Updated**: 2026-01-28

This document describes all fields AAPS uploads to Nightscout via the NSClient SDK.

---

## Collections

| Collection | Remote Model | Local Models |
|------------|--------------|--------------|
| `treatments` | `RemoteTreatment.kt` | `NSBolus`, `NSCarbs`, `NSTemporaryBasal`, `NSProfileSwitch`, etc. |
| `entries` | `RemoteEntry.kt` | `NSSgvV3` |
| `devicestatus` | `RemoteDeviceStatus.kt` | (direct) |
| `food` | `RemoteFood.kt` | `NSFood` |
| `profile` | `RemoteProfileStore.kt` | (direct) |

---

## Treatments Schema

**Source**: `remotemodel/RemoteTreatment.kt:17-102`

### Core Fields (All Treatment Types)

| Field | Type | Description | Notes |
|-------|------|-------------|-------|
| `identifier` | String? | Server-assigned document ID | Don't create client-side |
| `date` | Long? | Timestamp (epoch ms) | Primary timestamp |
| `mills` | Long? | Timestamp (epoch ms) | Legacy |
| `timestamp` | Long? | Timestamp (epoch ms) | Alternative |
| `created_at` | String? | ISO-8601 timestamp | Legacy API |
| `utcOffset` | Long? | UTC offset in **minutes** | Auto-parsed from date |
| `app` | String? | Source application | e.g., "AAPS" |
| `device` | String? | Device identifier | Includes serial if safe |
| `eventType` | EventType | Treatment type | See EventType enum |
| `enteredBy` | String? | Who created | e.g., "AndroidAPS" |
| `notes` | String? | Description | Free text |
| `isValid` | Boolean? | Deletion flag | Server-set for deleted docs |
| `isReadOnly` | Boolean? | Immutability flag | Locks document forever |

### Server-Managed Fields

| Field | Type | Description |
|-------|------|-------------|
| `srvCreated` | Long? | Server insert timestamp (ms) |
| `srvModified` | Long? | Server modification timestamp (ms) |
| `subject` | String? | Security subject (from token) |
| `modifiedBy` | String? | Last modifier subject |

### Bolus Fields

| Field | Type | Description | Used By |
|-------|------|-------------|---------|
| `insulin` | Double? | Insulin amount (units) | All bolus types |
| `type` | String? | Bolus type: `NORMAL`, `SMB`, `FAKE_EXTENDED` | Correction Bolus |
| `isSMB` | Boolean? | Is Super Micro Bolus | SMB detection |
| `isBasalInsulin` | Boolean? | Is basal insulin | Bolus classification |
| `pumpId` | Long? | Pump record ID | Deduplication |
| `pumpType` | String? | Pump driver name | e.g., `ACCU_CHEK_INSIGHT_BLUETOOTH` |
| `pumpSerial` | String? | Pump serial number | Deduplication |
| `bolusCalculatorResult` | String? | JSON of wizard calc | Bolus Wizard |

### Carbs Fields

| Field | Type | Description | Unit |
|-------|------|-------------|------|
| `carbs` | Double? | Carbohydrate amount | grams |
| `protein` | Int? | Protein amount | grams |
| `fat` | Int? | Fat amount | grams |
| `duration` | Long? | eCarbs duration | **minutes** |
| `durationInMilliseconds` | Long? | eCarbs duration | milliseconds |

### Temp Basal Fields

| Field | Type | Description | Unit |
|-------|------|-------------|------|
| `rate` | Double? | Absolute basal rate | U/hr |
| `absolute` | Double? | Absolute rate value | U/hr |
| `percent` | Double? | Percentage change | % |
| `duration` | Long? | Duration | **minutes** |
| `durationInMilliseconds` | Long? | Duration | milliseconds |

### Temporary Target Fields

| Field | Type | Description | Unit |
|-------|------|-------------|------|
| `targetTop` | Double? | Upper target limit | mg/dL or mmol/L |
| `targetBottom` | Double? | Lower target limit | mg/dL or mmol/L |
| `duration` | Long? | Duration | **minutes** |
| `reason` | String? | Target reason | e.g., "Exercise" |

### Profile Switch Fields

| Field | Type | Description |
|-------|------|-------------|
| `profile` | String? | Profile name |
| `profileJson` | String? | Full profile JSON |
| `timeshift` | Long? | Time shift |
| `percentage` | Int? | Percentage adjustment |
| `originalProfileName` | String? | Original profile (effective switch) |
| `originalPercentage` | Int? | Original percentage |
| `originalDuration` | Long? | Original duration |
| `originalEnd` | Long? | Original end time |

### Glucose Fields

| Field | Type | Description |
|-------|------|-------------|
| `glucose` | Double? | Current glucose value |
| `glucoseType` | String? | Source: `Sensor`, `Finger`, `Manual` |
| `units` | String? | Units: `mg/dl` or `mmol/l` |

### Extended/Combo Bolus Fields

| Field | Type | Description |
|-------|------|-------------|
| `enteredinsulin` | Double? | Entered insulin (combo) |
| `splitNow` | Int? | Immediate part (%) |
| `splitExt` | Int? | Extended part (%) |
| `relative` | Double? | Relative rate |
| `isEmulatingTempBasal` | Boolean? | Extended as temp basal |
| `extendedEmulated` | RemoteTreatment? | Nested emulated treatment |

### Other Fields

| Field | Type | Description |
|-------|------|-------------|
| `preBolus` | Int? | Minutes before meal |
| `endId` | Long? | ID of ending record |
| `location` | String? | Site location |
| `arrow` | String? | Site arrow |
| `mode` | String? | Running mode |
| `autoForced` | Boolean? | Auto-forced mode |
| `reasons` | String? | Multiple reasons |
| `isAnnouncement` | Boolean? | Is announcement |

---

## EventType Enum

**Source**: `localmodel/treatment/EventType.kt:6-43`

| Enum Value | Nightscout String | Category |
|------------|-------------------|----------|
| `CANNULA_CHANGE` | "Site Change" | Site Management |
| `INSULIN_CHANGE` | "Insulin Change" | Site Management |
| `PUMP_BATTERY_CHANGE` | "Pump Battery Change" | Site Management |
| `SENSOR_CHANGE` | "Sensor Change" | CGM |
| `SENSOR_STARTED` | "Sensor Start" | CGM |
| `SENSOR_STOPPED` | "Sensor Stop" | CGM |
| `FINGER_STICK_BG_VALUE` | "BG Check" | Glucose |
| `EXERCISE` | "Exercise" | Activity |
| `ANNOUNCEMENT` | "Announcement" | Notes |
| `NOTE` | "Note" | Notes |
| `QUESTION` | "Question" | Notes |
| `APS_OFFLINE` | "OpenAPS Offline" | APS |
| `DAD_ALERT` | "D.A.D. Alert" | Alerts |
| `CARBS_CORRECTION` | "Carb Correction" | Carbs |
| `BOLUS_WIZARD` | "Bolus Wizard" | Bolus |
| `CORRECTION_BOLUS` | "Correction Bolus" | Bolus |
| `MEAL_BOLUS` | "Meal Bolus" | Bolus |
| `COMBO_BOLUS` | "Combo Bolus" | Bolus |
| `SNACK_BOLUS` | "Snack Bolus" | Bolus |
| `TEMPORARY_TARGET` | "Temporary Target" | Targets |
| `TEMPORARY_TARGET_CANCEL` | "Temporary Target Cancel" | Targets |
| `PROFILE_SWITCH` | "Profile Switch" | Profile |
| `TEMPORARY_BASAL` | "Temp Basal" | Basal |
| `TEMPORARY_BASAL_START` | "Temp Basal Start" | Basal |
| `TEMPORARY_BASAL_END` | "Temp Basal End" | Basal |

---

## Entries Schema

**Source**: `remotemodel/RemoteEntry.kt:14-36`

| Field | Type | Description | Notes |
|-------|------|-------------|-------|
| `type` | String | Entry type | `sgv`, `mbg`, `cal` |
| `sgv` | Double? | Glucose value | SGV only |
| `date` | Long? | Timestamp (epoch ms) | Required |
| `dateString` | String? | ISO-8601 timestamp | Redundant with date |
| `direction` | String? | Trend direction | e.g., `Flat`, `FortyFiveUp` |
| `device` | String? | Source device | |
| `identifier` | String? | Document ID | Server-assigned |
| `utcOffset` | Long? | UTC offset | **minutes** |
| `noise` | Double? | Noise level | 0 or 1 |
| `filtered` | Double? | Filtered raw value | CGM raw |
| `unfiltered` | Double? | Unfiltered raw value | CGM raw |
| `units` | String? | Glucose units | `mg/dl` or `mmol/l` |
| `app` | String? | Source app | |
| `isValid` | Boolean? | Deletion flag | |
| `isReadOnly` | Boolean? | Immutability flag | |

---

## DeviceStatus Schema

**Source**: `remotemodel/RemoteDeviceStatus.kt:13-77`

### Top-Level Fields

| Field | Type | Description |
|-------|------|-------------|
| `identifier` | String? | Document ID |
| `date` | Long? | Timestamp (epoch ms) |
| `created_at` | String? | ISO-8601 timestamp |
| `device` | String? | Device identifier |
| `uploaderBattery` | Int? | Phone battery % |
| `isCharging` | Boolean? | Phone charging |
| `app` | String? | Source app |

### Pump Object

| Field | Type | Description |
|-------|------|-------------|
| `pump.clock` | String? | Pump clock (ISO) |
| `pump.reservoir` | Double? | Reservoir level (units) |
| `pump.reservoir_display_override` | String? | Display override |
| `pump.battery.percent` | Int? | Pump battery % |
| `pump.battery.voltage` | Double? | Pump battery voltage |
| `pump.status.status` | String? | Pump status |
| `pump.status.timestamp` | String? | Status timestamp |
| `pump.extended` | JsonObject? | Driver-specific data |

### OpenAPS Object

| Field | Type | Description |
|-------|------|-------------|
| `openaps.suggested` | JsonObject? | Suggested action |
| `openaps.enacted` | JsonObject? | Enacted action |
| `openaps.iob` | JsonObject? | IOB data |

### Configuration Object

| Field | Type | Description |
|-------|------|-------------|
| `configuration.pump` | String? | Pump type |
| `configuration.version` | String? | AAPS version |
| `configuration.insulin` | Int? | Insulin type |
| `configuration.aps` | String? | APS algorithm |
| `configuration.sensitivity` | Int? | Sensitivity algorithm |
| `configuration.smoothing` | String? | Smoothing algorithm |

---

## Unit Conventions

| Field | AAPS Unit | Nightscout Unit | Conversion |
|-------|-----------|-----------------|------------|
| `duration` | minutes or ms | minutes | ms ÷ 60000 |
| `durationInMilliseconds` | milliseconds | N/A | AAPS-specific |
| `utcOffset` | minutes | minutes | None |
| `timestamp/date` | epoch ms | epoch ms | None |

**Important**: AAPS provides both `duration` (minutes) and `durationInMilliseconds` for some treatment types. When uploading, `duration` is in **minutes** for Nightscout compatibility.

---

## Related Gaps

| Gap ID | Description |
|--------|-------------|
| GAP-TREAT-002 | Duration unit inconsistency (ms vs minutes) |
| GAP-TREAT-003 | No explicit SMB event type (uses `type: "SMB"` field) |
| GAP-SYNC-001 | `pumpId`/`pumpSerial` deduplication logic |

---

## Cross-References

- [Terminology Matrix](../cross-project/terminology-matrix.md) - Field name mappings
- [Treatment Sync Assertions](../../conformance/assertions/treatment-sync.yaml) - Validation tests
- [Nightscout API Spec](../../specs/openapi/aid-treatments-2025.yaml) - OpenAPI schema
