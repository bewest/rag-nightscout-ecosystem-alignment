#!/usr/bin/env python3
"""
EXP-2737: Settings Interaction Matrix
======================================

SCIENTIFIC QUESTION
Do ISF, CR, and basal settings interact? If ISF extraction is wrong, does that
systematically bias CR extraction? Does joint optimization beat independent?

Previous waves extracted ISF (EXP-2720/2723), CR (EXP-2729), and basal
(EXP-2730/2735) INDEPENDENTLY, each using deconfounding to isolate its signal.
But these settings interact physiologically:
  - Wrong ISF → wrong BGI subtraction → wrong CR extraction
  - Wrong basal → wrong "excess insulin" → wrong ISF
  - EGP subtraction quality affects all three

HYPOTHESES
  H1: ISF error correlates with CR error (r > 0.3) — settings are coupled
  H2: Perturbing ISF by ±20% changes CR by >10% — ISF→CR propagation exists
  H3: Joint ISF+CR optimisation outperforms independent by >5% MAE — joint wins
  H4: Basal error is independent of ISF/CR (r < 0.2) — basal is separable
  H5: Cross-talk magnitude is controller-dependent — loops differ in coupling

OUTPUT
  externals/experiments/exp-2737_settings_interactions.json
  visualizations/settings-interactions/settings_interactions.png
"""

from __future__ import annotations

import json
import os
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from numpy.linalg import lstsq
from scipy import stats

warnings.filterwarnings("ignore", category=FutureWarning)

# ── paths ─────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[2]
GRID_PATH = ROOT / "externals" / "ns-parquet" / "training" / "grid.parquet"
MANIFEST_PATH = ROOT / "externals" / "experiments" / "autoprepare-qualified.json"
RESULTS_DIR = ROOT / "externals" / "experiments"
VIZ_DIR = ROOT / "visualizations" / "settings-interactions"

EXP_ID = "2737"

# ── extraction constants ──────────────────────────────────────────────────────
STEPS_PER_HOUR = 12  # 5-min intervals
ISF_HORIZON = 24     # 2 h
CR_HORIZON = 48      # 4 h
DRIFT_HORIZON = 12   # 1 h
BG_FLOOR = 180       # mg/dL for correction events
MIN_DOSE = 0.3       # U minimum to count
MIN_CARBS = 5.0      # g minimum for meal event
MIN_GAP_STEPS = 24   # 2 h between independent events
FASTING_BOLUS_WINDOW = 24   # 2 h lookback for fasting
FASTING_CARB_WINDOW = 36    # 3 h lookback for fasting
MIN_EVENTS = 8       # minimum events per patient for valid estimate

# Metabolic coefficients from prior experiments
BOLUS_COEFF = -129.2
SMB_COEFF = -123.6
EXCESS_BASAL_COEFF = -130.5
EGP_RATE = 2.0       # mg/dL per 5-min baseline hepatic glucose production

BLOCK_LABELS = ["00-04", "04-08", "08-12", "12-16", "16-20", "20-24"]

# ── data loading ──────────────────────────────────────────────────────────────

def load_data() -> pd.DataFrame:
    """Load parquet grid, filter to qualified patients."""
    print(f"Loading grid from {GRID_PATH} …")
    grid = pd.read_parquet(GRID_PATH)
    manifest = json.loads(MANIFEST_PATH.read_text())
    qualified = manifest.get("qualified_patients", [])
    grid = grid[grid["patient_id"].isin(qualified)].copy()
    # ensure time column is datetime
    if not pd.api.types.is_datetime64_any_dtype(grid["time"]):
        grid["time"] = pd.to_datetime(grid["time"], errors="coerce")
    grid.sort_values(["patient_id", "time"], inplace=True)
    grid.reset_index(drop=True, inplace=True)
    print(f"  → {len(grid):,} rows, {grid['patient_id'].nunique()} patients")
    return grid


def _safe_col(df: pd.DataFrame, col: str) -> np.ndarray:
    """Return column as float array or zeros if missing."""
    if col in df.columns:
        return df[col].values.astype(float)
    return np.zeros(len(df), dtype=float)


# ══════════════════════════════════════════════════════════════════════════════
# STEP 1 — Independent extraction of ISF, CR, basal
# ══════════════════════════════════════════════════════════════════════════════

def extract_isf_events(grid: pd.DataFrame) -> pd.DataFrame:
    """Extract correction events for ISF estimation.

    Criteria: BG ≥ 180, no carbs >5 g in 2 h window, total insulin ≥ 0.3 U,
    valid glucose at start and +2 h.
    """
    events: list[dict] = []
    for pid in grid["patient_id"].unique():
        pg = grid[grid["patient_id"] == pid].sort_values("time").reset_index(drop=True)
        n = len(pg)
        glucose = pg["glucose"].values.astype(float)
        bolus = _safe_col(pg, "bolus")
        smb = _safe_col(pg, "bolus_smb")
        carbs = _safe_col(pg, "carbs")
        net_basal = _safe_col(pg, "net_basal")
        sched_isf = _safe_col(pg, "scheduled_isf")
        iob = _safe_col(pg, "iob")
        times = pg["time"].values

        profile_isf = float(np.nanmedian(sched_isf[sched_isf > 0])) if np.any(sched_isf > 0) else np.nan

        for i in range(1, n - ISF_HORIZON):
            bg0 = glucose[i]
            bg_end = glucose[i + ISF_HORIZON]
            if np.isnan(bg0) or np.isnan(bg_end) or bg0 < BG_FLOOR:
                continue
            carbs_2h = float(np.nansum(carbs[i : i + ISF_HORIZON]))
            if carbs_2h > MIN_CARBS:
                continue

            bolus_2h = float(np.nansum(bolus[i : i + ISF_HORIZON]))
            smb_2h = float(np.nansum(smb[i : i + ISF_HORIZON]))
            excess_basal_2h = float(np.nansum(np.maximum(net_basal[i : i + ISF_HORIZON], 0))) / STEPS_PER_HOUR
            total_insulin = bolus_2h + smb_2h + excess_basal_2h
            if total_insulin < MIN_DOSE:
                continue

            # EGP correction over 2h window (24 steps × 2 mg/dL per step)
            egp_correction = EGP_RATE * ISF_HORIZON
            observed_drop = bg0 - bg_end + egp_correction
            demand_isf = observed_drop / total_insulin

            if demand_isf < 1 or demand_isf > 500:
                continue

            hour = int(pd.Timestamp(times[i]).hour) if not pd.isna(pd.Timestamp(times[i])) else 0
            events.append({
                "patient_id": pid,
                "bg0": bg0,
                "bg_end": float(bg_end),
                "total_insulin": total_insulin,
                "demand_isf": demand_isf,
                "profile_isf": profile_isf,
                "iob_start": float(iob[i]) if not np.isnan(iob[i]) else 0.0,
                "hour": hour,
                "controller": pg["controller"].iloc[i] if "controller" in pg.columns else "unknown",
            })
    return pd.DataFrame(events)


