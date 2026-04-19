#!/usr/bin/env python3
"""EXP-2684: Aggregate Outcome Modeling — Controller Settings vs TIR/Hypo

Pivots from individual-event ISF analysis (proven futile at R²=0.165) to
aggregate outcome modeling: how do controller SETTINGS predict
TIME-IN-RANGE, HYPO RATE, and MEAN GLUCOSE?

This is the productive research direction after proving that:
  - Individual correction BG drop is 83.5% stochastic noise
  - Insulin dose is nearly irrelevant to individual BG drop
  - AID controller dominates individual correction trajectories

Aggregate metrics smooth over the stochastic noise and reveal whether
settings actually matter at the population level.

6-panel dashboard:
  1. TIR / hypo / mean BG by controller type
  2. Settings vs outcomes: scheduled ISF → TIR, hypo
  3. Settings vs outcomes: scheduled CR → TIR, hypo
  4. Controller aggressiveness (total daily insulin) vs outcomes
  5. Safety frontier: TIR vs hypo rate (Pareto)
  6. Per-patient outcome summary table
"""
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from pathlib import Path
from scipy import stats

VIS = Path("visualizations/aggregate-outcomes")
VIS.mkdir(parents=True, exist_ok=True)
EXP = Path("externals/experiments")

manifest = json.load(open(EXP / "autoprepare-qualified.json"))
grid = pd.read_parquet("externals/ns-parquet/training/grid.parquet")
ds = pd.read_parquet("externals/ns-parquet/training/devicestatus.parquet")
ctrl_map = ds.groupby("patient_id")["controller"].first().to_dict()
grid = grid[grid["patient_id"].isin(manifest["qualified_patients"])].copy()
grid["controller"] = grid["patient_id"].map(ctrl_map)

TIR_LOW, TIR_HIGH = 70.0, 180.0

# Compute per-patient aggregate outcomes
print("Computing per-patient aggregate outcomes...")
patient_outcomes = []

for pid in grid["patient_id"].unique():
    pdf = grid[grid["patient_id"] == pid]
    bg = pdf["glucose"].dropna()
    if len(bg) < 100:
        continue

    ctrl = ctrl_map.get(pid, "unknown")

    # Glycemic outcomes
    tir = ((bg >= TIR_LOW) & (bg <= TIR_HIGH)).mean() * 100
    hypo = (bg < TIR_LOW).mean() * 100
    severe_hypo = (bg < 54).mean() * 100
    hyper = (bg > TIR_HIGH).mean() * 100
    mean_bg = bg.mean()
    std_bg = bg.std()
    cv = std_bg / mean_bg * 100 if mean_bg > 0 else np.nan

    # Insulin metrics
    total_bolus = pdf["bolus"].sum()
    total_smb = pdf["bolus_smb"].sum() if "bolus_smb" in pdf.columns else 0
    total_basal = (pdf["actual_basal_rate"].mean() * len(pdf) * 5 / 60
                   if "actual_basal_rate" in pdf.columns else np.nan)
    days = (pdf["time"].max() - pdf["time"].min()).total_seconds() / 86400
    tdd = (total_bolus + (total_basal if not pd.isna(total_basal) else 0)) / max(days, 1)

    # Settings
    median_isf = pdf["scheduled_isf"].median()
    median_cr = pdf["scheduled_cr"].median()
    median_basal = pdf["scheduled_basal_rate"].median()

    # IOB statistics
    median_iob = pdf["iob"].median() if "iob" in pdf.columns else np.nan

    patient_outcomes.append({
        "patient_id": pid,
        "controller": ctrl,
        "n_readings": len(bg),
        "days": days,
        "tir": tir,
        "hypo": hypo,
        "severe_hypo": severe_hypo,
        "hyper": hyper,
        "mean_bg": mean_bg,
        "std_bg": std_bg,
        "cv": cv,
        "tdd": tdd,
        "total_bolus_per_day": total_bolus / max(days, 1),
        "total_smb_per_day": total_smb / max(days, 1),
        "median_isf": median_isf,
        "median_cr": median_cr,
        "median_basal": median_basal,
        "median_iob": median_iob,
    })

outcomes = pd.DataFrame(patient_outcomes)
print(f"Patients: {len(outcomes)} (Loop={sum(outcomes['controller']=='loop')}, "
      f"Trio={sum(outcomes['controller']=='trio')}, "
      f"OpenAPS={sum(outcomes['controller']=='openaps')})")

