#!/usr/bin/env python3
"""
EXP-2703: Per-Patient SC Absorption Ceiling Estimation

Extends EXP-2656 (population median 30%) to extract per-patient subcutaneous
absorption ceiling using the validated deconfounding pipeline.

Hypothesis:
  H1: SC ceiling varies >2× across patients (significant heterogeneity)
  H2: Low SC ceiling correlates with wall episode frequency (r < -0.3)
  H3: Controller type affects measured ceiling (Trio/DynISF higher than Loop)
  H4: Per-patient ceiling is stable across time (split-half reliability > 0.6)

Methodology:
  1. For each patient, bin correction events by IOB at start
  2. Compute dose-response: observed_drop vs total_insulin at different IOB levels
  3. Fit piecewise linear model: linear up to ceiling, then flat
  4. Estimate ceiling as IOB where marginal effect drops to <50% of baseline
  5. Correlate with wall episode rate (BG>250 for >2h)

Research basis:
  EXP-2656: Population SC ceiling 26-56%, median 30%
  EXP-2667: SC ceiling + demand ISF combined (production-ready)
  EXP-2698: Channel coefficients for subtraction
"""
import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats, optimize

warnings.filterwarnings("ignore")

# ── Paths ────────────────────────────────────────────────────────────
GRID = Path("externals/ns-parquet/training/grid.parquet")
DS = Path("externals/ns-parquet/training/devicestatus.parquet")
MANIFEST = Path("externals/experiments/autoprepare-qualified.json")
EXP = Path("externals/experiments")
VIS = Path("visualizations/sc-ceiling-per-patient")
VIS.mkdir(parents=True, exist_ok=True)

EXP_ID = "EXP-2703"
TITLE = "Per-Patient SC Absorption Ceiling Estimation"

# ── Constants ────────────────────────────────────────────────────────
BG_FLOOR = 150.0           # Slightly lower than 180 to get more events for ceiling
HORIZON_STEPS = 24         # 2h demand phase
MIN_EVENTS_PER_BIN = 10   # For dose-response bins
IOB_BINS = 6               # Number of IOB quantile bins
WALL_BG_THRESHOLD = 250.0  # BG threshold for wall episodes
WALL_DURATION_STEPS = 24   # 2h at high BG = wall episode


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


def extract_events(grid):
    """Extract correction events with IOB tracking for ceiling estimation."""
    print("Extracting events for SC ceiling...")
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
            if np.isnan(bg0) or np.isnan(bg_end) or np.isnan(iob[i]):
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
            if total_insulin < 0.1:
                continue

            observed_drop = bg0 - bg_end
            iob_start = float(iob[i])

            # ISF for this event
            demand_isf = observed_drop / total_insulin if total_insulin > 0.3 else np.nan

            # Marginal effectiveness = drop per unit insulin
            marginal_effect = observed_drop / total_insulin if total_insulin > 0 else 0

            events.append({
                "patient_id": pid,
                "time": times[i],
                "bg0": bg0,
                "bg_end": bg_end,
                "observed_drop": observed_drop,
                "total_insulin": total_insulin,
                "demand_isf": demand_isf,
                "iob_start": iob_start,
                "marginal_effect": marginal_effect,
                "bolus_2h": bolus_2h,
                "smb_2h": smb_2h,
                "excess_basal_2h": excess_basal_2h,
                "controller": ctrl,
                "profile_isf": isf_val,
            })

    df = pd.DataFrame(events)
    print(f"  {len(df):,} events, {df['patient_id'].nunique()} patients")
    return df


def detect_wall_episodes(grid):
    """Detect wall episodes: BG > 250 for > 2h."""
    print("Detecting wall episodes...")
    wall_episodes = {}

    for pid, pg in grid.groupby("patient_id"):
        pg = pg.sort_values("time").reset_index(drop=True)
        glucose = pg["glucose"].values
        above = glucose > WALL_BG_THRESHOLD

        # Count contiguous stretches
        episodes = 0
        streak = 0
        for val in above:
            if val:
                streak += 1
                if streak == WALL_DURATION_STEPS:
                    episodes += 1
            else:
                streak = 0

        # Normalize by data duration (episodes per week)
        duration_hours = len(pg) * 5 / 60  # 5-min steps
        duration_weeks = duration_hours / (24 * 7)
        rate = episodes / max(duration_weeks, 0.1)

        wall_episodes[pid] = {
            "n_episodes": episodes,
            "rate_per_week": round(rate, 2),
            "duration_weeks": round(duration_weeks, 1),
        }

    print(f"  {sum(1 for w in wall_episodes.values() if w['n_episodes'] > 0)} patients with wall episodes")
    return wall_episodes


