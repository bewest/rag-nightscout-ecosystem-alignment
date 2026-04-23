"""EXP-2892 — Protection-mechanism signature by lineage.

Hypothesis (from EXP-2891): oref1 protects setting-independently
because it has MULTIPLE protective channels (basal-cut + SMB-off),
while oref0 relies primarily on basal-cut which is capped at the
user's scheduled basal.  At conservative profiles, the basal-cut
channel has a low ceiling, leaving oref0 under-protected.

Test:
  Decompose extra-drop prevention into
    channel_A = basal-cut ceiling    = sched_basal * duration_h * ISF
    channel_B = SMB-off / IOB-shed   = (iob_start - iob_nadir) * ISF
                                        clipped to nonneg
  For each lineage × tercile, report the ratio of channels and
  correlate channel A ceiling with observed protection.

Writes exp-2892_mechanism.{parquet,png,json}.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
EXP = ROOT / "externals" / "experiments"
FIG = ROOT / "docs" / "60-research" / "figures"
FIG.mkdir(parents=True, exist_ok=True)

ISF_POP = 50.0

evt = pd.read_parquet(EXP / "exp-2881_evening_drivers.parquet")
evt = evt[evt["descent_slope"] < -0.05].copy()
evt["duration_min"] = ((evt["bg_start"] - evt["bg_nadir"])
                       / (-evt["descent_slope"])).clip(5, 360)
evt["duration_h"] = evt["duration_min"] / 60.0

evt["basal_ceiling_U"] = evt["sched_basal"] * evt["duration_h"]
evt["basal_cut_U"] = (evt["sched_basal"] - evt["actual_basal"]).clip(lower=0) * evt["duration_h"]
evt["iob_shed_U"] = (evt["iob_start"] - evt["iob_nadir"]).clip(lower=0)

evt["channel_A_mgdl"] = evt["basal_cut_U"] * ISF_POP        # actual basal cut
evt["channel_B_mgdl"] = evt["iob_shed_U"] * ISF_POP         # IOB shed (SMB-off/suspension)
evt["ceiling_A_mgdl"] = evt["basal_ceiling_U"] * ISF_POP    # max possible basal cut

sim = pd.read_parquet(EXP / "exp-2891_simpson_dose_response.parquet")[
    ["patient_id", "lineage", "tercile", "aid_protection_severe", "archetype"]
]

per = (evt.groupby("patient_id")
          .agg(mean_ceiling_A=("ceiling_A_mgdl", "mean"),
               mean_cut_A=("channel_A_mgdl", "mean"),
               mean_shed_B=("channel_B_mgdl", "mean"),
               n_events=("bg_start", "size"))
          .reset_index())
per["ratio_A_vs_B"] = per["mean_cut_A"] / (per["mean_cut_A"] + per["mean_shed_B"] + 1e-9)

m = per.merge(sim, on="patient_id", how="inner")
print("Rows merged:", len(m))

# 1) per-lineage channel decomposition
by_lin = (m.groupby("lineage")
            .agg(n=("patient_id","nunique"),
                 mean_ceiling_A=("mean_ceiling_A","mean"),
                 mean_cut_A=("mean_cut_A","mean"),
                 mean_shed_B=("mean_shed_B","mean"),
                 ratio_A=("ratio_A_vs_B","mean"),
                 prot=("aid_protection_severe","mean"))
            .round(3))
print("\nBy lineage:")
print(by_lin)

# 2) per-lineage × tercile ceiling
by_tc = (m.groupby(["lineage","tercile"])
            .agg(n=("patient_id","nunique"),
                 ceiling_A=("mean_ceiling_A","mean"),
                 cut_A=("mean_cut_A","mean"),
                 shed_B=("mean_shed_B","mean"),
                 prot=("aid_protection_severe","mean"))
            .round(3))
print("\nBy lineage × tercile:")
print(by_tc)

# 3) correlation: ceiling_A vs protection (within conservative tier, across lineage)
cons = m[m["tercile"]=="conservative"]
if len(cons) >= 3:
    from scipy.stats import spearmanr
    rho, p = spearmanr(cons["mean_ceiling_A"], cons["aid_protection_severe"])
    print(f"\nConservative-tier only (n={len(cons)}):")
    print(f"  Spearman ceiling_A vs protection: rho={rho:.3f} p={p:.3f}")
else:
    rho, p = np.nan, np.nan

# 4) figure: stacked bar of A vs B by lineage, and ceiling vs protection scatter
fig, axes = plt.subplots(1, 2, figsize=(13, 5))

lin_order = ["oref0 (legacy)", "Loop (iOS)", "oref1 (modern)", "unknown"]
plot_df = by_lin.reindex([l for l in lin_order if l in by_lin.index])
x = np.arange(len(plot_df))
axes[0].bar(x, plot_df["mean_cut_A"], label="channel A: basal-cut", color="steelblue")
axes[0].bar(x, plot_df["mean_shed_B"], bottom=plot_df["mean_cut_A"],
            label="channel B: IOB-shed", color="firebrick")
axes[0].set_xticks(x)
axes[0].set_xticklabels(plot_df.index, rotation=15)
axes[0].set_ylabel("mean protective mg/dL per event")
axes[0].set_title("Protection-channel decomposition by lineage")
axes[0].legend()

colors = {"Loop (iOS)":"tab:blue", "oref1 (modern)":"tab:green",
          "oref0 (legacy)":"tab:red", "unknown":"gray"}
for lin, sub in m.groupby("lineage"):
    axes[1].scatter(sub["mean_ceiling_A"], sub["aid_protection_severe"],
                    c=colors.get(lin,"k"), label=lin, s=60, alpha=0.75)
axes[1].set_xlabel("basal-cut ceiling (mg/dL, per event)")
axes[1].set_ylabel("AID protection (severe)")
axes[1].set_title(f"Ceiling vs protection (all terciles)")
axes[1].legend(fontsize=8)
axes[1].grid(alpha=0.3)

plt.tight_layout()
out_png = FIG / "exp-2892_mechanism.png"
plt.savefig(out_png, dpi=120)
print(f"\nWrote {out_png.relative_to(ROOT)}")

m.to_parquet(EXP / "exp-2892_mechanism.parquet", index=False)

summary = {
    "isf_pop": ISF_POP,
    "n_patients": int(m["patient_id"].nunique()),
    "by_lineage": by_lin.reset_index().to_dict(orient="records"),
    "by_lineage_tercile": by_tc.reset_index().to_dict(orient="records"),
    "conservative_tier_rho_ceiling_vs_prot": float(rho) if rho==rho else None,
    "conservative_tier_p_ceiling_vs_prot": float(p) if p==p else None,
}
(EXP / "exp-2892_mechanism_summary.json").write_text(json.dumps(summary, indent=2))
print("Wrote exp-2892_mechanism_summary.json")
