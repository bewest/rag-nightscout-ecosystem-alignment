#!/usr/bin/env python3
"""EXP-2734: Temporal Cross-Validation of Settings Extraction.

Train ISF and CR extraction on the first 75% of each patient's timeline,
test on the last 25%.  This is the CRITICAL validation step: do extracted
settings generalize to future data, or do they overfit to the training
period?

Prior results:
  EXP-2720/2723: Independent-event ISF — 29% lower MAE, 90.5% improve
  EXP-2729:      CR extraction — 95.5% improve with deconfounded CR
  EXP-2726b:     Empirical ISF validated prospectively — 29/31 improve
  EXP-2733:      Simulator-based ISF = 13.8 (profile gap 3.4×)

Hypotheses:
  H1: Empirical ISF generalizes — >60% patients improve MAE on TEST data
  H2: Empirical CR generalizes — >60% patients improve MAE on TEST data
  H3: Train-test ISF stability — median |Δ ISF| / train_isf < 30%
  H4: No overfitting — test improvement > 0.5 × train improvement
  H5: Population ISF outperforms profile but worse than individual

Author: Copilot + bewest
Date: 2025-07-22
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from numpy.linalg import lstsq
from scipy import stats

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ── Paths ────────────────────────────────────────────────────────────────────

GRID = Path("externals/ns-parquet/training/grid.parquet")
DS = Path("externals/ns-parquet/training/devicestatus.parquet")
MANIFEST = Path("externals/experiments/autoprepare-qualified.json")
RESULTS_DIR = Path("externals/experiments")
OUT_JSON = RESULTS_DIR / "exp-2734_temporal_crossval.json"
VIZ_DIR = Path("visualizations/temporal-crossval")

EXP_ID = "EXP-2734"
EXP_TITLE = "Temporal Cross-Validation — Do Settings Generalize?"

# ── Tuning constants ─────────────────────────────────────────────────────────

BG_FLOOR = 180.0
MIN_DOSE = 0.3
HORIZON_STEPS = 24   # 2 h at 5-min intervals (ISF)
MEAL_HORIZON = 48    # 4 h at 5-min intervals (CR)
MIN_GAP_STEPS = 24   # 2 h gap for ISF independence
MEAL_GAP_STEPS = 48  # 4 h gap for CR independence
MIN_CARBS = 5.0
MIN_TEST_EVENTS = 5  # skip patients with < 5 test events

# Channel coefficients (from EXP-2698)
BOLUS_COEFF = -129.2
SMB_COEFF = -123.6
EXCESS_BASAL_COEFF = -130.5

TRAIN_FRAC = 0.75

# ── Data loading ─────────────────────────────────────────────────────────────


def load_data():
    """Load grid parquet, devicestatus, and qualified-patient manifest."""
    print("Loading data...")
    grid = pd.read_parquet(GRID)
    ds = pd.read_parquet(DS)
    manifest = json.loads(MANIFEST.read_text())
    qual = manifest["qualified_patients"]
    ctrl_map = ds.groupby("patient_id")["controller"].first().to_dict()
    grid = grid[grid["patient_id"].isin(qual)].copy()
    grid["controller"] = grid["patient_id"].map(ctrl_map).fillna("unknown")
    grid = grid.sort_values(["patient_id", "time"]).reset_index(drop=True)
    print(f"  {len(grid):,} rows, {grid['patient_id'].nunique()} patients")
    return grid


# ── Temporal split ───────────────────────────────────────────────────────────


def temporal_split(pg):
    """Return (train_df, test_df) for a single patient's sorted grid."""
    n = len(pg)
    cut = int(n * TRAIN_FRAC)
    return pg.iloc[:cut].copy(), pg.iloc[cut:].copy()


# ── ISF event extraction ────────────────────────────────────────────────────


def extract_correction_events(pg, pid, profile_isf, ctrl):
    """Extract correction events from a single patient's grid slice.

    BG >= 180, carbs < 5 g in 2 h window, dose >= 0.3 U, demand_isf > 0.
    """
    h = HORIZON_STEPS
    n = len(pg)
    if n < h + 2:
        return []

    glucose = pg["glucose"].values
    bolus = pg["bolus"].values
    smb = pg["bolus_smb"].values if "bolus_smb" in pg.columns else np.zeros(n)
    smb = np.where(np.isnan(smb), 0.0, smb)
    net_basal = pg["net_basal"].values if "net_basal" in pg.columns else np.zeros(n)
    net_basal = np.where(np.isnan(net_basal), 0.0, net_basal)
    carbs = pg["carbs"].values if "carbs" in pg.columns else np.zeros(n)
    carbs = np.where(np.isnan(carbs), 0.0, carbs)
    iob = pg["iob"].values if "iob" in pg.columns else np.full(n, np.nan)

    events = []
    for i in range(1, n - h):
        bg0 = glucose[i]
        bg_end = glucose[i + h]
        if np.isnan(bg0) or np.isnan(bg_end):
            continue
        if bg0 < BG_FLOOR:
            continue

        bolus_2h = float(np.nansum(bolus[i:i + h]))
        smb_2h = float(np.nansum(smb[i:i + h]))
        excess_basal_2h = float(np.nansum(net_basal[i:i + h])) / 12.0
        carbs_2h = float(np.nansum(carbs[i:i + h]))

        if carbs_2h > 5.0:
            continue

        total_insulin = bolus_2h + smb_2h + excess_basal_2h
        if total_insulin < MIN_DOSE:
            continue

        observed_drop = bg0 - bg_end
        demand_isf = observed_drop / total_insulin
        if demand_isf <= 0:
            continue

        try:
            hour = int(pd.Timestamp(pg["time"].iloc[i]).hour)
        except Exception:
            hour = 0

        events.append({
            "patient_id": pid,
            "time_idx": i,
            "bg0": bg0,
            "bg_end": bg_end,
            "observed_drop": observed_drop,
            "total_insulin": total_insulin,
            "demand_isf": demand_isf,
            "bolus_2h": bolus_2h,
            "smb_2h": smb_2h,
            "excess_basal_2h": excess_basal_2h,
            "iob_start": float(iob[i]) if not np.isnan(iob[i]) else 0.0,
            "hour": hour,
            "controller": ctrl,
            "profile_isf": profile_isf,
        })

    return events


