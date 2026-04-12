"""
schemas.py — PyArrow schemas for Nightscout collections.

Defines typed, flat schemas for each Nightscout collection. These are the
canonical column definitions used when writing Parquet files.

Design notes:
- Timestamps are pa.timestamp('ms', tz='UTC') — millisecond precision, UTC
- patient_id is always the first column — enables efficient filtering
- Nullable fields use allow_null=True (the default for PyArrow)
- direction is stored as string (original Nightscout value) not numeric
- Units are normalized: durations → minutes, absorption → minutes
"""

import pyarrow as pa

# ── Entries (CGM glucose readings) ──────────────────────────────────────
ENTRIES_SCHEMA = pa.schema([
    pa.field('patient_id', pa.string(), nullable=False),
    pa.field('_id', pa.string()),
    pa.field('type', pa.string()),            # sgv, mbg, cal
    pa.field('date', pa.timestamp('ms', tz='UTC'), nullable=False),
    pa.field('sgv', pa.float32()),            # mg/dL (sensor glucose)
    pa.field('mbg', pa.float32()),            # mg/dL (meter blood glucose)
    pa.field('direction', pa.string()),       # DoubleUp .. DoubleDown
    pa.field('noise', pa.int8()),             # 0-5 signal quality
    pa.field('filtered', pa.float64()),       # filtered raw value
    pa.field('unfiltered', pa.float64()),     # unfiltered raw value
    pa.field('delta', pa.float32()),          # mg/dL change from previous
    pa.field('rssi', pa.int16()),             # signal strength dBm
    pa.field('trend', pa.int8()),             # numeric trend (Dexcom)
    pa.field('trend_rate', pa.float32()),     # mg/dL per 5 min
    pa.field('device', pa.string()),          # source device identifier
    pa.field('utc_offset', pa.int16()),       # UTC offset in minutes
])

# ── Treatments (insulin, carbs, events) ─────────────────────────────────
TREATMENTS_SCHEMA = pa.schema([
    pa.field('patient_id', pa.string(), nullable=False),
    pa.field('_id', pa.string()),
    pa.field('event_type', pa.string()),       # normalized eventType
    pa.field('created_at', pa.timestamp('ms', tz='UTC'), nullable=False),
    # Insulin fields
    pa.field('insulin', pa.float32()),         # units delivered
    pa.field('programmed', pa.float32()),      # units originally programmed
    pa.field('is_smb', pa.bool_()),            # auto micro-bolus (multi-step detection)
    pa.field('is_automatic', pa.bool_()),      # automatic (Loop/Trio auto-bolus)
    pa.field('bolus_type', pa.string()),       # Normal, Square, Dual
    pa.field('insulin_type', pa.string()),     # Humalog, NovoRapid, Fiasp, etc.
    # Carb fields
    pa.field('carbs', pa.float32()),           # grams
    pa.field('absorption_time_min', pa.float32()),  # minutes (converted from seconds if Loop)
    pa.field('food_type', pa.string()),
    pa.field('fat', pa.float32()),             # grams
    pa.field('protein', pa.float32()),         # grams
    # Basal fields
    pa.field('rate', pa.float32()),            # U/hr (temp basal rate)
    pa.field('duration_min', pa.float32()),    # minutes (converted from seconds/ms if needed)
    pa.field('percent', pa.float32()),         # % of scheduled basal
    pa.field('temp_type', pa.string()),        # absolute or percent
    # Target / override
    pa.field('target_top', pa.float32()),      # mg/dL
    pa.field('target_bottom', pa.float32()),   # mg/dL
    pa.field('reason', pa.string()),           # override/temp target reason
    # BG check
    pa.field('glucose', pa.float32()),         # mg/dL (finger stick)
    pa.field('glucose_type', pa.string()),     # Sensor, Finger, Manual
    # Metadata
    pa.field('entered_by', pa.string()),
    pa.field('device', pa.string()),
    pa.field('notes', pa.string()),
    pa.field('utc_offset', pa.int16()),
    # Sync identity (controller-specific)
    pa.field('identifier', pa.string()),       # AAPS sync ID
    pa.field('sync_identifier', pa.string()),  # Loop/Trio sync ID
])

