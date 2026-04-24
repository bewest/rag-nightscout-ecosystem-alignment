"""EXP-2987: Why do peers c/d/e/g suppress SMB at 70-100 while patient i fires?

Per EXP-2981/2985, patient i is a policy-outlier among Loop_AB_ON peers:
fires SMBs at 70-100 mg/dL where peers c/d/e/g do NOT, despite all five
patients having 5k-8k cells in that band.

Hypotheses tested per peer:
  (a) override_active suppresses SMB (low_temp_target / pre-meal mode)
  (b) recent carbs (within 30 min) elevate IOB above SMB cap
  (c) per-patient maxBolus/IOB cap difference (proxy: max observed iob)
  (d) higher iob threshold for the SMB-fire gate

For each peer, count cells in the 70-100 stratum with NO override AND no
recent carbs (last 30 min) AND iob below the patient-95th-percentile —
i.e., cells where SMB *could* fire by Loop's gate logic. Compare to cells
where SMB *did* fire.

Scope: AID-author audience.
What this is NOT: per-patient therapy advice; not a deterministic
reproduction of Loop's ABDose pre-condition (we don't have ABDose source
trace). This is a *behavioral correlate* showing which lever is most
asymmetric between i and peers.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent.parent
GRID = REPO / "externals" / "ns-parquet" / "training" / "grid.parquet"
OUT = REPO / "externals" / "experiments" / "exp-2987_summary.json"

PEERS = ["c", "d", "e", "g", "i"]
LO, HI = 70, 100
RECENT_CARB_MIN = 30


def main() -> None:
    g = pd.read_parquet(GRID)
    g = g[g.patient_id.isin(PEERS)].copy()
    g = g.sort_values(["patient_id", "time"]).reset_index(drop=True)

    rows = []
    for pid, sub in g.groupby("patient_id"):
        sub = sub.copy()
        in_band = sub.glucose.between(LO, HI, inclusive="both")
        n_band = int(in_band.sum())
        if n_band == 0:
            continue

        s = sub[in_band].copy()

        # Lever (a): override active in the cell
        n_override = int((s.get("override_active", 0) > 0).sum())

        # Lever (b): recent carbs (last 30 min)
        # time_since_carb_min already present
        if "time_since_carb_min" in s.columns:
            recent_carbs = (s["time_since_carb_min"] < RECENT_CARB_MIN) & s["time_since_carb_min"].notna()
            n_recent_carbs = int(recent_carbs.sum())
        else:
            recent_carbs = pd.Series(False, index=s.index)
            n_recent_carbs = 0

        # Lever (c): IOB cap proxy — patient's 95th-pct IOB
        iob = sub.get("iob", pd.Series(dtype=float))
        iob_p95 = float(iob.quantile(0.95)) if len(iob.dropna()) else np.nan
        iob_p50 = float(iob.median()) if len(iob.dropna()) else np.nan
        iob_max = float(iob.max()) if len(iob.dropna()) else np.nan
        if "iob" in s.columns and pd.notna(iob_p95):
            iob_above_cap = s["iob"] >= iob_p95
        else:
            iob_above_cap = pd.Series(False, index=s.index)
        n_iob_capped = int(iob_above_cap.sum())

        # Eligible: in band AND no override AND no recent carb AND iob below patient cap
        eligible = (~(s.get("override_active", 0) > 0)) & (~recent_carbs) & (~iob_above_cap)
        n_eligible = int(eligible.sum())

        # Fired
        n_fired = int((s["bolus_smb"] > 0).sum()) if "bolus_smb" in s.columns else 0
        n_fired_eligible = int(((s["bolus_smb"] > 0) & eligible).sum()) if "bolus_smb" in s.columns else 0

        rows.append({
            "patient_id": pid,
            "n_band_cells_70_100": n_band,
            "n_override_in_band": n_override,
            "frac_override": round(n_override / n_band, 4),
            "n_recent_carbs_in_band": n_recent_carbs,
            "frac_recent_carbs": round(n_recent_carbs / n_band, 4),
            "iob_p50": round(iob_p50, 3) if pd.notna(iob_p50) else None,
            "iob_p95": round(iob_p95, 3) if pd.notna(iob_p95) else None,
            "iob_max": round(iob_max, 3) if pd.notna(iob_max) else None,
            "n_iob_above_p95_in_band": n_iob_capped,
            "n_eligible_cells": n_eligible,
            "frac_eligible": round(n_eligible / n_band, 4),
            "n_smb_fired_in_band": n_fired,
            "fire_rate_overall": round(n_fired / n_band, 4),
            "fire_rate_eligible": round(n_fired_eligible / n_eligible, 4) if n_eligible else None,
            "suppression_rate_eligible": round(1 - n_fired_eligible / n_eligible, 4) if n_eligible else None,
        })

    df = pd.DataFrame(rows).sort_values("patient_id")
    print("\n=== EXP-2987 peer suppression at 70-100 ===")
    print(df.to_string(index=False))

    # Comparative levers — i vs peer mean
    i_row = df[df.patient_id == "i"].iloc[0] if (df.patient_id == "i").any() else None
    peers_df = df[df.patient_id.isin(["c", "d", "e", "g"])]
    if i_row is not None and len(peers_df):
        deltas = {}
        for col in ["frac_override", "frac_recent_carbs", "iob_p50", "iob_p95",
                    "fire_rate_overall", "fire_rate_eligible",
                    "suppression_rate_eligible"]:
            peer_mean = peers_df[col].mean()
            i_val = i_row[col]
            deltas[col] = {
                "i": float(i_val) if pd.notna(i_val) else None,
                "peer_mean": float(peer_mean) if pd.notna(peer_mean) else None,
                "delta_i_minus_peer": float(i_val - peer_mean) if (
                    pd.notna(i_val) and pd.notna(peer_mean)) else None,
            }
        print("\n=== i vs peer-mean deltas ===")
        for k, v in deltas.items():
            print(f"  {k:30s} i={v['i']!s:>10}  peers={v['peer_mean']!s:>10}  delta={v['delta_i_minus_peer']!s:>10}")

        ranked = sorted(
            [(k, abs(v["delta_i_minus_peer"])) for k, v in deltas.items()
             if v["delta_i_minus_peer"] is not None],
            key=lambda x: -x[1])
        top_lever = ranked[0][0] if ranked else None

        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps({
            "scope": "Peer suppression of SMB at 70-100 mg/dL among Loop_AB_ON patients (c,d,e,g) vs outlier i",
            "what_this_is_not": "Not a Loop ABDose source-trace; behavioral correlate only.",
            "per_patient": rows,
            "i_vs_peer_deltas": deltas,
            "top_asymmetric_lever": top_lever,
        }, indent=2, default=str))
        print(f"\n>>> Top asymmetric lever (|delta|): {top_lever}")
        print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
