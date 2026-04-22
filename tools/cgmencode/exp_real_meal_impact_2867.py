"""EXP-2867 — Re-validate EXP-2750 small-vs-large meal absorption under
real-meal gating.

EXP-2750 claimed large meals produce 60% of per-gram glucose impact
vs small meals (1.81 vs 2.99 mg/dL/g) and was universal across 22/22
patients. EXP-2866 found 30% of cohort carb events are <5g (likely
treat-of-low / detector noise). This experiment re-runs the small-vs-
large comparison after applying:

* `is_real_meal` floor of 10g → "small meal" pool excludes the
  contaminating sub-5g events and 5–10g snack/correction events.
* "large meal" floor of 60g (more selective than EXP-2750's 50g, to
  match user clinical prior of 50–60g+ true meals).

Per-meal impact: median glucose excursion (post − pre) over the
2-hour window after the meal, divided by carb amount.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from tools.cgmencode.production.meal_filter import (
    REAL_MEAL_FLOOR_G,
)
EXPDIR = REPO / "externals" / "experiments"
FIGDIR = REPO / "docs" / "60-research" / "figures"
GRID = REPO / "externals" / "ns-parquet" / "training" / "grid.parquet"

SMALL_MEAL_LO = REAL_MEAL_FLOOR_G   # >=10g
SMALL_MEAL_HI = 30.0                # <30g
LARGE_MEAL_FLOOR = 60.0             # >=60g (user prior)
ABSORB_HORIZON_MIN = 120
PRE_BASELINE_MIN = 30
MIN_MEALS_PER_BUCKET = 5


def _per_meal_impact(g: pd.DataFrame, meal_idx: int) -> float | None:
    """Mean glucose increment in the 120 min after a meal vs the 30
    min before, divided by carb amount. None if windows incomplete."""
    t = g["t_min"].iloc[meal_idx]
    pre_mask = (g["t_min"] >= t - PRE_BASELINE_MIN) & (g["t_min"] < t)
    post_mask = (g["t_min"] >= t) & (g["t_min"] <= t + ABSORB_HORIZON_MIN)
    pre = g.loc[pre_mask, "glucose"].dropna()
    post = g.loc[post_mask, "glucose"].dropna()
    if len(pre) < 3 or len(post) < 12:
        return None
    excursion = float(post.max() - pre.median())
    carbs = float(g["carbs"].iloc[meal_idx])
    if carbs <= 0:
        return None
    return excursion / carbs


def main() -> None:
    df = pd.read_parquet(GRID, columns=[
        "patient_id", "time", "glucose", "carbs",
    ])
    df = df.sort_values(["patient_id", "time"]).reset_index(drop=True)
    df["t_min"] = pd.to_datetime(df["time"]).astype("int64") / 60_000_000_000

    rows = []
    for pid, g in df.groupby("patient_id", sort=False):
        g = g.reset_index(drop=True)
        meal_indices = g.index[g["carbs"].fillna(0) >= SMALL_MEAL_LO].tolist()
        for mi in meal_indices:
            carbs = float(g["carbs"].iloc[mi])
            impact = _per_meal_impact(g, mi)
            if impact is None:
                continue
            if SMALL_MEAL_LO <= carbs < SMALL_MEAL_HI:
                bucket = "small_real_meal"
            elif carbs >= LARGE_MEAL_FLOOR:
                bucket = "large_real_meal"
            else:
                bucket = "mid_meal"
            rows.append({
                "patient_id": pid,
                "carbs": carbs,
                "bucket": bucket,
                "impact_mg_dl_per_g": impact,
            })
    out = pd.DataFrame(rows)
    out.to_parquet(EXPDIR / "exp-2867_per_meal_impact.parquet", index=False)

    summary_rows = []
    for pid, g in out.groupby("patient_id"):
        small = g[g["bucket"] == "small_real_meal"]["impact_mg_dl_per_g"]
        large = g[g["bucket"] == "large_real_meal"]["impact_mg_dl_per_g"]
        if len(small) < MIN_MEALS_PER_BUCKET or len(large) < MIN_MEALS_PER_BUCKET:
            continue
        summary_rows.append({
            "patient_id": pid,
            "n_small": int(len(small)),
            "n_large": int(len(large)),
            "small_med_impact": float(small.median()),
            "large_med_impact": float(large.median()),
            "ratio_large_over_small": float(large.median() / small.median())
                if small.median() > 0 else float("nan"),
        })
    per_p = pd.DataFrame(summary_rows)
    per_p.to_parquet(EXPDIR / "exp-2867_per_patient_size_compare.parquet",
                     index=False)

    summary = {
        "exp": "EXP-2867",
        "method": (
            f"Re-validate EXP-2750 small-vs-large meal impact under real-meal "
            f"gating (small=[{SMALL_MEAL_LO},{SMALL_MEAL_HI})g, "
            f"large=>={LARGE_MEAL_FLOOR}g). Per-meal "
            "impact = (post 120-min max BG - pre 30-min median) / carbs."
        ),
        "n_per_meal_rows": int(len(out)),
        "buckets": out["bucket"].value_counts().to_dict() if len(out) else {},
        "n_patients_with_both": int(len(per_p)),
        "cohort_med_small_impact": float(per_p["small_med_impact"].median())
            if len(per_p) else None,
        "cohort_med_large_impact": float(per_p["large_med_impact"].median())
            if len(per_p) else None,
        "cohort_med_ratio_large_over_small": float(per_p["ratio_large_over_small"].median())
            if len(per_p) else None,
        "n_patients_large_smaller_than_small": int(
            (per_p["large_med_impact"] < per_p["small_med_impact"]).sum()
        ) if len(per_p) else 0,
        "exp_2750_claim_ratio": "1.81 / 2.99 = 0.605",
    }
    (EXPDIR / "exp-2867_summary.json").write_text(json.dumps(summary, indent=2))

    try:
        import matplotlib.pyplot as plt
        if len(per_p):
            fig, ax = plt.subplots(figsize=(9, 5))
            x = np.arange(len(per_p))
            ax.bar(x - 0.2, per_p["small_med_impact"], 0.4, label="small (10–30g)",
                   color="#A0C4E0")
            ax.bar(x + 0.2, per_p["large_med_impact"], 0.4, label="large (>=60g)",
                   color="#4472C4")
            ax.set_xticks(x)
            ax.set_xticklabels(per_p["patient_id"], rotation=70, fontsize=8)
            ax.set_ylabel("median per-g impact (mg/dL/g)")
            ax.set_title(
                "EXP-2867: per-g meal impact under real-meal gating\n"
                "(EXP-2750 claim: large/small ratio ≈ 0.6)"
            )
            ax.legend()
            FIGDIR.mkdir(parents=True, exist_ok=True)
            plt.tight_layout()
            fig.savefig(FIGDIR / "exp-2867_real_meal_impact.png", dpi=120)
            plt.close(fig)
    except Exception as e:  # noqa: BLE001
        print("viz failed:", e)

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
