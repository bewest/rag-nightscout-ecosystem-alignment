#!/usr/bin/env python3
"""EXP-2724: Basal Rate Circadian Extraction — EGP Variation Matters More for Basal Than ISF

INSIGHT:
  EXP-2719 showed deviation (non-insulin glucose change) has circadian structure:
  night peaks (168.6) vs day troughs (152.3) — ~11% variation.  EXP-2721 showed
  circadian ISF (2.87× ratio) is real but does NOT improve ISF prediction.

  Hypothesis: circadian EGP variation is MORE relevant for basal rates, since
  basal insulin directly offsets endogenous glucose production (EGP).  If EGP is
  higher at night, basal should be higher at night to match.

METHOD:
  Instead of correction events (BG≥180 with bolus), identify "steady-state"
  fasting periods where:
    - No bolus in prior 2 h and no carbs in prior 3 h
    - IOB is relatively stable (within ±0.3 U of per-patient median)
    - Glucose drift over the next 1 h ≈ EGP − basal insulin effect
  Positive drift → basal too low; negative drift → basal too high.

HYPOTHESES:
  H1: Glucose drift has significant circadian structure (KW p<0.001)
  H2: Night drift > day drift (MWU p<0.01)
  H3: Circadian drift ratio exceeds 1.5× (cf. ISF ratio 2.87×)
  H4: Drift variability correlates with glucose variability (r>0.3)
"""
from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy import stats

warnings.filterwarnings("ignore", category=FutureWarning)

# ── Constants ────────────────────────────────────────────────────────

EXP_ID = "2724"
TITLE = "Basal Rate Circadian Extraction — EGP Variation Matters More for Basal Than ISF"

GRID = Path("externals/ns-parquet/training/grid.parquet")
DS = Path("externals/ns-parquet/training/devicestatus.parquet")
MANIFEST = Path("externals/experiments/autoprepare-qualified.json")
RESULTS_DIR = Path("externals/experiments")
VIZ_DIR = Path("visualizations/basal-circadian")
OUT_JSON = RESULTS_DIR / f"exp-{EXP_ID}_basal_circadian.json"

TIME_BLOCKS = [(0, 4), (4, 8), (8, 12), (12, 16), (16, 20), (20, 24)]
BLOCK_LABELS = ["00-04", "04-08", "08-12", "12-16", "16-20", "20-24"]

FASTING_BOLUS_WINDOW = 24   # 2 h = 24 steps at 5 min
FASTING_CARB_WINDOW = 36    # 3 h = 36 steps
DRIFT_HORIZON = 12          # 1 h = 12 steps
MIN_EVENTS_PER_BLOCK = 10
DRIFT_ADEQUATE_BAND = 5.0   # ±5 mg/dL/h considered "adequate"


# ── Data Loading ─────────────────────────────────────────────────────

def load_data() -> pd.DataFrame:
    """Load grid parquet, filter to qualified patients, attach controller."""
    grid = pd.read_parquet(GRID)
    ds = pd.read_parquet(DS)
    manifest = json.loads(MANIFEST.read_text())
    qual = manifest["qualified_patients"]
    ctrl_map = ds.groupby("patient_id")["controller"].first().to_dict()
    grid = grid[grid["patient_id"].isin(qual)].copy()
    grid["controller"] = grid["patient_id"].map(ctrl_map).fillna("unknown")
    grid = grid.sort_values(["patient_id", "time"]).reset_index(drop=True)
    return grid


# ── Steady-State Extraction ─────────────────────────────────────────

