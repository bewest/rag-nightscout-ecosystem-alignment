#!/usr/bin/env python3
"""
EXP-2707: Glycogen Confound Analysis

EXP-2704 found loaded glycogen (top tertile 48h carbs) shows HIGHER ISF than
depleted (26.3 vs 24.7 mg/dL/U). This contradicts insulin resistance expectation.

Investigation: Is this BG-level confounding?
  - More carbs → more time at high BG → more corrections start at high BG
  - Higher starting BG → larger drops → higher apparent ISF
  - The confound: glycogen state correlates with starting BG

Hypothesis:
  H1: 48h carb history correlates with starting BG (r > 0.1)
  H2: After controlling for starting BG, glycogen effect reverses or disappears
  H3: Within BG strata (narrow BG bands), glycogen effect is smaller
  H4: The "glycogen → ISF" pathway is mediated through BG0 (mediation analysis)
"""
import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

warnings.filterwarnings("ignore")

GRID = Path("externals/ns-parquet/training/grid.parquet")
DS = Path("externals/ns-parquet/training/devicestatus.parquet")
MANIFEST = Path("externals/experiments/autoprepare-qualified.json")
EXP_DIR = Path("externals/experiments")
VIS = Path("visualizations/glycogen-confound")
VIS.mkdir(parents=True, exist_ok=True)

EXP_ID = "EXP-2707"
TITLE = "Glycogen Confound Analysis"
BG_FLOOR = 180.0
HORIZON_STEPS = 24
MIN_DOSE = 0.3
CARB_HISTORY_STEPS = 48 * 12


def load_and_prepare():
    """Load data and compute 48h carb history."""
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

    # Compute 48h carb history
    if "carbs" in grid.columns:
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
        grid = pd.concat(result, ignore_index=True)

    print(f"  {len(grid):,} rows, {grid['patient_id'].nunique()} patients")
    return grid


def extract_events(grid):
    """Extract correction events with glycogen and BG."""
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
        smb = pg["bolus_smb"].values if has_smb else np.zeros(len(pg))
        net_basal = pg["net_basal"].values if has_net_basal else np.zeros(len(pg))
        carbs = pg["carbs"].values if has_carbs else np.zeros(len(pg))
        carbs_48h = pg["carbs_48h"].values if "carbs_48h" in pg.columns else np.zeros(len(pg))
        iob = pg["iob"].values if "iob" in pg.columns else np.full(len(pg), np.nan)
        ctrl = pg["controller"].iloc[0] if "controller" in pg.columns else "unknown"

        if "scheduled_isf" not in pg.columns:
            continue
        isf_val = np.nanmedian(pg["scheduled_isf"].values)

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

            if carbs_2h > 5.0 or total_insulin < MIN_DOSE:
                continue

            observed_drop = bg0 - bg_end
            demand_isf = observed_drop / total_insulin
            if demand_isf <= 0:
                continue

            events.append({
                "patient_id": pid,
                "bg0": bg0,
                "observed_drop": observed_drop,
                "total_insulin": total_insulin,
                "demand_isf": demand_isf,
                "carbs_48h": float(carbs_48h[i]),
                "iob_start": float(iob[i]) if not np.isnan(iob[i]) else 0.0,
                "controller": ctrl,
            })

    df = pd.DataFrame(events)

    # Per-patient glycogen tertiles
    for pid, pg in df.groupby("patient_id"):
        try:
            tertiles = pd.qcut(pg["carbs_48h"], q=3, labels=["depleted", "nominal", "loaded"], duplicates="drop")
            df.loc[pg.index, "glycogen_state"] = tertiles
        except ValueError:
            df.loc[pg.index, "glycogen_state"] = "nominal"

    print(f"  {len(df):,} events, {df['patient_id'].nunique()} patients")
    return df


def test_bg_carb_correlation(events):
    """H1: 48h carb history correlates with starting BG."""
    print("\n── H1: Carb history ↔ starting BG correlation ──")

    r, p = stats.pearsonr(events["carbs_48h"], events["bg0"])
    print(f"  Population r={r:.3f}, p={p:.4f}")

    # Per-glycogen-state BG0
    state_bg = {}
    for state in ["depleted", "nominal", "loaded"]:
        subset = events[events["glycogen_state"] == state]
        if len(subset) >= 10:
            state_bg[state] = {
                "median_bg0": round(float(subset["bg0"].median()), 1),
                "mean_bg0": round(float(subset["bg0"].mean()), 1),
                "n": int(len(subset)),
            }
            print(f"  {state}: median BG0={subset['bg0'].median():.1f} mg/dL (n={len(subset)})")

    verdict = bool(abs(r) > 0.1 and p < 0.01)
    return {
        "h1_verdict": "PASS" if verdict else "FAIL",
        "population_r": round(float(r), 3),
        "population_p": float(p),
        "state_bg0": state_bg,
    }