def extract_cr_events(grid: pd.DataFrame, isf_override: dict[str, float] | None = None) -> pd.DataFrame:
    """Extract meal events for CR estimation.

    Criteria: carbs ≥ 5 g (±30 min window), bolus present, no second meal in 4 h,
    valid glucose at start and +4 h.

    isf_override: optional dict {patient_id: isf_value} used for BGI subtraction.
    If None, uses scheduled_isf from profile.
    """
    events: list[dict] = []
    for pid in grid["patient_id"].unique():
        pg = grid[grid["patient_id"] == pid].sort_values("time").reset_index(drop=True)
        n = len(pg)
        glucose = pg["glucose"].values.astype(float)
        bolus = _safe_col(pg, "bolus")
        smb = _safe_col(pg, "bolus_smb")
        carbs = _safe_col(pg, "carbs")
        net_basal = _safe_col(pg, "net_basal")
        sched_isf = _safe_col(pg, "scheduled_isf")
        sched_cr = _safe_col(pg, "scheduled_cr") if "scheduled_cr" in pg.columns else np.full(n, np.nan)
        iob = _safe_col(pg, "iob")
        times = pg["time"].values

        # ISF for BGI subtraction
        if isf_override and pid in isf_override:
            isf_for_bgi = isf_override[pid]
        else:
            valid_isf = sched_isf[sched_isf > 0]
            isf_for_bgi = float(np.nanmedian(valid_isf)) if len(valid_isf) > 0 else 50.0

        profile_cr = float(np.nanmedian(sched_cr[sched_cr > 0])) if np.any(sched_cr > 0) else np.nan

        for i in range(6, n - CR_HORIZON):
            lo = max(i - 6, 0)
            hi = min(i + 7, n)
            window_carbs = float(np.nansum(carbs[lo:hi]))
            if window_carbs < MIN_CARBS:
                continue
            window_bolus = float(np.nansum(bolus[lo:hi]))
            if window_bolus <= 0:
                continue

            bg0 = glucose[i]
            bg_end = glucose[i + CR_HORIZON]
            if np.isnan(bg0) or np.isnan(bg_end):
                continue

            # No second meal in future 4 h (beyond the ±30 min window)
            future_carbs = float(np.nansum(carbs[i + 7 : i + CR_HORIZON]))
            if future_carbs >= MIN_CARBS:
                continue

            bolus_4h = float(np.nansum(bolus[i : i + CR_HORIZON]))
            smb_4h = float(np.nansum(smb[i : i + CR_HORIZON]))
            excess_basal_4h = float(np.nansum(np.maximum(net_basal[i : i + CR_HORIZON], 0))) / STEPS_PER_HOUR
            total_insulin = bolus_4h + smb_4h + excess_basal_4h

            if total_insulin < MIN_DOSE:
                continue

            bg_change = bg_end - bg0
            # EGP over 4h
            egp_4h = EGP_RATE * CR_HORIZON
            # BGI subtraction: insulin-attributable BG change
            bgi = total_insulin * isf_for_bgi * (-1)
            # Net carb effect = observed BG change - BGI - EGP
            carb_bg_effect = bg_change - bgi - egp_4h

            # CR = grams / units_insulin_equivalent
            # carb_bg_effect (mg/dL) / isf_for_bgi = insulin-equivalent of carb effect (U)
            if abs(isf_for_bgi) < 1:
                continue
            carb_insulin_equiv = carb_bg_effect / isf_for_bgi
            if carb_insulin_equiv < 0.1:
                continue
            observed_cr = window_carbs / carb_insulin_equiv

            if observed_cr < 1 or observed_cr > 100:
                continue

            hour = int(pd.Timestamp(times[i]).hour) if not pd.isna(pd.Timestamp(times[i])) else 0
            events.append({
                "patient_id": pid,
                "carbs": window_carbs,
                "bg0": bg0,
                "bg_end": float(bg_end),
                "bg_change": bg_change,
                "total_insulin": total_insulin,
                "isf_used": isf_for_bgi,
                "bgi": bgi,
                "carb_bg_effect": carb_bg_effect,
                "observed_cr": observed_cr,
                "profile_cr": profile_cr,
                "iob_start": float(iob[i]) if not np.isnan(iob[i]) else 0.0,
                "hour": hour,
                "controller": pg["controller"].iloc[i] if "controller" in pg.columns else "unknown",
            })
    return pd.DataFrame(events)


def extract_basal_events(grid: pd.DataFrame) -> pd.DataFrame:
    """Extract fasting-period drift events for basal assessment.

    Criteria: no bolus for prior 2 h, no carbs for prior 3 h,
    valid glucose at t and t+1 h.
    """
    events: list[dict] = []
    for pid in grid["patient_id"].unique():
        pg = grid[grid["patient_id"] == pid].sort_values("time").reset_index(drop=True)
        n = len(pg)
        glucose = pg["glucose"].values.astype(float)
        bolus = _safe_col(pg, "bolus")
        smb = _safe_col(pg, "bolus_smb")
        carbs = _safe_col(pg, "carbs")
        sched_basal = _safe_col(pg, "scheduled_basal_rate")
        sched_isf = _safe_col(pg, "scheduled_isf")
        times = pg["time"].values

        profile_isf = float(np.nanmedian(sched_isf[sched_isf > 0])) if np.any(sched_isf > 0) else np.nan

        for i in range(FASTING_CARB_WINDOW, n - DRIFT_HORIZON):
            if np.isnan(glucose[i]) or np.isnan(glucose[i + DRIFT_HORIZON]):
                continue
            # No bolus/SMB in prior 2 h
            win_bolus = np.nansum(bolus[max(0, i - FASTING_BOLUS_WINDOW + 1) : i + 1])
            win_smb = np.nansum(smb[max(0, i - FASTING_BOLUS_WINDOW + 1) : i + 1])
            if win_bolus > 0 or win_smb > 0:
                continue
            # No carbs in prior 3 h
            win_carbs = np.nansum(carbs[max(0, i - FASTING_CARB_WINDOW + 1) : i + 1])
            if win_carbs > 0:
                continue

            drift = float(glucose[i + DRIFT_HORIZON] - glucose[i])  # mg/dL per hour
            sched_b = float(sched_basal[i]) if not np.isnan(sched_basal[i]) else np.nan
            hour = int(pd.Timestamp(times[i]).hour) if not pd.isna(pd.Timestamp(times[i])) else 0

            events.append({
                "patient_id": pid,
                "glucose_start": float(glucose[i]),
                "drift": drift,
                "scheduled_basal": sched_b,
                "profile_isf": profile_isf,
                "hour": hour,
                "controller": pg["controller"].iloc[i] if "controller" in pg.columns else "unknown",
            })
    return pd.DataFrame(events)


# ── per-patient aggregation ───────────────────────────────────────────────────

def _filter_independent(events: pd.DataFrame, gap: int = MIN_GAP_STEPS) -> pd.DataFrame:
    """Thin events so no two from the same patient are within `gap` steps."""
    keep = []
    for _pid, grp in events.groupby("patient_id"):
        grp = grp.sort_index()
        last_idx = -gap - 1
        for idx in grp.index:
            if idx - last_idx >= gap:
                keep.append(idx)
                last_idx = idx
    return events.loc[keep]


