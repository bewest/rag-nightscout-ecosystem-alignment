#!/usr/bin/env python3
"""
EXP-2706: SC Ceiling via Dose-Response Slope

EXP-2703 found that threshold-based ceiling (50% drop-off) was too coarse —
most patients showed 100% ceiling. This experiment refines the methodology
using continuous dose-response slope as the ceiling metric.

Hypothesis:
  H1: Dose-response slope (marginal effect vs IOB) is significantly negative
      for most patients (diminishing returns at higher IOB)
  H2: Per-patient slope is stable (split-half reliability > 0.6)
  H3: Slope correlates with wall episode rate (steeper negative = more walls)
  H4: Patients cluster into absorption phenotypes (fast/normal/slow absorbers)

Methodology:
  1. For each patient, fit linear regression: marginal_effect ~ iob_start
  2. Negative slope = diminishing returns (SC ceiling effect)
  3. Normalize slope by baseline marginal effect for cross-patient comparison
  4. Cluster patients by normalized slope
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
VIS = Path("visualizations/sc-slope")
VIS.mkdir(parents=True, exist_ok=True)

EXP_ID = "EXP-2706"
TITLE = "SC Ceiling via Dose-Response Slope"
BG_FLOOR = 150.0
HORIZON_STEPS = 24
WALL_BG_THRESHOLD = 250.0
WALL_DURATION_STEPS = 24


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
    """Extract correction events with IOB for dose-response."""
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

        for i in range(1, len(pg) - h):
            bg0 = glucose[i]
            bg_end = glucose[i + h]
            if np.isnan(bg0) or np.isnan(bg_end) or np.isnan(iob[i]):
                continue
            if bg0 < BG_FLOOR:
                continue

            bolus_2h = float(np.nansum(bolus[i:i + h]))
            smb_2h = float(np.nansum(smb[i:i + h]))
            excess_basal_2h = float(np.nansum(net_basal[i:i + h])) / 12.0
            carbs_2h = float(np.nansum(carbs[i:i + h]))
            total_insulin = bolus_2h + smb_2h + excess_basal_2h

            if carbs_2h > 5.0 or total_insulin < 0.1:
                continue

            observed_drop = bg0 - bg_end
            marginal_effect = observed_drop / total_insulin

            events.append({
                "patient_id": pid,
                "bg0": bg0,
                "observed_drop": observed_drop,
                "total_insulin": total_insulin,
                "iob_start": float(iob[i]),
                "marginal_effect": marginal_effect,
                "controller": ctrl,
            })

    df = pd.DataFrame(events)
    print(f"  {len(df):,} events, {df['patient_id'].nunique()} patients")
    return df


def detect_wall_episodes(grid):
    """Detect wall episodes."""
    wall_episodes = {}
    for pid, pg in grid.groupby("patient_id"):
        pg = pg.sort_values("time").reset_index(drop=True)
        glucose = pg["glucose"].values
        above = glucose > WALL_BG_THRESHOLD
        episodes = 0
        streak = 0
        for val in above:
            if val:
                streak += 1
                if streak == WALL_DURATION_STEPS:
                    episodes += 1
            else:
                streak = 0
        duration_weeks = len(pg) * 5 / 60 / (24 * 7)
        wall_episodes[pid] = {"n_episodes": episodes,
                              "rate_per_week": round(episodes / max(duration_weeks, 0.1), 2)}
    return wall_episodes


def compute_per_patient_slopes(events):
    """Compute dose-response slope per patient."""
    print("\n── Computing per-patient dose-response slopes ──")
    results = []

    for pid, pg in events.groupby("patient_id"):
        ctrl = pg["controller"].iloc[0]
        n = len(pg)
        if n < 30:
            results.append({"patient_id": pid, "controller": ctrl, "n": n,
                            "slope": None, "verdict": "SKIP"})
            continue

        # Linear regression: marginal_effect ~ iob_start
        slope, intercept, r_val, p_val, se = stats.linregress(pg["iob_start"], pg["marginal_effect"])

        # Normalized slope: slope / baseline_effect (effect at low IOB)
        low_iob = pg[pg["iob_start"] <= pg["iob_start"].quantile(0.25)]
        baseline_effect = float(low_iob["marginal_effect"].median()) if len(low_iob) >= 5 else float(pg["marginal_effect"].median())
        norm_slope = slope / abs(baseline_effect) if abs(baseline_effect) > 0.1 else 0

        # IOB range
        iob_range = float(pg["iob_start"].quantile(0.95) - pg["iob_start"].quantile(0.05))

        results.append({
            "patient_id": pid,
            "controller": ctrl,
            "n": int(n),
            "slope": round(float(slope), 3),
            "intercept": round(float(intercept), 1),
            "r_value": round(float(r_val), 3),
            "p_value": float(p_val),
            "se": round(float(se), 3),
            "norm_slope": round(float(norm_slope), 4),
            "baseline_effect": round(baseline_effect, 1),
            "iob_range": round(iob_range, 1),
            "is_diminishing": bool(slope < 0 and p_val < 0.1),
            "verdict": "ESTIMATED",
        })

    valid = [r for r in results if r["verdict"] == "ESTIMATED"]
    n_diminishing = sum(1 for r in valid if r["is_diminishing"])
    print(f"  {len(valid)} patients estimated, {n_diminishing} show diminishing returns")
    return results


def test_hypotheses(patient_slopes, wall_episodes, events):
    """Test all hypotheses."""
    valid = [p for p in patient_slopes if p["verdict"] == "ESTIMATED"]
    slopes = [p["slope"] for p in valid]

    # H1: Most patients have negative slope
    print("\n── H1: Negative dose-response slope ──")
    n_negative = sum(1 for s in slopes if s < 0)
    n_sig_negative = sum(1 for p in valid if p["slope"] < 0 and p["p_value"] < 0.1)
    verdict_h1 = bool(n_negative > len(valid) * 0.5)
    print(f"  {n_negative}/{len(valid)} negative slope ({100*n_negative/max(len(valid),1):.0f}%)")
    print(f"  {n_sig_negative}/{len(valid)} significantly negative (p<0.1)")
    median_slope = float(np.median(slopes))
    print(f"  Median slope: {median_slope:.3f}")

    h1 = {"h1_verdict": "PASS" if verdict_h1 else "FAIL",
           "n_negative": n_negative, "n_total": len(valid),
           "n_sig_negative": n_sig_negative,
           "median_slope": round(median_slope, 3)}

    # H2: Split-half reliability
    print("\n── H2: Temporal stability ──")
    reliabilities = []
    for pid, pg in events.groupby("patient_id"):
        pg = pg.sort_values("bg0")  # Sort by some independent variable
        n = len(pg)
        if n < 60:
            continue
        half = n // 2
        first = pg.iloc[:half]
        second = pg.iloc[half:]

        try:
            s1, _, _, _, _ = stats.linregress(first["iob_start"], first["marginal_effect"])
            s2, _, _, _, _ = stats.linregress(second["iob_start"], second["marginal_effect"])
            reliabilities.append({"patient_id": pid, "slope_1": s1, "slope_2": s2})
        except Exception:
            continue

    if len(reliabilities) >= 5:
        r_half, p_half = stats.pearsonr(
            [r["slope_1"] for r in reliabilities],
            [r["slope_2"] for r in reliabilities],
        )
        verdict_h2 = bool(r_half > 0.6)
        print(f"  Split-half r={r_half:.3f}, p={p_half:.4f}")
    else:
        r_half, p_half = np.nan, np.nan
        verdict_h2 = False

    h2 = {"h2_verdict": "PASS" if verdict_h2 else "FAIL",
           "split_half_r": round(float(r_half), 3) if not np.isnan(r_half) else None,
           "n_patients": len(reliabilities)}

    # H3: Slope correlates with wall episodes
    print("\n── H3: Slope ↔ wall correlation ──")
    pairs = [(p["norm_slope"], wall_episodes.get(p["patient_id"], {}).get("rate_per_week", 0))
             for p in valid if p["patient_id"] in wall_episodes and p["norm_slope"] is not None]
    if len(pairs) >= 5:
        slope_vals = [x[0] for x in pairs]
        wall_vals = [x[1] for x in pairs]
        r_wall, p_wall = stats.spearmanr(slope_vals, wall_vals)
        verdict_h3 = bool(r_wall < -0.3 and p_wall < 0.1)
        print(f"  Spearman r={r_wall:.3f}, p={p_wall:.4f}")
    else:
        r_wall, p_wall = np.nan, np.nan
        verdict_h3 = False

    h3 = {"h3_verdict": "PASS" if verdict_h3 else "FAIL",
           "spearman_r": round(float(r_wall), 3) if not np.isnan(r_wall) else None,
           "spearman_p": float(p_wall) if not np.isnan(p_wall) else None}

    # H4: Absorption phenotype clustering
    print("\n── H4: Absorption phenotypes ──")
    norm_slopes = [p["norm_slope"] for p in valid if p["norm_slope"] is not None]
    if len(norm_slopes) >= 10:
        # Simple tertile clustering
        q33, q66 = np.percentile(norm_slopes, [33, 66])
        phenotypes = {"fast_absorber": 0, "normal_absorber": 0, "slow_absorber": 0}
        for ns in norm_slopes:
            if ns > q66:
                phenotypes["fast_absorber"] += 1
            elif ns > q33:
                phenotypes["normal_absorber"] += 1
            else:
                phenotypes["slow_absorber"] += 1

        # Check if phenotypes have different wall rates
        pheno_walls = {"fast_absorber": [], "normal_absorber": [], "slow_absorber": []}
        for p in valid:
            if p["norm_slope"] is None or p["patient_id"] not in wall_episodes:
                continue
            ns = p["norm_slope"]
            wr = wall_episodes[p["patient_id"]]["rate_per_week"]
            if ns > q66:
                pheno_walls["fast_absorber"].append(wr)
            elif ns > q33:
                pheno_walls["normal_absorber"].append(wr)
            else:
                pheno_walls["slow_absorber"].append(wr)

        pheno_stats = {}
        for pheno, walls in pheno_walls.items():
            pheno_stats[pheno] = {
                "n": len(walls),
                "mean_wall_rate": round(float(np.mean(walls)), 2) if walls else None,
            }

        groups = [v for v in pheno_walls.values() if len(v) >= 2]
        if len(groups) >= 2:
            kw_stat, kw_p = stats.kruskal(*groups)
            verdict_h4 = bool(kw_p < 0.1)
        else:
            kw_stat, kw_p = np.nan, np.nan
            verdict_h4 = False

        print(f"  Phenotypes: {phenotypes}")
        for ph, ps in pheno_stats.items():
            print(f"    {ph}: n={ps['n']}, mean wall rate={ps['mean_wall_rate']}")
    else:
        phenotypes = {}
        pheno_stats = {}
        kw_stat, kw_p = np.nan, np.nan
        verdict_h4 = False

    h4 = {"h4_verdict": "PASS" if verdict_h4 else "FAIL",
           "phenotypes": phenotypes, "phenotype_stats": pheno_stats,
           "kw_p": float(kw_p) if not np.isnan(kw_p) else None}

    return h1, h2, h3, h4


def make_visualization(events, patient_slopes, wall_episodes):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        valid = [p for p in patient_slopes if p["verdict"] == "ESTIMATED"]
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        fig.suptitle(f"{EXP_ID}: SC Ceiling via Dose-Response Slope (N={len(valid)} patients)", fontsize=14)

        # Panel 1: Slope distribution
        ax = axes[0, 0]
        slopes = [p["slope"] for p in valid]
        colors = ["green" if s < 0 else "red" for s in sorted(slopes)]
        ax.barh(range(len(slopes)), sorted(slopes), color=colors, alpha=0.7)
        ax.axvline(0, color="black", linewidth=0.8)
        ax.set_xlabel("Dose-Response Slope")
        ax.set_title("Per-Patient Dose-Response Slope")

        # Panel 2: Example dose-response curves (3 patients)
        ax = axes[0, 1]
        for p in sorted(valid, key=lambda x: x["slope"])[:3]:
            pid = p["patient_id"]
            pg = events[events["patient_id"] == pid]
            ax.scatter(pg["iob_start"], pg["marginal_effect"], s=5, alpha=0.2, label=f"{pid[:8]} (s={p['slope']:.2f})")
            x_line = np.array([pg["iob_start"].min(), pg["iob_start"].max()])
            ax.plot(x_line, p["intercept"] + p["slope"] * x_line, linewidth=2)
        ax.set_xlabel("IOB at Start (U)")
        ax.set_ylabel("Marginal Effect (mg/dL/U)")
        ax.set_title("Dose-Response Curves (most negative slopes)")
        ax.legend(fontsize=7)

        # Panel 3: Normalized slope vs wall rate
        ax = axes[1, 0]
        pairs = [(p["norm_slope"], wall_episodes.get(p["patient_id"], {}).get("rate_per_week", 0))
                 for p in valid if p["patient_id"] in wall_episodes]
        if pairs:
            ax.scatter([x[0] for x in pairs], [x[1] for x in pairs], alpha=0.7, color="steelblue")
        ax.set_xlabel("Normalized Slope")
        ax.set_ylabel("Wall Episodes / Week")
        ax.set_title("Slope vs Wall Rate")

        # Panel 4: Slope by controller
        ax = axes[1, 1]
        ctrl_slopes = {}
        for p in valid:
            ctrl_slopes.setdefault(p["controller"], []).append(p["slope"])
        labels = list(ctrl_slopes.keys())
        data = [ctrl_slopes[l] for l in labels]
        if data:
            ax.boxplot(data, labels=labels)
        ax.axhline(0, color="black", linestyle="--", linewidth=0.8)
        ax.set_ylabel("Dose-Response Slope")
        ax.set_title("Slope by Controller")

        plt.tight_layout()
        path = VIS / "sc_slope.png"
        fig.savefig(path, dpi=150)
        plt.close()
        print(f"\n  Visualization saved: {path}")
    except ImportError:
        print("  matplotlib not available")


def main():
    grid = load_data()
    events = extract_events(grid)
    wall_episodes = detect_wall_episodes(grid)

    print(f"\n{EXP_ID}: {TITLE}")
    print(f"  {len(events):,} events, {events['patient_id'].nunique()} patients")

    patient_slopes = compute_per_patient_slopes(events)
    h1, h2, h3, h4 = test_hypotheses(patient_slopes, wall_episodes, events)

    make_visualization(events, patient_slopes, wall_episodes)

    print(f"\n{'='*60}")
    print(f"RESULTS SUMMARY — {EXP_ID}")
    print(f"{'='*60}")
    print(f"  H1 (most patients negative slope): {h1['h1_verdict']}")
    print(f"  H2 (split-half r>0.6):             {h2['h2_verdict']}")
    print(f"  H3 (slope↔wall correlation):       {h3['h3_verdict']}")
    print(f"  H4 (absorption phenotypes):         {h4['h4_verdict']}")

    results = {
        "experiment": EXP_ID,
        "title": TITLE,
        "n_events": int(len(events)),
        "n_patients": int(events["patient_id"].nunique()),
        "hypotheses": {"h1_negative_slope": h1, "h2_stability": h2,
                       "h3_wall_correlation": h3, "h4_phenotypes": h4},
        "per_patient_slopes": [{k: v for k, v in p.items()} for p in patient_slopes],
    }

    out_path = EXP_DIR / "exp-2706_sc_slope.json"
    out_path.write_text(json.dumps(results, indent=2, default=str))
    print(f"\nResults saved: {out_path}")
    return results


if __name__ == "__main__":
    main()