def estimate_per_patient_ceiling(events):
    """Estimate SC absorption ceiling per patient using dose-response at different IOB levels."""
    print("\n── Estimating per-patient SC ceiling ──")

    patient_ceilings = []
    for pid, pg in events.groupby("patient_id"):
        if len(pg) < 30:
            patient_ceilings.append({
                "patient_id": pid,
                "n_events": int(len(pg)),
                "ceiling_pct": None,
                "verdict": "SKIP",
                "reason": "too few events",
            })
            continue

        ctrl = pg["controller"].iloc[0]

        # Bin events by IOB quantile
        try:
            pg = pg.copy()
            pg["iob_bin"] = pd.qcut(pg["iob_start"], q=IOB_BINS, labels=False, duplicates="drop")
        except ValueError:
            patient_ceilings.append({
                "patient_id": pid,
                "n_events": int(len(pg)),
                "ceiling_pct": None,
                "verdict": "SKIP",
                "reason": "insufficient IOB range",
                "controller": ctrl,
            })
            continue

        # Compute marginal effect per IOB bin
        bin_stats = []
        for b in sorted(pg["iob_bin"].dropna().unique()):
            bin_data = pg[pg["iob_bin"] == b]
            if len(bin_data) < MIN_EVENTS_PER_BIN:
                continue
            bin_stats.append({
                "bin": int(b),
                "iob_median": float(bin_data["iob_start"].median()),
                "marginal_effect_median": float(bin_data["marginal_effect"].median()),
                "n": int(len(bin_data)),
            })

        if len(bin_stats) < 3:
            patient_ceilings.append({
                "patient_id": pid,
                "n_events": int(len(pg)),
                "ceiling_pct": None,
                "verdict": "SKIP",
                "reason": "too few IOB bins with data",
                "controller": ctrl,
            })
            continue

        # Baseline marginal effect (lowest IOB bin)
        baseline_effect = bin_stats[0]["marginal_effect_median"]

        # Find where marginal effect drops to <50% of baseline
        ceiling_iob = None
        ceiling_pct = None
        for bs in bin_stats[1:]:
            if baseline_effect > 0:
                relative_effect = bs["marginal_effect_median"] / baseline_effect
                if relative_effect < 0.5:
                    ceiling_iob = bs["iob_median"]
                    # Express as % of max IOB observed
                    max_iob = pg["iob_start"].quantile(0.95)
                    ceiling_pct = (ceiling_iob / max(max_iob, 0.1)) * 100
                    break

        # If no ceiling found, it's >95th percentile IOB
        if ceiling_pct is None:
            ceiling_pct = 100.0  # No measurable ceiling

        # Dose-response slope (linear regression: marginal_effect ~ iob)
        iob_vals = [b["iob_median"] for b in bin_stats]
        me_vals = [b["marginal_effect_median"] for b in bin_stats]
        if len(iob_vals) >= 3:
            slope, intercept, r_val, p_val, _ = stats.linregress(iob_vals, me_vals)
            # Negative slope = diminishing returns at high IOB
            is_diminishing = bool(slope < 0 and p_val < 0.1)
        else:
            slope, r_val, p_val = np.nan, np.nan, np.nan
            is_diminishing = False

        patient_ceilings.append({
            "patient_id": pid,
            "controller": ctrl,
            "n_events": int(len(pg)),
            "ceiling_pct": round(float(ceiling_pct), 1),
            "ceiling_iob": round(float(ceiling_iob), 2) if ceiling_iob else None,
            "baseline_marginal_effect": round(float(baseline_effect), 1),
            "dose_response_slope": round(float(slope), 3) if not np.isnan(slope) else None,
            "dose_response_r": round(float(r_val), 3) if not np.isnan(r_val) else None,
            "dose_response_p": float(p_val) if not np.isnan(p_val) else None,
            "is_diminishing": is_diminishing,
            "bin_stats": bin_stats,
            "verdict": "ESTIMATED",
        })
        print(f"  {pid}: ceiling={ceiling_pct:.0f}%, slope={slope:.3f}, diminishing={is_diminishing}")

    return patient_ceilings


