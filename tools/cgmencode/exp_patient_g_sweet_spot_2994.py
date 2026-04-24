"""EXP-2994: Patient `g` sweet-spot vignette.

EXP-2993 identified patient `g` (mid-conservatism Loop_AB_ON) as the
within-design sweet spot: lowest TTT_median (50 min) and lowest TAR
(0.191) among the 5 Loop_AB_ON peers (c/d/e/g/i).

This experiment characterises *how* g achieves it, then asks whether
the pattern is reproducible (low across-week variance) or
idiosyncratic.

Audience: open-source AID code authors. Not therapy advice.
What this is NOT: a recommendation that any patient adopt g's
settings; n=1 sweet spot — descriptive only.

Outputs:
  externals/experiments/exp-2994_patient_g_sweet_spot.parquet
  externals/experiments/exp-2994_patient_g_summary.json
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent.parent
GRID = REPO / "externals" / "ns-parquet" / "training" / "grid.parquet"
CONS = REPO / "externals" / "experiments" / "exp-2991_policy_conservatism.parquet"
OUT_PARQUET = REPO / "externals" / "experiments" / "exp-2994_patient_g_sweet_spot.parquet"
OUT_JSON = REPO / "externals" / "experiments" / "exp-2994_patient_g_summary.json"

PEERS = ["c", "d", "e", "g", "i"]
BANDS = [
    ("hypo", 0, 70),
    ("low", 70, 100),
    ("tir", 100, 180),
    ("hyper1", 180, 250),
    ("hyper2", 250, 1000),
]
INTERVAL_MIN = 5


def per_band_metrics(sub: pd.DataFrame) -> dict:
    out: dict = {}
    n_total = len(sub)
    smb_total = float((sub.bolus_smb > 0).sum())
    for name, lo, hi in BANDS:
        mask = (sub.glucose >= lo) & (sub.glucose < hi)
        n = int(mask.sum())
        if n == 0:
            out[f"{name}_frac"] = 0.0
            out[f"{name}_smb_rate_per_h"] = np.nan
            out[f"{name}_smb_mean_size_U"] = np.nan
            continue
        out[f"{name}_frac"] = float(n / n_total)
        smb = sub.bolus_smb[mask]
        smb_n = float((smb > 0).sum())
        out[f"{name}_smb_rate_per_h"] = float(smb_n / (n * INTERVAL_MIN / 60.0))
        out[f"{name}_smb_mean_size_U"] = float(smb[smb > 0].mean()) if smb_n else 0.0

    # Overshoot per starting band: P(forward 90-min max > 180 | now in band)
    fwd_max = sub.glucose.iloc[::-1].rolling(18, min_periods=1).max().iloc[::-1].reset_index(drop=True)
    g_idx = sub.glucose.reset_index(drop=True)
    for name, lo, hi in BANDS:
        mask = (g_idx >= lo) & (g_idx < hi)
        if int(mask.sum()) == 0:
            out[f"{name}_overshoot_rate"] = np.nan
        else:
            out[f"{name}_overshoot_rate"] = float((fwd_max[mask] > 180).mean())

    out["n_cells"] = n_total
    out["smb_count_total"] = int(smb_total)
    out["smb_per_day"] = float(smb_total / (n_total * INTERVAL_MIN / (60 * 24)))
    out["tir_70_180"] = float(((sub.glucose >= 70) & (sub.glucose < 180)).mean())
    out["tbr_under_70"] = float((sub.glucose < 70).mean())
    out["tar_over_180"] = float((sub.glucose >= 180).mean())
    out["mean_glucose"] = float(sub.glucose.mean())
    out["cv_glucose"] = float(sub.glucose.std() / sub.glucose.mean())
    return out


def reproducibility(sub: pd.DataFrame) -> dict:
    """Weekly partition: variance of TIR / TAR / overshoot across weeks."""
    sub = sub.copy()
    sub["week"] = pd.to_datetime(sub.time).dt.to_period("W")
    rows = []
    for wk, w in sub.groupby("week"):
        if len(w) < 200:
            continue
        fwd = w.glucose.iloc[::-1].rolling(18, min_periods=1).max().iloc[::-1].reset_index(drop=True)
        g_idx = w.glucose.reset_index(drop=True)
        in_band = (g_idx >= 100) & (g_idx < 180)
        rows.append({
            "week": str(wk),
            "n_cells": len(w),
            "tir": float(((w.glucose >= 70) & (w.glucose < 180)).mean()),
            "tbr": float((w.glucose < 70).mean()),
            "tar": float((w.glucose >= 180).mean()),
            "overshoot_100_180": float((fwd[in_band] > 180).mean()) if int(in_band.sum()) else np.nan,
        })
    if not rows:
        return {"n_weeks": 0}
    wk = pd.DataFrame(rows)
    return {
        "n_weeks": len(wk),
        "tir_mean": float(wk.tir.mean()),
        "tir_std": float(wk.tir.std()),
        "tir_cv": float(wk.tir.std() / wk.tir.mean()) if wk.tir.mean() else None,
        "tar_mean": float(wk.tar.mean()),
        "tar_std": float(wk.tar.std()),
        "overshoot_mean": float(wk.overshoot_100_180.mean()),
        "overshoot_std": float(wk.overshoot_100_180.std()),
        "tbr_mean": float(wk.tbr.mean()),
        "tbr_std": float(wk.tbr.std()),
    }


def main() -> None:
    g = pd.read_parquet(GRID)
    cons = pd.read_parquet(CONS)

    rows = []
    repro = {}
    for pid in PEERS:
        sub = g[g.patient_id == pid].sort_values("time").reset_index(drop=True)
        m = per_band_metrics(sub)
        m["patient_id"] = pid
        rows.append(m)
        repro[pid] = reproducibility(sub)

    df = pd.DataFrame(rows).merge(cons, on="patient_id")
    df.to_parquet(OUT_PARQUET, index=False)

    # Distinguish g from peers: rank-by-axis distance
    g_row = df[df.patient_id == "g"].iloc[0]
    peers_row = df[df.patient_id != "g"]
    settings_signature = {
        "iob_p95":       {"g": float(g_row.iob_p95),
                          "peer_mean": float(peers_row.iob_p95.mean()),
                          "peer_std": float(peers_row.iob_p95.std())},
        "bolus_smb_p95": {"g": float(g_row.bolus_smb_p95),
                          "peer_mean": float(peers_row.bolus_smb_p95.mean()),
                          "peer_std": float(peers_row.bolus_smb_p95.std())},
        "suppress_70_100_eligible":
                         {"g": float(g_row.suppress_70_100_eligible),
                          "peer_mean": float(peers_row.suppress_70_100_eligible.mean()),
                          "peer_std": float(peers_row.suppress_70_100_eligible.std())},
        "basal_frac_of_tdd":
                         {"g": float(g_row.basal_frac_of_tdd),
                          "peer_mean": float(peers_row.basal_frac_of_tdd.mean()),
                          "peer_std": float(peers_row.basal_frac_of_tdd.std())},
    }

    summary = {
        "per_patient_band_metrics": df.to_dict(orient="records"),
        "g_settings_signature_vs_peers": settings_signature,
        "weekly_reproducibility": repro,
        "interpretation": (
            "Settings axes where g sits >1 SD outside peer mean = the "
            "distinguishing signature. Reproducibility judged by "
            "weekly TIR/TAR/overshoot CV: low CV = g's pattern is "
            "stable (tunable target); high CV = g had a lucky window."
        ),
    }
    OUT_JSON.write_text(json.dumps(summary, indent=2, default=str))
    print(df.to_string(index=False))
    print("\nSettings signature:")
    print(json.dumps(settings_signature, indent=2))
    print("\nReproducibility (g):")
    print(json.dumps(repro["g"], indent=2))


if __name__ == "__main__":
    main()
