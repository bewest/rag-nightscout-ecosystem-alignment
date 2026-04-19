#!/usr/bin/env python3
"""EXP-2712: SC Ceiling Impact on Settings

Quantifies how the SC ceiling (power-law β=0.595 from EXP-2709) affects
ISF recommendations at different IOB levels.

Produces IOB-conditional ISF tables: what ISF should the controller use
at different IOB levels? Compares to forward_simulator's β=0.9.

Hypotheses:
  H1: IOB-conditional ISF tables differ significantly from flat ISF
  H2: Power-law adjusted predictions reduce BG error
  H3: β=0.595 fits better than β=0.9 (forward_simulator value)
  H4: IOB-conditional ISF is per-patient heterogeneous

Author: Copilot + bewest
Date: 2026-04-19
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from scipy.optimize import curve_fit

GRID = Path("externals/ns-parquet/training/grid.parquet")
DS = Path("externals/ns-parquet/training/devicestatus.parquet")
MANIFEST = Path("externals/experiments/autoprepare-qualified.json")
OUT_JSON = Path("externals/experiments/exp-2712_sc_ceiling_settings.json")
VIS_DIR = Path("visualizations/sc-ceiling-settings")

BG_FLOOR = 180.0
HORIZON_STEPS = 24
MIN_DOSE = 0.3
IOB_THRESHOLD = 1.5  # from forward_simulator
POPULATION_BETA = 0.595  # from EXP-2709
SIMULATOR_BETA = 0.9     # from forward_simulator

EXP_ID = "EXP-2712"
EXP_TITLE = "SC Ceiling Impact on Settings"


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


def extract_events(grid):
    """Extract events with IOB for SC ceiling analysis."""
    print("Extracting events...")
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
        ctrl = pg["controller"].iloc[0] if "controller" in pg.columns else "unknown"
        if "scheduled_isf" not in pg.columns:
            continue
        profile_isf = float(np.nanmedian(pg["scheduled_isf"].values))

        for i in range(1, len(pg) - h):
            bg0 = glucose[i]
            bg_end = glucose[i + h]
            if np.isnan(bg0) or np.isnan(bg_end) or np.isnan(iob[i]) or bg0 < BG_FLOOR:
                continue
            bolus_2h = float(np.nansum(bolus[i:i + h]))
            smb_2h = float(np.nansum(smb[i:i + h]))
            excess_basal_2h = float(np.nansum(net_basal[i:i + h])) / 12.0
            carbs_2h = float(np.nansum(carbs[i:i + h]))
            total_insulin = bolus_2h + smb_2h + excess_basal_2h
            if carbs_2h > 5.0 or total_insulin < MIN_DOSE:
                continue
            observed_drop = bg0 - bg_end
            demand_isf = observed_drop / total_insulin
            if demand_isf <= 0:
                continue
            events.append({
                "patient_id": pid, "bg0": bg0, "bg_end": bg_end,
                "observed_drop": observed_drop, "total_insulin": total_insulin,
                "demand_isf": demand_isf, "iob_start": float(iob[i]),
                "controller": ctrl, "profile_isf": profile_isf,
            })

    df = pd.DataFrame(events)
    print(f"  {len(df):,} events, {df['patient_id'].nunique()} patients")
    return df


def build_iob_conditional_tables(events):
    """Build per-patient IOB-conditional ISF tables."""
    print("\nBuilding IOB-conditional ISF tables...")
    iob_bins = [(0, 1), (1, 2), (2, 3), (3, 5), (5, 8), (8, 15)]
    iob_labels = ["0-1", "1-2", "2-3", "3-5", "5-8", "8-15"]

    tables = []
    for pid, pg in events.groupby("patient_id"):
        if len(pg) < 30:
            continue

        ctrl = pg["controller"].iloc[0]
        profile_isf = pg["profile_isf"].iloc[0]
        flat_isf = float(pg["demand_isf"].median())

        # Within-BG-band analysis to control for BG confound
        bg_bands = [(180, 220), (220, 260), (260, 300), (300, 400)]
        bg_controlled_isfs = {}
        for lo_iob, hi_iob in iob_bins:
            iob_mask = (pg["iob_start"] >= lo_iob) & (pg["iob_start"] < hi_iob)
            if iob_mask.sum() < 10:
                bg_controlled_isfs[f"{lo_iob}-{hi_iob}"] = None
                continue
            # Average ISF across BG bands for this IOB bin
            band_isfs = []
            for bg_lo, bg_hi in bg_bands:
                mask = iob_mask & (pg["bg0"] >= bg_lo) & (pg["bg0"] < bg_hi)
                if mask.sum() >= 5:
                    band_isfs.append(float(pg.loc[mask, "demand_isf"].median()))
            bg_controlled_isfs[f"{lo_iob}-{hi_iob}"] = round(float(np.mean(band_isfs)), 1) if band_isfs else None

        # Fit power law per patient
        valid_points = [(lo + (hi - lo) / 2, bg_controlled_isfs[f"{lo}-{hi}"])
                        for (lo, hi), _ in zip(iob_bins, iob_labels)
                        if bg_controlled_isfs.get(f"{lo}-{hi}") is not None]

        patient_beta = None
        patient_isf0 = None
        if len(valid_points) >= 3:
            try:
                x_pts = np.array([p[0] for p in valid_points])
                y_pts = np.array([p[1] for p in valid_points])
                def power_law(iob, isf0, beta):
                    return isf0 * np.maximum(iob / IOB_THRESHOLD, 0.01) ** (-beta)
                popt, _ = curve_fit(power_law, x_pts, y_pts, p0=[flat_isf, 0.5],
                                    maxfev=5000, bounds=([0, 0], [200, 5]))
                patient_isf0 = round(float(popt[0]), 1)
                patient_beta = round(float(popt[1]), 3)
            except Exception:
                pass

        row = {
            "patient_id": pid, "controller": ctrl,
            "profile_isf": round(profile_isf, 1),
            "flat_demand_isf": round(flat_isf, 1),
            "patient_beta": patient_beta,
            "patient_isf0": patient_isf0,
            "n": int(len(pg)),
        }
        for label in iob_labels:
            row[f"isf_iob_{label}"] = bg_controlled_isfs.get(label.replace("-", "-"), None)

        tables.append(row)

    return tables


def test_h1_iob_table_differs(tables):
    """H1: IOB-conditional ISF differs from flat."""
    print("\n── H1: IOB-conditional differs from flat? ──")
    max_diffs = []
    for t in tables:
        flat = t["flat_demand_isf"]
        vals = [t.get(f"isf_iob_{l}", None) for l in ["0-1", "1-2", "2-3", "3-5", "5-8", "8-15"]]
        valid = [v for v in vals if v is not None]
        if valid:
            max_diff = max(abs(v - flat) for v in valid)
            max_diffs.append(max_diff)

    if not max_diffs:
        return {"h1_verdict": "SKIP"}

    median_diff = float(np.median(max_diffs))
    n_over_5 = sum(1 for d in max_diffs if d > 5)
    pct = 100 * n_over_5 / len(max_diffs)
    verdict = bool(pct > 50)

    print(f"  Median max IOB ISF diff from flat: {median_diff:.1f}")
    print(f"  Patients with diff > 5: {n_over_5}/{len(max_diffs)} ({pct:.0f}%)")
    print(f"  H1 verdict: {'PASS' if verdict else 'FAIL'}")

    return {
        "h1_verdict": "PASS" if verdict else "FAIL",
        "median_max_diff": round(median_diff, 1),
        "pct_over_5": round(pct, 1),
    }


def test_h2_prediction_improvement(events, tables):
    """H2: Power-law adjusted predictions reduce BG error."""
    print("\n── H2: Power-law improves predictions? ──")
    table_lookup = {t["patient_id"]: t for t in tables}
    per_patient = []

    for pid, pg in events.groupby("patient_id"):
        if pid not in table_lookup:
            continue
        t = table_lookup[pid]
        actual = pg["observed_drop"].values
        dose = pg["total_insulin"].values
        iob = pg["iob_start"].values

        # Flat prediction
        pred_flat = dose * t["flat_demand_isf"]
        mae_flat = float(np.mean(np.abs(actual - pred_flat)))

        # Power-law prediction (β=0.595 from population)
        effective_isf = np.where(
            iob > IOB_THRESHOLD,
            t["flat_demand_isf"] * (iob / IOB_THRESHOLD) ** (-POPULATION_BETA),
            t["flat_demand_isf"]
        )
        pred_pow = dose * effective_isf
        mae_pow = float(np.mean(np.abs(actual - pred_pow)))

        # Patient-specific β if available
        if t["patient_beta"] is not None and t["patient_isf0"] is not None:
            eff_isf_pt = np.where(
                iob > IOB_THRESHOLD,
                t["patient_isf0"] * (iob / IOB_THRESHOLD) ** (-t["patient_beta"]),
                t["patient_isf0"]
            )
            pred_pt = dose * eff_isf_pt
            mae_pt = float(np.mean(np.abs(actual - pred_pt)))
        else:
            mae_pt = mae_pow

        per_patient.append({
            "patient_id": pid,
            "mae_flat": round(mae_flat, 1),
            "mae_power_pop": round(mae_pow, 1),
            "mae_power_patient": round(mae_pt, 1),
            "improvement_pop": round(100 * (mae_flat - mae_pow) / max(mae_flat, 0.1), 1),
            "improvement_pt": round(100 * (mae_flat - mae_pt) / max(mae_flat, 0.1), 1),
        })

    med_flat = float(np.median([p["mae_flat"] for p in per_patient]))
    med_pow = float(np.median([p["mae_power_pop"] for p in per_patient]))
    med_pt = float(np.median([p["mae_power_patient"] for p in per_patient]))
    n_improved = sum(1 for p in per_patient if p["mae_power_pop"] < p["mae_flat"])
    pct = 100 * n_improved / max(len(per_patient), 1)

    verdict = bool(med_pow < med_flat and pct > 50)
    print(f"  Median MAE flat:        {med_flat:.1f}")
    print(f"  Median MAE power(pop):  {med_pow:.1f}")
    print(f"  Median MAE power(pt):   {med_pt:.1f}")
    print(f"  Improved (pop β): {n_improved}/{len(per_patient)} ({pct:.0f}%)")
    print(f"  H2 verdict: {'PASS' if verdict else 'FAIL'}")

    return {
        "h2_verdict": "PASS" if verdict else "FAIL",
        "median_mae_flat": round(med_flat, 1),
        "median_mae_power_pop": round(med_pow, 1),
        "median_mae_power_patient": round(med_pt, 1),
        "pct_improved": round(pct, 1),
        "per_patient": per_patient,
    }


def test_h3_beta_comparison(events):
    """H3: Population β=0.595 fits better than simulator β=0.9."""
    print("\n── H3: β=0.595 vs β=0.9? ──")

    # Population-level: bin by IOB, compare predicted ISF at each bin
    valid = events[events["iob_start"] > 0.1].copy()
    try:
        valid["iob_bin"] = pd.qcut(valid["iob_start"], 10, duplicates="drop")
    except ValueError:
        valid["iob_bin"] = pd.cut(valid["iob_start"], 10)

    bins = valid.groupby("iob_bin", observed=True).agg(
        iob_mid=("iob_start", "median"),
        isf_obs=("demand_isf", "median"),
        n=("demand_isf", "count"),
    ).dropna().reset_index()

    if len(bins) < 5:
        return {"h3_verdict": "SKIP"}

    x = bins["iob_mid"].values
    y_obs = bins["isf_obs"].values

    # Fit with both betas
    isf0_guess = float(y_obs[0])

    def power_law(iob, isf0, beta):
        return isf0 * np.maximum(iob / IOB_THRESHOLD, 0.01) ** (-beta)

    # Free beta
    try:
        popt_free, _ = curve_fit(power_law, x, y_obs, p0=[isf0_guess, 0.5],
                                 bounds=([0, 0], [200, 5]))
        y_free = power_law(x, *popt_free)
        sse_free = float(np.sum((y_obs - y_free) ** 2))
    except Exception:
        popt_free = [0, 0]
        sse_free = np.inf

    # Fixed β=0.9
    try:
        popt_09, _ = curve_fit(lambda iob, isf0: power_law(iob, isf0, 0.9), x, y_obs,
                               p0=[isf0_guess], bounds=([0], [200]))
        y_09 = power_law(x, popt_09[0], 0.9)
        sse_09 = float(np.sum((y_obs - y_09) ** 2))
    except Exception:
        sse_09 = np.inf

    # Fixed β=0.595
    try:
        popt_06, _ = curve_fit(lambda iob, isf0: power_law(iob, isf0, 0.595), x, y_obs,
                               p0=[isf0_guess], bounds=([0], [200]))
        y_06 = power_law(x, popt_06[0], 0.595)
        sse_06 = float(np.sum((y_obs - y_06) ** 2))
    except Exception:
        sse_06 = np.inf

    ss_tot = float(np.sum((y_obs - y_obs.mean()) ** 2))
    r2_free = 1 - sse_free / max(ss_tot, 1e-10)
    r2_09 = 1 - sse_09 / max(ss_tot, 1e-10)
    r2_06 = 1 - sse_06 / max(ss_tot, 1e-10)

    our_better = sse_06 < sse_09
    verdict = bool(our_better)

    print(f"  R² free (β={popt_free[1]:.3f}): {r2_free:.4f}")
    print(f"  R² β=0.595:             {r2_06:.4f}")
    print(f"  R² β=0.900:             {r2_09:.4f}")
    print(f"  β=0.595 better: {our_better}")
    print(f"  H3 verdict: {'PASS' if verdict else 'FAIL'}")

    return {
        "h3_verdict": "PASS" if verdict else "FAIL",
        "r2_free": round(float(r2_free), 4),
        "free_beta": round(float(popt_free[1]), 3),
        "r2_beta_06": round(float(r2_06), 4),
        "r2_beta_09": round(float(r2_09), 4),
        "our_beta_better": our_better,
    }


def test_h4_heterogeneity(tables):
    """H4: Per-patient β is heterogeneous."""
    print("\n── H4: Per-patient β heterogeneity? ──")
    betas = [t["patient_beta"] for t in tables if t["patient_beta"] is not None]
    if len(betas) < 5:
        return {"h4_verdict": "SKIP"}

    med = float(np.median(betas))
    iqr = float(np.percentile(betas, 75) - np.percentile(betas, 25))
    cv = float(np.std(betas) / max(np.mean(betas), 0.01))
    n_under_06 = sum(1 for b in betas if b < 0.6)
    n_over_09 = sum(1 for b in betas if b > 0.9)

    verdict = bool(cv > 0.3 or iqr > 0.3)
    print(f"  N patients with β: {len(betas)}")
    print(f"  Median β: {med:.3f}")
    print(f"  IQR: {iqr:.3f}")
    print(f"  CV: {cv:.3f}")
    print(f"  β<0.6: {n_under_06}, β>0.9: {n_over_09}")
    print(f"  H4 verdict: {'PASS' if verdict else 'FAIL'}")

    return {
        "h4_verdict": "PASS" if verdict else "FAIL",
        "n_patients": len(betas),
        "median_beta": round(med, 3),
        "iqr": round(iqr, 3),
        "cv": round(cv, 3),
    }


def make_visualization(events, tables, h1, h2, h3, h4):
    VIS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle(f"{EXP_ID}: {EXP_TITLE}", fontsize=14, fontweight="bold")

    # Panel 1: IOB-conditional ISF for example patients
    ax = axes[0, 0]
    iob_mids = [0.5, 1.5, 2.5, 4.0, 6.5, 11.5]
    for t in tables[:5]:
        vals = [t.get(f"isf_iob_{l}", None) for l in ["0-1", "1-2", "2-3", "3-5", "5-8", "8-15"]]
        valid_x = [iob_mids[i] for i, v in enumerate(vals) if v is not None]
        valid_y = [v for v in vals if v is not None]
        if valid_y:
            ax.plot(valid_x, valid_y, "o-", alpha=0.5, markersize=4, label=t["patient_id"][:8])
    ax.set_xlabel("IOB (U)")
    ax.set_ylabel("ISF (mg/dL/U)")
    ax.legend(fontsize=6, ncol=2)
    ax.set_title(f"H1: IOB-Conditional ISF [{h1['h1_verdict']}]")

    # Panel 2: MAE comparison
    ax = axes[0, 1]
    if h2.get("per_patient"):
        models = ["Flat ISF", "Power(pop β)", "Power(pt β)"]
        vals = [h2["median_mae_flat"], h2["median_mae_power_pop"], h2["median_mae_power_patient"]]
        ax.bar(models, vals, color=["gray", "coral", "green"], alpha=0.8)
        for i, v in enumerate(vals):
            ax.text(i, v + 0.5, f"{v:.0f}", ha="center", fontsize=10)
        ax.set_ylabel("Median MAE (mg/dL)")
    ax.set_title(f"H2: Prediction Improvement [{h2['h2_verdict']}]")

    # Panel 3: β comparison
    ax = axes[1, 0]
    if h3.get("h3_verdict") != "SKIP":
        labels = [f"Free\nβ={h3.get('free_beta', 0):.2f}", "β=0.595\n(ours)", "β=0.900\n(simulator)"]
        r2s = [h3.get("r2_free", 0), h3.get("r2_beta_06", 0), h3.get("r2_beta_09", 0)]
        colors = ["steelblue", "coral", "gray"]
        ax.bar(labels, r2s, color=colors, alpha=0.8)
        ax.set_ylabel("R²")
    ax.set_title(f"H3: β Comparison [{h3['h3_verdict']}]")

    # Panel 4: Per-patient β distribution
    ax = axes[1, 1]
    betas = [t["patient_beta"] for t in tables if t["patient_beta"] is not None]
    if betas:
        ax.hist(betas, bins=12, color="steelblue", alpha=0.8, edgecolor="black")
        ax.axvline(0.595, color="coral", linestyle="--", linewidth=2, label="Pop β=0.595")
        ax.axvline(0.9, color="gray", linestyle="--", linewidth=2, label="Sim β=0.900")
        ax.set_xlabel("Per-patient β")
        ax.set_ylabel("Count")
        ax.legend(fontsize=8)
    ax.set_title(f"H4: β Heterogeneity [{h4['h4_verdict']}]")

    plt.tight_layout()
    plt.savefig(VIS_DIR / "sc_ceiling_settings.png", dpi=150)
    plt.close()
    print(f"  Visualization: {VIS_DIR / 'sc_ceiling_settings.png'}")


def main():
    print(f"\n{'='*60}")
    print(f"  {EXP_ID}: {EXP_TITLE}")
    print(f"{'='*60}\n")

    grid = load_data()
    events = extract_events(grid)
    tables = build_iob_conditional_tables(events)

    h1 = test_h1_iob_table_differs(tables)
    h2 = test_h2_prediction_improvement(events, tables)
    h3 = test_h3_beta_comparison(events)
    h4 = test_h4_heterogeneity(tables)

    make_visualization(events, tables, h1, h2, h3, h4)

    results = {
        "experiment_id": EXP_ID, "title": EXP_TITLE,
        "n_events": int(len(events)), "n_patients": int(events["patient_id"].nunique()),
        "iob_tables": tables,
        "hypotheses": {
            "H1_iob_differs": h1, "H2_prediction": h2,
            "H3_beta_comparison": h3, "H4_heterogeneity": h4,
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
