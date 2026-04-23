"""EXP-2879 — Counter-regulation circadian structure (time-of-day).

Glucagon and catecholamine release follow circadian rhythms; dawn hours
(04:00-08:00 local) are classically associated with heightened hepatic
glucose output ("dawn phenomenon"). If the EXP-2875/2877 counter-reg
signal is real physiology, it should show TOD structure with stronger
response during dawn/morning vs overnight.

Method:
  1. Re-detect rescue-free hypo events (reuse EXP-2875 detection logic).
  2. Annotate each event with nadir hour-of-day (UTC, since patient
     timezone not available; for most US/EU patients UTC ≈ local ± <12h,
     and we report aggregate patterns).
  3. Bin events into 4 TOD bands:
       night     00:00-06:00
       morning   06:00-12:00  (dawn phenomenon band)
       afternoon 12:00-18:00
       evening   18:00-24:00
  4. Cohort-level stratum regression rise_rate ~ iob_nadir + basal_gap
     per TOD band; compare intercepts.
  5. Per-patient band difference: morning_intercept − night_intercept.

Hypothesis: morning > night (dawn amplifies counter-reg).

Output: externals/experiments/exp-2879_tod.parquet + summary + figure.
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

# Reuse EXP-2875 detection & annotation logic
from tools.cgmencode.exp_counter_regulation_2875 import (  # noqa: E402
    detect_hypo_recovery_events,
    annotate_event,
)

GRID = ROOT / "externals/ns-parquet/training/grid.parquet"
OUT_EVENTS = ROOT / "externals/experiments/exp-2879_tod_events.parquet"
OUT_SUMMARY = ROOT / "externals/experiments/exp-2879_tod_summary.json"
OUT_FIG = ROOT / "docs/60-research/figures/exp-2879_tod.png"

TOD_BINS = [
    ("night", 0, 6),
    ("morning", 6, 12),
    ("afternoon", 12, 18),
    ("evening", 18, 24),
]


def classify_tod(hour: int) -> str:
    for name, lo, hi in TOD_BINS:
        if lo <= hour < hi:
            return name
    return "unknown"


def run_regression(df: pd.DataFrame) -> dict:
    """Return dict with intercept, betas, R², n."""
    d = df.dropna(subset=["rise_rate", "iob_nadir", "basal_gap"])
    if len(d) < 10:
        return {
            "n": int(len(d)), "intercept": None,
            "beta_iob": None, "beta_basal": None, "r2": None,
            "median_rise": float(d.rise_rate.median()) if len(d) else None,
        }
    X = np.column_stack(
        [np.ones(len(d)), d.iob_nadir.values, d.basal_gap.values]
    )
    y = d.rise_rate.values
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    pred = X @ coef
    ss_res = float(((y - pred) ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else None
    return {
        "n": int(len(d)),
        "intercept": float(coef[0]),
        "beta_iob": float(coef[1]),
        "beta_basal": float(coef[2]),
        "r2": float(r2) if r2 is not None else None,
        "median_rise": float(d.rise_rate.median()),
    }


def main() -> None:
    print("Loading grid...")
    grid = pd.read_parquet(GRID)
    grid["time"] = pd.to_datetime(grid["time"], utc=True)
    patients = grid.patient_id.unique()
    print(f"  patients={len(patients)}")

    all_events = []
    for pid in patients:
        g_pat = grid[grid.patient_id == pid].copy()
        controller = (
            g_pat.get("controller").iloc[0]
            if "controller" in g_pat.columns
            else None
        )
        events = detect_hypo_recovery_events(g_pat)
        g_pat = g_pat.sort_values("time").reset_index(drop=True)
        for ev in events:
            ann = annotate_event(g_pat, ev)
            if ann is None:
                continue
            nadir_time = g_pat["time"].iloc[ev["nadir_idx"]]
            ann["nadir_hour"] = int(nadir_time.hour)
            ann["tod"] = classify_tod(ann["nadir_hour"])
            ann["patient_id"] = pid
            ann["controller"] = controller
            all_events.append(ann)
    df = pd.DataFrame(all_events)
    print(f"  events={len(df)}")

    # Need controller from somewhere if not in grid
    if "controller" not in df.columns or df.controller.isna().all():
        ev_2875 = pd.read_parquet(
            ROOT / "externals/experiments/exp-2875_counter_regulation_events.parquet"
        )
        pat_ctrl = ev_2875.drop_duplicates("patient_id").set_index("patient_id").controller
        df["controller"] = df.patient_id.map(pat_ctrl)

    df.to_parquet(OUT_EVENTS)
    print(f"Saved events: {OUT_EVENTS}")

    # Cohort stratum regression per TOD
    strata = {}
    for name, _lo, _hi in TOD_BINS:
        sub = df[df.tod == name]
        strata[name] = run_regression(sub)

    print("\nCohort stratum regression by TOD:")
    for name, _lo, _hi in TOD_BINS:
        r = strata[name]
        if r["intercept"] is not None:
            print(
                f"  {name:10s} n={r['n']:4d} int={r['intercept']:+.2f} "
                f"β_iob={r['beta_iob']:+.3f} β_basal={r['beta_basal']:+.2f} "
                f"R²={r['r2']:.3f} median={r['median_rise']:+.2f}"
            )

    # Per-patient morning vs night difference
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
            "morning_median": float(morning.rise_rate.median()),
            "night_median": float(night.rise_rate.median()),
            "diff": float(morning.rise_rate.median() - night.rise_rate.median()),
        })
    pp = pd.DataFrame(per_patient)
    print(f"\nPer-patient morning vs night: n={len(pp)}")

    wil_stat, wil_p = (
        stats.wilcoxon(pp["diff"].values) if len(pp) >= 5 else (None, None)
    )
    frac_pos = float((pp["diff"] > 0).mean()) if len(pp) else None
    median_diff = float(pp["diff"].median()) if len(pp) else None
    print(
        f"  median morning−night diff={median_diff:+.3f}  "
        f"frac_positive={frac_pos}  wilcoxon p={wil_p}"
    )

    # Spearman across all 4 TOD band-centers (mid-hour) vs intercepts
    band_centers = {"night": 3, "morning": 9, "afternoon": 15, "evening": 21}
    rho_input = [
        (band_centers[name], strata[name]["intercept"])
        for name, _lo, _hi in TOD_BINS
        if strata[name]["intercept"] is not None
    ]
    if len(rho_input) >= 3:
        xs = [x for x, _ in rho_input]
        ys = [y for _, y in rho_input]
        tod_rho, tod_p = stats.spearmanr(xs, ys)
    else:
        tod_rho, tod_p = None, None

    summary = {
        "exp_id": "2879",
        "n_events": int(len(df)),
        "n_patients": int(df.patient_id.nunique()),
        "strata": {k: v for k, v in strata.items()},
        "per_patient_morning_vs_night": {
            "n_patients_with_both": int(len(pp)),
            "median_diff": median_diff,
            "frac_positive": frac_pos,
            "wilcoxon_stat": float(wil_stat) if wil_stat is not None else None,
            "wilcoxon_p": float(wil_p) if wil_p is not None else None,
        },
        "tod_intercept_spearman_rho": float(tod_rho) if tod_rho is not None else None,
        "tod_intercept_spearman_p": float(tod_p) if tod_p is not None else None,
    }

    # Figure: 2-panel
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))

    # Panel 1: stratum intercepts
    names = [n for n, _, _ in TOD_BINS]
    intercepts = [strata[n]["intercept"] for n in names]
    ns = [strata[n]["n"] for n in names]
    bars = axes[0].bar(names, intercepts, color=["#1f3b5f", "#d99133", "#3d8a5f", "#6d3d8f"])
    for bar, n in zip(bars, ns):
        axes[0].text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.05,
            f"n={n}",
            ha="center", fontsize=9,
        )
    axes[0].axhline(0, color="gray", lw=0.5)
    axes[0].set_ylabel("Cohort intercept (mg/dL/min)")
    axes[0].set_title(
        f"Cohort stratum intercept by TOD  "
        f"(Spearman ρ={tod_rho:+.2f} if shown)"
        if tod_rho is not None else "Cohort stratum intercept by TOD"
    )
    axes[0].grid(axis="y", alpha=0.3)

    # Panel 2: per-patient morning − night differences
    if len(pp):
        color_map = {"Loop": "tab:blue", "Trio": "tab:orange", "OpenAPS": "tab:green"}
        colors = pp.controller.map(color_map).fillna("gray")
        y_pos = range(len(pp))
        axes[1].barh(y_pos, pp["diff"].values, color=colors)
        axes[1].set_yticks(y_pos)
        axes[1].set_yticklabels(pp.patient_id.values, fontsize=7)
        axes[1].axvline(0, color="k", lw=0.5)
        axes[1].set_xlabel("morning − night median rise (mg/dL/min)")
        axes[1].set_title(
            f"Per-patient morning − night  "
            f"(n={len(pp)}, median={median_diff:+.2f}, "
            f"{frac_pos:.0%} positive)"
        )
        axes[1].grid(axis="x", alpha=0.3)

    fig.suptitle(
        "EXP-2879 — Counter-Regulation Circadian Structure",
        fontsize=13,
    )
    fig.tight_layout()
    OUT_FIG.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_FIG, dpi=110)
    plt.close(fig)
    print(f"Saved figure: {OUT_FIG}")

    # Verdict
    if median_diff is not None and frac_pos is not None:
        if (
            median_diff > 0.1 and frac_pos >= 0.65
            and wil_p is not None and wil_p < 0.05
        ):
            verdict = (
                f"DAWN AMPLIFICATION CONFIRMED — per-patient morning "
                f"median exceeds night by {median_diff:+.2f} mg/dL/min "
                f"({frac_pos:.0%} positive, Wilcoxon p={wil_p:.2g}). "
                "Counter-reg has physiological circadian structure."
            )
        elif median_diff > 0.05 and frac_pos >= 0.55:
            verdict = (
                f"WEAK DAWN SIGNAL — morning − night = {median_diff:+.2f} "
                f"mg/dL/min ({frac_pos:.0%} positive, p={wil_p}). "
                "Directionally consistent with dawn amplification but "
                "underpowered."
            )
        elif abs(median_diff) <= 0.05:
            verdict = (
                f"NO CIRCADIAN STRUCTURE — morning and night responses "
                f"are indistinguishable (diff={median_diff:+.2f}). "
                "Either AID overrides circadian variation, or the "
                "closed-loop recovery signal is dominated by IOB/basal "
                "dynamics rather than endogenous hormones."
            )
        else:
            verdict = (
                f"UNEXPECTED NIGHT > MORNING — diff={median_diff:+.2f}; "
                "inconsistent with classical dawn phenomenon."
            )
    else:
        verdict = "INSUFFICIENT DATA"

    summary["verdict"] = verdict
    OUT_SUMMARY.write_text(json.dumps(summary, indent=2))
    print(f"\nVerdict: {verdict}")


if __name__ == "__main__":
    main()
