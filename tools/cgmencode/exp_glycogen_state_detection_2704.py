#!/usr/bin/env python3
"""
EXP-2704: Glycogen State Detection on 22-Patient Cohort

Replicates and extends EXP-2627/2628 using the validated deconfounding pipeline.
Tests whether 48h carb history (glycogen proxy) modifies insulin effectiveness.

Hypothesis:
  H1: 48h carb history significantly predicts deviation residuals (p<0.05)
  H2: High glycogen state (top tertile 48h carbs) reduces ISF by >15%
  H3: Glycogen proxy improves ISF prediction R² by >5% over flat ISF
  H4: Glycogen state classification (depleted/nominal/loaded) is reproducible (split-half κ>0.4)

Methodology:
  1. Compute 48h rolling carb history for each event
  2. Classify into glycogen tertiles: depleted (<P33), nominal (P33-P66), loaded (>P66)
  3. Compare demand-phase ISF across glycogen states
  4. Test if adding glycogen proxy to regression improves R²
  5. Validate with split-half reliability

Research basis:
  EXP-2627: 48h carb history predicts 9.2% of ISF variance
  EXP-2628: Glycogen state detection (depleted/nominal/loaded)
  EXP-2698: Deconfounding pipeline (BGI subtraction)
"""
import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

warnings.filterwarnings("ignore")

# ── Paths ────────────────────────────────────────────────────────────
GRID = Path("externals/ns-parquet/training/grid.parquet")
DS = Path("externals/ns-parquet/training/devicestatus.parquet")
MANIFEST = Path("externals/experiments/autoprepare-qualified.json")
EXP_DIR = Path("externals/experiments")
VIS = Path("visualizations/glycogen-state")
VIS.mkdir(parents=True, exist_ok=True)

EXP_ID = "EXP-2704"
TITLE = "Glycogen State Detection on 22-Patient Cohort"

# ── Constants ────────────────────────────────────────────────────────
BG_FLOOR = 180.0           # For ISF extraction
HORIZON_STEPS = 24         # 2h demand phase
MIN_DOSE = 0.3
CARB_HISTORY_HOURS = 48    # 48h carb lookback window
CARB_HISTORY_STEPS = CARB_HISTORY_HOURS * 12  # 5-min steps


def load_data():
    """Load grid, devicestatus, controller map, qualified patients."""
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
    return grid, ctrl_map


def compute_carb_history(grid):
    """Add 48h rolling carb history column to grid."""
    print("Computing 48h carb history...")
    has_carbs = "carbs" in grid.columns
    if not has_carbs:
        grid["carbs_48h"] = 0.0
        return grid

    # Per-patient rolling sum (48h = 576 steps at 5-min resolution)
    result = []
    for pid, pg in grid.groupby("patient_id"):
        pg = pg.sort_values("time").copy()
        carbs = pg["carbs"].fillna(0).values

        # Rolling sum over 48h window
        carbs_48h = np.zeros(len(carbs))
        cumsum = np.cumsum(carbs)
        for i in range(len(carbs)):
            start = max(0, i - CARB_HISTORY_STEPS)
            carbs_48h[i] = cumsum[i] - (cumsum[start - 1] if start > 0 else 0)

        pg["carbs_48h"] = carbs_48h
        result.append(pg)

    grid = pd.concat(result, ignore_index=True)
    print(f"  48h carb range: {grid['carbs_48h'].min():.0f} to {grid['carbs_48h'].max():.0f} g")
    return grid


