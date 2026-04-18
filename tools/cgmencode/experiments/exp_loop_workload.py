#!/usr/bin/env python3
"""
exp_loop_workload.py — Loop Workload as Settings Adequacy Metric (EXP-2391–2396)

Extends overnight findings to full 24h analysis. Loop workload (how much the
loop deviates from scheduled basal) is proposed as a first-class metric for
settings assessment — replacing TIR which the loop already optimizes.

Experiments:
  EXP-2391: 24h loop workload characterization
  EXP-2392: Workload vs TIR correlation (does more work = better outcomes?)
  EXP-2393: Workload vs hypo risk (does more work = more danger?)
  EXP-2394: Workload decomposition by time period (overnight/morning/afternoon/evening)
  EXP-2395: Workload stability over time (trending better or worse?)
  EXP-2396: Workload-based settings adequacy score

Usage:
    PYTHONPATH=tools python tools/cgmencode/production/exp_loop_workload.py
    PYTHONPATH=tools python tools/cgmencode/production/exp_loop_workload.py --tiny
"""

import argparse
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=FutureWarning)

ROOT = Path(__file__).resolve().parents[3]
VIZ_DIR = ROOT / "visualizations" / "loop-workload"
RESULTS_DIR = ROOT / "externals" / "experiments"

PERIODS = {
    "overnight": (0, 6),
    "morning": (6, 12),
    "afternoon": (12, 18),
    "evening": (18, 24),
}


def load_data(tiny: bool = False) -> pd.DataFrame:
    if tiny:
        path = ROOT / "externals" / "ns-parquet-tiny" / "training" / "grid.parquet"
    else:
        path = ROOT / "externals" / "ns-parquet" / "training" / "grid.parquet"
    print(f"Loading {path}...")
    df = pd.read_parquet(path)
    df["time"] = pd.to_datetime(df["time"])
    df["hour"] = df["time"].dt.hour + df["time"].dt.minute / 60.0
    print(f"  {len(df):,} rows, {df['patient_id'].nunique()} patients\n")
    return df


def compute_workload_metrics(pdf: pd.DataFrame) -> dict | None:
    """Compute loop workload metrics for a patient dataframe."""
    if "actual_basal_rate" not in pdf.columns or "scheduled_basal_rate" not in pdf.columns:
        return None

    ab = pdf["actual_basal_rate"].values
    sb = pdf["scheduled_basal_rate"].values
    valid = ~np.isnan(ab) & ~np.isnan(sb) & (sb > 0.01) & (ab < 50)  # filter implausible

    if valid.sum() < 100:
        return None

    ratio = ab[valid] / sb[valid]

    # Workload metrics
    suspension_pct = float(100 * np.mean(ratio < 0.1))
    increase_pct = float(100 * np.mean(ratio > 1.5))
    deviation_mean = float(np.mean(np.abs(ratio - 1.0)))
    deviation_std = float(np.std(ratio))

    # Directional workload
    reduction_workload = float(np.mean(np.maximum(0, 1 - ratio)))  # how much less than scheduled
    increase_workload = float(np.mean(np.maximum(0, ratio - 1)))  # how much more than scheduled
    net_direction = "REDUCING" if reduction_workload > increase_workload else "INCREASING"

    # Total workload score (0-100 scale)
    # 0 = loop never deviates, 100 = loop always at extreme
    workload_score = min(100, float(100 * deviation_mean / 0.5))  # normalize: 0.5 deviation = 100%

    return {
        "n_samples": int(valid.sum()),
        "suspension_pct": suspension_pct,
        "increase_pct": increase_pct,
        "deviation_mean": deviation_mean,
        "deviation_std": deviation_std,
        "reduction_workload": reduction_workload,
        "increase_workload": increase_workload,
        "net_direction": net_direction,
        "workload_score": workload_score,
        "ratio_median": float(np.median(ratio)),
        "ratio_q10": float(np.percentile(ratio, 10)),
        "ratio_q90": float(np.percentile(ratio, 90)),
    }


