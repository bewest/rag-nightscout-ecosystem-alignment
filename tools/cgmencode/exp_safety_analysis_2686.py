#!/usr/bin/env python3
"""EXP-2686: Safety Analysis — Aggressiveness vs Hypoglycemia Risk

EXP-2684 showed Trio achieves 89.9% TIR, but with 4.1% hypo (vs Loop 3.2%).
EXP-2685 showed Trio uses extreme bang-bang control (83% suspend, aggressive SMBs).

Is the extra hypo risk worth the TIR gain? Where does the hypo come from?

6-panel dashboard:
  1. Safety frontier with clinical targets (TIR>70, hypo<4%)
  2. Hypo event characterization: depth, duration, recovery
  3. Hypo temporal patterns: when do hypos happen?
  4. Pre-hypo controller behavior: what was the controller doing before hypo?
  5. IOB at hypo onset by controller
  6. DynISF formula effect within Trio patients
"""
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from pathlib import Path
from scipy import stats

VIS = Path("visualizations/safety-analysis")
VIS.mkdir(parents=True, exist_ok=True)
EXP = Path("externals/experiments")

manifest = json.load(open(EXP / "autoprepare-qualified.json"))
grid = pd.read_parquet("externals/ns-parquet/training/grid.parquet")
ds = pd.read_parquet("externals/ns-parquet/training/devicestatus.parquet")
ctrl_map = ds.groupby("patient_id")["controller"].first().to_dict()
grid = grid[grid["patient_id"].isin(manifest["qualified_patients"])].copy()
grid["controller"] = grid["patient_id"].map(ctrl_map)

TIR_LOW, TIR_HIGH = 70.0, 180.0
results = {}
colors = {"loop": "C0", "trio": "C1", "openaps": "C2"}

# DynISF formula annotations
SIGMOID_PATIENTS = {"ns-9b9a6a874e51", "ns-adde5f4af7ca", "ns-dde9e7c2e752",
                     "ns-554b16de7133", "ns-6bef17b4c1ec", "ns-c422538aa12a"}
LOG_PATIENTS = {"ns-d444c120c23a", "ns-8b3c1b50793c", "ns-a9ce2317bead",
                "ns-8ffa739b986b", "ns-1ccae8a375b9"}

# ── Extract hypo events ──────────────────────────────────────────────
def extract_hypo_events(df, threshold=70):
    """Find hypoglycemic episodes with full context."""
    events = []
    for pid in df["patient_id"].unique():
        pdf = df[df["patient_id"] == pid].sort_values("time").reset_index(drop=True)
        ctrl = ctrl_map.get(pid, "unknown")
        bg = pdf["glucose"].values
        in_hypo = False
        hypo_start = None
        nadir = 500

        for i in range(len(pdf)):
            if pd.isna(bg[i]):
                continue
            if bg[i] < threshold and not in_hypo:
                in_hypo = True
                hypo_start = i
                nadir = bg[i]
            elif bg[i] < threshold and in_hypo:
                nadir = min(nadir, bg[i])
            elif bg[i] >= threshold and in_hypo:
                in_hypo = False
                duration_min = (i - hypo_start) * 5
                # Pre-hypo context (30 min before)
                pre_start = max(0, hypo_start - 6)
                pre_bg = bg[pre_start:hypo_start]
                pre_bg = pre_bg[~np.isnan(pre_bg)]
                pre_iob = pdf["iob"].iloc[pre_start:hypo_start].median() if "iob" in pdf.columns else np.nan
                pre_smb = pdf["bolus_smb"].iloc[pre_start:hypo_start].sum() if "bolus_smb" in pdf.columns else 0
                pre_basal = pdf["actual_basal_rate"].iloc[pre_start:hypo_start].mean() if "actual_basal_rate" in pdf.columns else np.nan
                sched_basal = pdf["scheduled_basal_rate"].iloc[pre_start:hypo_start].mean() if "scheduled_basal_rate" in pdf.columns else np.nan

                onset_bg = bg[hypo_start] if not pd.isna(bg[hypo_start]) else np.nan
                onset_iob = pdf["iob"].iloc[hypo_start] if "iob" in pdf.columns else np.nan

                events.append({
                    "patient_id": pid,
                    "controller": ctrl,
                    "time": pdf["time"].iloc[hypo_start],
                    "hour": pd.Timestamp(pdf["time"].iloc[hypo_start]).hour,
                    "duration_min": duration_min,
                    "nadir": nadir,
                    "onset_bg": onset_bg,
                    "onset_iob": float(onset_iob) if not pd.isna(onset_iob) else np.nan,
                    "pre_30min_mean_bg": float(np.mean(pre_bg)) if len(pre_bg) > 0 else np.nan,
                    "pre_30min_iob": float(pre_iob),
                    "pre_30min_smb": float(pre_smb),
                    "pre_30min_basal": float(pre_basal),
                    "pre_sched_basal": float(sched_basal),
                    "severe": nadir < 54,
                })
    return pd.DataFrame(events)