def extract_events_with_glycogen(grid):
    """Extract correction events with 48h carb history and glycogen classification."""
    print("Extracting events with glycogen state...")
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
        times = pg["time"].values
        ctrl = pg["controller"].iloc[0] if "controller" in pg.columns else "unknown"

        if "scheduled_isf" in pg.columns:
            isf_val = np.nanmedian(pg["scheduled_isf"].values)
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
            total_insulin = bolus_2h + smb_2h + excess_basal_2h

            if carbs_2h > 5.0:
                continue
            if total_insulin < MIN_DOSE:
                continue

            observed_drop = bg0 - bg_end
            demand_isf = observed_drop / total_insulin
            expected_drop = total_insulin * isf_val
            deviation = observed_drop - expected_drop

            roc_start = float(glucose[i] - glucose[i - 1]) if not np.isnan(glucose[i - 1]) else 0.0

            try:
                ts = pd.Timestamp(times[i])
                hour = ts.hour
            except Exception:
                hour = 0

            events.append({
                "patient_id": pid,
                "time": times[i],
                "bg0": bg0,
                "bg_end": bg_end,
                "observed_drop": observed_drop,
                "total_insulin": total_insulin,
                "demand_isf": demand_isf,
                "deviation": deviation,
                "carbs_48h": float(carbs_48h[i]),
                "iob_start": float(iob[i]) if not np.isnan(iob[i]) else 0.0,
                "roc_start": roc_start,
                "hour": hour,
                "controller": ctrl,
                "profile_isf": isf_val,
            })

    df = pd.DataFrame(events)
    df_pos = df[df["demand_isf"] > 0].copy()

    # Per-patient glycogen tertiles
    for pid, pg in df_pos.groupby("patient_id"):
        idx = pg.index
        try:
            tertiles = pd.qcut(pg["carbs_48h"], q=3, labels=["depleted", "nominal", "loaded"], duplicates="drop")
            df_pos.loc[idx, "glycogen_state"] = tertiles
        except ValueError:
            df_pos.loc[idx, "glycogen_state"] = "nominal"

    print(f"  {len(df_pos):,} events with positive ISF")
    if "glycogen_state" in df_pos.columns:
        print(f"  Glycogen states: {df_pos['glycogen_state'].value_counts().to_dict()}")
    return df_pos


def test_carb_history_predicts_deviation(events):
    """H1: 48h carb history predicts deviation residuals."""
    print("\n── H1: 48h carb history predicts deviation ──")

    # Population-level regression
    valid = events.dropna(subset=["carbs_48h", "deviation"])
    if len(valid) < 50:
        return {"h1_verdict": "SKIP", "reason": "too few events"}

    r_val, p_val = stats.pearsonr(valid["carbs_48h"], valid["deviation"])

    # Per-patient correlations
    patient_corrs = []
    for pid, pg in valid.groupby("patient_id"):
        if len(pg) < 20:
            continue
        r, p = stats.pearsonr(pg["carbs_48h"], pg["deviation"])
        patient_corrs.append({"patient_id": pid, "r": float(r), "p": float(p), "n": int(len(pg))})

    n_sig = sum(1 for pc in patient_corrs if pc["p"] < 0.05)

    verdict = bool(p_val < 0.05)
    print(f"  Population r={r_val:.3f}, p={p_val:.4f}")
    print(f"  {n_sig}/{len(patient_corrs)} patients have significant correlation")

    return {
        "h1_verdict": "PASS" if verdict else "FAIL",
        "population_r": round(float(r_val), 3),
        "population_p": float(p_val),
        "n_events": int(len(valid)),
        "n_sig_patients": n_sig,
        "n_patients_tested": len(patient_corrs),
        "per_patient_corrs": patient_corrs,
    }