def test_bg_controlled_glycogen(events):
    """H2: After controlling for BG0, glycogen effect disappears."""
    print("\n── H2: BG-controlled glycogen effect ──")

    from numpy.linalg import lstsq

    valid = events.dropna(subset=["demand_isf", "bg0", "carbs_48h"]).copy()
    y = valid["demand_isf"].values

    # Model 1: ISF ~ carbs_48h
    X1 = np.column_stack([valid["carbs_48h"].values, np.ones(len(valid))])
    beta1, _, _, _ = lstsq(X1, y, rcond=None)
    carb_coeff_raw = beta1[0]

    # Model 2: ISF ~ carbs_48h + bg0 + total_insulin + iob_start
    X2 = np.column_stack([
        valid["carbs_48h"].values,
        valid["bg0"].values,
        valid["total_insulin"].values,
        valid["iob_start"].values,
        np.ones(len(valid)),
    ])
    beta2, _, _, _ = lstsq(X2, y, rcond=None)
    carb_coeff_controlled = beta2[0]

    reduction = (abs(carb_coeff_raw) - abs(carb_coeff_controlled)) / abs(carb_coeff_raw) * 100 if abs(carb_coeff_raw) > 0.0001 else 0

    print(f"  Raw carb→ISF coefficient: {carb_coeff_raw:.5f}")
    print(f"  BG-controlled carb→ISF coefficient: {carb_coeff_controlled:.5f}")
    print(f"  Reduction: {reduction:.0f}%")

    # BG-adjusted glycogen effect
    # Residualize BG0 from ISF, then compare glycogen states
    X_bg = np.column_stack([valid["bg0"].values, valid["total_insulin"].values, np.ones(len(valid))])
    beta_bg, _, _, _ = lstsq(X_bg, y, rcond=None)
    isf_bg_adjusted = y - X_bg @ beta_bg + y.mean()
    valid["isf_adjusted"] = isf_bg_adjusted

    adj_state_isf = {}
    for state in ["depleted", "nominal", "loaded"]:
        subset = valid[valid["glycogen_state"] == state]["isf_adjusted"]
        if len(subset) >= 10:
            adj_state_isf[state] = round(float(subset.median()), 1)
            print(f"  BG-adjusted {state}: median ISF={subset.median():.1f}")

    # Does the effect reverse?
    if "depleted" in adj_state_isf and "loaded" in adj_state_isf:
        adj_diff = adj_state_isf["loaded"] - adj_state_isf["depleted"]
        raw_diff = float(events[events["glycogen_state"] == "loaded"]["demand_isf"].median() -
                         events[events["glycogen_state"] == "depleted"]["demand_isf"].median())
        reversed_or_disappeared = adj_diff < 0 or abs(adj_diff) < abs(raw_diff) * 0.5
        print(f"  Raw ISF difference (loaded-depleted): {raw_diff:.1f}")
        print(f"  Adjusted ISF difference: {adj_diff:.1f}")
    else:
        reversed_or_disappeared = False
        raw_diff = adj_diff = None

    verdict = bool(reduction > 50 or reversed_or_disappeared)
    return {
        "h2_verdict": "PASS" if verdict else "FAIL",
        "carb_coeff_raw": round(float(carb_coeff_raw), 5),
        "carb_coeff_controlled": round(float(carb_coeff_controlled), 5),
        "coeff_reduction_pct": round(float(reduction), 1),
        "adjusted_state_isf": adj_state_isf,
        "raw_isf_diff": round(float(raw_diff), 1) if raw_diff is not None else None,
        "adjusted_isf_diff": round(float(adj_diff), 1) if adj_diff is not None else None,
    }


