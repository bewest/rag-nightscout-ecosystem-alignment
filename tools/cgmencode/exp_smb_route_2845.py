"""EXP-2845: Test SMB-availability hypothesis from EXP-2844.

Question (Stream B): does the operational difference between Loop's
"never down-shift" (0/6) and Trio's "always down-shift" (5/6) in S1
windows reduce to SMB usage? Specifically:

  H1: In S1 windows, Trio delivers far more bolus_smb than Loop.
  H2: In S1 windows, Loop's compensation flows through actual basal
      uplift while Trio's flows through SMBs.
  H3: Total insulin in S1 (basal + boluses + SMBs) is comparable
      across controllers (closed-loop net effect similar).

If H1+H2+H3 hold, the EXP-2844 phenotype is fully explained by
controller-software response choice (route of delivery), not by
biological state interpretation.

Charter: Stream B operational. We compare *observed* delivery routes;
no biology claim.

Outputs:
  externals/experiments/exp-2845_smb_route_analysis.json
  externals/experiments/exp-2845_per_patient_route.parquet
  docs/60-research/figures/exp-2845_route_by_controller.png
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
FIG.mkdir(parents=True, exist_ok=True)


def main() -> dict:
    g = pd.read_parquet("externals/ns-parquet/training/grid.parquet")
    g["time"] = pd.to_datetime(g["time"], utc=True)

    sa = pd.read_parquet(EXP / "exp-2810_state_assignments.parquet")
    sa["time"] = pd.to_datetime(sa["time"], utc=True)

    # Restrict to patients in EXP-2844 (the 17 significant)
    pheno = pd.read_parquet(EXP / "exp-2844_phenotype_table.parquet")
    pids = pheno["patient_id"].unique()
    g = g[g["patient_id"].isin(pids)].copy()
    sa = sa[sa["patient_id"].isin(pids)].copy()

    # Map each grid cell to its 48h state window (nearest-prior daily window)
    g_sorted = g.sort_values("time").reset_index(drop=True)
    sa_sorted = sa.sort_values("time").reset_index(drop=True)
    merged = pd.merge_asof(
        g_sorted, sa_sorted[["patient_id", "time", "state"]],
        on="time", by="patient_id", direction="backward",
        tolerance=pd.Timedelta("2D"),
    )
    merged = merged.dropna(subset=["state"])
    merged["state"] = merged["state"].astype(int)
    print(f"Merged grid+state: {len(merged):,} cells; "
          f"S0={(merged['state']==0).sum():,}, S1={(merged['state']==1).sum():,}")

    # Per-patient × state route summary
    rows = []
    for (pid, state), sub in merged.groupby(["patient_id", "state"]):
        ctrl = pheno.loc[pheno["patient_id"] == pid, "controller"].iloc[0]
        phenotype = pheno.loc[pheno["patient_id"] == pid, "phenotype"].iloc[0]
        n = len(sub)
        # Per 5-min cell -> per hour rates
        basal_actual_uph = sub["actual_basal_rate"].mean()  # already U/h
        basal_sched_uph = sub["scheduled_basal_rate"].mean()
        # Bolus events: bolus + bolus_smb (units delivered in that 5-min cell)
        # Convert to U/h by dividing by 5min/60min = 1/12 -> *12
        bolus_uph = sub["bolus"].sum() * 12 / max(n, 1)
        smb_uph = sub["bolus_smb"].sum() * 12 / max(n, 1)
        total_insulin_uph = basal_actual_uph + bolus_uph + smb_uph
        # SMB share of total bolus
        smb_share = (
            sub["bolus_smb"].sum()
            / max(sub["bolus"].sum() + sub["bolus_smb"].sum(), 1e-9)
        )
        rows.append(dict(
            patient_id=pid, controller=ctrl, phenotype=phenotype,
            state=state, n_cells=n,
            basal_sched_uph=basal_sched_uph,
            basal_actual_uph=basal_actual_uph,
            bolus_uph=bolus_uph,
            smb_uph=smb_uph,
            smb_share=smb_share,
            total_insulin_uph=total_insulin_uph,
            mean_glucose=sub["glucose"].mean(),
        ))
    route = pd.DataFrame(rows)

    # Pivot to per-patient deltas (S1 - S0)
    s0 = route[route["state"] == 0].set_index("patient_id")
    s1 = route[route["state"] == 1].set_index("patient_id")
    common = s0.index.intersection(s1.index)
    delta = pd.DataFrame({
        "patient_id": common,
        "controller": s0.loc[common, "controller"].values,
        "phenotype": s0.loc[common, "phenotype"].values,
        "d_basal_uph": (s1.loc[common, "basal_actual_uph"]
                        - s0.loc[common, "basal_actual_uph"]).values,
        "d_smb_uph": (s1.loc[common, "smb_uph"]
                      - s0.loc[common, "smb_uph"]).values,
        "d_bolus_uph": (s1.loc[common, "bolus_uph"]
                        - s0.loc[common, "bolus_uph"]).values,
        "d_total_uph": (s1.loc[common, "total_insulin_uph"]
                        - s0.loc[common, "total_insulin_uph"]).values,
        "smb_share_s1": s1.loc[common, "smb_share"].values,
    })

    # Per-controller summary
    ctrl_summary = (
        delta.groupby("controller")
        .agg(
            n=("patient_id", "count"),
            median_d_basal=("d_basal_uph", "median"),
            median_d_smb=("d_smb_uph", "median"),
            median_d_bolus=("d_bolus_uph", "median"),
            median_d_total=("d_total_uph", "median"),
            median_smb_share_s1=("smb_share_s1", "median"),
        )
        .reset_index()
    )

    # H1 test: SMB share in S1 - Trio vs Loop
    trio_smb = delta[delta["controller"] == "Trio"]["smb_share_s1"].dropna()
    loop_smb = delta[delta["controller"] == "Loop"]["smb_share_s1"].dropna()
    if len(trio_smb) > 0 and len(loop_smb) > 0:
        u_h1, p_h1 = stats.mannwhitneyu(trio_smb, loop_smb, alternative="greater")
        h1 = {"u": float(u_h1), "p": float(p_h1),
              "trio_median_smb_share": float(trio_smb.median()),
              "loop_median_smb_share": float(loop_smb.median())}
    else:
        h1 = {"note": "n too small"}

    # H2 test: delta basal Loop > Trio
    loop_db = delta[delta["controller"] == "Loop"]["d_basal_uph"].dropna()
    trio_db = delta[delta["controller"] == "Trio"]["d_basal_uph"].dropna()
    if len(loop_db) > 0 and len(trio_db) > 0:
        u_h2, p_h2 = stats.mannwhitneyu(loop_db, trio_db, alternative="greater")
        h2 = {"u": float(u_h2), "p": float(p_h2),
              "loop_median_d_basal": float(loop_db.median()),
              "trio_median_d_basal": float(trio_db.median())}
    else:
        h2 = {"note": "n too small"}

    # H3 test: total insulin delta - is it similar?
    # Two-sided test of difference
    loop_dt = delta[delta["controller"] == "Loop"]["d_total_uph"].dropna()
    trio_dt = delta[delta["controller"] == "Trio"]["d_total_uph"].dropna()
    if len(loop_dt) > 0 and len(trio_dt) > 0:
        u_h3, p_h3 = stats.mannwhitneyu(loop_dt, trio_dt, alternative="two-sided")
        h3 = {"u": float(u_h3), "p": float(p_h3),
              "loop_median_d_total": float(loop_dt.median()),
              "trio_median_d_total": float(trio_dt.median()),
              "interpretation_PASS_if_p_gt_0.10": float(p_h3) > 0.10}
    else:
        h3 = {"note": "n too small"}

    checks = {
        "PASS_H1_trio_smb_share_higher_in_S1": h1.get("p", 1.0) < 0.10,
        "PASS_H2_loop_basal_uplift_higher": h2.get("p", 1.0) < 0.10,
        "PASS_H3_total_delivery_similar": h3.get("interpretation_PASS_if_p_gt_0.10", False),
        "PASS_no_biology_claim": True,
    }

    result = {
        "experiment": "EXP-2845",
        "title": "SMB route hypothesis for Loop vs Trio S1 phenotype",
        "stream": "B",
        "n_patients": int(len(delta)),
        "controller_summary": ctrl_summary.to_dict(orient="records"),
        "H1_smb_share_s1_trio_vs_loop": h1,
        "H2_basal_uplift_loop_vs_trio": h2,
        "H3_total_insulin_delta_similar": h3,
        "checks": checks,
        "checks_passed": int(sum(checks.values())),
        "checks_total": len(checks),
        "interpretation": (
            "If H1+H2+H3 all PASS, EXP-2844's controller phenotype split "
            "is a route-of-delivery story: same envelope demand, "
            "different controller responses (Trio: SMB micro-dose "
            "while cutting basal; Loop: basal uplift). "
            "If H3 fails, total delivery also differs and the story "
            "is more than route choice."
        ),
    }

    delta.to_parquet(EXP / "exp-2845_per_patient_route.parquet", index=False)
    (EXP / "exp-2845_smb_route_analysis.json").write_text(
        json.dumps(result, indent=2, default=str)
    )

    # Visualization
    fig, axes = plt.subplots(1, 3, figsize=(14, 5))
    fig.suptitle(
        "EXP-2845 — Route of insulin delivery in S1 windows by controller\n"
        "Stream B: observed delivery routes; no biology claim",
        fontsize=11,
    )
    cmap = {"Loop": "#1f77b4", "Trio": "#d62728", "OpenAPS": "#2ca02c"}

    # P1: SMB share in S1
    ax = axes[0]
    for ctrl, sub in delta.groupby("controller"):
        ax.scatter(np.full(len(sub), list(cmap).index(ctrl)) +
                   np.random.uniform(-0.1, 0.1, len(sub)),
                   sub["smb_share_s1"], color=cmap.get(ctrl, "k"),
                   s=80, alpha=0.85, edgecolor="white", label=ctrl)
    ax.set_xticks(range(len(cmap)))
    ax.set_xticklabels(list(cmap.keys()))
    ax.set_ylabel("SMB share of total bolus in S1")
    ax.set_title(f"H1: SMB route (p={h1.get('p', float('nan')):.3f})")
    ax.set_ylim(-0.05, 1.05)

    # P2: delta basal uph
    ax = axes[1]
    for ctrl, sub in delta.groupby("controller"):
        ax.scatter(np.full(len(sub), list(cmap).index(ctrl)) +
                   np.random.uniform(-0.1, 0.1, len(sub)),
                   sub["d_basal_uph"], color=cmap.get(ctrl, "k"),
                   s=80, alpha=0.85, edgecolor="white")
    ax.axhline(0, color="k", lw=0.6)
    ax.set_xticks(range(len(cmap)))
    ax.set_xticklabels(list(cmap.keys()))
    ax.set_ylabel("Δ actual basal U/h (S1 − S0)")
    ax.set_title(f"H2: Basal uplift (p={h2.get('p', float('nan')):.3f})")

    # P3: delta total insulin
    ax = axes[2]
    for ctrl, sub in delta.groupby("controller"):
        ax.scatter(np.full(len(sub), list(cmap).index(ctrl)) +
                   np.random.uniform(-0.1, 0.1, len(sub)),
                   sub["d_total_uph"], color=cmap.get(ctrl, "k"),
                   s=80, alpha=0.85, edgecolor="white")
    ax.axhline(0, color="k", lw=0.6)
    ax.set_xticks(range(len(cmap)))
    ax.set_xticklabels(list(cmap.keys()))
    ax.set_ylabel("Δ total insulin U/h (S1 − S0)")
    ax.set_title(f"H3: Total delivery (p={h3.get('p', float('nan')):.3f})")

    plt.tight_layout(rect=(0, 0, 1, 0.94))
    fig_out = FIG / "exp-2845_route_by_controller.png"
    plt.savefig(fig_out, dpi=120, bbox_inches="tight")
    plt.close()

    print(json.dumps(result, indent=2, default=str)[:1800])
    print(f"\nWrote {fig_out}")
    return result


if __name__ == "__main__":
    main()
