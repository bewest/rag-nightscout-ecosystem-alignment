"""
schema.py — Canonical 8-feature vector schema and normalization constants.

Single source of truth for the cgmencode feature layout. All modules that
normalize or denormalize data should import from here.
"""

# Feature indices
IDX_GLUCOSE    = 0
IDX_IOB        = 1
IDX_COB        = 2
IDX_NET_BASAL  = 3
IDX_BOLUS      = 4
IDX_CARBS      = 5
IDX_TIME_SIN   = 6
IDX_TIME_COS   = 7

# Semantic groups
STATE_IDX  = [IDX_GLUCOSE, IDX_IOB, IDX_COB]
ACTION_IDX = [IDX_NET_BASAL, IDX_BOLUS, IDX_CARBS]
TIME_IDX   = [IDX_TIME_SIN, IDX_TIME_COS]
ALL_VALS_IDX = STATE_IDX + ACTION_IDX

NUM_FEATURES = 8
FEATURE_NAMES = ['glucose', 'iob', 'cob', 'net_basal', 'bolus', 'carbs', 'time_sin', 'time_cos']

# Normalization scales: raw value / SCALE → normalized
# Glucose: 0–400 mg/dL → [0, 1]
# IOB: 0–20 U → [0, 1]
# COB: 0–100 g → [0, 1]
# Net basal: −5..+5 U/hr → [−1, 1]
# Bolus: 0–10 U → [0, 1]
# Carbs: 0–100 g → [0, 1]
# time_sin/cos: already [−1, 1]
NORMALIZATION_SCALES = {
    'glucose':    400.0,
    'iob':         20.0,
    'cob':        100.0,
    'net_basal':    5.0,
    'bolus':       10.0,
    'carbs':      100.0,
}

# Glucose clipping range (mg/dL) — applied before normalization
GLUCOSE_CLIP_MIN = 40.0
GLUCOSE_CLIP_MAX = 400.0

# Per-channel scale array (for vectorized normalization)
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