results = {"n_patients": len(outcomes)}
colors = {"loop": "C0", "trio": "C1", "openaps": "C2"}

# ── Panel 1: Outcomes by Controller ──────────────────────────────────
fig, axes = plt.subplots(2, 2, figsize=(14, 10))

metrics = [
    ("tir", "Time in Range (%)", axes[0, 0]),
    ("hypo", "Time Below 70 (%)", axes[0, 1]),
    ("mean_bg", "Mean BG (mg/dL)", axes[1, 0]),
    ("cv", "Glycemic Variability (CV%)", axes[1, 1]),
]

for col, label, ax in metrics:
    data = []
    labels = []
    ctrl_colors = []
    for ctrl in ["loop", "trio", "openaps"]:
        sub = outcomes[outcomes["controller"] == ctrl]
        if len(sub) > 0:
            data.append(sub[col].dropna().values)
            labels.append(f"{ctrl}\n(n={len(sub)})")
            ctrl_colors.append(colors[ctrl])

    bp = ax.boxplot(data, patch_artist=True, widths=0.6)
    for patch, c in zip(bp["boxes"], ctrl_colors):
        patch.set_facecolor(c)
        patch.set_alpha(0.6)
    ax.set_xticklabels(labels)
    ax.set_ylabel(label)
    ax.set_title(label)

    # Kruskal-Wallis across controllers
    data_clean = [d for d in data if len(d) > 1]
    if len(data_clean) >= 2:
        kw_stat, kw_p = stats.kruskal(*data_clean)
        ax.text(0.02, 0.98, f"KW p={kw_p:.3f}", transform=ax.transAxes,
               va="top", fontsize=9, style="italic")
        results[f"kw_{col}"] = {"statistic": float(kw_stat), "p": float(kw_p)}

plt.suptitle("Glycemic Outcomes by Controller Type", fontsize=14)
plt.tight_layout()
plt.savefig(VIS / "fig1_outcomes_by_controller.png", dpi=150)
plt.close()
print("Panel 1: Outcomes by controller saved")

# Print summary
for ctrl in ["loop", "trio", "openaps"]:
    sub = outcomes[outcomes["controller"] == ctrl]
    if len(sub) > 0:
        print(f"\n  {ctrl} (n={len(sub)}):")
        print(f"    TIR: {sub['tir'].median():.1f}%, hypo: {sub['hypo'].median():.1f}%")
        print(f"    Mean BG: {sub['mean_bg'].median():.0f}, CV: {sub['cv'].median():.1f}%")
        print(f"    TDD: {sub['tdd'].median():.1f} U/day")

# ── Panel 2: Scheduled ISF vs Outcomes ───────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 6))

valid = outcomes.dropna(subset=["median_isf"])
for ctrl in ["loop", "trio", "openaps"]:
    sub = valid[valid["controller"] == ctrl]
    if len(sub) > 0:
        axes[0].scatter(sub["median_isf"], sub["tir"], c=colors[ctrl],
                       s=80, alpha=0.7, label=ctrl)
        axes[1].scatter(sub["median_isf"], sub["hypo"], c=colors[ctrl],
                       s=80, alpha=0.7, label=ctrl)

if len(valid) > 5:
    r_tir, p_tir = stats.spearmanr(valid["median_isf"], valid["tir"])
    r_hypo, p_hypo = stats.spearmanr(valid["median_isf"], valid["hypo"])
    axes[0].set_title(f"ISF vs TIR (r={r_tir:.3f}, p={p_tir:.3f})")
    axes[1].set_title(f"ISF vs Hypo (r={r_hypo:.3f}, p={p_hypo:.3f})")
    results["isf_vs_tir"] = {"r": float(r_tir), "p": float(p_tir)}
    results["isf_vs_hypo"] = {"r": float(r_hypo), "p": float(p_hypo)}

axes[0].set_xlabel("Scheduled ISF (mg/dL per U)")
axes[0].set_ylabel("TIR (%)")
axes[0].legend()
axes[1].set_xlabel("Scheduled ISF (mg/dL per U)")
axes[1].set_ylabel("Time Below 70 (%)")
axes[1].legend()

plt.suptitle("Do ISF Settings Predict Outcomes?", fontsize=14)
plt.tight_layout()
plt.savefig(VIS / "fig2_isf_vs_outcomes.png", dpi=150)
plt.close()
print("Panel 2: ISF vs outcomes saved")

# ── Panel 3: Scheduled CR vs Outcomes ────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 6))

