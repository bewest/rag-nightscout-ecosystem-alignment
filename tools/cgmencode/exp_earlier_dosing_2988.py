"""EXP-2988: Earlier-dosing hypothesis in 100-140 ascent before 70-100 entry.

EXP-2982 ruled out PAF cap as the overshoot-preventing lever.
Alternative hypothesis: peers c/d/e/g fire SMBs DURING the 100-140
ascent leading INTO a 70-100 entry, dosing the rise BEFORE it
matters. Patient i fires AT 70-100 instead.

Method:
  - For each Loop_AB_ON peer (c,d,e,g,i):
    - Identify "70-100 entries" = transitions glucose <70 -> [70,100]
      OR a sustained dwell starting at boundary
    - Look back 60 min before entry; in cells where 100 <= glucose < 140
      and glucose_roc > 0 (rising), count SMB fires
  - Compare per-patient pre-entry SMB rate (i vs peers).

If peers' pre-entry rate >> i, that explains why peers don't NEED to
fire AT 70-100 — they already dosed.

Scope: AID-author audience.
What this is NOT: not a control-system simulation; behavioral
correlate using observational grid data only.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent.parent
GRID = REPO / "externals" / "ns-parquet" / "training" / "grid.parquet"
OUT = REPO / "externals" / "experiments" / "exp-2988_summary.json"

PEERS = ["c", "d", "e", "g", "i"]
LO, HI = 70, 100
ASCENT_LO, ASCENT_HI = 100, 140
LOOKBACK_MIN = 60
LOOKBACK_CELLS = LOOKBACK_MIN // 5  # 12 cells


def main() -> None:
    g = pd.read_parquet(GRID)
    g = g[g.patient_id.isin(PEERS)].copy()
    g = g.sort_values(["patient_id", "time"]).reset_index(drop=True)

    rows = []
    for pid, sub in g.groupby("patient_id"):
        sub = sub.sort_values("time").reset_index(drop=True)
        gluc = sub.glucose.values
        smb = sub.bolus_smb.values if "bolus_smb" in sub.columns else np.zeros(len(sub))
        roc = sub.glucose_roc.values if "glucose_roc" in sub.columns else np.zeros(len(sub))

        # Identify 70-100 ENTRY events: glucose transitions from outside
        # band into [70,100]. We require prior cell glucose < 70 OR
        # prior cell glucose > 100 (entering from below or above).
        in_band = (gluc >= LO) & (gluc <= HI)
        # entry: in_band[i] True and in_band[i-1] False
        entries = np.flatnonzero(in_band[1:] & ~in_band[:-1]) + 1
        n_entries = len(entries)

        # For each entry, look back LOOKBACK_CELLS cells. Within that
        # window, count cells in 100-140 ascent (glucose_roc > 0) that
        # had an SMB fire vs total ascent cells.
        ascent_total = 0
        ascent_fired = 0
        for e in entries:
            lo_idx = max(0, e - LOOKBACK_CELLS)
            window_g = gluc[lo_idx:e]
            window_smb = smb[lo_idx:e]
            window_roc = roc[lo_idx:e]
            mask_ascent = (
                (window_g >= ASCENT_LO) & (window_g < ASCENT_HI)
                & (window_roc > 0)
            )
            ascent_total += int(mask_ascent.sum())
            ascent_fired += int(((window_smb > 0) & mask_ascent).sum())

        # Marginal rate: among ALL 100-140 ascent cells (not entry-conditional)
        all_ascent_mask = (gluc >= ASCENT_LO) & (gluc < ASCENT_HI) & (roc > 0)
        all_ascent_total = int(all_ascent_mask.sum())
        all_ascent_fired = int(((smb > 0) & all_ascent_mask).sum())

        rows.append({
            "patient_id": pid,
            "n_70_100_entries": n_entries,
            "pre_entry_ascent_cells_60min": ascent_total,
            "pre_entry_ascent_smb_fired": ascent_fired,
            "pre_entry_fire_rate": round(ascent_fired / ascent_total, 4) if ascent_total else None,
            "marginal_ascent_cells": all_ascent_total,
            "marginal_ascent_smb_fired": all_ascent_fired,
            "marginal_fire_rate": round(all_ascent_fired / all_ascent_total, 4) if all_ascent_total else None,
        })

    df = pd.DataFrame(rows).sort_values("patient_id")
    print("\n=== EXP-2988 pre-entry ascent dosing ===")
    print(df.to_string(index=False))

    i_row = df[df.patient_id == "i"].iloc[0] if (df.patient_id == "i").any() else None
    peers_df = df[df.patient_id.isin(["c", "d", "e", "g"])]
    if i_row is not None and len(peers_df):
        peer_pre_rate = peers_df.pre_entry_fire_rate.dropna().mean()
        peer_marg_rate = peers_df.marginal_fire_rate.dropna().mean()
        print(f"\ni pre_entry_fire_rate={i_row.pre_entry_fire_rate}  peer_mean={peer_pre_rate:.4f}")
        print(f"i marginal_fire_rate ={i_row.marginal_fire_rate}  peer_mean={peer_marg_rate:.4f}")

        peers_dose_earlier = (peer_pre_rate is not None
                              and i_row.pre_entry_fire_rate is not None
                              and peer_pre_rate > i_row.pre_entry_fire_rate)
        verdict = (
            "POSITIVE: peers fire MORE in 100-140 ascent before 70-100 entry; "
            "supports earlier-dosing hypothesis."
            if peers_dose_earlier else
            "NEGATIVE/NULL: peers do NOT fire more pre-entry; earlier-dosing "
            "hypothesis NOT supported. The dosing asymmetry stays at the "
            "70-100 band itself (per EXP-2987)."
        )
        print(f"\n>>> VERDICT: {verdict}")
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps({
            "scope": "Earlier-dosing hypothesis: do peers dose during 100-140 ascent "
                     "before 70-100 entry, explaining 70-100 quiescence?",
            "what_this_is_not": "Not a control-system simulation; observational only.",
            "per_patient": rows,
            "i_pre_entry_rate": float(i_row.pre_entry_fire_rate)
                if i_row.pre_entry_fire_rate is not None else None,
            "peer_pre_entry_mean": float(peer_pre_rate)
                if peer_pre_rate is not None else None,
            "i_marginal_ascent_rate": float(i_row.marginal_fire_rate)
                if i_row.marginal_fire_rate is not None else None,
            "peer_marginal_ascent_mean": float(peer_marg_rate)
                if peer_marg_rate is not None else None,
            "verdict": verdict,
        }, indent=2, default=str))
        print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
