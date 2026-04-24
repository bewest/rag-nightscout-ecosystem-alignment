"""EXP-2993: Within-Loop_AB_ON outcome stratification by policy tertile.

Uses EXP-2991's `conservatism_score` to split the 5 Loop_AB_ON
patients (c, d, e, g, i) into aggressive / mid / conservative tertiles
and compares two outcome families per tertile:

  (1) Overshoot: frac(future-90-min max BG > 180) | current BG in 100-180
      (already in EXP-2991).
  (2) Time-to-target (TTT) recovery: median minutes from first cell
      with BG > 180 in a hyperglycemic excursion to first BG ≤ 180.

Hypothesis (per task spec):
  aggressive Loop_AB_ON (patient i style) trades higher overshoot for
  faster TTT vs conservative Loop_AB_ON (peers c/d/e/g) trades lower
  overshoot for slower recovery.

Scope: AID-author audience.
What this is NOT: not a clinical recommendation; not a counterfactual
estimate of what would happen if patient i changed settings; the
"trade-off" interpretation is descriptive, not causal.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent.parent
GRID = REPO / "externals" / "ns-parquet" / "training" / "grid.parquet"
CONS = REPO / "externals" / "experiments" / "exp-2991_policy_conservatism.parquet"
OUT_PARQUET = REPO / "externals" / "experiments" / "exp-2993_within_loopabon.parquet"
OUT_JSON = REPO / "externals" / "experiments" / "exp-2993_summary.json"

PEERS = ["c", "d", "e", "g", "i"]
HIGH = 180
TARGET = 180  # ceiling of acceptable; "back to target" = BG <= 180
INTERVAL_MIN = 5  # 5-min cells


def excursion_durations(glucose: pd.Series) -> list[float]:
    """Return list of minutes for each contiguous BG > 180 run."""
    high = (glucose > HIGH).astype(int).values
    durations = []
    in_run = False
    start = None
    for i, x in enumerate(high):
        if x and not in_run:
            in_run = True
            start = i
        elif not x and in_run:
            in_run = False
            durations.append((i - start) * INTERVAL_MIN)
    if in_run:
        durations.append((len(high) - start) * INTERVAL_MIN)
    return durations


def per_patient_outcomes(g: pd.DataFrame, pid: str) -> dict:
    sub = g[g.patient_id == pid].sort_values("time").reset_index(drop=True)

    # Forward 90-min max
    fwd = sub.glucose.iloc[::-1].rolling(18, min_periods=1).max().iloc[::-1].reset_index(drop=True)
    in_band = sub.glucose.between(100, 180, inclusive="both")
    overshoot = float((fwd[in_band] > HIGH).mean()) if int(in_band.sum()) else np.nan

    # TTT (excursion durations)
    durs = excursion_durations(sub.glucose)
    ttt_med = float(np.median(durs)) if durs else np.nan
    ttt_mean = float(np.mean(durs)) if durs else np.nan

    # Time above range fraction
    tar = float((sub.glucose > HIGH).mean())

    return dict(
        patient_id=pid,
        overshoot_rate=overshoot,
        ttt_median_min=ttt_med,
        ttt_mean_min=ttt_mean,
        tar_frac=tar,
        n_excursions=len(durs),
    )


def main() -> None:
    g = pd.read_parquet(GRID)
    cons = pd.read_parquet(CONS)[["patient_id", "conservatism_score"]]

    rows = [per_patient_outcomes(g, pid) for pid in PEERS]
    out = pd.DataFrame(rows).merge(cons, on="patient_id")

    # Tertile split: 5 patients -> bottom/mid/top (2/1/2 by score rank)
    out = out.sort_values("conservatism_score", ascending=True).reset_index(drop=True)
    out["tertile"] = ["aggressive", "aggressive", "mid", "conservative", "conservative"][:len(out)]

    out.to_parquet(OUT_PARQUET, index=False)

    by_tert = (
        out.groupby("tertile")[["overshoot_rate", "ttt_median_min", "ttt_mean_min", "tar_frac"]]
        .mean()
        .to_dict(orient="index")
    )

    summary = {
        "per_patient": out.to_dict(orient="records"),
        "tertile_means": by_tert,
        "spearman_conservatism_vs_overshoot": float(
            out[["conservatism_score", "overshoot_rate"]].corr(method="spearman").iloc[0, 1]
        ),
        "spearman_conservatism_vs_ttt_median": float(
            out[["conservatism_score", "ttt_median_min"]].corr(method="spearman").iloc[0, 1]
        ),
        "spearman_conservatism_vs_tar": float(
            out[["conservatism_score", "tar_frac"]].corr(method="spearman").iloc[0, 1]
        ),
        "interpretation": (
            "If aggressive tertile shows higher overshoot AND lower TTT "
            "(faster recovery), the trade-off hypothesis is supported. "
            "If overshoot is independent of conservatism, no dial exists "
            "(NULL). With only 5 patients, ranks are reported as "
            "qualitative direction; not p-tested."
        ),
    }
    OUT_JSON.write_text(json.dumps(summary, indent=2))
    print(out.to_string(index=False))
    print()
    print("Tertile means:")
    for k, v in by_tert.items():
        print(f"  {k}: {v}")
    print()
    print(f"Spearman(conservatism, overshoot) = {summary['spearman_conservatism_vs_overshoot']:.3f}")
    print(f"Spearman(conservatism, TTT_median) = {summary['spearman_conservatism_vs_ttt_median']:.3f}")
    print(f"Spearman(conservatism, TAR_frac)   = {summary['spearman_conservatism_vs_tar']:.3f}")


if __name__ == "__main__":
    main()
