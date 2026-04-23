"""EXP-2889 - Counterfactual AID-off replay for descent events.

Addresses the C7 (collider) issue discovered in EXP-2888:  the
observed severe_fraction is confounded by AID intervention itself.
This experiment replays each descent event assuming the AID had
*not* suspended basal - i.e. scheduled basal had been delivered
for the event's duration.  The counterfactual nadir is the natural
outcome for validating AID-dependence constructs.

Method
------
For each event in exp-2881_evening_drivers:
  duration_min  = (bg_start - bg_nadir) / (-descent_slope)
  basal_deficit = max(0, sched_basal - actual_basal)  [U/h]
  extra_insulin = basal_deficit * (duration_min / 60)  [U]
  extra_drop    = extra_insulin * ISF_pop              [mg/dL]
  cf_nadir      = bg_nadir - extra_drop

We use ISF_pop = 50 mg/dL/U (population median from EXP-2756;
per-patient ISF is in profile but not in this parquet - a
conservative uniform ISF is appropriate since the question is
rank-ordering of fragility, not absolute prediction).

Outcomes per patient:
  cf_severe_fraction  = P(cf_nadir < 54)
  cf_hypo_fraction    = P(cf_nadir < 70)
  observed vs counterfactual gap = how much protection AID delivered

Validation of EXP-2886 constructs:
  Spearman rho ( hidden_leverage , cf_severe_fraction )
  Spearman rho ( braking_ratio   , cf_severe_fraction )
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

OUT = Path("externals/experiments")
FIGS = Path("docs/60-research/figures")
FIGS.mkdir(parents=True, exist_ok=True)

ISF_POP = 50.0  # mg/dL/U, EXP-2756 population median


def main() -> None:
    events = pd.read_parquet(OUT / "exp-2881_evening_drivers.parquet")
    pheno = pd.read_parquet(OUT / "exp-2886_phenotype.parquet")

    # Only events with real descent (slope < 0, nadir < start)
    ev = events[
        (events["descent_slope"] < -0.05)
        & (events["bg_nadir"] < events["bg_start"])
    ].copy()

    ev["duration_min"] = (
        (ev["bg_start"] - ev["bg_nadir"]) / (-ev["descent_slope"])
    ).clip(lower=5, upper=240)
    ev["basal_deficit_uh"] = (
        (ev["sched_basal"] - ev["actual_basal"]).clip(lower=0)
    )
    ev["extra_insulin_u"] = (
        ev["basal_deficit_uh"] * ev["duration_min"] / 60.0
    )
    ev["extra_drop_mgdl"] = ev["extra_insulin_u"] * ISF_POP
    ev["cf_nadir"] = ev["bg_nadir"] - ev["extra_drop_mgdl"]
    ev["cf_severe"] = (ev["cf_nadir"] < 54).astype(int)
    ev["cf_hypo"] = (ev["cf_nadir"] < 70).astype(int)
    ev["obs_severe"] = (ev["bg_nadir"] < 54).astype(int)
    ev["obs_hypo"] = (ev["bg_nadir"] < 70).astype(int)

    # Per-patient rollup
    agg = (ev.groupby("patient_id")
             .agg(n_events=("bg_start", "size"),
                  mean_duration=("duration_min", "mean"),
                  mean_deficit_uh=("basal_deficit_uh", "mean"),
                  mean_extra_drop=("extra_drop_mgdl", "mean"),
                  obs_severe=("obs_severe", "mean"),
                  cf_severe=("cf_severe", "mean"),
                  obs_hypo=("obs_hypo", "mean"),
                  cf_hypo=("cf_hypo", "mean"))
             .reset_index())
    agg["aid_protection_severe"] = agg["cf_severe"] - agg["obs_severe"]
    agg["aid_protection_hypo"] = agg["cf_hypo"] - agg["obs_hypo"]

    # Join phenotype
    merged = agg.merge(
        pheno[["patient_id", "controller", "lineage", "stack_score",
               "braking_ratio", "counter_reg_intercept",
               "hidden_leverage", "archetype"]],
        on="patient_id", how="left")

    # ------------------------------------------------------------------
    # Validation: does hidden_leverage predict cf_severe?
    # ------------------------------------------------------------------
    m = merged.dropna(subset=["hidden_leverage", "cf_severe",
                              "stack_score", "braking_ratio",
                              "counter_reg_intercept"])
    results = {}
    for var in ["hidden_leverage", "stack_score",
                "braking_ratio", "counter_reg_intercept"]:
        for outcome in ["cf_severe", "cf_hypo",
                        "aid_protection_severe"]:
            r, p = stats.spearmanr(m[var], m[outcome])
            results[f"{var}__{outcome}"] = {
                "rho": float(r), "p": float(p), "n": int(len(m))}

    for k, v in results.items():
        marker = "*" if v["p"] < 0.05 else " "
        print(f"  {marker} {k:56s} rho={v['rho']:+.3f} p={v['p']:.3f}")

    # ------------------------------------------------------------------
    # Archetype stratification on counterfactual outcome
    # ------------------------------------------------------------------
    arch_stats = (merged.groupby("archetype")
                        .agg(n=("patient_id", "count"),
                             obs_severe=("obs_severe", "mean"),
                             cf_severe=("cf_severe", "mean"),
                             protection=("aid_protection_severe", "mean"))
                        .reset_index())
    print("\nArchetype x counterfactual outcome:")
    print(arch_stats.to_string(index=False))

    # Kruskal on cf_severe by archetype
    groups = [g["cf_severe"].values
              for _, g in merged.groupby("archetype") if len(g) >= 2]
    kw = None
    if len(groups) >= 2:
        h, pk = stats.kruskal(*groups)
        kw = {"H": float(h), "p": float(pk), "n_groups": len(groups)}
        print(f"Kruskal cf_severe by archetype: H={h:.2f} p={pk:.3f}")

    # ------------------------------------------------------------------
    # Figure
    # ------------------------------------------------------------------
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5))

    ax = axes[0]
    for arch, g in merged.groupby("archetype"):
        ax.scatter(g["hidden_leverage"], g["cf_severe"] * 100,
                   label=arch, s=60, alpha=0.8)
    r, p = stats.spearmanr(m["hidden_leverage"], m["cf_severe"])
    ax.set_xlabel("hidden_leverage (stack x (1-brake))")
    ax.set_ylabel("counterfactual severe-hypo %  (AID-off)")
    ax.set_title(f"EXP-2889 counterfactual validation\n"
                 f"rho={r:+.3f} p={p:.3f} n={len(m)}")
    ax.legend(fontsize=7, loc="upper left")
    ax.grid(alpha=0.3)

    ax = axes[1]
    # Observed vs counterfactual severe fraction per patient
    merged_sorted = merged.sort_values("cf_severe", ascending=False)
    xs = np.arange(len(merged_sorted))
    ax.bar(xs - 0.2, merged_sorted["obs_severe"] * 100,
           width=0.4, label="observed", color="steelblue")
    ax.bar(xs + 0.2, merged_sorted["cf_severe"] * 100,
           width=0.4, label="counterfactual (AID-off)",
           color="firebrick")
    ax.set_xticks(xs)
    ax.set_xticklabels(merged_sorted["patient_id"],
                       rotation=90, fontsize=6)
    ax.set_ylabel("severe-hypo fraction of descents (%)")
    ax.set_title("Per-patient AID protection")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3, axis="y")

    ax = axes[2]
    # Protection magnitude by lineage
    lineage_order = (merged.groupby("lineage")["aid_protection_severe"]
                           .median().sort_values().index.tolist())
    data = [merged[merged["lineage"] == ln]["aid_protection_severe"].values
            * 100 for ln in lineage_order]
    ax.boxplot(data, tick_labels=lineage_order, showmeans=True)
    ax.set_ylabel("AID protection  (cf - obs)  (%)")
    ax.set_title("Protection delivered by lineage")
    ax.grid(alpha=0.3, axis="y")

    fig.tight_layout()
    fig_path = FIGS / "exp-2889_counterfactual_replay.png"
    fig.savefig(fig_path, dpi=130)
    plt.close(fig)

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------
    summary = {
        "exp": "EXP-2889",
        "method": "counterfactual AID-off replay",
        "isf_pop": ISF_POP,
        "n_patients": int(len(merged)),
        "n_events": int(len(ev)),
        "population_mean_observed_severe": float(ev["obs_severe"].mean()),
        "population_mean_counterfactual_severe":
            float(ev["cf_severe"].mean()),
        "population_aid_protection_absolute":
            float(ev["cf_severe"].mean() - ev["obs_severe"].mean()),
        "population_aid_protection_relative":
            float((ev["cf_severe"].mean() - ev["obs_severe"].mean())
                  / max(ev["cf_severe"].mean(), 1e-9)),
        "correlations": results,
        "archetype_stats": arch_stats.to_dict(orient="records"),
        "archetype_kruskal": kw,
        "figure": str(fig_path),
    }
    (OUT / "exp-2889_counterfactual_replay_summary.json").write_text(
        json.dumps(summary, indent=2))
    merged.to_parquet(OUT / "exp-2889_counterfactual_replay.parquet")
    ev.to_parquet(OUT / "exp-2889_event_replay.parquet")
    print(f"\nWrote {fig_path}")
    print(f"Pop observed severe = {ev['obs_severe'].mean():.3%}")
    print(f"Pop counterfactual severe = {ev['cf_severe'].mean():.3%}")
    print(f"AID protection = {summary['population_aid_protection_absolute']:.3%}"
          f" (rel {summary['population_aid_protection_relative']:.1%})")


if __name__ == "__main__":
    main()