print("Extracting hypo events...")
hypo = extract_hypo_events(grid)
print(f"Total hypo events: {len(hypo)}")

for ctrl in ["loop", "trio", "openaps"]:
    sub = hypo[hypo["controller"] == ctrl]
    severe = sub[sub["severe"]]
    print(f"  {ctrl}: {len(sub)} events, {len(severe)} severe (<54)")
    results[f"{ctrl}_hypo"] = {
        "n_events": len(sub),
        "n_severe": len(severe),
        "median_duration": float(sub["duration_min"].median()) if len(sub) > 0 else 0,
        "median_nadir": float(sub["nadir"].median()) if len(sub) > 0 else 0,
    }

# ── Panel 1: Safety Frontier with Clinical Targets ───────────────────
fig, ax = plt.subplots(figsize=(10, 8))

# Compute per-patient TIR/hypo
patient_outcomes = []
for pid in grid["patient_id"].unique():
    pdf = grid[grid["patient_id"] == pid]
    bg = pdf["glucose"].dropna()
    ctrl = ctrl_map.get(pid, "unknown")
    tir = ((bg >= TIR_LOW) & (bg <= TIR_HIGH)).mean() * 100
    hypo_pct = (bg < TIR_LOW).mean() * 100
    severe_pct = (bg < 54).mean() * 100
    patient_outcomes.append({"patient_id": pid, "controller": ctrl,
                            "tir": tir, "hypo": hypo_pct, "severe": severe_pct})

po = pd.DataFrame(patient_outcomes)

for ctrl in ["loop", "trio", "openaps"]:
    sub = po[po["controller"] == ctrl]
    ax.scatter(sub["hypo"], sub["tir"], c=colors[ctrl], s=120, alpha=0.7,
              label=ctrl, edgecolors="black", linewidths=0.5, zorder=5)
    for _, row in sub.iterrows():
        ax.annotate(row["patient_id"][:6], (row["hypo"] + 0.1, row["tir"] - 1),
                   fontsize=6, alpha=0.7)

# Clinical targets
ax.axhline(70, color="green", linestyle="--", alpha=0.4, linewidth=2)
ax.axvline(4, color="red", linestyle="--", alpha=0.4, linewidth=2)
ax.fill_between([0, 4], [70, 70], [100, 100], alpha=0.05, color="green", label="Clinical target zone")

ax.set_xlabel("Time Below 70 mg/dL (%)", fontsize=12)
ax.set_ylabel("Time in Range 70-180 (%)", fontsize=12)
ax.set_title("Safety Frontier: TIR vs Hypoglycemia Risk", fontsize=14)
ax.legend(loc="lower left")
ax.set_xlim(-0.5, max(po["hypo"]) * 1.1)

plt.tight_layout()
plt.savefig(VIS / "fig1_safety_frontier.png", dpi=150)
plt.close()
print("Panel 1: Safety frontier saved")

