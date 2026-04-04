"""
schema.py — Canonical feature vector schema and normalization constants.

Single source of truth for the cgmencode feature layout. All modules that
normalize or denormalize data should import from here.

The schema has two tiers:
  - Core (indices 0–7): The original 8-feature vector used by all existing
    models and checkpoints. Backward-compatible; never changes.
  - Extended (indices 8–15): Additional context features for agentic insulin
    delivery (override detection, temporal patterns, glucose dynamics).
    Only used by models explicitly constructed with input_dim=NUM_FEATURES_EXTENDED.
"""

# ── Core feature indices (frozen — do not reorder) ──────────────────────
IDX_GLUCOSE    = 0
IDX_IOB        = 1
IDX_COB        = 2
IDX_NET_BASAL  = 3
IDX_BOLUS      = 4
IDX_CARBS      = 5
IDX_TIME_SIN   = 6
IDX_TIME_COS   = 7

# ── Extended feature indices (agentic delivery context) ─────────────────
IDX_DAY_SIN             = 8   # sin(2π · day_of_week / 7) — weekly patterns
IDX_DAY_COS             = 9   # cos(2π · day_of_week / 7)
IDX_OVERRIDE_ACTIVE     = 10  # 1.0 if an override is currently active, else 0.0
IDX_OVERRIDE_TYPE       = 11  # Encoded override type (0=none, see OVERRIDE_TYPES)
IDX_GLUCOSE_ROC         = 12  # Rate of change (mg/dL per 5 min), normalized
IDX_GLUCOSE_ACCEL       = 13  # Acceleration (Δ rate-of-change), normalized
IDX_TIME_SINCE_BOLUS    = 14  # Minutes since last bolus, normalized
IDX_TIME_SINCE_CARB     = 15  # Minutes since last carb entry, normalized

# ── Device lifecycle indices (CAGE/SAGE) ────────────────────────────────
IDX_CAGE_HOURS          = 16  # Hours since last Site Change (cannula age)
IDX_SAGE_HOURS          = 17  # Hours since last Sensor Start (sensor age)
IDX_SENSOR_WARMUP       = 18  # Binary: 1.0 during first 2h after Sensor Start

# ── Monthly phase encoding ──────────────────────────────────────────────
IDX_MONTH_SIN           = 19  # sin(2π · day_of_month / 30.4) — monthly patterns
IDX_MONTH_COS           = 20  # cos(2π · day_of_month / 30.4)

# ── CGM signal quality (Gen-4 enrichment) ────────────────────────────────
IDX_TREND_DIRECTION     = 21  # Ordinal trend arrow: -2(DoubleDown) to +2(DoubleUp) / 2
IDX_TREND_RATE          = 22  # CGM-provided trendRate (mg/dL per 5min) / 10
IDX_ROLLING_NOISE       = 23  # Rolling 1hr std of glucose diffs / 20 (signal quality)
IDX_HOURS_SINCE_CGM     = 24  # Hours since last valid CGM reading / 24 (gap proxy)

# ── AID algorithm context ────────────────────────────────────────────────
IDX_LOOP_PREDICTED_30   = 25  # Loop's predicted glucose at +30min / 400
IDX_LOOP_PREDICTED_60   = 26  # Loop's predicted glucose at +60min / 400
IDX_LOOP_PREDICTED_MIN  = 27  # Loop's predicted minimum glucose / 400
IDX_LOOP_HYPO_RISK      = 28  # Count of predicted values <70 / 20
IDX_LOOP_RECOMMENDED    = 29  # Loop's recommended bolus / 10 U
IDX_LOOP_ENACTED_RATE   = 30  # Actual enacted temp basal rate / 6 U/hr
IDX_LOOP_ENACTED_BOLUS  = 31  # Enacted micro-bolus volume / 5 U

# ── Profile-derived context ──────────────────────────────────────────────
IDX_SCHEDULED_ISF       = 32  # Profile ISF at current time / 200
IDX_SCHEDULED_CR        = 33  # Profile carb ratio at current time / 20
IDX_GLUCOSE_VS_TARGET   = 34  # (glucose - target_mid) / 100 → signed offset

# ── Device hardware state ────────────────────────────────────────────────
IDX_PUMP_BATTERY        = 35  # Pump battery percent / 100
IDX_PUMP_RESERVOIR      = 36  # Pump reservoir units / 300

