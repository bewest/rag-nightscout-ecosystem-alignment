"""EXP-2900: per-patient deviation index from lineage-tercile median.

Operational triage signal: which patients within a lineage-tercile cell
deviate enough from the cell median to warrant individual investigation
(either over-performer = replicable best practice, or under-performer =
high tuning headroom)?

Two scopes:
  - cell deviation: protection - cell_median, where cell = (lineage, tercile)
  - lineage deviation: protection - lineage_median, when cell n < 3

Output:
  - per-patient deviation table with rank within lineage and within cell
  - flags: outlier_high (>= +1 SD from comparator) and outlier_low
    (<= -1 SD from comparator)
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path("externals/experiments")
EXP_ID = "exp-2900"


def main() -> None:
    df = pd.read_parquet(OUT / "exp-2891_simpson_dose_response.parquet")
    df = df[df["lineage"] != "unknown"].copy()

    # Cell stats
    cell_stats = (
        df.groupby(["lineage", "tercile"])["aid_protection_severe"]
        .agg(["count", "median", "std"])
        .reset_index()
        .rename(columns={"count": "cell_n", "median": "cell_median", "std": "cell_std"})
    )

    # Lineage-level stats (fallback when cell n < 3)
    lineage_stats = (
        df.groupby("lineage")["aid_protection_severe"]
        .agg(["count", "median", "std"])
        .reset_index()
        .rename(columns={"count": "lineage_n", "median": "lineage_median", "std": "lineage_std"})
    )

    out = df.merge(cell_stats, on=["lineage", "tercile"]).merge(lineage_stats, on="lineage")

    out["cell_deviation"] = out["aid_protection_severe"] - out["cell_median"]
    out["lineage_deviation"] = out["aid_protection_severe"] - out["lineage_median"]

    # Comparator: prefer cell when cell_n >= 3, else lineage
    use_cell = out["cell_n"] >= 3
    out["comparator"] = np.where(use_cell, "cell", "lineage")
    out["comparator_median"] = np.where(use_cell, out["cell_median"], out["lineage_median"])
    out["comparator_std"] = np.where(use_cell, out["cell_std"], out["lineage_std"])
    out["deviation"] = out["aid_protection_severe"] - out["comparator_median"]
    # z-score, guarded
    std_safe = out["comparator_std"].replace(0, np.nan)
    out["z_score"] = out["deviation"] / std_safe

    out["outlier_high"] = out["z_score"] >= 1.0
    out["outlier_low"] = out["z_score"] <= -1.0

    # Rank within lineage
    out["lineage_rank"] = (
        out.groupby("lineage")["aid_protection_severe"].rank(ascending=False, method="min").astype(int)
    )

    # Sort for report
    out = out.sort_values(["lineage", "tercile", "aid_protection_severe"], ascending=[True, True, False])

    keep_cols = [
        "patient_id", "lineage", "tercile", "aggressiveness",
        "aid_protection_severe", "comparator", "comparator_median",
        "comparator_std", "deviation", "z_score",
        "outlier_high", "outlier_low", "lineage_rank",
    ]
    out_min = out[keep_cols]

    out_path = OUT / f"{EXP_ID}_deviation.parquet"
    out_min.to_parquet(out_path, index=False)

    # Summary JSON
    summary = {
        "exp": EXP_ID,
        "n_patients": int(len(out_min)),
        "by_comparator": out_min.groupby("comparator").size().to_dict(),
        "outlier_high_count": int(out_min["outlier_high"].sum()),
        "outlier_low_count": int(out_min["outlier_low"].sum()),
        "outlier_high_patients": out_min[out_min["outlier_high"]][
            ["patient_id", "lineage", "tercile", "aid_protection_severe", "z_score"]
        ].to_dict(orient="records"),
        "outlier_low_patients": out_min[out_min["outlier_low"]][
            ["patient_id", "lineage", "tercile", "aid_protection_severe", "z_score"]
        ].to_dict(orient="records"),
    }
    (OUT / f"{EXP_ID}_summary.json").write_text(json.dumps(summary, indent=2, default=str))

    print(f"[{EXP_ID}] wrote {out_path} (n={len(out_min)})")
    print(f"  outliers high: {summary['outlier_high_count']}, low: {summary['outlier_low_count']}")
    for rec in summary["outlier_high_patients"]:
        print(f"    HIGH  {rec['patient_id']}  {rec['lineage']}/{rec['tercile']}  "
              f"prot={rec['aid_protection_severe']:.3f}  z={rec['z_score']:.2f}")
    for rec in summary["outlier_low_patients"]:
        print(f"    LOW   {rec['patient_id']}  {rec['lineage']}/{rec['tercile']}  "
              f"prot={rec['aid_protection_severe']:.3f}  z={rec['z_score']:.2f}")


if __name__ == "__main__":
    main()