def extract_steady_periods(
    patient_df: pd.DataFrame,
) -> List[Dict[str, Any]]:
    """Find fasting steady-state periods for a single patient.

    Returns list of dicts with keys: hour, block, glucose_drift,
    scheduled_basal, glucose_now.
    """
    glucose = patient_df["glucose"].values
    bolus = patient_df["bolus"].values if "bolus" in patient_df.columns else None
    carbs = patient_df["carbs"].values if "carbs" in patient_df.columns else None
    iob = patient_df["iob"].values if "iob" in patient_df.columns else None
    net_basal = (
        patient_df["net_basal"].values
        if "net_basal" in patient_df.columns
        else None
    )
    times = pd.to_datetime(patient_df["time"].values)

    n = len(glucose)
    if n < DRIFT_HORIZON + FASTING_CARB_WINDOW:
        return []

    # Pre-compute IOB median for stability check
    iob_median = float(np.nanmedian(iob)) if iob is not None else 0.0

    periods: List[Dict[str, Any]] = []
    for i in range(FASTING_CARB_WINDOW, n - DRIFT_HORIZON):
        # Valid glucose at start and end
        g_now = glucose[i]
        g_future = glucose[i + DRIFT_HORIZON]
        if np.isnan(g_now) or np.isnan(g_future):
            continue

        # No bolus in prior 2 h
        if bolus is not None:
            bolus_sum = np.nansum(bolus[max(0, i - FASTING_BOLUS_WINDOW) : i])
            if bolus_sum >= 0.05:
                continue
        # No carbs in prior 3 h
        if carbs is not None:
            carb_sum = np.nansum(carbs[max(0, i - FASTING_CARB_WINDOW) : i])
            if carb_sum >= 1.0:
                continue
        # IOB stability (within ±0.3 U of median)
        if iob is not None and not np.isnan(iob[i]):
            if abs(float(iob[i]) - iob_median) > 0.3:
                continue

        drift = float(g_future - g_now)  # mg/dL per hour
        hour = int(times[i].hour)
        block_idx = min(hour // 4, 5)

        rec: Dict[str, Any] = {
            "hour": hour,
            "block": BLOCK_LABELS[block_idx],
            "block_idx": block_idx,
            "glucose_drift": drift,
            "glucose_now": float(g_now),
            "scheduled_basal": float(net_basal[i]) if net_basal is not None and not np.isnan(net_basal[i]) else 0.0,
        }
        periods.append(rec)

    return periods


# ── Per-Patient Analysis ─────────────────────────────────────────────

def analyze_patient(
    pid: str,
    patient_df: pd.DataFrame,
) -> Optional[Dict[str, Any]]:
    """Compute per-block drift statistics for one patient."""
    periods = extract_steady_periods(patient_df)
    if len(periods) < MIN_EVENTS_PER_BLOCK:
        return None

    pdf = pd.DataFrame(periods)
    glucose_col = patient_df["glucose"].dropna()
    patient_glucose_sd = float(glucose_col.std()) if len(glucose_col) > 1 else np.nan

    block_stats: List[Dict[str, Any]] = []
    for idx, label in enumerate(BLOCK_LABELS):
        bdf = pdf[pdf["block_idx"] == idx]
        n_b = len(bdf)
        if n_b < MIN_EVENTS_PER_BLOCK:
            block_stats.append({
                "block": label,
                "n_steady_periods": n_b,
                "median_drift": np.nan,
                "drift_direction": "insufficient",
                "scheduled_basal": np.nan,
            })
            continue
        med_drift = float(bdf["glucose_drift"].median())
        med_basal = float(bdf["scheduled_basal"].median())
        direction = (
            "high" if med_drift > DRIFT_ADEQUATE_BAND
            else "low" if med_drift < -DRIFT_ADEQUATE_BAND
            else "adequate"
        )
        block_stats.append({
            "block": label,
            "n_steady_periods": n_b,
            "median_drift": round(med_drift, 2),
            "drift_direction": direction,
            "scheduled_basal": round(med_basal, 3),
        })

    # Per-patient drift SD (across block medians, excluding NaN blocks)
    valid_medians = [b["median_drift"] for b in block_stats if not np.isnan(b["median_drift"])]
    drift_sd = float(np.std(valid_medians)) if len(valid_medians) >= 2 else np.nan

    return {
        "patient_id": pid,
        "n_steady_periods": len(periods),
        "n_valid_blocks": sum(1 for b in block_stats if not np.isnan(b["median_drift"])),
        "block_stats": block_stats,
        "drift_sd": round(drift_sd, 3) if not np.isnan(drift_sd) else None,
        "glucose_sd": round(patient_glucose_sd, 2) if not np.isnan(patient_glucose_sd) else None,
        "controller": patient_df["controller"].iloc[0] if "controller" in patient_df.columns else "unknown",
    }


# ── Hypothesis Testing ───────────────────────────────────────────────

def test_hypotheses(
    patient_results: List[Dict[str, Any]],
    all_periods: pd.DataFrame,
) -> Dict[str, Any]:
    """Run all four hypothesis tests and return structured results."""
    hypotheses: Dict[str, Any] = {}

    # ── H1: Circadian structure in drift (Kruskal-Wallis) ──
    groups = [
        all_periods.loc[all_periods["block_idx"] == idx, "glucose_drift"].dropna().values
        for idx in range(6)
    ]
    groups_nonempty = [g for g in groups if len(g) >= MIN_EVENTS_PER_BLOCK]
    if len(groups_nonempty) >= 3:
        kw_stat, kw_p = stats.kruskal(*groups_nonempty)
        h1_pass = bool(kw_p < 0.001)
    else:
        kw_stat, kw_p, h1_pass = np.nan, np.nan, False

    block_medians = []
    for idx, label in enumerate(BLOCK_LABELS):
        g = groups[idx] if idx < len(groups) else np.array([])
        med = float(np.median(g)) if len(g) > 0 else np.nan
        block_medians.append({"block": label, "n": int(len(g)), "median_drift": round(med, 2) if not np.isnan(med) else None})

    hypotheses["H1"] = {
        "description": "Glucose drift has significant circadian structure",
        "verdict": "PASS" if h1_pass else "FAIL",
        "kw_statistic": round(float(kw_stat), 2) if not np.isnan(kw_stat) else None,
        "kw_p_value": float(kw_p) if not np.isnan(kw_p) else None,
        "block_medians": block_medians,
    }

    # ── H2: Night drift > day drift ──
    night_blocks = {0, 5}  # 00-04, 20-24
    day_blocks = {2, 3}    # 08-12, 12-16
    night_vals = all_periods.loc[all_periods["block_idx"].isin(night_blocks), "glucose_drift"].dropna().values
    day_vals = all_periods.loc[all_periods["block_idx"].isin(day_blocks), "glucose_drift"].dropna().values

    if len(night_vals) >= MIN_EVENTS_PER_BLOCK and len(day_vals) >= MIN_EVENTS_PER_BLOCK:
        mw_stat, mw_p = stats.mannwhitneyu(night_vals, day_vals, alternative="greater")
        night_med = float(np.median(night_vals))
        day_med = float(np.median(day_vals))
        h2_pass = bool(night_med > day_med and mw_p < 0.01)
    else:
        mw_stat, mw_p = np.nan, np.nan
        night_med, day_med = np.nan, np.nan
        h2_pass = False

    hypotheses["H2"] = {
        "description": "Night drift is higher than day drift",
        "verdict": "PASS" if h2_pass else "FAIL",
        "night_median": round(night_med, 2) if not np.isnan(night_med) else None,
        "day_median": round(day_med, 2) if not np.isnan(day_med) else None,
        "mw_statistic": round(float(mw_stat), 2) if not np.isnan(mw_stat) else None,
        "mw_p_value": float(mw_p) if not np.isnan(mw_p) else None,
        "n_night": int(len(night_vals)),
        "n_day": int(len(day_vals)),
    }

    # ── H3: Circadian drift ratio > 1.5× ──
    valid_block_meds = [b["median_drift"] for b in block_medians if b["median_drift"] is not None]
    if len(valid_block_meds) >= 2:
        abs_meds = [abs(m) for m in valid_block_meds]
        max_abs = max(abs_meds)
        min_abs = min(abs_meds)
        circadian_ratio = max_abs / min_abs if min_abs > 0 else np.inf
        h3_pass = bool(circadian_ratio > 1.5)
    else:
        circadian_ratio = np.nan
        h3_pass = False

    hypotheses["H3"] = {
        "description": "Circadian drift ratio exceeds 1.5× (cf. ISF ratio 2.87×)",
        "verdict": "PASS" if h3_pass else "FAIL",
        "circadian_ratio": round(float(circadian_ratio), 2) if not np.isnan(circadian_ratio) and not np.isinf(circadian_ratio) else None,
        "isf_circadian_ratio_ref": 2.87,
    }

    # ── H4: Drift SD correlates with glucose SD (r > 0.3) ──
    drift_sds = []
    glucose_sds = []
    for pr in patient_results:
        if pr["drift_sd"] is not None and pr["glucose_sd"] is not None:
            drift_sds.append(pr["drift_sd"])
            glucose_sds.append(pr["glucose_sd"])

    if len(drift_sds) >= 5:
        r_val, r_p = stats.pearsonr(drift_sds, glucose_sds)
        h4_pass = bool(abs(r_val) > 0.3)
    else:
        r_val, r_p = np.nan, np.nan
        h4_pass = False

    hypotheses["H4"] = {
        "description": "Drift variability correlates with glucose variability (r>0.3)",
        "verdict": "PASS" if h4_pass else "FAIL",
        "r": round(float(r_val), 4) if not np.isnan(r_val) else None,
        "r_p_value": float(r_p) if not np.isnan(r_p) else None,
        "n_patients": len(drift_sds),
    }

    return hypotheses


# ── Visualization ────────────────────────────────────────────────────

def create_dashboard(
    patient_results: List[Dict[str, Any]],
    all_periods: pd.DataFrame,
    hypotheses: Dict[str, Any],
) -> None:
    """Create 2×2 summary dashboard."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.colors as mcolors
    except ImportError:
        print("  matplotlib not available — skipping dashboard")
        return

    VIZ_DIR.mkdir(parents=True, exist_ok=True)

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle(
        f"EXP-{EXP_ID}: Circadian Basal Assessment — EGP Variation Matters More for Basal Than ISF",
        fontsize=12,
        fontweight="bold",
    )

    # ── Panel 1 (top-left): Circadian drift heatmap ──
    ax1 = axes[0, 0]
    sorted_results = sorted(patient_results, key=lambda r: r["controller"])
    matrix = []
    ylabels = []
    for pr in sorted_results:
        row = []
        for bs in pr["block_stats"]:
            row.append(bs["median_drift"] if not np.isnan(bs.get("median_drift", np.nan) or np.nan) else 0.0)
        matrix.append(row)
        ylabels.append(f"{pr['patient_id'][:8]} ({pr['controller'][:4]})")

    if matrix:
        mat = np.array(matrix)
        vmax = max(abs(np.nanmin(mat)), abs(np.nanmax(mat)), 1.0)
        im = ax1.imshow(mat, aspect="auto", cmap="RdBu_r", vmin=-vmax, vmax=vmax)
        ax1.set_xticks(range(6))
        ax1.set_xticklabels(BLOCK_LABELS, fontsize=7)
        ax1.set_yticks(range(len(ylabels)))
        ax1.set_yticklabels(ylabels, fontsize=5)
        fig.colorbar(im, ax=ax1, label="mg/dL/h drift", shrink=0.8)
    ax1.set_title(f"Circadian Drift Heatmap [H1 {hypotheses['H1']['verdict']}]", fontsize=9)

    # ── Panel 2 (top-right): Population-level circadian drift ──
    ax2 = axes[0, 1]
    box_data = []
    box_labels_used = []
    block_ns = []
    block_meds = []
    for idx, label in enumerate(BLOCK_LABELS):
        vals = all_periods.loc[all_periods["block_idx"] == idx, "glucose_drift"].dropna().values
        if len(vals) > 0:
            box_data.append(vals)
            box_labels_used.append(label)
            block_ns.append(len(vals))
            block_meds.append(float(np.median(vals)))

    if box_data:
        bp = ax2.boxplot(box_data, patch_artist=True, showfliers=False)
        for patch in bp["boxes"]:
            patch.set_facecolor("#8ecae6")
        ax2.set_xticklabels(box_labels_used, fontsize=8)
        ax2.axhline(0, color="black", linewidth=0.8, linestyle="--", label="perfect basal")
        for j, (n, med) in enumerate(zip(block_ns, block_meds)):
            ax2.annotate(
                f"n={n}\nmed={med:.1f}",
                xy=(j + 1, med),
                fontsize=5,
                ha="center",
                va="bottom",
            )
    ax2.set_ylabel("Glucose drift (mg/dL/h)")
    ax2.set_title(f"Population Circadian Drift [H2 {hypotheses['H2']['verdict']}]", fontsize=9)

    # ── Panel 3 (bottom-left): Night vs day drift per patient ──
    ax3 = axes[1, 0]
    night_blocks = {0, 5}
    day_blocks = {2, 3}
    ctrl_colors = {"loop": "#1f77b4", "openaps": "#ff7f0e", "trio": "#2ca02c", "unknown": "#999999"}
    for pr in patient_results:
        bs = pr["block_stats"]
        night_meds = [bs[i]["median_drift"] for i in night_blocks if not np.isnan(bs[i].get("median_drift", np.nan) or np.nan)]
        day_meds = [bs[i]["median_drift"] for i in day_blocks if not np.isnan(bs[i].get("median_drift", np.nan) or np.nan)]
        if night_meds and day_meds:
            nx = float(np.mean(night_meds))
            dy = float(np.mean(day_meds))
            c = ctrl_colors.get(pr["controller"], "#999999")
            ax3.scatter(nx, dy, c=c, s=30, alpha=0.7, edgecolors="k", linewidths=0.3)

    lim_range = ax3.get_xlim() + ax3.get_ylim()
    lo = min(lim_range) - 2
    hi = max(lim_range) + 2
    ax3.plot([lo, hi], [lo, hi], "k--", linewidth=0.6, alpha=0.5, label="equal")
    ax3.set_xlabel("Night drift (mg/dL/h)")
    ax3.set_ylabel("Day drift (mg/dL/h)")
    # Legend for controllers
    for ctrl, col in ctrl_colors.items():
        ax3.scatter([], [], c=col, label=ctrl, s=20)
    ax3.legend(fontsize=6, loc="upper left")
    ax3.set_title("Night vs Day Drift per Patient", fontsize=9)

    # ── Panel 4 (bottom-right): Drift SD vs glucose SD ──
    ax4 = axes[1, 1]
    drift_sds = []
    glucose_sds = []
    pt_labels = []
    for pr in patient_results:
        if pr["drift_sd"] is not None and pr["glucose_sd"] is not None:
            drift_sds.append(pr["drift_sd"])
            glucose_sds.append(pr["glucose_sd"])
            pt_labels.append(pr["patient_id"][:8])

    if len(drift_sds) >= 3:
        ax4.scatter(drift_sds, glucose_sds, c="#2ca02c", s=30, alpha=0.7, edgecolors="k", linewidths=0.3)
        for x, y, lbl in zip(drift_sds, glucose_sds, pt_labels):
            ax4.annotate(lbl, (x, y), fontsize=4, alpha=0.6)
        # Fit line
        slope, intercept, r_val, _, _ = stats.linregress(drift_sds, glucose_sds)
        xs = np.linspace(min(drift_sds), max(drift_sds), 50)
        ax4.plot(xs, slope * xs + intercept, "r-", linewidth=1, alpha=0.7)
        ax4.annotate(f"r²={r_val**2:.3f}", xy=(0.05, 0.92), xycoords="axes fraction", fontsize=8, color="red")

    ax4.set_xlabel("Per-patient drift SD (mg/dL/h)")
    ax4.set_ylabel("Glucose SD (mg/dL)")
    ax4.set_title(f"Drift Variability vs Glucose Variability [H4 {hypotheses['H4']['verdict']}]", fontsize=9)

    plt.tight_layout(rect=[0, 0, 1, 0.95])
    out_path = VIZ_DIR / "basal_circadian.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Dashboard saved: {out_path}")


# ── Main ─────────────────────────────────────────────────────────────

def main() -> None:
    print(f"{'=' * 70}")
    print(f"EXP-{EXP_ID}: {TITLE}")
    print(f"{'=' * 70}")

    # ── Load data ──
    print("\nLoading data...")
    grid = load_data()
    n_patients = grid["patient_id"].nunique()
    print(f"  {len(grid):,} rows, {n_patients} patients")

    # ── Extract steady-state periods ──
    print("\nExtracting steady-state fasting periods...")
    patient_results: List[Dict[str, Any]] = []
    all_period_rows: List[Dict[str, Any]] = []

    for pid, pdf in grid.groupby("patient_id"):
        result = analyze_patient(str(pid), pdf)
        if result is not None:
            patient_results.append(result)
            for p in extract_steady_periods(pdf):
                p["patient_id"] = str(pid)
                all_period_rows.append(p)

    all_periods = pd.DataFrame(all_period_rows) if all_period_rows else pd.DataFrame()
    print(f"  {len(patient_results)} patients with sufficient steady-state data")
    print(f"  {len(all_periods):,} total steady-state periods")

    if len(patient_results) == 0 or all_periods.empty:
        print("ERROR: No steady-state periods found — check data columns.")
        sys.exit(1)

    # ── Per-patient × per-block drift table ──
    print(f"\n{'=' * 70}")
    print("PER-PATIENT × PER-BLOCK DRIFT TABLE")
    print(f"{'=' * 70}")
    header = f"  {'Patient':<14} {'Ctrl':<6}"
    for label in BLOCK_LABELS:
        header += f" {label:>8}"
    header += f" {'DriftSD':>8}"
    print(header)
    print(f"  {'-' * (14 + 6 + 8 * 6 + 8 + 6)}")

    for pr in sorted(patient_results, key=lambda r: r["controller"]):
        row = f"  {pr['patient_id'][:12]:<14} {pr['controller'][:5]:<6}"
        for bs in pr["block_stats"]:
            val = bs["median_drift"]
            if val is not None and not np.isnan(val):
                row += f" {val:>+7.1f} "
            else:
                row += f" {'---':>7} "
        ds = pr["drift_sd"]
        row += f" {ds:>7.2f}" if ds is not None else f" {'---':>7}"
        print(row)

    # ── Hypothesis testing ──
    print(f"\n{'=' * 70}")
    print("HYPOTHESIS TESTING")
    print(f"{'=' * 70}")

    hypotheses = test_hypotheses(patient_results, all_periods)

    # H1
    h1 = hypotheses["H1"]
    print(f"\n── H1: {h1['description']} ──")
    print(f"  Kruskal-Wallis H = {h1['kw_statistic']}, p = {h1['kw_p_value']:.2e}" if h1["kw_p_value"] is not None else "  Insufficient data")
    for bm in h1["block_medians"]:
        print(f"    {bm['block']}: median_drift = {bm['median_drift']}  (n={bm['n']})")
    print(f"  → H1 verdict: {h1['verdict']}")

    # H2
    h2 = hypotheses["H2"]
    print(f"\n── H2: {h2['description']} ──")
    print(f"  Night median = {h2['night_median']}  (n={h2['n_night']})")
    print(f"  Day median   = {h2['day_median']}  (n={h2['n_day']})")
    if h2["mw_p_value"] is not None:
        print(f"  Mann-Whitney U = {h2['mw_statistic']}, p = {h2['mw_p_value']:.2e}")
    print(f"  → H2 verdict: {h2['verdict']}")

    # H3
    h3 = hypotheses["H3"]
    print(f"\n── H3: {h3['description']} ──")
    print(f"  Circadian drift ratio = {h3['circadian_ratio']}")
    print(f"  ISF circadian ratio (ref) = {h3['isf_circadian_ratio_ref']}")
    print(f"  → H3 verdict: {h3['verdict']}")

    # H4
    h4 = hypotheses["H4"]
    print(f"\n── H4: {h4['description']} ──")
    print(f"  Pearson r = {h4['r']}, p = {h4['r_p_value']:.2e}" if h4["r"] is not None else "  Insufficient data")
    print(f"  n_patients = {h4['n_patients']}")
    print(f"  → H4 verdict: {h4['verdict']}")

    # ── Summary verdict ──
    verdicts = {k: v["verdict"] for k, v in hypotheses.items()}
    print(f"\nVerdict: H1={verdicts['H1']} H2={verdicts['H2']} H3={verdicts['H3']} H4={verdicts['H4']}")

    # ── Save results ──
    output: Dict[str, Any] = {
        "experiment_id": EXP_ID,
        "title": TITLE,
        "n_patients": len(patient_results),
        "n_steady_periods": len(all_periods),
        "controllers": (
            all_periods.merge(
                pd.DataFrame(patient_results)[["patient_id", "controller"]],
                on="patient_id",
                how="left",
            )["controller"]
            .value_counts()
            .to_dict()
            if "patient_id" in all_periods.columns
            else {}
        ),
        "hypotheses": hypotheses,
        "verdict_summary": verdicts,
        "patient_results": patient_results,
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nResults saved to {OUT_JSON}")

    # ── Visualization ──
    print("\nGenerating dashboard...")
    create_dashboard(patient_results, all_periods, hypotheses)

    print(f"\n{'=' * 70}")
    print("EXP-2724 complete.")


if __name__ == "__main__":
    main()
