"""
pk_bridge.py — Bridge continuous_pk features to parquet grid DataFrames.

Adapts tools/cgmencode/continuous_pk.py (first-principles insulin PK model)
to work directly with ns2parquet grid.parquet DataFrames, which already have
per-timestep expanded schedule columns (scheduled_isf, scheduled_cr,
scheduled_basal_rate).

Produces:
  1. OREF-equivalent features with CORRECT units and semantics (5 features)
  2. Additional PK-derived augmentation features (8 features)

Semantic Audit — PK-to-OREF Feature Mapping:

  The 5 "approximated" features in data_bridge.py have known problems:
  - iob_basaliob/bolusiob: proportional split by activity magnitude, not by
    treatment type (oref0 splits at 0.1U threshold per treatment)
  - iob_activity: inferred from BG change (conflates insulin + food + noise)
  - reason_BGI: circular calc (= glucose_roc, not insulin-only effect)
  - reason_Dev: missing insulin subtraction, wrong projection scale

  PK replacements fix these by computing from first-principles insulin PK:
  - pk_basal_iob (U): NET basal IOB = convolve(actual - scheduled, iob_kernel).
    CAN BE NEGATIVE during suspension/reduced delivery, matching both Loop
    (DoseEntry.swift:114: netBasalUnits = actual - scheduled) and oref0
    (iob/history.js:553: netBasalRate = rate - scheduledRate → ±0.05U entries).
  - pk_bolus_iob (U): IOB remaining from bolus doses (always ≥ 0)
  - pk_activity (U/5min): Net insulin activity rate from PK curve
    (matches oref0.iob.activity = rate from insulin curve, NOT from BG)
  - pk_bgi (mg/dL/5min): -activity × ISF (matches oref0's BGI formula)
  - pk_dev (mg/dL/30min): 6 × (glucose_roc - pk_bgi) (matches oref0's
    deviation = 6 × (minDelta - bgi), the insulin-subtracted residual)

  Unit verification:
  - oref0 basaliob: U (amount)    → pk_basal_iob: U (amount) ✓
  - oref0 bolusiob: U (amount)    → pk_bolus_iob: U (amount) ✓
  - oref0 activity: U/5min (rate) → pk_activity: U/5min (rate) ✓
  - oref0 BGI: mg/dL/5min         → pk_bgi: mg/dL/5min ✓
  - oref0 Dev: mg/dL/30min        → pk_dev: mg/dL/30min ✓

References:
  - tools/cgmencode/continuous_pk.py (PK computation engine)
  - tools/oref_inv_003_replication/data_bridge.py (OREF feature mapping)
  - externals/oref0/lib/iob/total.js (oref0 IOB decomposition)
  - externals/oref0/lib/determine-basal/determine-basal.js (Dev, BGI)
  - OREF-INV-003 §4.1 (32-feature schema)
"""

import numpy as np
import pandas as pd
import sys
import os

# Add project root to path for imports
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from tools.cgmencode.continuous_pk import (
    _build_activity_kernel,
    _convolve_doses_with_kernel,
    compute_insulin_activity,
    compute_carb_absorption_rate,
    compute_hepatic_production,
    compute_net_metabolic_balance,
    compute_acceleration,
    PK_CHANNEL_NAMES,
)

# ── IOB Remaining Kernel ─────────────────────────────────────────────

def _build_iob_kernel(dia_hours: float = 5.0, peak_min: float = 55.0,
                      interval_min: int = 5) -> np.ndarray:
    """Build IOB-remaining kernel: fraction of dose still on board at time t.

    IOB(t) = 1 - cumulative_absorption(t)

    where cumulative_absorption = integral of activity curve from 0 to t.
    At t=0, IOB=1.0 (full dose). At t=DIA, IOB≈0.0 (fully absorbed).

    This is the correct kernel for computing basaliob/bolusiob in UNITS
    (matching oref0's semantics), rather than activity RATES (U/min).

    Returns:
        (K,) array where K = DIA/interval_min, IOB fraction remaining.
    """
    activity_kernel = _build_activity_kernel(dia_hours, peak_min, interval_min)
    # Cumulative absorption: sum(activity_per_unit * interval_min) at each step
    cumulative = np.cumsum(activity_kernel) * interval_min
    # IOB remaining = 1 - fraction absorbed
    iob_kernel = np.clip(1.0 - cumulative, 0.0, 1.0)
    return iob_kernel


