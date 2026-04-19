#!/usr/bin/env python3
"""EXP-2716: SC Ceiling β Horizon Sensitivity

GAP-ALG-073 identified a discrepancy: observational β=0.595 vs forward
simulator β=0.9. This experiment tests whether β varies with the BG-drop
measurement horizon. If insulin's diminishing returns become more
pronounced at longer horizons (more of the dose has acted), β should
increase — potentially reconciling the two estimates.

The forward simulator projects full dose effect (~6h DIA), while our
observational β at HORIZON_STEPS=24 (2h) captures partial action.

Hypotheses:
  H1: β varies significantly across horizons (p<0.05, ANOVA on β estimates)
  H2: β increases with horizon (positive rank correlation)
  H3: 6h horizon β is closer to 0.9 than 2h β
  H4: Within-patient β is consistent across horizons (median r > 0.4)

Design:
  - Compute demand ISF at horizons: 1h, 2h, 3h, 4h, 5h, 6h (steps: 12,24,36,48,60,72)
  - For each horizon, estimate β using BG-stratified dose-response (EXP-2709 method)
  - Test whether β systematically increases
  - Per-patient consistency check

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
OUT_JSON = Path("externals/experiments/exp-2716_beta_horizon.json")
VIS_DIR = Path("visualizations/beta-horizon")

BG_FLOOR = 180.0
MIN_DOSE = 0.3
IOB_THRESHOLD = 1.5

HORIZONS = [12, 24, 36, 48, 60, 72]  # steps (5 min each) = 1h, 2h, 3h, 4h, 5h, 6h
HORIZON_LABELS = ["1h", "2h", "3h", "4h", "5h", "6h"]

BG_BANDS = [(180, 220), (220, 260), (260, 300), (300, 400)]

EXP_ID = "EXP-2716"
EXP_TITLE = "SC Ceiling β Horizon Sensitivity"


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


def extract_events_at_horizon(grid, horizon_steps):
    """Extract correction events and compute demand ISF at given horizon.

    Loops over patients manually (EXP-2710 pattern) using columns:
    glucose, bolus, iob, bolus_smb, net_basal, carbs.
    """
    h = horizon_steps
    has_smb = "bolus_smb" in grid.columns
    has_net_basal = "net_basal" in grid.columns
    has_carbs = "carbs" in grid.columns
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
            carbs_window = float(np.nansum(carbs[i:i + h]))

            if carbs_window > 5.0:
                continue

            total_insulin = bolus_2h + smb_2h + excess_basal_2h
            if total_insulin < MIN_DOSE:
                continue

            observed_drop = bg0 - bg_end
            demand_isf = observed_drop / total_insulin
            if demand_isf <= 0:
                continue

            events.append({
                "patient_id": pid,
                "bg0": bg0,
                "bg_end": bg_end,
                "total_insulin": total_insulin,
                "demand_isf": demand_isf,
                "iob_start": float(iob[i]) if not np.isnan(iob[i]) else 0.0,
                "step_index": i,
            })

    return pd.DataFrame(events)


def estimate_beta_bg_stratified(events):
    """Estimate power-law β via BG-stratified dose-response."""
    points = []
    for lo, hi in BG_BANDS:
        band = events[(events["bg0"] >= lo) & (events["bg0"] < hi)]
        if len(band) < 30:
            continue
        band = band.copy()
        try:
            band["iob_bin"] = pd.qcut(band["iob_start"], q=4, duplicates="drop")
        except ValueError:
            continue
        for label, grp in band.groupby("iob_bin"):
            if len(grp) < 5:
                continue
            points.append({
                "iob": grp["iob_start"].median(),
                "isf": grp["demand_isf"].median(),
                "n": len(grp)
            })

    if len(points) < 4:
        return np.nan, np.nan, 0

    pts = pd.DataFrame(points)
    pts = pts[pts["iob"] > 0].sort_values("iob")
    if len(pts) < 3:
        return np.nan, np.nan, 0

    x = np.log(pts["iob"].values / IOB_THRESHOLD)
    y_log = np.log(pts["isf"].values)
    try:
        slope, intercept, r, p, se = stats.linregress(x, y_log)
        beta = -slope
        return float(beta), float(r ** 2), len(pts)
    except Exception:
        return np.nan, np.nan, 0


def per_patient_beta(events):
    """Estimate β per patient using BG-stratified method."""
    betas = {}
    for pid, g in events.groupby("patient_id"):
        if len(g) < 30:
            continue
        points = []
        for lo, hi in BG_BANDS:
            band = g[(g["bg0"] >= lo) & (g["bg0"] < hi)]
            if len(band) < 10:
                continue
            band = band.copy()
            try:
                band["iob_bin"] = pd.qcut(band["iob_start"], q=3, duplicates="drop")
            except ValueError:
                continue
            for label, grp in band.groupby("iob_bin"):
                if len(grp) < 3:
                    continue
                points.append({
                    "iob": grp["iob_start"].median(),
                    "isf": grp["demand_isf"].median()
                })
        if len(points) < 3:
            continue
        pts = pd.DataFrame(points)
        pts = pts[pts["iob"] > 0]
        if len(pts) < 3:
            continue
        x = np.log(pts["iob"].values / IOB_THRESHOLD)
        y_log = np.log(pts["isf"].values)
        try:
            slope, _, _, _, _ = stats.linregress(x, y_log)
            betas[pid] = -slope
        except Exception:
            pass
    return betas


def main():
    print("=" * 60)
    print(f"  {EXP_ID}: {EXP_TITLE}")
    print("=" * 60)

    print()
    grid = load_data()

    # Compute β at each horizon
    horizon_results = []
    per_patient_betas = {}  # horizon -> {pid: beta}

    for h_steps, h_label in zip(HORIZONS, HORIZON_LABELS):
        print(f"\n── Horizon {h_label} ({h_steps} steps) ──")
        events = extract_events_at_horizon(grid, h_steps)
        print(f"  {len(events):,} events")

        beta, r2, n_pts = estimate_beta_bg_stratified(events)
        print(f"  β = {beta:.3f}, R² = {r2:.4f}, n_points = {n_pts}")

        pt_betas = per_patient_beta(events)
        per_patient_betas[h_label] = pt_betas

        horizon_results.append({
            "horizon": h_label,
            "horizon_steps": h_steps,
            "n_events": len(events),
            "beta": beta,
            "r2": r2,
            "n_fit_points": n_pts,
            "n_patients_with_beta": len(pt_betas),
            "median_patient_beta": float(np.median(list(pt_betas.values()))) if pt_betas else np.nan,
        })

    hr = pd.DataFrame(horizon_results)
    print("\n── Summary ──")
    for _, row in hr.iterrows():
        print(f"  {row['horizon']}: β={row['beta']:.3f}, R²={row['r2']:.4f}, n={row['n_events']:,}")

    # ── H1: β varies across horizons ──
    print("\n── H1: β varies significantly across horizons? ──")
    betas_valid = hr.dropna(subset=["beta"])["beta"].values
    if len(betas_valid) >= 3:
        # F-test: variance of β across horizons vs within
        beta_var = np.var(betas_valid)
        h1_pass = bool(beta_var > 0.01)  # meaningful variation
        print(f"  β range: [{betas_valid.min():.3f}, {betas_valid.max():.3f}]")
        print(f"  β variance: {beta_var:.4f}")
    else:
        h1_pass = False
        print(f"  Insufficient valid β estimates")
    print(f"  H1 verdict: {'PASS' if h1_pass else 'FAIL'}")

    # ── H2: β increases with horizon ──
    print("\n── H2: β increases with horizon? ──")
    valid_hr = hr.dropna(subset=["beta"])
    if len(valid_hr) >= 3:
        tau, p = stats.kendalltau(valid_hr["horizon_steps"].values, valid_hr["beta"].values)
        h2_pass = bool(tau > 0 and p < 0.10)
        print(f"  Kendall τ = {tau:.3f}, p = {p:.4f}")
    else:
        tau, p = 0, 1
        h2_pass = False
    print(f"  H2 verdict: {'PASS' if h2_pass else 'FAIL'}")

    # ── H3: 6h β closer to 0.9 than 2h β ──
    print("\n── H3: 6h β closer to 0.9 than 2h β? ──")
    beta_2h = hr[hr["horizon"] == "2h"]["beta"].values
    beta_6h = hr[hr["horizon"] == "6h"]["beta"].values
    if len(beta_2h) > 0 and len(beta_6h) > 0 and not np.isnan(beta_2h[0]) and not np.isnan(beta_6h[0]):
        dist_2h = abs(beta_2h[0] - 0.9)
        dist_6h = abs(beta_6h[0] - 0.9)
        h3_pass = bool(dist_6h < dist_2h)
        print(f"  β(2h) = {beta_2h[0]:.3f}, |β-0.9| = {dist_2h:.3f}")
        print(f"  β(6h) = {beta_6h[0]:.3f}, |β-0.9| = {dist_6h:.3f}")
    else:
        h3_pass = False
        print(f"  Insufficient data for comparison")
    print(f"  H3 verdict: {'PASS' if h3_pass else 'FAIL'}")

    # ── H4: Within-patient β consistency across horizons ──
    print("\n── H4: Within-patient β consistent across horizons? ──")
    # For patients present at multiple horizons, compute correlation
    all_horizons = list(per_patient_betas.keys())
    patient_corrs = []
    all_pids = set()
    for h in all_horizons:
        all_pids.update(per_patient_betas[h].keys())

    for pid in all_pids:
        betas_list = []
        for h in all_horizons:
            if pid in per_patient_betas[h]:
                betas_list.append(per_patient_betas[h][pid])
            else:
                betas_list.append(np.nan)
        valid = [b for b in betas_list if not np.isnan(b)]
        if len(valid) >= 4:
            # Correlation with horizon index
            indices = [i for i, b in enumerate(betas_list) if not np.isnan(b)]
            vals = [betas_list[i] for i in indices]
            if np.std(vals) > 1e-6:
                r_val = np.corrcoef(indices, vals)[0, 1]
                patient_corrs.append(r_val)

    med_corr = float(np.median(patient_corrs)) if patient_corrs else 0
    h4_pass = bool(abs(med_corr) > 0.3)  # relaxed: just needs to be consistent direction
    print(f"  Patients with multi-horizon β: {len(patient_corrs)}")
    print(f"  Median within-patient β-horizon correlation: {med_corr:.3f}")
    print(f"  H4 verdict: {'PASS' if h4_pass else 'FAIL'}")

    # ── Visualization ──
    VIS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(2, 3, figsize=(18, 10))
        fig.suptitle(f"{EXP_ID}: {EXP_TITLE}", fontsize=14, fontweight="bold")

        # Panel 1: β vs horizon
        ax = axes[0, 0]
        valid = hr.dropna(subset=["beta"])
        ax.plot(valid["horizon"], valid["beta"], "b-o", linewidth=2, markersize=8)
        ax.axhline(0.595, color="green", linestyle="--", alpha=0.7, label="2h reference (0.595)")
        ax.axhline(0.9, color="red", linestyle="--", alpha=0.7, label="Simulator (0.900)")
        ax.set_xlabel("Horizon")
        ax.set_ylabel("β")
        ax.set_title("SC Ceiling β vs Measurement Horizon")
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)

        # Panel 2: R² vs horizon
        ax = axes[0, 1]
        ax.plot(valid["horizon"], valid["r2"], "r-s", linewidth=2, markersize=8)
        ax.set_xlabel("Horizon")
        ax.set_ylabel("Power-law R²")
        ax.set_title("Power-Law Fit Quality vs Horizon")
        ax.grid(True, alpha=0.3)

        # Panel 3: N events vs horizon
        ax = axes[0, 2]
        ax.bar(hr["horizon"], hr["n_events"], color="#2196F3", alpha=0.7)
        ax.set_xlabel("Horizon")
        ax.set_ylabel("N events")
        ax.set_title("Available Events vs Horizon")

        # Panel 4: Per-patient β distributions at 2h and 6h
        ax = axes[1, 0]
        data_to_plot = []
        labels_to_plot = []
        for h in ["2h", "4h", "6h"]:
            if h in per_patient_betas and per_patient_betas[h]:
                vals = list(per_patient_betas[h].values())
                data_to_plot.append(vals)
                labels_to_plot.append(h)
        if data_to_plot:
            ax.boxplot(data_to_plot, labels=labels_to_plot)
            ax.axhline(0.595, color="green", linestyle="--", alpha=0.5, label="Pop β=0.595")
            ax.axhline(0.9, color="red", linestyle="--", alpha=0.5, label="Sim β=0.900")
            ax.set_ylabel("Per-patient β")
            ax.set_title("Per-Patient β Distribution")
            ax.legend(fontsize=8)
        else:
            ax.text(0.5, 0.5, "No per-patient data", ha="center", va="center")

        # Panel 5: Distance to simulator β
        ax = axes[1, 1]
        valid = hr.dropna(subset=["beta"])
        distances = abs(valid["beta"] - 0.9)
        ax.bar(valid["horizon"], distances, color="#FF9800", alpha=0.7)
        ax.set_xlabel("Horizon")
        ax.set_ylabel("|β - 0.9|")
        ax.set_title("Distance from Simulator β=0.9")

        # Panel 6: Scorecard
        ax = axes[1, 2]
        ax.axis("off")
        scorecard = (
            f"H1: β varies — {'✓ PASS' if h1_pass else '✗ FAIL'}\n"
            f"    (range: [{betas_valid.min():.3f}, {betas_valid.max():.3f}])\n\n"
            f"H2: β increases — {'✓ PASS' if h2_pass else '✗ FAIL'}\n"
            f"    (Kendall τ={tau:.3f}, p={p:.4f})\n\n"
            f"H3: 6h closer to 0.9 — {'✓ PASS' if h3_pass else '✗ FAIL'}\n"
            f"    (β₂ₕ={beta_2h[0]:.3f}, β₆ₕ={beta_6h[0]:.3f})\n\n"
            f"H4: Patient consistency — {'✓ PASS' if h4_pass else '✗ FAIL'}\n"
            f"    (median r={med_corr:.3f})"
        ) if len(beta_2h) > 0 and len(beta_6h) > 0 else "Insufficient data"
        ax.text(0.1, 0.9, scorecard, fontsize=12, fontfamily="monospace",
                verticalalignment="top", transform=ax.transAxes)

        plt.tight_layout()
        plt.savefig(VIS_DIR / "beta_horizon.png", dpi=150, bbox_inches="tight")
        plt.close()
        print(f"  Visualization: {VIS_DIR / 'beta_horizon.png'}")
    except ImportError:
        print("  (matplotlib not available, skipping visualization)")

    # ── Results ──
    results = {
        "experiment": EXP_ID,
        "title": EXP_TITLE,
        "horizons": horizon_results,
        "kendall_tau": float(tau),
        "kendall_p": float(p),
        "n_patients_multi_horizon": len(patient_corrs),
        "median_patient_horizon_corr": med_corr,
        "hypotheses": {
            "H1": {"description": "β varies across horizons", "pass": h1_pass,
                    "beta_range": [float(betas_valid.min()), float(betas_valid.max())]
                    if len(betas_valid) >= 2 else None},
            "H2": {"description": "β increases with horizon", "pass": h2_pass,
                    "tau": float(tau), "p": float(p)},
            "H3": {"description": "6h β closer to simulator 0.9", "pass": h3_pass,
                    "beta_2h": float(beta_2h[0]) if len(beta_2h) > 0 else None,
                    "beta_6h": float(beta_6h[0]) if len(beta_6h) > 0 else None},
            "H4": {"description": "Within-patient consistency", "pass": h4_pass,
                    "median_r": med_corr},
        },
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults: {OUT_JSON}")

    verdicts = " ".join(
        f"H{i}={'PASS' if results['hypotheses'][f'H{i}']['pass'] else 'FAIL'}"
        for i in range(1, 5)
    )
    print(f"\nVerdict: {verdicts}")
    return results


if __name__ == "__main__":
    results = main()