# Count patients in clinical target zone
for ctrl in ["loop", "trio", "openaps"]:
    sub = po[po["controller"] == ctrl]
    in_target = ((sub["tir"] >= 70) & (sub["hypo"] <= 4)).sum()
    print(f"  {ctrl}: {in_target}/{len(sub)} in clinical target (TIR≥70, hypo≤4%)")
    results[f"{ctrl}_in_target"] = {"n": int(in_target), "total": len(sub)}

# ── Panel 2: Hypo Event Characterization ─────────────────────────────
fig, axes = plt.subplots(1, 3, figsize=(16, 5))

# 2a: Duration
for ctrl in ["loop", "trio", "openaps"]:
    sub = hypo[hypo["controller"] == ctrl]
    if len(sub) > 5:
        axes[0].hist(sub["duration_min"].clip(0, 120), bins=24, alpha=0.5,
                    label=f"{ctrl} (median={sub['duration_min'].median():.0f}min)",
                    density=True, color=colors[ctrl])
axes[0].set_xlabel("Hypo Duration (minutes)")
axes[0].set_ylabel("Density")
axes[0].set_title("Hypoglycemic Episode Duration")
axes[0].legend(fontsize=8)

# 2b: Nadir
for ctrl in ["loop", "trio", "openaps"]:
    sub = hypo[hypo["controller"] == ctrl]
    if len(sub) > 5:
        axes[1].hist(sub["nadir"], bins=30, alpha=0.5,
                    label=f"{ctrl} (median={sub['nadir'].median():.0f})",
                    density=True, color=colors[ctrl])
axes[1].axvline(54, color="red", linestyle="--", alpha=0.5, label="54 mg/dL (severe)")
axes[1].set_xlabel("Nadir BG (mg/dL)")
axes[1].set_ylabel("Density")
axes[1].set_title("Hypo Nadir Distribution")
axes[1].legend(fontsize=8)

# 2c: Onset BG (where was BG 30min before hypo)
for ctrl in ["loop", "trio", "openaps"]:
    sub = hypo[hypo["controller"] == ctrl]
    valid = sub.dropna(subset=["pre_30min_mean_bg"])
    if len(valid) > 5:
        axes[2].hist(valid["pre_30min_mean_bg"].clip(50, 200), bins=30, alpha=0.5,
                    label=f"{ctrl} (median={valid['pre_30min_mean_bg'].median():.0f})",
                    density=True, color=colors[ctrl])
axes[2].set_xlabel("Mean BG 30min Before Hypo (mg/dL)")
axes[2].set_ylabel("Density")
axes[2].set_title("Pre-Hypo BG Level")
axes[2].axvline(TIR_LOW, color="orange", linestyle="--", alpha=0.5)
axes[2].legend(fontsize=8)

plt.tight_layout()
plt.savefig(VIS / "fig2_hypo_characterization.png", dpi=150)
plt.close()
print("Panel 2: Hypo characterization saved")

# ── Panel 3: Hypo Temporal Patterns ──────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 6))

for ctrl in ["loop", "trio", "openaps"]:
    sub = hypo[hypo["controller"] == ctrl]
    if len(sub) > 5:
        hourly = sub.groupby("hour").size()
        hourly = hourly.reindex(range(24), fill_value=0)
        axes[0].plot(hourly.index, hourly.values, "o-", color=colors[ctrl],
                    label=ctrl, linewidth=2)

axes[0].set_xlabel("Hour of Day (UTC)")
axes[0].set_ylabel("Number of Hypo Events")
axes[0].set_title("Hypo Events by Hour")
axes[0].legend()

# Severe hypos by hour
for ctrl in ["loop", "trio", "openaps"]:
    sub = hypo[(hypo["controller"] == ctrl) & (hypo["severe"])]
    if len(sub) > 3:
        hourly = sub.groupby("hour").size()
        hourly = hourly.reindex(range(24), fill_value=0)
        axes[1].plot(hourly.index, hourly.values, "o-", color=colors[ctrl],
                    label=ctrl, linewidth=2)

