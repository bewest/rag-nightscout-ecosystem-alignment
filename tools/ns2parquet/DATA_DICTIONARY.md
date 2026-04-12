# ns2parquet Data Dictionary

Schema version: ns2parquet v0.3.0

All glucose values are in **mg/dL**. All timestamps are **UTC, millisecond precision**.
All durations are in **minutes**. All absorption times are in **minutes**.

## Collections

| File | Records | Description |
|------|---------|-------------|
| `entries.parquet` | CGM readings | Sensor glucose, meter BG, calibration |
| `treatments.parquet` | Insulin/carb events | Bolus, carbs, temp basal, overrides |
| `devicestatus.parquet` | AID controller state | IOB, COB, predictions, pump status |
| `profiles.parquet` | Therapy schedules | Basal rates, ISF, CR, targets (expanded) |
| `settings.parquet` | Site configuration | Units, plugins, BG thresholds |
| `grid.parquet` | 5-min research grid | All features aligned to 5-min intervals |

All files include a `patient_id` column for multi-patient filtering.

---

### Entries

CGM glucose readings and meter blood glucose values.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `patient_id` | string | ✗ |  |
| `_id` | string | ✓ |  |
| `type` | string | ✓ | sgv, mbg, cal |
| `date` | timestamp (ms, UTC) | ✗ |  |
| `sgv` | float | ✓ | mg/dL (sensor glucose) |
| `mbg` | float | ✓ | mg/dL (meter blood glucose) |
| `direction` | string | ✓ | DoubleUp .. DoubleDown |
| `noise` | int8 | ✓ | 0-5 signal quality |
| `filtered` | double | ✓ | filtered raw value |
| `unfiltered` | double | ✓ | unfiltered raw value |
| `delta` | float | ✓ | mg/dL change from previous |
| `rssi` | int16 | ✓ | signal strength dBm |
| `trend` | int8 | ✓ | numeric trend (Dexcom) |
| `trend_rate` | float | ✓ | mg/dL per 5 min |
| `device` | string | ✓ | loop://iPhone, openaps://model, etc. |
| `utc_offset` | int16 | ✓ | UTC offset in minutes |

---

### Treatments

Insulin delivery, carbohydrate intake, temp basals, and events.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `patient_id` | string | ✗ |  |
| `_id` | string | ✓ |  |
| `event_type` | string | ✓ | normalized eventType |
| `created_at` | timestamp (ms, UTC) | ✗ |  |
| `insulin` | float | ✓ | units delivered |
| `programmed` | float | ✓ | units originally programmed |
| `is_smb` | bool | ✓ | auto micro-bolus (multi-step detection) |
| `is_automatic` | bool | ✓ | automatic (Loop/Trio auto-bolus) |
| `bolus_type` | string | ✓ | Normal, Square, Dual |
| `insulin_type` | string | ✓ | Humalog, NovoRapid, Fiasp, etc. |
| `carbs` | float | ✓ | grams (at this 5-min slot) |
| `absorption_time_min` | float | ✓ | minutes (converted from seconds if Loop) |
| `food_type` | string | ✓ |  |
| `fat` | float | ✓ | grams |
| `protein` | float | ✓ | grams |
| `rate` | float | ✓ | U/hr (temp basal rate) |
| `duration_min` | float | ✓ | minutes (converted from seconds/ms if needed) |
| `percent` | float | ✓ | % of scheduled basal |
| `temp_type` | string | ✓ | absolute or percent |
| `target_top` | float | ✓ | mg/dL |
| `target_bottom` | float | ✓ | mg/dL |
| `reason` | string | ✓ | oref0 reason string |
| `glucose` | float | ✓ | mg/dL |
| `glucose_type` | string | ✓ | Sensor, Finger, Manual |
| `entered_by` | string | ✓ |  |
| `device` | string | ✓ | loop://iPhone, openaps://model, etc. |
| `notes` | string | ✓ |  |
| `utc_offset` | int16 | ✓ | UTC offset in minutes |
| `identifier` | string | ✓ | AAPS sync ID |
| `sync_identifier` | string | ✓ | Loop/Trio sync ID |

---

### DeviceStatus