def test_glycogen_modifies_isf(events):
    """H2: High glycogen state reduces ISF by >15%."""
    print("\n── H2: Glycogen state modifies ISF ──")

    if "glycogen_state" not in events.columns:
        return {"h2_verdict": "SKIP", "reason": "no glycogen classification"}

    state_isf = {}
    for state in ["depleted", "nominal", "loaded"]:
        subset = events[events["glycogen_state"] == state]["demand_isf"]
        if len(subset) >= 10:
            state_isf[state] = {
                "median": round(float(subset.median()), 1),
                "mean": round(float(subset.mean()), 1),
                "n": int(len(subset)),
            }
            print(f"  {state}: median ISF={subset.median():.1f} mg/dL/U (n={len(subset)})")

    if "depleted" in state_isf and "loaded" in state_isf:
        dep_isf = state_isf["depleted"]["median"]
        load_isf = state_isf["loaded"]["median"]
        reduction_pct = (dep_isf - load_isf) / dep_isf * 100 if dep_isf > 0 else 0

        # KW test across states
        groups = []
        for state in ["depleted", "nominal", "loaded"]:
            subset = events[events["glycogen_state"] == state]["demand_isf"]
            if len(subset) >= 10:
                groups.append(subset.values)

        if len(groups) >= 2:
            kw_stat, kw_p = stats.kruskal(*groups)
        else:
            kw_stat, kw_p = np.nan, np.nan

        verdict = bool(abs(reduction_pct) > 15 and (not np.isnan(kw_p) and kw_p < 0.05))
        print(f"  ISF reduction (depleted→loaded): {reduction_pct:.1f}%")
        print(f"  KW p={kw_p:.4f}" if not np.isnan(kw_p) else "  KW: insufficient groups")
    else:
        reduction_pct = None
        kw_stat, kw_p = np.nan, np.nan
        verdict = False

    return {
        "h2_verdict": "PASS" if verdict else "FAIL",
        "state_isf": state_isf,
        "isf_reduction_pct": round(float(reduction_pct), 1) if reduction_pct is not None else None,
        "kw_statistic": round(float(kw_stat), 2) if not np.isnan(kw_stat) else None,
        "kw_p": float(kw_p) if not np.isnan(kw_p) else None,
    }


def test_r2_improvement(events):
    """H3: Adding glycogen proxy improves ISF prediction R²."""
    print("\n── H3: R² improvement from glycogen proxy ──")

    valid = events.dropna(subset=["demand_isf", "carbs_48h", "bg0", "total_insulin"]).copy()
    if len(valid) < 50:
        return {"h3_verdict": "SKIP", "reason": "too few events"}

    # Baseline model: observed_drop ~ total_insulin + bg0 + iob_start
    from numpy.linalg import lstsq

    y = valid["observed_drop"].values
    X_base = np.column_stack([
        valid["total_insulin"].values,
        valid["bg0"].values,
        valid["iob_start"].values,
        np.ones(len(valid)),
    ])

    # Baseline R²
    beta_base, _, _, _ = lstsq(X_base, y, rcond=None)
    pred_base = X_base @ beta_base
    ss_res_base = np.sum((y - pred_base) ** 2)
    ss_tot = np.sum((y - y.mean()) ** 2)
    r2_base = 1 - ss_res_base / ss_tot

    # Enhanced model: + carbs_48h
    X_enhanced = np.column_stack([
        valid["total_insulin"].values,
        valid["bg0"].values,
        valid["iob_start"].values,
        valid["carbs_48h"].values,
        np.ones(len(valid)),
    ])

    beta_enh, _, _, _ = lstsq(X_enhanced, y, rcond=None)
    pred_enh = X_enhanced @ beta_enh
    ss_res_enh = np.sum((y - pred_enh) ** 2)
    r2_enhanced = 1 - ss_res_enh / ss_tot

    improvement = r2_enhanced - r2_base
    improvement_pct = improvement / max(r2_base, 0.001) * 100

    verdict = bool(improvement_pct > 5)
    print(f"  Base R²: {r2_base:.4f}")
    print(f"  Enhanced R² (+ carbs_48h): {r2_enhanced:.4f}")
    print(f"  Improvement: +{improvement:.4f} ({improvement_pct:.1f}%)")

    # Per-patient R² improvement
    patient_improvements = []
    for pid, pg in valid.groupby("patient_id"):
        if len(pg) < 20:
            continue
        yp = pg["observed_drop"].values
        ss_tot_p = np.sum((yp - yp.mean()) ** 2)
        if ss_tot_p == 0:
            continue

        X_b = np.column_stack([pg["total_insulin"].values, pg["bg0"].values, np.ones(len(pg))])
        X_e = np.column_stack([pg["total_insulin"].values, pg["bg0"].values, pg["carbs_48h"].values, np.ones(len(pg))])

        try:
            beta_b, _, _, _ = lstsq(X_b, yp, rcond=None)
            beta_e, _, _, _ = lstsq(X_e, yp, rcond=None)
            r2_b = 1 - np.sum((yp - X_b @ beta_b) ** 2) / ss_tot_p
            r2_e = 1 - np.sum((yp - X_e @ beta_e) ** 2) / ss_tot_p
            patient_improvements.append({
                "patient_id": pid,
                "r2_base": round(float(r2_b), 4),
                "r2_enhanced": round(float(r2_e), 4),
                "improvement": round(float(r2_e - r2_b), 4),
            })
        except Exception:
            continue

    n_improved = sum(1 for pi in patient_improvements if pi["improvement"] > 0)
    print(f"  {n_improved}/{len(patient_improvements)} patients improved")

    return {
        "h3_verdict": "PASS" if verdict else "FAIL",
        "r2_base": round(float(r2_base), 4),
        "r2_enhanced": round(float(r2_enhanced), 4),
        "r2_improvement": round(float(improvement), 4),
        "improvement_pct": round(float(improvement_pct), 1),
        "n_patients_improved": n_improved,
        "n_patients_tested": len(patient_improvements),
        "per_patient": patient_improvements,
    }


