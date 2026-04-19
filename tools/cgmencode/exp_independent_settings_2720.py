#!/usr/bin/env python3
"""EXP-2720: Independent-Event Settings Extraction

Re-runs ISF extraction using ONLY independent events (≥2h gap between
events per patient, ~6K of 65K total). Compares per-patient settings
derived from independent events vs all events vs profile ISF.

The key question: does deconfounding via temporal independence yield
more accurate and precise per-patient ISF estimates?

Hypotheses:
  H1: Independent-event ISF differs from all-event ISF (paired Wilcoxon, p<0.05)
  H2: Independent-event ISF has lower within-patient CV (>50% of patients)
  H3: Independent-event ISF is closer to profile ISF (>50% of patients)
  H4: Independent-event ISF produces better BG predictions (lowest median MAE)

Design:
  - Extract correction events at BG≥180, carbs<5g in 2h, dose≥0.3U
  - Filter for temporal independence (≥2h gap between events per patient)
  - Per patient: compute median ISF from all events, independent events, profile
  - Test 4 hypotheses comparing ISF sources
  - 50/50 held-out split for H4 prediction test

Author: Copilot + bewest
Date: 2025-07-18
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

# ── Constants ──
GRID = Path("externals/ns-parquet/training/grid.parquet")
DS = Path("externals/ns-parquet/training/devicestatus.parquet")
MANIFEST = Path("externals/experiments/autoprepare-qualified.json")
RESULTS_DIR = Path("externals/experiments")
OUT_JSON = RESULTS_DIR / "exp-2720_independent_settings.json"
VIZ_DIR = Path("visualizations/independent-settings")

HORIZON_STEPS = 24  # 2h at 5-min intervals
BG_FLOOR = 180
MIN_DOSE = 0.3
MIN_GAP_STEPS = 24  # 2h gap for independence
CARB_HISTORY_STEPS = 48 * 12  # 48h at 5-min intervals

BOLUS_COEFF = -129.2
SMB_COEFF = -123.6
EXCESS_BASAL_COEFF = -130.5

TIME_BLOCKS = [(0, 4), (4, 8), (8, 12), (12, 16), (16, 20), (20, 24)]
BLOCK_LABELS = ["00-04", "04-08", "08-12", "12-16", "16-20", "20-24"]

EXP_ID = "EXP-2720"
EXP_TITLE = "Independent-Event Settings Extraction"


# ── Data loading (matches EXP-2710/2714) ──

def load_data():
    """Load grid, devicestatus, and qualified patients."""
    print("Loading data...")
    grid = pd.read_parquet(GRID)
    ds = pd.read_parquet(DS)
    manifest = json.loads(MANIFEST.read_text())
    qual = manifest["qualified_patients"]
    ctrl_map = ds.groupby("patient_id")["controller"].first().to_dict()
    grid = grid[grid["patient_id"].isin(qual)].copy()
    grid["controller"] = grid["patient_id"].map(ctrl_map).fillna("unknown")
    if not pd.api.types.is_datetime64_any_dtype(grid["time"]):
        grid["time"] = pd.to_datetime(grid["time"], utc=True)
    grid = grid.sort_values(["patient_id", "time"]).reset_index(drop=True)
    # Compute carbs_48h
    if "carbs" in grid.columns:
        grid = _compute_48h_carbs(grid)
    else:
        grid["carbs_48h"] = 0.0
    print(f"  {len(grid):,} rows, {grid['patient_id'].nunique()} patients")
    return grid


def _compute_48h_carbs(grid):
    """Add 48h rolling carb history — matches EXP-2710."""
    result = []
    for pid, pg in grid.groupby("patient_id"):
        pg = pg.sort_values("time").copy()
        carbs = pg["carbs"].fillna(0).values
        carbs_48h = np.zeros(len(carbs))
        cumsum = np.cumsum(carbs)
        for i in range(len(carbs)):
            start = max(0, i - CARB_HISTORY_STEPS)
            carbs_48h[i] = cumsum[i] - (cumsum[start - 1] if start > 0 else 0)
        pg["carbs_48h"] = carbs_48h
        result.append(pg)
    return pd.concat(result, ignore_index=True)


# ── Event extraction (matches EXP-2710 loop, adds time_idx) ──

def extract_events(grid):
    """Extract correction events with all features needed for multi-factor analysis.

    Identical to EXP-2710 event schema plus time_idx for independence filtering.
    """
    print("Extracting correction events...")
    h = HORIZON_STEPS
    has_smb = "bolus_smb" in grid.columns
    has_net_basal = "net_basal" in grid.columns
    has_carbs = "carbs" in grid.columns
    has_carbs_48h = "carbs_48h" in grid.columns
    events = []

    for pid in grid["patient_id"].unique():
        pg = grid[grid["patient_id"] == pid].sort_values("time").reset_index(drop=True)
        if len(pg) < h + 2:
            continue
        glucose = pg["glucose"].values
        bolus = pg["bolus"].values
        iob = pg["iob"].values if "iob" in pg.columns else np.full(len(pg), np.nan)
        smb = pg["bolus_smb"].values if has_smb else np.zeros(len(pg))
        net_basal = pg["net_basal"].values if has_net_basal else np.zeros(len(pg))
        carbs = pg["carbs"].values if has_carbs else np.zeros(len(pg))
        carbs_48h = pg["carbs_48h"].values if has_carbs_48h else np.zeros(len(pg))
        ctrl = pg["controller"].iloc[0] if "controller" in pg.columns else "unknown"

        if "scheduled_isf" in pg.columns:
            profile_isf = float(np.nanmedian(pg["scheduled_isf"].values))
        else:
            continue

        for i in range(1, len(pg) - h):
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

            # BGI subtraction
            expected_drop = total_insulin * profile_isf
            deviation = observed_drop - expected_drop

            # Channel decomposition (EXP-2698 coefficients)
            est_bolus = bolus_2h * BOLUS_COEFF
            est_smb = smb_2h * SMB_COEFF
            est_basal = excess_basal_2h * EXCESS_BASAL_COEFF
            residual_all_channels = deviation - est_bolus - est_smb - est_basal

            try:
                ts = pd.Timestamp(pg["time"].iloc[i])
                hour = ts.hour
            except Exception:
                hour = 0
            block_idx = min(hour // 4, 5)

            c48 = float(carbs_48h[i]) if not np.isnan(carbs_48h[i]) else 0.0

            events.append({
                "patient_id": pid,
                "time_idx": i,
                "bg0": bg0,
                "bg_end": bg_end,
                "observed_drop": observed_drop,
                "total_insulin": total_insulin,
                "demand_isf": demand_isf,
                "expected_drop": expected_drop,
                "deviation": deviation,
                "bolus_2h": bolus_2h,
                "smb_2h": smb_2h,
                "excess_basal_2h": excess_basal_2h,
                "est_bolus_effect": est_bolus,
                "est_smb_effect": est_smb,
                "est_basal_effect": est_basal,
                "residual_all_channels": residual_all_channels,
                "iob_start": float(iob[i]) if not np.isnan(iob[i]) else 0.0,
                "hour": hour,
                "block_idx": block_idx,
                "block_label": BLOCK_LABELS[block_idx],
                "carbs_48h": c48,
                "controller": ctrl,
                "profile_isf": profile_isf,
            })

    df = pd.DataFrame(events)
    if len(df) == 0:
        print("  WARNING: 0 events extracted")
        return df
    # Glycogen state classification (median split per patient)
    for pid in df["patient_id"].unique():
        mask = df["patient_id"] == pid
        med = df.loc[mask, "carbs_48h"].median()
        df.loc[mask, "glycogen_state"] = np.where(
            df.loc[mask, "carbs_48h"] >= med, "loaded", "depleted"
        )

    print(f"  {len(df):,} events, {df['patient_id'].nunique()} patients")
    return df


# ── Independence filtering ──

def filter_independent(ev):
    """Keep only events with ≥2h gap from previous event (same patient)."""
    ev = ev.sort_values(["patient_id", "time_idx"]).copy()
    keep = []
    last_idx = {}
    for _, row in ev.iterrows():
        pid = row["patient_id"]
        tidx = row["time_idx"]
        if pid not in last_idx or (tidx - last_idx[pid]) >= MIN_GAP_STEPS:
            keep.append(True)
            last_idx[pid] = tidx
        else:
            keep.append(False)
    ev["independent"] = keep
    return ev


# ── Hypothesis tests ──

def test_h1_isf_differs(ev_all, ev_indep):
    """H1: Independent-event ISF systematically differs from all-event ISF.

    Per patient: median ISF from all events vs independent events.
    Paired Wilcoxon signed-rank across patients. PASS if p<0.05.
    """
    print("\n── H1: Independent-event ISF differs from all-event ISF ──")

    med_all = ev_all.groupby("patient_id")["demand_isf"].median()
    med_ind = ev_indep.groupby("patient_id")["demand_isf"].median()
    common = sorted(set(med_all.index) & set(med_ind.index))

    if len(common) < 5:
        print("  SKIP: fewer than 5 shared patients")
        return {"h1_verdict": "SKIP", "reason": "insufficient patients"}

    vals_all = np.array([med_all[p] for p in common])
    vals_ind = np.array([med_ind[p] for p in common])

    # Guard against constant arrays
    if np.std(vals_all - vals_ind) < 1e-6:
        print("  SKIP: no variation in paired differences")
        return {"h1_verdict": "SKIP", "reason": "no variation"}

    try:
        stat_val, p_val = stats.wilcoxon(vals_all, vals_ind)
    except ValueError:
        p_val = 1.0
        stat_val = 0.0

    h1_pass = bool(p_val < 0.05)
    mean_diff = float(np.mean(vals_ind - vals_all))

    print(f"  Patients compared: {len(common)}")
    print(f"  Median ISF (all):   {np.median(vals_all):.1f}")
    print(f"  Median ISF (indep): {np.median(vals_ind):.1f}")
    print(f"  Mean paired diff:   {mean_diff:+.1f}")
    print(f"  Wilcoxon stat:      {stat_val:.1f}")
    print(f"  Wilcoxon p:         {p_val:.4e}")
    print(f"  H1 verdict: {'PASS' if h1_pass else 'FAIL'}")

    return {
        "h1_verdict": "PASS" if h1_pass else "FAIL",
        "n_patients": len(common),
        "median_isf_all": round(float(np.median(vals_all)), 2),
        "median_isf_independent": round(float(np.median(vals_ind)), 2),
        "mean_paired_diff": round(mean_diff, 2),
        "wilcoxon_stat": round(float(stat_val), 2),
        "wilcoxon_p": float(p_val),
        "per_patient_all": {str(p): round(float(med_all[p]), 2) for p in common},
        "per_patient_independent": {str(p): round(float(med_ind[p]), 2) for p in common},
    }


def test_h2_lower_cv(ev_all, ev_indep):
    """H2: Independent-event ISF has lower within-patient CV.

    Per patient: CV = std/mean of demand_isf.
    PASS if majority (>50%) have lower CV with independent events.
    """
    print("\n── H2: Independent-event ISF has lower within-patient CV ──")

    cv_all = {}
    cv_ind = {}

    for pid, g in ev_all.groupby("patient_id"):
        if len(g) < 5:
            continue
        m = g["demand_isf"].mean()
        s = g["demand_isf"].std()
        if abs(m) > 1e-6:
            cv_all[pid] = float(s / abs(m))

    for pid, g in ev_indep.groupby("patient_id"):
        if len(g) < 5:
            continue
        m = g["demand_isf"].mean()
        s = g["demand_isf"].std()
        if abs(m) > 1e-6:
            cv_ind[pid] = float(s / abs(m))

    common = sorted(set(cv_all.keys()) & set(cv_ind.keys()))

    if len(common) < 5:
        print("  SKIP: fewer than 5 shared patients with enough events")
        return {"h2_verdict": "SKIP", "reason": "insufficient patients"}

    n_lower = sum(1 for p in common if cv_ind[p] < cv_all[p])
    pct_lower = 100.0 * n_lower / len(common)
    h2_pass = bool(pct_lower > 50)

    med_cv_all = float(np.median([cv_all[p] for p in common]))
    med_cv_ind = float(np.median([cv_ind[p] for p in common]))

    print(f"  Patients compared: {len(common)}")
    print(f"  Median CV (all):   {med_cv_all:.3f}")
    print(f"  Median CV (indep): {med_cv_ind:.3f}")
    print(f"  Lower CV with independent: {n_lower}/{len(common)} ({pct_lower:.0f}%)")
    print(f"  H2 verdict: {'PASS' if h2_pass else 'FAIL'}")

    return {
        "h2_verdict": "PASS" if h2_pass else "FAIL",
        "n_patients": len(common),
        "median_cv_all": round(med_cv_all, 4),
        "median_cv_independent": round(med_cv_ind, 4),
        "n_lower_cv": n_lower,
        "pct_lower_cv": round(pct_lower, 1),
        "per_patient_cv_all": {str(p): round(cv_all[p], 4) for p in common},
        "per_patient_cv_independent": {str(p): round(cv_ind[p], 4) for p in common},
    }


def test_h3_closer_to_profile(ev_all, ev_indep):
    """H3: Independent-event ISF is closer to profile ISF.

    Per patient: |median_ISF - profile_ISF| for all vs independent.
    PASS if majority have smaller absolute error with independent events.
    """
    print("\n── H3: Independent-event ISF closer to profile ISF ──")

    # Profile ISF per patient (same across all events for a patient)
    profile_map = ev_all.groupby("patient_id")["profile_isf"].first().to_dict()
    med_all = ev_all.groupby("patient_id")["demand_isf"].median().to_dict()
    med_ind = ev_indep.groupby("patient_id")["demand_isf"].median().to_dict()

    common = sorted(set(med_all.keys()) & set(med_ind.keys()) & set(profile_map.keys()))

    if len(common) < 5:
        print("  SKIP: fewer than 5 shared patients")
        return {"h3_verdict": "SKIP", "reason": "insufficient patients"}

    err_all = {}
    err_ind = {}
    for p in common:
        prof = profile_map[p]
        err_all[p] = abs(med_all[p] - prof)
        err_ind[p] = abs(med_ind[p] - prof)

    n_closer = sum(1 for p in common if err_ind[p] < err_all[p])
    pct_closer = 100.0 * n_closer / len(common)
    h3_pass = bool(pct_closer > 50)

    med_err_all = float(np.median([err_all[p] for p in common]))
    med_err_ind = float(np.median([err_ind[p] for p in common]))

    print(f"  Patients compared: {len(common)}")
    print(f"  Median |ISF-profile| (all):   {med_err_all:.1f}")
    print(f"  Median |ISF-profile| (indep): {med_err_ind:.1f}")
    print(f"  Closer to profile with independent: {n_closer}/{len(common)} ({pct_closer:.0f}%)")
    print(f"  H3 verdict: {'PASS' if h3_pass else 'FAIL'}")

    return {
        "h3_verdict": "PASS" if h3_pass else "FAIL",
        "n_patients": len(common),
        "median_abs_err_all": round(med_err_all, 2),
        "median_abs_err_independent": round(med_err_ind, 2),
        "n_closer": n_closer,
        "pct_closer": round(pct_closer, 1),
        "per_patient_err_all": {str(p): round(err_all[p], 2) for p in common},
        "per_patient_err_independent": {str(p): round(err_ind[p], 2) for p in common},
    }


def test_h4_prediction_accuracy(ev_all, ev_indep):
    """H4: Independent-event ISF produces better held-out predictions.

    For each patient, split independent events 50/50:
      - Train: compute median ISF from first half
      - Test: predict BG drop on second half
    Compare MAE: independent-extracted ISF vs all-event ISF vs profile ISF.
    PASS if independent-event ISF has lowest median MAE.
    """
    print("\n── H4: Independent-event ISF produces better predictions ──")

    np.random.seed(42)
    patient_results = []

    # Precompute per-patient all-event median ISF
    all_med_isf = ev_all.groupby("patient_id")["demand_isf"].median().to_dict()
    profile_map = ev_all.groupby("patient_id")["profile_isf"].first().to_dict()

    for pid, g in ev_indep.groupby("patient_id"):
        if len(g) < 10:
            continue
        if pid not in all_med_isf or pid not in profile_map:
            continue

        g = g.sort_values("time_idx").reset_index(drop=True)
        n = len(g)
        mid = n // 2

        train = g.iloc[:mid]
        test = g.iloc[mid:]

        if len(train) < 3 or len(test) < 3:
            continue

        isf_indep = float(train["demand_isf"].median())
        isf_all = float(all_med_isf[pid])
        isf_profile = float(profile_map[pid])

        # Predict BG drop on held-out test set
        actual_drop = test["observed_drop"].values
        dose = test["total_insulin"].values

        pred_indep = isf_indep * dose
        pred_all = isf_all * dose
        pred_profile = isf_profile * dose

        mae_indep = float(np.mean(np.abs(actual_drop - pred_indep)))
        mae_all = float(np.mean(np.abs(actual_drop - pred_all)))
        mae_profile = float(np.mean(np.abs(actual_drop - pred_profile)))

        patient_results.append({
            "patient_id": str(pid),
            "n_train": int(len(train)),
            "n_test": int(len(test)),
            "isf_independent": round(isf_indep, 1),
            "isf_all_events": round(isf_all, 1),
            "isf_profile": round(isf_profile, 1),
            "mae_independent": round(mae_indep, 1),
            "mae_all_events": round(mae_all, 1),
            "mae_profile": round(mae_profile, 1),
        })

    if len(patient_results) < 5:
        print("  SKIP: fewer than 5 patients with enough independent events")
        return {"h4_verdict": "SKIP", "reason": "insufficient patients", "per_patient": []}

    maes_indep = [r["mae_independent"] for r in patient_results]
    maes_all = [r["mae_all_events"] for r in patient_results]
    maes_prof = [r["mae_profile"] for r in patient_results]

    med_mae_indep = float(np.median(maes_indep))
    med_mae_all = float(np.median(maes_all))
    med_mae_prof = float(np.median(maes_prof))

    h4_pass = bool(med_mae_indep <= med_mae_all and med_mae_indep <= med_mae_prof)
    n_best_indep = sum(
        1 for r in patient_results
        if r["mae_independent"] <= r["mae_all_events"]
        and r["mae_independent"] <= r["mae_profile"]
    )

    print(f"  Patients evaluated: {len(patient_results)}")
    print(f"  Median MAE (independent ISF): {med_mae_indep:.1f}")
    print(f"  Median MAE (all-event ISF):   {med_mae_all:.1f}")
    print(f"  Median MAE (profile ISF):     {med_mae_prof:.1f}")
    print(f"  Patients where indep is best: {n_best_indep}/{len(patient_results)}")
    print(f"  H4 verdict: {'PASS' if h4_pass else 'FAIL'}")

    return {
        "h4_verdict": "PASS" if h4_pass else "FAIL",
        "n_patients": len(patient_results),
        "median_mae_independent": round(med_mae_indep, 2),
        "median_mae_all_events": round(med_mae_all, 2),
        "median_mae_profile": round(med_mae_prof, 2),
        "n_best_independent": n_best_indep,
        "per_patient": patient_results,
    }


# ── Visualization ──

def make_visualization(h1_res, h2_res, h3_res, h4_res):
    """Create 2×2 panel figure summarizing all 4 hypotheses."""
    VIZ_DIR.mkdir(parents=True, exist_ok=True)
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("  matplotlib not available, skipping visualization")
        return

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle(f"{EXP_ID}: {EXP_TITLE}", fontsize=14, fontweight="bold")

    # Panel 1: Scatter — all-event ISF vs independent-event ISF per patient
    ax = axes[0, 0]
    if h1_res.get("per_patient_all") and h1_res.get("per_patient_independent"):
        pids = sorted(h1_res["per_patient_all"].keys())
        x_vals = [h1_res["per_patient_all"][p] for p in pids]
        y_vals = [h1_res["per_patient_independent"][p] for p in pids]
        ax.scatter(x_vals, y_vals, alpha=0.6, s=40, edgecolors="black", linewidth=0.5)
        lim_lo = min(min(x_vals), min(y_vals)) * 0.9
        lim_hi = max(max(x_vals), max(y_vals)) * 1.1
        ax.plot([lim_lo, lim_hi], [lim_lo, lim_hi], "r--", alpha=0.7, label="y = x")
        ax.set_xlim(lim_lo, lim_hi)
        ax.set_ylim(lim_lo, lim_hi)
        ax.legend(fontsize=8)
    ax.set_xlabel("All-event median ISF (mg/dL per U)")
    ax.set_ylabel("Independent-event median ISF")
    p_str = f"p={h1_res.get('wilcoxon_p', 'N/A'):.2e}" if isinstance(h1_res.get("wilcoxon_p"), float) else ""
    ax.set_title(f"H1: ISF Comparison [{h1_res.get('h1_verdict', 'N/A')}] {p_str}")
    ax.grid(True, alpha=0.3)

    # Panel 2: Bar — CV comparison per patient
    ax = axes[0, 1]
    if h2_res.get("per_patient_cv_all") and h2_res.get("per_patient_cv_independent"):
        pids = sorted(h2_res["per_patient_cv_all"].keys())
        cv_a = [h2_res["per_patient_cv_all"][p] for p in pids]
        cv_i = [h2_res["per_patient_cv_independent"][p] for p in pids]
        x = np.arange(len(pids))
        w = 0.35
        ax.bar(x - w / 2, cv_a, w, label="All events", alpha=0.7, color="#1976D2")
        ax.bar(x + w / 2, cv_i, w, label="Independent", alpha=0.7, color="#F44336")
        ax.set_xticks(x)
        ax.set_xticklabels([str(p)[:6] for p in pids], rotation=45, ha="right", fontsize=7)
        ax.legend(fontsize=8)
    ax.set_ylabel("CV (std / mean)")
    ax.set_title(f"H2: Within-Patient CV [{h2_res.get('h2_verdict', 'N/A')}]")

    # Panel 3: Bar — |ISF - profile| per patient
    ax = axes[1, 0]
    if h3_res.get("per_patient_err_all") and h3_res.get("per_patient_err_independent"):
        pids = sorted(h3_res["per_patient_err_all"].keys())
        ea = [h3_res["per_patient_err_all"][p] for p in pids]
        ei = [h3_res["per_patient_err_independent"][p] for p in pids]
        x = np.arange(len(pids))
        w = 0.35
        ax.bar(x - w / 2, ea, w, label="All events", alpha=0.7, color="#1976D2")
        ax.bar(x + w / 2, ei, w, label="Independent", alpha=0.7, color="#F44336")
        ax.set_xticks(x)
        ax.set_xticklabels([str(p)[:6] for p in pids], rotation=45, ha="right", fontsize=7)
        ax.legend(fontsize=8)
    ax.set_ylabel("|median ISF − profile ISF|")
    ax.set_title(f"H3: Distance to Profile [{h3_res.get('h3_verdict', 'N/A')}]")

    # Panel 4: Box — MAE distributions for 3 ISF sources
    ax = axes[1, 1]
    if h4_res.get("per_patient") and len(h4_res["per_patient"]) > 0:
        mae_indep = [r["mae_independent"] for r in h4_res["per_patient"]]
        mae_all = [r["mae_all_events"] for r in h4_res["per_patient"]]
        mae_prof = [r["mae_profile"] for r in h4_res["per_patient"]]
        bp = ax.boxplot(
            [mae_indep, mae_all, mae_prof],
            tick_labels=["Independent\nISF", "All-event\nISF", "Profile\nISF"],
            patch_artist=True,
        )
        colors_bp = ["#F44336", "#1976D2", "#FF9800"]
        for patch, color in zip(bp["boxes"], colors_bp):
            patch.set_facecolor(color)
            patch.set_alpha(0.6)
        # Annotate medians
        for i, (med_val, label) in enumerate(zip(
            [np.median(mae_indep), np.median(mae_all), np.median(mae_prof)],
            ["Independent", "All", "Profile"],
        )):
            ax.text(i + 1, med_val + 2, f"{med_val:.0f}", ha="center", fontsize=9)
    ax.set_ylabel("MAE (mg/dL)")
    ax.set_title(f"H4: Prediction MAE [{h4_res.get('h4_verdict', 'N/A')}]")

    plt.tight_layout()
    out_path = VIZ_DIR / "independent_settings.png"
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Visualization: {out_path}")


# ── Main ──

def main():
    print("=" * 60)
    print(f"  {EXP_ID}: {EXP_TITLE}")
    print("=" * 60)

    grid = load_data()
    ev_all = extract_events(grid)
    if len(ev_all) < 100:
        print("ERROR: Too few events extracted")
        sys.exit(1)

    # Apply independence filter
    print("\nFiltering for temporal independence...")
    ev_all = filter_independent(ev_all)
    ev_indep = ev_all[ev_all["independent"]].copy()
    n_all = len(ev_all)
    n_indep = len(ev_indep)
    print(f"  All events:         {n_all:,}")
    print(f"  Independent events: {n_indep:,} ({100*n_indep/n_all:.1f}%)")
    print(f"  Patients (all):     {ev_all['patient_id'].nunique()}")
    print(f"  Patients (indep):   {ev_indep['patient_id'].nunique()}")

    # Run hypothesis tests
    h1_res = test_h1_isf_differs(ev_all, ev_indep)
    h2_res = test_h2_lower_cv(ev_all, ev_indep)
    h3_res = test_h3_closer_to_profile(ev_all, ev_indep)
    h4_res = test_h4_prediction_accuracy(ev_all, ev_indep)

    # Visualization
    print("\nGenerating visualization...")
    make_visualization(h1_res, h2_res, h3_res, h4_res)

    # Assemble results
    results = {
        "experiment_id": EXP_ID,
        "title": EXP_TITLE,
        "n_all_events": n_all,
        "n_independent_events": n_indep,
        "retention_pct": round(100 * n_indep / max(n_all, 1), 1),
        "n_patients_all": int(ev_all["patient_id"].nunique()),
        "n_patients_independent": int(ev_indep["patient_id"].nunique()),
        "min_gap_steps": MIN_GAP_STEPS,
        "min_gap_hours": MIN_GAP_STEPS / 12,
        "hypotheses": {
            "H1_isf_differs": h1_res,
            "H2_lower_cv": h2_res,
            "H3_closer_to_profile": h3_res,
            "H4_prediction_accuracy": h4_res,
        },
        "verdict_summary": {
            "H1": h1_res.get("h1_verdict", "SKIP"),
            "H2": h2_res.get("h2_verdict", "SKIP"),
            "H3": h3_res.get("h3_verdict", "SKIP"),
            "H4": h4_res.get("h4_verdict", "SKIP"),
        },
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults: {OUT_JSON}")

    v = results["verdict_summary"]
    print(f"\nVerdict: H1={v['H1']} H2={v['H2']} H3={v['H3']} H4={v['H4']}")
    return results


if __name__ == "__main__":
    main()