Flattened AID controller state. Handles both Loop and oref0/AAPS/Trio structures.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `patient_id` | string | ✗ |  |
| `_id` | string | ✓ |  |
| `created_at` | timestamp (ms, UTC) | ✗ |  |
| `device` | string | ✓ | loop://iPhone, openaps://model, etc. |
| `controller` | string | ✓ | loop, openaps, trio (detected from device) |
| `iob` | float | ✓ | units |
| `basal_iob` | float | ✓ | NET basal IOB: actual−scheduled (oref0/AAPS basaliob). Can be negative during suspension. |
| `bolussnooze` | float | ✓ | AAPS accelerated-decay bolus IOB (safety metric, ≠ true bolus IOB). True bolus IOB = `iob − basal_iob`. |
| `cob` | float | ✓ | grams |
| `bg` | int16 | ✓ | current BG per algorithm (mg/dL) |
| `eventual_bg` | int16 | ✓ | predicted eventual BG (mg/dL) |
| `target_bg` | int16 | ✓ | algorithm target |
| `sensitivity_ratio` | float | ✓ | autosens ratio (1.0 = normal) |
| `insulin_req` | float | ✓ | insulin required (U) |
| `suggested_rate` | float | ✓ | suggested temp basal U/hr |
| `suggested_duration_min` | float | ✓ | minutes |
| `suggested_smb` | float | ✓ | suggested SMB units |
| `enacted_rate` | float | ✓ | enacted temp basal U/hr |
| `enacted_duration_min` | float | ✓ | minutes |
| `enacted_smb` | float | ✓ | enacted SMB units |
| `enacted_received` | bool | ✓ |  |
| `predicted_30` | float | ✓ | +30 min predicted glucose |
| `predicted_60` | float | ✓ | +60 min predicted glucose |
| `predicted_min` | float | ✓ | minimum predicted glucose |
| `hypo_risk_count` | int16 | ✓ | count of predicted values < 70 |
| `pred_iob_30` | float | ✓ | IOB-only curve at +30min |
| `pred_cob_30` | float | ✓ | COB curve at +30min |
| `pred_uam_30` | float | ✓ | UAM curve at +30min |
| `pred_zt_30` | float | ✓ | Zero-Temp curve at +30min |
| `pump_battery_pct` | float | ✓ |  |
| `pump_reservoir` | float | ✓ | units remaining |
| `pump_status` | string | ✓ | normal, suspended, bolusing |
| `pump_clock` | timestamp (ms, UTC) | ✓ |  |
| `uploader_battery_pct` | float | ✓ |  |
| `loop_failure_reason` | string | ✓ |  |
| `loop_version` | string | ✓ |  |
| `recommended_bolus` | float | ✓ |  |
| `override_active` | bool | ✓ |  |
| `override_name` | string | ✓ |  |
| `override_multiplier` | float | ✓ |  |
| `reason` | string (large) | ✓ | oref0 reason string |
| `utc_offset` | int16 | ✓ | UTC offset in minutes |

---

### Profiles

Therapy settings expanded to one row per schedule segment.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `patient_id` | string | ✗ |  |
| `_id` | string | ✓ |  |
| `profile_name` | string | ✓ | Default, Exercise, etc. |
| `created_at` | timestamp (ms, UTC) | ✓ |  |
| `start_date` | timestamp (ms, UTC) | ✓ |  |
| `timezone` | string | ✓ | IANA timezone |
| `dia_hours` | float | ✓ | Duration of Insulin Action |
| `insulin_curve` | string | ✓ | rapid-acting, ultra-rapid, etc. |
| `schedule_type` | string | ✓ | basal, isf, cr, target_low, target_high |
| `time_seconds` | int32 | ✓ | seconds since midnight (local) |
| `time_str` | string | ✓ | "HH:MM" format |
| `value` | float | ✓ | rate, ISF, CR, or target (mg/dL) |
| `units` | string | ✓ | Always 'mg/dL' (converted at normalization time) |

---

### Settings

Nightscout site configuration from /api/v1/status.json.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `patient_id` | string | ✗ |  |
| `fetched_at` | timestamp (ms, UTC) | ✓ |  |
| `server_version` | string | ✓ |  |
| `units` | string | ✓ | mg/dl or mmol/L — site preference |
| `data_mode` | string | ✓ | AID, pump, or MDI |
| `has_pump` | bool | ✓ |  |
| `has_loop` | bool | ✓ |  |
| `has_openaps` | bool | ✓ |  |
| `enabled_plugins` | string | ✓ | comma-separated sorted list |
| `bg_high` | float | ✓ | mg/dL (converted if mmol) |
| `bg_target_top` | float | ✓ | mg/dL |
| `bg_target_bottom` | float | ✓ | mg/dL |
| `bg_low` | float | ✓ | mg/dL |
| `timezone` | string | ✓ | IANA timezone |
| `language` | string | ✓ |  |