# ── Enhanced sensor lifecycle ────────────────────────────────────────────
IDX_SENSOR_PHASE        = 37  # Discrete phase: warmup=0, early=0.25, peak=0.5, late=0.75, extended=1.0
IDX_SUSPENSION_TIME     = 38  # Minutes since last insulin suspension / 360

# ── Semantic groups ─────────────────────────────────────────────────────
STATE_IDX  = [IDX_GLUCOSE, IDX_IOB, IDX_COB]
ACTION_IDX = [IDX_NET_BASAL, IDX_BOLUS, IDX_CARBS]
TIME_IDX   = [IDX_TIME_SIN, IDX_TIME_COS]
ALL_VALS_IDX = STATE_IDX + ACTION_IDX

# Extended groups (Layer 4 / agentic features)
WEEKDAY_IDX   = [IDX_DAY_SIN, IDX_DAY_COS]
OVERRIDE_IDX  = [IDX_OVERRIDE_ACTIVE, IDX_OVERRIDE_TYPE]
DYNAMICS_IDX  = [IDX_GLUCOSE_ROC, IDX_GLUCOSE_ACCEL]
TEMPORAL_IDX  = [IDX_TIME_SINCE_BOLUS, IDX_TIME_SINCE_CARB]
DEVICE_IDX    = [IDX_CAGE_HOURS, IDX_SAGE_HOURS, IDX_SENSOR_WARMUP]
MONTHLY_IDX   = [IDX_MONTH_SIN, IDX_MONTH_COS]

# Gen-4 enrichment groups
CGM_QUALITY_IDX   = [IDX_TREND_DIRECTION, IDX_TREND_RATE, IDX_ROLLING_NOISE, IDX_HOURS_SINCE_CGM]
AID_CONTEXT_IDX   = [IDX_LOOP_PREDICTED_30, IDX_LOOP_PREDICTED_60, IDX_LOOP_PREDICTED_MIN,
                     IDX_LOOP_HYPO_RISK, IDX_LOOP_RECOMMENDED,
                     IDX_LOOP_ENACTED_RATE, IDX_LOOP_ENACTED_BOLUS]
PROFILE_IDX       = [IDX_SCHEDULED_ISF, IDX_SCHEDULED_CR, IDX_GLUCOSE_VS_TARGET]
PUMP_STATE_IDX    = [IDX_PUMP_BATTERY, IDX_PUMP_RESERVOIR]
SENSOR_LIFECYCLE_IDX = [IDX_SENSOR_PHASE, IDX_SUSPENSION_TIME]

CONTEXT_IDX   = (WEEKDAY_IDX + OVERRIDE_IDX + DYNAMICS_IDX + TEMPORAL_IDX
                 + DEVICE_IDX + MONTHLY_IDX + CGM_QUALITY_IDX + AID_CONTEXT_IDX
                 + PROFILE_IDX + PUMP_STATE_IDX + SENSOR_LIFECYCLE_IDX)