def _deconfound(y: np.ndarray, X_features: np.ndarray) -> float:
    """Residualise y on X_features, return median(residuals) + median(y)."""
    mask = np.isfinite(y) & np.all(np.isfinite(X_features), axis=1)
    y_c, X_c = y[mask], X_features[mask]
    if len(y_c) < MIN_EVENTS:
        return float(np.nanmedian(y))
    X_int = np.column_stack([X_c, np.ones(len(y_c))])
    beta, _, _, _ = lstsq(X_int, y_c, rcond=None)
    residuals = y_c - X_int @ beta
    return float(np.median(residuals) + np.median(y_c))


def compute_patient_settings(
    isf_events: pd.DataFrame,
    cr_events: pd.DataFrame,
    basal_events: pd.DataFrame,
) -> pd.DataFrame:
    """Compute per-patient independent ISF, CR, and basal estimates."""
    all_pids = sorted(
        set(isf_events["patient_id"].unique())
        | set(cr_events["patient_id"].unique())
        | set(basal_events["patient_id"].unique())
    )

    rows: list[dict] = []
    for pid in all_pids:
        row: dict = {"patient_id": pid}

        # ── ISF ───────────────────────────────────────────────────────────
        pi = isf_events[isf_events["patient_id"] == pid]
        pi_ind = _filter_independent(pi, MIN_GAP_STEPS)
        row["n_isf_events"] = len(pi_ind)

        if len(pi_ind) >= MIN_EVENTS:
            y_isf = pi_ind["demand_isf"].values.astype(float)
            X_isf = np.column_stack([pi_ind["bg0"].values, pi_ind["total_insulin"].values])
            row["isf_deconf"] = _deconfound(y_isf, X_isf)
            row["isf_raw_median"] = float(np.nanmedian(y_isf))
        else:
            row["isf_deconf"] = np.nan
            row["isf_raw_median"] = float(np.nanmedian(pi["demand_isf"])) if len(pi) > 0 else np.nan

        row["isf_profile"] = float(pi["profile_isf"].iloc[0]) if len(pi) > 0 else np.nan
        # Controller for this patient (mode)
        if len(pi) > 0 and "controller" in pi.columns:
            row["controller"] = pi["controller"].mode().iloc[0] if len(pi["controller"].mode()) > 0 else "unknown"
        else:
            row["controller"] = "unknown"

        # ── CR ────────────────────────────────────────────────────────────
        pc = cr_events[cr_events["patient_id"] == pid]
        pc_ind = _filter_independent(pc, CR_HORIZON)
        row["n_cr_events"] = len(pc_ind)

        if len(pc_ind) >= MIN_EVENTS:
            y_cr = pc_ind["observed_cr"].values.astype(float)
            X_cr = np.column_stack([pc_ind["bg0"].values, pc_ind["total_insulin"].values])
            row["cr_deconf"] = _deconfound(y_cr, X_cr)
            row["cr_raw_median"] = float(np.nanmedian(y_cr))
        else:
            row["cr_deconf"] = np.nan
            row["cr_raw_median"] = float(np.nanmedian(pc["observed_cr"])) if len(pc) > 0 else np.nan

        row["cr_profile"] = float(pc["profile_cr"].iloc[0]) if len(pc) > 0 and not np.isnan(pc["profile_cr"].iloc[0]) else np.nan

        # ── Basal ─────────────────────────────────────────────────────────
        pb = basal_events[basal_events["patient_id"] == pid]
        row["n_basal_events"] = len(pb)

        if len(pb) >= MIN_EVENTS:
            drift_vals = pb["drift"].values.astype(float)
            row["basal_drift_median"] = float(np.nanmedian(drift_vals))
            p_isf = float(pb["profile_isf"].iloc[0]) if not np.isnan(pb["profile_isf"].iloc[0]) else 50.0
            # Basal adjustment: positive drift → need more basal (U/h)
            row["basal_adjustment"] = row["basal_drift_median"] / p_isf
        else:
            row["basal_drift_median"] = np.nan
            row["basal_adjustment"] = np.nan

        rows.append(row)

    return pd.DataFrame(rows)


# ══════════════════════════════════════════════════════════════════════════════
# STEP 2 — Settings error computation and coupling analysis
# ══════════════════════════════════════════════════════════════════════════════

def compute_settings_errors(settings: pd.DataFrame) -> pd.DataFrame:
    """Compute relative errors for ISF, CR, and basal."""
    df = settings.copy()
    # ISF error: (profile - empirical) / profile
    isf_emp = df["isf_deconf"].where(df["isf_deconf"].notna(), df["isf_raw_median"])
    df["isf_error"] = (df["isf_profile"] - isf_emp) / df["isf_profile"].replace(0, np.nan)

    # CR error: (profile - empirical) / profile
    cr_emp = df["cr_deconf"].where(df["cr_deconf"].notna(), df["cr_raw_median"])
    df["cr_error"] = (df["cr_profile"] - cr_emp) / df["cr_profile"].replace(0, np.nan)

    # Basal error: normalised drift (mg/dL/h) / profile_ISF
    df["basal_error"] = df["basal_adjustment"]

    return df


def test_h1_coupling(errors: pd.DataFrame) -> dict:
    """H1: ISF error correlates with CR error (threshold r > 0.3)."""
    mask = errors["isf_error"].notna() & errors["cr_error"].notna()
    valid = errors[mask]
    n = len(valid)
    if n < 5:
        return {"verdict": "INSUFFICIENT_DATA", "n": n}

    x, y = valid["isf_error"].values, valid["cr_error"].values
    if np.std(x) < 1e-6 or np.std(y) < 1e-6:
        return {"verdict": "CONSTANT_VALUES", "n": n}

    r, p = stats.pearsonr(x, y)
    rho, p_rho = stats.spearmanr(x, y)
    verdict = "PASS" if abs(r) > 0.3 else "FAIL"
    return {
        "verdict": verdict,
        "pearson_r": round(float(r), 4),
        "pearson_p": float(p),
        "spearman_rho": round(float(rho), 4),
        "spearman_p": float(p_rho),
        "n": n,
        "threshold": 0.3,
        "interpretation": (
            f"ISF and CR errors are {'coupled' if verdict == 'PASS' else 'not strongly coupled'} "
            f"(r={r:.3f}, p={p:.4f})"
        ),
    }


# ══════════════════════════════════════════════════════════════════════════════
# STEP 2b — ISF perturbation → CR sensitivity
# ══════════════════════════════════════════════════════════════════════════════