axes[1].set_xlabel("Hour of Day (UTC)")
axes[1].set_ylabel("Number of Severe Hypo Events")
axes[1].set_title("Severe Hypo (<54) by Hour")
axes[1].legend()

plt.tight_layout()
plt.savefig(VIS / "fig3_hypo_temporal.png", dpi=150)
plt.close()
print("Panel 3: Temporal patterns saved")

# ── Panel 4: Pre-Hypo Controller Behavior ────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 6))

# 4a: Pre-hypo SMB delivery
for ctrl in ["loop", "trio", "openaps"]:
    sub = hypo[hypo["controller"] == ctrl]
    valid = sub.dropna(subset=["pre_30min_smb"])
    if len(valid) > 5:
        axes[0].hist(valid["pre_30min_smb"].clip(0, 3), bins=20, alpha=0.5,
                    label=f"{ctrl} (median={valid['pre_30min_smb'].median():.2f}U)",
                    density=True, color=colors[ctrl])
axes[0].set_xlabel("Total SMBs in 30min Before Hypo (U)")
axes[0].set_ylabel("Density")
axes[0].set_title("SMB Delivery Before Hypo")
axes[0].legend(fontsize=8)

# 4b: Pre-hypo basal (as ratio of scheduled)
for ctrl in ["loop", "trio", "openaps"]:
    sub = hypo[hypo["controller"] == ctrl]
    valid = sub.dropna(subset=["pre_30min_basal", "pre_sched_basal"])
    valid = valid[valid["pre_sched_basal"] > 0]
    if len(valid) > 5:
        ratio = valid["pre_30min_basal"] / valid["pre_sched_basal"]
        ratio = ratio.clip(0, 3)
        axes[1].hist(ratio, bins=20, alpha=0.5,
                    label=f"{ctrl} (median={ratio.median():.2f})",
                    density=True, color=colors[ctrl])
axes[1].axvline(1.0, color="gray", linestyle="--", alpha=0.5, label="1.0 = scheduled")
axes[1].set_xlabel("Basal Rate / Scheduled Rate (30min before hypo)")
axes[1].set_ylabel("Density")
axes[1].set_title("Basal Rate Before Hypo")
axes[1].legend(fontsize=8)

plt.tight_layout()
plt.savefig(VIS / "fig4_prehypo_controller.png", dpi=150)
plt.close()
print("Panel 4: Pre-hypo controller saved")

# ── Panel 5: IOB at Hypo Onset ──────────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 6))

for ctrl in ["loop", "trio", "openaps"]:
    sub = hypo[hypo["controller"] == ctrl]
    valid = sub.dropna(subset=["onset_iob"])
    if len(valid) > 5:
        axes[0].hist(valid["onset_iob"].clip(-2, 10), bins=30, alpha=0.5,
                    label=f"{ctrl} (median={valid['onset_iob'].median():.1f}U)",
                    density=True, color=colors[ctrl])

axes[0].set_xlabel("IOB at Hypo Onset (U)")
axes[0].set_ylabel("Density")
axes[0].set_title("IOB When Entering Hypoglycemia")
axes[0].legend(fontsize=8)

# 5b: IOB at hypo vs overall IOB distribution
for ctrl in ["loop", "trio", "openaps"]:
    sub_all = grid[grid["controller"] == ctrl]["iob"].dropna()
    sub_hypo = hypo[hypo["controller"] == ctrl]["onset_iob"].dropna()
    if len(sub_all) > 100 and len(sub_hypo) > 5:
        axes[1].boxplot([sub_all.clip(-2, 10).values, sub_hypo.clip(-2, 10).values],
                       positions=[["loop", "trio", "openaps"].index(ctrl) * 3,
                                  ["loop", "trio", "openaps"].index(ctrl) * 3 + 1],
                       widths=0.6, patch_artist=True,
                       boxprops=dict(facecolor=colors[ctrl], alpha=0.5))
        results[f"{ctrl}_iob_comparison"] = {
            "overall_median": float(sub_all.median()),
            "hypo_onset_median": float(sub_hypo.median()),
        }

