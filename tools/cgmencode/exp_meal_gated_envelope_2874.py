"""EXP-2874 — Meal-gated re-run of EXP-2851 fast-scale envelope.

Hypothesis (from EXP-2873 cascade follow-up):
  EXP-2851 post-bugfix found basal_shift_pct positive at all windows
  (median +50% at 1h decaying smoothly to +1% at 48h). High-glucose
  windows show HIGHER basal — opposite of the audition expectation.

  Q: is this driven by post-meal periods, where glucose rises BEFORE
     basal can be reduced (carbs > basal-down-correction in the same
     window)? If the shift VANISHES under meal gating it was a
     post-meal artifact, not a true envelope-coupling phenomenon.

Design:
  - Same windowing/percentile aggregation as EXP-2851 (post-bugfix).
  - Cell-level meal mask: any 5-min cell with carbs > 0 OR
    time_since_carb_min < 240 (4h) is "post-meal".
  - Window is "meal-gated" if ≥80% of its cells are NON-meal.
  - Re-compute the elev-vs-norm basal shift on the gated subset.
  - Compare median_shift_pct between full and gated cohorts.

Charter: Stream B operational — observed effective basal shift; not
biological causation. Apply NaN guard from EXP-2873.

Output:
  externals/experiments/exp-2874_meal_gated_envelope.parquet
  externals/experiments/exp-2874_summary.json
  docs/60-research/figures/exp-2874_meal_gated_envelope.png
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

EXP = Path("externals/experiments")
FIG = Path("docs/60-research/figures")
WINDOWS_HOURS = [1, 2, 3, 6, 12, 24, 48]
MEAL_LOOKBACK_MIN = 240  # 4h post-carb still counted as post-meal
GATE_FRACTION = 0.80     # ≥80% of cells must be non-meal


def _flag_meal_cells(g_pat: pd.DataFrame) -> pd.Series:
    """Cell-level meal mask: True = post-meal (within 4h of carbs OR
    has carbs in the cell). Falls back to carbs>0 only if
    time_since_carb_min is missing.
    """
    has_carbs = g_pat.get("carbs", pd.Series(0, index=g_pat.index)).fillna(0) > 0
    if "time_since_carb_min" in g_pat.columns:
        recent = g_pat["time_since_carb_min"].fillna(np.inf) < MEAL_LOOKBACK_MIN
    else:
        recent = pd.Series(False, index=g_pat.index)
    return has_carbs | recent


def aggregate_windows(g_pat: pd.DataFrame, window_h: int,
                      meal_gated: bool) -> pd.DataFrame:
    cells_per_window = window_h * 12
    if len(g_pat) < cells_per_window * 6:
        return pd.DataFrame()
    g_pat = g_pat.sort_values("time").reset_index(drop=True).copy()
    g_pat["window_id"] = g_pat.index // cells_per_window
    g_pat["meal_cell"] = _flag_meal_cells(g_pat)
    agg = (
        g_pat.groupby("window_id")
        .agg(
            n=("glucose", "size"),
            glucose=("glucose", "mean"),
            actual_basal=("actual_basal_rate", "mean"),
            meal_cells=("meal_cell", "sum"),
        )
        .reset_index()
    )
    agg = agg[agg["n"] >= cells_per_window * 0.8].copy()
    if meal_gated:
        agg = agg[agg["meal_cells"] <= (1 - GATE_FRACTION) * agg["n"]]
    return agg.reset_index(drop=True)


def per_patient_signal(g_pat: pd.DataFrame, window_h: int,
                       meal_gated: bool) -> dict | None:
    agg = aggregate_windows(g_pat, window_h, meal_gated)
    if agg.empty:
        return None
    agg = agg.dropna(subset=["glucose", "actual_basal"])
    if len(agg) < 6:
        return None
    q33, q67 = np.percentile(agg["glucose"], [33, 67])
    elev = agg[agg["glucose"] >= q67]
    norm = agg[agg["glucose"] <= q33]
    if len(elev) < 3 or len(norm) < 3:
        return None
    basal_elev = float(elev["actual_basal"].mean())
    basal_norm = float(norm["actual_basal"].mean())
    if basal_norm <= 0:
        return None
    shift_pct = 100 * (basal_elev - basal_norm) / basal_norm
    try:
        u, p = stats.mannwhitneyu(
            elev["actual_basal"].dropna(),
            norm["actual_basal"].dropna(),
            alternative="two-sided",
        )
    except ValueError:
        p = np.nan
    return dict(
        window_h=window_h,
        gated=meal_gated,
        n_windows=int(len(agg)),
        n_elev=int(len(elev)),
        n_norm=int(len(norm)),
        basal_shift_pct=shift_pct,
        mannwhitney_p=float(p) if not np.isnan(p) else None,
    )


def cohort_summary(df: pd.DataFrame, gated: bool) -> list[dict]:
    out = []
    sub_all = df[df["gated"] == gated]
    for w in WINDOWS_HOURS:
        sub = sub_all[sub_all["window_h"] == w]
        if sub.empty:
            continue
        n = len(sub)
        n_sig01 = int((sub["mannwhitney_p"].fillna(1.0) < 0.01).sum())
        out.append(dict(
            window_h=w,
            gated=gated,
            n_patients=n,
            frac_sig_p01=round(n_sig01 / n, 3),
            median_shift_pct=round(float(sub["basal_shift_pct"].median()), 2),
            iqr_shift_pct=round(
                float(np.percentile(sub["basal_shift_pct"], 75)
                      - np.percentile(sub["basal_shift_pct"], 25)),
                2,
            ),
        ))
    return out


def main() -> None:
    g = pd.read_parquet("externals/ns-parquet/training/grid.parquet")
    g["time"] = pd.to_datetime(g["time"], utc=True)

    rows = []
    for pid, g_pat in g.groupby("patient_id"):
        for w in WINDOWS_HOURS:
            for gated in (False, True):
                r = per_patient_signal(g_pat, w, gated)
                if r is None:
                    continue
                r["patient_id"] = pid
                rows.append(r)

    df = pd.DataFrame(rows)
    print(f"Rows: {len(df)}")

    full = cohort_summary(df, gated=False)
    gated = cohort_summary(df, gated=True)

    print("\nFULL cohort by window:")
    print(pd.DataFrame(full).to_string(index=False))
    print("\nMEAL-GATED cohort by window:")
    print(pd.DataFrame(gated).to_string(index=False))

    # Diff per window (gated - full median shift)
    full_by_w = {r["window_h"]: r for r in full}
    gated_by_w = {r["window_h"]: r for r in gated}
    diffs = []
    for w in WINDOWS_HOURS:
        if w not in full_by_w or w not in gated_by_w:
            continue
        diffs.append({
            "window_h": w,
            "full_median": full_by_w[w]["median_shift_pct"],
            "gated_median": gated_by_w[w]["median_shift_pct"],
            "delta": round(gated_by_w[w]["median_shift_pct"]
                           - full_by_w[w]["median_shift_pct"], 2),
            "full_n": full_by_w[w]["n_patients"],
            "gated_n": gated_by_w[w]["n_patients"],
        })

    df.to_parquet(EXP / "exp-2874_meal_gated_envelope.parquet", index=False)

    # Verdict
    median_gated_1h = gated_by_w.get(1, {}).get("median_shift_pct", None)
    median_full_1h = full_by_w.get(1, {}).get("median_shift_pct", None)
    if median_gated_1h is None or median_full_1h is None:
        verdict = "INCONCLUSIVE — 1h window not represented in both cohorts"
    elif median_gated_1h <= 0 and median_full_1h > 0:
        verdict = ("MEAL-DRIVEN — positive shift collapses (or reverses) "
                   "under meal gating; was a post-meal artifact")
    elif median_gated_1h >= median_full_1h:
        verdict = ("STRENGTHENED — gated 1h shift ≥ full; envelope coupling "
                   "is NOT driven by post-meal periods (meals add noise)")
    elif abs(median_gated_1h - median_full_1h) <= 0.2 * abs(median_full_1h):
        verdict = ("ROBUST — gated 1h shift within 20% of full; envelope "
                   "coupling persists outside meal periods")
    elif median_gated_1h < median_full_1h * 0.5:
        verdict = ("MOSTLY MEAL-DRIVEN — gated 1h shift <50% of full; "
                   "envelope coupling is partly a post-meal artifact")
    else:
        verdict = ("PARTIAL — gated 1h shift in [50%, 80%] of full; "
                   "real coupling exists but post-meal contributes")

    summary = {
        "experiment": "EXP-2874",
        "title": "Meal-gated re-run of EXP-2851 fast-scale envelope",
        "stream": "B",
        "meal_lookback_min": MEAL_LOOKBACK_MIN,
        "gate_fraction_non_meal": GATE_FRACTION,
        "windows_h": WINDOWS_HOURS,
        "full_by_window": full,
        "gated_by_window": gated,
        "deltas": diffs,
        "verdict": verdict,
    }
    (EXP / "exp-2874_summary.json").write_text(
        json.dumps(summary, indent=2, default=str)
    )

    # Figure
    fig, ax = plt.subplots(1, 1, figsize=(8, 5))
    full_df = pd.DataFrame(full)
    gated_df = pd.DataFrame(gated)
    if not full_df.empty:
        ax.plot(full_df["window_h"], full_df["median_shift_pct"],
                "o-", label="full cohort", color="#1f77b4")
    if not gated_df.empty:
        ax.plot(gated_df["window_h"], gated_df["median_shift_pct"],
                "s--", label="meal-gated", color="#d62728")
    ax.axhline(0, color="gray", ls=":", alpha=0.6)
    ax.set_xscale("log")
    ax.set_xticks(WINDOWS_HOURS)
    ax.set_xticklabels([f"{w}h" for w in WINDOWS_HOURS])
    ax.set_xlabel("Aggregation window")
    ax.set_ylabel("Median basal_shift_pct (elev/norm)")
    ax.set_title("EXP-2874 — Meal-gated envelope coupling\n"
                 "Does the post-bugfix positive shift survive meal gating?")
    ax.legend()
    ax.grid(alpha=0.3)
    plt.tight_layout()
    FIG.mkdir(parents=True, exist_ok=True)
    plt.savefig(FIG / "exp-2874_meal_gated_envelope.png", dpi=120)
    plt.close()

    print(f"\nVerdict: {verdict}")


if __name__ == "__main__":
    main()