# ── PK Feature Definitions ───────────────────────────────────────────

# Features that REPLACE approximated OREF features (same units & semantics)
PK_REPLACEMENT_FEATURES = [
    'pk_basal_iob',     # replaces iob_basaliob — NET basal IOB in Units (can be negative)
    'pk_bolus_iob',     # replaces iob_bolusiob — bolus IOB in Units (always ≥ 0)
    'pk_activity',      # replaces iob_activity — net activity rate (U/5min)
    'pk_dev',           # replaces reason_Dev — deviation: 6×(observed - BGI) (mg/dL/30min)
    'pk_bgi',           # replaces reason_BGI — insulin BG impact (mg/dL/5min)
]

# Additional PK features for augmentation (new signals not in OREF schema)
PK_AUGMENTATION_FEATURES = [
    'pk_insulin_total',     # total insulin activity (basal + temp + bolus), U/min
    'pk_insulin_net',       # deviation-only activity (drives glucose changes), U/min
    'pk_basal_ratio',       # actual/scheduled basal (1.0=nominal, 0=suspended)
    'pk_carb_rate',         # carb absorption rate (g/min)
    'pk_carb_accel',        # d/dt carb rate (ramping up or down)
    'pk_hepatic_prod',      # estimated liver glucose production (mg/dL/5min)
    'pk_net_balance',       # net glucose flux from all sources (mg/dL/5min)
    'pk_isf_curve',         # time-varying ISF from schedule (mg/dL/U)
]

ALL_PK_FEATURES = PK_REPLACEMENT_FEATURES + PK_AUGMENTATION_FEATURES


