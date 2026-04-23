"""EXP-2919 - Loop autobolus on/off latency split.

Derived autobolus configuration from EXP-2918 grid:
  bolus_smb sum > 0 => autobolus ENABLED
  bolus_smb sum = 0 => autobolus DISABLED

Tests whether Loop's internal heterogeneity in EXP-2918
basal-cut response rate (27-99%) is explained by autobolus
configuration. Counter-hypothesis from EXP-2894: maybe
autobolus-enabled patients deliver more SMBs and rely less on
deep basal cuts, while autobolus-disabled patients rely entirely
on basal cuts.

Scope: same as EXP-2916 - design comparison, not therapy advice.
"""
from __future__ import annotations
import json
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent.parent
GRID = REPO / "externals" / "ns-parquet" / "training" / "grid.parquet"
LATENCY = REPO / "externals" / "experiments" / "exp-2918_basal_cut_latency.parquet"
LINEAGE = REPO / "externals" / "experiments" / "exp-2891_simpson_dose_response.parquet"
SUMMARY = REPO / "externals" / "experiments" / "exp-2919_summary.json"
OUT = REPO / "externals" / "experiments" / "exp-2919_loop_autobolus_split.parquet"


def main() -> None:
    g = pd.read_parquet(GRID, columns=["patient_id", "bolus_smb"])
    smb_per_pt = g.groupby("patient_id")["bolus_smb"].agg(
        n_rows="count", smb_total="sum", smb_mean="mean"
    ).reset_index()
    smb_per_pt["autobolus_enabled"] = smb_per_pt["smb_total"] > 0
    smb_per_pt["smb_per_day"] = (
        smb_per_pt["smb_total"] / (smb_per_pt["n_rows"] / 288.0)
    )

    lat = pd.read_parquet(LATENCY)
    lat = lat.merge(
        smb_per_pt[["patient_id", "autobolus_enabled", "smb_per_day"]],
        on="patient_id", how="left",
    )

    loop_lat = lat[lat["lineage"] == "Loop (iOS)"].copy()
    found = loop_lat[loop_lat["found_cut"]].copy()

    by_config = (
        found.groupby("autobolus_enabled")["latency_min"]
        .agg(["count", "median", "mean", "std"])
        .rename(columns={"count": "n_episodes"})
    )

    per_pt_loop = lat[lat["lineage"] == "Loop (iOS)"].groupby(
        ["patient_id", "autobolus_enabled", "smb_per_day", "tercile"]
    ).agg(
        n_episodes=("found_cut", "size"),
        n_with_cut=("found_cut", "sum"),
        median_latency_min=("latency_min", "median"),
    ).reset_index()
    per_pt_loop["response_rate"] = per_pt_loop["n_with_cut"] / per_pt_loop["n_episodes"]

    per_pt_loop.to_parquet(OUT, index=False)

    # Counter-hypothesis: enabled patients have lower response rate
    # because SMB substitutes for deep basal cuts
    enabled = per_pt_loop[per_pt_loop["autobolus_enabled"]]["response_rate"].values
    disabled = per_pt_loop[~per_pt_loop["autobolus_enabled"]]["response_rate"].values

    summary = {
        "scope": "Loop autobolus on/off latency split. Design-level. Not therapy advice.",
        "loop_patients_by_config": (
            smb_per_pt[smb_per_pt.patient_id.isin(["a", "c", "d", "e", "f", "g", "i"])]
            .to_dict(orient="records")
        ),
        "latency_by_config": by_config.reset_index().to_dict(orient="records"),
        "per_patient_loop": per_pt_loop.to_dict(orient="records"),
        "counter_hypothesis_test": {
            "n_enabled": int(len(enabled)),
            "n_disabled": int(len(disabled)),
            "median_response_rate_enabled": (
                float(np.median(enabled)) if len(enabled) else None
            ),
            "median_response_rate_disabled": (
                float(np.median(disabled)) if len(disabled) else None
            ),
            "interpretation": (
                "If response_rate(enabled) < response_rate(disabled), "
                "autobolus substitutes for deep basal cuts. If similar, "
                "Loop heterogeneity is from another source."
            ),
        },
    }

    SUMMARY.write_text(json.dumps(summary, indent=2, default=str))
    print(f"[exp-2919] {SUMMARY}")
    print("\nLoop patients SMB profile:")
    print(smb_per_pt[smb_per_pt.patient_id.isin(['a','c','d','e','f','g','i'])].to_string(index=False))
    print("\nLatency by autobolus config (Loop only):")
    print(by_config.to_string())
    print("\nPer-patient Loop:")
    print(per_pt_loop.sort_values(["autobolus_enabled", "response_rate"]).to_string(index=False))


if __name__ == "__main__":
    main()