valid = outcomes.dropna(subset=["median_cr"])
for ctrl in ["loop", "trio", "openaps"]:
    sub = valid[valid["controller"] == ctrl]
    if len(sub) > 0:
        axes[0].scatter(sub["median_cr"], sub["tir"], c=colors[ctrl],
                       s=80, alpha=0.7, label=ctrl)
        axes[1].scatter(sub["median_cr"], sub["hypo"], c=colors[ctrl],
                       s=80, alpha=0.7, label=ctrl)

if len(valid) > 5:
    r_tir, p_tir = stats.spearmanr(valid["median_cr"], valid["tir"])
    r_hypo, p_hypo = stats.spearmanr(valid["median_cr"], valid["hypo"])
    axes[0].set_title(f"CR vs TIR (r={r_tir:.3f}, p={p_tir:.3f})")
    axes[1].set_title(f"CR vs Hypo (r={r_hypo:.3f}, p={p_hypo:.3f})")
    results["cr_vs_tir"] = {"r": float(r_tir), "p": float(p_tir)}
    results["cr_vs_hypo"] = {"r": float(r_hypo), "p": float(p_hypo)}

axes[0].set_xlabel("Scheduled CR (g/U)")
axes[0].set_ylabel("TIR (%)")
axes[0].legend()
axes[1].set_xlabel("Scheduled CR (g/U)")
axes[1].set_ylabel("Time Below 70 (%)")
axes[1].legend()

plt.suptitle("Do CR Settings Predict Outcomes?", fontsize=14)
plt.tight_layout()
plt.savefig(VIS / "fig3_cr_vs_outcomes.png", dpi=150)
plt.close()
print("Panel 3: CR vs outcomes saved")

# ── Panel 4: Controller Aggressiveness vs Outcomes ───────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 6))

for ctrl in ["loop", "trio", "openaps"]:
    sub = outcomes[outcomes["controller"] == ctrl]
    if len(sub) > 0:
        axes[0].scatter(sub["tdd"], sub["tir"], c=colors[ctrl],
                       s=80, alpha=0.7, label=ctrl)
        axes[1].scatter(sub["tdd"], sub["hypo"], c=colors[ctrl],
                       s=80, alpha=0.7, label=ctrl)

if len(outcomes) > 5:
    r_tir, p_tir = stats.spearmanr(outcomes["tdd"], outcomes["tir"])
    r_hypo, p_hypo = stats.spearmanr(outcomes["tdd"], outcomes["hypo"])
    axes[0].set_title(f"TDD vs TIR (r={r_tir:.3f}, p={p_tir:.3f})")
    axes[1].set_title(f"TDD vs Hypo (r={r_hypo:.3f}, p={p_hypo:.3f})")
    results["tdd_vs_tir"] = {"r": float(r_tir), "p": float(p_tir)}
    results["tdd_vs_hypo"] = {"r": float(r_hypo), "p": float(p_hypo)}

axes[0].set_xlabel("Total Daily Dose (U/day)")
axes[0].set_ylabel("TIR (%)")
axes[0].legend()
axes[1].set_xlabel("Total Daily Dose (U/day)")
axes[1].set_ylabel("Time Below 70 (%)")
axes[1].legend()

plt.suptitle("Does More Insulin = Better Outcomes?", fontsize=14)
plt.tight_layout()
plt.savefig(VIS / "fig4_tdd_vs_outcomes.png", dpi=150)
plt.close()
print("Panel 4: TDD vs outcomes saved")

# ── Panel 5: Safety Frontier (TIR vs Hypo) ──────────────────────────
fig, ax = plt.subplots(figsize=(10, 8))

for ctrl in ["loop", "trio", "openaps"]:
    sub = outcomes[outcomes["controller"] == ctrl]
    if len(sub) > 0:
        ax.scatter(sub["hypo"], sub["tir"], c=colors[ctrl], s=100, alpha=0.7,
                  label=ctrl, edgecolors="black", linewidths=0.5)
        for _, row in sub.iterrows():
            short = row["patient_id"][:6]
            ax.annotate(short, (row["hypo"], row["tir"]),
                       fontsize=6, alpha=0.7, ha="left")

