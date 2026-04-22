"""EXP-2855 — Per-TOD Simpson decomposition.

For each patient and each time-of-day bucket (dawn 0-6, midday 6-12,
afternoon 12-18, night 18-24), compute β_fast (5-min) and β_slow
(48h window means restricted to that TOD bucket).

Question (Stream B): does the reactive-vs-structural balance shift
across the day? If a patient is Simpson at midday but coherent at
dawn, the audition matrix can target TOD windows where the signal is
unambiguous and avoid windows where it's confounded.

Charter B compliant. β values are operational measurements of
controller behavior at different times of day.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

REPO = Path(__file__).resolve().parents[2]
EXPDIR = REPO / "externals" / "experiments"
FIGDIR = REPO / "docs" / "60-research" / "figures"
GRID = REPO / "externals" / "ns-parquet" / "training" / "grid.parquet"

TOD_BUCKETS = [
    ("dawn", 0, 6),
    ("midday", 6, 12),
    ("afternoon", 12, 18),
    ("night", 18, 24),
]


def per_patient_tod(g: pd.DataFrame, window_h: int = 48) -> list[dict]:
    g = g.sort_values("time").reset_index(drop=True)
    g["hour"] = pd.to_datetime(g["time"], utc=True).dt.hour
    rows = []
    for name, lo, hi in TOD_BUCKETS:
        sub = g[(g["hour"] >= lo) & (g["hour"] < hi)]
        if len(sub) < 24 * 12:  # need 24 bucket-hours worth
            continue
        x = sub["glucose"].to_numpy()
        y = sub["actual_basal_rate"].to_numpy()
        if np.std(x) < 1e-6 or np.std(y) < 1e-6:
            continue
        fast = stats.linregress(x, y)

        # Slow: aggregate by (date) within this TOD bucket
        sub2 = sub.copy()
        sub2["date"] = pd.to_datetime(sub2["time"], utc=True).dt.date
        agg = sub2.groupby("date").agg(g=("glucose", "mean"),
                                       b=("actual_basal_rate", "mean"))
        if len(agg) < 6 or np.std(agg["g"]) < 1e-3:
            continue
        slow = stats.linregress(agg["g"], agg["b"])

        mean_basal = float(np.mean(y))
        rows.append({
            "tod": name,
            "n_5min": int(len(sub)),
            "n_days": int(len(agg)),
            "mean_basal_uph": mean_basal,
            "beta_fast_uph_per_50": float(fast.slope * 50),
            "beta_fast_p": float(fast.pvalue),
            "beta_slow_uph_per_50": float(slow.slope * 50),
            "beta_slow_p": float(slow.pvalue),
            "simpson": bool(
                np.sign(fast.slope) != np.sign(slow.slope)
                and abs(fast.slope) > 1e-6 and abs(slow.slope) > 1e-6
            ),
        })
    return rows


def main() -> None:
    cols = ["patient_id", "time", "glucose", "actual_basal_rate"]
    df = pd.read_parquet(GRID, columns=cols).dropna(
        subset=["glucose", "actual_basal_rate"]
    )

    rows = []
    for pid, g in df.groupby("patient_id", sort=False):
        if len(g) < 24 * 12 * 7:
            continue
        for r in per_patient_tod(g):
            r["patient_id"] = pid
            rows.append(r)

    out = pd.DataFrame(rows)
    out_path = EXPDIR / "exp-2855_tod_simpson.parquet"
    out.to_parquet(out_path, index=False)

    # Summary by TOD
    summary = []
    for name, _, _ in TOD_BUCKETS:
        sub = out[out["tod"] == name]
        if sub.empty:
            continue
        summary.append({
            "tod": name,
            "n_patients": int(len(sub)),
            "n_simpson": int(sub["simpson"].sum()),
            "frac_simpson": float(sub["simpson"].mean()),
            "median_beta_fast_uph_per_50": float(sub["beta_fast_uph_per_50"].median()),
            "median_beta_slow_uph_per_50": float(sub["beta_slow_uph_per_50"].median()),
            "n_fast_negative": int((sub["beta_fast_uph_per_50"] < 0).sum()),
            "n_slow_negative": int((sub["beta_slow_uph_per_50"] < 0).sum()),
        })

    # Per-patient Simpson-by-TOD pivot
    pivot = out.pivot_table(
        index="patient_id", columns="tod", values="simpson", aggfunc="first"
    )
    pivot["n_simpson_buckets"] = pivot.fillna(False).sum(axis=1)
    pivot.to_parquet(EXPDIR / "exp-2855_per_patient_tod_pivot.parquet")

    n_any = int((pivot["n_simpson_buckets"] >= 1).sum())
    n_all = int((pivot["n_simpson_buckets"] == pivot.drop(columns=["n_simpson_buckets"]).notna().sum(axis=1)).sum())

    out_summary = {
        "exp": "EXP-2855",
        "method": "Per (patient, TOD bucket) β_fast (5-min) and β_slow (per-day means within bucket).",
        "summary_by_tod": summary,
        "n_patients_with_any_simpson_tod": n_any,
        "n_patients_with_all_simpson_tods": n_all,
        "interpretation": [
            "If frac_simpson varies across TOD: audition matrix can target the unambiguous TOD windows.",
            "If a patient is Simpson at one bucket only: that bucket is the deconfounding-relevant target.",
        ],
    }
    out_json = EXPDIR / "exp-2855_summary.json"
    out_json.write_text(json.dumps(out_summary, indent=2))

    # Visualization
    try:
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(1, 2, figsize=(14, 5))

        ax = axes[0]
        tods = [s["tod"] for s in summary]
        fracs = [s["frac_simpson"] for s in summary]
        ns = [s["n_patients"] for s in summary]
        colors = ["#4472C4", "#ED7D31", "#A5A5A5", "#264478"]
        ax.bar(tods, fracs, color=colors[: len(tods)], edgecolor="black")
        for i, (f, n) in enumerate(zip(fracs, ns)):
            ax.text(i, f + 0.02, f"{f*100:.0f}%\nn={n}", ha="center", fontsize=9)
        ax.set_ylim(0, 0.6)
        ax.set_ylabel("Fraction Simpson")
        ax.set_title("Simpson rate by TOD bucket")
        ax.axhline(0.31, color="gray", linestyle="--", alpha=0.5,
                   label="EXP-2853 cohort baseline 31%")
        ax.legend(fontsize=8)

        ax = axes[1]
        # Box-plot of β_fast by TOD
        data_fast = [out[out["tod"] == t]["beta_fast_uph_per_50"].values for t in tods]
        data_slow = [out[out["tod"] == t]["beta_slow_uph_per_50"].values for t in tods]
        positions_fast = np.arange(len(tods)) - 0.18
        positions_slow = np.arange(len(tods)) + 0.18
        bp1 = ax.boxplot(data_fast, positions=positions_fast, widths=0.3,
                         patch_artist=True, showfliers=False)
        bp2 = ax.boxplot(data_slow, positions=positions_slow, widths=0.3,
                         patch_artist=True, showfliers=False)
        for box in bp1["boxes"]:
            box.set_facecolor("#4472C4")
        for box in bp2["boxes"]:
            box.set_facecolor("#ED7D31")
        ax.axhline(0, color="black", linewidth=0.5)
        ax.set_xticks(np.arange(len(tods)))
        ax.set_xticklabels(tods)
        ax.set_ylabel("β (U/h per +50 mg/dL)")
        ax.set_title("β_fast (blue) vs β_slow (orange) by TOD")

        fig.suptitle(
            "EXP-2855: per-TOD Simpson decomposition — when does the "
            "reactive vs structural balance shift?",
            fontsize=12,
        )
        plt.tight_layout()
        FIGDIR.mkdir(parents=True, exist_ok=True)
        fig.savefig(FIGDIR / "exp-2855_tod_simpson.png", dpi=120)
        plt.close(fig)
    except Exception as e:  # noqa: BLE001
        print("viz failed:", e)

    print(json.dumps(out_summary, indent=2))


if __name__ == "__main__":
    main()
