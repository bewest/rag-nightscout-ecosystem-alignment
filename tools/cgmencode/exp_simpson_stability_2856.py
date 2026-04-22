"""EXP-2856 — Rolling-30d Simpson Stability.

For each patient with sufficient data, slide a 30-day window across
their timeline (15-day stride). Compute β_fast (5-min) and β_slow
(48h windows) within each rolling window. Track:
  - Simpson flag stability: fraction of windows that agree with the
    patient's overall classification
  - β_fast and β_slow value drift

If Simpson is highly stable: refresh cadence can be quarterly+.
If unstable: production must refresh per audition cycle.

Charter B compliant.
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

WINDOW_DAYS = 30
STRIDE_DAYS = 15


def betas(g: pd.DataFrame) -> dict | None:
    if len(g) < 24 * 12 * 7:
        return None
    x = g["glucose"].to_numpy()
    y = g["actual_basal_rate"].to_numpy()
    if np.std(x) < 1e-3 or np.std(y) < 1e-6:
        return None
    fast = stats.linregress(x, y)
    win_size = 48 * 12
    n_full = len(g) // win_size
    if n_full < 4:
        return None
    g_trim = g.iloc[: n_full * win_size]
    bg_w = g_trim["glucose"].to_numpy().reshape(n_full, win_size).mean(axis=1)
    ba_w = g_trim["actual_basal_rate"].to_numpy().reshape(n_full, win_size).mean(axis=1)
    if np.std(bg_w) < 1e-3:
        return None
    slow = stats.linregress(bg_w, ba_w)
    return {
        "beta_fast": float(fast.slope),
        "beta_slow": float(slow.slope),
        "simpson": bool(
            np.sign(fast.slope) != np.sign(slow.slope)
            and abs(fast.slope) > 1e-6 and abs(slow.slope) > 1e-6
        ),
    }


def main() -> None:
    cols = ["patient_id", "time", "glucose", "actual_basal_rate"]
    df = pd.read_parquet(GRID, columns=cols).dropna(
        subset=["glucose", "actual_basal_rate"]
    )
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df = df.sort_values(["patient_id", "time"])

    rows = []
    for pid, g in df.groupby("patient_id", sort=False):
        if len(g) < 24 * 12 * 60:  # need >=60 days for stability check
            continue
        t0 = g["time"].min()
        t_end = g["time"].max()
        total_days = (t_end - t0).days
        if total_days < 60:
            continue
        # Overall classification (anchor)
        overall = betas(g)
        if not overall:
            continue
        win_start = 0
        while win_start + WINDOW_DAYS <= total_days:
            ws = t0 + pd.Timedelta(days=win_start)
            we = ws + pd.Timedelta(days=WINDOW_DAYS)
            sub = g[(g["time"] >= ws) & (g["time"] < we)]
            r = betas(sub)
            if r:
                rows.append({
                    "patient_id": pid,
                    "window_start_day": int(win_start),
                    "n_samples": int(len(sub)),
                    **r,
                    "overall_simpson": overall["simpson"],
                    "agrees_with_overall": r["simpson"] == overall["simpson"],
                })
            win_start += STRIDE_DAYS

    out = pd.DataFrame(rows)
    out_path = EXPDIR / "exp-2856_rolling_simpson.parquet"
    out.to_parquet(out_path, index=False)

    # Per-patient stability
    pp = out.groupby("patient_id").agg(
        n_windows=("simpson", "count"),
        frac_simpson=("simpson", "mean"),
        frac_agree_with_overall=("agrees_with_overall", "mean"),
        overall_simpson=("overall_simpson", "first"),
        beta_fast_std=("beta_fast", "std"),
        beta_slow_std=("beta_slow", "std"),
    ).reset_index()
    pp_path = EXPDIR / "exp-2856_per_patient_stability.parquet"
    pp.to_parquet(pp_path, index=False)

    # Cohort
    n_pts = int(len(pp))
    median_agreement = float(pp["frac_agree_with_overall"].median())
    n_stable_75 = int((pp["frac_agree_with_overall"] >= 0.75).sum())
    n_stable_90 = int((pp["frac_agree_with_overall"] >= 0.90).sum())
    # Simpson-positive subset
    pp_simpson = pp[pp["overall_simpson"]]
    pp_clean = pp[~pp["overall_simpson"]]

    out_summary = {
        "exp": "EXP-2856",
        "method": (
            "Rolling 30-day windows with 15-day stride per patient. "
            "Compute β_fast/β_slow + Simpson per window; compare to overall."
        ),
        "n_patients_with_60d": n_pts,
        "median_agreement_with_overall": median_agreement,
        "n_stable_75pct": n_stable_75,
        "n_stable_90pct": n_stable_90,
        "frac_stable_75pct": float(n_stable_75 / n_pts) if n_pts else 0.0,
        "frac_stable_90pct": float(n_stable_90 / n_pts) if n_pts else 0.0,
        "simpson_positive_n": int(len(pp_simpson)),
        "simpson_positive_median_agreement": float(
            pp_simpson["frac_agree_with_overall"].median()
        ) if len(pp_simpson) else None,
        "simpson_negative_n": int(len(pp_clean)),
        "simpson_negative_median_agreement": float(
            pp_clean["frac_agree_with_overall"].median()
        ) if len(pp_clean) else None,
        "interpretation": [
            ">90% agreement → Simpson is stable, audition can refresh quarterly.",
            "<75% agreement → unstable, refresh per audition cycle (monthly).",
            "Simpson-positive vs negative agreement asymmetry: are flagged "
            "patients more or less stable?",
        ],
    }
    out_json = EXPDIR / "exp-2856_summary.json"
    out_json.write_text(json.dumps(out_summary, indent=2))

    # Visualization
    try:
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(1, 2, figsize=(14, 5))

        ax = axes[0]
        ax.hist(
            pp["frac_agree_with_overall"], bins=15,
            color="#4472C4", edgecolor="black", alpha=0.8,
        )
        ax.axvline(0.75, color="orange", linestyle="--", label="75% stable")
        ax.axvline(0.90, color="green", linestyle="--", label="90% stable")
        ax.set_xlabel("Fraction of rolling windows agreeing with overall classification")
        ax.set_ylabel("Patient count")
        ax.set_title(
            f"Per-patient Simpson stability (median={median_agreement:.0%}, "
            f"n={n_pts})"
        )
        ax.legend(fontsize=9)

        ax = axes[1]
        # Per-patient β_fast trace over time (small multiples)
        if not out.empty:
            for pid, sub in out.groupby("patient_id"):
                if len(sub) < 3:
                    continue
                ax.plot(sub["window_start_day"], sub["beta_fast"] * 50,
                        alpha=0.4, linewidth=1)
            ax.axhline(0, color="black", linewidth=0.5)
            ax.set_xlabel("Window start day")
            ax.set_ylabel("β_fast (U/h per +50 mg/dL)")
            ax.set_title("β_fast drift over rolling 30d windows")

        fig.suptitle(
            "EXP-2856: rolling-30d Simpson stability — refresh-cadence diagnostic",
            fontsize=12,
        )
        plt.tight_layout()
        FIGDIR.mkdir(parents=True, exist_ok=True)
        fig.savefig(FIGDIR / "exp-2856_rolling_simpson.png", dpi=120)
        plt.close(fig)
    except Exception as e:  # noqa: BLE001
        print("viz failed:", e)

    print(json.dumps(out_summary, indent=2))


if __name__ == "__main__":
    main()