axes[1].set_xticks([0.5, 3.5, 6.5])
axes[1].set_xticklabels(["Loop\n(all vs hypo)", "Trio\n(all vs hypo)", "OpenAPS\n(all vs hypo)"])
axes[1].set_ylabel("IOB (U)")
axes[1].set_title("IOB: Overall vs at Hypo Onset")

plt.tight_layout()
plt.savefig(VIS / "fig5_iob_at_hypo.png", dpi=150)
plt.close()
print("Panel 5: IOB at hypo saved")

# ── Panel 6: DynISF Formula Effect Within Trio ──────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 6))

trio_po = po[po["controller"] == "trio"].copy()
trio_po["formula"] = trio_po["patient_id"].apply(
    lambda x: "sigmoid" if x in SIGMOID_PATIENTS else (
        "log" if x in LOG_PATIENTS else "other"))

# 6a: TIR by formula
formula_colors = {"sigmoid": "C3", "log": "C4", "other": "gray"}
for formula in ["sigmoid", "log", "other"]:
    sub = trio_po[trio_po["formula"] == formula]
    if len(sub) > 0:
        for _, row in sub.iterrows():
            axes[0].scatter(formula, row["tir"], c=formula_colors[formula],
                          s=100, alpha=0.7, edgecolors="black", linewidths=0.5)

axes[0].set_ylabel("TIR (%)")
axes[0].set_title("Trio TIR by DynISF Formula")

# 6b: Hypo by formula
for formula in ["sigmoid", "log", "other"]:
    sub = trio_po[trio_po["formula"] == formula]
    if len(sub) > 0:
        for _, row in sub.iterrows():
            axes[1].scatter(formula, row["hypo"], c=formula_colors[formula],
                          s=100, alpha=0.7, edgecolors="black", linewidths=0.5)

axes[1].set_ylabel("Time Below 70 (%)")
axes[1].set_title("Trio Hypo by DynISF Formula")

# Stats
for formula in ["sigmoid", "log"]:
    sub = trio_po[trio_po["formula"] == formula]
    if len(sub) > 0:
        results[f"trio_{formula}"] = {
            "n": len(sub),
            "median_tir": float(sub["tir"].median()),
            "median_hypo": float(sub["hypo"].median()),
        }
        print(f"  Trio {formula}: TIR={sub['tir'].median():.1f}%, hypo={sub['hypo'].median():.1f}% (n={len(sub)})")

plt.tight_layout()
plt.savefig(VIS / "fig6_dynisf_formula.png", dpi=150)
plt.close()
print("Panel 6: DynISF formula saved")

# Save
with open(EXP / "exp-2686_safety_analysis.json", "w") as f:
    json.dump(results, f, indent=2, default=str)

# Summary
print(f"\n{'='*60}")
print(f"EXP-2686: Safety Analysis — SUMMARY")
print(f"{'='*60}")
for ctrl in ["loop", "trio", "openaps"]:
    h = results.get(f"{ctrl}_hypo", {})
    t = results.get(f"{ctrl}_in_target", {})
    ic = results.get(f"{ctrl}_iob_comparison", {})
    print(f"\n  {ctrl.upper()}:")
    print(f"    Hypo events: {h.get('n_events', 0)}, severe: {h.get('n_severe', 0)}")
    print(f"    Median duration: {h.get('median_duration', 0):.0f} min")
    print(f"    Median nadir: {h.get('median_nadir', 0):.0f} mg/dL")
    print(f"    In clinical target: {t.get('n', 0)}/{t.get('total', 0)}")
    if ic:
        print(f"    IOB: overall={ic['overall_median']:.1f}U, at hypo={ic['hypo_onset_median']:.1f}U")
