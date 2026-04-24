"""Per-patient on-demand fact computation.

Reuses per-patient functions from research EXP scripts so that any
patient with a `grid.parquet` (and optionally `treatments.parquet`) can
have facts computed inline without re-running the full cohort pipeline.

Design: every helper takes a single-patient DataFrame and returns a
plain dict whose keys are the columns of the corresponding research
artifact (e.g. exp-2861_bootstrap_isf_gap.parquet). FactsLoaders adapt
those dicts into their dataclass.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd


# ─── ISF-Gap (EXP-2847 + EXP-2861) ────────────────────────────────────────

_ISF_N_BOOT = 500
_ISF_THRESH_UNDER = -10.0
_ISF_THRESH_OVER = +30.0
_ISF_MIN_EVENTS = 20


def _find_correction_events(g: pd.DataFrame) -> pd.DataFrame:
    """Port of exp_flat_isf_audit_2847.find_correction_events for one patient."""
    sub = g.sort_values("time").reset_index(drop=True)
    total_bolus = sub.get("bolus", 0).fillna(0) + sub.get("bolus_smb", 0).fillna(0)
    recent_carbs = (
        sub.get("carbs", 0).fillna(0).rolling(6, min_periods=1).sum().shift(1)
    )
    is_corr = (
        (total_bolus >= 0.5)
        & (sub["glucose"] >= 180)
        & (recent_carbs.fillna(0) < 5)
    )
    rows = []
    sched_col = "scheduled_isf" if "scheduled_isf" in sub.columns else None
    for i in np.where(is_corr.values)[0]:
        end = min(i + 36, len(sub) - 1)
        win = sub.iloc[i:end + 1]
        if win["carbs"].fillna(0).sum() > 10:
            continue
        bg_start = sub["glucose"].iat[i]
        bg_min = win["glucose"].min()
        drop = bg_start - bg_min
        bolus = float(total_bolus.iat[i])
        sched_isf = float(sub[sched_col].iat[i]) if sched_col else np.nan
        obs_isf = drop / max(bolus, 0.01)
        rows.append({
            "drop": float(drop),
            "bolus": bolus,
            "obs_isf": float(obs_isf),
            "sched_isf": sched_isf,
        })
    return pd.DataFrame(rows)


def compute_isf_gap_bootstrap(
    grid_df: pd.DataFrame,
    *,
    seed: int = 2861,
) -> Optional[dict]:
    """Per-patient ISF-gap bootstrap (EXP-2861) directly from grid.

    Returns dict with the columns of exp-2861_bootstrap_isf_gap.parquet,
    or None if the patient has too few correction events.
    """
    ev = _find_correction_events(grid_df)
    if ev.empty:
        return None
    ev = ev[(ev["drop"] > 0) & (ev["bolus"] > 0) & (ev["sched_isf"] > 0)]
    if ev.empty:
        return None
    ev = ev.assign(gap_pct=100.0 * (ev["obs_isf"] - ev["sched_isf"]) / ev["sched_isf"])
    gaps = ev["gap_pct"].dropna().to_numpy()
    n = len(gaps)
    if n < _ISF_MIN_EVENTS:
        return {
            "n_events": int(n),
            "point_median_gap_pct": float(np.median(gaps)) if n else None,
            "p_under_correction": None,
            "p_over_correction": None,
            "p_within_band": None,
            "_insufficient": True,
        }
    rng = np.random.default_rng(seed)
    boot = np.array([
        np.median(gaps[rng.integers(0, n, size=n)]) for _ in range(_ISF_N_BOOT)
    ])
    return {
        "n_events": int(n),
        "point_median_gap_pct": float(np.median(gaps)),
        "boot_median_mean": float(boot.mean()),
        "boot_median_ci_lo": float(np.quantile(boot, 0.025)),
        "boot_median_ci_hi": float(np.quantile(boot, 0.975)),
        "p_under_correction": float(np.mean(boot < _ISF_THRESH_UNDER)),
        "p_over_correction": float(np.mean(boot > _ISF_THRESH_OVER)),
        "p_within_band": float(np.mean(
            (boot >= _ISF_THRESH_UNDER) & (boot <= _ISF_THRESH_OVER)
        )),
    }


# ─── Basal Mismatch (EXP-2869) ────────────────────────────────────────────

_BASAL_EQUILIBRIUM_ROC = 0.5
_BASAL_MIN_ROWS_PER_TOD = 30
_BASAL_N_BOOT = 300
_BASAL_MISMATCH_THRESHOLD = 0.5
_BASAL_REAL_CARB_THRESHOLD_G = 5.0


def _tod_block(h: int) -> str:
    if 6 <= h < 12:
        return "morning"
    if 12 <= h < 18:
        return "afternoon"
    if 18 <= h < 24:
        return "evening"
    return "night"


def compute_basal_mismatch(
    grid_df: pd.DataFrame,
    *,
    seed: int = 2869,
) -> Optional[dict]:
    """Per-patient basal-mismatch summary (EXP-2869) from grid only."""
    needed = {
        "time", "glucose", "cob", "carbs", "time_since_bolus_min",
        "exercise_active", "override_active",
        "actual_basal_rate", "scheduled_basal_rate", "glucose_roc",
    }
    if not needed.issubset(grid_df.columns):
        return None

    df = grid_df.copy()
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df = df.sort_values("time").reset_index(drop=True)

    real_event = df["carbs"].fillna(0) >= _BASAL_REAL_CARB_THRESHOLD_G
    last_real = df["time"].where(real_event).ffill()
    df["time_since_real_carb_min"] = (
        (df["time"] - last_real).dt.total_seconds() / 60.0
    )

    df = df[
        (df["cob"].fillna(0) == 0)
        & (df["time_since_real_carb_min"].fillna(1e9) >= 240)
        & (df["time_since_bolus_min"].fillna(1e9) >= 240)
        & (~df["exercise_active"].fillna(False).astype(bool))
        & (~df["override_active"].fillna(False).astype(bool))
        & df["actual_basal_rate"].notna()
        & df["scheduled_basal_rate"].notna()
        & (df["scheduled_basal_rate"] > 0)
    ]
    df = df[df["glucose_roc"].abs() <= _BASAL_EQUILIBRIUM_ROC]
    if df.empty:
        return None
    df["tod"] = df["time"].dt.hour.apply(_tod_block)

    rng = np.random.default_rng(seed)
    rows = []
    for tod, g in df.groupby("tod"):
        if len(g) < _BASAL_MIN_ROWS_PER_TOD:
            continue
        actual = g["actual_basal_rate"].to_numpy()
        scheduled = float(g["scheduled_basal_rate"].median())
        if scheduled <= 0:
            continue
        mults = actual / scheduled
        idx = rng.integers(0, len(mults), size=(_BASAL_N_BOOT, len(mults)))
        boot_meds = np.median(mults[idx], axis=1)
        p = float((boot_meds < _BASAL_MISMATCH_THRESHOLD).mean())
        rows.append({
            "tod": tod,
            "median_actual_mult": float(np.median(mults)),
            "p_scheduled_gt_actual": p,
        })
    if not rows:
        return None
    tod_df = pd.DataFrame(rows)
    return {
        "max_mismatch_p": float(tod_df["p_scheduled_gt_actual"].max()),
        "median_recommended_mult": float(tod_df["median_actual_mult"].median()),
        "n_tod": int(len(tod_df)),
        "spread_recommended_mult": float(
            tod_df["median_actual_mult"].max() - tod_df["median_actual_mult"].min()
        ),
    }


# ─── Controller Dynamics (EXP-2753) ───────────────────────────────────────

def compute_controller_decomposition(
    grid_df: pd.DataFrame,
    patient_id: str,
) -> Optional[dict]:
    """Per-patient controller-decomposition (EXP-2753) from grid only.

    Imports the EXP-2753 `analyze_patient` function which is already
    structured as a per-patient computation.
    """
    try:
        # Import lazily to avoid pulling matplotlib at module import time.
        import importlib
        mod = importlib.import_module(
            "tools.cgmencode.exp_controller_decomposition_2753"
        )
    except Exception:
        return None
    fn = getattr(mod, "analyze_patient", None)
    if fn is None:
        return None
    try:
        out = fn(grid_df.copy(), patient_id)
    except Exception:
        return None
    return out  # may be None if too few events


# ─── Phenotype subset (EXP-2886/2878/2881) ────────────────────────────────
# Full phenotype synthesis depends on multiple cohort-level experiments
# (HAAF detection requires hypo nadir distribution comparisons; evening
# drivers require multi-patient regression). Per-patient computation is
# intentionally limited to the easily-derivable fields; complex cohort
# fields stay None for compute_for'd patients.

def compute_phenotype_minimal(
    grid_df: pd.DataFrame,
    *,
    detected_controller: Optional[str] = None,
) -> dict:
    """Minimal per-patient phenotype: lineage + observable rates.

    Computes only the fields that are well-defined from a single patient's
    grid. HAAF / evening-stacking signals require cohort context and stay
    None.
    """
    out = {
        "controller_lineage": detected_controller,
        "stack_score": None,
        "brake_ratio": None,
        "counter_reg_intercept": None,
        "beta_nadir": None,
        "p_haaf": None,
        "evening_bolus_excess_4h": None,
        "evening_iob_at_descent": None,
    }

    if grid_df.empty or "actual_basal_rate" not in grid_df.columns:
        return out

    # brake_ratio: fraction of cells with actual_basal_rate < 0.05 U/hr
    # (suspended/very-low). EXP-2886 uses a more nuanced definition; this
    # is a usable proxy.
    abr = grid_df["actual_basal_rate"].dropna()
    if len(abr) > 0:
        out["brake_ratio"] = float((abr < 0.05).mean())

    # stack_score: median 4-hour cumulative bolus during high-bolus periods
    if "bolus" in grid_df.columns:
        bolus_4h = grid_df["bolus"].fillna(0).rolling(48, min_periods=1).sum()
        nonzero = bolus_4h[bolus_4h > 0]
        if len(nonzero) > 0:
            out["stack_score"] = float(nonzero.median())

    return out
