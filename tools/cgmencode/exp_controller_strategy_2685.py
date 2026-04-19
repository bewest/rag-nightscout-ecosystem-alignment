#!/usr/bin/env python3
"""EXP-2685: Controller Decision-Making Strategy Comparison

Following the insulin irrelevance discovery (EXP-2680-2684), we now ask:
HOW do controllers achieve different outcomes?

Trio achieves 89.9% TIR vs Loop 73.3% vs OpenAPS 68.4%.
Settings don't predict outcomes. So what does?

This experiment characterizes the decision-making STRATEGY of each controller:
  - When does it dose? (glucose thresholds, trends)
  - How does it dose? (temp basal vs SMB vs suspend)
  - How quickly does it react? (latency from BG rise to action)
  - What fraction of time is it active vs passive?

7-panel dashboard:
  1. Dosing intensity timeline: SMBs, temp basal, suspend by controller
  2. Action threshold: at what BG level does each controller act?
  3. Reaction speed: BG rise → first controller action latency
  4. Basal modulation patterns: temp basal distributions
  5. SMB characteristics: size, frequency, timing
  6. Suspend behavior: how often and for how long?
  7. Overnight vs daytime strategy differences
"""
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from pathlib import Path
from scipy import stats

VIS = Path("visualizations/controller-strategy")
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

print(f"Grid: {len(grid):,} rows, {grid['patient_id'].nunique()} patients")

# ── Panel 1: Dosing Intensity by BG Zone ─────────────────────────────
fig, axes = plt.subplots(2, 2, figsize=(14, 10))

# Classify BG zones
grid["bg_zone"] = pd.cut(grid["glucose"], bins=[0, 54, 70, 180, 250, 500],
                         labels=["<54", "54-70", "70-180", "180-250", ">250"])

# 1a: SMB frequency by BG zone
ax = axes[0, 0]
for ctrl in ["loop", "trio", "openaps"]:
    sub = grid[grid["controller"] == ctrl]
    zone_smb = sub.groupby("bg_zone", observed=True)["bolus_smb"].apply(
        lambda x: (x > 0).mean() * 100)
    ax.plot(zone_smb.index.astype(str), zone_smb.values, "o-",
           color=colors[ctrl], label=ctrl, linewidth=2)
ax.set_xlabel("BG Zone (mg/dL)")
ax.set_ylabel("% of 5-min intervals with SMB")
ax.set_title("SMB Frequency by BG Zone")
ax.legend()

# 1b: Mean temp basal rate by BG zone
ax = axes[0, 1]
for ctrl in ["loop", "trio", "openaps"]:
    sub = grid[grid["controller"] == ctrl]
    if "actual_basal_rate" in sub.columns:
        zone_basal = sub.groupby("bg_zone", observed=True)["actual_basal_rate"].median()
        ax.plot(zone_basal.index.astype(str), zone_basal.values, "o-",
               color=colors[ctrl], label=ctrl, linewidth=2)
ax.set_xlabel("BG Zone (mg/dL)")
ax.set_ylabel("Median Actual Basal Rate (U/h)")
ax.set_title("Basal Rate by BG Zone")
ax.legend()

# 1c: Net basal (actual - scheduled) by BG zone
ax = axes[1, 0]
for ctrl in ["loop", "trio", "openaps"]:
    sub = grid[grid["controller"] == ctrl]
    sub_net = sub["actual_basal_rate"] - sub["scheduled_basal_rate"]
    zone_net = sub_net.groupby(sub["bg_zone"], observed=False).median()
    ax.plot(zone_net.index.astype(str), zone_net.values, "o-",
           color=colors[ctrl], label=ctrl, linewidth=2)
ax.set_xlabel("BG Zone (mg/dL)")
ax.set_ylabel("Net Basal (actual - scheduled, U/h)")
ax.set_title("Controller Basal Adjustment by BG Zone")
ax.axhline(0, color="gray", linestyle="--", alpha=0.3)
ax.legend()

# 1d: Total insulin delivery rate (bolus + basal) by BG zone
ax = axes[1, 1]
for ctrl in ["loop", "trio", "openaps"]:
    sub = grid[grid["controller"] == ctrl].copy()
    sub["total_rate"] = sub["actual_basal_rate"] + sub["bolus_smb"] * 12  # SMBs → U/h rate
    zone_total = sub.groupby("bg_zone", observed=True)["total_rate"].median()
    ax.plot(zone_total.index.astype(str), zone_total.values, "o-",
           color=colors[ctrl], label=ctrl, linewidth=2)
