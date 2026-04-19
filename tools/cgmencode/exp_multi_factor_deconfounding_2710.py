#!/usr/bin/env python3
"""EXP-2710: Multi-Factor Deconfounding — Combined Signal Extraction

Combines all deconfounding techniques discovered in EXP-2698 through 2709:
1. BGI subtraction (EXP-2698): remove known insulin effect → deviation
2. BG0 residualization (EXP-2705): remove starting-BG confound
3. Circadian block adjustment (EXP-2702/2708): account for time-of-day
4. Channel decomposition (EXP-2698): separate bolus/SMB/basal contributions
5. Glycogen state (EXP-2704/2707): 48h carb history proxy

Tests whether COMBINING these techniques extracts more signal than any
individual technique, and whether the combined residual is more precise
(lower within-patient variance) and more accurate (better predicts actual BG).

Hypotheses:
  H1: Combined R² > best single-factor R² (complementary signals)
  H2: Stepwise addition — each factor adds incremental R²
  H3: Combined residual has lower within-patient CV (more precise)
  H4: Combined model reduces per-patient MAE for BG prediction

Design:
  - Extract correction events at BG≥180, carbs<5g, dose≥0.3U
  - Apply each deconfounding technique individually and in combination
  - Measure R² at each step (waterfall pattern)
  - Evaluate prediction accuracy: predict BG_end from BG0 + deconfounded ISF

Author: Copilot + bewest
Date: 2026-04-19
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
OUT_JSON = Path("externals/experiments/exp-2710_multi_factor_deconfounding.json")
VIS_DIR = Path("visualizations/multi-factor-deconfounding")

BG_FLOOR = 180.0
HORIZON_STEPS = 24
MIN_DOSE = 0.3
CARB_HISTORY_STEPS = 48 * 12  # 48 hours at 5-min intervals

# EXP-2698 validated coefficients
BOLUS_COEFF = -129.2
SMB_COEFF = -123.6
EXCESS_BASAL_COEFF = -130.5

TIME_BLOCKS = [(0, 4), (4, 8), (8, 12), (12, 16), (16, 20), (20, 24)]
BLOCK_LABELS = ["00-04", "04-08", "08-12", "12-16", "16-20", "20-24"]

EXP_ID = "EXP-2710"
EXP_TITLE = "Multi-Factor Deconfounding"


def load_data():
    print("Loading data...")
    grid = pd.read_parquet(GRID)
    ds = pd.read_parquet(DS)
    ctrl_map = ds.groupby("patient_id")["controller"].first().to_dict()
    grid["controller"] = grid["patient_id"].map(ctrl_map)
    manifest = json.loads(MANIFEST.read_text())
    qual = manifest["qualified_patients"]
    grid = grid[grid["patient_id"].isin(qual)].copy()
    if not pd.api.types.is_datetime64_any_dtype(grid["time"]):
        grid["time"] = pd.to_datetime(grid["time"], utc=True)
    grid = grid.sort_values(["patient_id", "time"]).reset_index(drop=True)
    print(f"  {len(grid):,} rows, {grid['patient_id'].nunique()} patients")
    return grid


def compute_48h_carbs(grid):
    """Add 48h rolling carb history."""
    if "carbs" not in grid.columns:
        grid["carbs_48h"] = 0.0
        return grid

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


def extract_events(grid):
    """Extract correction events with all features needed for multi-factor analysis."""
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

            # BGI subtraction: expected_drop = dose × profile_ISF
            expected_drop = total_insulin * profile_isf
            deviation = observed_drop - expected_drop

            # Channel decomposition
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

            # Glycogen state
            c48 = float(carbs_48h[i]) if not np.isnan(carbs_48h[i]) else 0.0

            events.append({
                "patient_id": pid,
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
    # Glycogen state classification (median split per patient)
    for pid in df["patient_id"].unique():
        mask = df["patient_id"] == pid
        med = df.loc[mask, "carbs_48h"].median()
        df.loc[mask, "glycogen_state"] = np.where(df.loc[mask, "carbs_48h"] >= med, "loaded", "depleted")

    print(f"  {len(df):,} events, {df['patient_id'].nunique()} patients")
    return df


def test_h1_combined_r2(events):
    """H1: Combined model R² exceeds best single-factor R²."""
    print("\n── H1: Combined vs single-factor R² ──")
    from numpy.linalg import lstsq

    y = events["demand_isf"].values
    ss_tot = np.sum((y - y.mean()) ** 2)

    def compute_r2(X):
        X_int = np.column_stack([X, np.ones(len(X))])
        beta, _, _, _ = lstsq(X_int, y, rcond=None)
        return 1 - np.sum((y - X_int @ beta) ** 2) / ss_tot

    # Single factors
    r2_bg = compute_r2(events[["bg0"]].values)
    r2_block = compute_r2(pd.get_dummies(events["block_idx"], prefix="b").values)
    r2_dose = compute_r2(events[["total_insulin"]].values)
    r2_iob = compute_r2(events[["iob_start"]].values)
    r2_glycogen = compute_r2(events[["carbs_48h"]].values)
    r2_patient = compute_r2(pd.get_dummies(events["patient_id"], prefix="p").values)

    # Channel decomposition (3 channels)
    r2_channels = compute_r2(events[["bolus_2h", "smb_2h", "excess_basal_2h"]].values)

    # Combined: BG0 + block + dose + IOB + glycogen
    X_combined = np.column_stack([
        events["bg0"].values,
        pd.get_dummies(events["block_idx"], prefix="b").values,
        events["total_insulin"].values,
        events["iob_start"].values,
        events["carbs_48h"].values,
    ])
    r2_combined = compute_r2(X_combined)

    # Combined + channels
    X_full = np.column_stack([
        events["bg0"].values,
        pd.get_dummies(events["block_idx"], prefix="b").values,
        events["bolus_2h"].values,
        events["smb_2h"].values,
        events["excess_basal_2h"].values,
        events["iob_start"].values,
        events["carbs_48h"].values,
    ])
    r2_full = compute_r2(X_full)

    # Full + patient dummies (upper bound)
    X_upper = np.column_stack([
        X_full,
        pd.get_dummies(events["patient_id"], prefix="p").values,
    ])
    r2_upper = compute_r2(X_upper)

    best_single = max(r2_bg, r2_block, r2_dose, r2_iob, r2_glycogen)
    combined_better = r2_combined > best_single

    print(f"  Single-factor R²:")
    print(f"    BG0:        {r2_bg:.4f}")
    print(f"    Block:      {r2_block:.4f}")
    print(f"    Dose:       {r2_dose:.4f}")
    print(f"    IOB:        {r2_iob:.4f}")
    print(f"    Glycogen:   {r2_glycogen:.4f}")
    print(f"    Channels:   {r2_channels:.4f}")
    print(f"    Patient:    {r2_patient:.4f}")
    print(f"  Combined R²:  {r2_combined:.4f}")
    print(f"  Full+channels: {r2_full:.4f}")
    print(f"  +Patient (UB): {r2_upper:.4f}")
    print(f"  Combined > best single: {combined_better}")
    print(f"  H1 verdict: {'PASS' if combined_better else 'FAIL'}")

    return {
        "h1_verdict": "PASS" if bool(combined_better) else "FAIL",
        "r2_bg": round(float(r2_bg), 4),
        "r2_block": round(float(r2_block), 4),
        "r2_dose": round(float(r2_dose), 4),
        "r2_iob": round(float(r2_iob), 4),
        "r2_glycogen": round(float(r2_glycogen), 4),
        "r2_channels": round(float(r2_channels), 4),
        "r2_patient": round(float(r2_patient), 4),
        "r2_combined": round(float(r2_combined), 4),
        "r2_full": round(float(r2_full), 4),
        "r2_upper_bound": round(float(r2_upper), 4),
        "best_single": round(float(best_single), 4),
    }


def test_h2_stepwise(events):
    """H2: Stepwise addition — each factor adds incremental R²."""
    print("\n── H2: Stepwise R² waterfall ──")
    from numpy.linalg import lstsq

    y = events["demand_isf"].values
    ss_tot = np.sum((y - y.mean()) ** 2)

    # Step-by-step addition in priority order
    steps = []
    X_running = np.ones((len(events), 1))  # intercept only

    factor_list = [
        ("patient_id", pd.get_dummies(events["patient_id"], prefix="p").values),
        ("BG0", events[["bg0"]].values),
        ("circadian_block", pd.get_dummies(events["block_idx"], prefix="b").values),
        ("dose", events[["total_insulin"]].values),
        ("IOB", events[["iob_start"]].values),
        ("channels", events[["bolus_2h", "smb_2h", "excess_basal_2h"]].values),
        ("glycogen", events[["carbs_48h"]].values),
    ]

    prev_r2 = 0.0
    for name, X_new in factor_list:
        X_running = np.column_stack([X_running, X_new])
        beta, _, _, _ = lstsq(X_running, y, rcond=None)
        r2 = 1 - np.sum((y - X_running @ beta) ** 2) / ss_tot
        delta = r2 - prev_r2

        steps.append({
            "factor": name,
            "cumulative_r2": round(float(r2), 4),
            "delta_r2": round(float(delta), 4),
            "n_columns": int(X_running.shape[1]),
        })
        print(f"  +{name:20s} → R²={r2:.4f} (Δ={delta:+.4f})")
        prev_r2 = r2

    # All factors add something?
    all_positive = all(s["delta_r2"] > 0 for s in steps)
    n_positive = sum(1 for s in steps if s["delta_r2"] > 0.0001)

    verdict = bool(n_positive >= 4)  # At least 4 of 7 factors contribute

    print(f"  Factors with Δ>0.0001: {n_positive}/{len(steps)}")
    print(f"  H2 verdict: {'PASS' if verdict else 'FAIL'}")

    return {
        "h2_verdict": "PASS" if verdict else "FAIL",
        "steps": steps,
        "n_positive_factors": n_positive,
        "all_positive": all_positive,
    }


def test_h3_precision(events):
    """H3: Combined residual has lower within-patient CV (more precise)."""
    print("\n── H3: Precision — within-patient CV ──")
    from numpy.linalg import lstsq

    # Raw ISF CV per patient
    raw_cvs = []
    for pid, pg in events.groupby("patient_id"):
        if len(pg) < 30:
            continue
        raw_cv = float(pg["demand_isf"].std() / max(pg["demand_isf"].mean(), 0.1))
        raw_cvs.append({"patient_id": pid, "raw_cv": round(raw_cv, 3)})

    # Adjusted ISF: residualize BG0 + block + dose + IOB + glycogen per patient
    adj_cvs = []
    for pid, pg in events.groupby("patient_id"):
        if len(pg) < 30:
            continue

        y = pg["demand_isf"].values
        X = np.column_stack([
            pg["bg0"].values,
            pd.get_dummies(pg["block_idx"], prefix="b").values,
            pg["total_insulin"].values,
            pg["iob_start"].values,
            pg["carbs_48h"].values,
            np.ones(len(pg)),
        ])
        beta, _, _, _ = lstsq(X, y, rcond=None)
        resid = y - X @ beta
        adj_cv = float(resid.std() / max(abs(y.mean()), 0.1))
        adj_cvs.append({"patient_id": pid, "adj_cv": round(adj_cv, 3)})

    if len(raw_cvs) < 5 or len(adj_cvs) < 5:
        return {"h3_verdict": "SKIP", "reason": "insufficient patients"}

    # Merge and compare
    raw_vals = [r["raw_cv"] for r in raw_cvs]
    adj_vals = [a["adj_cv"] for a in adj_cvs[:len(raw_cvs)]]

    med_raw = float(np.median(raw_vals))
    med_adj = float(np.median(adj_vals))
    reduction_pct = 100 * (med_raw - med_adj) / max(med_raw, 0.01)

    n_improved = sum(1 for r, a in zip(raw_vals, adj_vals) if a < r)
    pct_improved = 100 * n_improved / max(len(raw_vals), 1)

    try:
        stat, p = stats.wilcoxon(raw_vals, adj_vals, alternative="greater")
    except ValueError:
        p = 1.0

    verdict = bool(med_adj < med_raw and pct_improved > 50)

    print(f"  Median raw CV:      {med_raw:.3f}")
    print(f"  Median adjusted CV: {med_adj:.3f}")
    print(f"  CV reduction:       {reduction_pct:.1f}%")
    print(f"  Patients improved:  {n_improved}/{len(raw_vals)} ({pct_improved:.0f}%)")
    print(f"  Wilcoxon p:         {p:.4f}")
    print(f"  H3 verdict: {'PASS' if verdict else 'FAIL'}")

    return {
        "h3_verdict": "PASS" if verdict else "FAIL",
        "median_raw_cv": round(med_raw, 3),
        "median_adj_cv": round(med_adj, 3),
        "cv_reduction_pct": round(reduction_pct, 1),
        "pct_improved": round(pct_improved, 1),
        "wilcoxon_p": round(float(p), 4),
        "n_patients": len(raw_vals),
    }


def test_h4_bg_prediction(events):
    """H4: Combined model reduces MAE for BG_end prediction."""
    print("\n── H4: BG prediction accuracy ──")
    from numpy.linalg import lstsq

    per_patient_results = []
    for pid, pg in events.groupby("patient_id"):
        if len(pg) < 50:
            continue

        actual_bg_end = pg["bg_end"].values

        # Model 1: Naive (predict BG_end = BG0 - profile_ISF × dose)
        naive_pred = pg["bg0"].values - pg["profile_isf"].values * pg["total_insulin"].values
        mae_naive = float(np.mean(np.abs(actual_bg_end - naive_pred)))

        # Model 2: Flat demand ISF (BG_end = BG0 - median_demand_ISF × dose)
        flat_isf = float(pg["demand_isf"].median())
        flat_pred = pg["bg0"].values - flat_isf * pg["total_insulin"].values
        mae_flat = float(np.mean(np.abs(actual_bg_end - flat_pred)))

        # Model 3: Multi-factor (learn BG_end directly from all features)
        y = actual_bg_end
        X = np.column_stack([
            pg["bg0"].values,
            pd.get_dummies(pg["block_idx"], prefix="b").values,
            pg["total_insulin"].values,
            pg["iob_start"].values,
            pg["carbs_48h"].values,
            pg["bolus_2h"].values,
            pg["smb_2h"].values,
            pg["excess_basal_2h"].values,
            np.ones(len(pg)),
        ])

        # Leave-one-out is expensive; use 5-fold CV
        n = len(pg)
        fold_size = n // 5
        cv_errors = []
        indices = np.arange(n)
        np.random.seed(42)
        np.random.shuffle(indices)

        for fold in range(5):
            test_idx = indices[fold * fold_size:(fold + 1) * fold_size]
            train_idx = np.setdiff1d(indices, test_idx)
            if len(train_idx) < 20 or len(test_idx) < 5:
                continue
            X_train, X_test = X[train_idx], X[test_idx]
            y_train, y_test = y[train_idx], y[test_idx]
            try:
                beta, _, _, _ = lstsq(X_train, y_train, rcond=None)
                pred = X_test @ beta
                cv_errors.extend(np.abs(y_test - pred).tolist())
            except Exception:
                continue

        mae_multi = float(np.mean(cv_errors)) if cv_errors else mae_flat

        per_patient_results.append({
            "patient_id": pid,
            "controller": pg["controller"].iloc[0],
            "n": int(len(pg)),
            "mae_naive": round(mae_naive, 1),
            "mae_flat_isf": round(mae_flat, 1),
            "mae_multi_factor": round(mae_multi, 1),
            "improvement_vs_naive": round(100 * (mae_naive - mae_multi) / max(mae_naive, 0.1), 1),
            "improvement_vs_flat": round(100 * (mae_flat - mae_multi) / max(mae_flat, 0.1), 1),
        })

    if len(per_patient_results) < 5:
        return {"h4_verdict": "SKIP", "reason": "insufficient patients"}

    med_naive = float(np.median([p["mae_naive"] for p in per_patient_results]))
    med_flat = float(np.median([p["mae_flat_isf"] for p in per_patient_results]))
    med_multi = float(np.median([p["mae_multi_factor"] for p in per_patient_results]))

    n_improved_vs_flat = sum(1 for p in per_patient_results if p["mae_multi_factor"] < p["mae_flat_isf"])
    pct_improved = 100 * n_improved_vs_flat / len(per_patient_results)

    verdict = bool(med_multi < med_flat and pct_improved > 50)

    print(f"  Median MAE naive (profile ISF):    {med_naive:.1f} mg/dL")
    print(f"  Median MAE flat demand ISF:        {med_flat:.1f} mg/dL")
    print(f"  Median MAE multi-factor (5-fold):  {med_multi:.1f} mg/dL")
    print(f"  Improved vs flat: {n_improved_vs_flat}/{len(per_patient_results)} ({pct_improved:.0f}%)")
    print(f"  H4 verdict: {'PASS' if verdict else 'FAIL'}")

    return {
        "h4_verdict": "PASS" if verdict else "FAIL",
        "median_mae_naive": round(med_naive, 1),
        "median_mae_flat_isf": round(med_flat, 1),
        "median_mae_multi_factor": round(med_multi, 1),
        "pct_improved_vs_flat": round(pct_improved, 1),
        "per_patient": per_patient_results,
    }


def make_visualization(events, h1, h2, h3, h4):
    VIS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("  matplotlib not available, skipping visualization")
        return

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle(f"{EXP_ID}: {EXP_TITLE}", fontsize=14, fontweight="bold")

    # Panel 1: Single-factor R² comparison
    ax = axes[0, 0]
    factors = ["BG₀", "Block", "Dose", "IOB", "Glyc", "Chan", "Patient", "Combined", "Full", "Upper"]
    vals = [h1.get(k, 0) for k in ["r2_bg", "r2_block", "r2_dose", "r2_iob",
                                     "r2_glycogen", "r2_channels", "r2_patient",
                                     "r2_combined", "r2_full", "r2_upper_bound"]]
    colors = ["steelblue"] * 7 + ["coral", "darkorange", "gray"]
    ax.barh(factors, vals, color=colors, alpha=0.8)
    ax.set_xlabel("R²")
    ax.set_title(f"H1: Single vs Combined [{h1['h1_verdict']}]")

    # Panel 2: Stepwise waterfall
    ax = axes[0, 1]
    if h2.get("steps"):
        steps = h2["steps"]
        names = [s["factor"] for s in steps]
        deltas = [s["delta_r2"] for s in steps]
        cumulative = [s["cumulative_r2"] for s in steps]
        ax.bar(range(len(names)), deltas, color="coral", alpha=0.8)
        ax.plot(range(len(names)), cumulative, "ko-", markersize=5)
        ax.set_xticks(range(len(names)))
        ax.set_xticklabels(names, rotation=45, ha="right", fontsize=8)
        ax.set_ylabel("ΔR² / Cumulative R²")
    ax.set_title(f"H2: Stepwise Waterfall [{h2['h2_verdict']}]")

    # Panel 3: CV reduction
    ax = axes[1, 0]
    if h3.get("h3_verdict") != "SKIP":
        ax.bar(["Raw CV", "Adjusted CV"], [h3["median_raw_cv"], h3["median_adj_cv"]],
               color=["steelblue", "coral"], alpha=0.8)
        ax.set_ylabel("Median within-patient CV")
        pct = h3.get("cv_reduction_pct", 0)
        ax.text(1, h3["median_adj_cv"] + 0.01, f"-{pct:.0f}%", ha="center", fontsize=12)
    ax.set_title(f"H3: Precision [{h3['h3_verdict']}]")

    # Panel 4: BG prediction MAE
    ax = axes[1, 1]
    if h4.get("h4_verdict") != "SKIP":
        models = ["Profile\nISF", "Flat\nDemand ISF", "Multi-\nFactor"]
        maes = [h4["median_mae_naive"], h4["median_mae_flat_isf"], h4["median_mae_multi_factor"]]
        colors = ["gray", "steelblue", "coral"]
        ax.bar(models, maes, color=colors, alpha=0.8)
        ax.set_ylabel("Median MAE (mg/dL)")
        for i, v in enumerate(maes):
            ax.text(i, v + 0.5, f"{v:.0f}", ha="center", fontsize=10)
    ax.set_title(f"H4: BG Prediction [{h4['h4_verdict']}]")

    plt.tight_layout()
    out_path = VIS_DIR / "multi_factor_deconfounding.png"
    plt.savefig(out_path, dpi=150)
    plt.close()
    print(f"  Visualization: {out_path}")


def main():
    print(f"\n{'='*60}")
    print(f"  {EXP_ID}: {EXP_TITLE}")
    print(f"{'='*60}\n")

    grid = load_data()
    grid = compute_48h_carbs(grid)
    events = extract_events(grid)
    if len(events) < 100:
        print("ERROR: Too few events")
        sys.exit(1)

    h1 = test_h1_combined_r2(events)
    h2 = test_h2_stepwise(events)
    h3 = test_h3_precision(events)
    h4 = test_h4_bg_prediction(events)

    make_visualization(events, h1, h2, h3, h4)

    results = {
        "experiment_id": EXP_ID,
        "title": EXP_TITLE,
        "n_events": int(len(events)),
        "n_patients": int(events["patient_id"].nunique()),
        "hypotheses": {
            "H1_combined_r2": h1,
            "H2_stepwise_waterfall": h2,
            "H3_precision": h3,
            "H4_bg_prediction": h4,
        },
        "verdict_summary": {
            "H1": h1["h1_verdict"],
            "H2": h2["h2_verdict"],
            "H3": h3["h3_verdict"],
            "H4": h4["h4_verdict"],
        },
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(results, indent=2, default=str))
    print(f"\nResults: {OUT_JSON}")
    print(f"\nVerdict summary: H1={h1['h1_verdict']} H2={h2['h2_verdict']} H3={h3['h3_verdict']} H4={h4['h4_verdict']}")
    return results


if __name__ == "__main__":
    main()