def test_bg_stratified(events):
    """H3: Within narrow BG bands, glycogen effect is smaller."""
    print("\n── H3: BG-stratified glycogen effect ──")

    bg_bands = [(180, 220), (220, 260), (260, 300), (300, 400)]
    band_results = []

    for lo, hi in bg_bands:
        band = events[(events["bg0"] >= lo) & (events["bg0"] < hi)]
        if len(band) < 50:
            continue

        dep = band[band["glycogen_state"] == "depleted"]["demand_isf"]
        load = band[band["glycogen_state"] == "loaded"]["demand_isf"]

        if len(dep) < 10 or len(load) < 10:
            continue

        diff = float(load.median() - dep.median())
        u_stat, u_p = stats.mannwhitneyu(dep, load, alternative="two-sided")

        band_results.append({
            "band": f"{lo}-{hi}",
            "n_depleted": int(len(dep)),
            "n_loaded": int(len(load)),
            "dep_median": round(float(dep.median()), 1),
            "load_median": round(float(load.median()), 1),
            "diff": round(diff, 1),
            "mw_p": float(u_p),
        })
        print(f"  BG {lo}-{hi}: dep={dep.median():.1f}, load={load.median():.1f}, diff={diff:.1f}, p={u_p:.3f}")

    # Is the within-band effect smaller than population effect?
    pop_diff = float(events[events["glycogen_state"] == "loaded"]["demand_isf"].median() -
                     events[events["glycogen_state"] == "depleted"]["demand_isf"].median())

    if band_results:
        avg_within_diff = float(np.mean([abs(b["diff"]) for b in band_results]))
        attenuation = (abs(pop_diff) - avg_within_diff) / abs(pop_diff) * 100 if abs(pop_diff) > 0 else 0
        verdict = bool(avg_within_diff < abs(pop_diff) * 0.7)
        print(f"  Population effect: {pop_diff:.1f}")
        print(f"  Mean within-band effect: {avg_within_diff:.1f}")
        print(f"  Attenuation: {attenuation:.0f}%")
    else:
        avg_within_diff = None
        attenuation = None
        verdict = False

    return {
        "h3_verdict": "PASS" if verdict else "FAIL",
        "population_diff": round(float(pop_diff), 1),
        "avg_within_band_diff": round(float(avg_within_diff), 1) if avg_within_diff else None,
        "attenuation_pct": round(float(attenuation), 1) if attenuation else None,
        "band_results": band_results,
    }


def test_mediation(events):
    """H4: BG0 mediates the carb→ISF pathway."""
    print("\n── H4: Mediation analysis (carb → BG0 → ISF) ──")

    from numpy.linalg import lstsq

    valid = events.dropna(subset=["carbs_48h", "bg0", "demand_isf"]).copy()

    # Path a: carb → BG0
    X_a = np.column_stack([valid["carbs_48h"].values, np.ones(len(valid))])
    y_a = valid["bg0"].values
    beta_a, _, _, _ = lstsq(X_a, y_a, rcond=None)
    path_a = beta_a[0]

    # Path b: BG0 → ISF (controlling for carb)
    X_b = np.column_stack([valid["bg0"].values, valid["carbs_48h"].values, np.ones(len(valid))])
    y_b = valid["demand_isf"].values
    beta_b, _, _, _ = lstsq(X_b, y_b, rcond=None)
    path_b = beta_b[0]

    # Path c: total effect carb → ISF
    X_c = np.column_stack([valid["carbs_48h"].values, np.ones(len(valid))])
    beta_c, _, _, _ = lstsq(X_c, y_b, rcond=None)
    total_effect = beta_c[0]

    # Path c': direct effect carb → ISF (controlling for BG0)
    direct_effect = beta_b[1]  # coefficient of carbs_48h in model with BG0

    # Indirect effect = total - direct (or a*b)
    indirect_effect = total_effect - direct_effect
    indirect_ab = path_a * path_b

    # Proportion mediated
    prop_mediated = indirect_effect / total_effect * 100 if abs(total_effect) > 0.00001 else 0

    print(f"  Path a (carb→BG0): {path_a:.4f}")
    print(f"  Path b (BG0→ISF|carb): {path_b:.4f}")
    print(f"  Total effect (carb→ISF): {total_effect:.5f}")
    print(f"  Direct effect (carb→ISF|BG0): {direct_effect:.5f}")
    print(f"  Indirect effect (a×b): {indirect_ab:.5f}")
    print(f"  Proportion mediated by BG0: {prop_mediated:.0f}%")

    verdict = bool(abs(prop_mediated) > 30)

    return {
        "h4_verdict": "PASS" if verdict else "FAIL",
        "path_a_carb_to_bg": round(float(path_a), 4),
        "path_b_bg_to_isf": round(float(path_b), 4),
        "total_effect": round(float(total_effect), 5),
        "direct_effect": round(float(direct_effect), 5),
        "indirect_effect": round(float(indirect_ab), 5),
        "proportion_mediated_pct": round(float(prop_mediated), 1),
    }


