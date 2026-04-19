#!/usr/bin/env python3
"""EXP-2713: Residual Structure Analysis

After multi-factor deconfounding (EXP-2710 R²=0.224), 77.6% of ISF variance
remains unexplained. This experiment analyzes the residual to determine:
- Is it purely stochastic noise?
- Does it contain structured components (exercise, stress, sensor lag)?
- Are there temporal patterns (autocorrelation, seasonality)?

Understanding the residual tells us whether further deconfounding is possible
or whether we've reached the noise floor.

Hypotheses:
  H1: Residual is NOT pure noise (autocorrelation > 0 at lag 1-6 steps)
  H2: Residual has structure detectable by BG rate of change (sensor dynamics)
  H3: Consecutive events have correlated residuals (temporal clustering)
  H4: Residual magnitude differs by controller (systematic differences)

Author: Copilot + bewest
Date: 2026-04-19
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

GRID = Path("externals/ns-parquet/training/grid.parquet")
DS = Path("externals/ns-parquet/training/devicestatus.parquet")
MANIFEST = Path("externals/experiments/autoprepare-qualified.json")
OUT_JSON = Path("externals/experiments/exp-2713_residual_structure.json")
VIS_DIR = Path("visualizations/residual-structure")

BG_FLOOR = 180.0
HORIZON_STEPS = 24
MIN_DOSE = 0.3
CARB_HISTORY_STEPS = 48 * 12
BOLUS_COEFF = -129.2
SMB_COEFF = -123.6
EXCESS_BASAL_COEFF = -130.5
BLOCK_LABELS = ["00-04", "04-08", "08-12", "12-16", "16-20", "20-24"]

EXP_ID = "EXP-2713"
EXP_TITLE = "Residual Structure Analysis"


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

    # 48h carb history
    if "carbs" in grid.columns:
        result = []
        for pid, pg in grid.groupby("patient_id"):
            pg = pg.sort_values("time").copy()
            carbs_arr = pg["carbs"].fillna(0).values
            c48 = np.zeros(len(carbs_arr))
            cs = np.cumsum(carbs_arr)
            for i in range(len(carbs_arr)):
                start = max(0, i - CARB_HISTORY_STEPS)
                c48[i] = cs[i] - (cs[start - 1] if start > 0 else 0)
            pg["carbs_48h"] = c48
            result.append(pg)
        grid = pd.concat(result, ignore_index=True)
    else:
        grid["carbs_48h"] = 0.0

    print(f"  {len(grid):,} rows, {grid['patient_id'].nunique()} patients")
    return grid


def extract_events_with_residuals(grid):
    """Extract events and compute multi-factor residual."""
    from numpy.linalg import lstsq
    print("Extracting events and computing residuals...")
    h = HORIZON_STEPS
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
        carbs_48h = pg["carbs_48h"].values
        ctrl = pg["controller"].iloc[0] if "controller" in pg.columns else "unknown"
        if "scheduled_isf" not in pg.columns:
            continue
        profile_isf = float(np.nanmedian(pg["scheduled_isf"].values))
        times = pg["time"].values

        for i in range(1, len(pg) - h):
            bg0 = glucose[i]
            bg_end = glucose[i + h]
            if np.isnan(bg0) or np.isnan(bg_end) or bg0 < BG_FLOOR:
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

            # Rate of change
            roc = float(glucose[i] - glucose[i - 1]) if not np.isnan(glucose[i - 1]) else 0.0

            try:
                ts = pd.Timestamp(times[i])
                hour = ts.hour
            except Exception:
                hour = 0
            block_idx = min(hour // 4, 5)

            events.append({
                "patient_id": pid, "time": times[i],
                "bg0": bg0, "bg_end": bg_end,
                "observed_drop": observed_drop, "total_insulin": total_insulin,
                "demand_isf": demand_isf,
                "bolus_2h": bolus_2h, "smb_2h": smb_2h,
                "excess_basal_2h": excess_basal_2h,
                "iob_start": float(iob[i]) if not np.isnan(iob[i]) else 0.0,
                "roc_start": roc,
                "hour": hour, "block_idx": block_idx,
                "carbs_48h": float(carbs_48h[i]),
                "controller": ctrl, "profile_isf": profile_isf,
            })

    df = pd.DataFrame(events)

    # Compute multi-factor residual per patient
    residuals = []
    for pid, pg in df.groupby("patient_id"):
        if len(pg) < 30:
            continue
        y = pg["demand_isf"].values
        X = np.column_stack([
            pg["bg0"].values,
            pd.get_dummies(pg["block_idx"], prefix="b").values,
            pg["total_insulin"].values,
            pg["iob_start"].values,
            pg["bolus_2h"].values,
            pg["smb_2h"].values,
            pg["excess_basal_2h"].values,
            pg["carbs_48h"].values,
            np.ones(len(pg)),
        ])
        beta, _, _, _ = lstsq(X, y, rcond=None)
        pg = pg.copy()
        pg["predicted_isf"] = X @ beta
        pg["residual"] = y - pg["predicted_isf"]
        residuals.append(pg)

    result = pd.concat(residuals, ignore_index=True)
    print(f"  {len(result):,} events with residuals")
    return result


def test_h1_autocorrelation(events):
    """H1: Residual shows autocorrelation (not pure noise)."""
    print("\n── H1: Residual autocorrelation? ──")

    per_patient_ac = []
    for pid, pg in events.groupby("patient_id"):
        pg_sorted = pg.sort_values("time")
        resid = pg_sorted["residual"].values
        if len(resid) < 50:
            continue

        # Compute autocorrelation at lags 1-6
        mean_r = np.mean(resid)
        var_r = np.var(resid)
        if var_r < 1e-10:
            continue

        lags = {}
        for lag in range(1, 7):
            if len(resid) > lag:
                ac = np.mean((resid[lag:] - mean_r) * (resid[:-lag] - mean_r)) / var_r
                lags[lag] = round(float(ac), 3)

        per_patient_ac.append({
            "patient_id": pid,
            "ac_lag1": lags.get(1, 0),
            "ac_lag3": lags.get(3, 0),
            "ac_lag6": lags.get(6, 0),
        })

    if len(per_patient_ac) < 5:
        return {"h1_verdict": "SKIP"}

    median_lag1 = float(np.median([p["ac_lag1"] for p in per_patient_ac]))
    median_lag3 = float(np.median([p["ac_lag3"] for p in per_patient_ac]))
    n_positive = sum(1 for p in per_patient_ac if p["ac_lag1"] > 0.05)
    pct = 100 * n_positive / len(per_patient_ac)

    verdict = bool(median_lag1 > 0.05 and pct > 50)
    print(f"  Median AC lag 1: {median_lag1:.3f}")
    print(f"  Median AC lag 3: {median_lag3:.3f}")
    print(f"  Patients with AC>0.05: {n_positive}/{len(per_patient_ac)} ({pct:.0f}%)")
    print(f"  H1 verdict: {'PASS' if verdict else 'FAIL'}")

    return {
        "h1_verdict": "PASS" if verdict else "FAIL",
        "median_ac_lag1": round(median_lag1, 3),
        "median_ac_lag3": round(median_lag3, 3),
        "pct_positive": round(pct, 1),
        "per_patient": per_patient_ac,
    }


def test_h2_roc_structure(events):
    """H2: Rate of change predicts residual magnitude."""
    print("\n── H2: ROC → residual structure? ──")
    from numpy.linalg import lstsq

    # Does adding ROC to the model improve R²?
    y = events["residual"].values
    ss_tot = np.sum((y - y.mean()) ** 2)

    # Baseline: residual ~ 1 (should be ~0 since we already deconfounded)
    r2_baseline = 0.0

    # ROC model: residual ~ roc_start
    X_roc = np.column_stack([events["roc_start"].values, np.ones(len(events))])
    beta, _, _, _ = lstsq(X_roc, y, rcond=None)
    r2_roc = 1 - np.sum((y - X_roc @ beta) ** 2) / max(ss_tot, 1e-10)

    # ROC + abs(ROC) (sensor dynamics are often magnitude-dependent)
    X_roc2 = np.column_stack([events["roc_start"].values,
                               np.abs(events["roc_start"].values),
                               np.ones(len(events))])
    beta, _, _, _ = lstsq(X_roc2, y, rcond=None)
    r2_roc2 = 1 - np.sum((y - X_roc2 @ beta) ** 2) / max(ss_tot, 1e-10)

    # Correlation
    r_roc, p_roc = stats.pearsonr(events["roc_start"].values, y)

    # Per-patient ROC→residual correlation
    per_patient = []
    for pid, pg in events.groupby("patient_id"):
        if len(pg) < 30:
            continue
        r, p = stats.pearsonr(pg["roc_start"].values, pg["residual"].values)
        per_patient.append({"patient_id": pid, "r": round(float(r), 3), "p": float(p)})

    n_sig = sum(1 for p in per_patient if abs(p["r"]) > 0.1 and p["p"] < 0.05)
    pct_sig = 100 * n_sig / max(len(per_patient), 1)

    verdict = bool(r2_roc > 0.001 and pct_sig > 30)
    print(f"  R² ROC:          {r2_roc:.4f}")
    print(f"  R² ROC+|ROC|:    {r2_roc2:.4f}")
    print(f"  Correlation:     r={r_roc:.3f}, p={p_roc:.4f}")
    print(f"  Patients sig:    {n_sig}/{len(per_patient)} ({pct_sig:.0f}%)")
    print(f"  H2 verdict: {'PASS' if verdict else 'FAIL'}")

    return {
        "h2_verdict": "PASS" if verdict else "FAIL",
        "r2_roc": round(float(r2_roc), 4),
        "r2_roc_abs": round(float(r2_roc2), 4),
        "correlation_r": round(float(r_roc), 3),
        "pct_patients_significant": round(pct_sig, 1),
    }


def test_h3_temporal_clustering(events):
    """H3: Consecutive events have correlated residuals."""
    print("\n── H3: Temporal clustering? ──")

    per_patient = []
    for pid, pg in events.groupby("patient_id"):
        pg_sorted = pg.sort_values("time").reset_index(drop=True)
        if len(pg_sorted) < 30:
            continue

        resid = pg_sorted["residual"].values
        # Sign runs test: do + and - residuals cluster?
        signs = np.sign(resid)
        signs = signs[signs != 0]  # remove zeros
        if len(signs) < 20:
            continue

        # Count runs
        runs = 1
        for i in range(1, len(signs)):
            if signs[i] != signs[i - 1]:
                runs += 1

        n_pos = np.sum(signs > 0)
        n_neg = np.sum(signs < 0)
        n = n_pos + n_neg

        # Expected runs under randomness
        expected_runs = 1 + 2 * n_pos * n_neg / n
        var_runs = 2 * n_pos * n_neg * (2 * n_pos * n_neg - n) / (n ** 2 * (n - 1))
        if var_runs > 0:
            z = (runs - expected_runs) / np.sqrt(var_runs)
        else:
            z = 0

        per_patient.append({
            "patient_id": pid,
            "runs": int(runs),
            "expected_runs": round(float(expected_runs), 1),
            "z_score": round(float(z), 2),
            "is_clustered": bool(z < -1.96),  # fewer runs = more clustering
        })

    if len(per_patient) < 5:
        return {"h3_verdict": "SKIP"}

    n_clustered = sum(1 for p in per_patient if p["is_clustered"])
    pct = 100 * n_clustered / len(per_patient)
    median_z = float(np.median([p["z_score"] for p in per_patient]))

    verdict = bool(pct > 30 and median_z < -1)
    print(f"  Patients with clustering: {n_clustered}/{len(per_patient)} ({pct:.0f}%)")
    print(f"  Median runs z-score: {median_z:.2f}")
    print(f"  H3 verdict: {'PASS' if verdict else 'FAIL'}")

    return {
        "h3_verdict": "PASS" if verdict else "FAIL",
        "pct_clustered": round(pct, 1),
        "median_z": round(median_z, 2),
        "per_patient": per_patient,
    }


def test_h4_controller_differences(events):
    """H4: Residual magnitude differs by controller."""
    print("\n── H4: Controller differences in residual? ──")

    ctrl_stats = []
    for ctrl, cg in events.groupby("controller"):
        resid = cg["residual"].values
        ctrl_stats.append({
            "controller": ctrl,
            "n": int(len(cg)),
            "mean_resid": round(float(np.mean(resid)), 2),
            "median_abs_resid": round(float(np.median(np.abs(resid))), 2),
            "std_resid": round(float(np.std(resid)), 2),
        })
        print(f"  {ctrl}: n={len(cg):,}, mean={np.mean(resid):.2f}, MAR={np.median(np.abs(resid)):.2f}, std={np.std(resid):.2f}")

    # Kruskal-Wallis on absolute residuals
    groups = [cg["residual"].abs().values for _, cg in events.groupby("controller")]
    if len(groups) >= 2 and all(len(g) >= 10 for g in groups):
        stat, p = stats.kruskal(*groups)
        # Eta-squared
        n_total = sum(len(g) for g in groups)
        eta_sq = (stat - len(groups) + 1) / (n_total - len(groups))
    else:
        stat, p, eta_sq = 0, 1, 0

    verdict = bool(p < 0.05 and eta_sq > 0.01)
    print(f"  Kruskal-Wallis: H={stat:.1f}, p={p:.4f}")
    print(f"  η²: {eta_sq:.4f}")
    print(f"  H4 verdict: {'PASS' if verdict else 'FAIL'}")

    return {
        "h4_verdict": "PASS" if verdict else "FAIL",
        "kruskal_h": round(float(stat), 1),
        "kruskal_p": round(float(p), 4),
        "eta_squared": round(float(eta_sq), 4),
        "controller_stats": ctrl_stats,
    }


def make_visualization(events, h1, h2, h3, h4):
    VIS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle(f"{EXP_ID}: {EXP_TITLE}", fontsize=14, fontweight="bold")

    # Panel 1: Residual distribution
    ax = axes[0, 0]
    ax.hist(events["residual"].values, bins=50, color="steelblue", alpha=0.7, edgecolor="black", density=True)
    mu = events["residual"].mean()
    sigma = events["residual"].std()
    x_norm = np.linspace(mu - 3*sigma, mu + 3*sigma, 100)
    ax.plot(x_norm, stats.norm.pdf(x_norm, mu, sigma), 'r-', linewidth=2, label=f"Normal μ={mu:.1f}, σ={sigma:.1f}")
    ax.set_xlabel("Residual ISF (mg/dL/U)")
    ax.set_ylabel("Density")
    ax.legend(fontsize=8)
    ax.set_title(f"H1: Residual Distribution [{h1['h1_verdict']}]\nAC lag1={h1.get('median_ac_lag1', 0):.3f}", fontsize=10)

    # Panel 2: ROC vs residual
    ax = axes[0, 1]
    sample = events.sample(min(5000, len(events)), random_state=42)
    ax.scatter(sample["roc_start"], sample["residual"], s=2, alpha=0.2, color="steelblue")
    ax.axhline(0, color="gray", linestyle="--", alpha=0.5)
    ax.axvline(0, color="gray", linestyle="--", alpha=0.5)
    ax.set_xlabel("BG Rate of Change (mg/dL per 5min)")
    ax.set_ylabel("Residual ISF")
    r2 = h2.get("r2_roc", 0)
    ax.set_title(f"H2: ROC → Residual [{h2['h2_verdict']}]\nR²={r2:.4f}", fontsize=10)

    # Panel 3: Runs test z-scores
    ax = axes[1, 0]
    if h3.get("per_patient"):
        zs = [p["z_score"] for p in h3["per_patient"]]
        ax.hist(zs, bins=15, color="coral", alpha=0.8, edgecolor="black")
        ax.axvline(-1.96, color="red", linestyle="--", label="p<0.05 (clustered)")
        ax.set_xlabel("Runs test z-score")
        ax.set_ylabel("Patients")
        ax.legend(fontsize=8)
    ax.set_title(f"H3: Temporal Clustering [{h3['h3_verdict']}]", fontsize=10)

    # Panel 4: Controller comparison
    ax = axes[1, 1]
    if h4.get("controller_stats"):
        cstats = h4["controller_stats"]
        names = [c["controller"] for c in cstats]
        mars = [c["median_abs_resid"] for c in cstats]
        ax.bar(names, mars, color=["steelblue", "coral", "seagreen"][:len(names)], alpha=0.8)
        ax.set_ylabel("Median |Residual| (mg/dL/U)")
        for i, v in enumerate(mars):
            ax.text(i, v + 0.2, f"{v:.1f}", ha="center", fontsize=10)
    ax.set_title(f"H4: Controller Differences [{h4['h4_verdict']}]\nη²={h4.get('eta_squared', 0):.4f}", fontsize=10)

    plt.tight_layout()
    plt.savefig(VIS_DIR / "residual_structure.png", dpi=150)
    plt.close()
    print(f"  Visualization: {VIS_DIR / 'residual_structure.png'}")


def main():
    print(f"\n{'='*60}")
    print(f"  {EXP_ID}: {EXP_TITLE}")
    print(f"{'='*60}\n")

    grid = load_data()
    events = extract_events_with_residuals(grid)
    if len(events) < 100:
        print("ERROR: Too few events")
        sys.exit(1)

    h1 = test_h1_autocorrelation(events)
    h2 = test_h2_roc_structure(events)
    h3 = test_h3_temporal_clustering(events)
    h4 = test_h4_controller_differences(events)

    make_visualization(events, h1, h2, h3, h4)

    results = {
        "experiment_id": EXP_ID, "title": EXP_TITLE,
        "n_events": int(len(events)), "n_patients": int(events["patient_id"].nunique()),
        "hypotheses": {
            "H1_autocorrelation": h1, "H2_roc_structure": h2,
            "H3_temporal_clustering": h3, "H4_controller_differences": h4,
        },
        "verdict_summary": {"H1": h1["h1_verdict"], "H2": h2["h2_verdict"],
                            "H3": h3["h3_verdict"], "H4": h4["h4_verdict"]},
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(results, indent=2, default=str))
    print(f"\nResults: {OUT_JSON}")
    print(f"\nVerdict: H1={h1['h1_verdict']} H2={h2['h2_verdict']} H3={h3['h3_verdict']} H4={h4['h4_verdict']}")

if __name__ == "__main__":
    main()