# ── Future masking ───────────────────────────────────────────────────────
# Channels containing information truly unknown at real-time inference.
# These must be zeroed in the future half during forecast training/eval.
#
# EXP-230 showed selective masking (7 channels) achieves 18.2 MAE vs
# full masking (10 channels) at 25.1 MAE.  IOB/COB/basal decay curves
# are deterministic from current state and must NOT be masked.
FUTURE_UNKNOWN_CHANNELS = [
    IDX_GLUCOSE,            # 0 - future glucose is what we predict
    IDX_BOLUS,              # 4 - future bolus events unknown
    IDX_CARBS,              # 5 - future carb entries unknown
    IDX_GLUCOSE_ROC,        # 12 - derived from future glucose
    IDX_GLUCOSE_ACCEL,      # 13 - derived from future glucose
    IDX_TIME_SINCE_BOLUS,   # 14 - reveals future bolus timing
    IDX_TIME_SINCE_CARB,    # 15 - reveals future carb timing
    IDX_TREND_DIRECTION,    # 21 - derived from future glucose
    IDX_TREND_RATE,         # 22 - derived from future glucose
    IDX_ROLLING_NOISE,      # 23 - derived from future glucose
    IDX_HOURS_SINCE_CGM,    # 24 - future gap status unknown
    IDX_LOOP_PREDICTED_30,  # 25 - future AID predictions unknown
    IDX_LOOP_PREDICTED_60,  # 26 - future AID predictions unknown
    IDX_LOOP_PREDICTED_MIN, # 27 - future AID predictions unknown
    IDX_LOOP_HYPO_RISK,     # 28 - future AID predictions unknown
    IDX_LOOP_RECOMMENDED,   # 29 - future AID recommendation unknown
    IDX_LOOP_ENACTED_RATE,  # 30 - future AID actions unknown
    IDX_LOOP_ENACTED_BOLUS, # 31 - future AID actions unknown
    IDX_GLUCOSE_VS_TARGET,  # 34 - contains (glucose-target)/100 → glucose leak!
    IDX_PUMP_RESERVOIR,     # 36 - decreases with insulin delivery → reveals future dosing
    IDX_SUSPENSION_TIME,    # 38 - future suspensions unknown
]
# Deterministic channels kept unmasked (EXP-230 validated):
#   IOB (1) - decays via known insulin curve from current value
#   COB (2) - decays via known absorption model from current value
#   net_basal (3) - scheduled from pump profile
# Also unmasked: time_sin/cos (6,7), day_sin/cos (8,9),
# override (10,11), CAGE/SAGE/warmup (16-18), month_sin/cos (19,20),
# scheduled_isf/cr (32,33), pump_battery (35), sensor_phase (37)
#
# EXP-261 leak detection: ch34 (glucose_vs_target) caused 1.1 MAE →
# 39.5 MAE when ablated. ch36 (pump_reservoir) caused 1.1 → 1.6 MAE.

# ── Feature counts ──────────────────────────────────────────────────────
NUM_FEATURES = 8                  # Core — existing models use this
NUM_FEATURES_EXTENDED = 21        # Gen-3: Core + extended context + CAGE/SAGE + monthly
NUM_FEATURES_ENRICHED = 39        # Gen-4: Gen-3 + CGM quality + AID context + profile + pump + lifecycle

FEATURE_NAMES = ['glucose', 'iob', 'cob', 'net_basal', 'bolus', 'carbs', 'time_sin', 'time_cos']

EXTENDED_FEATURE_NAMES = FEATURE_NAMES + [
    'day_sin', 'day_cos',
    'override_active', 'override_type',
    'glucose_roc', 'glucose_accel',
    'time_since_bolus', 'time_since_carb',
    'cage_hours', 'sage_hours', 'sensor_warmup',
    'month_sin', 'month_cos',
]

ENRICHED_FEATURE_NAMES = EXTENDED_FEATURE_NAMES + [
    'trend_direction', 'trend_rate', 'rolling_noise', 'hours_since_cgm',
    'loop_predicted_30', 'loop_predicted_60', 'loop_predicted_min',
    'loop_hypo_risk', 'loop_recommended',
    'loop_enacted_rate', 'loop_enacted_bolus',
    'scheduled_isf', 'scheduled_cr', 'glucose_vs_target',
    'pump_battery', 'pump_reservoir',
    'sensor_phase', 'suspension_time',
]

# ── Override type encoding ──────────────────────────────────────────────
OVERRIDE_TYPES = {
    'none':         0.0,
    'eating_soon':  0.2,
    'exercise':     0.4,
    'sleep':        0.6,
    'sick':         0.8,
    'custom':       1.0,
}
OVERRIDE_TYPE_NAMES = {v: k for k, v in OVERRIDE_TYPES.items()}

