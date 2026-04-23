"""EXP-2916 — Controller-design protection-gap characterisation.

Scope: scientific comparison of AID controller-design protection
across load terciles. NOT a per-patient device-migration recommendation
surface. See docs/60-research/exp-2916-design-gap-2026-04-23.md
"Scope statement" for binding framing.

Method:
  1. Build cell-mean protection table (lineage x tercile) from
     EXP-2891 cohort (Guard-#6 verified per EXP-2904).
  2. For each patient, compute the per-cell design gap to alternative
     lineages at the same tercile: alt_protection - own_protection.
  3. Translate into per-patient design_gap_exposure (gap weighted by
     the patient's load): (alt_protection - own_protection) * cf.
  4. Aggregate at the design (lineage) level for AID-author audience.

Caveats:
  - n=1-4 per cell; bootstrap CI deferred to EXP-2917.
  - oref0-aggressive cell is n=1 manual-SMB outlier (EXP-2905);
    excluded from "reference design" claims in the report.
  - Output is a comparative-design metric only; never therapy advice
    for any individual patient.
"""
from __future__ import annotations
import json
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent.parent
SRC = REPO / "externals" / "experiments" / "exp-2891_simpson_dose_response.parquet"
SUMMARY = REPO / "externals" / "experiments" / "exp-2916_summary.json"
OUT_PARQUET = REPO / "externals" / "experiments" / "exp-2916_design_gap.parquet"

DESIGN_GAP_FLAG = 0.05


def main() -> None:
    df = pd.read_parquet(SRC)
    df = df[df["lineage"] != "unknown"].copy()

    cell_means = (
        df.groupby(["lineage", "tercile"])
        .agg(cell_mean_protection=("aid_protection_severe", "mean"),
             cell_n=("patient_id", "size"))
        .reset_index()
    )

    rows = []
    for _, p in df.iterrows():
        own_lineage = p["lineage"]
        own_protection = p["aid_protection_severe"]
        cf = p["cf_severe"]
        tier = p["tercile"]

        for alt_lineage in df["lineage"].unique():
            if alt_lineage == own_lineage:
                continue
            alt_cell = cell_means[
                (cell_means["lineage"] == alt_lineage) & (cell_means["tercile"] == tier)
            ]
            if alt_cell.empty:
                continue
            alt_mean = float(alt_cell["cell_mean_protection"].iloc[0])
            alt_n = int(alt_cell["cell_n"].iloc[0])

            design_gap_exposure = (alt_mean - own_protection) * cf
            rows.append({
                "patient_id": p["patient_id"],
                "own_lineage": own_lineage,
                "own_tercile": tier,
                "own_cf_severe": cf,
                "own_protection": own_protection,
                "alt_lineage": alt_lineage,
                "alt_cell_mean_protection": alt_mean,
                "alt_cell_n": alt_n,
                "delta_protection_design_level": alt_mean - own_protection,
                "design_gap_exposure": design_gap_exposure,
                "exceeds_5pp_threshold": design_gap_exposure > DESIGN_GAP_FLAG,
            })

    out = pd.DataFrame(rows)
    out.to_parquet(OUT_PARQUET, index=False)

    max_exposures = []
    for pid, g in out.groupby("patient_id"):
        best = g.sort_values("design_gap_exposure", ascending=False).iloc[0]
        max_exposures.append({
            "patient_id": pid,
            "own_lineage": best["own_lineage"],
            "own_tercile": best["own_tercile"],
            "own_protection": float(best["own_protection"]),
            "max_alt_design": best["alt_lineage"],
            "max_design_gap_exposure": float(best["design_gap_exposure"]),
            "exceeds_5pp_threshold": bool(best["exceeds_5pp_threshold"]),
        })
    max_df = pd.DataFrame(max_exposures).sort_values(
        "max_design_gap_exposure", ascending=False
    )

    cell_pairs = []
    for tier in cell_means["tercile"].unique():
        tier_cells = cell_means[cell_means["tercile"] == tier]
        for _, a in tier_cells.iterrows():
            for _, b in tier_cells.iterrows():
                if a["lineage"] >= b["lineage"]:
                    continue
                cell_pairs.append({
                    "tercile": tier,
                    "design_a": a["lineage"],
                    "design_b": b["lineage"],
                    "protection_a": float(a["cell_mean_protection"]),
                    "protection_b": float(b["cell_mean_protection"]),
                    "n_a": int(a["cell_n"]),
                    "n_b": int(b["cell_n"]),
                    "abs_gap": abs(float(a["cell_mean_protection"] - b["cell_mean_protection"])),
                })
    cell_pairs_df = pd.DataFrame(cell_pairs).sort_values("abs_gap", ascending=False)

    summary = {
        "scope": (
            "Controller-design protection comparison; NOT a per-patient "
            "device-migration recommendation. See exp-2916-design-gap-"
            "2026-04-23.md scope statement."
        ),
        "n_patients": int(out["patient_id"].nunique()),
        "n_patient_cells_above_5pp_design_gap": int(
            max_df["exceeds_5pp_threshold"].sum()
        ),
        "by_own_design": {
            ln: {
                "n_patients": int((max_df["own_lineage"] == ln).sum()),
                "n_above_5pp": int(
                    ((max_df["own_lineage"] == ln) & max_df["exceeds_5pp_threshold"]).sum()
                ),
                "mean_max_design_gap_exposure": float(
                    max_df.loc[max_df["own_lineage"] == ln, "max_design_gap_exposure"].mean()
                ),
            }
            for ln in max_df["own_lineage"].unique()
        },
        "largest_design_gaps_cell_level": cell_pairs_df.head(5).to_dict(orient="records"),
        "cell_means": cell_means.to_dict(orient="records"),
        "low_confidence_cells_n_le_1": [
            {"lineage": r["lineage"], "tercile": r["tercile"], "n": int(r["cell_n"])}
            for _, r in cell_means.iterrows() if r["cell_n"] <= 1
        ],
    }

    SUMMARY.write_text(json.dumps(summary, indent=2, default=str))
    print(f"[exp-2916] {SUMMARY}")
    print(json.dumps(summary, indent=2, default=str))
    print("\nLargest design-level cell gaps:")
    print(cell_pairs_df.head(5).to_string(index=False))


if __name__ == "__main__":
    main()
