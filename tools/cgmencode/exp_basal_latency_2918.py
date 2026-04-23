"""EXP-2918 - Basal-cut latency by controller design.

Scope: scientific characterisation of how quickly each AID
controller design (Loop / oref0 / oref1) cuts basal once a
glucose descent begins. NOT therapy advice. Same scope statement
as EXP-2916.

Method:
  Per patient, walk the 5-min grid. For each independent descent
  episode (30-min rolling slope < -0.5 mg/dL/min while glucose in
  the 60-150 range), find the first 5-min cell at or after the
  descent onset where net_basal drops below the patient-specific
  p10 of net_basal (a normalized 'deep cut' threshold).
  Latency = minutes from descent onset to first deep-cut cell.

Why p10: avoids needing absolute scheduled basal rate, which is
not present in the unified grid for all 19 patients. The p10
threshold normalizes for pump scheduled-rate magnitude.

Output:
  per-event, per-patient latency in minutes; aggregate by lineage
  and tercile.

Caveats:
  - oref0 cohort is n=3 patients (each tercile has n=1, see
    EXP-2916 caveat).
  - Latency is per-design property; not patient-actionable.
"""
from __future__ import annotations
import json
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent.parent
GRID = REPO / "externals" / "ns-parquet" / "training" / "grid.parquet"
LINEAGE_SRC = REPO / "externals" / "experiments" / "exp-2891_simpson_dose_response.parquet"
SUMMARY = REPO / "externals" / "experiments" / "exp-2918_summary.json"
OUT_PARQUET = REPO / "externals" / "experiments" / "exp-2918_basal_cut_latency.parquet"


def detect_episodes(g: pd.DataFrame, p10_net_basal: float) -> list[dict]:
    """Return list of (descent_onset_idx, first_cut_idx, latency_min, ...)."""
    g = g.sort_values("time").reset_index(drop=True)
    glu = g["glucose"].astype(float).values
    nb = g["net_basal"].astype(float).values
    t = g["time"].values

    n = len(g)
    if n < 24:
        return []

    rolling_slope = pd.Series(glu).rolling(7, min_periods=4).apply(
        lambda x: (x.iloc[-1] - x.iloc[0]) / max(1, (len(x) - 1) * 5), raw=False
    ).values

    in_episode = False
    episodes = []
    onset = None
    for i in range(6, n):
        if not in_episode:
            if (rolling_slope[i] < -0.5 and 60 <= glu[i] <= 150
                    and glu[i] < glu[i - 6]):
                in_episode = True
                onset = i
        else:
            if i - onset > 36 or rolling_slope[i] > 0 or glu[i] < 55:
                first_cut = None
                for j in range(onset, min(n, onset + 36)):
                    if nb[j] <= p10_net_basal:
                        first_cut = j
                        break
                latency_min = (
                    (t[first_cut] - t[onset]).astype("timedelta64[m]").astype(int)
                    if first_cut is not None else None
                )
                episodes.append({
                    "onset_time": pd.Timestamp(t[onset]),
                    "onset_glucose": float(glu[onset]),
                    "min_glucose": float(np.nanmin(glu[onset:i + 1])),
                    "first_cut_idx_offset": (first_cut - onset) if first_cut is not None else None,
                    "latency_min": latency_min,
                    "found_cut": first_cut is not None,
                })
                in_episode = False
                onset = None
    return episodes


def main() -> None:
    print(f"[exp-2918] loading {GRID} ...")
    cols = ["patient_id", "time", "glucose", "net_basal"]
    grid = pd.read_parquet(GRID, columns=cols)
    grid["time"] = pd.to_datetime(grid["time"])

    lineage_df = pd.read_parquet(LINEAGE_SRC)[
        ["patient_id", "lineage", "tercile"]
    ]
    grid = grid.merge(lineage_df, on="patient_id", how="inner")
    grid = grid[grid["lineage"] != "unknown"].copy()

    rows = []
    for pid, g in grid.groupby("patient_id"):
        nb_p10 = float(np.percentile(g["net_basal"].dropna(), 10))
        eps = detect_episodes(g, nb_p10)
        ln = g["lineage"].iloc[0]
        tier = g["tercile"].iloc[0]
        for ep in eps:
            ep_row = {
                "patient_id": pid,
                "lineage": ln,
                "tercile": tier,
                "p10_net_basal": nb_p10,
                **ep,
            }
            rows.append(ep_row)

    out = pd.DataFrame(rows)
    out.to_parquet(OUT_PARQUET, index=False)

    # Aggregate by lineage
    found = out[out["found_cut"]].copy()
    by_lineage = (
        found.groupby("lineage")["latency_min"]
        .agg(["count", "median", "mean", "std",
              lambda x: float(np.percentile(x, 25)),
              lambda x: float(np.percentile(x, 75))])
    )
    by_lineage.columns = ["n_events", "median_min", "mean_min", "std_min", "q25", "q75"]

    by_lin_tier = (
        found.groupby(["lineage", "tercile"])["latency_min"]
        .agg(["count", "median"]).rename(columns={"count": "n", "median": "median_min"})
    )

    # Per-patient response rate (events with deep cut detected)
    by_patient = out.groupby(["patient_id", "lineage", "tercile"]).agg(
        n_episodes=("found_cut", "size"),
        n_with_cut=("found_cut", "sum"),
        median_latency_min=("latency_min", "median"),
    ).reset_index()
    by_patient["response_rate"] = by_patient["n_with_cut"] / by_patient["n_episodes"]

    summary = {
        "scope": (
            "Controller-design latency comparison; NOT per-patient "
            "advice. See exp-2916-design-gap-2026-04-23.md scope."
        ),
        "n_patients": int(grid["patient_id"].nunique()),
        "n_episodes_total": int(len(out)),
        "n_episodes_with_deep_cut": int(found.shape[0]),
        "by_lineage": by_lineage.reset_index().to_dict(orient="records"),
        "by_lineage_tercile": by_lin_tier.reset_index().to_dict(orient="records"),
        "by_patient": by_patient.to_dict(orient="records"),
    }
    SUMMARY.write_text(json.dumps(summary, indent=2, default=str))
    print(f"[exp-2918] {SUMMARY}")
    print("\nLatency to first deep basal cut after descent onset (minutes):")
    print(by_lineage.to_string())
    print("\nPer-patient response rate (frac of descent episodes with deep cut detected):")
    print(by_patient.sort_values(["lineage", "tercile"]).to_string(index=False))


if __name__ == "__main__":
    main()