def test_h2_perturbation(
    grid: pd.DataFrame, settings: pd.DataFrame
) -> dict:
    """H2: Perturbing ISF by ±20% changes CR extraction by >10%."""
    # Build per-patient ISF overrides
    baseline_isf: dict[str, float] = {}
    for _, row in settings.iterrows():
        pid = row["patient_id"]
        isf_val = row["isf_deconf"] if not np.isnan(row["isf_deconf"]) else row["isf_profile"]
        if not np.isnan(isf_val) and isf_val > 0:
            baseline_isf[pid] = isf_val

    if len(baseline_isf) < 3:
        return {"verdict": "INSUFFICIENT_DATA", "n_patients": len(baseline_isf)}

    # Extract CR at three ISF levels: -20%, baseline, +20%
    overrides_low = {pid: v * 0.8 for pid, v in baseline_isf.items()}
    overrides_high = {pid: v * 1.2 for pid, v in baseline_isf.items()}

    print("  Extracting CR with ISF -20% …")
    cr_low = extract_cr_events(grid, isf_override=overrides_low)
    print("  Extracting CR with ISF +20% …")
    cr_high = extract_cr_events(grid, isf_override=overrides_high)
    print("  Extracting CR with baseline ISF …")
    cr_base = extract_cr_events(grid, isf_override=baseline_isf)

    # Per-patient median CR at each ISF level
    pids_valid = []
    cr_at_low, cr_at_base, cr_at_high = [], [], []

    for pid in baseline_isf:
        cl = cr_low[cr_low["patient_id"] == pid]["observed_cr"]
        cb = cr_base[cr_base["patient_id"] == pid]["observed_cr"]
        ch = cr_high[cr_high["patient_id"] == pid]["observed_cr"]
        if len(cl) >= 3 and len(cb) >= 3 and len(ch) >= 3:
            pids_valid.append(pid)
            cr_at_low.append(float(np.nanmedian(cl)))
            cr_at_base.append(float(np.nanmedian(cb)))
            cr_at_high.append(float(np.nanmedian(ch)))

    if len(pids_valid) < 3:
        return {"verdict": "INSUFFICIENT_DATA", "n_patients": len(pids_valid)}

    cr_at_low = np.array(cr_at_low)
    cr_at_base = np.array(cr_at_base)
    cr_at_high = np.array(cr_at_high)

    # Percentage change from baseline
    pct_change_low = np.abs((cr_at_low - cr_at_base) / np.maximum(cr_at_base, 0.1)) * 100
    pct_change_high = np.abs((cr_at_high - cr_at_base) / np.maximum(cr_at_base, 0.1)) * 100
    max_pct = np.maximum(pct_change_low, pct_change_high)

    median_sensitivity = float(np.median(max_pct))
    mean_sensitivity = float(np.mean(max_pct))
    fraction_above_10 = float(np.mean(max_pct > 10))

    verdict = "PASS" if median_sensitivity > 10 else "FAIL"

    per_patient = []
    for j, pid in enumerate(pids_valid):
        per_patient.append({
            "patient_id": pid,
            "cr_at_isf_low": round(cr_at_low[j], 2),
            "cr_at_isf_base": round(cr_at_base[j], 2),
            "cr_at_isf_high": round(cr_at_high[j], 2),
            "pct_change_low": round(float(pct_change_low[j]), 1),
            "pct_change_high": round(float(pct_change_high[j]), 1),
        })

    return {
        "verdict": verdict,
        "median_cr_sensitivity_pct": round(median_sensitivity, 2),
        "mean_cr_sensitivity_pct": round(mean_sensitivity, 2),
        "fraction_above_10pct": round(fraction_above_10, 3),
        "n_patients": len(pids_valid),
        "threshold_pct": 10,
        "per_patient": per_patient,
        "interpretation": (
            f"ISF ±20% perturbation changes CR by median {median_sensitivity:.1f}% "
            f"({'significant' if verdict == 'PASS' else 'negligible'} propagation)"
        ),
    }


# ══════════════════════════════════════════════════════════════════════════════
# STEP 3 — Joint vs independent optimisation
# ══════════════════════════════════════════════════════════════════════════════

def _prediction_mae_isf(events: pd.DataFrame, isf_val: float) -> float:
    """MAE for ISF: predicted BG drop vs actual."""
    if len(events) == 0 or np.isnan(isf_val):
        return np.nan
    predicted_drop = events["total_insulin"].values * isf_val
    actual_drop = events["bg0"].values - events["bg_end"].values + EGP_RATE * ISF_HORIZON
    return float(np.mean(np.abs(predicted_drop - actual_drop)))


def _prediction_mae_cr(events: pd.DataFrame, cr_val: float, isf_val: float) -> float:
    """MAE for CR: predicted BG rise from carbs vs actual carb effect."""
    if len(events) == 0 or np.isnan(cr_val) or np.isnan(isf_val):
        return np.nan
    predicted_carb_insulin = events["carbs"].values / cr_val
    predicted_carb_bg = predicted_carb_insulin * isf_val
    actual_carb_bg = events["carb_bg_effect"].values
    return float(np.mean(np.abs(predicted_carb_bg - actual_carb_bg)))


def _prediction_mae_basal(events: pd.DataFrame, adj: float, isf_val: float) -> float:
    """MAE for basal: predicted drift given basal adjustment vs actual drift."""
    if len(events) == 0 or np.isnan(adj):
        return np.nan
    predicted_drift = -adj * isf_val  # if adj is right, drift should be ~0
    actual_drift = events["drift"].values.astype(float)
    return float(np.mean(np.abs(actual_drift - predicted_drift)))