ax.set_xlabel("BG Zone (mg/dL)")
ax.set_ylabel("Total Insulin Rate (U/h equiv)")
ax.set_title("Total Insulin Delivery by BG Zone")
ax.legend()

plt.suptitle("Controller Dosing Strategy by BG Zone", fontsize=14)
plt.tight_layout()
plt.savefig(VIS / "fig1_dosing_by_zone.png", dpi=150)
plt.close()
print("Panel 1: Dosing by zone saved")

# Compute summary stats
for ctrl in ["loop", "trio", "openaps"]:
    sub = grid[grid["controller"] == ctrl]
    smb_pct = (sub["bolus_smb"] > 0).mean() * 100
    smb_mean = sub.loc[sub["bolus_smb"] > 0, "bolus_smb"].mean() if smb_pct > 0 else 0
    suspend_pct = (sub["actual_basal_rate"] < 0.01).mean() * 100
    high_basal = (sub["actual_basal_rate"] > sub["scheduled_basal_rate"] * 1.5).mean() * 100
    print(f"\n  {ctrl}:")
    print(f"    SMB: {smb_pct:.1f}% of intervals, mean size={smb_mean:.2f}U")
    print(f"    Suspend: {suspend_pct:.1f}% of intervals")
    print(f"    High basal (>1.5× scheduled): {high_basal:.1f}%")
    results[f"{ctrl}_strategy"] = {
        "smb_pct": float(smb_pct),
        "smb_mean_size": float(smb_mean),
        "suspend_pct": float(suspend_pct),
        "high_basal_pct": float(high_basal),
    }

# ── Panel 2: Action Threshold — BG at first controller action ───────
fig, axes = plt.subplots(1, 2, figsize=(14, 6))

# 2a: BG distribution when SMBs are delivered
ax = axes[0]
for ctrl in ["loop", "trio", "openaps"]:
    sub = grid[(grid["controller"] == ctrl) & (grid["bolus_smb"] > 0)]
    if len(sub) > 10:
        ax.hist(sub["glucose"].dropna(), bins=50, alpha=0.4,
               label=f"{ctrl} (n={len(sub):,}, median={sub['glucose'].median():.0f})",
               density=True, color=colors[ctrl])
ax.set_xlabel("BG at SMB delivery (mg/dL)")
ax.set_ylabel("Density")
ax.set_title("BG Level When Controller Delivers SMBs")
ax.axvline(TIR_HIGH, color="red", linestyle="--", alpha=0.5, label="180 mg/dL")
ax.axvline(TIR_LOW, color="orange", linestyle="--", alpha=0.5, label="70 mg/dL")
ax.legend(fontsize=8)

# 2b: BG distribution when basal is suspended
ax = axes[1]
for ctrl in ["loop", "trio", "openaps"]:
    sub = grid[(grid["controller"] == ctrl) & (grid["actual_basal_rate"] < 0.01)]
    if len(sub) > 10:
        ax.hist(sub["glucose"].dropna(), bins=50, alpha=0.4,
               label=f"{ctrl} (n={len(sub):,}, median={sub['glucose'].median():.0f})",
               density=True, color=colors[ctrl])
ax.set_xlabel("BG at basal suspend (mg/dL)")
ax.set_ylabel("Density")
ax.set_title("BG Level When Controller Suspends Basal")
ax.axvline(TIR_HIGH, color="red", linestyle="--", alpha=0.5)
ax.axvline(TIR_LOW, color="orange", linestyle="--", alpha=0.5)
ax.legend(fontsize=8)

plt.tight_layout()
plt.savefig(VIS / "fig2_action_thresholds.png", dpi=150)
plt.close()
print("Panel 2: Action thresholds saved")

# ── Panel 3: Reaction Speed — excursion onset to first SMB ──────────
fig, axes = plt.subplots(1, 2, figsize=(14, 6))