def test_hypotheses(patient_ceilings, wall_episodes, events):
    """Test all 4 hypotheses."""

    # Gather valid ceilings
    valid = [p for p in patient_ceilings if p.get("ceiling_pct") is not None and p["verdict"] == "ESTIMATED"]
    ceilings = [p["ceiling_pct"] for p in valid]

    # H1: Heterogeneity
    print("\n── H1: SC ceiling heterogeneity ──")
    if len(ceilings) >= 5:
        ceiling_range = max(ceilings) - min(ceilings)
        ceiling_ratio = max(ceilings) / max(min(ceilings), 1.0)
        h1_verdict = bool(ceiling_ratio > 2.0)
        print(f"  Range: {min(ceilings):.0f}% to {max(ceilings):.0f}%, ratio={ceiling_ratio:.1f}×")
    else:
        h1_verdict = False
        ceiling_ratio = None
    h1 = {"h1_verdict": "PASS" if h1_verdict else "FAIL",
           "ceiling_ratio": round(float(ceiling_ratio), 2) if ceiling_ratio else None,
           "n_patients": len(valid),
           "median_ceiling": round(float(np.median(ceilings)), 1) if ceilings else None,
           "range": [round(float(min(ceilings)), 1), round(float(max(ceilings)), 1)] if ceilings else None}

    # H2: Correlation with wall episodes
    print("\n── H2: Ceiling ↔ wall episode correlation ──")
    ceiling_wall_pairs = []
    for p in valid:
        pid = p["patient_id"]
        if pid in wall_episodes:
            ceiling_wall_pairs.append((p["ceiling_pct"], wall_episodes[pid]["rate_per_week"]))

    if len(ceiling_wall_pairs) >= 5:
        ceil_vals = [x[0] for x in ceiling_wall_pairs]
        wall_vals = [x[1] for x in ceiling_wall_pairs]
        r_val, p_val = stats.spearmanr(ceil_vals, wall_vals)
        h2_verdict = bool(r_val < -0.3 and p_val < 0.1)
        print(f"  Spearman r={r_val:.3f}, p={p_val:.4f}")
    else:
        r_val, p_val = np.nan, np.nan
        h2_verdict = False
    h2 = {"h2_verdict": "PASS" if h2_verdict else "FAIL",
           "spearman_r": round(float(r_val), 3) if not np.isnan(r_val) else None,
           "spearman_p": float(p_val) if not np.isnan(p_val) else None,
           "n_pairs": len(ceiling_wall_pairs)}

    # H3: Controller effect
    print("\n── H3: Controller type affects ceiling ──")
    ctrl_ceilings = {}
    for p in valid:
        ctrl = p.get("controller", "unknown")
        ctrl_ceilings.setdefault(ctrl, []).append(p["ceiling_pct"])

    ctrl_stats = {}
    for ctrl, vals in ctrl_ceilings.items():
        ctrl_stats[ctrl] = {
            "n": len(vals),
            "median": round(float(np.median(vals)), 1),
            "mean": round(float(np.mean(vals)), 1),
            "std": round(float(np.std(vals)), 1) if len(vals) > 1 else 0,
        }
        print(f"  {ctrl}: median={np.median(vals):.0f}%, n={len(vals)}")

    groups = [v for v in ctrl_ceilings.values() if len(v) >= 3]
    if len(groups) >= 2:
        kw_stat, kw_p = stats.kruskal(*groups)
        h3_verdict = bool(kw_p < 0.1)
    else:
        kw_stat, kw_p = np.nan, np.nan
        h3_verdict = False
    h3 = {"h3_verdict": "PASS" if h3_verdict else "FAIL",
           "controller_stats": ctrl_stats,
           "kw_statistic": round(float(kw_stat), 2) if not np.isnan(kw_stat) else None,
           "kw_p": float(kw_p) if not np.isnan(kw_p) else None}

    # H4: Split-half reliability
    print("\n── H4: Temporal stability (split-half) ──")
    reliabilities = []
    for pid, pg in events.groupby("patient_id"):
        pg = pg.sort_values("time")
        n = len(pg)
        if n < 60:
            continue
        half = n // 2
        first_half = pg.iloc[:half]
        second_half = pg.iloc[half:]

        # Compute median marginal effect per half as proxy for ceiling
        me1 = first_half["marginal_effect"].median()
        me2 = second_half["marginal_effect"].median()
        reliabilities.append({"patient_id": pid, "first_me": me1, "second_me": me2})

    if len(reliabilities) >= 5:
        r_half, p_half = stats.pearsonr(
            [r["first_me"] for r in reliabilities],
            [r["second_me"] for r in reliabilities],
        )
        h4_verdict = bool(r_half > 0.6)
        print(f"  Split-half r={r_half:.3f}, p={p_half:.4f}")
    else:
        r_half, p_half = np.nan, np.nan
        h4_verdict = False
    h4 = {"h4_verdict": "PASS" if h4_verdict else "FAIL",
           "split_half_r": round(float(r_half), 3) if not np.isnan(r_half) else None,
           "split_half_p": float(p_half) if not np.isnan(p_half) else None,
           "n_patients": len(reliabilities)}

    return h1, h2, h3, h4