def test_h3_joint_vs_independent(
    isf_events: pd.DataFrame,
    cr_events: pd.DataFrame,
    basal_events: pd.DataFrame,
    settings: pd.DataFrame,
) -> dict:
    """H3: Joint optimisation outperforms independent by >5% MAE reduction.

    Joint optimisation: grid search ISF, then use that ISF for CR and basal
    predictions (coupled). Independent: each uses its own best estimate.
    """
    per_patient: list[dict] = []
    independent_maes: list[float] = []
    joint_maes: list[float] = []

    for _, row in settings.iterrows():
        pid = row["patient_id"]
        pi_ev = isf_events[isf_events["patient_id"] == pid]
        pc_ev = cr_events[cr_events["patient_id"] == pid]
        pb_ev = basal_events[basal_events["patient_id"] == pid]

        if len(pi_ev) < MIN_EVENTS or len(pc_ev) < MIN_EVENTS:
            continue

        isf_ind = row["isf_deconf"] if not np.isnan(row["isf_deconf"]) else row["isf_raw_median"]
        cr_ind = row["cr_deconf"] if not np.isnan(row["cr_deconf"]) else row["cr_raw_median"]
        basal_adj = row["basal_adjustment"] if not np.isnan(row["basal_adjustment"]) else 0.0

        if np.isnan(isf_ind) or np.isnan(cr_ind):
            continue

        # Independent MAE: each setting uses its own best estimate
        mae_isf_ind = _prediction_mae_isf(pi_ev, isf_ind)
        mae_cr_ind = _prediction_mae_cr(pc_ev, cr_ind, isf_ind)
        mae_basal_ind = _prediction_mae_basal(pb_ev, basal_adj, isf_ind) if len(pb_ev) >= MIN_EVENTS else 0.0
        total_ind = mae_isf_ind + mae_cr_ind + mae_basal_ind

        # Joint optimisation: grid-search ISF that minimises total error
        isf_candidates = np.linspace(max(isf_ind * 0.5, 5), isf_ind * 2.0, 40)
        best_joint_mae = np.inf
        best_isf_joint = isf_ind
        best_cr_joint = cr_ind

        for isf_try in isf_candidates:
            # Re-estimate CR given this ISF
            cr_try_vals = []
            for _, ev in pc_ev.iterrows():
                bgi = ev["total_insulin"] * isf_try * (-1)
                carb_bg = ev["bg_change"] - bgi - EGP_RATE * CR_HORIZON
                if isf_try > 0:
                    carb_iu = carb_bg / isf_try
                    if carb_iu > 0.1:
                        cr_try_vals.append(ev["carbs"] / carb_iu)
            cr_try = float(np.median(cr_try_vals)) if len(cr_try_vals) > 3 else cr_ind

            # Basal adjustment at this ISF
            if len(pb_ev) >= MIN_EVENTS:
                drift_med = float(np.nanmedian(pb_ev["drift"].values))
                adj_try = drift_med / isf_try if isf_try > 0 else 0.0
            else:
                adj_try = 0.0

            # Total MAE
            m_isf = _prediction_mae_isf(pi_ev, isf_try)
            m_cr = _prediction_mae_cr(pc_ev, cr_try, isf_try)
            m_basal = _prediction_mae_basal(pb_ev, adj_try, isf_try) if len(pb_ev) >= MIN_EVENTS else 0.0
            total_j = m_isf + m_cr + m_basal

            if total_j < best_joint_mae:
                best_joint_mae = total_j
                best_isf_joint = isf_try
                best_cr_joint = cr_try

        improvement_pct = (total_ind - best_joint_mae) / max(total_ind, 1e-6) * 100

        per_patient.append({
            "patient_id": pid,
            "independent_mae": round(total_ind, 2),
            "joint_mae": round(best_joint_mae, 2),
            "improvement_pct": round(float(improvement_pct), 2),
            "isf_ind": round(isf_ind, 1),
            "isf_joint": round(float(best_isf_joint), 1),
            "cr_ind": round(cr_ind, 1),
            "cr_joint": round(float(best_cr_joint), 1),
        })
        independent_maes.append(total_ind)
        joint_maes.append(best_joint_mae)

    if len(per_patient) < 3:
        return {"verdict": "INSUFFICIENT_DATA", "n_patients": len(per_patient)}

    independent_maes = np.array(independent_maes)
    joint_maes = np.array(joint_maes)
    overall_improvement = float((np.mean(independent_maes) - np.mean(joint_maes)) / np.mean(independent_maes) * 100)
    median_improvement = float(np.median([(p["improvement_pct"]) for p in per_patient]))

    verdict = "PASS" if overall_improvement > 5 else "FAIL"

    return {
        "verdict": verdict,
        "overall_mae_independent": round(float(np.mean(independent_maes)), 2),
        "overall_mae_joint": round(float(np.mean(joint_maes)), 2),
        "overall_improvement_pct": round(overall_improvement, 2),
        "median_improvement_pct": round(median_improvement, 2),
        "fraction_improved": round(float(np.mean(joint_maes < independent_maes)), 3),
        "n_patients": len(per_patient),
        "threshold_pct": 5,
        "per_patient": per_patient,
        "interpretation": (
            f"Joint optimisation {'outperforms' if verdict == 'PASS' else 'does not outperform'} "
            f"independent by {overall_improvement:.1f}% (threshold: 5%)"
        ),
    }


# ══════════════════════════════════════════════════════════════════════════════
# STEP 4 — Basal separability
# ══════════════════════════════════════════════════════════════════════════════

def test_h4_basal_separability(errors: pd.DataFrame) -> dict:
    """H4: Basal error independent of ISF/CR error (r < 0.2)."""
    results: dict = {}
    for other_name, other_col in [("isf", "isf_error"), ("cr", "cr_error")]:
        mask = errors["basal_error"].notna() & errors[other_col].notna()
        valid = errors[mask]
        n = len(valid)
        if n < 5:
            results[f"basal_vs_{other_name}"] = {"verdict": "INSUFFICIENT_DATA", "n": n}
            continue

        x = valid["basal_error"].values
        y = valid[other_col].values

        if np.std(x) < 1e-6 or np.std(y) < 1e-6:
            results[f"basal_vs_{other_name}"] = {"verdict": "CONSTANT_VALUES", "n": n}
            continue

        r, p = stats.pearsonr(x, y)
        rho, p_rho = stats.spearmanr(x, y)
        is_independent = abs(r) < 0.2
        results[f"basal_vs_{other_name}"] = {
            "pearson_r": round(float(r), 4),
            "pearson_p": float(p),
            "spearman_rho": round(float(rho), 4),
            "spearman_p": float(p_rho),
            "n": n,
            "is_independent": bool(is_independent),
        }

    # Overall verdict
    indep_flags = [
        v.get("is_independent", False)
        for v in results.values()
        if isinstance(v, dict) and "is_independent" in v
    ]
    verdict = "PASS" if all(indep_flags) else "FAIL" if indep_flags else "INSUFFICIENT_DATA"
    results["verdict"] = verdict
    results["threshold"] = 0.2
    results["interpretation"] = (
        f"Basal error is {'independent of' if verdict == 'PASS' else 'coupled with'} "
        f"ISF/CR errors (threshold |r| < 0.2)"
    )
    return results


# ══════════════════════════════════════════════════════════════════════════════
# STEP 5 — Controller-dependent coupling
# ══════════════════════════════════════════════════════════════════════════════