---

### Research Grid

Pre-computed 5-minute research grid with all features. Raw values (not normalized). The `loop_*` columns store predictions/actions from **any** AID controller (Loop, oref0, AAPS, Trio) — the prefix is historical.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `patient_id` | string | ✗ |  |
| `time` | timestamp (ms, UTC) | ✗ |  |
| `glucose` | float | ✓ | mg/dL |
| `iob` | float | ✓ | units |
| `cob` | float | ✓ | grams |
| `net_basal` | float | ✓ | U/hr deviation from scheduled |
| `bolus` | float | ✓ | units (at this 5-min slot) |
| `bolus_smb` | float | ✓ | units from SMB auto-boluses |
| `carbs` | float | ✓ | grams (at this 5-min slot) |
| `time_sin` | float | ✓ |  |
| `time_cos` | float | ✓ |  |
| `day_sin` | float | ✓ |  |
| `day_cos` | float | ✓ |  |
| `override_active` | float | ✓ |  |
| `override_type` | float | ✓ |  |
| `exercise_active` | float | ✓ | 1.0 during exercise events |
| `glucose_roc` | float | ✓ | mg/dL per 5 min |
| `glucose_accel` | float | ✓ |  |
| `time_since_bolus_min` | float | ✓ |  |
| `time_since_carb_min` | float | ✓ |  |
| `cage_hours` | float | ✓ |  |
| `sage_hours` | float | ✓ |  |
| `sensor_warmup` | float | ✓ |  |
| `month_sin` | float | ✓ |  |
| `month_cos` | float | ✓ |  |
| `trend_direction` | float | ✓ |  |
| `trend_rate` | float | ✓ | mg/dL per 5 min |
| `rolling_noise` | float | ✓ |  |
| `hours_since_cgm` | float | ✓ |  |
| `loop_predicted_30` | float | ✓ |  |
| `loop_predicted_60` | float | ✓ |  |
| `loop_predicted_min` | float | ✓ |  |
| `loop_hypo_risk` | float | ✓ |  |
| `loop_recommended` | float | ✓ |  |
| `loop_enacted_rate` | float | ✓ |  |
| `loop_enacted_bolus` | float | ✓ |  |
| `eventual_bg` | float | ✓ | predicted eventual BG (mg/dL) |
| `sensitivity_ratio` | float | ✓ | autosens ratio (1.0 = normal) |
| `insulin_req` | float | ✓ | insulin required (U) |
| `scheduled_isf` | float | ✓ |  |
| `scheduled_cr` | float | ✓ |  |
| `glucose_vs_target` | float | ✓ |  |
| `pump_battery` | float | ✓ |  |
| `pump_reservoir` | float | ✓ | units remaining |
| `sensor_phase` | float | ✓ |  |
| `suspension_time_min` | float | ✓ |  |
| `scheduled_basal_rate` | float | ✓ | U/hr |
| `actual_basal_rate` | float | ✓ | U/hr (temp or scheduled) |
| `direction` | string | ✓ | DoubleUp .. DoubleDown |

---

## Units & Conventions

| Measurement | Unit | Notes |
|-------------|------|-------|
| Glucose (sgv, mbg) | mg/dL | mmol/L sites pre-converted at ingestion |
| ISF | mg/dL per U | Converted from mmol/L if needed |
| CR | g per U | No conversion needed |
| Basal rate | U/hr | |
| Insulin | U | |
| Carbs | g | |
| Duration | minutes | Converted from seconds (Loop) or ms (AAPS) |
| Absorption time | minutes | Converted from seconds if Loop |
| Timestamps | UTC, ms precision | ISO 8601 or epoch ms accepted at input |
| Conversion factor | 18.01559 | mmol/L × 18.01559 = mg/dL |

## Quick Start

```python
import pandas as pd

# Load the research grid
grid = pd.read_parquet("grid.parquet")

# Filter to one patient
pat = grid[grid["patient_id"] == "a"]

# Basic statistics
print(pat[["glucose", "iob", "cob", "bolus", "carbs"]].describe())
```
