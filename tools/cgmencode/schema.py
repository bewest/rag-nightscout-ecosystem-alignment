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
CONTEXT_IDX   = WEEKDAY_IDX + OVERRIDE_IDX + DYNAMICS_IDX + TEMPORAL_IDX + DEVICE_IDX + MONTHLY_IDX

# ── Feature counts ──────────────────────────────────────────────────────
NUM_FEATURES = 8                  # Core — existing models use this
NUM_FEATURES_EXTENDED = 21        # Core + extended context + CAGE/SAGE + monthly

FEATURE_NAMES = ['glucose', 'iob', 'cob', 'net_basal', 'bolus', 'carbs', 'time_sin', 'time_cos']

EXTENDED_FEATURE_NAMES = FEATURE_NAMES + [
    'day_sin', 'day_cos',
    'override_active', 'override_type',
    'glucose_roc', 'glucose_accel',
    'time_since_bolus', 'time_since_carb',
    'cage_hours', 'sage_hours', 'sensor_warmup',
    'month_sin', 'month_cos',
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