def exp_2391_24h_workload(df: pd.DataFrame) -> dict:
    """EXP-2391: 24h loop workload characterization."""
    print("=" * 60)
    print("EXP-2391: 24h Loop Workload Characterization")
    print("=" * 60)

    results = {}
    for pid in sorted(df["patient_id"].unique()):
        pdf = df[df["patient_id"] == pid]
        metrics = compute_workload_metrics(pdf)
        if metrics is None:
            continue
        results[pid] = metrics
        print(f"  {pid}: workload={metrics['workload_score']:.0f}/100, "
              f"suspend {metrics['suspension_pct']:.0f}%, increase {metrics['increase_pct']:.0f}%, "
              f"direction={metrics['net_direction']}, ratio_median={metrics['ratio_median']:.2f}")
    return results


def exp_2392_workload_vs_tir(df: pd.DataFrame, workload: dict) -> dict:
    """EXP-2392: Does more loop work = better outcomes?"""
    print("\n" + "=" * 60)
    print("EXP-2392: Workload vs TIR Correlation")
    print("=" * 60)

    results = {}
    scores = []
    tirs = []

    for pid in sorted(df["patient_id"].unique()):
        w = workload.get(pid)
        if w is None:
            continue

        pdf = df[df["patient_id"] == pid]
        gluc = pdf["glucose"].dropna()
        if len(gluc) < 100:
            continue

        tir = float(100 * np.mean((gluc >= 70) & (gluc <= 180)))
        below70 = float(100 * np.mean(gluc < 70))
        above180 = float(100 * np.mean(gluc > 180))
        cv = float(gluc.std() / gluc.mean() * 100) if gluc.mean() > 0 else 0

        scores.append(w["workload_score"])
        tirs.append(tir)

        results[pid] = {
            "workload_score": w["workload_score"],
            "tir_pct": tir,
            "below70_pct": below70,
            "above180_pct": above180,
            "cv_pct": cv,
        }

    # Population correlation
    if len(scores) > 5:
        corr = float(np.corrcoef(scores, tirs)[0, 1])
    else:
        corr = 0

    results["_correlation"] = {
        "workload_vs_tir_r": corr,
        "interpretation": "positive" if corr > 0.3 else "negative" if corr < -0.3 else "no correlation",
    }

    print(f"\n  Workload vs TIR correlation: r = {corr:.3f}")
    if abs(corr) < 0.3:
        print("  → No significant correlation — workload is independent of outcomes")
    elif corr > 0:
        print("  → More work = better outcomes (loop compensation effective)")
    else:
        print("  → More work = worse outcomes (loop fighting losing battle)")

    return results


def exp_2393_workload_vs_hypo(df: pd.DataFrame, workload: dict) -> dict:
    """EXP-2393: Does more loop work = more hypo risk?"""
    print("\n" + "=" * 60)
    print("EXP-2393: Workload vs Hypo Risk")
    print("=" * 60)

    results = {}
    scores = []
    hypo_pcts = []

    for pid in sorted(df["patient_id"].unique()):
        w = workload.get(pid)
        if w is None:
            continue

        pdf = df[df["patient_id"] == pid]
        gluc = pdf["glucose"].dropna()
        if len(gluc) < 100:
            continue

        below70 = float(100 * np.mean(gluc < 70))
        below54 = float(100 * np.mean(gluc < 54))

        scores.append(w["workload_score"])
        hypo_pcts.append(below70)

        # Workload direction matters for hypo
        if w["net_direction"] == "REDUCING":
            hypo_risk = "HIGHER" if below70 > 5 else "MODERATE"
            mechanism = "Loop reduces basal → less insulin → but already had hypos?"
        else:
            hypo_risk = "LOWER" if below70 < 3 else "MODERATE"
            mechanism = "Loop increases basal → more insulin → hypo risk from increases"

        results[pid] = {
            "workload_score": w["workload_score"],
            "direction": w["net_direction"],
            "below70_pct": below70,
            "below54_pct": below54,
            "hypo_risk": hypo_risk,
        }
        print(f"  {pid}: workload={w['workload_score']:.0f}, "
              f"<70={below70:.1f}%, direction={w['net_direction']}, risk={hypo_risk}")

    if len(scores) > 5:
        corr = float(np.corrcoef(scores, hypo_pcts)[0, 1])
    else:
        corr = 0

    results["_correlation"] = {
        "workload_vs_hypo_r": corr,
    }
    print(f"\n  Workload vs hypo correlation: r = {corr:.3f}")

    return results


