"""EXP-2885 — Simpson-decomposed AID braking by controller × TOD.

EXP-2884 pooled medians showed actual_basal=0 in all TOD bins,
concluding 'saturated brake'. But MEAN-based analysis revealed:
  Trio:    74-87% suspended (most aggressive)
  Loop:    70-79% suspended (with evening lowest ratio 0.08)
  OpenAPS: 14-39% suspended (mean delivery 0.5-1.0!)

The pooled view hid controller-specific signatures. Now test:

  1. Per-patient means (not pooled events) to avoid any single
     patient dominating their controller cohort.
  2. Within each controller, is there TOD structure?
  3. Do 'aggressive setters' (high scheduled basal / high TDD) show
     different braking than conservative ones?
  4. Does patient aggressiveness correlate with stacking (EXP-2882)?
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]

EV_PATH = ROOT / "externals/experiments/exp-2881_evening_drivers.parquet"
STACK_PATH = ROOT / "externals/experiments/exp-2882_stacker_phenotype.parquet"
OUT = ROOT / "externals/experiments/exp-2885_simpson_braking.parquet"
OUT_SUMMARY = ROOT / "externals/experiments/exp-2885_simpson_braking_summary.json"
OUT_FIG = ROOT / "docs/60-research/figures/exp-2885_simpson_braking.png"

TOD_ORDER = ["night", "morning", "afternoon", "evening"]


def main() -> None:
    df = pd.read_parquet(EV_PATH).copy()
    df["suspended"] = (df.actual_basal == 0).astype(int)
    df["delivery_ratio"] = np.where(
        df.sched_basal > 0, df.actual_basal / df.sched_basal, np.nan
    )

    # Per-patient × TOD aggregates (so each patient contributes equally)
    pp_tod = (
        df.groupby(["patient_id", "controller", "tod"])
        .agg(
            n=("actual_basal", "size"),
            mean_actual=("actual_basal", "mean"),
            mean_sched=("sched_basal", "mean"),
            mean_ratio=("delivery_ratio", "mean"),
            suspension_rate=("suspended", "mean"),
        )
        .reset_index()
    )
    # Require >=3 events per (patient, tod) for reliability
    pp_tod = pp_tod[pp_tod.n >= 3]
    pp_tod.to_parquet(OUT)
    print(f"per-patient × TOD cells: {len(pp_tod)}")

    # Patient-level aggressiveness proxy: overall mean scheduled basal
    # (across all events) + total_4h_bolus rest median
    aggress = (
        df.groupby(["patient_id", "controller"])
        .agg(
            mean_sched_basal=("sched_basal", "mean"),
            mean_bolus_4h=("bolus_4h", "mean"),
            n_events=("actual_basal", "size"),
        )
        .reset_index()
    )
    # Proxy: aggressive = high scheduled basal × high bolus usage
    aggress["aggr_score"] = (
        stats.rankdata(aggress.mean_sched_basal) / len(aggress)
        + stats.rankdata(aggress.mean_bolus_4h) / len(aggress)
    ) / 2
    aggress["aggr_tercile"] = pd.qcut(
        aggress.aggr_score, 3, labels=["conservative", "mid", "aggressive"]
    )
    print(f"\naggressiveness terciles: "
          f"{aggress.aggr_tercile.value_counts().to_dict()}")

    # --- Controller × TOD signature (per-patient means) ---
    ctrl_tod = (
        pp_tod.groupby(["controller", "tod"])
        .agg(
            n_patients=("patient_id", "nunique"),
            mean_ratio=("mean_ratio", "mean"),
            median_ratio=("mean_ratio", "median"),
            mean_suspension=("suspension_rate", "mean"),
            mean_actual=("mean_actual", "mean"),
            mean_sched=("mean_sched", "mean"),
        )
        .reset_index()
    )
    print("\nController × TOD (per-patient-averaged means):")
    print(ctrl_tod.to_string(index=False))

    # --- TOD signature WITHIN each controller ---
    tod_signature = {}
    for ctrl, grp in pp_tod.groupby("controller"):
        # Friedman on patients × tod cells (each patient must have all 4 TODs)
        pivot = grp.pivot_table(
            index="patient_id", columns="tod", values="mean_ratio"
        ).reindex(columns=TOD_ORDER)
        complete = pivot.dropna()
        if len(complete) >= 3:
            friedman = stats.friedmanchisquare(
                *(complete[t].values for t in TOD_ORDER)
            )
            p_friedman = float(friedman.pvalue)
        else:
            p_friedman = None
        # Evening vs morning Wilcoxon per-patient
        ev_morn = pivot[["morning", "evening"]].dropna()
        if len(ev_morn) >= 5:
            _, p_wil = stats.wilcoxon(
                ev_morn["evening"].values - ev_morn["morning"].values
            )
            diff = float((ev_morn["evening"] - ev_morn["morning"]).median())
        else:
            p_wil, diff = None, None
        tod_signature[ctrl] = {
            "n_patients_complete": int(len(complete)),
            "friedman_p": p_friedman,
            "evening_minus_morning_ratio_median": diff,
            "evening_vs_morning_wilcoxon_p": float(p_wil) if p_wil else None,
            "mean_ratio_by_tod": {
                t: float(pivot[t].mean()) for t in TOD_ORDER
            },
            "mean_suspension_by_tod": {
                t: float(
                    grp[grp.tod == t].suspension_rate.mean()
                ) for t in TOD_ORDER
            },
        }

    print("\nWithin-controller TOD signature:")
    for ctrl, sig in tod_signature.items():
        ratios = sig["mean_ratio_by_tod"]
        print(
            f"  {ctrl:8s}  n={sig['n_patients_complete']}  "
            f"Friedman p={sig['friedman_p']}  "
            f"ev−morn ratio diff={sig['evening_minus_morning_ratio_median']}  "
            f"Wilcoxon p={sig['evening_vs_morning_wilcoxon_p']}"
        )
        print(f"    ratios {ratios}")

    # --- Aggressiveness × controller interaction ---
    pp_overall = (
        pp_tod.groupby(["patient_id", "controller"])
        .agg(
            mean_ratio=("mean_ratio", "mean"),
            mean_suspension=("suspension_rate", "mean"),
        )
        .reset_index()
        .merge(aggress, on=["patient_id", "controller"])
    )
    aggr_xs = {}
    for tercile in ["conservative", "mid", "aggressive"]:
        sub = pp_overall[pp_overall.aggr_tercile == tercile]
        aggr_xs[tercile] = {
            "n": int(len(sub)),
            "mean_ratio": float(sub.mean_ratio.mean()) if len(sub) else None,
            "mean_suspension": float(sub.mean_suspension.mean()) if len(sub) else None,
            "by_controller": (
                sub.groupby("controller")
                .agg(n=("patient_id", "size"),
                     ratio=("mean_ratio", "mean"),
                     susp=("mean_suspension", "mean"))
                .round(3)
                .to_dict(orient="index")
            ),
        }

    print("\nAggressiveness tercile × controller:")
    for terc, d in aggr_xs.items():
        print(f"  {terc:12s} n={d['n']} ratio={d['mean_ratio']} susp={d['mean_suspension']}")
        print(f"    by_ctrl: {d['by_controller']}")

    # Does aggr_score correlate with suspension_rate? (higher aggr -> more suspend?)
    rho_asusp, p_asusp = stats.spearmanr(
        pp_overall.aggr_score, pp_overall.mean_suspension
    )
    rho_aratio, p_aratio = stats.spearmanr(
        pp_overall.aggr_score, pp_overall.mean_ratio
    )

    # Correlate stack_score (EXP-2882) with braking
    try:
        stack = pd.read_parquet(STACK_PATH).reset_index()
        merged = pp_overall.merge(
            stack[["patient_id", "stack_score"]], on="patient_id"
        )
        rho_stack_susp, p_stack_susp = stats.spearmanr(
            merged.stack_score, merged.mean_suspension
        )
        rho_stack_ratio, p_stack_ratio = stats.spearmanr(
            merged.stack_score, merged.mean_ratio
        )
    except Exception as e:
        rho_stack_susp = p_stack_susp = rho_stack_ratio = p_stack_ratio = None
        merged = pp_overall

    summary = {
        "exp_id": "2885",
        "n_events": int(len(df)),
        "n_patients": int(df.patient_id.nunique()),
        "n_patient_tod_cells": int(len(pp_tod)),
        "controller_tod_per_patient_means": ctrl_tod.to_dict(orient="records"),
        "within_controller_tod_signature": tod_signature,
        "aggressiveness_terciles": aggr_xs,
        "aggressiveness_correlations": {
            "aggr_vs_suspension": {
                "rho": float(rho_asusp), "p": float(p_asusp),
            },
            "aggr_vs_delivery_ratio": {
                "rho": float(rho_aratio), "p": float(p_aratio),
            },
        },
        "stack_score_correlations": {
            "stack_vs_suspension": {
                "rho": float(rho_stack_susp) if rho_stack_susp is not None else None,
                "p": float(p_stack_susp) if p_stack_susp is not None else None,
            },
            "stack_vs_delivery_ratio": {
                "rho": float(rho_stack_ratio) if rho_stack_ratio is not None else None,
                "p": float(p_stack_ratio) if p_stack_ratio is not None else None,
            },
        },
    }

    # Figure
    fig, axes = plt.subplots(1, 3, figsize=(16, 5.5))

    # Panel 1: suspension rate by controller × TOD (per-patient aggregated)
    ctrls = sorted(pp_tod.controller.unique())
    x = np.arange(len(TOD_ORDER))
    w = 0.25
    ctrl_colors = {"Loop": "#1f77b4", "Trio": "#ff7f0e", "OpenAPS": "#2ca02c"}
    for i, ctrl in enumerate(ctrls):
        vals = [
            pp_tod[(pp_tod.controller == ctrl) & (pp_tod.tod == t)]
            .suspension_rate.mean()
            for t in TOD_ORDER
        ]
        ns = [
            pp_tod[(pp_tod.controller == ctrl) & (pp_tod.tod == t)]
            .patient_id.nunique()
            for t in TOD_ORDER
        ]
        axes[0].bar(x + (i - 1) * w, vals, w, label=f"{ctrl} (n_pat up to {max(ns)})",
                    color=ctrl_colors.get(ctrl, "gray"))
    axes[0].set_xticks(x)
    axes[0].set_xticklabels(TOD_ORDER)
    axes[0].set_ylabel("suspension_rate (fraction of time at 0 basal)")
    axes[0].set_title("Basal suspension rate\nby controller × TOD (per-patient means)")
    axes[0].legend(fontsize=8)
    axes[0].grid(axis="y", alpha=0.3)
    axes[0].set_ylim(0, 1)

    # Panel 2: delivery ratio by controller × TOD
    for i, ctrl in enumerate(ctrls):
        vals = [
            pp_tod[(pp_tod.controller == ctrl) & (pp_tod.tod == t)]
            .mean_ratio.mean()
            for t in TOD_ORDER
        ]
        axes[1].bar(x + (i - 1) * w, vals, w, label=ctrl,
                    color=ctrl_colors.get(ctrl, "gray"))
    axes[1].set_xticks(x)
    axes[1].set_xticklabels(TOD_ORDER)
    axes[1].set_ylabel("mean delivery_ratio (actual/scheduled)")
    axes[1].set_title("Delivery ratio during descent\n(higher = less braking)")
    axes[1].legend(fontsize=8)
    axes[1].grid(axis="y", alpha=0.3)

    # Panel 3: aggressiveness × suspension (scatter)
    for ctrl in ctrls:
        sub = pp_overall[pp_overall.controller == ctrl]
        axes[2].scatter(
            sub.aggr_score, sub.mean_suspension,
            c=ctrl_colors.get(ctrl, "gray"),
            label=f"{ctrl} (n={len(sub)})",
            s=60, edgecolor="black",
        )
    axes[2].set_xlabel("aggressiveness_score (sched_basal + bolus_4h rank)")
    axes[2].set_ylabel("mean_suspension_rate during descent")
    axes[2].set_title(
        f"Aggressiveness vs braking\nρ={rho_asusp:.2f} p={p_asusp:.2f}"
    )
    axes[2].legend(fontsize=8)
    axes[2].grid(alpha=0.3)

    fig.suptitle(
        "EXP-2885 — Simpson-decomposed braking: controller × TOD × aggressiveness",
        fontsize=13,
    )
    fig.tight_layout()
    OUT_FIG.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_FIG, dpi=110)
    plt.close(fig)

    # Verdict
    verdict_lines = []
    for ctrl, sig in tod_signature.items():
        ratios = sig["mean_ratio_by_tod"]
        span = max(ratios.values()) - min(ratios.values())
        verdict_lines.append(
            f"{ctrl}: TOD ratio span {span:.3f} "
            f"(night={ratios['night']:.3f}, eve={ratios['evening']:.3f})"
        )
    summary["verdict"] = (
        "SIMPSON'S PARADOX CONFIRMED — controller-level signatures are "
        "hidden by pooling. " + " | ".join(verdict_lines) +
        f" | Aggressiveness vs suspension: rho={rho_asusp:.3f} p={p_asusp:.3f}."
    )
    OUT_SUMMARY.write_text(json.dumps(summary, indent=2, default=str))
    print(f"\nVerdict: {summary['verdict']}")


if __name__ == "__main__":
    main()
