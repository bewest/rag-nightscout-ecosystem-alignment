#!/usr/bin/env python3
"""
EXP-2705: Midday ISF Peak Investigation

EXP-2702 found circadian demand-ISF peaks at 12-16h (28.8 mg/dL/U), NOT dawn
(04-08h was only 21.3 mg/dL/U). This contradicts clinical expectations of
dawn phenomenon being the main circadian ISF driver.

Hypothesis:
  H1: Midday ISF peak is partially explained by post-meal correction context
      (corrections after lunch happen at higher BG → larger drops → higher ISF)
  H2: After controlling for starting BG, circadian ISF pattern changes shape
  H3: Meal-free corrections show different circadian pattern than post-meal
  H4: BGI-subtracted deviation shows less circadian pattern than raw ISF
      (proving BGI subtraction removes the meal confound)

Methodology:
  1. Re-extract correction events from EXP-2702 with starting BG as covariate
  2. Compute BG-adjusted ISF via regression: ISF ~ BG0 + time_block
  3. Compare raw vs BG-adjusted circadian patterns
  4. Split into meal-proximate (carbs 2-6h ago) vs meal-free corrections
  5. Test if BGI-subtracted deviation has less circadian variance than raw ISF

This experiment demonstrates the deconfounding infrastructure's value:
without BGI subtraction and BG control, the circadian ISF signal is confounded.
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
VIS = Path("visualizations/midday-isf-peak")
VIS.mkdir(parents=True, exist_ok=True)

EXP_ID = "EXP-2705"
TITLE = "Midday ISF Peak Investigation"

BG_FLOOR = 180.0
HORIZON_STEPS = 24
MIN_DOSE = 0.3
BLOCK_LABELS = ["00-04", "04-08", "08-12", "12-16", "16-20", "20-24"]
# Meal-proximate: had carbs 2-6h before this correction
MEAL_PROXIMATE_WINDOW = (24, 72)  # 2-6h in 5-min steps


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
    """Extract correction events with meal-proximity classification."""
    print("Extracting events with meal-proximity...")
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
            if demand_isf <= 0:
                continue

            expected_drop = total_insulin * isf_val
            deviation = observed_drop - expected_drop

            # Meal proximity: were there carbs 2-6h before this event?
            lookback_start = max(0, i - MEAL_PROXIMATE_WINDOW[1])
            lookback_end = max(0, i - MEAL_PROXIMATE_WINDOW[0])
            carbs_prior = float(np.nansum(carbs[lookback_start:lookback_end])) if lookback_end > lookback_start else 0
            is_meal_proximate = carbs_prior > 10.0

            roc_start = float(glucose[i] - glucose[i - 1]) if not np.isnan(glucose[i - 1]) else 0.0

            try:
                ts = pd.Timestamp(times[i])
                hour = ts.hour
            except Exception:
                hour = 0

            block_idx = min(hour // 4, 5)

            events.append({
                "patient_id": pid,
                "bg0": bg0,
                "bg_end": bg_end,
                "observed_drop": observed_drop,
                "total_insulin": total_insulin,
                "demand_isf": demand_isf,
                "deviation": deviation,
                "expected_drop": expected_drop,
                "iob_start": float(iob[i]) if not np.isnan(iob[i]) else 0.0,
                "roc_start": roc_start,
                "carbs_prior_2_6h": carbs_prior,
                "is_meal_proximate": is_meal_proximate,
                "hour": hour,
                "block_idx": block_idx,
                "block_label": BLOCK_LABELS[block_idx],
                "controller": ctrl,
            })

    df = pd.DataFrame(events)
    n_mp = df["is_meal_proximate"].sum()
    print(f"  {len(df):,} events, meal-proximate: {n_mp:,} ({100*n_mp/len(df):.0f}%)")
    return df


def test_bg_confound(events):
    """H1: Is midday ISF peak explained by starting BG?"""
    print("\n── H1: Starting BG confound analysis ──")

    # Compare median BG0 by time block
    bg_by_block = []
    isf_by_block = []
    for idx, label in enumerate(BLOCK_LABELS):
        block = events[events["block_idx"] == idx]
        if len(block) < 20:
            continue
        bg_by_block.append({"block": label, "median_bg0": float(block["bg0"].median()),
                            "n": int(len(block))})
        isf_by_block.append({"block": label, "median_isf": float(block["demand_isf"].median())})

    # Correlation between block median BG0 and block median ISF
    if len(bg_by_block) >= 4:
        bg_vals = [b["median_bg0"] for b in bg_by_block]
        isf_vals = [b["median_isf"] for b in isf_by_block]
        r, p = stats.pearsonr(bg_vals, isf_vals)
        print(f"  Block-level BG↔ISF correlation: r={r:.3f}, p={p:.3f}")
    else:
        r, p = np.nan, np.nan

    # Per-event: partial correlation of ISF ~ block controlling for BG0
    from numpy.linalg import lstsq

    valid = events[["demand_isf", "bg0", "block_idx"]].dropna()
    y = valid["demand_isf"].values

    # Raw model: ISF ~ block dummies
    X_block = pd.get_dummies(valid["block_idx"], prefix="block").values
    X_block = np.column_stack([X_block, np.ones(len(valid))])
    beta_block, _, _, _ = lstsq(X_block, y, rcond=None)
    ss_res_block = np.sum((y - X_block @ beta_block) ** 2)
    ss_tot = np.sum((y - y.mean()) ** 2)
    r2_block_only = 1 - ss_res_block / ss_tot

    # Enhanced model: ISF ~ block dummies + BG0
    X_bg_block = np.column_stack([X_block[:, :-1], valid["bg0"].values, np.ones(len(valid))])
    beta_bg_block, _, _, _ = lstsq(X_bg_block, y, rcond=None)
    ss_res_bg_block = np.sum((y - X_bg_block @ beta_bg_block) ** 2)
    r2_bg_block = 1 - ss_res_bg_block / ss_tot

    # BG0 alone
    X_bg = np.column_stack([valid["bg0"].values, np.ones(len(valid))])
    beta_bg, _, _, _ = lstsq(X_bg, y, rcond=None)
    ss_res_bg = np.sum((y - X_bg @ beta_bg) ** 2)
    r2_bg_only = 1 - ss_res_bg / ss_tot

    print(f"  R² (block only): {r2_block_only:.4f}")
    print(f"  R² (BG0 only):   {r2_bg_only:.4f}")
    print(f"  R² (block+BG0):  {r2_bg_block:.4f}")
    print(f"  BG0 explains: {r2_bg_only/max(r2_bg_block, 0.001)*100:.0f}% of joint model")

    # BG-adjusted ISF by block (residualize BG0 first)
    bg_residuals = y - X_bg @ beta_bg  # ISF after removing BG effect
    valid_copy = valid.copy()
    valid_copy["isf_bg_adjusted"] = bg_residuals + y.mean()  # re-center

    adjusted_by_block = []
    for idx, label in enumerate(BLOCK_LABELS):
        block_adj = valid_copy[valid_copy["block_idx"] == idx]["isf_bg_adjusted"]
        if len(block_adj) >= 20:
            adjusted_by_block.append({"block": label, "adjusted_median": round(float(block_adj.median()), 1)})

    verdict = bool(r2_bg_only > r2_block_only)  # BG explains more than time block
    print(f"  H1 verdict: {'PASS' if verdict else 'FAIL'} (BG0 {'>' if verdict else '<'} time block as ISF predictor)")

    return {
        "h1_verdict": "PASS" if verdict else "FAIL",
        "bg_isf_block_r": round(float(r), 3) if not np.isnan(r) else None,
        "r2_block_only": round(float(r2_block_only), 4),
        "r2_bg_only": round(float(r2_bg_only), 4),
        "r2_bg_block": round(float(r2_bg_block), 4),
        "bg0_by_block": bg_by_block,
        "adjusted_isf_by_block": adjusted_by_block,
    }


def test_adjusted_pattern(events):
    """H2: After controlling for BG, circadian pattern changes."""
    print("\n── H2: BG-adjusted circadian pattern ──")

    from numpy.linalg import lstsq

    valid = events[["demand_isf", "bg0", "block_idx", "total_insulin", "iob_start"]].dropna()
    y = valid["demand_isf"].values

    # Compute BG-adjusted ISF (residualize out BG0, dose, IOB)
    X_covariates = np.column_stack([
        valid["bg0"].values,
        valid["total_insulin"].values,
        valid["iob_start"].values,
        np.ones(len(valid)),
    ])
    beta_cov, _, _, _ = lstsq(X_covariates, y, rcond=None)
    residuals = y - X_covariates @ beta_cov

    # Raw vs adjusted circadian pattern
    raw_pattern = {}
    adj_pattern = {}
    for idx, label in enumerate(BLOCK_LABELS):
        mask = valid["block_idx"].values == idx
        if mask.sum() < 20:
            continue
        raw_pattern[label] = round(float(np.median(y[mask])), 1)
        adj_pattern[label] = round(float(np.median(residuals[mask])), 1)

    # Does the pattern shape change?
    if len(raw_pattern) >= 4 and len(adj_pattern) >= 4:
        common = sorted(set(raw_pattern.keys()) & set(adj_pattern.keys()))
        raw_vals = [raw_pattern[k] for k in common]
        adj_vals = [adj_pattern[k] for k in common]

        # Rank correlation: does the ordering change?
        r_rank, p_rank = stats.spearmanr(raw_vals, adj_vals)

        # Find peak block in each
        raw_peak = common[np.argmax(raw_vals)]
        adj_peak = common[np.argmax(adj_vals)]
        peak_shifted = raw_peak != adj_peak

        print(f"  Raw pattern peak:     {raw_peak} ({raw_pattern[raw_peak]} mg/dL/U)")
        print(f"  Adjusted pattern peak: {adj_peak} ({adj_pattern[adj_peak]} residual)")
        print(f"  Rank correlation: r={r_rank:.3f}")
        print(f"  Peak shifted: {peak_shifted}")

        verdict = bool(peak_shifted or r_rank < 0.8)
    else:
        r_rank, peak_shifted = np.nan, False
        raw_peak = adj_peak = None
        verdict = False

    return {
        "h2_verdict": "PASS" if verdict else "FAIL",
        "raw_pattern": raw_pattern,
        "adjusted_pattern": adj_pattern,
        "rank_correlation": round(float(r_rank), 3) if not np.isnan(r_rank) else None,
        "raw_peak_block": raw_peak,
        "adjusted_peak_block": adj_peak,
        "peak_shifted": peak_shifted,
    }


def test_meal_proximity(events):
    """H3: Meal-free vs post-meal corrections show different patterns."""
    print("\n── H3: Meal-free vs meal-proximate circadian ISF ──")

    meal_free = events[~events["is_meal_proximate"]]
    meal_prox = events[events["is_meal_proximate"]]

    print(f"  Meal-free: {len(meal_free):,} events")
    print(f"  Meal-proximate: {len(meal_prox):,} events")

    mf_pattern = {}
    mp_pattern = {}
    for idx, label in enumerate(BLOCK_LABELS):
        mf_block = meal_free[meal_free["block_idx"] == idx]["demand_isf"]
        mp_block = meal_prox[meal_prox["block_idx"] == idx]["demand_isf"]
        if len(mf_block) >= 10:
            mf_pattern[label] = round(float(mf_block.median()), 1)
        if len(mp_block) >= 10:
            mp_pattern[label] = round(float(mp_block.median()), 1)

    print("  Meal-free pattern:", mf_pattern)
    print("  Meal-proximate pattern:", mp_pattern)

    # Compare: do meal-proximate corrections have higher midday ISF?
    common = sorted(set(mf_pattern.keys()) & set(mp_pattern.keys()))
    if len(common) >= 4:
        diffs = {k: mp_pattern[k] - mf_pattern[k] for k in common}
        midday_blocks = [k for k in common if k in ["08-12", "12-16"]]
        other_blocks = [k for k in common if k not in ["08-12", "12-16"]]

        midday_diff = np.mean([diffs[k] for k in midday_blocks]) if midday_blocks else 0
        other_diff = np.mean([diffs[k] for k in other_blocks]) if other_blocks else 0

        # Meal-proximate corrections inflate midday ISF more than other blocks?
        excess_midday = midday_diff - other_diff
        verdict = bool(abs(excess_midday) > 2.0)

        print(f"  Midday meal-prox excess ISF: {midday_diff:.1f} mg/dL/U")
        print(f"  Other blocks meal-prox excess: {other_diff:.1f} mg/dL/U")
        print(f"  Differential: {excess_midday:.1f} mg/dL/U")
    else:
        excess_midday = 0
        verdict = False

    # KW test within meal-free only: does circadian pattern survive?
    mf_groups = [g["demand_isf"].values for _, g in meal_free.groupby("block_idx") if len(g) >= 10]
    if len(mf_groups) >= 3:
        kw_stat, kw_p = stats.kruskal(*mf_groups)
        mf_circadian_sig = kw_p < 0.05
        print(f"  Meal-free circadian KW: stat={kw_stat:.1f}, p={kw_p:.4f} ({'significant' if mf_circadian_sig else 'not significant'})")
    else:
        kw_stat, kw_p = np.nan, np.nan
        mf_circadian_sig = False

    return {
        "h3_verdict": "PASS" if verdict else "FAIL",
        "meal_free_pattern": mf_pattern,
        "meal_proximate_pattern": mp_pattern,
        "excess_midday_isf": round(float(excess_midday), 1),
        "meal_free_n": int(len(meal_free)),
        "meal_proximate_n": int(len(meal_prox)),
        "meal_free_circadian_kw_p": float(kw_p) if not np.isnan(kw_p) else None,
        "meal_free_circadian_significant": mf_circadian_sig,
    }


def test_deviation_circadian(events):
    """H4: BGI-subtracted deviation has less circadian variance than raw ISF."""
    print("\n── H4: Deviation vs raw ISF circadian variance ──")

    # Variance ratio: circadian variance / total variance
    # For raw ISF
    raw_group_means = events.groupby("block_idx")["demand_isf"].mean()
    grand_mean = events["demand_isf"].mean()
    ss_between_raw = sum(
        len(events[events["block_idx"] == b]) * (m - grand_mean) ** 2
        for b, m in raw_group_means.items()
    )
    ss_total_raw = ((events["demand_isf"] - grand_mean) ** 2).sum()
    eta2_raw = ss_between_raw / ss_total_raw if ss_total_raw > 0 else 0

    # For deviation
    dev_group_means = events.groupby("block_idx")["deviation"].mean()
    dev_grand_mean = events["deviation"].mean()
    ss_between_dev = sum(
        len(events[events["block_idx"] == b]) * (m - dev_grand_mean) ** 2
        for b, m in dev_group_means.items()
    )
    ss_total_dev = ((events["deviation"] - dev_grand_mean) ** 2).sum()
    eta2_dev = ss_between_dev / ss_total_dev if ss_total_dev > 0 else 0

    reduction_pct = (eta2_raw - eta2_dev) / eta2_raw * 100 if eta2_raw > 0 else 0
    verdict = bool(eta2_dev < eta2_raw)

    print(f"  Raw ISF η² (circadian): {eta2_raw:.4f}")
    print(f"  Deviation η² (circadian): {eta2_dev:.4f}")
    print(f"  Reduction: {reduction_pct:.0f}%")

    return {
        "h4_verdict": "PASS" if verdict else "FAIL",
        "eta2_raw_isf": round(float(eta2_raw), 4),
        "eta2_deviation": round(float(eta2_dev), 4),
        "reduction_pct": round(float(reduction_pct), 1),
    }


def make_visualization(events, h1, h2, h3):
    """Generate midday ISF peak visualization."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        fig.suptitle(f"{EXP_ID}: Midday ISF Peak Investigation (N={len(events):,})", fontsize=14)

        # Panel 1: Raw vs BG-adjusted circadian ISF
        ax = axes[0, 0]
        raw = h2.get("raw_pattern", {})
        adj = h2.get("adjusted_pattern", {})
        if raw and adj:
            common = sorted(set(raw.keys()) & set(adj.keys()))
            x = range(len(common))
            ax.plot(x, [raw[k] for k in common], "o-", label="Raw ISF", color="steelblue")
            ax2 = ax.twinx()
            ax2.plot(x, [adj[k] for k in common], "s--", label="BG-adjusted", color="orange")
            ax.set_xticks(x)
            ax.set_xticklabels(common, rotation=45)
            ax.set_ylabel("Raw ISF (mg/dL/U)", color="steelblue")
            ax2.set_ylabel("Adjusted residual", color="orange")
            ax.legend(loc="upper left")
            ax2.legend(loc="upper right")
        ax.set_title("Raw vs BG-Adjusted Circadian ISF")

        # Panel 2: Starting BG by time block
        ax = axes[0, 1]
        bg_data = h1.get("bg0_by_block", [])
        if bg_data:
            labels = [b["block"] for b in bg_data]
            medians = [b["median_bg0"] for b in bg_data]
            ax.bar(range(len(labels)), medians, color="coral", alpha=0.7)
            ax.set_xticks(range(len(labels)))
            ax.set_xticklabels(labels, rotation=45)
        ax.set_ylabel("Median Starting BG (mg/dL)")
        ax.set_title("Starting BG by Time Block")

        # Panel 3: Meal-free vs meal-proximate
        ax = axes[1, 0]
        mf = h3.get("meal_free_pattern", {})
        mp = h3.get("meal_proximate_pattern", {})
        if mf and mp:
            common = sorted(set(mf.keys()) & set(mp.keys()))
            x = range(len(common))
            ax.plot(x, [mf[k] for k in common], "o-", label=f"Meal-free (n={h3.get('meal_free_n', 0):,})")
            ax.plot(x, [mp[k] for k in common], "s--", label=f"Meal-proximate (n={h3.get('meal_proximate_n', 0):,})")
            ax.set_xticks(x)
            ax.set_xticklabels(common, rotation=45)
            ax.legend()
        ax.set_ylabel("ISF (mg/dL/U)")
        ax.set_title("Meal-Free vs Post-Meal Corrections")

        # Panel 4: BG0 vs ISF scatter with block coloring
        ax = axes[1, 1]
        sample = events.sample(min(3000, len(events)), random_state=42)
        colors_map = {0: "navy", 1: "blue", 2: "green", 3: "orange", 4: "red", 5: "purple"}
        for idx, label in enumerate(BLOCK_LABELS):
            block = sample[sample["block_idx"] == idx]
            ax.scatter(block["bg0"], block["demand_isf"], s=3, alpha=0.2,
                       color=colors_map.get(idx, "gray"), label=label)
        ax.set_xlabel("Starting BG (mg/dL)")
        ax.set_ylabel("Demand-ISF (mg/dL/U)")
        ax.set_title("BG0 vs ISF by Time Block")
        ax.legend(fontsize=7, markerscale=3)

        plt.tight_layout()
        path = VIS / "midday_isf_peak.png"
        fig.savefig(path, dpi=150)
        plt.close()
        print(f"\n  Visualization saved: {path}")
    except ImportError:
        print("  matplotlib not available, skipping visualization")


