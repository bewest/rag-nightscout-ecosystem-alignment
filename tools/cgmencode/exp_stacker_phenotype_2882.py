"""EXP-2882 — Per-patient evening-stacking phenotype.

EXP-2881 established cohort-level evening bolus stacking as dominant
evening-hypo driver. This experiment derives a per-patient
stacking_score and tests whether it correlates with:
  - controller type (Loop vs Trio)
  - TDD (larger-TDD patients may stack more boluses?)
  - counter-reg intercept (EXP-2875)
  - β_nadir (EXP-2877)
  - hypo_fraction (EXP-2878)

Per-patient stacking_score:
  delta_bolus4h_ev_vs_rest  —  evening 4h-bolus median minus rest median
  delta_iob_start_ev_vs_rest — evening IOB-start median minus rest median
  composite_stacking_score  — average of rank-normalized versions

Output: per-patient parquet + summary + figure.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]

EV_2881 = ROOT / "externals/experiments/exp-2881_evening_drivers.parquet"
PP_2877 = ROOT / "externals/experiments/exp-2877_per_patient.parquet"
EV_2875 = ROOT / "externals/experiments/exp-2875_counter_regulation_events.parquet"
HAAF_2878 = ROOT / "externals/experiments/exp-2878_haaf.parquet"

OUT = ROOT / "externals/experiments/exp-2882_stacker_phenotype.parquet"
OUT_SUMMARY = ROOT / "externals/experiments/exp-2882_stacker_phenotype_summary.json"
OUT_FIG = ROOT / "docs/60-research/figures/exp-2882_stacker_phenotype.png"


def main() -> None:
    print("Loading inputs...")
    df = pd.read_parquet(EV_2881)
    pp_cr = pd.read_parquet(PP_2877).set_index("patient_id")
    haaf = pd.read_parquet(HAAF_2878)
    if haaf.index.name != "patient_id" and "patient_id" in haaf.columns:
        haaf = haaf.set_index("patient_id")
    ev_2875 = pd.read_parquet(EV_2875)
    print(f"  2881 events: {len(df)}, patients {df.patient_id.nunique()}")

    # Per-patient aggregates
    rows = []
    for pid, g in df.groupby("patient_id"):
        ev = g[g.tod == "evening"]
        rest = g[g.tod != "evening"]
        if len(ev) < 3 or len(rest) < 10:
            continue
        controller = g.controller.iloc[0] if g.controller.notna().any() else None
        # Approximate TDD: total bolus / days for this patient in events
        # Use 4h bolus median as a crude proxy, actual TDD requires grid
        row = {
            "patient_id": pid,
            "controller": controller,
            "n_evening_events": len(ev),
            "n_rest_events": len(rest),
            "evening_bolus4h_med": float(ev.bolus_4h.median()),
            "rest_bolus4h_med": float(rest.bolus_4h.median()),
            "delta_bolus4h": float(ev.bolus_4h.median() - rest.bolus_4h.median()),
            "evening_iob_start_med": float(ev.iob_start.median()),
            "rest_iob_start_med": float(rest.iob_start.median()),
            "delta_iob_start": float(
                ev.iob_start.median() - rest.iob_start.median()
            ),
            "evening_descent_med": float(ev.descent_slope.median()),
            "rest_descent_med": float(rest.descent_slope.median()),
            "delta_descent": float(
                ev.descent_slope.median() - rest.descent_slope.median()
            ),
            "evening_sched_basal_med": float(ev.sched_basal.median()),
            "rest_sched_basal_med": float(rest.sched_basal.median()),
            "delta_sched_basal": float(
                ev.sched_basal.median() - rest.sched_basal.median()
            ),
        }
        rows.append(row)
    pp = pd.DataFrame(rows).set_index("patient_id")
    print(f"  per-patient n={len(pp)}")

    # Attach counter-reg signals
    pp["counter_reg_intercept"] = pp_cr["intercept"]
    pp["counter_reg_beta_nadir"] = pp_cr["beta_nadir"]
    if "hypo_fraction" in haaf.columns:
        pp["hypo_fraction"] = haaf["hypo_fraction"]
    if "severe_fraction" in haaf.columns:
        pp["severe_fraction"] = haaf["severe_fraction"]

    # Composite stacking score: rank-normalize delta_bolus4h + delta_iob_start
    def rank_norm(s: pd.Series) -> pd.Series:
        return s.rank(pct=True)
    pp["stack_score"] = 0.5 * (
        rank_norm(pp["delta_bolus4h"]) + rank_norm(pp["delta_iob_start"])
    )

    pp.to_parquet(OUT)

    # Summary stats
    summary = {
        "exp_id": "2882",
        "n_patients": int(len(pp)),
        "cohort_medians": {
            c: float(pp[c].median())
            for c in [
                "delta_bolus4h", "delta_iob_start", "delta_descent",
                "delta_sched_basal",
            ]
        },
        "frac_positive_bolus4h": float((pp["delta_bolus4h"] > 0).mean()),
        "frac_positive_iob": float((pp["delta_iob_start"] > 0).mean()),
    }

    print(
        f"\nCohort medians:\n"
        f"  delta_bolus4h    (U)   = {summary['cohort_medians']['delta_bolus4h']:+.2f} "
        f"({summary['frac_positive_bolus4h']:.0%} positive)\n"
        f"  delta_iob_start  (U)   = {summary['cohort_medians']['delta_iob_start']:+.2f} "
        f"({summary['frac_positive_iob']:.0%} positive)\n"
        f"  delta_descent    (mg/dL/min) = {summary['cohort_medians']['delta_descent']:+.3f}\n"
        f"  delta_sched_basal (U/h) = {summary['cohort_medians']['delta_sched_basal']:+.3f}"
    )

    # Controller split
    summary["by_controller"] = {}
    for ctrl, g in pp.groupby("controller"):
        if len(g) < 3:
            continue
        summary["by_controller"][str(ctrl)] = {
            "n": int(len(g)),
            "delta_bolus4h_median": float(g["delta_bolus4h"].median()),
            "delta_iob_start_median": float(g["delta_iob_start"].median()),
            "stack_score_median": float(g["stack_score"].median()),
        }
    print("\nBy controller:")
    for ctrl, s in summary["by_controller"].items():
        print(
            f"  {ctrl:8s} n={s['n']:3d}  delta_b4h={s['delta_bolus4h_median']:+.2f}  "
            f"delta_iob={s['delta_iob_start_median']:+.2f}  "
            f"stack_score={s['stack_score_median']:.2f}"
        )

    # Correlations: stack_score vs counter-reg, hypo_fraction
    correlations = {}
    for target in [
        "counter_reg_intercept", "counter_reg_beta_nadir",
        "hypo_fraction", "severe_fraction", "delta_descent",
    ]:
        if target not in pp.columns:
            continue
        d = pp[["stack_score", target]].dropna()
        if len(d) < 8:
            continue
        rho, p = stats.spearmanr(d.stack_score, d[target])
        correlations[target] = {
            "n": int(len(d)),
            "spearman_rho": float(rho),
            "spearman_p": float(p),
        }
        print(
            f"  stack_score vs {target:26s} n={len(d):3d} rho={rho:+.3f} p={p:.3g}"
        )
    summary["stack_score_correlations"] = correlations

    # Top stackers
    top = pp.nlargest(5, "stack_score")[
        ["controller", "delta_bolus4h", "delta_iob_start",
         "delta_descent", "stack_score"]
    ]
    bottom = pp.nsmallest(5, "stack_score")[
        ["controller", "delta_bolus4h", "delta_iob_start",
         "delta_descent", "stack_score"]
    ]
    print("\nTop stackers:")
    print(top.to_string())
    print("\nBottom stackers (no evening excess):")
    print(bottom.to_string())
    summary["top_stackers"] = top.reset_index().to_dict(orient="records")
    summary["bottom_stackers"] = bottom.reset_index().to_dict(orient="records")

    # Figure: 4-panel
    fig, axes = plt.subplots(2, 2, figsize=(13, 9))
    color_map = {"Loop": "tab:blue", "Trio": "tab:orange", "OpenAPS": "tab:green"}
    colors = pp.controller.map(color_map).fillna("gray")

    # Panel 1: per-patient delta_bolus4h horizontal bar
    order = pp.sort_values("delta_bolus4h").index
    ax = axes[0, 0]
    ax.barh(range(len(order)), pp.loc[order, "delta_bolus4h"],
            color=[colors.loc[p] for p in order])
    ax.set_yticks(range(len(order)))
    ax.set_yticklabels(order, fontsize=7)
    ax.axvline(0, color="k", lw=0.5)
    ax.set_xlabel("Evening − rest median 4h bolus (U)")
    ax.set_title("Per-patient evening bolus excess")
    ax.grid(axis="x", alpha=0.3)

    # Panel 2: stack_score vs counter_reg_intercept
    ax = axes[0, 1]
    if "counter_reg_intercept" in correlations:
        d = pp[["stack_score", "counter_reg_intercept", "controller"]].dropna()
        for ctrl in d.controller.unique():
            m = d.controller == ctrl
            ax.scatter(
                d.loc[m, "stack_score"], d.loc[m, "counter_reg_intercept"],
                c=color_map.get(ctrl, "gray"), label=ctrl, s=60, alpha=0.8,
                edgecolor="k",
            )
        rho = correlations["counter_reg_intercept"]["spearman_rho"]
        p = correlations["counter_reg_intercept"]["spearman_p"]
        ax.set_title(f"Stack score vs CR intercept  ρ={rho:+.2f} p={p:.2g}")
        ax.set_xlabel("stacking score (rank-normalized)")
        ax.set_ylabel("Counter-reg intercept (EXP-2875)")
        ax.legend()
        ax.grid(alpha=0.3)

    # Panel 3: stack_score vs hypo_fraction
    ax = axes[1, 0]
    if "hypo_fraction" in correlations:
        d = pp[["stack_score", "hypo_fraction", "controller"]].dropna()
        for ctrl in d.controller.unique():
            m = d.controller == ctrl
            ax.scatter(
                d.loc[m, "stack_score"], d.loc[m, "hypo_fraction"],
                c=color_map.get(ctrl, "gray"), label=ctrl, s=60, alpha=0.8,
                edgecolor="k",
            )
        rho = correlations["hypo_fraction"]["spearman_rho"]
        p = correlations["hypo_fraction"]["spearman_p"]
        ax.set_title(f"Stack score vs hypo fraction  ρ={rho:+.2f} p={p:.2g}")
        ax.set_xlabel("stacking score")
        ax.set_ylabel("Hypo fraction (<70)")
        ax.legend()
        ax.grid(alpha=0.3)

    # Panel 4: delta_bolus4h vs delta_descent
    ax = axes[1, 1]
    d = pp[["delta_bolus4h", "delta_descent", "controller"]].dropna()
    for ctrl in d.controller.unique():
        m = d.controller == ctrl
        ax.scatter(
            d.loc[m, "delta_bolus4h"], d.loc[m, "delta_descent"],
            c=color_map.get(ctrl, "gray"), label=ctrl, s=60, alpha=0.8,
            edgecolor="k",
        )
    rho2, p2 = stats.spearmanr(d.delta_bolus4h, d.delta_descent)
    ax.set_title(f"Δbolus4h vs Δdescent  ρ={rho2:+.2f} p={p2:.2g}")
    ax.set_xlabel("Δ evening bolus4h (U)")
    ax.set_ylabel("Δ evening descent (mg/dL/min, more negative=faster)")
    ax.axhline(0, color="gray", lw=0.5)
    ax.axvline(0, color="gray", lw=0.5)
    ax.legend()
    ax.grid(alpha=0.3)

    fig.suptitle(
        "EXP-2882 — Per-Patient Evening-Stacking Phenotype",
        fontsize=13,
    )
    fig.tight_layout()
    OUT_FIG.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_FIG, dpi=110)
    plt.close(fig)

    # Verdict
    frac_pos = summary["frac_positive_bolus4h"]
    if frac_pos >= 0.75:
        verdict_core = (
            f"UNIVERSAL PHENOTYPE — {frac_pos:.0%} of patients show positive "
            "evening bolus excess. Evening stacking is a pervasive cohort "
            "trait, not a subgroup-specific pattern."
        )
    elif frac_pos >= 0.55:
        verdict_core = (
            f"MAJORITY PHENOTYPE — {frac_pos:.0%} positive. Evening "
            "stacking is common but has meaningful variation."
        )
    else:
        verdict_core = (
            f"VARIABLE PHENOTYPE — only {frac_pos:.0%} positive. Evening "
            "stacking is patient-specific."
        )

    # Check if stack_score correlates with hypo metrics
    sig_corrs = [
        k for k, v in correlations.items() if v["spearman_p"] < 0.05
    ]
    if sig_corrs:
        verdict_core += f" Stack score correlates with: {', '.join(sig_corrs)}."

    summary["verdict"] = verdict_core
    OUT_SUMMARY.write_text(json.dumps(summary, indent=2, default=str))
    print(f"\nVerdict: {verdict_core}")


if __name__ == "__main__":
    main()
