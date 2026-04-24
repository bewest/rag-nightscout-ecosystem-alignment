"""EXP-2991: Per-patient policy-conservatism score for Loop_AB_ON peers.

Builds a composite "policy conservatism" score from observable proxies
for each Loop_AB_ON patient (c, d, e, g, i):

  * inferred_max_iob       = iob p95
  * inferred_max_bolus     = bolus_smb p95 over non-zero cells
  * suppression_70_100     = 1 - fire_rate among eligible cells in 70-100
  * basal_frac_of_tdd      = mean(net_basal) / mean(total dosing per day)
  * overshoot_rate         = frac of cells with eventual_bg > 180 conditional
                             on current BG in 100-180 (post-correction window)

Each proxy is min-max-normalised across the five peers; conservatism is
the mean of the normalised proxies, with `inferred_max_iob` and
`inferred_max_bolus` inverted (lower = more conservative).

Outputs:
  externals/experiments/exp-2991_policy_conservatism.parquet
  externals/experiments/exp-2991_summary.json

Scope: AID-author audience.
What this is NOT: not a per-user dosing recommendation; not a clinical
risk score; the proxies are observational and may be confounded by
behavioural (carbs, exercise) and physiological factors.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent.parent
GRID = REPO / "externals" / "ns-parquet" / "training" / "grid.parquet"
OUT_PARQUET = REPO / "externals" / "experiments" / "exp-2991_policy_conservatism.parquet"
OUT_JSON = REPO / "externals" / "experiments" / "exp-2991_summary.json"

PEERS = ["c", "d", "e", "g", "i"]
BAND_LO, BAND_HI = 70, 100
HIGH_BAND_LO, HIGH_BAND_HI = 100, 180
OVERSHOOT_THRESHOLD = 180


def per_patient_metrics(g: pd.DataFrame, pid: str) -> dict:
    sub = g[g.patient_id == pid].copy()
    n = len(sub)
    if n == 0:
        return {}

    iob_p95 = float(np.nanpercentile(sub.iob.dropna(), 95))
    smb_nz = sub.bolus_smb[sub.bolus_smb > 0]
    bolus_p95 = float(np.nanpercentile(smb_nz, 95)) if len(smb_nz) else 0.0

    in_band = sub.glucose.between(BAND_LO, BAND_HI, inclusive="both")
    band = sub[in_band].copy()
    no_override = (band.get("override_active", 0).fillna(0) == 0)
    no_recent_carbs = (band.get("time_since_carb_min", np.inf).fillna(np.inf) >= 30)
    iob_thr = np.nanpercentile(sub.iob.dropna(), 95)
    iob_below = (band.iob < iob_thr)
    eligible = no_override & no_recent_carbs & iob_below
    n_elig = int(eligible.sum())
    fired_elig = int(((band.bolus_smb > 0) & eligible).sum())
    suppress_70_100 = 1.0 - (fired_elig / n_elig if n_elig else 0.0)

    # actual_basal_rate (U/hr) * (5/60) cell width; bolus already in U/cell
    basal_units_per_cell = sub.actual_basal_rate.fillna(0) * (5.0 / 60.0)
    bolus_units_per_cell = sub.bolus.fillna(0)
    basal_total = float(basal_units_per_cell.sum())
    bolus_total = float(bolus_units_per_cell.sum())
    total = basal_total + bolus_total
    basal_frac = basal_total / total if total > 0 else np.nan

    # eventual_bg is empty for Loop patients; use forward glucose
    # window: max glucose in next 18 cells (~90 min) > 180 mg/dL
    sub_sorted = sub.sort_values("time").reset_index(drop=True)
    fut_max = (
        sub_sorted.glucose
        .iloc[::-1].rolling(window=18, min_periods=1).max().iloc[::-1]
        .reset_index(drop=True)
    )
    in_high = sub_sorted.glucose.between(HIGH_BAND_LO, HIGH_BAND_HI, inclusive="both")
    if int(in_high.sum()) > 0:
        overshoot_rate = float((fut_max[in_high] > OVERSHOOT_THRESHOLD).mean())
    else:
        overshoot_rate = np.nan

    return {
        "patient_id": pid,
        "n_cells": n,
        "iob_p95": iob_p95,
        "bolus_smb_p95": bolus_p95,
        "suppress_70_100_eligible": suppress_70_100,
        "basal_frac_of_tdd": basal_frac,
        "overshoot_rate_100_180": overshoot_rate,
    }


def normalize(vals: pd.Series, invert: bool = False) -> pd.Series:
    lo, hi = vals.min(), vals.max()
    if hi == lo:
        return pd.Series([0.5] * len(vals), index=vals.index)
    n = (vals - lo) / (hi - lo)
    return 1.0 - n if invert else n


def main() -> None:
    g = pd.read_parquet(GRID)
    g = g[g.patient_id.isin(PEERS)].copy()

    rows = [per_patient_metrics(g, pid) for pid in PEERS]
    df = pd.DataFrame(rows)

    # Composite conservatism: lower iob/bolus + higher suppression +
    # higher basal_frac → more conservative.
    df["norm_iob"] = normalize(df.iob_p95, invert=True)
    df["norm_bolus"] = normalize(df.bolus_smb_p95, invert=True)
    df["norm_suppress"] = normalize(df.suppress_70_100_eligible, invert=False)
    df["norm_basal_frac"] = normalize(df.basal_frac_of_tdd, invert=False)

    df["conservatism_score"] = df[
        ["norm_iob", "norm_bolus", "norm_suppress", "norm_basal_frac"]
    ].mean(axis=1)

    # Pearson correlation of conservatism vs overshoot
    r = df[["conservatism_score", "overshoot_rate_100_180"]].corr().iloc[0, 1]

    df = df.sort_values("conservatism_score", ascending=False).reset_index(drop=True)
    df.to_parquet(OUT_PARQUET, index=False)

    summary = {
        "patients": df.to_dict(orient="records"),
        "pearson_conservatism_vs_overshoot": float(r) if not np.isnan(r) else None,
        "interpretation": (
            "Higher conservatism_score = more conservative policy "
            "(lower IOB cap, smaller SMBs, higher 70-100 suppression, "
            "higher basal share). Negative correlation with overshoot "
            "would support the hypothesis that conservatism trades "
            "overshoot for slower recovery."
        ),
    }
    OUT_JSON.write_text(json.dumps(summary, indent=2))

    print(df.to_string(index=False))
    print(f"\nPearson(conservatism, overshoot) = {r:.3f}")
    print(f"Wrote {OUT_PARQUET}")
    print(f"Wrote {OUT_JSON}")


if __name__ == "__main__":
    main()
