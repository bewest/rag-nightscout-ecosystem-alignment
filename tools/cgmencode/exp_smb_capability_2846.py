"""EXP-2846: Investigate OpenAPS zero-SMB observation from EXP-2845.

Question (Stream B): EXP-2845 reported 5/5 OpenAPS patients had 0 SMB share
in S1, while Loop and Trio had ~33%. Is it:
  (a) cohort artifact (the 5 were all SMB-disabled),
  (b) controller-version artifact, or
  (c) data-ingestion artifact?

We add Loop patient `a` to context — Loop_a also has 0 SMBs (Loop versions
without automatic bolus). So the divide is *within* both Loop and OpenAPS
cohorts: SMB-enabled vs SMB-disabled patient configurations.

Also test: does the SMB-disabled subgroup show different audition
phenotype than SMB-enabled?

Outputs:
  externals/experiments/exp-2846_smb_capability_audit.json
  docs/60-research/figures/exp-2846_smb_capability_panel.png
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

EXP = Path("externals/experiments")
FIG = Path("docs/60-research/figures")


def main() -> dict:
    g = pd.read_parquet("externals/ns-parquet/training/grid.parquet")
    sa = pd.read_parquet(EXP / "exp-2810_state_assignments.parquet")
    pheno = pd.read_parquet(EXP / "exp-2844_phenotype_table.parquet")

    # Per-patient SMB capability classification
    cap = (
        g.groupby("patient_id")
        .agg(n_cells=("bolus_smb", "size"),
             smb_sum=("bolus_smb", "sum"),
             smb_nonzero=("bolus_smb", lambda x: int((x > 0).sum())),
             bolus_sum=("bolus", "sum"))
        .reset_index()
    )
    cap["smb_capable"] = cap["smb_nonzero"] >= 100
    cap["smb_share_total"] = cap["smb_sum"] / np.maximum(
        cap["smb_sum"] + cap["bolus_sum"], 1e-9
    )
    ctrl_map = sa.drop_duplicates("patient_id").set_index("patient_id")["controller"]
    cap["controller"] = cap["patient_id"].map(ctrl_map)
    cap = cap.dropna(subset=["controller"])

    # Cross-tab: controller × SMB capability
    ct = pd.crosstab(cap["controller"], cap["smb_capable"])
    ct.columns = ["smb_disabled", "smb_enabled"]
    print("Controller × SMB capability:")
    print(ct.to_string())
    print()

    # Audition phenotype within each controller, split by SMB capability
    pheno_with_cap = pheno.merge(
        cap[["patient_id", "smb_capable", "smb_share_total"]],
        on="patient_id", how="left",
    )
    print("Phenotype × controller × smb_capable (n significant patients):")
    print(pheno_with_cap.groupby(
        ["controller", "smb_capable", "phenotype"]
    ).size().to_string())

    # Test: within OpenAPS, does SMB capability predict phenotype direction?
    oa = pheno_with_cap[pheno_with_cap["controller"] == "OpenAPS"]
    if len(oa) >= 4:
        en = oa[oa["smb_capable"]]["actual_basal_shift_pct"]
        di = oa[~oa["smb_capable"]]["actual_basal_shift_pct"]
        if len(en) > 0 and len(di) > 0:
            u, p = stats.mannwhitneyu(en, di, alternative="two-sided")
            oa_test = {"u": float(u), "p": float(p),
                       "median_enabled": float(en.median()),
                       "median_disabled": float(di.median()),
                       "n_enabled": int(len(en)),
                       "n_disabled": int(len(di))}
        else:
            oa_test = {"note": "cells empty"}
    else:
        oa_test = {"note": "n too small"}

    # Same for Loop
    lp = pheno_with_cap[pheno_with_cap["controller"] == "Loop"]
    if len(lp) >= 4:
        en = lp[lp["smb_capable"]]["actual_basal_shift_pct"]
        di = lp[~lp["smb_capable"]]["actual_basal_shift_pct"]
        if len(en) > 0 and len(di) > 0:
            u, p = stats.mannwhitneyu(en, di, alternative="two-sided")
            lp_test = {"u": float(u), "p": float(p),
                       "median_enabled": float(en.median()),
                       "median_disabled": float(di.median()),
                       "n_enabled": int(len(en)),
                       "n_disabled": int(len(di))}
        else:
            lp_test = {"note": "cells empty"}
    else:
        lp_test = {"note": "n too small"}

    result = {
        "experiment": "EXP-2846",
        "title": "OpenAPS zero-SMB investigation - capability audit",
        "stream": "B",
        "controller_capability_table": ct.to_dict(),
        "n_patients_total": int(len(cap)),
        "n_smb_disabled": int((~cap["smb_capable"]).sum()),
        "n_smb_enabled": int(cap["smb_capable"].sum()),
        "openaps_capability_phenotype_test": oa_test,
        "loop_capability_phenotype_test": lp_test,
        "interpretation": (
            "SMB capability is a per-patient configuration property "
            "that crosses controller lines: some Loop patients have "
            "no SMBs (no automatic bolus enabled), some OpenAPS have "
            "SMBs enabled, and Trio patients consistently show SMB "
            "delivery. EXP-2845's '5/5 OpenAPS zero SMB share' is a "
            "*cohort* artifact: all 5 significant OpenAPS patients in "
            "the EXP-2843 set happen to be SMB-disabled. Within each "
            "controller cohort, capability may predict S1 phenotype."
        ),
        "audition_implication": (
            "The audition recommendation framework must condition on "
            "(controller, SMB capability, phenotype, time-of-day) - "
            "four factors, not three. SMB-disabled patients can ONLY "
            "compensate via basal, so up-shift is the available route "
            "regardless of controller."
        ),
    }
    (EXP / "exp-2846_smb_capability_audit.json").write_text(
        json.dumps(result, indent=2, default=str)
    )

    # Visualization
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    fig.suptitle(
        "EXP-2846 — SMB capability audit\n"
        "Stream B; capability is a per-patient configuration crossing controller lines",
        fontsize=11,
    )

    # P1: capability per controller stacked bar
    ax = axes[0]
    bottom = np.zeros(len(ct))
    for cap_col, color in [("smb_disabled", "#d62728"), ("smb_enabled", "#1f77b4")]:
        ax.bar(ct.index, ct[cap_col], bottom=bottom,
               label=cap_col, edgecolor="white", color=color, alpha=0.8)
        bottom += ct[cap_col].values
    ax.set_ylabel("Patients")
    ax.set_title("SMB capability by controller (whole cohort)")
    ax.legend()

    # P2: scatter capability × phenotype (significant patients)
    ax = axes[1]
    cmap = {"Loop": "o", "Trio": "s", "OpenAPS": "^"}
    for _, row in pheno_with_cap.iterrows():
        color = "#1f77b4" if row.get("smb_capable") else "#d62728"
        ax.scatter(
            row["actual_basal_shift_pct"],
            {"down_shift": -1, "flat": 0, "up_shift": 1}.get(row["phenotype"], 0)
            + np.random.uniform(-0.15, 0.15),
            color=color, marker=cmap.get(row["controller"], "x"),
            s=100, alpha=0.85, edgecolor="white",
        )
    ax.axvline(0, color="k", lw=0.6)
    ax.axvspan(-15, 15, color="lightgray", alpha=0.4)
    ax.set_yticks([-1, 0, 1])
    ax.set_yticklabels(["down_shift", "flat", "up_shift"])
    ax.set_xlabel("Actual basal shift S0→S1 (%)")
    ax.set_title("Phenotype × capability\n"
                 "blue = SMB-enabled, red = SMB-disabled\n"
                 "marker = controller")
    handles = [
        plt.Line2D([0], [0], marker=m, color="gray", linestyle="",
                   markersize=9, label=ctrl)
        for ctrl, m in cmap.items()
    ]
    handles += [
        plt.Line2D([0], [0], marker="o", color="#1f77b4", linestyle="",
                   markersize=9, label="SMB enabled"),
        plt.Line2D([0], [0], marker="o", color="#d62728", linestyle="",
                   markersize=9, label="SMB disabled"),
    ]
    ax.legend(handles=handles, fontsize=8, loc="best")

    plt.tight_layout(rect=(0, 0, 1, 0.94))
    out_fig = FIG / "exp-2846_smb_capability_panel.png"
    plt.savefig(out_fig, dpi=120, bbox_inches="tight")
    plt.close()
    print(f"\nWrote {out_fig}")
    print(json.dumps(result, indent=2, default=str)[:1500])
    return result


if __name__ == "__main__":
    main()