def test_h5_controller_coupling(errors: pd.DataFrame) -> dict:
    """H5: Cross-talk magnitude is controller-dependent."""
    results: dict = {"per_controller": {}}
    controllers = errors["controller"].unique()

    coupling_strengths: dict[str, float] = {}

    for ctrl in sorted(controllers):
        ctrl_str = str(ctrl)
        ce = errors[errors["controller"] == ctrl]
        mask = ce["isf_error"].notna() & ce["cr_error"].notna()
        valid = ce[mask]
        n = len(valid)
        if n < 4:
            results["per_controller"][ctrl_str] = {
                "n": n, "isf_cr_r": np.nan, "verdict": "INSUFFICIENT_DATA"
            }
            continue

        x, y = valid["isf_error"].values, valid["cr_error"].values
        if np.std(x) < 1e-6 or np.std(y) < 1e-6:
            results["per_controller"][ctrl_str] = {
                "n": n, "isf_cr_r": np.nan, "verdict": "CONSTANT_VALUES"
            }
            continue

        r, p = stats.pearsonr(x, y)
        coupling_strengths[ctrl_str] = abs(float(r))

        # Also compute basal coupling per controller
        mask_b = ce["basal_error"].notna() & ce["isf_error"].notna()
        valid_b = ce[mask_b]
        basal_isf_r = np.nan
        if len(valid_b) >= 4:
            bx = valid_b["basal_error"].values
            by = valid_b["isf_error"].values
            if np.std(bx) > 1e-6 and np.std(by) > 1e-6:
                basal_isf_r, _ = stats.pearsonr(bx, by)

        results["per_controller"][ctrl_str] = {
            "n": n,
            "isf_cr_r": round(float(r), 4),
            "isf_cr_p": float(p),
            "basal_isf_r": round(float(basal_isf_r), 4) if not np.isnan(basal_isf_r) else None,
            "coupling_strength": round(abs(float(r)), 4),
        }

    # Test if coupling varies across controllers
    if len(coupling_strengths) >= 2:
        vals = list(coupling_strengths.values())
        coupling_range = max(vals) - min(vals)
        verdict = "PASS" if coupling_range > 0.2 else "FAIL"
        results["coupling_range"] = round(coupling_range, 4)
        results["max_coupling_controller"] = max(coupling_strengths, key=coupling_strengths.get)
        results["min_coupling_controller"] = min(coupling_strengths, key=coupling_strengths.get)
    else:
        verdict = "INSUFFICIENT_DATA"
        results["coupling_range"] = None

    results["verdict"] = verdict
    results["interpretation"] = (
        f"Controller coupling {'varies significantly' if verdict == 'PASS' else 'is similar'} "
        f"across controllers (range={results.get('coupling_range', 'N/A')})"
    )
    return results


# ══════════════════════════════════════════════════════════════════════════════
# STEP 6 — Correlation matrix
# ══════════════════════════════════════════════════════════════════════════════

def compute_correlation_matrix(errors: pd.DataFrame) -> dict:
    """Compute 3×3 error correlation matrix."""
    cols = ["isf_error", "cr_error", "basal_error"]
    labels = ["ISF error", "CR error", "Basal error"]
    matrix: dict = {}

    for i, ci in enumerate(cols):
        for j, cj in enumerate(cols):
            mask = errors[ci].notna() & errors[cj].notna()
            valid = errors[mask]
            if len(valid) < 5 or np.std(valid[ci]) < 1e-6 or np.std(valid[cj]) < 1e-6:
                matrix[f"{labels[i]}_vs_{labels[j]}"] = {"r": np.nan, "p": np.nan}
            else:
                r, p = stats.pearsonr(valid[ci].values, valid[cj].values)
                matrix[f"{labels[i]}_vs_{labels[j]}"] = {
                    "r": round(float(r), 4),
                    "p": float(p),
                }
    return matrix


# ══════════════════════════════════════════════════════════════════════════════
# VISUALIZATION
# ══════════════════════════════════════════════════════════════════════════════