# ── Normalization scales: raw value / SCALE → normalized ────────────────
# Glucose: 0–400 mg/dL → [0, 1]
# IOB: 0–20 U → [0, 1]
# COB: 0–100 g → [0, 1]
# Net basal: −5..+5 U/hr → [−1, 1]
# Bolus: 0–10 U → [0, 1]
# Carbs: 0–100 g → [0, 1]
# time_sin/cos, day_sin/cos: already [−1, 1]
# override_active: binary [0, 1]
# override_type: [0, 1] categorical encoding
# glucose_roc: rate of change ~[-10, +10] mg/dL per 5min → /10
# glucose_accel: acceleration ~[-5, +5] → /5
# time_since_bolus/carb: 0–360 min (6 hr cap) → /360
NORMALIZATION_SCALES = {
    'glucose':          400.0,
    'iob':               20.0,
    'cob':              100.0,
    'net_basal':          5.0,
    'bolus':             10.0,
    'carbs':            100.0,
    'glucose_roc':       10.0,
    'glucose_accel':      5.0,
    'time_since_bolus': 360.0,
    'time_since_carb':  360.0,
    'cage_hours':        72.0,   # 3-day infusion set life (0-72h typical)
    'sage_hours':       240.0,   # 10-day sensor life (0-240h, allows extended wear)
    # Gen-4 enrichment scales
    'trend_direction':    2.0,   # ordinal: -2 to +2 → [-1, 1]
    'trend_rate':        10.0,   # mg/dL per 5min → [-1, 1] typical
    'rolling_noise':     20.0,   # std of diffs, typically 0-20 mg/dL
    'hours_since_cgm':   24.0,   # hours → [0, 1] at 1-day cap
    'loop_predicted':   400.0,   # mg/dL same as glucose
    'loop_hypo_risk':    20.0,   # count of predicted <70 values
    'loop_recommended':  10.0,   # bolus units
    'loop_enacted_rate':  6.0,   # U/hr max basal rate
    'loop_enacted_bolus': 5.0,   # U micro-bolus
    'scheduled_isf':    200.0,   # mg/dL per U
    'scheduled_cr':      20.0,   # g per U
    'glucose_vs_target':100.0,   # signed mg/dL offset from target
    'pump_battery':     100.0,   # percent
    'pump_reservoir':   300.0,   # units
    'suspension_time':  360.0,   # minutes, same cap as time_since_bolus
}

# Glucose clipping range (mg/dL) — applied before normalization
GLUCOSE_CLIP_MIN = 40.0
GLUCOSE_CLIP_MAX = 400.0

# Time-since cap (minutes) — applied before normalization
TIME_SINCE_CAP_MIN = 360.0

# ── Per-channel scale arrays (for vectorized normalization) ─────────────
SCALE_ARRAY = [
    NORMALIZATION_SCALES['glucose'],
    NORMALIZATION_SCALES['iob'],
    NORMALIZATION_SCALES['cob'],
    NORMALIZATION_SCALES['net_basal'],
    NORMALIZATION_SCALES['bolus'],
    NORMALIZATION_SCALES['carbs'],
    1.0,  # time_sin (native)
    1.0,  # time_cos (native)
]

EXTENDED_SCALE_ARRAY = SCALE_ARRAY + [
    1.0,  # day_sin (native)
    1.0,  # day_cos (native)
    1.0,  # override_active (binary)
    1.0,  # override_type (pre-encoded)
    NORMALIZATION_SCALES['glucose_roc'],
    NORMALIZATION_SCALES['glucose_accel'],
    NORMALIZATION_SCALES['time_since_bolus'],
    NORMALIZATION_SCALES['time_since_carb'],
    NORMALIZATION_SCALES['cage_hours'],
    NORMALIZATION_SCALES['sage_hours'],
    1.0,  # sensor_warmup (binary)
    1.0,  # month_sin (native)
    1.0,  # month_cos (native)
]

ENRICHED_SCALE_ARRAY = EXTENDED_SCALE_ARRAY + [
    NORMALIZATION_SCALES['trend_direction'],     # 21
    NORMALIZATION_SCALES['trend_rate'],           # 22
    NORMALIZATION_SCALES['rolling_noise'],        # 23
    NORMALIZATION_SCALES['hours_since_cgm'],      # 24
    NORMALIZATION_SCALES['loop_predicted'],        # 25 - loop_predicted_30
    NORMALIZATION_SCALES['loop_predicted'],        # 26 - loop_predicted_60
    NORMALIZATION_SCALES['loop_predicted'],        # 27 - loop_predicted_min
    NORMALIZATION_SCALES['loop_hypo_risk'],        # 28
    NORMALIZATION_SCALES['loop_recommended'],      # 29
    NORMALIZATION_SCALES['loop_enacted_rate'],     # 30
    NORMALIZATION_SCALES['loop_enacted_bolus'],    # 31
    NORMALIZATION_SCALES['scheduled_isf'],         # 32
    NORMALIZATION_SCALES['scheduled_cr'],          # 33
    NORMALIZATION_SCALES['glucose_vs_target'],     # 34
    NORMALIZATION_SCALES['pump_battery'],           # 35
    NORMALIZATION_SCALES['pump_reservoir'],         # 36
    1.0,                                           # 37 - sensor_phase (pre-encoded 0-1)
    NORMALIZATION_SCALES['suspension_time'],        # 38
]
