"""EXP-2880 — Pre-nadir BG trajectory by time-of-day.

EXP-2879 established that counter-regulation (recovery side) is TOD-
invariant in AID users because basal profiles compensate circadian
hormones pre-hypo. This experiment tests the mirror question: does
the *pre-hypo descent* show TOD structure?

Hypotheses:
  A) Dawn EGP amplification: pre-hypo descent is SLOWER at dawn
     (less negative slope) — EGP opposes insulin-driven descent.
  B) AID basal over-delivery at dawn: pre-hypo descent is FASTER at
     dawn — if basal profiles are mis-calibrated to compensate
     dawn phenomenon they may over-deliver when dawn is milder.
  C) Null: AID basal profile is well-tuned and pre-hypo descent is
     TOD-invariant, paralleling EXP-2879.

Method:
  1. Reuse EXP-2875 event detection to get hypo event indices + times.
  2. For each event, compute pre_descent_slope = (bg_nadir - bg_60min_before) / 60
     (mg/dL/min; negative = descent).
  3. Stratify by TOD band; compare descent slopes (not intercepts this
     time — raw descent rate is the observable).
  4. Per-patient morning vs night descent-rate difference.

Output: externals/experiments/exp-2880_prenadir.parquet + summary + figure.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.cgmencode.exp_counter_regulation_2875 import (  # noqa: E402
    detect_hypo_recovery_events,
)

GRID = ROOT / "externals/ns-parquet/training/grid.parquet"
OUT_EVENTS = ROOT / "externals/experiments/exp-2880_prenadir_events.parquet"
OUT_SUMMARY = ROOT / "externals/experiments/exp-2880_prenadir_summary.json"
OUT_FIG = ROOT / "docs/60-research/figures/exp-2880_prenadir.png"

TOD_BINS = [
    ("night", 0, 6),
    ("morning", 6, 12),
    ("afternoon", 12, 18),
    ("evening", 18, 24),
]

PRE_WINDOW_MIN = 60  # look back this far from nadir


def classify_tod(hour: int) -> str:
    for name, lo, hi in TOD_BINS:
        if lo <= hour < hi:
            return name
    return "unknown"


def annotate_pre_nadir(g_pat: pd.DataFrame, ev: dict) -> dict | None:
    """Compute pre-nadir descent slope, pre-window insulin context, TOD."""
    nadir = ev["nadir_idx"]
    n = len(g_pat)
    cells_back = PRE_WINDOW_MIN // 5
    start = nadir - cells_back
    if start < 0:
        return None

    bg_nadir = float(g_pat["glucose"].iloc[nadir])
    bg_start = float(g_pat["glucose"].iloc[start])
    if np.isnan(bg_nadir) or np.isnan(bg_start):
        return None

    # Reject if any carbs/bolus in the pre-window (natural descent, not post-meal)
    pre_slice = g_pat.iloc[start:nadir + 1]
    if pre_slice["carbs"].fillna(0).sum() > 0:
        return None

    descent_slope = (bg_nadir - bg_start) / PRE_WINDOW_MIN  # mg/dL/min, negative

    # Pre-window insulin context
    iob_start = float(pre_slice["iob"].iloc[0])
    iob_nadir = float(pre_slice["iob"].iloc[-1])
    iob_delta = iob_start - iob_nadir if not (np.isnan(iob_start) or np.isnan(iob_nadir)) else np.nan

    actual_basal = float(pre_slice["actual_basal_rate"].mean())
    sched_basal = float(pre_slice["scheduled_basal_rate"].mean())
    basal_gap = actual_basal - sched_basal if not (
        np.isnan(actual_basal) or np.isnan(sched_basal)
    ) else np.nan

    # Bolus in pre-window
    bolus_sum = float(pre_slice["bolus"].fillna(0).sum())

    nadir_time = g_pat["time"].iloc[nadir]
    hour = int(nadir_time.hour)

    return {
        "bg_start": bg_start,
        "bg_nadir": bg_nadir,
        "descent_slope": descent_slope,
        "iob_delta": iob_delta,
        "actual_basal": actual_basal,
        "sched_basal": sched_basal,
        "basal_gap": basal_gap,
        "pre_bolus": bolus_sum,
        "nadir_hour": hour,
        "tod": classify_tod(hour),
    }


def run_regression(df: pd.DataFrame) -> dict:
    """descent ~ iob_delta + basal_gap + pre_bolus."""
    d = df.dropna(subset=["descent_slope", "iob_delta", "basal_gap", "pre_bolus"])
    if len(d) < 10:
        return {
            "n": int(len(d)), "intercept": None, "r2": None,
            "median_descent": float(d.descent_slope.median()) if len(d) else None,
        }
    X = np.column_stack([
        np.ones(len(d)),
        d.iob_delta.values,
        d.basal_gap.values,
        d.pre_bolus.values,
    ])
    y = d.descent_slope.values
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    pred = X @ coef
    ss_res = float(((y - pred) ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else None
    return {
        "n": int(len(d)),
        "intercept": float(coef[0]),
        "beta_iob_delta": float(coef[1]),
        "beta_basal_gap": float(coef[2]),
        "beta_pre_bolus": float(coef[3]),
        "r2": float(r2) if r2 is not None else None,
        "median_descent": float(d.descent_slope.median()),
    }


def main() -> None:
    print("Loading grid...")
    grid = pd.read_parquet(GRID)
    grid["time"] = pd.to_datetime(grid["time"], utc=True)
    patients = grid.patient_id.unique()
    print(f"  patients={len(patients)}")

    all_events = []
    for pid in patients:
        g_pat = grid[grid.patient_id == pid].sort_values("time").reset_index(drop=True).copy()
        events = detect_hypo_recovery_events(g_pat)
        for ev in events:
            ann = annotate_pre_nadir(g_pat, ev)
            if ann is None:
                continue
            ann["patient_id"] = pid
            all_events.append(ann)
    df = pd.DataFrame(all_events)
    print(f"  events with valid pre-window: {len(df)}")

    # Attach controller
    ev_2875 = pd.read_parquet(
        ROOT / "externals/experiments/exp-2875_counter_regulation_events.parquet"
    )
    pat_ctrl = ev_2875.drop_duplicates("patient_id").set_index("patient_id").controller
    df["controller"] = df.patient_id.map(pat_ctrl)

    df.to_parquet(OUT_EVENTS)

    # Cohort stratum regression
    strata = {}
    for name, _, _ in TOD_BINS:
        sub = df[df.tod == name]
        strata[name] = run_regression(sub)

    print("\nCohort pre-nadir descent by TOD:")
    for name, _, _ in TOD_BINS:
        r = strata[name]
        if r["intercept"] is not None:
            print(
                f"  {name:10s} n={r['n']:4d} int={r['intercept']:+.3f} "
                f"median={r['median_descent']:+.3f} mg/dL/min R²={r['r2']:.3f}"
            )

    # Per-patient morning vs night descent-rate comparison
    per_patient = []
    for pid, g in df.groupby("patient_id"):
        morning = g[g.tod == "morning"]
        night = g[g.tod == "night"]
        if len(morning) < 5 or len(night) < 5:
            continue
        per_patient.append({
            "patient_id": pid,
            "controller": g.controller.iloc[0],
            "n_morning": len(morning),
            "n_night": len(night),
            "morning_descent": float(morning.descent_slope.median()),
            "night_descent": float(night.descent_slope.median()),
            # positive diff = morning descent is more negative (faster descent at dawn)
            "diff": float(night.descent_slope.median() - morning.descent_slope.median()),
        })
    pp = pd.DataFrame(per_patient)
    print(f"\nPer-patient morning vs night descent: n={len(pp)}")

    if len(pp) >= 5:
        wil_stat, wil_p = stats.wilcoxon(pp["diff"].values)
    else:
        wil_stat, wil_p = None, None
    median_diff = float(pp["diff"].median()) if len(pp) else None
    frac_morning_faster = float((pp["diff"] > 0).mean()) if len(pp) else None
    print(
        f"  median diff (night-morning, pos=morning-faster-descent)={median_diff:+.4f}  "
        f"frac morning faster={frac_morning_faster}  wilcoxon p={wil_p}"
    )

    # Stratum-level descent Spearman vs band center
    band_centers = {"night": 3, "morning": 9, "afternoon": 15, "evening": 21}
    rho_input = [
        (band_centers[n], strata[n]["median_descent"])
        for n, _, _ in TOD_BINS
        if strata[n]["median_descent"] is not None
    ]
    if len(rho_input) >= 3:
        xs = [x for x, _ in rho_input]
        ys = [y for _, y in rho_input]
        tod_rho, tod_p = stats.spearmanr(xs, ys)
    else:
        tod_rho, tod_p = None, None

    summary = {
        "exp_id": "2880",
        "n_events": int(len(df)),
        "n_patients": int(df.patient_id.nunique()),
        "pre_window_min": PRE_WINDOW_MIN,
        "strata": strata,
        "per_patient_morning_vs_night": {
            "n_patients_with_both": int(len(pp)),
            "median_diff": median_diff,
            "frac_morning_faster_descent": frac_morning_faster,
            "wilcoxon_p": float(wil_p) if wil_p is not None else None,
        },
        "descent_tod_spearman_rho": float(tod_rho) if tod_rho is not None else None,
        "descent_tod_spearman_p": float(tod_p) if tod_p is not None else None,
    }

    # Figure
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    names = [n for n, _, _ in TOD_BINS]
    medians = [strata[n]["median_descent"] for n in names]
    ns = [strata[n]["n"] for n in names]
    colors = ["#1f3b5f", "#d99133", "#3d8a5f", "#6d3d8f"]
    bars = axes[0].bar(names, medians, color=colors)
    for bar, n in zip(bars, ns):
        axes[0].text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() - 0.02,
            f"n={n}",
            ha="center", fontsize=9,
        )
    axes[0].axhline(0, color="gray", lw=0.5)
    axes[0].set_ylabel("Median descent slope (mg/dL/min, negative=falling)")
    axes[0].set_title(
        f"Pre-nadir descent by TOD "
        f"(ρ_band_center={tod_rho:+.2f})" if tod_rho is not None
        else "Pre-nadir descent by TOD"
    )
    axes[0].grid(axis="y", alpha=0.3)

    if len(pp):
        color_map = {"Loop": "tab:blue", "Trio": "tab:orange", "OpenAPS": "tab:green"}
        pp_colors = pp.controller.map(color_map).fillna("gray")
        y_pos = range(len(pp))
        axes[1].barh(y_pos, pp["diff"].values, color=pp_colors)
        axes[1].set_yticks(y_pos)
        axes[1].set_yticklabels(pp.patient_id.values, fontsize=7)
        axes[1].axvline(0, color="k", lw=0.5)
        axes[1].set_xlabel("night − morning descent (positive = morning descends faster)")
        axes[1].set_title(
            f"Per-patient night−morning descent\n"
            f"(n={len(pp)}, median={median_diff:+.3f}, "
            f"{frac_morning_faster:.0%} morning-faster, p={wil_p:.2g})"
        )
        axes[1].grid(axis="x", alpha=0.3)

    fig.suptitle(
        "EXP-2880 — Pre-Nadir BG Descent by Time-of-Day",
        fontsize=13,
    )
    fig.tight_layout()
    OUT_FIG.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_FIG, dpi=110)
    plt.close(fig)

    # Verdict
    # More-negative diff means morning descends FASTER (AID basal over-delivery at dawn)
    # Positive diff means morning descent is SLOWER (EGP amplification / dawn opposition)
    if median_diff is None or frac_morning_faster is None:
        verdict = "INSUFFICIENT DATA"
    elif (
        frac_morning_faster >= 0.65 and median_diff > 0.02
        and wil_p is not None and wil_p < 0.05
    ):
        verdict = (
            f"MORNING DESCENT FASTER — median night−morning descent "
            f"= {median_diff:+.3f} mg/dL/min ({frac_morning_faster:.0%} of "
            f"patients, Wilcoxon p={wil_p:.2g}). Consistent with AID basal "
            "over-delivery at dawn / under-compensation of dawn phenomenon "
            "tapering. Pre-hypo risk IS time-of-day structured."
        )
    elif (
        frac_morning_faster <= 0.35 and median_diff < -0.02
        and wil_p is not None and wil_p < 0.05
    ):
        verdict = (
            f"MORNING DESCENT SLOWER — median night−morning descent "
            f"= {median_diff:+.3f} mg/dL/min ({frac_morning_faster:.0%} "
            f"morning-faster, Wilcoxon p={wil_p:.2g}). Consistent with dawn "
            "EGP amplification opposing insulin-driven descent."
        )
    elif abs(median_diff) <= 0.02:
        verdict = (
            f"NO TOD DESCENT STRUCTURE — median night−morning descent "
            f"= {median_diff:+.3f} (effectively zero). Mirrors EXP-2879 null: "
            "AID is well-tuned on both offense and defense sides of hypo events."
        )
    else:
        verdict = (
            f"WEAK/DIRECTIONAL — median diff={median_diff:+.3f}, "
            f"{frac_morning_faster:.0%} morning-faster, p={wil_p}; "
            "directionally consistent but underpowered."
        )

    summary["verdict"] = verdict
    OUT_SUMMARY.write_text(json.dumps(summary, indent=2))
    print(f"\nVerdict: {verdict}")


if __name__ == "__main__":
    main()