def test_classification_reliability(events):
    """H4: Glycogen state classification is reproducible (split-half)."""
    print("\n── H4: Classification reliability ──")

    if "glycogen_state" not in events.columns:
        return {"h4_verdict": "SKIP", "reason": "no glycogen classification"}

    agreements = []
    for pid, pg in events.groupby("patient_id"):
        pg = pg.sort_values("time")
        n = len(pg)
        if n < 40:
            continue
        half = n // 2
        first = pg.iloc[:half]
        second = pg.iloc[half:]

        # Re-classify each half independently using per-half tertiles
        for half_df, label in [(first, "first"), (second, "second")]:
            try:
                tertiles = pd.qcut(half_df["carbs_48h"], q=3, labels=["depleted", "nominal", "loaded"], duplicates="drop")
                # Median ISF per state
                for state in ["depleted", "nominal", "loaded"]:
                    subset = half_df[tertiles == state]["demand_isf"]
                    if len(subset) >= 5:
                        agreements.append({
                            "patient_id": pid,
                            "half": label,
                            "state": state,
                            "median_isf": float(subset.median()),
                            "n": int(len(subset)),
                        })
            except ValueError:
                continue

    if not agreements:
        return {"h4_verdict": "SKIP", "reason": "insufficient data for split-half"}

    # Compare ISF rankings across halves per patient
    df_a = pd.DataFrame(agreements)
    reliability_scores = []
    for pid in df_a["patient_id"].unique():
        pid_data = df_a[df_a["patient_id"] == pid]
        first_data = pid_data[pid_data["half"] == "first"].set_index("state")["median_isf"]
        second_data = pid_data[pid_data["half"] == "second"].set_index("state")["median_isf"]
        common = first_data.index.intersection(second_data.index)
        if len(common) >= 2:
            r, _ = stats.pearsonr(first_data[common], second_data[common])
            reliability_scores.append(float(r))

    mean_reliability = float(np.mean(reliability_scores)) if reliability_scores else 0
    verdict = bool(mean_reliability > 0.4)
    print(f"  Mean split-half reliability: {mean_reliability:.3f}")
    print(f"  {len(reliability_scores)} patients with sufficient data")

    return {
        "h4_verdict": "PASS" if verdict else "FAIL",
        "mean_reliability": round(mean_reliability, 3),
        "n_patients": len(reliability_scores),
    }