# Find excursion events: BG crosses 150 going up
reaction_times = []
for pid in grid["patient_id"].unique():
    pdf = grid[grid["patient_id"] == pid].sort_values("time").reset_index(drop=True)
    ctrl = ctrl_map.get(pid, "unknown")
    bg = pdf["glucose"].values
    smb = pdf["bolus_smb"].values if "bolus_smb" in pdf.columns else np.zeros(len(pdf))

    # Find upward crossings of 150 mg/dL
    for i in range(1, len(bg) - 24):  # need 2h lookahead
        if pd.isna(bg[i]) or pd.isna(bg[i-1]):
            continue
        if bg[i-1] < 150 and bg[i] >= 150:
            # Find first SMB after crossing
            for j in range(i, min(i + 24, len(smb))):
                if smb[j] > 0:
                    latency_min = (j - i) * 5
                    reaction_times.append({
                        "patient_id": pid,
                        "controller": ctrl,
                        "latency_min": latency_min,
                        "bg_at_cross": bg[i],
                        "smb_size": smb[j],
                    })
                    break

rt = pd.DataFrame(reaction_times)
if len(rt) > 10:
    for ctrl in ["loop", "trio", "openaps"]:
        sub = rt[rt["controller"] == ctrl]
        if len(sub) > 5:
            axes[0].hist(sub["latency_min"], bins=range(0, 125, 5), alpha=0.5,
                        label=f"{ctrl} (median={sub['latency_min'].median():.0f}min, n={len(sub)})",
                        density=True, color=colors[ctrl])
    axes[0].set_xlabel("Minutes from BG≥150 to first SMB")
    axes[0].set_ylabel("Density")
    axes[0].set_title("Reaction Speed: BG≥150 → First SMB")
    axes[0].legend(fontsize=8)

    # By controller
    for ctrl in ["loop", "trio", "openaps"]:
        sub = rt[rt["controller"] == ctrl]
        if len(sub) > 0:
            results[f"{ctrl}_reaction"] = {
                "median_latency_min": float(sub["latency_min"].median()),
                "n_excursions": len(sub),
            }
            print(f"  {ctrl} reaction time: {sub['latency_min'].median():.0f} min (n={len(sub)})")

# 3b: Excursion peak BG by controller
ax = axes[1]
# Track peak BG after 150 crossing
peaks = []
for pid in grid["patient_id"].unique():
    pdf = grid[grid["patient_id"] == pid].sort_values("time").reset_index(drop=True)
    ctrl = ctrl_map.get(pid, "unknown")
    bg = pdf["glucose"].values

    for i in range(1, len(bg) - 24):
        if pd.isna(bg[i]) or pd.isna(bg[i-1]):
            continue
        if bg[i-1] < 150 and bg[i] >= 150:
            peak = np.nanmax(bg[i:min(i+24, len(bg))])
            peaks.append({"controller": ctrl, "peak_bg": peak})

pk = pd.DataFrame(peaks)
if len(pk) > 10:
    for ctrl in ["loop", "trio", "openaps"]:
        sub = pk[pk["controller"] == ctrl]
        if len(sub) > 5:
            ax.hist(sub["peak_bg"], bins=50, alpha=0.5,
                   label=f"{ctrl} (median={sub['peak_bg'].median():.0f}, n={len(sub)})",
                   density=True, color=colors[ctrl])
    ax.set_xlabel("Peak BG after excursion (mg/dL)")
    ax.set_ylabel("Density")
    ax.set_title("Excursion Peak BG (crossing 150)")
    ax.legend(fontsize=8)

plt.tight_layout()
plt.savefig(VIS / "fig3_reaction_speed.png", dpi=150)
plt.close()
print("Panel 3: Reaction speed saved")

# ── Panel 4: Basal Modulation Distribution ───────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 6))

# 4a: Ratio of actual/scheduled basal
for ctrl in ["loop", "trio", "openaps"]:
    sub = grid[grid["controller"] == ctrl].copy()
    sub["basal_ratio"] = sub["actual_basal_rate"] / sub["scheduled_basal_rate"].replace(0, np.nan)
    valid = sub["basal_ratio"].dropna()
    valid = valid[(valid >= 0) & (valid <= 5)]
    if len(valid) > 100:
        axes[0].hist(valid, bins=50, alpha=0.4, label=ctrl, density=True, color=colors[ctrl])

axes[0].axvline(1.0, color="red", linestyle="--", alpha=0.5, label="1.0 = scheduled")
axes[0].set_xlabel("Actual / Scheduled Basal Ratio")
axes[0].set_ylabel("Density")
axes[0].set_title("Basal Modulation Distribution")
axes[0].legend()
axes[0].set_xlim(0, 4)

