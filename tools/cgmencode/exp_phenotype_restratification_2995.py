"""EXP-2995: Re-stratify EXP-2886 phenotype clusters by algorithm_mode.

EXP-2886 produced three orthogonal phenotype axes (stacking, braking,
counter-regulation) and 8 archetypes. EXP-2992 added the
`algorithm_mode` schema column (Loop-AB-ON, Loop-AB-OFF, Trio-oref1,
AAPS-oref0, unknown). EXP-2986 fixed the AAPS labelling.

Question: do EXP-2886's phenotype clusters ALIGN with algorithm_mode
(implying the 'phenotype' was confounded by AID-design — i.e. an
algorithm signature, not a patient signature), or do they CROSS-CUT
algorithm_mode (implying the phenotype is patient-physiology
heterogeneity that survives algorithm assignment)?

Audience: open-source AID code authors. Not therapy advice.
What this is NOT: a re-classification of any individual patient; the
n's per cell remain too small for definitive claims (max cell = 5).

Outputs:
  externals/experiments/exp-2995_phenotype_x_algorithm_mode.parquet
  externals/experiments/exp-2995_summary.json
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent.parent
COHORT = REPO / "externals" / "experiments" / "exp-2891_simpson_dose_response.parquet"
OUT_PARQUET = REPO / "externals" / "experiments" / "exp-2995_phenotype_x_algorithm_mode.parquet"
OUT_JSON = REPO / "externals" / "experiments" / "exp-2995_summary.json"


def cramers_v(ct: pd.DataFrame) -> float:
    """Cramér's V (bias-corrected) for a contingency table."""
    chi2 = 0.0
    n = float(ct.values.sum())
    row_t = ct.sum(axis=1).values
    col_t = ct.sum(axis=0).values
    for i in range(ct.shape[0]):
        for j in range(ct.shape[1]):
            e = row_t[i] * col_t[j] / n
            if e > 0:
                chi2 += (ct.iloc[i, j] - e) ** 2 / e
    r, k = ct.shape
    if min(r, k) <= 1 or n == 0:
        return float("nan")
    phi2 = chi2 / n
    phi2c = max(0.0, phi2 - (r - 1) * (k - 1) / (n - 1))
    rc = r - (r - 1) ** 2 / (n - 1)
    kc = k - (k - 1) ** 2 / (n - 1)
    denom = min(rc - 1, kc - 1)
    return float(np.sqrt(phi2c / denom)) if denom > 0 else float("nan")


def main() -> None:
    df = pd.read_parquet(COHORT)
    keep = [
        "patient_id", "archetype", "lineage", "algorithm_mode",
        "stack_score", "braking_ratio", "counter_reg_intercept",
        "hidden_leverage", "aggressiveness", "tercile",
    ]
    df = df[[c for c in keep if c in df.columns]].copy()
    df.to_parquet(OUT_PARQUET, index=False)

    # Confusion: archetype × algorithm_mode
    ct_arch = pd.crosstab(df.archetype, df.algorithm_mode)
    v_arch = cramers_v(ct_arch)

    # Confusion: lineage × algorithm_mode (sanity — should be HIGH because
    # algorithm_mode is a refinement of lineage)
    ct_lin = pd.crosstab(df.lineage, df.algorithm_mode)
    v_lin = cramers_v(ct_lin)

    # Per-mode mean phenotype scores (continuous, more powerful than
    # archetype labels)
    by_mode = df.groupby("algorithm_mode")[
        ["stack_score", "braking_ratio", "counter_reg_intercept", "hidden_leverage"]
    ].agg(["mean", "std", "count"])

    # Within-mode dispersion: if the phenotype CROSS-CUTS mode, within-mode
    # std should be comparable to overall std (i.e. each mode contains the
    # full spectrum). If phenotype ALIGNS with mode, within-mode std should
    # be small relative to between-mode std.
    overall_std = df[
        ["stack_score", "braking_ratio", "counter_reg_intercept"]
    ].std()
    within_mode_std = df.groupby("algorithm_mode")[
        ["stack_score", "braking_ratio", "counter_reg_intercept"]
    ].std()
    within_over_overall = (within_mode_std / overall_std).round(3)

    # ANOVA-style eta^2 per phenotype axis vs algorithm_mode
    def eta2(col: str) -> float:
        x = df[[col, "algorithm_mode"]].dropna()
        if x.empty:
            return float("nan")
        grand = x[col].mean()
        ss_total = ((x[col] - grand) ** 2).sum()
        ss_between = sum(
            len(g) * (g[col].mean() - grand) ** 2
            for _, g in x.groupby("algorithm_mode")
        )
        return float(ss_between / ss_total) if ss_total > 0 else float("nan")

    eta_table = {
        c: eta2(c)
        for c in ["stack_score", "braking_ratio", "counter_reg_intercept", "hidden_leverage"]
    }

    summary = {
        "n_patients": int(len(df)),
        "algorithm_mode_counts": df.algorithm_mode.value_counts().to_dict(),
        "archetype_counts": df.archetype.value_counts().to_dict(),
        "contingency_archetype_x_mode": ct_arch.to_dict(),
        "cramers_v_archetype_vs_mode": v_arch,
        "contingency_lineage_x_mode": ct_lin.to_dict(),
        "cramers_v_lineage_vs_mode": v_lin,
        "phenotype_mean_by_mode": {
            "__".join(map(str, k)): v
            for k, v in by_mode.round(3).stack().stack().to_dict().items()
        },
        "within_mode_std_over_overall_std": within_over_overall.to_dict(),
        "eta_squared_phenotype_vs_mode": eta_table,
        "interpretation": (
            "Cramér's V near 1.0 = archetypes ALIGN with algorithm_mode "
            "(phenotype was a design-confounded label). Cramér's V near "
            "0.0 = archetypes CROSS-CUT mode (genuine patient "
            "heterogeneity). eta^2 quantifies the same for the "
            "continuous phenotype axes."
        ),
    }
    OUT_JSON.write_text(json.dumps(summary, indent=2, default=str))

    print("=== Archetype × algorithm_mode ===")
    print(ct_arch)
    print(f"\nCramér's V (archetype vs algorithm_mode) = {v_arch:.3f}")
    print(f"Cramér's V (lineage   vs algorithm_mode) = {v_lin:.3f}")
    print("\n=== eta^2 (continuous phenotype vs mode) ===")
    for k, v in eta_table.items():
        print(f"  {k:30s}: {v:.3f}")
    print("\n=== Within-mode std / overall std ===")
    print(within_over_overall.to_string())


if __name__ == "__main__":
    main()