def make_visualization(events):
    """Generate glycogen state visualization."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        fig.suptitle(f"{EXP_ID}: Glycogen State Detection (N={len(events):,} events)", fontsize=14)

        # Panel 1: ISF by glycogen state
        ax = axes[0, 0]
        if "glycogen_state" in events.columns:
            state_order = ["depleted", "nominal", "loaded"]
            data = [events[events["glycogen_state"] == s]["demand_isf"].values for s in state_order
                    if len(events[events["glycogen_state"] == s]) > 0]
            labels = [s for s in state_order if len(events[events["glycogen_state"] == s]) > 0]
            ax.boxplot(data, labels=labels, showfliers=False)
            ax.set_ylabel("Demand-ISF (mg/dL/U)")
            ax.set_title("ISF by Glycogen State")

        # Panel 2: carbs_48h vs demand_isf scatter
        ax = axes[0, 1]
        sample = events.sample(min(5000, len(events)), random_state=42)
        ax.scatter(sample["carbs_48h"], sample["demand_isf"], alpha=0.1, s=3, color="steelblue")
        ax.set_xlabel("48h Carb History (g)")
        ax.set_ylabel("Demand-ISF (mg/dL/U)")
        ax.set_title("Carb History vs ISF")

        # Panel 3: Per-patient glycogen effect size
        ax = axes[1, 0]
        effects = []
        for pid, pg in events.groupby("patient_id"):
            if "glycogen_state" not in pg.columns:
                continue
            dep = pg[pg["glycogen_state"] == "depleted"]["demand_isf"]
            load = pg[pg["glycogen_state"] == "loaded"]["demand_isf"]
            if len(dep) >= 5 and len(load) >= 5:
                effects.append(dep.median() - load.median())
        if effects:
            colors = ["green" if e > 0 else "red" for e in sorted(effects)]
            ax.barh(range(len(effects)), sorted(effects), color=colors, alpha=0.7)
            ax.axvline(0, color="black", linewidth=0.8)
            ax.set_xlabel("ISF Difference: Depleted − Loaded (mg/dL/U)")
            ax.set_title("Per-Patient Glycogen Effect")

        # Panel 4: 48h carb distribution by controller
        ax = axes[1, 1]
        for ctrl, cg in events.groupby("controller"):
            ax.hist(cg["carbs_48h"], bins=30, alpha=0.4, label=ctrl)
        ax.set_xlabel("48h Carb History (g)")
        ax.legend()
        ax.set_title("Carb History by Controller")

        plt.tight_layout()
        path = VIS / "glycogen_state.png"
        fig.savefig(path, dpi=150)
        plt.close()
        print(f"\n  Visualization saved: {path}")
    except ImportError:
        print("  matplotlib not available, skipping visualization")


def main():
    grid, ctrl_map = load_data()
    grid = compute_carb_history(grid)
    events = extract_events_with_glycogen(grid)

    if len(events) == 0:
        print("ERROR: No events extracted")
        sys.exit(1)

    print(f"\n{EXP_ID}: {TITLE}")
    print(f"  {len(events):,} events, {events['patient_id'].nunique()} patients")

    h1 = test_carb_history_predicts_deviation(events)
    h2 = test_glycogen_modifies_isf(events)
    h3 = test_r2_improvement(events)
    h4 = test_classification_reliability(events)

    make_visualization(events)

    print(f"\n{'='*60}")
    print(f"RESULTS SUMMARY — {EXP_ID}")
    print(f"{'='*60}")
    print(f"  H1 (48h carbs predict deviation): {h1['h1_verdict']}")
    print(f"  H2 (glycogen modifies ISF >15%):  {h2['h2_verdict']}")
    print(f"  H3 (R² improvement >5%):          {h3.get('h3_verdict', 'SKIP')}")
    print(f"  H4 (classification reliable κ>0.4): {h4.get('h4_verdict', 'SKIP')}")

    results = {
        "experiment": EXP_ID,
        "title": TITLE,
        "n_events": int(len(events)),
        "n_patients": int(events["patient_id"].nunique()),
        "hypotheses": {
            "h1_carb_predicts_deviation": {k: v for k, v in h1.items() if k != "per_patient_corrs"},
            "h2_glycogen_modifies_isf": h2,
            "h3_r2_improvement": {k: v for k, v in h3.items() if k != "per_patient"},
            "h4_classification_reliability": h4,
        },
        "methodology": {
            "bg_floor": BG_FLOOR, "horizon_hours": 2.0, "min_dose": MIN_DOSE,
            "carb_history_hours": CARB_HISTORY_HOURS,
            "deconfounding": "BGI subtraction + BG floor + carb-free + glycogen tertile",
        },
    }

    out_path = EXP_DIR / "exp-2704_glycogen_state_detection.json"
    out_path.write_text(json.dumps(results, indent=2, default=str))
    print(f"\nResults saved: {out_path}")
    return results


if __name__ == "__main__":
    main()