# 4b: % time in each basal mode
basal_modes = []
for ctrl in ["loop", "trio", "openaps"]:
    sub = grid[grid["controller"] == ctrl]
    ratio = sub["actual_basal_rate"] / sub["scheduled_basal_rate"].replace(0, np.nan)
    suspend = (ratio < 0.05).mean() * 100
    reduced = ((ratio >= 0.05) & (ratio < 0.8)).mean() * 100
    normal = ((ratio >= 0.8) & (ratio <= 1.2)).mean() * 100
    elevated = ((ratio > 1.2) & (ratio <= 3)).mean() * 100
    max_basal = (ratio > 3).mean() * 100
    basal_modes.append({
        "controller": ctrl,
        "Suspend": suspend,
        "Reduced": reduced,
        "Normal": normal,
        "Elevated": elevated,
        "Max": max_basal,
    })
    results[f"{ctrl}_basal_modes"] = {
        "suspend": float(suspend), "reduced": float(reduced),
        "normal": float(normal), "elevated": float(elevated),
        "max": float(max_basal),
    }

bm = pd.DataFrame(basal_modes).set_index("controller")
bm.plot(kind="barh", stacked=True, ax=axes[1], alpha=0.7,
        color=["red", "orange", "green", "steelblue", "purple"])
axes[1].set_xlabel("% of Time")
axes[1].set_title("Time in Each Basal Mode")
axes[1].legend(fontsize=8, loc="lower right")

plt.tight_layout()
plt.savefig(VIS / "fig4_basal_modulation.png", dpi=150)
plt.close()
print("Panel 4: Basal modulation saved")

# ── Panel 5: SMB Characteristics ─────────────────────────────────────
fig, axes = plt.subplots(1, 3, figsize=(16, 5))

# 5a: SMB size distribution
for ctrl in ["loop", "trio", "openaps"]:
    sub = grid[(grid["controller"] == ctrl) & (grid["bolus_smb"] > 0)]
    if len(sub) > 10:
        axes[0].hist(sub["bolus_smb"].clip(0, 3), bins=30, alpha=0.5,
                    label=f"{ctrl} (median={sub['bolus_smb'].median():.2f}U)",
                    density=True, color=colors[ctrl])
axes[0].set_xlabel("SMB Size (U)")
axes[0].set_ylabel("Density")
axes[0].set_title("SMB Size Distribution")
axes[0].legend(fontsize=8)

# 5b: SMBs per hour by controller
for ctrl in ["loop", "trio", "openaps"]:
    sub = grid[grid["controller"] == ctrl]
    hourly_smb = sub.groupby("time")["bolus_smb"].apply(lambda x: (x > 0).sum())
    # Group by hour of day
    sub_smb = sub[sub["bolus_smb"] > 0].copy()
    if len(sub_smb) > 10:
        sub_smb["hour"] = pd.to_datetime(sub_smb["time"]).dt.hour
        hourly = sub_smb.groupby("hour").size() / sub["patient_id"].nunique()
        # Normalize by days
        days = (sub["time"].max() - sub["time"].min()).total_seconds() / 86400
        hourly = hourly / max(days / sub["patient_id"].nunique(), 1)
        axes[1].plot(hourly.index, hourly.values, "o-", color=colors[ctrl],
                    label=ctrl, linewidth=2)
axes[1].set_xlabel("Hour of Day (UTC)")
axes[1].set_ylabel("SMBs per hour (normalized)")
axes[1].set_title("SMB Delivery Pattern by Hour")
axes[1].legend()

# 5c: Cumulative insulin by type
for ctrl in ["loop", "trio", "openaps"]:
    sub = grid[grid["controller"] == ctrl]
    days = (sub["time"].max() - sub["time"].min()).total_seconds() / 86400 / sub["patient_id"].nunique()
    smb_daily = sub["bolus_smb"].sum() / max(days, 1) / sub["patient_id"].nunique()
    manual_daily = (sub["bolus"].sum() - sub["bolus_smb"].sum()) / max(days, 1) / sub["patient_id"].nunique()
    basal_daily = sub["actual_basal_rate"].mean() * 24 if "actual_basal_rate" in sub.columns else 0

    results[f"{ctrl}_insulin_breakdown"] = {
        "smb_daily": float(smb_daily),
        "manual_daily": float(manual_daily),
        "basal_daily": float(basal_daily),
    }