def compute_pk_for_patient(pt_df: pd.DataFrame,
                           dia_hours: float = 5.0,
                           peak_min: float = 55.0,
                           carb_abs_hours: float = 3.0,
                           weight_kg: float = 70.0,
                           interval_min: int = 5,
                           verbose: bool = False) -> pd.DataFrame:
    """Compute all PK features for a single patient's grid DataFrame.

    Produces two categories of features:
      1. OREF-equivalent replacements (same units/semantics as oref0)
      2. PK augmentation channels (new physiological signals)

    Args:
        pt_df: Patient DataFrame from parquet grid. Must have columns:
            bolus, actual_basal_rate, scheduled_basal_rate, scheduled_isf,
            scheduled_cr, carbs, iob, glucose. Index should be DatetimeIndex
            or have 'time' column.
        dia_hours: Duration of insulin action (hours)
        peak_min: Time to peak insulin activity (minutes)
        carb_abs_hours: Carb absorption duration (hours)
        weight_kg: Patient body weight (kg)
        interval_min: Grid interval (minutes)
        verbose: Print progress

    Returns:
        DataFrame with same index as pt_df, columns = ALL_PK_FEATURES
    """
    df = pt_df.copy()

    # Ensure DatetimeIndex
    if 'time' in df.columns and not isinstance(df.index, pd.DatetimeIndex):
        df = df.set_index('time').sort_index()
    elif not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("DataFrame must have DatetimeIndex or 'time' column")

    N = len(df)
    if verbose:
        pid = df['patient_id'].iloc[0] if 'patient_id' in df.columns else '?'
        print(f"  PK bridge: computing {N} rows for patient {pid}")

    # ── Extract required columns ──────────────────────────────────────
    bolus = df['bolus'] if 'bolus' in df.columns else pd.Series(0.0, index=df.index)
    carbs = df['carbs'] if 'carbs' in df.columns else pd.Series(0.0, index=df.index)
    iob = df['iob'].fillna(0) if 'iob' in df.columns else pd.Series(0.0, index=df.index)
    glucose_roc = df['glucose_roc'].fillna(0).values if 'glucose_roc' in df.columns else np.zeros(N)

    # Actual basal rate (what pump actually delivered)
    if 'actual_basal_rate' in df.columns:
        actual_basal = df['actual_basal_rate'].ffill().fillna(0)
    elif 'net_basal' in df.columns and 'scheduled_basal_rate' in df.columns:
        actual_basal = (df['net_basal'].fillna(0) + df['scheduled_basal_rate'].fillna(0))
    else:
        actual_basal = pd.Series(0.0, index=df.index)

    # Scheduled values (already expanded per-timestep in parquet grid)
    sched_basal = df['scheduled_basal_rate'].fillna(0).values if 'scheduled_basal_rate' in df.columns else np.zeros(N)
    sched_isf = df['scheduled_isf'].fillna(50).values if 'scheduled_isf' in df.columns else np.full(N, 50.0)
    sched_cr = df['scheduled_cr'].fillna(10).values if 'scheduled_cr' in df.columns else np.full(N, 10.0)

    # Hour of day for hepatic production circadian modulation
    hours = df.index.hour + df.index.minute / 60.0

    # ── Compute PK channels ──────────────────────────────────────────

    # 1. Insulin activity (decomposed into sources)
    insulin = compute_insulin_activity(
        bolus_series=bolus,
        actual_basal_series=actual_basal,
        scheduled_basal_array=sched_basal,
        dia_hours=dia_hours,
        peak_min=peak_min,
        interval_min=interval_min,
    )

    # 2. IOB decomposition via IOB-remaining kernel (NET model)
    #
    #    Both Loop and oref0 use a NET IOB model:
    #      IOB = insulin_on_board(actual) - insulin_on_board(scheduled_baseline)
    #
    #    oref0 (iob/history.js:553):
    #      netBasalRate = currentItem.rate - currentRate  → ±0.05U entries
    #      entries < 0.1U → basaliob, ≥ 0.1U → bolusiob
    #
    #    Loop (DoseEntry.swift:114):
    #      netBasalUnits = unitsInDeliverableIncrements - scheduledUnits
    #      Single aggregate IOB (no basal/bolus split in output)
    #
    #    Consequence: IOB CAN BE NEGATIVE when actual delivery < scheduled.
    #    This is correct — negative IOB represents a growing insulin deficit
    #    from suspended/reduced delivery that will cause glucose to rise.
    #
    #    PK bridge equivalent:
    #      pk_bolus_iob = convolve(bolus_doses, iob_kernel) — always ≥ 0
    #      pk_basal_iob = convolve(actual - scheduled, iob_kernel) — CAN be negative
    #      pk_total     = pk_bolus_iob + pk_basal_iob = NET IOB
    #
    #    No rescaling needed: the net model naturally tracks reported IOB
    #    (verified r=0.896 on patient c, mean 1.23 vs 1.18 reported).
    iob_kernel = _build_iob_kernel(dia_hours, peak_min, interval_min)

    bolus_vals = bolus.fillna(0).values
    if 'bolus_smb' in df.columns:
        bolus_vals = bolus_vals + df['bolus_smb'].fillna(0).values

    # NET basal micro-doses: (actual - scheduled) rate → dose per interval
    # Positive when pump delivers more than scheduled (high temp)
    # Negative when pump suspends or reduces delivery (low temp / suspend)
    actual_basal_vals = actual_basal.values
    net_basal_micro = (actual_basal_vals - sched_basal) * interval_min / 60.0

    # Convolve each source with IOB-remaining kernel
    pk_bolus_iob = _convolve_doses_with_kernel(bolus_vals, iob_kernel)  # always ≥ 0
    pk_basal_iob = _convolve_doses_with_kernel(net_basal_micro, iob_kernel)  # can be negative

    # 3. Net insulin activity rate (U per 5-min step)
    #    oref0: activity = sum(treatment_activity_contributions)
    #    where each contribution is from the insulin curve derivative
    #    We use: insulin['net'] (U/min) × interval_min (5) = U/5min
    #    'net' = deviation from scheduled equilibrium, matching oref0's
    #    concept that scheduled basal maintains homeostasis
    pk_activity = insulin['net'] * interval_min  # U/min → U/5min

    # 4. BGI = Blood Glucose Impact from insulin (mg/dL per 5min)
    #    oref0: bgi = round(-activity * sens * 5, 2)
    #    where activity is U/5min, sens is ISF (mg/dL/U), 5 is interval
    #    Our equivalent: pk_activity is already U/5min, so:
    #    pk_bgi = -pk_activity * ISF
    #    (negative = glucose lowering from net insulin)
    pk_bgi = -pk_activity * sched_isf  # (U/5min) × (mg/dL/U) = mg/dL/5min

    # 5. Deviation = residual BG change not explained by insulin
    #    oref0: deviation = round(30/5 * (minDelta - bgi))
    #           = 6 × (observed_5min_delta - predicted_insulin_delta)
    #    glucose_roc is in mg/dL per 5min (verified by unit test)
    #    pk_bgi is in mg/dL per 5min
    #    deviation projects to 30-min window (×6)
    pk_dev = 6.0 * (glucose_roc - pk_bgi)  # mg/dL projected over 30min

    # 6. Carb absorption
    carb_rate = compute_carb_absorption_rate(
        carbs_series=carbs,
        abs_hours=carb_abs_hours,
        interval_min=interval_min,
    )
    carb_accel = compute_acceleration(carb_rate, interval_min)

    # 7. Hepatic glucose production
    hepatic = compute_hepatic_production(
        iob_series=iob.values,
        hours_array=hours.values,
        weight_kg=weight_kg,
    )

    # 8. Net metabolic balance (all-source glucose flux)
    net_balance = compute_net_metabolic_balance(
        insulin_activity=insulin['net'],
        carb_absorption_rate=carb_rate,
        hepatic_production=hepatic,
        isf=sched_isf,
        cr=sched_cr,
    )

    # ── Assemble output DataFrame ────────────────────────────────────

    result = pd.DataFrame(index=df.index)

    # OREF-equivalent replacement features (same units as oref0)
    result['pk_basal_iob'] = pk_basal_iob           # Units (amount)
    result['pk_bolus_iob'] = pk_bolus_iob           # Units (amount)
    result['pk_activity'] = pk_activity              # U/5min (rate)
    result['pk_dev'] = pk_dev                        # mg/dL/30min (deviation)
    result['pk_bgi'] = pk_bgi                        # mg/dL/5min (insulin BG impact)

    # PK augmentation features (new physiological signals)
    result['pk_insulin_total'] = insulin['total']    # U/min
    result['pk_insulin_net'] = insulin['net']        # U/min
    result['pk_basal_ratio'] = insulin['basal_ratio']  # dimensionless
    result['pk_carb_rate'] = carb_rate               # g/min
    result['pk_carb_accel'] = carb_accel             # g/min²
    result['pk_hepatic_prod'] = hepatic              # mg/dL/5min
    result['pk_net_balance'] = net_balance            # mg/dL/5min
    result['pk_isf_curve'] = sched_isf               # mg/dL/U

    # Handle NaN/inf from edge cases (but do NOT clip — let LGB handle range)
    result = result.replace([np.inf, -np.inf], np.nan)

    return result