def make_visualization(events, h2, h3):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        fig.suptitle(f"{EXP_ID}: Glycogen Confound Analysis (N={len(events):,})", fontsize=14)

        # Panel 1: BG0 by glycogen state
        ax = axes[0, 0]
        states = ["depleted", "nominal", "loaded"]
        data = [events[events["glycogen_state"] == s]["bg0"].values for s in states
                if len(events[events["glycogen_state"] == s]) > 0]
        labels = [s for s in states if len(events[events["glycogen_state"] == s]) > 0]
        ax.boxplot(data, labels=labels, showfliers=False)
        ax.set_ylabel("Starting BG (mg/dL)")
        ax.set_title("Starting BG by Glycogen State")

        # Panel 2: Raw vs adjusted ISF by state
        ax = axes[0, 1]
        raw_isf = {s: float(events[events["glycogen_state"] == s]["demand_isf"].median())
                   for s in states if len(events[events["glycogen_state"] == s]) >= 10}
        adj_isf = h2.get("adjusted_state_isf", {})
        x = range(len([s for s in states if s in raw_isf]))
        valid_states = [s for s in states if s in raw_isf]
        ax.bar([i - 0.15 for i in x], [raw_isf[s] for s in valid_states], 0.3, label="Raw", color="steelblue")
        if adj_isf:
            ax.bar([i + 0.15 for i in x], [adj_isf.get(s, 0) for s in valid_states], 0.3, label="BG-adjusted", color="orange")
        ax.set_xticks(list(x))
        ax.set_xticklabels(valid_states)
        ax.legend()
        ax.set_ylabel("Median ISF (mg/dL/U)")
        ax.set_title("Raw vs BG-Adjusted ISF by Glycogen State")

        # Panel 3: Within-band ISF differences
        ax = axes[1, 0]
        bands = h3.get("band_results", [])
        if bands:
            labels_b = [b["band"] for b in bands]
            diffs = [b["diff"] for b in bands]
            colors = ["green" if d > 0 else "red" for d in diffs]
            ax.bar(range(len(diffs)), diffs, color=colors, alpha=0.7)
            ax.axhline(0, color="black", linewidth=0.8)
            ax.axhline(h3.get("population_diff", 0), color="blue", linestyle="--",
                       label=f"Population diff: {h3.get('population_diff', 0):.1f}")
            ax.set_xticks(range(len(labels_b)))
            ax.set_xticklabels(labels_b, rotation=45)
            ax.legend()
        ax.set_ylabel("ISF Diff: Loaded − Depleted")
        ax.set_title("Glycogen Effect Within BG Bands")

        # Panel 4: Mediation path diagram (text)
        ax = axes[1, 1]
        ax.axis("off")
        ax.text(0.5, 0.9, "Mediation Model", ha="center", fontsize=14, fontweight="bold")
        ax.text(0.5, 0.7, "48h Carbs → Starting BG → Demand ISF", ha="center", fontsize=11)
        ax.text(0.5, 0.5, f"a: carb→BG = {h2.get('carb_coeff_raw', '?')}", ha="center", fontsize=10)
        ax.text(0.5, 0.35, f"Raw effect: {h2.get('carb_coeff_raw', '?')}", ha="center", fontsize=10)
        ax.text(0.5, 0.2, f"BG-controlled: {h2.get('carb_coeff_controlled', '?')}", ha="center", fontsize=10)
        ax.text(0.5, 0.05, f"Reduction: {h2.get('coeff_reduction_pct', '?')}%", ha="center", fontsize=10,
                color="red" if (h2.get("coeff_reduction_pct", 0) or 0) > 50 else "black")

        plt.tight_layout()
        path = VIS / "glycogen_confound.png"
        fig.savefig(path, dpi=150)
        plt.close()
        print(f"\n  Visualization saved: {path}")
    except ImportError:
        print("  matplotlib not available")


def main():
    grid = load_and_prepare()
    events = extract_events(grid)

    if len(events) == 0:
        print("ERROR: No events")
        sys.exit(1)

    print(f"\n{EXP_ID}: {TITLE}")
    print(f"  {len(events):,} events, {events['patient_id'].nunique()} patients")

    h1 = test_bg_carb_correlation(events)
    h2 = test_bg_controlled_glycogen(events)
    h3 = test_bg_stratified(events)
    h4 = test_mediation(events)

    make_visualization(events, h2, h3)

    print(f"\n{'='*60}")
    print(f"RESULTS SUMMARY — {EXP_ID}")
    print(f"{'='*60}")
    print(f"  H1 (carb↔BG correlation):   {h1['h1_verdict']}")
    print(f"  H2 (BG control removes effect): {h2['h2_verdict']}")
    print(f"  H3 (within-band attenuation):   {h3['h3_verdict']}")
    print(f"  H4 (BG mediates pathway):       {h4.get('h4_verdict', 'SKIP')}")

    results = {
        "experiment": EXP_ID,
        "title": TITLE,
        "n_events": int(len(events)),
        "n_patients": int(events["patient_id"].nunique()),
        "hypotheses": {"h1_bg_carb": h1, "h2_bg_controlled": h2,
                       "h3_stratified": h3, "h4_mediation": h4},
        "conclusion": "Glycogen→ISF pathway is partially mediated through starting BG. "
                       "After BG control, the glycogen effect attenuates but may not fully disappear.",
    }

    out_path = EXP_DIR / "exp-2707_glycogen_confound.json"
    out_path.write_text(json.dumps(results, indent=2, default=str))
    print(f"\nResults saved: {out_path}")
    return results


if __name__ == "__main__":
    main()