breakdown = pd.DataFrame([
    {"controller": "loop", "SMBs": results.get("loop_insulin_breakdown", {}).get("smb_daily", 0),
     "Manual bolus": results.get("loop_insulin_breakdown", {}).get("manual_daily", 0),
     "Basal": results.get("loop_insulin_breakdown", {}).get("basal_daily", 0)},
    {"controller": "trio", "SMBs": results.get("trio_insulin_breakdown", {}).get("smb_daily", 0),
     "Manual bolus": results.get("trio_insulin_breakdown", {}).get("manual_daily", 0),
     "Basal": results.get("trio_insulin_breakdown", {}).get("basal_daily", 0)},
    {"controller": "openaps", "SMBs": results.get("openaps_insulin_breakdown", {}).get("smb_daily", 0),
     "Manual bolus": results.get("openaps_insulin_breakdown", {}).get("manual_daily", 0),
     "Basal": results.get("openaps_insulin_breakdown", {}).get("basal_daily", 0)},
]).set_index("controller")
breakdown.plot(kind="bar", stacked=True, ax=axes[2], alpha=0.7)
axes[2].set_ylabel("Daily Insulin (U/day per patient)")
axes[2].set_title("Insulin Delivery Breakdown")
axes[2].legend(fontsize=8)

plt.tight_layout()
plt.savefig(VIS / "fig5_smb_characteristics.png", dpi=150)
plt.close()
print("Panel 5: SMB characteristics saved")

# ── Panel 6: Suspend Behavior ────────────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 6))

# 6a: Suspend duration distribution (consecutive zero-basal intervals)
for ctrl in ["loop", "trio", "openaps"]:
    sub = grid[grid["controller"] == ctrl].sort_values(["patient_id", "time"])
    suspended = (sub["actual_basal_rate"] < 0.01).astype(int)
    # Count consecutive suspend runs
    runs = []
    current_run = 0
    for val in suspended.values:
        if val:
            current_run += 1
        else:
            if current_run > 0:
                runs.append(current_run * 5)  # minutes
            current_run = 0
    if runs:
        axes[0].hist(runs, bins=range(0, 125, 5), alpha=0.5,
                    label=f"{ctrl} (median={np.median(runs):.0f}min, n={len(runs)})",
                    density=True, color=colors[ctrl])
        results[f"{ctrl}_suspend"] = {
            "median_duration_min": float(np.median(runs)),
            "mean_duration_min": float(np.mean(runs)),
            "n_events": len(runs),
        }

axes[0].set_xlabel("Suspend Duration (minutes)")
axes[0].set_ylabel("Density")
axes[0].set_title("Basal Suspend Duration")
axes[0].legend(fontsize=8)

# 6b: BG at end of suspend
for ctrl in ["loop", "trio", "openaps"]:
    sub = grid[grid["controller"] == ctrl].sort_values(["patient_id", "time"])
    suspended = sub["actual_basal_rate"] < 0.01
    # Find transitions from suspended to active
    transitions = suspended.astype(int).diff()
    end_suspend = sub[transitions == -1]
    if len(end_suspend) > 10:
        axes[1].hist(end_suspend["glucose"].dropna(), bins=40, alpha=0.5,
                    label=f"{ctrl} (median={end_suspend['glucose'].median():.0f}, n={len(end_suspend)})",
                    density=True, color=colors[ctrl])

axes[1].axvline(TIR_LOW, color="orange", linestyle="--", alpha=0.5, label="70 mg/dL")
axes[1].set_xlabel("BG at End of Suspend (mg/dL)")
axes[1].set_ylabel("Density")
axes[1].set_title("BG When Basal Resumes")
axes[1].legend(fontsize=8)

plt.tight_layout()
plt.savefig(VIS / "fig6_suspend_behavior.png", dpi=150)
plt.close()
print("Panel 6: Suspend behavior saved")

# ── Panel 7: Overnight vs Daytime Strategy ───────────────────────────
fig, axes = plt.subplots(2, 2, figsize=(14, 10))

grid["period"] = pd.to_datetime(grid["time"]).dt.hour.apply(
    lambda h: "Overnight\n(0-6 UTC)" if h < 6 else (
        "Morning\n(6-12)" if h < 12 else (
            "Afternoon\n(12-18)" if h < 18 else "Evening\n(18-24)")))

periods = ["Overnight\n(0-6 UTC)", "Morning\n(6-12)", "Afternoon\n(12-18)", "Evening\n(18-24)"]