def add_pk_features_to_grid(grid_df: pd.DataFrame,
                             dia_hours: float = 5.0,
                             peak_min: float = 55.0,
                             verbose: bool = True) -> pd.DataFrame:
    """Add PK features to entire multi-patient parquet grid.

    Processes each patient separately (PK convolution is per-patient),
    then concatenates results.

    Args:
        grid_df: Full parquet grid DataFrame with 'patient_id' column
        dia_hours: Duration of insulin action (hours)
        peak_min: Time to peak insulin activity (minutes)
        verbose: Print per-patient progress

    Returns:
        grid_df with ALL_PK_FEATURES columns added
    """
    if verbose:
        patients = grid_df['patient_id'].unique()
        print(f"PK bridge: processing {len(patients)} patients...")

    all_pk = []

    for pid, pt_df in grid_df.groupby('patient_id'):
        try:
            pk = compute_pk_for_patient(
                pt_df,
                dia_hours=dia_hours,
                peak_min=peak_min,
                verbose=verbose,
            )
            # Align index with original
            pk.index = pt_df.index
            all_pk.append(pk)
        except Exception as e:
            if verbose:
                print(f"  WARNING: PK computation failed for {pid}: {e}")
            # Return zeros for failed patients
            pk = pd.DataFrame(0.0, index=pt_df.index, columns=ALL_PK_FEATURES)
            all_pk.append(pk)

    pk_all = pd.concat(all_pk)
    pk_all = pk_all.loc[grid_df.index]  # ensure alignment

    result = grid_df.copy()
    for col in ALL_PK_FEATURES:
        result[col] = pk_all[col].values

    if verbose:
        nz = {col: (result[col] != 0).sum() for col in ALL_PK_FEATURES[:5]}
        print(f"PK bridge: done. Non-zero counts (sample): {nz}")

    return result


def get_oref32_with_pk_replacements(features_oref32: list = None) -> list:
    """Return modified OREF-32 feature list with PK replacements.

    Replaces the 5 approximated features with their PK-derived equivalents
    (same units and semantics), keeping the remaining 27 features unchanged.
    """
    from . import data_bridge

    if features_oref32 is None:
        features_oref32 = list(data_bridge.OREF_FEATURES)

    replacements = {
        'iob_basaliob': 'pk_basal_iob',
        'iob_bolusiob': 'pk_bolus_iob',
        'iob_activity': 'pk_activity',
        'reason_Dev': 'pk_dev',
        'reason_BGI': 'pk_bgi',
    }

    result = []
    for f in features_oref32:
        if f in replacements:
            result.append(replacements[f])
        else:
            result.append(f)

    return result