def create_visualizations(
    errors: pd.DataFrame,
    h2_result: dict,
    h3_result: dict,
    corr_matrix: dict,
    output_path: Path,
) -> None:
    """Generate 2×3 panel figure."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import Normalize
    from matplotlib import cm

    fig, axes = plt.subplots(2, 3, figsize=(18, 11))
    fig.suptitle(
        "EXP-2737: Settings Interaction Matrix — ISF / CR / Basal Coupling",
        fontsize=14, fontweight="bold", y=0.98,
    )

    # ── Panel 1: ISF_error vs CR_error scatter ────────────────────────────
    ax = axes[0, 0]
    mask = errors["isf_error"].notna() & errors["cr_error"].notna()
    valid = errors[mask]
    if len(valid) >= 3:
        x, y = valid["isf_error"].values, valid["cr_error"].values
        # Color by controller
        ctrl_colors = {"loop": "#1f77b4", "trio": "#ff7f0e", "openaps": "#2ca02c"}
        for ctrl in valid["controller"].unique():
            cm_ = valid["controller"] == ctrl
            color = ctrl_colors.get(str(ctrl), "#999999")
            ax.scatter(
                valid.loc[cm_, "isf_error"], valid.loc[cm_, "cr_error"],
                c=color, label=str(ctrl), alpha=0.7, s=60, edgecolors="k", linewidths=0.5,
            )
        # Regression line
        if np.std(x) > 1e-6 and np.std(y) > 1e-6:
            slope, intercept, r_val, p_val, _ = stats.linregress(x, y)
            x_line = np.linspace(x.min(), x.max(), 100)
            ax.plot(x_line, slope * x_line + intercept, "r--", lw=2,
                    label=f"r={r_val:.3f}, p={p_val:.3f}")
        ax.axhline(0, color="grey", ls=":", lw=0.8)
        ax.axvline(0, color="grey", ls=":", lw=0.8)
        ax.legend(fontsize=8)
    ax.set_xlabel("ISF Error (relative)")
    ax.set_ylabel("CR Error (relative)")
    ax.set_title("H1: ISF–CR Error Coupling")

    # ── Panel 2: CR sensitivity to ISF perturbation ──────────────────────
    ax = axes[0, 1]
    if "per_patient" in h2_result and len(h2_result["per_patient"]) > 0:
        pp = h2_result["per_patient"]
        cr_low = [p["cr_at_isf_low"] for p in pp]
        cr_base = [p["cr_at_isf_base"] for p in pp]
        cr_high = [p["cr_at_isf_high"] for p in pp]

        positions = [1, 2, 3]
        bp = ax.boxplot(
            [cr_low, cr_base, cr_high],
            positions=positions, widths=0.6, patch_artist=True,
            tick_labels=["ISF −20%", "Baseline", "ISF +20%"],
        )
        colours = ["#ff9999", "#99ccff", "#99ff99"]
        for patch, colour in zip(bp["boxes"], colours):
            patch.set_facecolor(colour)
        ax.set_ylabel("Median CR (g/U)")
        med_sens = h2_result.get("median_cr_sensitivity_pct", 0)
        ax.set_title(f"H2: CR Sensitivity (median Δ={med_sens:.1f}%)")
    else:
        ax.text(0.5, 0.5, "Insufficient data", ha="center", va="center", transform=ax.transAxes)
        ax.set_title("H2: CR Sensitivity to ISF Perturbation")

    # ── Panel 3: Joint vs Independent MAE ────────────────────────────────
    ax = axes[0, 2]
    if "per_patient" in h3_result and len(h3_result["per_patient"]) > 0:
        pp = h3_result["per_patient"]
        pids = [p["patient_id"][:8] for p in pp]
        ind_mae = [p["independent_mae"] for p in pp]
        jnt_mae = [p["joint_mae"] for p in pp]
        x_pos = np.arange(len(pids))
        width = 0.35
        ax.bar(x_pos - width / 2, ind_mae, width, label="Independent", color="#ff7f0e", alpha=0.8)
        ax.bar(x_pos + width / 2, jnt_mae, width, label="Joint", color="#1f77b4", alpha=0.8)
        ax.set_xticks(x_pos)
        ax.set_xticklabels(pids, rotation=45, ha="right", fontsize=7)
        ax.legend(fontsize=8)
        ax.set_ylabel("Total MAE (mg/dL)")
        imp = h3_result.get("overall_improvement_pct", 0)
        ax.set_title(f"H3: Joint vs Independent (Δ={imp:.1f}%)")
    else:
        ax.text(0.5, 0.5, "Insufficient data", ha="center", va="center", transform=ax.transAxes)
        ax.set_title("H3: Joint vs Independent MAE")

    # ── Panel 4: Basal error vs ISF error ────────────────────────────────
    ax = axes[1, 0]
    mask_bi = errors["basal_error"].notna() & errors["isf_error"].notna()
    valid_bi = errors[mask_bi]
    if len(valid_bi) >= 3:
        x_b, y_b = valid_bi["basal_error"].values, valid_bi["isf_error"].values
        ctrl_colors = {"loop": "#1f77b4", "trio": "#ff7f0e", "openaps": "#2ca02c"}
        for ctrl in valid_bi["controller"].unique():
            cm_ = valid_bi["controller"] == ctrl
            color = ctrl_colors.get(str(ctrl), "#999999")
            ax.scatter(
                valid_bi.loc[cm_, "basal_error"], valid_bi.loc[cm_, "isf_error"],
                c=color, label=str(ctrl), alpha=0.7, s=60, edgecolors="k", linewidths=0.5,
            )
        if np.std(x_b) > 1e-6 and np.std(y_b) > 1e-6:
            slope, intercept, r_val, p_val, _ = stats.linregress(x_b, y_b)
            x_line = np.linspace(x_b.min(), x_b.max(), 100)
            ax.plot(x_line, slope * x_line + intercept, "r--", lw=2,
                    label=f"r={r_val:.3f}, p={p_val:.3f}")
        ax.axhline(0, color="grey", ls=":", lw=0.8)
        ax.axvline(0, color="grey", ls=":", lw=0.8)
        ax.legend(fontsize=8)
    ax.set_xlabel("Basal Error (U/h)")
    ax.set_ylabel("ISF Error (relative)")
    ax.set_title("H4: Basal Independence from ISF")

    # ── Panel 5: Coupling by controller ──────────────────────────────────
    ax = axes[1, 1]
    h5_data = h3_result  # we'll pull from h5 at call site, but use errors
    # Re-compute per-controller coupling for viz
    ctrl_labels_viz: list[str] = []
    isf_cr_r_viz: list[float] = []
    basal_isf_r_viz: list[float] = []
    for ctrl in sorted(errors["controller"].unique()):
        ctrl_str = str(ctrl)
        ce = errors[errors["controller"] == ctrl]
        m1 = ce["isf_error"].notna() & ce["cr_error"].notna()
        v1 = ce[m1]
        r1 = np.nan
        if len(v1) >= 4 and np.std(v1["isf_error"]) > 1e-6 and np.std(v1["cr_error"]) > 1e-6:
            r1, _ = stats.pearsonr(v1["isf_error"].values, v1["cr_error"].values)
        m2 = ce["basal_error"].notna() & ce["isf_error"].notna()
        v2 = ce[m2]
        r2 = np.nan
        if len(v2) >= 4 and np.std(v2["basal_error"]) > 1e-6 and np.std(v2["isf_error"]) > 1e-6:
            r2, _ = stats.pearsonr(v2["basal_error"].values, v2["isf_error"].values)
        ctrl_labels_viz.append(ctrl_str)
        isf_cr_r_viz.append(abs(r1) if not np.isnan(r1) else 0)
        basal_isf_r_viz.append(abs(r2) if not np.isnan(r2) else 0)

    if ctrl_labels_viz:
        x_pos = np.arange(len(ctrl_labels_viz))
        width = 0.35
        ax.bar(x_pos - width / 2, isf_cr_r_viz, width, label="|r| ISF↔CR", color="#e74c3c", alpha=0.8)
        ax.bar(x_pos + width / 2, basal_isf_r_viz, width, label="|r| Basal↔ISF", color="#3498db", alpha=0.8)
        ax.set_xticks(x_pos)
        ax.set_xticklabels(ctrl_labels_viz, rotation=30, ha="right", fontsize=8)
        ax.axhline(0.3, color="red", ls="--", lw=1, label="Coupling threshold")
        ax.axhline(0.2, color="blue", ls="--", lw=1, label="Independence threshold")
        ax.legend(fontsize=7)
        ax.set_ylim(0, 1.0)
    ax.set_ylabel("|Pearson r|")
    ax.set_title("H5: Coupling Strength by Controller")

    # ── Panel 6: Settings error correlation heatmap ──────────────────────
    ax = axes[1, 2]
    labels_hm = ["ISF", "CR", "Basal"]
    r_matrix = np.full((3, 3), np.nan)
    col_pairs = [
        ("isf_error", "isf_error"), ("isf_error", "cr_error"), ("isf_error", "basal_error"),
        ("cr_error", "isf_error"), ("cr_error", "cr_error"), ("cr_error", "basal_error"),
        ("basal_error", "isf_error"), ("basal_error", "cr_error"), ("basal_error", "basal_error"),
    ]
    label_map = {"isf_error": 0, "cr_error": 1, "basal_error": 2}
    for ci, cj in col_pairs:
        ii, jj = label_map[ci], label_map[cj]
        if ii == jj:
            r_matrix[ii, jj] = 1.0
        else:
            mask = errors[ci].notna() & errors[cj].notna()
            v = errors[mask]
            if len(v) >= 5 and np.std(v[ci]) > 1e-6 and np.std(v[cj]) > 1e-6:
                r_val, _ = stats.pearsonr(v[ci].values, v[cj].values)
                r_matrix[ii, jj] = r_val

    im = ax.imshow(r_matrix, cmap="RdBu_r", vmin=-1, vmax=1, aspect="equal")
    ax.set_xticks(range(3))
    ax.set_xticklabels(labels_hm, fontsize=10)
    ax.set_yticks(range(3))
    ax.set_yticklabels(labels_hm, fontsize=10)
    for i in range(3):
        for j in range(3):
            val = r_matrix[i, j]
            txt = f"{val:.2f}" if not np.isnan(val) else "N/A"
            ax.text(j, i, txt, ha="center", va="center", fontsize=12, fontweight="bold",
                    color="white" if abs(val) > 0.5 else "black" if not np.isnan(val) else "grey")
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04, label="Pearson r")
    ax.set_title("Settings Error Correlation Matrix")

    plt.tight_layout(rect=[0, 0, 1, 0.95])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(output_path), dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Visualization saved → {output_path}")


# ══════════════════════════════════════════════════════════════════════════════
# JSON-safe serialisation
# ══════════════════════════════════════════════════════════════════════════════

def _jsonify(obj):
    """Recursively convert numpy types for JSON serialisation."""
    if isinstance(obj, dict):
        return {k: _jsonify(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonify(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        v = float(obj)
        return None if np.isnan(v) else v
    if isinstance(obj, np.ndarray):
        return _jsonify(obj.tolist())
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, float) and np.isnan(obj):
        return None
    return obj


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    t0 = time.time()
    print("=" * 70)
    print("EXP-2737: Settings Interaction Matrix")
    print("=" * 70)

    # ── Load data ─────────────────────────────────────────────────────────
    grid = load_data()

    # ── Step 1: Independent extraction ────────────────────────────────────
    print("\n▶ Step 1: Extracting settings independently …")
    print("  ISF events …")
    isf_events = extract_isf_events(grid)
    print(f"    → {len(isf_events):,} ISF events across {isf_events['patient_id'].nunique()} patients")

    print("  CR events …")
    cr_events = extract_cr_events(grid)
    print(f"    → {len(cr_events):,} CR events across {cr_events['patient_id'].nunique()} patients")

    print("  Basal drift events …")
    basal_events = extract_basal_events(grid)
    print(f"    → {len(basal_events):,} basal events across {basal_events['patient_id'].nunique()} patients")

    print("  Computing per-patient settings …")
    settings = compute_patient_settings(isf_events, cr_events, basal_events)
    errors = compute_settings_errors(settings)
    n_valid = errors[["isf_error", "cr_error", "basal_error"]].notna().sum()
    print(f"    → {len(settings)} patients; valid errors: ISF={n_valid['isf_error']}, "
          f"CR={n_valid['cr_error']}, Basal={n_valid['basal_error']}")

    # ── Step 2: H1 — ISF↔CR coupling ─────────────────────────────────────
    print("\n▶ Step 2: Testing H1 — ISF↔CR coupling …")
    h1 = test_h1_coupling(errors)
    print(f"    H1 verdict: {h1['verdict']}  ({h1.get('interpretation', '')})")

    # ── Step 2b: H2 — ISF perturbation → CR ──────────────────────────────
    print("\n▶ Step 2b: Testing H2 — ISF perturbation → CR sensitivity …")
    h2 = test_h2_perturbation(grid, settings)
    print(f"    H2 verdict: {h2['verdict']}  ({h2.get('interpretation', '')})")

    # ── Step 3: H3 — Joint vs independent ─────────────────────────────────
    print("\n▶ Step 3: Testing H3 — Joint vs independent optimisation …")
    h3 = test_h3_joint_vs_independent(isf_events, cr_events, basal_events, settings)
    print(f"    H3 verdict: {h3['verdict']}  ({h3.get('interpretation', '')})")

    # ── Step 4: H4 — Basal separability ───────────────────────────────────
    print("\n▶ Step 4: Testing H4 — Basal separability …")
    h4 = test_h4_basal_separability(errors)
    print(f"    H4 verdict: {h4['verdict']}  ({h4.get('interpretation', '')})")

    # ── Step 5: H5 — Controller-dependent coupling ────────────────────────
    print("\n▶ Step 5: Testing H5 — Controller-dependent coupling …")
    h5 = test_h5_controller_coupling(errors)
    print(f"    H5 verdict: {h5['verdict']}  ({h5.get('interpretation', '')})")

    # ── Correlation matrix ────────────────────────────────────────────────
    corr_matrix = compute_correlation_matrix(errors)

    # ── Visualization ─────────────────────────────────────────────────────
    print("\n▶ Generating visualizations …")
    viz_path = VIZ_DIR / "settings_interactions.png"
    create_visualizations(errors, h2, h3, corr_matrix, viz_path)

    # ── Assemble results ──────────────────────────────────────────────────
    elapsed = time.time() - t0

    results = {
        "experiment": f"EXP-{EXP_ID}",
        "title": "Settings Interaction Matrix: ISF / CR / Basal Coupling",
        "scientific_question": (
            "Do ISF, CR, and basal settings interact? If ISF extraction is wrong, "
            "does that systematically bias CR extraction? Does joint optimisation "
            "beat independent optimisation?"
        ),
        "n_patients": int(len(settings)),
        "n_isf_events": int(len(isf_events)),
        "n_cr_events": int(len(cr_events)),
        "n_basal_events": int(len(basal_events)),
        "controllers": {
            str(k): int(v) for k, v in
            errors["controller"].value_counts().items()
        },
        "hypotheses": {
            "h1_isf_cr_coupling": h1,
            "h2_isf_perturbation_cr_sensitivity": h2,
            "h3_joint_vs_independent": h3,
            "h4_basal_separability": h4,
            "h5_controller_dependent_coupling": h5,
        },
        "correlation_matrix": corr_matrix,
        "per_patient_settings": [
            {k: (round(v, 4) if isinstance(v, float) else v) for k, v in row.items()}
            for row in errors.to_dict("records")
        ],
        "metadata": {
            "egp_rate_mg_per_5min": EGP_RATE,
            "bolus_coeff": BOLUS_COEFF,
            "smb_coeff": SMB_COEFF,
            "excess_basal_coeff": EXCESS_BASAL_COEFF,
            "isf_horizon_h": ISF_HORIZON / STEPS_PER_HOUR,
            "cr_horizon_h": CR_HORIZON / STEPS_PER_HOUR,
            "drift_horizon_h": DRIFT_HORIZON / STEPS_PER_HOUR,
            "bg_floor": BG_FLOOR,
            "min_dose": MIN_DOSE,
            "min_carbs": MIN_CARBS,
            "min_events_per_patient": MIN_EVENTS,
        },
        "elapsed_seconds": round(elapsed, 1),
    }

    # ── Save results ──────────────────────────────────────────────────────
    out_path = RESULTS_DIR / f"exp-{EXP_ID}_settings_interactions.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(_jsonify(results), f, indent=2)
    print(f"\n  Results saved → {out_path}")

    # ── Summary ───────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("HYPOTHESIS VERDICTS")
    print("=" * 70)
    for hname, hdata in results["hypotheses"].items():
        v = hdata.get("verdict", "?")
        interp = hdata.get("interpretation", "")
        symbol = "✓" if v == "PASS" else "✗" if v == "FAIL" else "?"
        print(f"  {symbol} {hname}: {v}")
        if interp:
            print(f"      {interp}")

    print("\n" + "-" * 70)
    print("CLINICAL IMPLICATIONS")
    print("-" * 70)

    h1v = h1.get("verdict", "")
    h2v = h2.get("verdict", "")
    h3v = h3.get("verdict", "")
    h4v = h4.get("verdict", "")

    if h1v == "PASS" or h2v == "PASS":
        print("  ⚠  ISF and CR are coupled — independent extraction introduces bias.")
        print("     Recommendation: use joint optimisation or iterative refinement.")
    else:
        print("  ✓  ISF and CR are effectively independent — separate extraction is valid.")

    if h3v == "PASS":
        imp = h3.get("overall_improvement_pct", 0)
        print(f"  ⚠  Joint optimisation improves MAE by {imp:.1f}% — worth the complexity.")
    else:
        print("  ✓  Independent optimisation is adequate — joint approach is not necessary.")

    if h4v == "PASS":
        print("  ✓  Basal settings can be extracted independently of ISF/CR.")
    else:
        print("  ⚠  Basal is coupled — consider joint basal+ISF extraction.")

    print(f"\nCompleted in {elapsed:.1f}s ({elapsed / 60:.1f}min)")
    print("=" * 70)


if __name__ == "__main__":
    main()