def main():
    grid = load_data()
    events = extract_events(grid)

    if len(events) == 0:
        print("ERROR: No events")
        sys.exit(1)

    print(f"\n{EXP_ID}: {TITLE}")
    print(f"  {len(events):,} events, {events['patient_id'].nunique()} patients")

    h1 = test_bg_confound(events)
    h2 = test_adjusted_pattern(events)
    h3 = test_meal_proximity(events)
    h4 = test_deviation_circadian(events)

    make_visualization(events, h1, h2, h3)

    print(f"\n{'='*60}")
    print(f"RESULTS SUMMARY — {EXP_ID}")
    print(f"{'='*60}")
    print(f"  H1 (BG confounds midday peak): {h1['h1_verdict']}")
    print(f"  H2 (pattern changes after BG control): {h2['h2_verdict']}")
    print(f"  H3 (meal-prox inflates midday): {h3['h3_verdict']}")
    print(f"  H4 (BGI subtraction reduces circadian): {h4['h4_verdict']}")

    results = {
        "experiment": EXP_ID,
        "title": TITLE,
        "n_events": int(len(events)),
        "n_patients": int(events["patient_id"].nunique()),
        "hypotheses": {
            "h1_bg_confound": h1,
            "h2_adjusted_pattern": h2,
            "h3_meal_proximity": h3,
            "h4_deviation_circadian": h4,
        },
        "methodology": {
            "bg_floor": BG_FLOOR, "horizon_hours": 2.0, "min_dose": MIN_DOSE,
            "meal_proximate_window_hours": "2-6h prior carbs >10g",
            "deconfounding": "BG0 residualization + meal proximity split",
        },
    }

    out_path = EXP_DIR / "exp-2705_midday_isf_peak.json"
    out_path.write_text(json.dumps(results, indent=2, default=str))
    print(f"\nResults saved: {out_path}")
    return results


if __name__ == "__main__":
    main()
