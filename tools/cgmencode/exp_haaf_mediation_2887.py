"""EXP-2887 — HAAF mediation of the oref1 counter-reg gap.

EXP-2886 found lineage means:
  Loop         CR intercept  0.975
  oref1 (Trio) CR intercept  0.767 (lowest)
  oref0        CR intercept  0.966

Hypothesis (HAAF feedback):
  Tighter oref1 defense -> more hypo exposure -> attenuated
  counter-regulation over time. If true, hypo_fraction mediates
  the lineage -> CR association.

Method:
  Path A:  lineage -> hypo_fraction  (does lineage predict exposure?)
  Path B:  hypo_fraction -> CR       (does exposure predict CR?)
          controlling for lineage (Path B | A)
  Path C:  lineage -> CR             (total effect)
  Path C': lineage -> CR | hypo_fraction  (direct effect after mediation)

  Mediation proportion = (C - C') / C

Small-n caveat: ~19 patients with complete data. Directional only.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]

PHENO = ROOT / "externals/experiments/exp-2886_phenotype.parquet"
HAAF = ROOT / "externals/experiments/exp-2878_haaf.parquet"
OUT = ROOT / "externals/experiments/exp-2887_mediation.parquet"
OUT_SUMMARY = ROOT / "externals/experiments/exp-2887_mediation_summary.json"
OUT_FIG = ROOT / "docs/60-research/figures/exp-2887_mediation.png"


def main() -> None:
    ph = pd.read_parquet(PHENO)
    haaf = pd.read_parquet(HAAF).reset_index()[
        ["patient_id", "hypo_fraction", "severe_fraction", "n_hypo"]
    ]
    df = ph.merge(haaf, on="patient_id", how="left", suffixes=("_ph", ""))
    # deduplicate columns
    for col in ("hypo_fraction", "severe_fraction"):
        if col + "_ph" in df.columns:
            df[col] = df[col].fillna(df[col + "_ph"])
            df = df.drop(columns=[col + "_ph"])
    df = df.dropna(subset=["counter_reg_intercept", "hypo_fraction", "lineage"])
    df = df[df.lineage != "unknown"]
    print(f"n patients with complete data: {len(df)}")
    print(df.lineage.value_counts())
    df.to_parquet(OUT, index=False)

    # Encode lineage as two dummy vars (baseline = Loop)
    df["is_oref1"] = (df.lineage == "oref1 (modern)").astype(int)
    df["is_oref0"] = (df.lineage == "oref0 (legacy)").astype(int)

    # Path A: lineage -> hypo_fraction
    X_a = sm.add_constant(df[["is_oref1", "is_oref0"]])
    mod_a = sm.OLS(df["hypo_fraction"], X_a).fit()

    # Path C: lineage -> CR (total effect)
    X_c = sm.add_constant(df[["is_oref1", "is_oref0"]])
    mod_c = sm.OLS(df["counter_reg_intercept"], X_c).fit()

    # Path B + C': lineage + hypo -> CR
    X_cp = sm.add_constant(df[["is_oref1", "is_oref0", "hypo_fraction"]])
    mod_cp = sm.OLS(df["counter_reg_intercept"], X_cp).fit()

    # Extract coefs
    a_oref1 = mod_a.params["is_oref1"]
    a_oref0 = mod_a.params["is_oref0"]
    c_oref1 = mod_c.params["is_oref1"]
    c_oref0 = mod_c.params["is_oref0"]
    cp_oref1 = mod_cp.params["is_oref1"]
    cp_oref0 = mod_cp.params["is_oref0"]
    b_hypo = mod_cp.params["hypo_fraction"]

    print("\nPath A: lineage -> hypo_fraction")
    print(mod_a.summary().tables[1])

    print("\nPath C: lineage -> CR (total effect)")
    print(mod_c.summary().tables[1])

    print("\nPath B + C': lineage + hypo -> CR")
    print(mod_cp.summary().tables[1])

    def med_prop(c, cp):
        if abs(c) < 1e-6:
            return None
        return float((c - cp) / c)

    mp_oref1 = med_prop(c_oref1, cp_oref1)
    mp_oref0 = med_prop(c_oref0, cp_oref0)

    # Indirect effect a*b and Sobel-like approximation
    se_a1 = mod_a.bse["is_oref1"]
    se_b = mod_cp.bse["hypo_fraction"]
    indirect_oref1 = a_oref1 * b_hypo
    sobel_se_oref1 = np.sqrt((b_hypo ** 2) * (se_a1 ** 2) +
                             (a_oref1 ** 2) * (se_b ** 2))
    sobel_z_oref1 = (indirect_oref1 / sobel_se_oref1
                     if sobel_se_oref1 > 0 else None)
    sobel_p_oref1 = (2 * (1 - stats.norm.cdf(abs(sobel_z_oref1)))
                     if sobel_z_oref1 is not None else None)

    print("\nMediation summary:")
    print(f"  Path A (lineage -> hypo_fraction):")
    print(f"    oref1: {a_oref1:+.4f}  p={mod_a.pvalues['is_oref1']:.3f}")
    print(f"    oref0: {a_oref0:+.4f}  p={mod_a.pvalues['is_oref0']:.3f}")
    print(f"  Path B (hypo_fraction -> CR | lineage):")
    print(f"    b    : {b_hypo:+.4f}  p={mod_cp.pvalues['hypo_fraction']:.3f}")
    print(f"  Path C  (total lineage -> CR):")
    print(f"    oref1: {c_oref1:+.4f}  p={mod_c.pvalues['is_oref1']:.3f}")
    print(f"    oref0: {c_oref0:+.4f}")
    print(f"  Path C' (direct lineage -> CR | hypo):")
    print(f"    oref1: {cp_oref1:+.4f}  p={mod_cp.pvalues['is_oref1']:.3f}")
    print(f"    oref0: {cp_oref0:+.4f}")
    print(f"  Mediation proportion oref1: {mp_oref1}")
    print(f"  Indirect effect (a*b) oref1: {indirect_oref1:+.4f}")
    print(f"  Sobel z={sobel_z_oref1:.3f}  p={sobel_p_oref1:.3f}")

    # Simple scatter: hypo_fraction vs CR, colored by lineage
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5))

    lineage_colors = {
        "Loop (iOS)": "#1f77b4",
        "oref1 (modern)": "#ff7f0e",
        "oref0 (legacy)": "#2ca02c",
    }
    for lin, sub in df.groupby("lineage"):
        axes[0].scatter(
            sub.hypo_fraction, sub.counter_reg_intercept,
            c=lineage_colors.get(lin, "gray"),
            label=f"{lin} (n={len(sub)})",
            s=80, edgecolor="black",
        )
    # Fit overall line
    xs = np.linspace(df.hypo_fraction.min(), df.hypo_fraction.max(), 50)
    slope, intercept, r, _, _ = stats.linregress(
        df.hypo_fraction, df.counter_reg_intercept
    )
    axes[0].plot(xs, intercept + slope * xs, "k--", alpha=0.5,
                 label=f"overall r={r:.2f}")
    axes[0].set_xlabel("hypo_fraction (HAAF exposure)")
    axes[0].set_ylabel("counter_reg_intercept")
    axes[0].set_title("HAAF exposure × counter-reg by lineage")
    axes[0].legend(fontsize=8)
    axes[0].grid(alpha=0.3)

    # Bar: mediation decomposition for oref1 vs Loop
    labels = ["total (C)", "direct (C')", "indirect (a×b)"]
    vals_oref1 = [c_oref1, cp_oref1, indirect_oref1]
    vals_oref0 = [c_oref0, cp_oref0, a_oref0 * b_hypo]
    x_pos = np.arange(len(labels))
    axes[1].bar(x_pos - 0.2, vals_oref1, 0.4, label="oref1",
                color=lineage_colors["oref1 (modern)"])
    axes[1].bar(x_pos + 0.2, vals_oref0, 0.4, label="oref0",
                color=lineage_colors["oref0 (legacy)"])
    axes[1].axhline(0, color="k", lw=0.5)
    axes[1].set_xticks(x_pos)
    axes[1].set_xticklabels(labels)
    axes[1].set_ylabel("effect on CR intercept (Δ vs Loop baseline)")
    med_title = (f"Mediation decomposition\n"
                 f"oref1 mediated prop: "
                 f"{mp_oref1 if mp_oref1 is None else f'{mp_oref1:.0%}'} | "
                 f"Sobel p={sobel_p_oref1:.3f}")
    axes[1].set_title(med_title)
    axes[1].legend(fontsize=8)
    axes[1].grid(axis="y", alpha=0.3)

    fig.suptitle(
        "EXP-2887 — Does HAAF exposure mediate the oref1 counter-reg gap?",
        fontsize=13,
    )
    fig.tight_layout()
    OUT_FIG.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_FIG, dpi=110)
    plt.close(fig)

    # Verdict
    if mp_oref1 is not None and mp_oref1 > 0.7 and sobel_p_oref1 < 0.1:
        verdict = (
            f"STRONG MEDIATION: {mp_oref1:.0%} of oref1 CR gap explained "
            f"by hypo exposure (Sobel p={sobel_p_oref1:.3f}). oref1 low CR "
            "is a downstream consequence of tight control, not intrinsic "
            "to the algorithm."
        )
    elif mp_oref1 is not None and mp_oref1 > 0.3:
        verdict = (
            f"PARTIAL MEDIATION: {mp_oref1:.0%} of oref1 CR gap mediated "
            f"by hypo_fraction (Sobel p={sobel_p_oref1:.3f}). Both exposure "
            "and direct lineage effects contribute."
        )
    elif mp_oref1 is not None and abs(mp_oref1) < 0.3:
        verdict = (
            f"NO MEDIATION: {mp_oref1:.0%} via hypo exposure. oref1 CR gap "
            "is either intrinsic to the algorithm lineage, driven by "
            "other confounders (age, diabetes duration, TDD), or a "
            "small-sample artifact."
        )
    else:
        verdict = (
            f"INCONCLUSIVE — mediation proportion {mp_oref1}, "
            f"Sobel p={sobel_p_oref1}. n={len(df)} too small to separate."
        )

    summary = {
        "exp_id": "2887",
        "n_patients": int(len(df)),
        "lineage_counts": df.lineage.value_counts().to_dict(),
        "path_A_lineage_to_hypo": {
            "oref1_coef": float(a_oref1),
            "oref1_p": float(mod_a.pvalues["is_oref1"]),
            "oref0_coef": float(a_oref0),
            "oref0_p": float(mod_a.pvalues["is_oref0"]),
            "r2": float(mod_a.rsquared),
        },
        "path_C_total_lineage_to_CR": {
            "oref1_coef": float(c_oref1),
            "oref1_p": float(mod_c.pvalues["is_oref1"]),
            "oref0_coef": float(c_oref0),
            "oref0_p": float(mod_c.pvalues["is_oref0"]),
            "r2": float(mod_c.rsquared),
        },
        "path_Cprime_direct_lineage_to_CR_given_hypo": {
            "oref1_coef": float(cp_oref1),
            "oref1_p": float(mod_cp.pvalues["is_oref1"]),
            "oref0_coef": float(cp_oref0),
            "hypo_coef": float(b_hypo),
            "hypo_p": float(mod_cp.pvalues["hypo_fraction"]),
            "r2": float(mod_cp.rsquared),
        },
        "mediation_proportion": {
            "oref1": mp_oref1,
            "oref0": mp_oref0,
        },
        "indirect_effect_oref1": {
            "value": float(indirect_oref1),
            "sobel_z": float(sobel_z_oref1),
            "sobel_p": float(sobel_p_oref1),
        },
        "verdict": verdict,
    }
    OUT_SUMMARY.write_text(json.dumps(summary, indent=2))
    print(f"\nVerdict: {verdict}")


if __name__ == "__main__":
    main()