# 7a: TIR by period
ax = axes[0, 0]
for ctrl in ["loop", "trio", "openaps"]:
    sub = grid[grid["controller"] == ctrl]
    period_tir = sub.groupby("period")["glucose"].apply(
        lambda x: ((x >= TIR_LOW) & (x <= TIR_HIGH)).mean() * 100)
    period_tir = period_tir.reindex(periods)
    ax.plot(range(len(periods)), period_tir.values, "o-", color=colors[ctrl],
           label=ctrl, linewidth=2)
ax.set_xticks(range(len(periods)))
ax.set_xticklabels(periods, fontsize=8)
ax.set_ylabel("TIR (%)")
ax.set_title("TIR by Time of Day")
ax.legend()

# 7b: Hypo by period
ax = axes[0, 1]
for ctrl in ["loop", "trio", "openaps"]:
    sub = grid[grid["controller"] == ctrl]
    period_hypo = sub.groupby("period")["glucose"].apply(
        lambda x: (x < TIR_LOW).mean() * 100)
    period_hypo = period_hypo.reindex(periods)
    ax.plot(range(len(periods)), period_hypo.values, "o-", color=colors[ctrl],
           label=ctrl, linewidth=2)
ax.set_xticks(range(len(periods)))
ax.set_xticklabels(periods, fontsize=8)
ax.set_ylabel("Hypo (%)")
ax.set_title("Hypoglycemia by Time of Day")
ax.legend()

# 7c: SMB rate by period
ax = axes[1, 0]
for ctrl in ["loop", "trio", "openaps"]:
    sub = grid[grid["controller"] == ctrl]
    period_smb = sub.groupby("period")["bolus_smb"].apply(
        lambda x: (x > 0).mean() * 100)
    period_smb = period_smb.reindex(periods)
    ax.plot(range(len(periods)), period_smb.values, "o-", color=colors[ctrl],
           label=ctrl, linewidth=2)
ax.set_xticks(range(len(periods)))
ax.set_xticklabels(periods, fontsize=8)
ax.set_ylabel("% intervals with SMB")
ax.set_title("SMB Rate by Time of Day")
ax.legend()

# 7d: Mean BG by period
ax = axes[1, 1]
for ctrl in ["loop", "trio", "openaps"]:
    sub = grid[grid["controller"] == ctrl]
    period_bg = sub.groupby("period")["glucose"].mean()
    period_bg = period_bg.reindex(periods)
    ax.plot(range(len(periods)), period_bg.values, "o-", color=colors[ctrl],
           label=ctrl, linewidth=2)
ax.set_xticks(range(len(periods)))
ax.set_xticklabels(periods, fontsize=8)
ax.set_ylabel("Mean BG (mg/dL)")
ax.set_title("Mean BG by Time of Day")
ax.axhline(TIR_HIGH, color="red", linestyle="--", alpha=0.3)
ax.legend()

plt.suptitle("Overnight vs Daytime Controller Strategy", fontsize=14)
plt.tight_layout()
plt.savefig(VIS / "fig7_time_of_day.png", dpi=150)
plt.close()
print("Panel 7: Time of day saved")

# Save results
with open(EXP / "exp-2685_controller_strategy.json", "w") as f:
    json.dump(results, f, indent=2, default=str)

print(f"\n{'='*60}")
print(f"EXP-2685: Controller Strategy Comparison — SUMMARY")
print(f"{'='*60}")
for ctrl in ["loop", "trio", "openaps"]:
    s = results.get(f"{ctrl}_strategy", {})
    bm = results.get(f"{ctrl}_basal_modes", {})
    r = results.get(f"{ctrl}_reaction", {})
    ins = results.get(f"{ctrl}_insulin_breakdown", {})
    print(f"\n  {ctrl.upper()}:")
    print(f"    SMB rate: {s.get('smb_pct', 0):.1f}%, mean size: {s.get('smb_mean_size', 0):.2f}U")
    print(f"    Suspend: {s.get('suspend_pct', 0):.1f}%")
    print(f"    Basal modes: suspend={bm.get('suspend', 0):.0f}%, "
          f"normal={bm.get('normal', 0):.0f}%, elevated={bm.get('elevated', 0):.0f}%")
    print(f"    Reaction time: {r.get('median_latency_min', '?')} min")
    print(f"    Insulin: SMB={ins.get('smb_daily', 0):.1f}, "
          f"manual={ins.get('manual_daily', 0):.1f}, basal={ins.get('basal_daily', 0):.1f} U/day")