# ── DeviceStatus (flattened controller state) ───────────────────────────
DEVICESTATUS_SCHEMA = pa.schema([
    pa.field('patient_id', pa.string(), nullable=False),
    pa.field('_id', pa.string()),
    pa.field('created_at', pa.timestamp('ms', tz='UTC'), nullable=False),
    pa.field('device', pa.string()),          # loop://iPhone, openaps://model, etc.
    pa.field('controller', pa.string()),      # loop, openaps, trio (detected from device)
    # IOB / COB
    pa.field('iob', pa.float32()),            # total insulin on board (U)
    pa.field('basal_iob', pa.float32()),      # NET basal IOB: actual-scheduled (oref0 basaliob)
    pa.field('bolussnooze', pa.float32()),    # AAPS bolussnooze: accelerated-decay bolus IOB (safety metric, ≠ true bolus IOB)
    pa.field('cob', pa.float32()),            # carbs on board (g)
    # Algorithm output
    pa.field('bg', pa.int16()),               # current BG per algorithm (mg/dL)
    pa.field('eventual_bg', pa.int16()),      # predicted eventual BG
    pa.field('target_bg', pa.int16()),        # algorithm target
    pa.field('sensitivity_ratio', pa.float32()),  # autosens ratio (1.0 = normal)
    pa.field('insulin_req', pa.float32()),    # insulin required
    # Recommendation
    pa.field('suggested_rate', pa.float32()), # suggested temp basal U/hr
    pa.field('suggested_duration_min', pa.float32()),  # minutes
    pa.field('suggested_smb', pa.float32()),  # suggested SMB units
    # Enacted
    pa.field('enacted_rate', pa.float32()),   # enacted temp basal U/hr
    pa.field('enacted_duration_min', pa.float32()),  # minutes
    pa.field('enacted_smb', pa.float32()),    # enacted SMB units
    pa.field('enacted_received', pa.bool_()),
    # Predictions (first values from each curve)
    pa.field('predicted_30', pa.float32()),   # +30 min predicted glucose
    pa.field('predicted_60', pa.float32()),   # +60 min predicted glucose
    pa.field('predicted_min', pa.float32()),  # minimum predicted glucose
    pa.field('hypo_risk_count', pa.int16()),  # count of predicted values < 70
    # oref0 multi-curve predictions (indices [6] and [12] from each)
    pa.field('pred_iob_30', pa.float32()),    # IOB-only curve at +30min
    pa.field('pred_cob_30', pa.float32()),    # COB curve at +30min
    pa.field('pred_uam_30', pa.float32()),    # UAM curve at +30min
    pa.field('pred_zt_30', pa.float32()),     # Zero-Temp curve at +30min
    # Pump state
    pa.field('pump_battery_pct', pa.float32()),
    pa.field('pump_reservoir', pa.float32()), # units remaining
    pa.field('pump_status', pa.string()),     # normal, suspended, bolusing
    pa.field('pump_clock', pa.timestamp('ms', tz='UTC')),
    # Uploader
    pa.field('uploader_battery_pct', pa.float32()),
    # Loop-specific
    pa.field('loop_failure_reason', pa.string()),
    pa.field('loop_version', pa.string()),
    pa.field('recommended_bolus', pa.float32()),
    # Override (Loop)
    pa.field('override_active', pa.bool_()),
    pa.field('override_name', pa.string()),
    pa.field('override_multiplier', pa.float32()),
    # Algorithm reason text
    pa.field('reason', pa.large_string()),    # oref0 reason string
    pa.field('utc_offset', pa.int16()),
])

# ── Profiles (expanded therapy schedules) ───────────────────────────────
PROFILES_SCHEMA = pa.schema([
    pa.field('patient_id', pa.string(), nullable=False),
    pa.field('_id', pa.string()),
    pa.field('profile_name', pa.string()),     # Default, Exercise, etc.
    pa.field('created_at', pa.timestamp('ms', tz='UTC')),
    pa.field('start_date', pa.timestamp('ms', tz='UTC')),
    pa.field('timezone', pa.string()),         # IANA timezone
    pa.field('dia_hours', pa.float32()),       # Duration of Insulin Action
    pa.field('insulin_curve', pa.string()),    # rapid-acting, ultra-rapid, etc.
    # Schedule entries (one row per time segment)
    pa.field('schedule_type', pa.string()),    # basal, isf, cr, target_low, target_high
    pa.field('time_seconds', pa.int32()),      # seconds since midnight (local)
    pa.field('time_str', pa.string()),         # "HH:MM" format
    pa.field('value', pa.float32()),           # rate, ISF, CR, or target (mg/dL)
    pa.field('units', pa.string()),            # always 'mg/dL' after conversion
])