def make_visualization(events, patient_ceilings, wall_episodes):
    """Generate SC ceiling visualization."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        valid = [p for p in patient_ceilings if p.get("ceiling_pct") is not None and p["verdict"] == "ESTIMATED"]

        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        fig.suptitle(f"{EXP_ID}: Per-Patient SC Absorption Ceiling (N={len(valid)} patients)", fontsize=14)

        # Panel 1: Ceiling distribution
        ax = axes[0, 0]
        ceilings = [p["ceiling_pct"] for p in valid]
        ax.hist(ceilings, bins=15, color="steelblue", alpha=0.7, edgecolor="black")
        ax.axvline(np.median(ceilings), color="red", linestyle="--", label=f"Median: {np.median(ceilings):.0f}%")
        ax.set_xlabel("SC Ceiling (%)")
        ax.set_ylabel("Count")
        ax.set_title("SC Ceiling Distribution")
        ax.legend()

        # Panel 2: Ceiling vs wall rate
        ax = axes[0, 1]
        pairs = [(p["ceiling_pct"], wall_episodes.get(p["patient_id"], {}).get("rate_per_week", 0))
                 for p in valid if p["patient_id"] in wall_episodes]
        if pairs:
            ax.scatter([x[0] for x in pairs], [x[1] for x in pairs], alpha=0.7, color="steelblue")
            ax.set_xlabel("SC Ceiling (%)")
            ax.set_ylabel("Wall Episodes / Week")
            ax.set_title("Ceiling vs Wall Episode Rate")

        # Panel 3: Dose-response by IOB (sample patient)
        ax = axes[1, 0]
        for p in valid[:3]:
            if "bin_stats" in p:
                iob = [b["iob_median"] for b in p["bin_stats"]]
                me = [b["marginal_effect_median"] for b in p["bin_stats"]]
                ax.plot(iob, me, "o-", label=f'{p["patient_id"][:8]}', alpha=0.7)
        ax.set_xlabel("IOB at Start (U)")
        ax.set_ylabel("Marginal Effect (mg/dL/U)")
        ax.set_title("Dose-Response Curves (sample patients)")
        ax.legend(fontsize=8)

        # Panel 4: Ceiling by controller
        ax = axes[1, 1]
        ctrl_ceilings = {}
        for p in valid:
            ctrl = p.get("controller", "unknown")
            ctrl_ceilings.setdefault(ctrl, []).append(p["ceiling_pct"])
        labels = list(ctrl_ceilings.keys())
        data = [ctrl_ceilings[l] for l in labels]
        if data:
            ax.boxplot(data, labels=labels)
        ax.set_ylabel("SC Ceiling (%)")
        ax.set_title("Ceiling by Controller Type")

        plt.tight_layout()
        path = VIS / "sc_ceiling_per_patient.png"
        fig.savefig(path, dpi=150)
        plt.close()
        print(f"\n  Visualization saved: {path}")
    except ImportError:
        print("  matplotlib not available, skipping visualization")


def main():
    grid, ctrl_map = load_data()
    events = extract_events(grid)
    wall_episodes = detect_wall_episodes(grid)

    if len(events) == 0:
        print("ERROR: No events extracted")
        sys.exit(1)

    print(f"\n{EXP_ID}: {TITLE}")
    print(f"  {len(events):,} events, {events['patient_id'].nunique()} patients")

    # Estimate per-patient ceiling
    patient_ceilings = estimate_per_patient_ceiling(events)

    # Test hypotheses
    h1, h2, h3, h4 = test_hypotheses(patient_ceilings, wall_episodes, events)

    # Visualization
    make_visualization(events, patient_ceilings, wall_episodes)

    # Summary
    print(f"\n{'='*60}")
    print(f"RESULTS SUMMARY — {EXP_ID}")
    print(f"{'='*60}")
    print(f"  H1 (heterogeneity >2×):      {h1['h1_verdict']}")
    print(f"  H2 (ceiling↔wall r<-0.3):    {h2['h2_verdict']}")
    print(f"  H3 (controller effect):       {h3['h3_verdict']}")
    print(f"  H4 (split-half r>0.6):        {h4['h4_verdict']}")

    results = {
        "experiment": EXP_ID,
        "title": TITLE,
        "n_events": int(len(events)),
        "n_patients": int(events["patient_id"].nunique()),
        "hypotheses": {"h1_heterogeneity": h1, "h2_wall_correlation": h2,
                       "h3_controller_effect": h3, "h4_temporal_stability": h4},
        "per_patient_ceilings": [{k: v for k, v in p.items() if k != "bin_stats"} for p in patient_ceilings],
        "wall_episodes": wall_episodes,
        "methodology": {
            "bg_floor": BG_FLOOR, "horizon_hours": 2.0, "iob_bins": IOB_BINS,
            "wall_threshold": WALL_BG_THRESHOLD, "wall_duration_hours": 2.0,
        },
    }

    out_path = EXP / "exp-2703_sc_ceiling_per_patient.json"
    out_path.write_text(json.dumps(results, indent=2, default=str))
    print(f"\nResults saved: {out_path}")
    return results


if __name__ == "__main__":
    main()