# Ideal corner: top-left (high TIR, low hypo)
ax.axhline(70, color="green", linestyle="--", alpha=0.3, label="TIR=70% target")
ax.axvline(4, color="red", linestyle="--", alpha=0.3, label="Hypo=4% limit")
ax.set_xlabel("Time Below 70 (%)")
ax.set_ylabel("Time in Range (%)")
ax.set_title("Safety Frontier: TIR vs Hypoglycemia")
ax.legend(loc="lower left")
ax.invert_xaxis()  # Low hypo on the right (good)

# Compute Pareto frontier
sorted_pts = outcomes.sort_values("hypo")
pareto = []
max_tir = -1
for _, row in sorted_pts.iterrows():
    if row["tir"] > max_tir:
        pareto.append((row["hypo"], row["tir"]))
        max_tir = row["tir"]

if pareto:
    px, py = zip(*pareto)
    ax.plot(px, py, "k-", linewidth=2, alpha=0.5, label="Pareto frontier")
    ax.legend(loc="lower left")

plt.tight_layout()
plt.savefig(VIS / "fig5_safety_frontier.png", dpi=150)
plt.close()
print("Panel 5: Safety frontier saved")

# ── Panel 6: Summary Table ──────────────────────────────────────────
fig, ax = plt.subplots(figsize=(16, 10))
ax.axis("off")

rows = []
for _, row in outcomes.sort_values(["controller", "tir"], ascending=[True, False]).iterrows():
    rows.append([
        row["patient_id"][:12],
        row["controller"],
        f"{row['days']:.0f}",
        f"{row['tir']:.1f}",
        f"{row['hypo']:.1f}",
        f"{row['mean_bg']:.0f}",
        f"{row['cv']:.1f}",
        f"{row['tdd']:.1f}",
        f"{row['median_isf']:.0f}" if not pd.isna(row["median_isf"]) else "—",
        f"{row['median_cr']:.0f}" if not pd.isna(row["median_cr"]) else "—",
    ])

table = ax.table(
    cellText=rows,
    colLabels=["Patient", "Controller", "Days", "TIR%", "Hypo%", "Mean BG",
               "CV%", "TDD", "ISF", "CR"],
    loc="center",
    cellLoc="center",
)
table.auto_set_font_size(False)
table.set_fontsize(7)
table.scale(1, 1.2)

ctrl_colors = {"loop": "#cce5ff", "trio": "#ffe5cc", "openaps": "#ccffcc"}
for i, row_data in enumerate(rows):
    color = ctrl_colors.get(row_data[1], "white")
    for j in range(len(row_data)):
        table[i + 1, j].set_facecolor(color)

ax.set_title("EXP-2684: Aggregate Outcomes Summary", fontsize=14, pad=20)
plt.tight_layout()
plt.savefig(VIS / "fig6_summary_table.png", dpi=150)
plt.close()
print("Panel 6: Summary table saved")

# Store per-patient results
results["by_patient"] = {row["patient_id"]: {
    "controller": row["controller"],
    "tir": float(row["tir"]),
    "hypo": float(row["hypo"]),
    "mean_bg": float(row["mean_bg"]),
    "tdd": float(row["tdd"]),
    "median_isf": float(row["median_isf"]) if not pd.isna(row["median_isf"]) else None,
} for _, row in outcomes.iterrows()}

# Save
with open(EXP / "exp-2684_aggregate_outcomes.json", "w") as f:
    json.dump(results, f, indent=2, default=str)

print(f"\n{'='*60}")
print(f"EXP-2684: Aggregate Outcome Modeling — RESULTS")
print(f"{'='*60}")
print(f"Patients: {len(outcomes)}")
for ctrl in ["loop", "trio", "openaps"]:
    sub = outcomes[outcomes["controller"] == ctrl]
    if len(sub) > 0:
        print(f"\n  {ctrl} (n={len(sub)}):")
        print(f"    TIR: {sub['tir'].median():.1f}% [{sub['tir'].min():.0f}-{sub['tir'].max():.0f}]")
        print(f"    Hypo: {sub['hypo'].median():.1f}% [{sub['hypo'].min():.0f}-{sub['hypo'].max():.0f}]")
        print(f"    Mean BG: {sub['mean_bg'].median():.0f} mg/dL")
        print(f"    TDD: {sub['tdd'].median():.1f} U/day")

print(f"\nSettings → Outcomes correlations:")
for k in ["isf_vs_tir", "isf_vs_hypo", "cr_vs_tir", "cr_vs_hypo", "tdd_vs_tir", "tdd_vs_hypo"]:
    if k in results:
        print(f"  {k}: r={results[k]['r']:.3f}, p={results[k]['p']:.3f}")