# ── Site Settings (from /api/v1/status.json) ───────────────────────────
SETTINGS_SCHEMA = pa.schema([
    pa.field('patient_id', pa.string(), nullable=False),
    pa.field('fetched_at', pa.timestamp('ms', tz='UTC')),
    pa.field('server_version', pa.string()),
    pa.field('units', pa.string()),            # mg/dl or mmol/L — site preference
    pa.field('data_mode', pa.string()),        # AID, pump, or MDI
    pa.field('has_pump', pa.bool_()),
    pa.field('has_loop', pa.bool_()),
    pa.field('has_openaps', pa.bool_()),
    pa.field('enabled_plugins', pa.string()),  # comma-separated sorted list
    pa.field('bg_high', pa.float32()),         # mg/dL (converted if mmol)
    pa.field('bg_target_top', pa.float32()),   # mg/dL
    pa.field('bg_target_bottom', pa.float32()),# mg/dL
    pa.field('bg_low', pa.float32()),          # mg/dL
    pa.field('timezone', pa.string()),
    pa.field('language', pa.string()),
])

# ── Research Grid (5-min intervals, all features) ──────────────────────
GRID_SCHEMA = pa.schema([
    pa.field('patient_id', pa.string(), nullable=False),
    pa.field('time', pa.timestamp('ms', tz='UTC'), nullable=False),
    # Core 8 features (raw units, not normalized)
    pa.field('glucose', pa.float32()),         # mg/dL
    pa.field('iob', pa.float32()),             # units
    pa.field('cob', pa.float32()),             # grams
    pa.field('net_basal', pa.float32()),       # U/hr deviation from scheduled
    pa.field('bolus', pa.float32()),           # units (at this 5-min slot)
    pa.field('bolus_smb', pa.float32()),       # units from SMB auto-boluses
    pa.field('carbs', pa.float32()),           # grams (at this 5-min slot)
    # Circadian (computed from patient timezone)
    pa.field('time_sin', pa.float32()),
    pa.field('time_cos', pa.float32()),
    # Extended context
    pa.field('day_sin', pa.float32()),
    pa.field('day_cos', pa.float32()),
    pa.field('override_active', pa.float32()),
    pa.field('override_type', pa.float32()),
    pa.field('exercise_active', pa.float32()),  # 1.0 during exercise events
    pa.field('glucose_roc', pa.float32()),     # mg/dL per 5 min
    pa.field('glucose_accel', pa.float32()),
    pa.field('time_since_bolus_min', pa.float32()),
    pa.field('time_since_carb_min', pa.float32()),
    pa.field('cage_hours', pa.float32()),
    pa.field('sage_hours', pa.float32()),
    pa.field('sensor_warmup', pa.float32()),
    pa.field('month_sin', pa.float32()),
    pa.field('month_cos', pa.float32()),
    # CGM quality
    pa.field('trend_direction', pa.float32()),
    pa.field('trend_rate', pa.float32()),
    pa.field('rolling_noise', pa.float32()),
    pa.field('hours_since_cgm', pa.float32()),
    # AID algorithm context
    # NOTE: "loop_" prefix is historical. These columns store predictions and
    # recommendations from ANY AID controller (Loop, oref0, AAPS, Trio).
    # For oref0/AAPS/Trio, values come from the openaps/suggested/enacted objects.
    # For Loop, values come from the loop/predicted/automaticDoseRecommendation objects.
    pa.field('loop_predicted_30', pa.float32()),
    pa.field('loop_predicted_60', pa.float32()),
    pa.field('loop_predicted_min', pa.float32()),
    pa.field('loop_hypo_risk', pa.float32()),
    pa.field('loop_recommended', pa.float32()),
    pa.field('loop_enacted_rate', pa.float32()),
    pa.field('loop_enacted_bolus', pa.float32()),
    # oref0 algorithm context (Trio/AAPS/OpenAPS)
    pa.field('eventual_bg', pa.float32()),          # predicted eventual BG (mg/dL)
    pa.field('sensitivity_ratio', pa.float32()),    # autosens ratio (1.0 = normal)
    pa.field('insulin_req', pa.float32()),          # insulin required (U)
    # Profile-derived
    pa.field('scheduled_isf', pa.float32()),
    pa.field('scheduled_cr', pa.float32()),
    pa.field('glucose_vs_target', pa.float32()),
    # Pump state
    pa.field('pump_battery', pa.float32()),
    pa.field('pump_reservoir', pa.float32()),
    # Sensor lifecycle
    pa.field('sensor_phase', pa.float32()),
    pa.field('suspension_time_min', pa.float32()),
    # Basal context (raw, not net)
    pa.field('scheduled_basal_rate', pa.float32()),  # U/hr
    pa.field('actual_basal_rate', pa.float32()),      # U/hr (temp or scheduled)
    # Direction as original string (for reference)
    pa.field('direction', pa.string()),
])