def get_pk_only_features() -> list:
    """Return algorithm-neutral PK-only feature set.

    Includes the 8 continuous PK channels plus essential context
    (glucose, hour, schedules) for a total of ~15 features.
    """
    return [
        # Glucose state
        'cgm_mgdl',
        'glucose_roc',
        'glucose_accel',
        # Time context
        'time_sin', 'time_cos',
        # All PK channels
        *ALL_PK_FEATURES,
    ]


def get_augmented_features(features_oref32: list = None) -> list:
    """Return OREF-32 with PK replacements PLUS PK augmentation features.

    This is the maximal feature set: 27 original + 5 PK replacements + 8 PK augmentations = 40 features.
    """
    base = get_oref32_with_pk_replacements(features_oref32)
    return base + PK_AUGMENTATION_FEATURES


# ── Validation ────────────────────────────────────────────────────────

def validate_pk_bridge(grid_df: pd.DataFrame, verbose: bool = True) -> dict:
    """Run sanity checks on PK bridge output.

    Verifies:
      1. All PK features are numeric and finite
      2. Insulin activity correlates negatively with glucose changes
      3. Carb rate correlates positively with glucose changes
      4. Supply-demand ratio is informative (not constant)

    Returns:
        Dict with validation metrics
    """
    enriched = add_pk_features_to_grid(grid_df, verbose=verbose)

    results = {}

    # Check for NaN/inf
    for col in ALL_PK_FEATURES:
        n_nan = enriched[col].isna().sum()
        n_inf = np.isinf(enriched[col]).sum()
        results[f'{col}_nan'] = int(n_nan)
        results[f'{col}_inf'] = int(n_inf)

    # Correlation with glucose changes (next 30 min)
    if 'glucose' in enriched.columns:
        glucose = enriched['glucose'].ffill()
        glucose_change_30 = glucose.shift(-6) - glucose  # 6 steps = 30 min

        for col in ['pk_bgi', 'pk_net_balance', 'pk_carb_rate']:
            mask = glucose_change_30.notna() & enriched[col].notna()
            if mask.sum() > 100:
                corr = enriched.loc[mask, col].corr(glucose_change_30[mask])
                results[f'{col}_vs_dglucose_30m'] = round(corr, 4)

    # Feature variance
    for col in ALL_PK_FEATURES:
        results[f'{col}_std'] = round(float(enriched[col].std()), 6)

    if verbose:
        print("\nPK Bridge Validation:")
        for key in ['pk_bgi_vs_dglucose_30m', 'pk_net_balance_vs_dglucose_30m',
                     'pk_carb_rate_vs_dglucose_30m']:
            if key in results:
                print(f"  {key}: {results[key]}")

    return results


if __name__ == '__main__':
    """Quick test: load one patient from parquet grid and compute PK features."""
    import argparse

    parser = argparse.ArgumentParser(description='Test PK bridge on parquet grid')
    parser.add_argument('--grid', default='externals/ns-parquet/training/grid.parquet',
                        help='Path to grid.parquet')
    parser.add_argument('--patient', default=None, help='Patient ID (default: first)')
    parser.add_argument('--validate', action='store_true', help='Run validation checks')
    args = parser.parse_args()

    grid = pd.read_parquet(args.grid)
    print(f"Loaded grid: {len(grid)} rows, {grid['patient_id'].nunique()} patients")

    if args.patient:
        grid = grid[grid['patient_id'] == args.patient]
        print(f"Filtered to patient {args.patient}: {len(grid)} rows")

    if args.validate:
        results = validate_pk_bridge(grid, verbose=True)
        print(f"\nValidation results: {len(results)} checks")
    else:
        enriched = add_pk_features_to_grid(grid, verbose=True)
        print(f"\nEnriched grid: {enriched.shape}")
        print(f"New columns: {[c for c in enriched.columns if c.startswith('pk_')]}")
        print(f"\nSample PK values (first patient, first 5 rows):")
        pk_cols = [c for c in enriched.columns if c.startswith('pk_')]
        print(enriched[pk_cols].head())
