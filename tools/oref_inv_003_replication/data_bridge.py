"""
data_bridge.py — Bridge ns-parquet grid data to the OREF-INV-003 32-feature schema.

The ns-parquet grid (803 895 rows × 49 cols) contains data from both Loop (patients a–k)
and AAPS/oref (patients odc-*) systems.  The OREF-INV-003 study trained LightGBM hypo-
prediction models on a 32-feature vector extracted from OpenAPS suggestion/IOB/meal
documents.  This module maps our grid columns onto that schema so we can:

  1. Train comparable models on our data.
  2. Run OREF-INV-003's pre-trained models on our data.

Every approximation is documented in its docstring and tracked in
``FEATURE_QUALITY``.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STEPS_PER_HOUR: int = 12          # 5-minute CGM intervals
STEPS_4H: int = STEPS_PER_HOUR * 4  # 48 steps = 4 hours

OREF_FEATURES: List[str] = [
    "cgm_mgdl",
    "sug_current_target",
    "sug_ISF",
    "sug_CR",
    "sug_sensitivityRatio",
    "sug_rate",
    "sug_duration",
    "sug_insulinReq",
    "sug_eventualBG",
    "sug_threshold",
    "iob_iob",
    "iob_basaliob",
    "iob_bolusiob",
    "iob_activity",
    "sug_COB",
    "reason_Dev",
    "reason_BGI",
    "reason_minGuardBG",
    "direction_num",
    "hour",
    "has_dynisf",
    "has_smb",
    "has_uam",
    "bg_above_target",
    "isf_ratio",
    "iob_pct_max",
    "sr_deviation",
    "dynisf_x_sr",
    "dynisf_x_isf_ratio",
    "maxSMBBasalMinutes",
    "maxUAMSMBBasalMinutes",
    "sug_smb_units",
]

DIRECTION_MAP: Dict[str, float] = {
    "DoubleDown": -2.0,
    "SingleDown": -1.5,
    "FortyFiveDown": -1.0,
    "Flat": 0.0,
    "FortyFiveUp": 1.0,
    "SingleUp": 1.5,
    "DoubleUp": 2.0,
    "NONE": 0.0,
    "NOT COMPUTABLE": 0.0,
}

# ---------------------------------------------------------------------------
# Feature quality registry — records how each OREF feature is produced.
#
#   "direct"       – 1:1 column mapping, high fidelity
#   "derived"      – calculated from available columns, moderate fidelity
#   "approximated" – heuristic stand-in, lower fidelity
#   "constant"     – fixed default value, placeholder only
# ---------------------------------------------------------------------------

FEATURE_QUALITY: Dict[str, str] = {
    "cgm_mgdl":              "direct",
    "sug_current_target":    "derived",
    "sug_ISF":               "direct",
    "sug_CR":                "direct",
    "sug_sensitivityRatio":  "direct",
    "sug_rate":              "direct",
    "sug_duration":          "derived",
    "sug_insulinReq":        "direct",
    "sug_eventualBG":        "direct",
    "sug_threshold":         "derived",
    "iob_iob":               "direct",
    "iob_basaliob":          "approximated",
    "iob_bolusiob":          "approximated",
    "iob_activity":          "approximated",
    "sug_COB":               "direct",
    "reason_Dev":            "approximated",
    "reason_BGI":            "approximated",
    "reason_minGuardBG":     "derived",
    "direction_num":         "derived",
    "hour":                  "derived",
    "has_dynisf":            "derived",
    "has_smb":               "derived",
    "has_uam":               "derived",
    "bg_above_target":       "direct",
    "isf_ratio":             "derived",
    "iob_pct_max":           "derived",
    "sr_deviation":          "derived",
    "dynisf_x_sr":           "derived",
    "dynisf_x_isf_ratio":    "derived",
    "maxSMBBasalMinutes":    "constant",
    "maxUAMSMBBasalMinutes": "constant",
    "sug_smb_units":         "direct",
}

assert set(FEATURE_QUALITY) == set(OREF_FEATURES), "Quality dict / feature list mismatch"


# ---------------------------------------------------------------------------
# Loading helpers
# ---------------------------------------------------------------------------

def load_grid(parquet_path: str = "externals/ns-parquet/training") -> pd.DataFrame:
    """Load grid.parquet from *parquet_path* and return a DataFrame.

    Expects either a directory containing ``grid.parquet`` or a direct path
    to a ``.parquet`` file.  Prints row/column counts on load.
    """
    p = Path(parquet_path)
    if p.is_dir():
        p = p / "grid.parquet"
    if not p.exists():
        raise FileNotFoundError(f"Grid parquet not found at {p}")

    print(f"[data_bridge] Loading {p} …")
    df = pd.read_parquet(p)
    print(f"[data_bridge] Loaded {len(df):,} rows × {len(df.columns)} cols")
    return df


# ---------------------------------------------------------------------------
# Core feature builder
# ---------------------------------------------------------------------------

def build_oref_features(grid_df: pd.DataFrame) -> pd.DataFrame:
    """Map ns-parquet grid columns to the OREF-INV-003 32-feature schema.

    Parameters
    ----------
    grid_df : pd.DataFrame
        Raw grid data with columns documented in the module docstring.

    Returns
    -------
    pd.DataFrame
        A copy of *grid_df* with the 32 OREF features appended (plus
        ``patient_id`` and ``time`` retained for downstream joins).

    Notes
    -----
    Columns that cannot be mapped perfectly are approximated; see
    ``FEATURE_QUALITY`` for per-feature fidelity ratings.
    """
    df = grid_df.copy()
    n = len(df)

    # Convenience accessors (avoid repeated getattr)
    glucose: pd.Series = df["glucose"].astype("float64")
    iob: pd.Series = df["iob"].astype("float64").fillna(0.0)
    cob: pd.Series = df["cob"].astype("float64").fillna(0.0)
    glucose_roc: pd.Series = df["glucose_roc"].astype("float64").fillna(0.0)
    glucose_vs_target: pd.Series = df["glucose_vs_target"].astype("float64").fillna(0.0)
    scheduled_isf: pd.Series = df["scheduled_isf"].astype("float64")
    scheduled_cr: pd.Series = df["scheduled_cr"].astype("float64")
    net_basal: pd.Series = df["net_basal"].astype("float64").fillna(0.0)
    actual_basal: pd.Series = df["actual_basal_rate"].astype("float64").fillna(0.0)
    bolus: pd.Series = df["bolus"].astype("float64").fillna(0.0)
    bolus_smb: pd.Series = df["bolus_smb"].astype("float64").fillna(0.0)
    sensitivity_ratio: pd.Series = df["sensitivity_ratio"].astype("float64")
    patient_id: pd.Series = df["patient_id"]

    is_odc = patient_id.str.startswith("odc", na=False)

    # ------------------------------------------------------------------
    # 1. Direct mappings
    # ------------------------------------------------------------------
    df["cgm_mgdl"] = glucose
    df["sug_ISF"] = scheduled_isf
    df["sug_CR"] = scheduled_cr
    # sensitivity_ratio is sparse (~130K/803K non-null).
    # Fill NaN with 1.0 (no sensitivity adjustment) — the neutral value.
    df["sug_sensitivityRatio"] = sensitivity_ratio.fillna(1.0)
    df["sug_rate"] = actual_basal
    # insulin_req is sparse; 0 means "no additional insulin needed".
    df["sug_insulinReq"] = df["insulin_req"].astype("float64").fillna(0.0)
    # eventual_bg is sparse (~186K non-null, mostly Loop patients).
    # Fill NaN with current glucose (best available estimate when no
    # prediction is present).
    df["sug_eventualBG"] = df["eventual_bg"].astype("float64").fillna(glucose)
    df["iob_iob"] = iob
    df["sug_COB"] = cob
    df["bg_above_target"] = glucose_vs_target
    df["sug_smb_units"] = bolus_smb

    # ------------------------------------------------------------------
    # 2. Derived features
    # ------------------------------------------------------------------

    # --- target & threshold ---
    # glucose_vs_target = glucose - target  →  target = glucose - glucose_vs_target
    target = glucose - glucose_vs_target
    df["sug_current_target"] = target

    # sug_threshold: the BG level at which the algorithm starts suspending.
    # oref formula: target - 0.5*(target - 40), clamped to ≥60.
    df["sug_threshold"] = (target - 0.5 * (target - 40.0)).clip(lower=60.0)

    # --- hour (from time column) ---
    time_col = pd.to_datetime(df["time"], utc=True)
    df["hour"] = time_col.dt.hour.astype("float64")

    # --- direction_num ---
    # Prefer the `direction` string column mapped through DIRECTION_MAP.
    # Fall back to `trend_direction` (float) when direction is missing.
    if "direction" in df.columns:
        mapped = df["direction"].map(DIRECTION_MAP)
        if "trend_direction" in df.columns:
            fallback = df["trend_direction"].astype("float64")
            df["direction_num"] = mapped.fillna(fallback).fillna(0.0)
        else:
            df["direction_num"] = mapped.fillna(0.0)
    elif "trend_direction" in df.columns:
        df["direction_num"] = df["trend_direction"].astype("float64").fillna(0.0)
    else:
        df["direction_num"] = 0.0

    # --- sug_duration ---
    # In oref, sug_duration is the minutes remaining on a temp basal.
    # We approximate: 30 min when a temp basal is active (rate > 0), else 0.
    df["sug_duration"] = np.where(actual_basal > 0, 30.0, 0.0)

    # --- IOB decomposition (approximated) ---
    # oref tracks basal-IOB and bolus-IOB separately.  Our grid only has
    # total IOB plus net_basal (deviation from scheduled) and bolus columns.
    #
    # Heuristic: partition total IOB proportionally by the magnitude of
    # basal-deviation vs bolus activity.  The denominator includes a small
    # epsilon (0.001) to avoid division by zero.
    abs_net = net_basal.abs()
    abs_bolus_total = bolus.abs() + bolus_smb.abs()
    denom = abs_net + abs_bolus_total + 0.001
    basal_frac = abs_net / denom
    df["iob_basaliob"] = iob * basal_frac
    df["iob_bolusiob"] = iob * (1.0 - basal_frac)

    # --- iob_activity (approximated) ---
    # Insulin activity ≈ rate of BG change attributable to insulin.
    # In oref: activity = IOB decay rate, units U/5min.  The BG effect of
    # activity is  activity * ISF = BGI.
    # We approximate activity from observed BG rate of change and ISF:
    #   glucose_roc ≈ -activity * ISF  →  activity ≈ -glucose_roc / ISF
    # This conflates food absorption with insulin action, but is the best
    # we can do without the raw insulin curve.
    safe_isf = scheduled_isf.clip(lower=1.0)  # avoid /0
    df["iob_activity"] = (-glucose_roc / safe_isf)

    # --- has_dynisf ---
    # Loop does not use Dynamic ISF.  ODC patients *may* use it; we detect
    # DynISF by checking whether sensitivity_ratio varies within a patient.
    # If a patient has >1 distinct non-null sensitivity_ratio, assume DynISF.
    sr_nunique = (
        df.groupby("patient_id")["sensitivity_ratio"]
        .transform(lambda s: s.dropna().nunique())
    )
    df["has_dynisf"] = np.where(is_odc & (sr_nunique > 1), 1.0, 0.0)

    # --- has_smb ---
    df["has_smb"] = np.where(bolus_smb > 0, 1.0, 0.0)

    # --- has_uam ---
    # Loop does not support UAM.  For oref/AAPS patients: UAM is active
    # when there are no announced carbs (COB=0) and glucose is rising.
    df["has_uam"] = np.where(
        is_odc & (cob == 0) & (glucose_roc > 0),
        1.0,
        0.0,
    )

    # --- isf_ratio ---
    # Ratio of effective ISF to profile ISF.  Without DynISF the ratio is 1.
    # With DynISF it equals sensitivity_ratio (which scales ISF).
    df["isf_ratio"] = np.where(
        df["has_dynisf"] == 1.0,
        df["sug_sensitivityRatio"],
        1.0,
    )

    # --- iob_pct_max ---
    # Fraction of patient's observed max IOB.
    max_iob_per_patient = df.groupby("patient_id")["iob"].transform("max")
    safe_max_iob = max_iob_per_patient.clip(lower=0.01)  # avoid /0
    df["iob_pct_max"] = iob / safe_max_iob

    # --- sr_deviation ---
    # How far sensitivity_ratio is from neutral (1.0).
    df["sr_deviation"] = (sensitivity_ratio.fillna(1.0) - 1.0).abs()

    # --- interaction terms ---
    df["dynisf_x_sr"] = df["has_dynisf"] * df["sug_sensitivityRatio"]
    df["dynisf_x_isf_ratio"] = df["has_dynisf"] * df["isf_ratio"]

    # --- reason_Dev (approximated) ---
    # oref "deviation" = (observed BG change) - (expected BG change from IOB).
    # glucose_roc is a per-5-min rate.  We scale by 5 to get a 5-min delta,
    # consistent with oref's 5-min loop interval.
    df["reason_Dev"] = glucose_roc * 5.0

    # --- reason_BGI (approximated) ---
    # Blood Glucose Impact of insulin = -activity * ISF.
    # Since we already computed iob_activity ≈ -glucose_roc/ISF:
    #   BGI = -iob_activity * ISF  =  glucose_roc  (circular, but correct in
    # magnitude for the features the model actually sees).
    # More faithfully: BGI should reflect only the insulin component of BG
    # change.  We keep the explicit formula for clarity.
    df["reason_BGI"] = -df["iob_activity"] * scheduled_isf

    # --- reason_minGuardBG ---
    # The minimum predicted BG used by oref's safety guard.
    # We use Loop's 'loop_predicted_min' where available; fill NaN with a
    # conservative estimate (glucose − 10).
    if "loop_predicted_min" in df.columns:
        df["reason_minGuardBG"] = (
            df["loop_predicted_min"].astype("float64").fillna(glucose - 10.0)
        )
    else:
        df["reason_minGuardBG"] = glucose - 10.0

    # --- constants (not available in our data) ---
    df["maxSMBBasalMinutes"] = 30.0
    df["maxUAMSMBBasalMinutes"] = 30.0

    # ------------------------------------------------------------------
    # Sanity: ensure all 32 features are present
    # ------------------------------------------------------------------
    missing = set(OREF_FEATURES) - set(df.columns)
    if missing:
        raise RuntimeError(f"Missing OREF features after build: {missing}")

    return df


# ---------------------------------------------------------------------------
# 4-hour outcome labels
# ---------------------------------------------------------------------------

def compute_4h_outcomes(df: pd.DataFrame) -> pd.DataFrame:
    """Compute forward-looking outcome labels per patient.

    For each row we look 4 hours (48 × 5-min steps) ahead **within the same
    patient** and compute:

    * ``hypo_4h``      — 1 if any glucose < 70 mg/dL in the next 4 h, else 0.
    * ``hyper_4h``     — 1 if any glucose > 180 mg/dL in the next 4 h, else 0.
    * ``bg_change_4h`` — glucose at +4 h minus current glucose (NaN if the
      patient's time-series does not extend 4 h ahead of this row).

    Parameters
    ----------
    df : pd.DataFrame
        Must contain ``patient_id``, ``time``, and ``glucose``.

    Returns
    -------
    pd.DataFrame
        The input DataFrame with three new columns appended.
    """
    df = df.copy()
    df["hypo_4h"] = np.nan
    df["hyper_4h"] = np.nan
    df["bg_change_4h"] = np.nan

    patients = df["patient_id"].unique()
    n_patients = len(patients)

    for idx, pid in enumerate(patients, 1):
        if idx % 5 == 1 or idx == n_patients:
            print(
                f"[data_bridge] Computing 4 h outcomes: patient {idx}/{n_patients} "
                f"({pid})"
            )
        mask = df["patient_id"] == pid
        g = df.loc[mask, "glucose"].values.astype("float64")
        n = len(g)

        hypo = np.zeros(n, dtype="float64")
        hyper = np.zeros(n, dtype="float64")
        bg_change = np.full(n, np.nan, dtype="float64")

        for i in range(n):
            end = min(i + STEPS_4H + 1, n)
            window = g[i + 1 : end]  # exclude current row
            if len(window) == 0:
                hypo[i] = np.nan
                hyper[i] = np.nan
                continue
            hypo[i] = 1.0 if np.nanmin(window) < 70.0 else 0.0
            hyper[i] = 1.0 if np.nanmax(window) > 180.0 else 0.0
            # bg_change_4h requires a reading at exactly +48 steps
            if i + STEPS_4H < n and not np.isnan(g[i + STEPS_4H]):
                bg_change[i] = g[i + STEPS_4H] - g[i]

        df.loc[mask, "hypo_4h"] = hypo
        df.loc[mask, "hyper_4h"] = hyper
        df.loc[mask, "bg_change_4h"] = bg_change

    return df


# ---------------------------------------------------------------------------
# Multi-horizon outcome labels
# ---------------------------------------------------------------------------

HORIZON_MAP = {
    "30min": 6,    # 6 × 5-min
    "1h":    12,   # 12 × 5-min
    "2h":    24,   # 24 × 5-min
    "4h":    48,   # 48 × 5-min
}


def compute_multi_horizon_outcomes(
    df: pd.DataFrame,
    horizons: Optional[Dict[str, int]] = None,
) -> pd.DataFrame:
    """Compute forward-looking hypo/hyper labels at multiple horizons.

    For each horizon *h* the function creates:

    * ``hypo_{h}``      — 1 if any glucose < 70 mg/dL in the next *h*, else 0.
    * ``hyper_{h}``     — 1 if any glucose > 180 mg/dL in the next *h*, else 0.
    * ``bg_change_{h}`` — glucose at +*h* minus current glucose.

    The default horizons are 30 min, 1 h, 2 h, and 4 h.

    Parameters
    ----------
    df : pd.DataFrame
        Must contain ``patient_id``, ``time``, and ``glucose``.
    horizons : dict, optional
        Mapping of label → number of 5-min steps.  Defaults to
        ``HORIZON_MAP`` (30 min, 1 h, 2 h, 4 h).

    Returns
    -------
    pd.DataFrame
        The input DataFrame with outcome columns for every horizon.
    """
    if horizons is None:
        horizons = HORIZON_MAP

    df = df.copy()
    for label in horizons:
        df[f"hypo_{label}"] = np.nan
        df[f"hyper_{label}"] = np.nan
        df[f"bg_change_{label}"] = np.nan

    patients = df["patient_id"].unique()
    n_patients = len(patients)
    max_steps = max(horizons.values())

    for p_idx, pid in enumerate(patients, 1):
        if p_idx % 5 == 1 or p_idx == n_patients:
            print(
                f"[data_bridge] Multi-horizon outcomes: patient "
                f"{p_idx}/{n_patients} ({pid})"
            )
        mask = df["patient_id"] == pid
        g = df.loc[mask, "glucose"].values.astype("float64")
        n = len(g)

        # Pre-compute cumulative min/max for efficiency
        # For each horizon we only need to scan up to that many steps ahead
        for label, steps in horizons.items():
            hypo = np.full(n, np.nan, dtype="float64")
            hyper = np.full(n, np.nan, dtype="float64")
            bg_change = np.full(n, np.nan, dtype="float64")

            for i in range(n):
                end = min(i + steps + 1, n)
                window = g[i + 1 : end]
                if len(window) == 0:
                    continue
                hypo[i] = 1.0 if np.nanmin(window) < 70.0 else 0.0
                hyper[i] = 1.0 if np.nanmax(window) > 180.0 else 0.0
                if i + steps < n and not np.isnan(g[i + steps]):
                    bg_change[i] = g[i + steps] - g[i]

            df.loc[mask, f"hypo_{label}"] = hypo
            df.loc[mask, f"hyper_{label}"] = hyper
            df.loc[mask, f"bg_change_{label}"] = bg_change

    return df


def load_patients_multi_horizon(
    parquet_path: str = "externals/ns-parquet/training",
    horizons: Optional[Dict[str, int]] = None,
) -> pd.DataFrame:
    """Load grid, build OREF features, compute outcomes at multiple horizons.

    Like ``load_patients_with_features`` but adds columns for every
    requested horizon (default: 30 min, 1 h, 2 h, 4 h).

    Parameters
    ----------
    parquet_path : str
        Path to directory containing ``grid.parquet``.
    horizons : dict, optional
        Label → steps mapping.  Defaults to ``HORIZON_MAP``.

    Returns
    -------
    pd.DataFrame
        Ready-to-model DataFrame with multi-horizon outcome columns.
    """
    grid = load_grid(parquet_path)
    print("[data_bridge] Building OREF-INV-003 features …")
    featured = build_oref_features(grid)
    print("[data_bridge] Computing multi-horizon outcome labels …")
    result = compute_multi_horizon_outcomes(featured, horizons)
    # Ensure backward-compatible 4h columns exist
    if "hypo_4h" not in result.columns and "hypo_4h" in (horizons or HORIZON_MAP):
        pass  # already created by multi-horizon with "4h" key
    print(f"[data_bridge] Done. Final shape: {result.shape}")
    return result


# ---------------------------------------------------------------------------
# Split helper
# ---------------------------------------------------------------------------

def split_loop_vs_oref(
    df: pd.DataFrame,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Split a DataFrame into Loop patients (a-k) and oref/AAPS patients (odc-*).

    Parameters
    ----------
    df : pd.DataFrame
        Must contain a ``patient_id`` column.

    Returns
    -------
    loop_df : pd.DataFrame
        Rows where ``patient_id`` matches single-letter Loop patients (a–k).
    oref_df : pd.DataFrame
        Rows where ``patient_id`` starts with ``odc``.
    """
    is_odc = df["patient_id"].str.startswith("odc", na=False)
    return df[~is_odc].copy(), df[is_odc].copy()


# ---------------------------------------------------------------------------
# High-level loader
# ---------------------------------------------------------------------------

def load_patients_with_features(
    parquet_path: str = "externals/ns-parquet/training",
) -> pd.DataFrame:
    """Load grid, build OREF features, compute 4 h outcomes.

    This is the primary entry-point for downstream modelling scripts.  It
    returns a DataFrame containing the original grid columns, the 32 OREF
    features, and the three outcome columns.

    Parameters
    ----------
    parquet_path : str
        Path to directory containing ``grid.parquet`` (or direct path).

    Returns
    -------
    pd.DataFrame
        Ready-to-model DataFrame.
    """
    grid = load_grid(parquet_path)
    print("[data_bridge] Building OREF-INV-003 features …")
    featured = build_oref_features(grid)
    print("[data_bridge] Computing 4 h outcome labels …")
    result = compute_4h_outcomes(featured)
    print(f"[data_bridge] Done. Final shape: {result.shape}")
    return result


# ---------------------------------------------------------------------------
# Reporting utilities
# ---------------------------------------------------------------------------

def feature_quality_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Return a summary table of OREF feature quality and NaN rates.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame with the 32 OREF features present (output of
        ``build_oref_features``).

    Returns
    -------
    pd.DataFrame
        One row per feature with columns: feature, quality, nan_count,
        nan_pct, mean, std, min, max.
    """
    rows = []
    n = len(df)
    for feat in OREF_FEATURES:
        col = df[feat]
        nan_ct = int(col.isna().sum())
        nan_pct = 100.0 * nan_ct / n if n > 0 else 0.0
        desc = col.describe()
        rows.append(
            {
                "feature": feat,
                "quality": FEATURE_QUALITY.get(feat, "unknown"),
                "nan_count": nan_ct,
                "nan_pct": round(nan_pct, 2),
                "mean": round(float(desc.get("mean", np.nan)), 4),
                "std": round(float(desc.get("std", np.nan)), 4),
                "min": round(float(desc.get("min", np.nan)), 4),
                "max": round(float(desc.get("max", np.nan)), 4),
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Self-test / CLI
# ---------------------------------------------------------------------------

def _print_section(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    import sys

    path = sys.argv[1] if len(sys.argv) > 1 else "externals/ns-parquet/training"

    _print_section("1. Load grid")
    grid = load_grid(path)

    _print_section("2. Build OREF-INV-003 features")
    featured = build_oref_features(grid)

    _print_section("3. Feature quality summary")
    summary = feature_quality_summary(featured)
    quality_counts = summary["quality"].value_counts()
    print("\nFeature provenance breakdown:")
    for q, ct in quality_counts.items():
        print(f"  {q:15s}: {ct}")
    print(f"\n{'Feature':<30s} {'Quality':<14s} {'NaN%':>7s} {'Mean':>10s} {'Std':>10s}")
    print("-" * 75)
    for _, row in summary.iterrows():
        print(
            f"{row['feature']:<30s} {row['quality']:<14s} "
            f"{row['nan_pct']:>6.2f}% "
            f"{row['mean']:>10.4f} {row['std']:>10.4f}"
        )

    _print_section("4. Split Loop vs oref")
    loop_df, oref_df = split_loop_vs_oref(featured)
    print(f"  Loop patients : {loop_df['patient_id'].nunique()} patients, "
          f"{len(loop_df):,} rows")
    print(f"  oref patients : {oref_df['patient_id'].nunique()} patients, "
          f"{len(oref_df):,} rows")

    _print_section("5. Compute 4 h outcomes (may take a minute)")
    result = compute_4h_outcomes(featured)
    for col in ("hypo_4h", "hyper_4h", "bg_change_4h"):
        non_null = result[col].notna().sum()
        print(f"  {col}: {non_null:,} non-null values")
        if col in ("hypo_4h", "hyper_4h"):
            rate = result[col].mean()
            print(f"    positive rate: {rate:.4f}" if not np.isnan(rate) else "    (all NaN)")
        else:
            print(f"    mean Δ: {result[col].mean():.2f} mg/dL"
                  if not np.isnan(result[col].mean()) else "    (all NaN)")

    _print_section("Done")
    print(f"Final DataFrame: {result.shape[0]:,} rows × {result.shape[1]} cols")
    print(f"OREF features present: {sum(f in result.columns for f in OREF_FEATURES)}/32")