def exp_2394_period_workload(df: pd.DataFrame) -> dict:
    """EXP-2394: Workload decomposition by time period."""
    print("\n" + "=" * 60)
    print("EXP-2394: Workload by Time Period")
    print("=" * 60)

    results = {}
    for pid in sorted(df["patient_id"].unique()):
        pdf = df[df["patient_id"] == pid]
        period_metrics = {}

        for period, (start, end) in PERIODS.items():
            if start < end:
                mask = (pdf["hour"] >= start) & (pdf["hour"] < end)
            else:
                mask = (pdf["hour"] >= start) | (pdf["hour"] < end)

            period_data = pdf[mask]
            metrics = compute_workload_metrics(period_data)
            if metrics:
                period_metrics[period] = metrics

        if not period_metrics:
            continue

        results[pid] = period_metrics

        # Print summary
        scores = {p: m["workload_score"] for p, m in period_metrics.items()}
        worst = max(scores, key=scores.get) if scores else "N/A"
        best = min(scores, key=scores.get) if scores else "N/A"
        print(f"  {pid}: " + ", ".join(f"{p}={s:.0f}" for p, s in scores.items()) +
              f" (worst={worst}, best={best})")

    return results


def exp_2395_workload_stability(df: pd.DataFrame) -> dict:
    """EXP-2395: Is workload stable or trending?"""
    print("\n" + "=" * 60)
    print("EXP-2395: Workload Stability Over Time")
    print("=" * 60)

    results = {}
    for pid in sorted(df["patient_id"].unique()):
        pdf = df[df["patient_id"] == pid].sort_values("time")

        if "actual_basal_rate" not in pdf.columns or "scheduled_basal_rate" not in pdf.columns:
            continue

        ab = pdf["actual_basal_rate"].values
        sb = pdf["scheduled_basal_rate"].values
        valid = ~np.isnan(ab) & ~np.isnan(sb) & (sb > 0.01) & (ab < 50)

        if valid.sum() < 500:
            continue

        ratio = ab[valid] / sb[valid]
        deviation = np.abs(ratio - 1.0)

        # Split into weekly chunks
        n_chunks = min(12, len(deviation) // 2016)  # 2016 = 1 week at 5-min resolution
        if n_chunks < 3:
            continue

        chunk_size = len(deviation) // n_chunks
        weekly_scores = []
        for i in range(n_chunks):
            chunk = deviation[i * chunk_size:(i + 1) * chunk_size]
            weekly_scores.append(min(100, float(100 * np.mean(chunk) / 0.5)))

        # Trend: linear fit to weekly scores
        x = np.arange(len(weekly_scores))
        try:
            slope, intercept = np.polyfit(x, weekly_scores, 1)
        except (np.linalg.LinAlgError, ValueError):
            continue

        trend = "IMPROVING" if slope < -0.5 else "WORSENING" if slope > 0.5 else "STABLE"

        results[pid] = {
            "n_weeks": n_chunks,
            "weekly_scores": [float(s) for s in weekly_scores],
            "slope_per_week": float(slope),
            "trend": trend,
            "initial_score": float(weekly_scores[0]),
            "final_score": float(weekly_scores[-1]),
        }
        print(f"  {pid}: {trend} ({weekly_scores[0]:.0f} → {weekly_scores[-1]:.0f}, "
              f"slope {slope:+.1f}/week, {n_chunks} weeks)")

    return results


def exp_2396_adequacy_score(workload: dict, period_workload: dict,
                            stability: dict) -> dict:
    """
    EXP-2396: Composite settings adequacy score.

    Combines:
    - Overall workload (lower = better settings)
    - Period balance (similar workload across periods = better)
    - Stability (improving or stable = better than worsening)

    Score: 0-100, where 100 = perfectly calibrated settings.
    """
    print("\n" + "=" * 60)
    print("EXP-2396: Settings Adequacy Score")
    print("=" * 60)

    results = {}
    for pid in workload:
        w = workload[pid]
        pw = period_workload.get(pid, {})
        st = stability.get(pid, {})

        # Component 1: Workload (inverted — lower workload = higher score)
        workload_component = max(0, 100 - w["workload_score"])

        # Component 2: Balance (low variance across periods = good)
        if pw:
            period_scores = [pw[p]["workload_score"] for p in pw if isinstance(pw[p], dict)]
            if len(period_scores) > 1:
                balance = max(0, 100 - float(np.std(period_scores)))
            else:
                balance = 50
        else:
            balance = 50

        # Component 3: Stability (not worsening = good)
        if st:
            slope = st.get("slope_per_week", 0)
            if slope < -1:
                stability_score = 90  # improving
            elif slope > 1:
                stability_score = 30  # worsening
            else:
                stability_score = 70  # stable
        else:
            stability_score = 50  # unknown

        # Composite: weighted average
        adequacy = 0.5 * workload_component + 0.3 * balance + 0.2 * stability_score

        grade = ("A" if adequacy >= 80 else "B" if adequacy >= 65 else
                 "C" if adequacy >= 50 else "D" if adequacy >= 35 else "F")

        results[pid] = {
            "adequacy_score": float(adequacy),
            "grade": grade,
            "workload_component": float(workload_component),
            "balance_component": float(balance),
            "stability_component": float(stability_score),
        }
        print(f"  {pid}: {grade} ({adequacy:.0f}/100) — "
              f"workload={workload_component:.0f}, "
              f"balance={balance:.0f}, stability={stability_score:.0f}")

    # Population stats
    if results:
        scores = [r["adequacy_score"] for r in results.values()]
        grades = [r["grade"] for r in results.values()]
        print(f"\n  Population: mean={np.mean(scores):.0f}/100, "
              f"A={grades.count('A')}, B={grades.count('B')}, "
              f"C={grades.count('C')}, D={grades.count('D')}, F={grades.count('F')}")

    return results


def generate_visualizations(workload: dict, period_workload: dict,
                            tir_corr: dict, adequacy: dict):
    """Generate loop workload figures."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not available")
        return

    VIZ_DIR.mkdir(parents=True, exist_ok=True)
    patients = sorted([p for p in workload if not p.startswith("_")])

    # --- Figure 1: Workload scores + adequacy grades ---
    fig, axes = plt.subplots(1, 3, figsize=(18, 6))

    # 1a: Workload scores
    scores = [workload[p]["workload_score"] for p in patients]
    colors = ["red" if s > 70 else "orange" if s > 50 else "green" for s in scores]
    axes[0].barh(range(len(patients)), scores, color=colors)
    axes[0].set_yticks(range(len(patients)))
    axes[0].set_yticklabels([p[:12] for p in patients], fontsize=8)
    axes[0].axvline(50, color="orange", linewidth=0.5, linestyle="--")
    axes[0].axvline(70, color="red", linewidth=0.5, linestyle="--")
    axes[0].set_xlabel("Workload Score (0-100)")
    axes[0].set_title("24h Loop Workload")
    axes[0].set_xlim(0, 100)

    # 1b: Period workload heatmap
    period_data = []
    for p in patients:
        pw = period_workload.get(p, {})
        row = [pw.get(per, {}).get("workload_score", 0) if isinstance(pw.get(per), dict) else 0
               for per in ["overnight", "morning", "afternoon", "evening"]]
        period_data.append(row)

    if period_data:
        im = axes[1].imshow(period_data, aspect="auto", cmap="RdYlGn_r", vmin=0, vmax=100)
        axes[1].set_yticks(range(len(patients)))
        axes[1].set_yticklabels([p[:12] for p in patients], fontsize=8)
        axes[1].set_xticks(range(4))
        axes[1].set_xticklabels(["Night", "Morning", "Afternoon", "Evening"], fontsize=9)
        axes[1].set_title("Workload by Period")
        plt.colorbar(im, ax=axes[1], shrink=0.8, label="Workload Score")

    # 1c: Adequacy grades
    if adequacy:
        adeq_scores = [adequacy.get(p, {}).get("adequacy_score", 0) for p in patients]
        grade_colors = {"A": "green", "B": "lightgreen", "C": "orange", "D": "red", "F": "darkred"}
        colors_a = [grade_colors.get(adequacy.get(p, {}).get("grade", "F"), "gray") for p in patients]
        axes[2].barh(range(len(patients)), adeq_scores, color=colors_a)
        axes[2].set_yticks(range(len(patients)))
        axes[2].set_yticklabels([p[:12] for p in patients], fontsize=8)
        axes[2].set_xlabel("Adequacy Score (0-100)")
        axes[2].set_title("Settings Adequacy Grade")
        axes[2].set_xlim(0, 100)
        # Add grade labels
        for i, p in enumerate(patients):
            grade = adequacy.get(p, {}).get("grade", "?")
            axes[2].text(adeq_scores[i] + 1, i, grade, va="center", fontsize=8, fontweight="bold")

    plt.tight_layout()
    fig.savefig(VIZ_DIR / "fig1_workload_overview.png", dpi=150)
    plt.close()
    print(f"  Saved fig1_workload_overview.png")

    # --- Figure 2: Workload vs outcomes scatter ---
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    valid_patients = [p for p in patients if p in tir_corr and not p.startswith("_")]
    if valid_patients:
        ws = [tir_corr[p]["workload_score"] for p in valid_patients]
        tirs = [tir_corr[p]["tir_pct"] for p in valid_patients]
        hypos = [tir_corr[p]["below70_pct"] for p in valid_patients]

        axes[0].scatter(ws, tirs, c="steelblue", s=60, edgecolors="black", zorder=5)
        for i, p in enumerate(valid_patients):
            axes[0].annotate(p[:6], (ws[i], tirs[i]), fontsize=6)
        corr_tir = tir_corr.get("_correlation", {}).get("workload_vs_tir_r", 0)
        axes[0].set_xlabel("Loop Workload Score")
        axes[0].set_ylabel("TIR (%)")
        axes[0].set_title(f"Workload vs TIR (r={corr_tir:.3f})")

        axes[1].scatter(ws, hypos, c="coral", s=60, edgecolors="black", zorder=5)
        for i, p in enumerate(valid_patients):
            axes[1].annotate(p[:6], (ws[i], hypos[i]), fontsize=6)
        axes[1].set_xlabel("Loop Workload Score")
        axes[1].set_ylabel("Time Below 70 (%)")
        axes[1].set_title("Workload vs Hypo Risk")

    plt.tight_layout()
    fig.savefig(VIZ_DIR / "fig2_workload_vs_outcomes.png", dpi=150)
    plt.close()
    print(f"  Saved fig2_workload_vs_outcomes.png")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tiny", action="store_true")
    args = parser.parse_args()

    df = load_data(tiny=args.tiny)

    workload = exp_2391_24h_workload(df)
    tir_corr = exp_2392_workload_vs_tir(df, workload)
    hypo_corr = exp_2393_workload_vs_hypo(df, workload)
    period = exp_2394_period_workload(df)
    stability = exp_2395_workload_stability(df)
    adequacy = exp_2396_adequacy_score(workload, period, stability)

    print("\nGenerating visualizations...")
    generate_visualizations(workload, period, tir_corr, adequacy)

    all_results = {
        "exp_2391": workload,
        "exp_2392": tir_corr,
        "exp_2393": hypo_corr,
        "exp_2394": period,
        "exp_2395": stability,
        "exp_2396": adequacy,
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / "exp-2391-2396_loop_workload.json"
    with open(out_path, "w") as f:
        def convert(obj):
            if isinstance(obj, np.ndarray): return obj.tolist()
            if isinstance(obj, (np.float64, np.float32)): return float(obj)
            if isinstance(obj, (np.int64, np.int32)): return int(obj)
            if isinstance(obj, (np.bool_,)): return bool(obj)
            raise TypeError(f"Cannot serialize {type(obj)}")
        json.dump(all_results, f, indent=2, default=convert)

    print(f"\nResults saved to {out_path}")


if __name__ == "__main__":
    main()
