# tconnectsync Domain Models

> **Source**: `externals/tconnectsync/tconnectsync/domain/`  
> **Last Updated**: 2026-01-29

Field mappings for tconnectsync's domain models and their transformation to Nightscout format.

---

## Bolus Model

**Source**: `tconnectsync/domain/bolus.py`

### tconnectsync Fields

| Field | Type | Description |
|-------|------|-------------|
| `description` | str | Bolus description text |
| `complete` | bool | Whether bolus completed |
| `request_time` | datetime | When bolus was requested |
| `completion_time` | datetime | When bolus finished |
| `insulin` | float | Actual insulin delivered (units) |
| `requested_insulin` | float | Requested insulin amount |
| `carbs` | int | Carbs entered (grams) |
| `bg` | int | Blood glucose at bolus time |
| `user_override` | bool | User overrode recommendation |
| `extended_bolus` | bool | Extended/combo bolus flag |
| `bolex_completion_time` | datetime | Extended portion completion |
| `bolex_start_time` | datetime | Extended portion start |

### Mapping to Nightscout Treatment

| tconnectsync | Nightscout | Notes |
|--------------|------------|-------|
| `insulin` | `insulin` | Units |
| `carbs` | `carbs` | Grams |
| `bg` | `glucose` | mg/dL |
| `request_time` | `created_at` | ISO-8601 |
| `description` | `notes` | Free text |
| - | `eventType` | `Combo Bolus` (fixed) |
| - | `enteredBy` | `tconnectsync` (fixed) |

---

## TherapyEvent Hierarchy

**Source**: `tconnectsync/domain/therapy_event.py`

### Base Class: TherapyEvent

| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | datetime | Event time |
| `event_type` | str | Event classification |

### CGMTherapyEvent

| Field | Type | Nightscout Mapping |
|-------|------|-------------------|
| `glucose` | int | `sgv` (mg/dL) |
| `timestamp` | datetime | `date` (epoch ms) |
| - | - | `type`: `sgv` |
| - | - | `device`: `tconnectsync` |

### BGTherapyEvent

| Field | Type | Nightscout Mapping |
|-------|------|-------------------|
| `bg_value` | int | `glucose` or `mbg` |
| `timestamp` | datetime | `date` |
| - | - | `type`: `mbg` |

### BolusTherapyEvent

Extends TherapyEvent with Bolus model data.

| Field | Nightscout Mapping |
|-------|-------------------|
| `bolus.insulin` | `insulin` |
| `bolus.carbs` | `carbs` |
| - | `eventType`: `Combo Bolus` |

### BasalTherapyEvent

| Field | Type | Nightscout Mapping |
|-------|------|-------------------|
| `rate` | float | `rate` (U/hr) |
| `duration` | int | `duration` (minutes) |
| `reason` | str | `notes` |
| - | - | `eventType`: `Temp Basal` |

---

## Profile Model

**Source**: `tconnectsync/domain/device_settings.py`

### Profile Class

| Field | Type | Description |
|-------|------|-------------|
| `segments` | List[ProfileSegment] | Time-based settings |

### ProfileSegment Class

| Field | Type | Description |
|-------|------|-------------|
| `display_time` | str | Human-readable time |
| `time` | str | Time in HH:MM format |
| `basal_rate` | float | Basal rate (U/hr) |
| `correction_factor` | int | ISF (mg/dL per unit) |
| `carb_ratio` | int | CR (g per unit) |
| `target_bg_mgdl` | int | Target BG (mg/dL) |

### Mapping to Nightscout Profile

| tconnectsync | Nightscout | Notes |
|--------------|------------|-------|
| `basal_rate` | `basal[].value` | U/hr |
| `time` | `basal[].time` | HH:MM:SS |
| `carb_ratio` | `carbratio[].value` | g/U |
| `correction_factor` | `sens[].value` | mg/dL/U |
| `target_bg_mgdl` | `target_low`, `target_high` | Same value for both |

---

## Device Settings

**Source**: `tconnectsync/domain/device_settings.py`

| Field | Type | Description |
|-------|------|-------------|
| `serial_number` | str | Pump serial number |
| `model_number` | str | Pump model |
| `firmware_version` | str | Pump firmware |
| `active_profile` | str | Currently active profile name |

---

## Unit Conventions

| Data Type | tconnectsync Unit | Nightscout Unit | Conversion |
|-----------|-------------------|-----------------|------------|
| Glucose | mg/dL | mg/dL | None |
| Insulin | units | units | None |
| Carbs | grams | grams | None |
| Basal Rate | U/hr | U/hr | None |
| Duration | minutes | minutes | None |
| Timestamp | datetime | epoch ms or ISO-8601 | Convert |

**Note**: tconnectsync uses standard units matching Nightscout conventions.

---

## Cross-References

- [Nightscout Treatments Schema](../nightscout/v3-treatments-schema.md)
- [AAPS Treatment Models](../aaps/nsclient-schema.md)
- [Duration/utcOffset Analysis](../../docs/10-domain/duration-utcoffset-unit-analysis.md)
