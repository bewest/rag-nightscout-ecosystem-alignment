"""EXP-2917 - Bootstrap CIs for design-cell protection means.

Refines EXP-2916: per (lineage, tercile) cell, computes 95% CI
on mean protection via stratified resampling. Critical for
honest reporting of n=1 oref0 cells.

Method:
  - For cells with n>=2: standard percentile bootstrap of patient
    means (resample patients with replacement within cell).
  - For cells with n=1: report point estimate with explicit
    'no CI possible (n=1)' flag.
  - Also report between-design gap CIs (e.g. oref1_cons - oref0_cons)
    by paired bootstrap.

Scope: design-level uncertainty quantification. Not therapy advice.
"""
from __future__ import annotations
import json
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent.parent
SRC = REPO / "externals" / "experiments" / "exp-2891_simpson_dose_response.parquet"
SUMMARY = REPO / "externals" / "experiments" / "exp-2917_summary.json"
OUT = REPO / "externals" / "experiments" / "exp-2917_design_cell_cis.parquet"

RNG = np.random.default_rng(42)
N_BOOT = 5000


def boot_mean_ci(values: np.ndarray) -> tuple[float, float, float, float]:
    n = len(values)
    if n == 0:
        return float("nan"), float("nan"), float("nan"), float("nan")
    if n == 1:
        v = float(values[0])
        return v, v, v, 0.0
    boots = []
    for _ in range(N_BOOT):
        s = RNG.choice(values, size=n, replace=True)
        boots.append(float(np.mean(s)))
    return (
        float(np.mean(values)),
        float(np.percentile(boots, 2.5)),
        float(np.percentile(boots, 97.5)),
        float(np.std(boots)),
    )


def main() -> None:
    df = pd.read_parquet(SRC)
    df = df[df["lineage"] != "unknown"].copy()

    rows = []
    for (ln, tier), g in df.groupby(["lineage", "tercile"]):
        vals = g["aid_protection_severe"].astype(float).values
        mean_, lo, hi, se = boot_mean_ci(vals)
        rows.append({
            "lineage": ln, "tercile": tier, "n": int(len(vals)),
            "mean_protection": mean_,
            "ci95_lo": lo, "ci95_hi": hi, "se": se,
            "ci_width": float(hi - lo),
            "ci_possible": bool(len(vals) >= 2),
        })
    cell_df = pd.DataFrame(rows)
    cell_df.to_parquet(OUT, index=False)

    # Pairwise design gaps per tercile with bootstrap
    pair_rows = []
    for tier in cell_df["tercile"].unique():
        tier_df = cell_df[cell_df["tercile"] == tier]
        lineages = list(tier_df["lineage"])
        for i, ln_a in enumerate(lineages):
            for ln_b in lineages[i + 1:]:
                vals_a = df[(df.lineage == ln_a) & (df.tercile == tier)][
                    "aid_protection_severe"].values
                vals_b = df[(df.lineage == ln_b) & (df.tercile == tier)][
                    "aid_protection_severe"].values
                if len(vals_a) == 0 or len(vals_b) == 0:
                    continue
                if len(vals_a) == 1 and len(vals_b) == 1:
                    gap = float(vals_a[0] - vals_b[0])
                    pair_rows.append({
                        "tercile": tier,
                        "design_a": ln_a, "n_a": 1,
                        "design_b": ln_b, "n_b": 1,
                        "gap_mean": gap,
                        "gap_ci_lo": gap, "gap_ci_hi": gap,
                        "ci_possible": False,
                    })
                    continue
                boots = []
                for _ in range(N_BOOT):
                    sa = RNG.choice(vals_a, size=len(vals_a), replace=True)
                    sb = RNG.choice(vals_b, size=len(vals_b), replace=True)
                    boots.append(float(np.mean(sa) - np.mean(sb)))
                pair_rows.append({
                    "tercile": tier,
                    "design_a": ln_a, "n_a": int(len(vals_a)),
                    "design_b": ln_b, "n_b": int(len(vals_b)),
                    "gap_mean": float(np.mean(vals_a) - np.mean(vals_b)),
                    "gap_ci_lo": float(np.percentile(boots, 2.5)),
                    "gap_ci_hi": float(np.percentile(boots, 97.5)),
                    "ci_excludes_zero": bool(
                        np.percentile(boots, 2.5) > 0
                        or np.percentile(boots, 97.5) < 0
                    ),
                    "ci_possible": True,
                })
    pair_df = pd.DataFrame(pair_rows)

    summary = {
        "scope": "Bootstrap CIs for design-cell protection. Design-level. Not therapy advice.",
        "cell_cis": cell_df.to_dict(orient="records"),
        "pairwise_design_gaps": pair_df.sort_values(
            by="gap_mean", key=lambda s: s.abs(), ascending=False
        ).to_dict(orient="records"),
        "n_pairs_with_significant_gap": int(
            pair_df.get("ci_excludes_zero", pd.Series([], dtype=bool)).sum()
        ),
    }

    SUMMARY.write_text(json.dumps(summary, indent=2, default=str))
    print(f"[exp-2917] {SUMMARY}")
    print("\nCell CIs:")
    print(cell_df.sort_values(["lineage", "tercile"]).to_string(index=False))
    print("\nPairwise design-gap CIs (sorted by |gap|):")
    print(pair_df.sort_values(
        by="gap_mean", key=lambda s: s.abs(), ascending=False
    ).to_string(index=False))


if __name__ == "__main__":
    main()
