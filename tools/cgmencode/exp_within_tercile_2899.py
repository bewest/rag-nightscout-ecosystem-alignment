"""EXP-2899: within-tercile heterogeneity in protection.

For each (lineage, aggressiveness tercile) cell from EXP-2891, compute
the patient-to-patient variance in aid_protection_severe.

Hypothesis: lineages differ not only in mean protection but in
patient-to-patient consistency. oref1 should show low within-cell
variance (algorithm normalises across users); Loop and oref0 may show
larger variance (more user-configurable).

Diagnostic: high variance within a cell signals a lineage where the
SAME settings can produce very different outcomes -> the audition
matrix needs to flag patients whose individual protection deviates
from their lineage-tercile median.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path("externals/experiments")
EXP_ID = "exp-2899"


def main() -> None:
    df = pd.read_parquet(OUT / "exp-2891_simpson_dose_response.parquet")
    df = df[df["lineage"] != "unknown"]

    cells = (
        df.groupby(["lineage", "tercile"])
        .agg(
            n=("patient_id", "size"),
            median_protection=("aid_protection_severe", "median"),
            iqr_protection=(
                "aid_protection_severe",
                lambda s: float(s.quantile(0.75) - s.quantile(0.25)),
            ),
            cv_protection=(
                "aid_protection_severe",
                lambda s: float(s.std() / s.mean()) if s.mean() != 0 else float("nan"),
            ),
            min_protection=("aid_protection_severe", "min"),
            max_protection=("aid_protection_severe", "max"),
        )
        .reset_index()
    )
    cells["range"] = cells["max_protection"] - cells["min_protection"]

    # Aggregate by lineage (across terciles)
    by_lineage = (
        df.groupby("lineage")["aid_protection_severe"]
        .agg(["count", "median", "std", "min", "max"])
        .reset_index()
    )
    by_lineage["range"] = by_lineage["max"] - by_lineage["min"]
    by_lineage["consistency_score"] = 1 - (
        by_lineage["std"] / by_lineage["median"].abs()
    )

    summary = {
        "exp_id": EXP_ID,
        "title": "Within-tercile heterogeneity in AID protection",
        "n_patients": int(df["patient_id"].nunique()),
        "cells": cells.to_dict("records"),
        "by_lineage": by_lineage.to_dict("records"),
        "interpretation": (
            "consistency_score = 1 - std/median. High score (close to "
            "1) means patient-to-patient outcomes are tight given "
            "lineage. Low/negative means lineage is high-variance: "
            "outcomes depend more on user configuration than algorithm."
        ),
    }
    out = OUT / f"{EXP_ID}_summary.json"
    out.write_text(json.dumps(summary, indent=2, default=str))
    print(json.dumps(summary, indent=2, default=str))
    print("\nCells:")
    print(cells.to_string(index=False))


if __name__ == "__main__":
    main()