# ── CR event extraction ──────────────────────────────────────────────────────


def extract_meal_events(pg, pid, ctrl):
    """Extract meal events from a single patient's grid slice.

    carbs > 5 g in ±30-min window, bolus present, valid BG at t and t+4h,
    no meal stacking in [t+30min .. t+4h).
    """
    h = MEAL_HORIZON
    n = len(pg)
    if n < h + 7:
        return []

    glucose = pg["glucose"].values.astype(float)
    carbs = pg["carbs"].values.astype(float)
    carbs = np.where(np.isnan(carbs), 0.0, carbs)
    bolus = pg["bolus"].values.astype(float)
    bolus = np.where(np.isnan(bolus), 0.0, bolus)
    smb = pg["bolus_smb"].values.astype(float) if "bolus_smb" in pg.columns else np.zeros(n)
    smb = np.where(np.isnan(smb), 0.0, smb)
    net_basal = pg["net_basal"].values.astype(float) if "net_basal" in pg.columns else np.zeros(n)
    net_basal = np.where(np.isnan(net_basal), 0.0, net_basal)
    iob = pg["iob"].values.astype(float) if "iob" in pg.columns else np.zeros(n)
    iob = np.where(np.isnan(iob), 0.0, iob)
    times = pg["time"].values

    has_scheduled_cr = "scheduled_cr" in pg.columns
    if has_scheduled_cr:
        sched_cr = pg["scheduled_cr"].values.astype(float)
        sched_cr = np.where(np.isnan(sched_cr), 0.0, sched_cr)
    else:
        sched_cr = np.zeros(n)

    events = []
    for i in range(6, n - h):
        lo = max(i - 6, 0)
        hi = min(i + 7, n)
        window_carbs = float(np.sum(carbs[lo:hi]))
        if window_carbs < MIN_CARBS:
            continue

        window_bolus = float(np.sum(bolus[lo:hi]))
        if window_bolus <= 0:
            continue

        bg0 = glucose[i]
        bg_end = glucose[i + h]
        if np.isnan(bg0) or np.isnan(bg_end):
            continue

        future_carbs = float(np.sum(carbs[i + 6:i + h]))
        if future_carbs >= MIN_CARBS:
            continue

        bolus_4h = float(np.nansum(bolus[i:i + h]))
        smb_4h = float(np.nansum(smb[i:i + h]))
        excess_basal_4h = float(np.nansum(net_basal[i:i + h])) / 12.0
        total_insulin = bolus_4h + smb_4h + excess_basal_4h
        if total_insulin < MIN_DOSE:
            continue

        bg_change = bg_end - bg0
        try:
            hour = int(pd.Timestamp(times[i]).hour) if not pd.isna(times[i]) else 0
        except Exception:
            hour = 0

        profile_cr_val = float(np.median(sched_cr[lo:hi])) if has_scheduled_cr else 0.0
        if profile_cr_val <= 0:
            profile_cr_val = 0.0
        observed_cr = window_carbs / max(total_insulin, 0.1)

        events.append({
            "patient_id": pid,
            "time_idx": i,
            "bg0": bg0,
            "bg_end": bg_end,
            "bg_change": bg_change,
            "carbs": window_carbs,
            "bolus_4h": bolus_4h,
            "smb_4h": smb_4h,
            "excess_basal_4h": excess_basal_4h,
            "total_insulin": total_insulin,
            "iob_start": float(iob[i]),
            "hour": hour,
            "block_idx": min(hour // 4, 5),
            "controller": ctrl,
            "profile_cr": profile_cr_val,
            "observed_cr": observed_cr,
        })

    return events


# ── Independence filtering ───────────────────────────────────────────────────


def filter_independent(ev_df, gap_steps):
    """Keep only events with >= gap_steps from previous event per patient."""
    if len(ev_df) == 0:
        return ev_df
    ev_df = ev_df.sort_values(["patient_id", "time_idx"]).copy()
    keep = []
    last_idx: dict[str, int] = {}

    for _, row in ev_df.iterrows():
        pid = row["patient_id"]
        tidx = row["time_idx"]
        if pid not in last_idx or (tidx - last_idx[pid]) >= gap_steps:
            keep.append(True)
            last_idx[pid] = tidx
        else:
            keep.append(False)

    ev_df["independent"] = keep
    return ev_df[ev_df["independent"]].drop(columns=["independent"]).copy()


# ── Deconfounding (ISF) ─────────────────────────────────────────────────────


def deconfound_isf(events):
    """Deconfound demand_isf by regressing out BG0, IOB, hour (OLS).

    Returns median of (residuals + grand median).
    """
    y = events["demand_isf"].values.copy()
    if len(y) < 4 or np.std(y) < 1e-9:
        return float(np.median(y))

    bg0 = events["bg0"].values
    iob = events["iob_start"].values
    hour_sin = np.sin(2 * np.pi * events["hour"].values / 24.0)
    hour_cos = np.cos(2 * np.pi * events["hour"].values / 24.0)
    X = np.column_stack([bg0, iob, hour_sin, hour_cos, np.ones(len(y))])

    beta, _, _, _ = lstsq(X, y, rcond=None)
    residuals = y - X @ beta
    return float(np.median(residuals) + np.median(y))


# ── Deconfounding (CR) ──────────────────────────────────────────────────────


def deconfound_cr(events):
    """Deconfound observed_cr by regressing out BG0, total_insulin (OLS)."""
    y = events["observed_cr"].values.copy()
    if len(y) < 4 or np.std(y) < 1e-9:
        return float(np.median(y))

    bg0 = events["bg0"].values
    dose = events["total_insulin"].values
    X = np.column_stack([bg0, dose, np.ones(len(y))])

    beta, _, _, _ = lstsq(X, y, rcond=None)
    residuals = y - X @ beta
    return float(np.median(residuals) + np.median(y))


# ── Main pipeline ────────────────────────────────────────────────────────────


def run_temporal_crossval(grid):
    """Run the full temporal cross-validation pipeline.

    For each patient:
      1. Temporal split: first 75% → train, last 25% → test
      2. Extract ISF events on train & test independently
      3. Extract CR events on train & test independently
      4. Derive per-patient settings on train, evaluate on test
    """
    print("\nRunning temporal cross-validation...")
    patients = grid["patient_id"].unique()
    records = []

    # Population ISF: collect all train ISFs first pass
    all_train_isf_events = []

    per_patient_data: dict = {}

    for pid in patients:
        pg = grid[grid["patient_id"] == pid].sort_values("time").reset_index(drop=True)
        ctrl = pg["controller"].iloc[0] if "controller" in pg.columns else "unknown"

        if "scheduled_isf" not in pg.columns:
            continue
        profile_isf = float(np.nanmedian(pg["scheduled_isf"].values))
        if np.isnan(profile_isf) or profile_isf <= 0:
            continue

        train_g, test_g = temporal_split(pg)

        # ── ISF events ──
        train_isf_ev = extract_correction_events(train_g, pid, profile_isf, ctrl)
        test_isf_ev = extract_correction_events(test_g, pid, profile_isf, ctrl)

        # ── CR events ──
        train_cr_ev = extract_meal_events(train_g, pid, ctrl)
        test_cr_ev = extract_meal_events(test_g, pid, ctrl)

        per_patient_data[pid] = {
            "ctrl": ctrl,
            "profile_isf": profile_isf,
            "train_isf_ev": pd.DataFrame(train_isf_ev),
            "test_isf_ev": pd.DataFrame(test_isf_ev),
            "train_cr_ev": pd.DataFrame(train_cr_ev),
            "test_cr_ev": pd.DataFrame(test_cr_ev),
        }
        all_train_isf_events.extend(train_isf_ev)

    # Independence-filter train events and compute population ISF
    all_train_isf_df = pd.DataFrame(all_train_isf_events)
    if len(all_train_isf_df) > 0:
        all_train_isf_indep = filter_independent(all_train_isf_df, MIN_GAP_STEPS)
        population_isf = float(np.median(all_train_isf_indep["demand_isf"]))
    else:
        population_isf = 50.0  # fallback

    print(f"  Population ISF (pooled train): {population_isf:.1f}")

    # ── Per-patient evaluation ──
    for pid, d in per_patient_data.items():
        ctrl = d["ctrl"]
        profile_isf = d["profile_isf"]

        # Independence filter
        train_isf = filter_independent(d["train_isf_ev"], MIN_GAP_STEPS) if len(d["train_isf_ev"]) > 0 else d["train_isf_ev"]
        test_isf = filter_independent(d["test_isf_ev"], MIN_GAP_STEPS) if len(d["test_isf_ev"]) > 0 else d["test_isf_ev"]
        train_cr = filter_independent(d["train_cr_ev"], MEAL_GAP_STEPS) if len(d["train_cr_ev"]) > 0 else d["train_cr_ev"]
        test_cr = filter_independent(d["test_cr_ev"], MEAL_GAP_STEPS) if len(d["test_cr_ev"]) > 0 else d["test_cr_ev"]

        n_train_isf = len(train_isf)
        n_test_isf = len(test_isf)
        n_train_cr = len(train_cr)
        n_test_cr = len(test_cr)

        # ── Train ISF ──
        if n_train_isf >= 3:
            empirical_isf = deconfound_isf(train_isf)
        elif n_train_isf > 0:
            empirical_isf = float(np.median(train_isf["demand_isf"]))
        else:
            empirical_isf = profile_isf

        # Clamp ISF to physiological range [5, 500]
        empirical_isf = float(np.clip(empirical_isf, 5.0, 500.0))

        # ── Train CR ──
        profile_cr = 0.0
        if n_train_cr > 0:
            pcr_vals = train_cr["profile_cr"].values
            profile_cr = float(np.median(pcr_vals[pcr_vals > 0])) if np.any(pcr_vals > 0) else 0.0

        if n_train_cr >= 4:
            empirical_cr = deconfound_cr(train_cr)
        elif n_train_cr > 0:
            empirical_cr = float(np.median(train_cr["observed_cr"]))
        else:
            empirical_cr = profile_cr if profile_cr > 0 else 10.0

        # Clamp CR to [2, 50]
        empirical_cr = float(np.clip(empirical_cr, 2.0, 50.0))

        # ── Test ISF evaluation ──
        isf_profile_mae = np.nan
        isf_empirical_mae = np.nan
        isf_population_mae = np.nan
        isf_train_mae = np.nan
        isf_train_empirical_mae = np.nan

        if n_test_isf >= MIN_TEST_EVENTS:
            actual_drops = test_isf["observed_drop"].values
            doses = test_isf["total_insulin"].values
            pred_profile = doses * profile_isf
            pred_empirical = doses * empirical_isf
            pred_population = doses * population_isf

            isf_profile_mae = float(np.mean(np.abs(actual_drops - pred_profile)))
            isf_empirical_mae = float(np.mean(np.abs(actual_drops - pred_empirical)))
            isf_population_mae = float(np.mean(np.abs(actual_drops - pred_population)))

        if n_train_isf >= MIN_TEST_EVENTS:
            actual_drops_tr = train_isf["observed_drop"].values
            doses_tr = train_isf["total_insulin"].values
            isf_train_mae = float(np.mean(np.abs(actual_drops_tr - doses_tr * profile_isf)))
            isf_train_empirical_mae = float(np.mean(np.abs(actual_drops_tr - doses_tr * empirical_isf)))

        # ── Test CR evaluation ──
        cr_profile_mae = np.nan
        cr_empirical_mae = np.nan
        cr_train_mae = np.nan
        cr_train_empirical_mae = np.nan

        if n_test_cr >= MIN_TEST_EVENTS and profile_cr > 0:
            test_obs_cr = test_cr["observed_cr"].values
            cr_profile_mae = float(np.mean(np.abs(test_obs_cr - profile_cr)))
            cr_empirical_mae = float(np.mean(np.abs(test_obs_cr - empirical_cr)))

        if n_train_cr >= MIN_TEST_EVENTS and profile_cr > 0:
            train_obs_cr = train_cr["observed_cr"].values
            cr_train_mae = float(np.mean(np.abs(train_obs_cr - profile_cr)))
            cr_train_empirical_mae = float(np.mean(np.abs(train_obs_cr - empirical_cr)))

        # ── Test-period ISF (for stability check) ──
        test_isf_median = float(np.median(test_isf["demand_isf"])) if n_test_isf >= 3 else np.nan
        train_isf_median = float(np.median(train_isf["demand_isf"])) if n_train_isf >= 3 else np.nan

        # ── Test-period CR (for stability check) ──
        test_cr_median = float(np.median(test_cr["observed_cr"])) if n_test_cr >= 3 else np.nan
        train_cr_median = float(np.median(train_cr["observed_cr"])) if n_train_cr >= 3 else np.nan

        # ── Improvement flags ──
        isf_improves = bool(isf_empirical_mae < isf_profile_mae) if not (np.isnan(isf_empirical_mae) or np.isnan(isf_profile_mae)) else None
        cr_improves = bool(cr_empirical_mae < cr_profile_mae) if not (np.isnan(cr_empirical_mae) or np.isnan(cr_profile_mae)) else None

        records.append({
            "patient_id": str(pid),
            "controller": ctrl,
            "n_train_isf": n_train_isf,
            "n_test_isf": n_test_isf,
            "n_train_cr": n_train_cr,
            "n_test_cr": n_test_cr,
            "profile_isf": round(profile_isf, 2),
            "empirical_isf": round(empirical_isf, 2),
            "population_isf": round(population_isf, 2),
            "train_isf_median": round(train_isf_median, 2) if not np.isnan(train_isf_median) else None,
            "test_isf_median": round(test_isf_median, 2) if not np.isnan(test_isf_median) else None,
            "isf_profile_mae": round(isf_profile_mae, 2) if not np.isnan(isf_profile_mae) else None,
            "isf_empirical_mae": round(isf_empirical_mae, 2) if not np.isnan(isf_empirical_mae) else None,
            "isf_population_mae": round(isf_population_mae, 2) if not np.isnan(isf_population_mae) else None,
            "isf_train_profile_mae": round(isf_train_mae, 2) if not np.isnan(isf_train_mae) else None,
            "isf_train_empirical_mae": round(isf_train_empirical_mae, 2) if not np.isnan(isf_train_empirical_mae) else None,
            "profile_cr": round(profile_cr, 2),
            "empirical_cr": round(empirical_cr, 2),
            "train_cr_median": round(train_cr_median, 2) if not np.isnan(train_cr_median) else None,
            "test_cr_median": round(test_cr_median, 2) if not np.isnan(test_cr_median) else None,
            "cr_profile_mae": round(cr_profile_mae, 2) if not np.isnan(cr_profile_mae) else None,
            "cr_empirical_mae": round(cr_empirical_mae, 2) if not np.isnan(cr_empirical_mae) else None,
            "cr_train_profile_mae": round(cr_train_mae, 2) if not np.isnan(cr_train_mae) else None,
            "cr_train_empirical_mae": round(cr_train_empirical_mae, 2) if not np.isnan(cr_train_empirical_mae) else None,
            "isf_improves": isf_improves,
            "cr_improves": cr_improves,
        })

    pt_df = pd.DataFrame(records)
    return pt_df, population_isf


# ── Hypothesis tests ─────────────────────────────────────────────────────────


def test_h1_isf_generalizes(pt_df):
    """H1: Empirical ISF generalizes — >60% patients improve MAE on TEST data."""
    print("\n── H1: Empirical ISF generalizes to held-out test data ──")
    valid = pt_df.dropna(subset=["isf_profile_mae", "isf_empirical_mae"])
    valid = valid[valid["n_test_isf"] >= MIN_TEST_EVENTS]

    if len(valid) < 3:
        print("  SKIP: fewer than 3 patients with enough test ISF events")
        return {"verdict": "SKIP", "reason": "insufficient patients"}

    n_improve = int(valid["isf_improves"].sum())
    n_total = len(valid)
    pct = 100.0 * n_improve / n_total

    med_profile = float(valid["isf_profile_mae"].median())
    med_empirical = float(valid["isf_empirical_mae"].median())
    improvement_pct = float(100.0 * (med_profile - med_empirical) / max(med_profile, 1e-6))

    h1_pass = bool(pct > 60)
    print(f"  Patients evaluated: {n_total}")
    print(f"  Improved on test:   {n_improve}/{n_total} ({pct:.1f}%)")
    print(f"  Median profile MAE: {med_profile:.1f}")
    print(f"  Median empirical MAE: {med_empirical:.1f}")
    print(f"  Median MAE reduction: {improvement_pct:.1f}%")
    print(f"  H1 verdict: {'PASS' if h1_pass else 'FAIL'}")

    return {
        "verdict": "PASS" if h1_pass else "FAIL",
        "n_patients": n_total,
        "n_improve": n_improve,
        "pct_improve": round(pct, 1),
        "median_profile_mae": round(med_profile, 2),
        "median_empirical_mae": round(med_empirical, 2),
        "mae_reduction_pct": round(improvement_pct, 1),
    }


def test_h2_cr_generalizes(pt_df):
    """H2: Empirical CR generalizes — >60% patients improve MAE on TEST data."""
    print("\n── H2: Empirical CR generalizes to held-out test data ──")
    valid = pt_df.dropna(subset=["cr_profile_mae", "cr_empirical_mae"])
    valid = valid[valid["n_test_cr"] >= MIN_TEST_EVENTS]

    if len(valid) < 3:
        print("  SKIP: fewer than 3 patients with enough test CR events")
        return {"verdict": "SKIP", "reason": "insufficient patients"}

    n_improve = int(valid["cr_improves"].sum())
    n_total = len(valid)
    pct = 100.0 * n_improve / n_total

    med_profile = float(valid["cr_profile_mae"].median())
    med_empirical = float(valid["cr_empirical_mae"].median())
    improvement_pct = float(100.0 * (med_profile - med_empirical) / max(med_profile, 1e-6))

    h2_pass = bool(pct > 60)
    print(f"  Patients evaluated: {n_total}")
    print(f"  Improved on test:   {n_improve}/{n_total} ({pct:.1f}%)")
    print(f"  Median profile MAE: {med_profile:.1f}")
    print(f"  Median empirical MAE: {med_empirical:.1f}")
    print(f"  Median MAE reduction: {improvement_pct:.1f}%")
    print(f"  H2 verdict: {'PASS' if h2_pass else 'FAIL'}")

    return {
        "verdict": "PASS" if h2_pass else "FAIL",
        "n_patients": n_total,
        "n_improve": n_improve,
        "pct_improve": round(pct, 1),
        "median_profile_mae": round(med_profile, 2),
        "median_empirical_mae": round(med_empirical, 2),
        "mae_reduction_pct": round(improvement_pct, 1),
    }


def test_h3_isf_stability(pt_df):
    """H3: Train-test ISF stability — median |ΔISF|/train_isf < 30%."""
    print("\n── H3: Train-test ISF stability ──")
    valid = pt_df.dropna(subset=["train_isf_median", "test_isf_median"])

    if len(valid) < 3:
        print("  SKIP: fewer than 3 patients with train+test ISF medians")
        return {"verdict": "SKIP", "reason": "insufficient patients"}

    train_vals = valid["train_isf_median"].values
    test_vals = valid["test_isf_median"].values
    rel_diff = np.abs(train_vals - test_vals) / np.maximum(np.abs(train_vals), 1e-6)

    median_rel_diff = float(np.median(rel_diff))
    h3_pass = bool(median_rel_diff < 0.30)

    # Pearson correlation if enough patients
    r_val = np.nan
    p_val = np.nan
    if len(valid) >= 5 and np.std(train_vals) > 1e-6 and np.std(test_vals) > 1e-6:
        r_val, p_val = stats.pearsonr(train_vals, test_vals)
        r_val = float(r_val)
        p_val = float(p_val)

    print(f"  Patients evaluated:  {len(valid)}")
    print(f"  Median |ΔISF|/train: {median_rel_diff:.3f} ({100 * median_rel_diff:.1f}%)")
    if not np.isnan(r_val):
        print(f"  Pearson r:           {r_val:.3f} (p={p_val:.2e})")
    print(f"  H3 verdict: {'PASS' if h3_pass else 'FAIL'}")

    return {
        "verdict": "PASS" if h3_pass else "FAIL",
        "n_patients": len(valid),
        "median_rel_diff": round(median_rel_diff, 4),
        "median_rel_diff_pct": round(100.0 * median_rel_diff, 1),
        "pearson_r": round(r_val, 4) if not np.isnan(r_val) else None,
        "pearson_p": float(p_val) if not np.isnan(p_val) else None,
    }


def test_h4_no_overfitting(pt_df):
    """H4: No overfitting — test improvement >= 0.5 × train improvement.

    Compare train MAE improvement ratio vs test MAE improvement ratio.
    """
    print("\n── H4: No evidence of overfitting ──")
    valid = pt_df.dropna(subset=[
        "isf_profile_mae", "isf_empirical_mae",
        "isf_train_profile_mae", "isf_train_empirical_mae",
    ])
    valid = valid[
        (valid["n_test_isf"] >= MIN_TEST_EVENTS)
        & (valid["n_train_isf"] >= MIN_TEST_EVENTS)
    ]

    if len(valid) < 3:
        print("  SKIP: fewer than 3 patients with both train & test MAEs")
        return {"verdict": "SKIP", "reason": "insufficient patients"}

    # Per-patient improvement ratios (positive = empirical is better)
    train_imp = (
        (valid["isf_train_profile_mae"] - valid["isf_train_empirical_mae"])
        / valid["isf_train_profile_mae"].clip(lower=1e-6)
    ).values
    test_imp = (
        (valid["isf_profile_mae"] - valid["isf_empirical_mae"])
        / valid["isf_profile_mae"].clip(lower=1e-6)
    ).values

    med_train_imp = float(np.median(train_imp))
    med_test_imp = float(np.median(test_imp))

    # PASS if test improvement >= 50% of train improvement
    if med_train_imp > 0:
        ratio = med_test_imp / med_train_imp
        h4_pass = bool(ratio >= 0.5)
    else:
        ratio = np.nan
        h4_pass = bool(med_test_imp >= 0)

    print(f"  Patients evaluated:     {len(valid)}")
    print(f"  Median train improvement: {100 * med_train_imp:.1f}%")
    print(f"  Median test improvement:  {100 * med_test_imp:.1f}%")
    if not np.isnan(ratio):
        print(f"  Test/train ratio:         {ratio:.2f}")
    print(f"  H4 verdict: {'PASS' if h4_pass else 'FAIL'}")

    return {
        "verdict": "PASS" if h4_pass else "FAIL",
        "n_patients": len(valid),
        "median_train_improvement_pct": round(100.0 * med_train_imp, 1),
        "median_test_improvement_pct": round(100.0 * med_test_imp, 1),
        "test_train_ratio": round(float(ratio), 3) if not np.isnan(ratio) else None,
        "per_patient_train_imp": [round(float(x), 3) for x in train_imp],
        "per_patient_test_imp": [round(float(x), 3) for x in test_imp],
    }


def test_h5_population_ranking(pt_df):
    """H5: Population ISF outperforms profile but worse than individual.

    Expected ranking: empirical < population < profile MAE.
    """
    print("\n── H5: Population ISF ranking — empirical < population < profile ──")
    valid = pt_df.dropna(subset=[
        "isf_profile_mae", "isf_empirical_mae", "isf_population_mae",
    ])
    valid = valid[valid["n_test_isf"] >= MIN_TEST_EVENTS]

    if len(valid) < 3:
        print("  SKIP: fewer than 3 patients")
        return {"verdict": "SKIP", "reason": "insufficient patients"}

    n_pop_beats_profile = int((valid["isf_population_mae"] < valid["isf_profile_mae"]).sum())
    n_emp_beats_pop = int((valid["isf_empirical_mae"] < valid["isf_population_mae"]).sum())
    n_total = len(valid)

    pct_pop_beats_profile = 100.0 * n_pop_beats_profile / n_total
    pct_emp_beats_pop = 100.0 * n_emp_beats_pop / n_total

    h5_pass = bool(pct_pop_beats_profile > 60 and pct_emp_beats_pop > 50)

    print(f"  Patients evaluated: {n_total}")
    print(f"  Population < profile: {n_pop_beats_profile}/{n_total} ({pct_pop_beats_profile:.0f}%)")
    print(f"  Empirical < population: {n_emp_beats_pop}/{n_total} ({pct_emp_beats_pop:.0f}%)")
    print(f"  Median MAE — profile:    {valid['isf_profile_mae'].median():.1f}")
    print(f"  Median MAE — population: {valid['isf_population_mae'].median():.1f}")
    print(f"  Median MAE — empirical:  {valid['isf_empirical_mae'].median():.1f}")
    print(f"  H5 verdict: {'PASS' if h5_pass else 'FAIL'}")

    return {
        "verdict": "PASS" if h5_pass else "FAIL",
        "n_patients": n_total,
        "n_population_beats_profile": n_pop_beats_profile,
        "pct_population_beats_profile": round(pct_pop_beats_profile, 1),
        "n_empirical_beats_population": n_emp_beats_pop,
        "pct_empirical_beats_population": round(pct_emp_beats_pop, 1),
        "median_profile_mae": round(float(valid["isf_profile_mae"].median()), 2),
        "median_population_mae": round(float(valid["isf_population_mae"].median()), 2),
        "median_empirical_mae": round(float(valid["isf_empirical_mae"].median()), 2),
    }


# ── Visualization ────────────────────────────────────────────────────────────


def make_visualization(pt_df, h1_res, h2_res, h3_res, h4_res, h5_res):
    """Create 2×2 summary figure for temporal cross-validation."""
    VIZ_DIR.mkdir(parents=True, exist_ok=True)

    ctrl_colors = {
        "loop": "#1f77b4",
        "openaps": "#ff7f0e",
        "trio": "#2ca02c",
        "unknown": "#999999",
    }

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle(
        f"{EXP_ID}: {EXP_TITLE}",
        fontsize=14, fontweight="bold", y=0.98,
    )

    # ── Panel 1 (top-left): Test MAE comparison — profile vs empirical ISF ──
    ax = axes[0, 0]
    isf_valid = pt_df.dropna(subset=["isf_profile_mae", "isf_empirical_mae"])
    isf_valid = isf_valid[isf_valid["n_test_isf"] >= MIN_TEST_EVENTS].copy()

    if len(isf_valid) > 0:
        isf_valid = isf_valid.sort_values(
            "isf_profile_mae", ascending=False,
        ).reset_index(drop=True)
        x = np.arange(len(isf_valid))
        w = 0.35
        ax.bar(x - w / 2, isf_valid["isf_profile_mae"], w,
               color="#ff9999", edgecolor="k", linewidth=0.5, label="Profile ISF")
        ax.bar(x + w / 2, isf_valid["isf_empirical_mae"], w,
               color="#99ccff", edgecolor="k", linewidth=0.5, label="Empirical ISF")
        short_ids = [str(p)[:6] for p in isf_valid["patient_id"]]
        ax.set_xticks(x)
        ax.set_xticklabels(short_ids, rotation=60, ha="right", fontsize=6)
        ax.legend(fontsize=7, loc="upper right")
    ax.set_ylabel("MAE on TEST data (mg/dL)")
    ax.set_title("Test MAE: Profile vs Empirical ISF")
    h1v = h1_res.get("verdict", "SKIP")
    ax.text(0.02, 0.98, f"H1: {h1v}", transform=ax.transAxes,
            fontsize=9, va="top",
            color="green" if h1v == "PASS" else "red")

    # ── Panel 2 (top-right): Train vs test ISF scatter ──
    ax = axes[0, 1]
    stab_valid = pt_df.dropna(subset=["train_isf_median", "test_isf_median"])
    if len(stab_valid) > 0:
        colors = [ctrl_colors.get(c, "#999999") for c in stab_valid["controller"]]
        ax.scatter(stab_valid["train_isf_median"], stab_valid["test_isf_median"],
                   c=colors, s=40, alpha=0.7, edgecolors="k", linewidths=0.5)
        lo = min(stab_valid["train_isf_median"].min(),
                 stab_valid["test_isf_median"].min()) * 0.8
        hi = max(stab_valid["train_isf_median"].max(),
                 stab_valid["test_isf_median"].max()) * 1.2
        lo = max(lo, 0)
        ax.plot([lo, hi], [lo, hi], "k--", lw=1, alpha=0.5, label="y = x")
        ax.set_xlim(lo, hi)
        ax.set_ylim(lo, hi)
        ax.legend(fontsize=7)
    ax.set_xlabel("Train ISF (mg/dL/U)")
    ax.set_ylabel("Test ISF (mg/dL/U)")
    ax.set_title("Train vs Test ISF per Patient")
    h3v = h3_res.get("verdict", "SKIP")
    ax.text(0.02, 0.98, f"H3: {h3v}", transform=ax.transAxes,
            fontsize=9, va="top",
            color="green" if h3v == "PASS" else "red")

    # ── Panel 3 (bottom-left): Overfitting diagnostic ──
    ax = axes[1, 0]
    h4_train = h4_res.get("per_patient_train_imp", [])
    h4_test = h4_res.get("per_patient_test_imp", [])
    if len(h4_train) > 0 and len(h4_test) > 0:
        train_arr = np.array(h4_train) * 100
        test_arr = np.array(h4_test) * 100
        ax.scatter(train_arr, test_arr, s=40, alpha=0.7,
                   c="#1f77b4", edgecolors="k", linewidths=0.5)
        lim_lo = min(train_arr.min(), test_arr.min()) - 5
        lim_hi = max(train_arr.max(), test_arr.max()) + 5
        ax.plot([lim_lo, lim_hi], [lim_lo, lim_hi], "k--", lw=1, alpha=0.5,
                label="y = x (no overfit)")
        ax.plot([lim_lo, lim_hi], [(lim_lo) * 0.5, (lim_hi) * 0.5], "r:",
                lw=1, alpha=0.5, label="y = 0.5x (threshold)")
        ax.set_xlim(lim_lo, lim_hi)
        ax.set_ylim(lim_lo, lim_hi)
        ax.legend(fontsize=7, loc="upper left")
    ax.set_xlabel("Train improvement (%)")
    ax.set_ylabel("Test improvement (%)")
    ax.set_title("Overfitting Diagnostic")
    h4v = h4_res.get("verdict", "SKIP")
    ax.text(0.02, 0.98, f"H4: {h4v}", transform=ax.transAxes,
            fontsize=9, va="top",
            color="green" if h4v == "PASS" else "red")

    # ── Panel 4 (bottom-right): CR cross-validation ──
    ax = axes[1, 1]
    cr_valid = pt_df.dropna(subset=["cr_profile_mae", "cr_empirical_mae"])
    cr_valid = cr_valid[cr_valid["n_test_cr"] >= MIN_TEST_EVENTS].copy()

    if len(cr_valid) > 0:
        cr_valid = cr_valid.sort_values(
            "cr_profile_mae", ascending=False,
        ).reset_index(drop=True)
        x = np.arange(len(cr_valid))
        w = 0.35
        ax.bar(x - w / 2, cr_valid["cr_profile_mae"], w,
               color="#ff9999", edgecolor="k", linewidth=0.5, label="Profile CR")
        ax.bar(x + w / 2, cr_valid["cr_empirical_mae"], w,
               color="#99ccff", edgecolor="k", linewidth=0.5, label="Empirical CR")
        short_ids = [str(p)[:6] for p in cr_valid["patient_id"]]
        ax.set_xticks(x)
        ax.set_xticklabels(short_ids, rotation=60, ha="right", fontsize=6)
        ax.legend(fontsize=7, loc="upper right")
    ax.set_ylabel("MAE on TEST data (g/U)")
    ax.set_title("Test MAE: Profile vs Empirical CR")
    h2v = h2_res.get("verdict", "SKIP")
    ax.text(0.02, 0.98, f"H2: {h2v}", transform=ax.transAxes,
            fontsize=9, va="top",
            color="green" if h2v == "PASS" else "red")

    plt.tight_layout(rect=[0, 0, 1, 0.96])
    out_path = VIZ_DIR / "temporal_crossval.png"
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Visualization: {out_path}")


# ── Main ─────────────────────────────────────────────────────────────────────


def main():
    print("=" * 70)
    print(f"  {EXP_ID}: {EXP_TITLE}")
    print("=" * 70)

    # ── Load data ──
    grid = load_data()

    # ── Run cross-validation ──
    pt_df, population_isf = run_temporal_crossval(grid)
    if len(pt_df) == 0:
        print("ERROR: No patients processed. Exiting.")
        sys.exit(1)

    # ── Print summary table ──
    print(f"\n  {len(pt_df)} patients processed")
    print(f"  Population ISF: {population_isf:.1f}")

    print("\n" + "=" * 70)
    print("  PER-PATIENT TEMPORAL CROSS-VALIDATION")
    print("=" * 70)
    display_cols = [
        "patient_id", "controller",
        "n_train_isf", "n_test_isf",
        "profile_isf", "empirical_isf",
        "isf_profile_mae", "isf_empirical_mae", "isf_improves",
        "n_train_cr", "n_test_cr",
        "profile_cr", "empirical_cr",
        "cr_profile_mae", "cr_empirical_mae", "cr_improves",
    ]
    show_cols = [c for c in display_cols if c in pt_df.columns]
    with pd.option_context(
        "display.max_rows", None,
        "display.max_columns", None,
        "display.width", 200,
        "display.float_format", "{:.1f}".format,
    ):
        print(pt_df[show_cols].to_string(index=False))

    # ── Hypothesis tests ──
    h1_res = test_h1_isf_generalizes(pt_df)
    h2_res = test_h2_cr_generalizes(pt_df)
    h3_res = test_h3_isf_stability(pt_df)
    h4_res = test_h4_no_overfitting(pt_df)
    h5_res = test_h5_population_ranking(pt_df)

    verdicts = {
        "H1": h1_res.get("verdict", "SKIP"),
        "H2": h2_res.get("verdict", "SKIP"),
        "H3": h3_res.get("verdict", "SKIP"),
        "H4": h4_res.get("verdict", "SKIP"),
        "H5": h5_res.get("verdict", "SKIP"),
    }
    print(f"\nVerdict: {' '.join(f'{k}={v}' for k, v in verdicts.items())}")

    # ── Visualization ──
    print("\nGenerating visualizations...")
    make_visualization(pt_df, h1_res, h2_res, h3_res, h4_res, h5_res)

    # ── Assemble & save results ──
    results = {
        "experiment_id": EXP_ID,
        "title": EXP_TITLE,
        "method": "temporal_crossval_75_25",
        "train_fraction": TRAIN_FRAC,
        "n_patients": int(pt_df["patient_id"].nunique()),
        "population_isf": round(population_isf, 2),
        "hypotheses": {
            "H1_isf_generalizes": h1_res,
            "H2_cr_generalizes": h2_res,
            "H3_isf_stability": h3_res,
            "H4_no_overfitting": h4_res,
            "H5_population_ranking": h5_res,
        },
        "verdict_summary": verdicts,
        "per_patient": pt_df.to_dict(orient="records"),
        "population_summary": {
            "n_isf_evaluable": int(pt_df["isf_improves"].notna().sum()),
            "n_cr_evaluable": int(pt_df["cr_improves"].notna().sum()),
            "median_profile_isf": round(float(pt_df["profile_isf"].median()), 2),
            "median_empirical_isf": round(float(pt_df["empirical_isf"].median()), 2),
            "median_profile_cr": round(float(pt_df[pt_df["profile_cr"] > 0]["profile_cr"].median()), 2)
                if (pt_df["profile_cr"] > 0).any() else None,
            "median_empirical_cr": round(float(pt_df["empirical_cr"].median()), 2),
        },
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults: {OUT_JSON}")


if __name__ == "__main__":
    main()
