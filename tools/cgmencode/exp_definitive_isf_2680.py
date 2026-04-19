#!/usr/bin/env python3
"""EXP-2680: Definitive Cross-Controller Demand ISF Characterization

Incorporates ALL methodology learnings from EXP-2671-2679:
  - BG ≥ 180 mg/dL floor (EXP-2677/2678: excludes misclassified meals)
  - 2h prior-bolus isolation (EXP-2666: validated equivalence to 6h)
  - Demand-phase ISF (0-2h drop/dose) which is dose-independent (EXP-2663)
  - 22 qualified patients from autoprepare manifest (EXP-2672)
  - Controller-aware analysis (Loop, Trio, OpenAPS)

7-panel dashboard:
  1. ISF distribution by controller (BG≥180 vs all BG)
  2. Per-patient ISF profiles (ordered by median ISF)
  3. Variance decomposition (patient vs controller vs residual)
  4. ISF vs profile settings (scheduled_isf)
  5. ISF vs DynISF formula (sigmoid vs log) for Trio patients
  6. ISF stability over time (monthly trend)
  7. Summary statistics table
"""
import json
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from pathlib import Path
from scipy import stats

VIS = Path("visualizations/definitive-isf")
VIS.mkdir(parents=True, exist_ok=True)
EXP = Path("externals/experiments")

# Load manifest
manifest = json.load(open(EXP / "autoprepare-qualified.json"))
qualified = manifest["qualified_patients"]
print(f"Qualified patients: {len(qualified)}")

# Load data
grid = pd.read_parquet("externals/ns-parquet/training/grid.parquet")
ds = pd.read_parquet("externals/ns-parquet/training/devicestatus.parquet")
ctrl_map = ds.groupby("patient_id")["controller"].first().to_dict()

# Filter to qualified
grid = grid[grid["patient_id"].isin(qualified)].copy()
grid["controller"] = grid["patient_id"].map(ctrl_map)
print(f"Grid rows: {len(grid):,}")

# DynISF formula annotations (from EXP-2674)
SIGMOID_PATIENTS = {"ns-9b9a6a874e51", "ns-adde5f4af7ca", "ns-dde9e7c2e752",
                     "ns-554b16de7133", "ns-6bef17b4c1ec", "ns-c422538aa12a"}
LOG_PATIENTS = {"ns-d444c120c23a", "ns-8b3c1b50793c", "ns-a9ce2317bead",
                "ns-8ffa739b986b", "ns-1ccae8a375b9"}
AUTOISF_PATIENTS = {"ns-8f3527d1ee40"}


def extract_demand_isf(df, bg_floor=0, isolation_hours=2, min_dose=0.1):
    """Extract demand-phase ISF events from grid data.
    
    Demand ISF = (BG at bolus - BG at 2h) / dose
    Requires:
      - BG at bolus >= bg_floor
      - No other bolus within isolation_hours before
      - dose >= min_dose
    """
    events = []
    for pid in df["patient_id"].unique():
        pdf = df[df["patient_id"] == pid].sort_values("time").reset_index(drop=True)
        bolus_mask = pdf["bolus"] > min_dose
        bolus_idx = pdf.index[bolus_mask].tolist()
        
        for idx in bolus_idx:
            row = pdf.loc[idx]
            bg0 = row["glucose"]
            dose = row["bolus"]
            t0 = row["time"]
            
            if pd.isna(bg0) or bg0 < bg_floor:
                continue
            
            # Isolation: no bolus in prior isolation_hours
            t_iso = pd.Timestamp(t0) - pd.Timedelta(hours=isolation_hours)
            if hasattr(t_iso, 'tz') and t_iso.tz is None:
                try:
                    t_iso = t_iso.tz_localize("UTC")
                except Exception:
                    pass
            
            prior_mask = (pdf["time"] >= t_iso) & (pdf["time"] < t0) & (pdf["bolus"] > min_dose)
            if prior_mask.sum() > 0:
                continue
            
            # Get BG at t+2h
            t2h = pd.Timestamp(t0) + pd.Timedelta(hours=2)
            if hasattr(t2h, 'tz') and t2h.tz is None:
                try:
                    t2h = t2h.tz_localize("UTC")
                except Exception:
                    pass
            
            window = pdf[(pdf["time"] >= t2h - pd.Timedelta(minutes=10)) & 
                        (pdf["time"] <= t2h + pd.Timedelta(minutes=10))]
            if len(window) == 0:
                continue
            
            closest = window.iloc[(window["time"] - t2h).abs().argsort().iloc[0]]
            bg2h = closest["glucose"]
            if pd.isna(bg2h):
                continue
            
            isf = (bg0 - bg2h) / dose
            events.append({
                "patient_id": pid,
                "controller": ctrl_map.get(pid, "unknown"),
                "time": t0,
                "bg0": bg0,
                "bg2h": bg2h,
                "dose": dose,
                "demand_isf": isf,
                "hour": pd.Timestamp(t0).hour,
                "scheduled_isf": row.get("scheduled_isf", np.nan),
                "iob": row.get("iob", np.nan),
            })
    
    return pd.DataFrame(events)


# Extract events at two thresholds
print("\nExtracting demand ISF events...")
events_all = extract_demand_isf(grid, bg_floor=0, min_dose=0.1)
events_180 = extract_demand_isf(grid, bg_floor=180, min_dose=0.1)
print(f"  All BG: {len(events_all)} events")
print(f"  BG≥180: {len(events_180)} events")

results = {
    "n_events_all": len(events_all),
    "n_events_180": len(events_180),
    "by_controller": {},
    "by_patient": {},
}

# ── Panel 1: ISF Distribution by Controller ──────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 6))
for ax, (label, evts) in zip(axes, [("All BG", events_all), ("BG ≥ 180", events_180)]):
    for ctrl in ["loop", "trio", "openaps"]:
        sub = evts[evts["controller"] == ctrl]
        if len(sub) > 5:
            vals = sub["demand_isf"].clip(-100, 200)
            ax.hist(vals, bins=50, alpha=0.5, label=f"{ctrl} (n={len(sub)})", density=True)
    ax.set_xlabel("Demand ISF (mg/dL per U)")
    ax.set_ylabel("Density")
    ax.set_title(f"ISF Distribution — {label}")
    ax.axvline(0, color="red", linestyle="--", alpha=0.5, label="ISF=0")
    ax.legend()
    ax.set_xlim(-100, 200)

plt.tight_layout()
plt.savefig(VIS / "fig1_isf_distribution.png", dpi=150)
plt.close()
print("Panel 1: ISF distribution saved")

# Compute per-controller stats
for ctrl in ["loop", "trio", "openaps"]:
    for label, evts in [("all", events_all), ("bg180", events_180)]:
        sub = evts[evts["controller"] == ctrl]
        if len(sub) > 0:
            key = f"{ctrl}_{label}"
            results["by_controller"][key] = {
                "n": len(sub),
                "median_isf": float(sub["demand_isf"].median()),
                "mean_isf": float(sub["demand_isf"].mean()),
                "std_isf": float(sub["demand_isf"].std()),
                "pct_positive": float((sub["demand_isf"] > 0).mean() * 100),
                "iqr": float(sub["demand_isf"].quantile(0.75) - sub["demand_isf"].quantile(0.25)),
            }
            print(f"  {key}: n={len(sub)}, median={sub['demand_isf'].median():.1f}, "
                  f"pos={100*(sub['demand_isf']>0).mean():.0f}%")

# ── Panel 2: Per-Patient ISF Profile ─────────────────────────────────
fig, ax = plt.subplots(figsize=(16, 8))
ev = events_180.copy()
if len(ev) > 0:
    patient_medians = ev.groupby("patient_id")["demand_isf"].median().sort_values()
    order = patient_medians.index.tolist()
    
    colors = {"loop": "C0", "trio": "C1", "openaps": "C2"}
    positions = []
    labels = []
    data_for_box = []
    color_list = []
    
    for i, pid in enumerate(order):
        sub = ev[ev["patient_id"] == pid]
        ctrl = ctrl_map.get(pid, "unknown")
        data_for_box.append(sub["demand_isf"].values)
        positions.append(i)
        short = pid[:8] if len(pid) > 8 else pid
        labels.append(f"{short}\n({ctrl[0].upper()})")
        color_list.append(colors.get(ctrl, "gray"))
        
        results["by_patient"][pid] = {
            "controller": ctrl,
            "n_events": len(sub),
            "median_isf": float(sub["demand_isf"].median()),
            "iqr": float(sub["demand_isf"].quantile(0.75) - sub["demand_isf"].quantile(0.25)),
            "pct_positive": float((sub["demand_isf"] > 0).mean() * 100),
        }
    
    bp = ax.boxplot(data_for_box, positions=positions, patch_artist=True,
                    showfliers=False, widths=0.6)
    for patch, c in zip(bp["boxes"], color_list):
        patch.set_facecolor(c)
        patch.set_alpha(0.6)
    
    ax.set_xticks(positions)
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=7)
    ax.axhline(0, color="red", linestyle="--", alpha=0.5)
    ax.set_ylabel("Demand ISF (mg/dL per U)")
    ax.set_title("Per-Patient Demand ISF (BG≥180, sorted by median)")
    
    from matplotlib.patches import Patch
    legend_elements = [Patch(facecolor="C0", alpha=0.6, label="Loop"),
                       Patch(facecolor="C1", alpha=0.6, label="Trio"),
                       Patch(facecolor="C2", alpha=0.6, label="OpenAPS")]
    ax.legend(handles=legend_elements, loc="upper left")

plt.tight_layout()
plt.savefig(VIS / "fig2_per_patient.png", dpi=150)
plt.close()
print("Panel 2: Per-patient profile saved")

# ── Panel 3: Variance Decomposition ─────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(12, 5))
for ax, (label, evts) in zip(axes, [("All BG", events_all), ("BG ≥ 180", events_180)]):
    if len(evts) < 50:
        continue
    
    # ANOVA-style decomposition
    grand_mean = evts["demand_isf"].mean()
    ss_total = ((evts["demand_isf"] - grand_mean) ** 2).sum()
    
    # Patient effect
    patient_means = evts.groupby("patient_id")["demand_isf"].transform("mean")
    ss_patient = ((patient_means - grand_mean) ** 2).sum()
    
    # Controller effect
    ctrl_means = evts.groupby("controller")["demand_isf"].transform("mean")
    ss_controller = ((ctrl_means - grand_mean) ** 2).sum()
    
    # Residual
    ss_residual = ss_total - ss_patient
    
    eta2_patient = ss_patient / ss_total if ss_total > 0 else 0
    eta2_controller = ss_controller / ss_total if ss_total > 0 else 0
    eta2_residual = 1 - eta2_patient
    
    sizes = [eta2_patient, eta2_controller, max(0, eta2_residual - eta2_controller)]
    labels_pie = [f"Patient\n{eta2_patient:.1%}", 
                  f"Controller\n{eta2_controller:.1%}",
                  f"Residual\n{max(0, eta2_residual - eta2_controller):.1%}"]
    ax.pie(sizes, labels=labels_pie, colors=["steelblue", "coral", "lightgray"],
           autopct=None, startangle=90)
    ax.set_title(f"Variance Decomposition — {label}")
    
    results[f"variance_{label.lower().replace(' ', '_').replace('≥', 'ge')}"] = {
        "eta2_patient": float(eta2_patient),
        "eta2_controller": float(eta2_controller),
        "ss_total": float(ss_total),
        "n": len(evts),
    }

plt.tight_layout()
plt.savefig(VIS / "fig3_variance_decomposition.png", dpi=150)
plt.close()
print("Panel 3: Variance decomposition saved")

# ── Panel 4: ISF vs Profile Settings ────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 6))

# 4a: Demand ISF vs scheduled ISF
ev = events_180.copy()
ev_with_sched = ev.dropna(subset=["scheduled_isf"])
if len(ev_with_sched) > 10:
    patient_stats = ev_with_sched.groupby("patient_id").agg(
        median_demand=("demand_isf", "median"),
        median_sched=("scheduled_isf", "median"),
        controller=("controller", "first"),
    )
    
    colors = {"loop": "C0", "trio": "C1", "openaps": "C2"}
    for ctrl in ["loop", "trio", "openaps"]:
        sub = patient_stats[patient_stats["controller"] == ctrl]
        if len(sub) > 0:
            axes[0].scatter(sub["median_sched"], sub["median_demand"],
                          c=colors.get(ctrl, "gray"), label=ctrl, s=80, alpha=0.7)
    
    # Correlation
    r, p = stats.spearmanr(patient_stats["median_sched"], patient_stats["median_demand"])
    axes[0].set_xlabel("Scheduled ISF (mg/dL per U)")
    axes[0].set_ylabel("Observed Demand ISF (mg/dL per U)")
    axes[0].set_title(f"Profile vs Observed ISF (r={r:.3f}, p={p:.4f})")
    
    # 1:1 line
    lim = max(patient_stats["median_sched"].max(), patient_stats["median_demand"].max()) * 1.1
    axes[0].plot([0, lim], [0, lim], "k--", alpha=0.3, label="1:1 line")
    axes[0].legend()
    
    results["profile_vs_demand"] = {
        "spearman_r": float(r),
        "spearman_p": float(p),
        "n_patients": len(patient_stats),
    }

# 4b: Ratio of scheduled/demand ISF
if len(ev_with_sched) > 10:
    patient_stats["ratio"] = patient_stats["median_sched"] / patient_stats["median_demand"].replace(0, np.nan)
    valid = patient_stats.dropna(subset=["ratio"])
    valid = valid[valid["ratio"] > 0]  # only positive demand ISF
    if len(valid) > 0:
        for ctrl in ["loop", "trio", "openaps"]:
            sub = valid[valid["controller"] == ctrl]
            if len(sub) > 0:
                axes[1].barh([f"{pid[:8]}" for pid in sub.index],
                           sub["ratio"], alpha=0.7, color=colors.get(ctrl, "gray"),
                           label=ctrl)
        axes[1].axvline(1, color="red", linestyle="--", alpha=0.5, label="1:1")
        axes[1].set_xlabel("Scheduled ISF / Demand ISF")
        axes[1].set_title("ISF Inflation Ratio by Patient")
        axes[1].legend()
        
        results["isf_inflation"] = {
            "median_ratio": float(valid["ratio"].median()),
            "mean_ratio": float(valid["ratio"].mean()),
            "n_patients": len(valid),
        }

plt.tight_layout()
plt.savefig(VIS / "fig4_profile_vs_observed.png", dpi=150)
plt.close()
print("Panel 4: Profile vs observed saved")

# ── Panel 5: DynISF Formula Comparison (Trio only, BG≥180) ──────────
fig, axes = plt.subplots(1, 2, figsize=(14, 6))

trio_ev = events_180[events_180["controller"] == "trio"].copy()
trio_ev["formula"] = trio_ev["patient_id"].apply(
    lambda x: "sigmoid" if x in SIGMOID_PATIENTS else (
        "log" if x in LOG_PATIENTS else (
            "autoisf" if x in AUTOISF_PATIENTS else "unknown")))

# 5a: ISF by formula
for formula in ["sigmoid", "log", "autoisf"]:
    sub = trio_ev[trio_ev["formula"] == formula]
    if len(sub) > 5:
        axes[0].hist(sub["demand_isf"].clip(-50, 150), bins=30, alpha=0.5,
                    label=f"{formula} (n={len(sub)})", density=True)

axes[0].axvline(0, color="red", linestyle="--", alpha=0.5)
axes[0].set_xlabel("Demand ISF (mg/dL per U)")
axes[0].set_ylabel("Density")
axes[0].set_title("ISF by DynISF Formula (Trio, BG≥180)")
axes[0].legend()

# 5b: Per-patient median by formula
formula_stats = trio_ev.groupby(["patient_id", "formula"]).agg(
    median_isf=("demand_isf", "median"),
    n=("demand_isf", "count"),
).reset_index()

formula_colors = {"sigmoid": "C3", "log": "C4", "autoisf": "C5"}
for formula in ["sigmoid", "log", "autoisf"]:
    sub = formula_stats[formula_stats["formula"] == formula]
    if len(sub) > 0:
        axes[1].scatter(sub.index, sub["median_isf"],
                       c=formula_colors.get(formula, "gray"),
                       label=formula, s=80, alpha=0.7)

axes[1].axhline(0, color="red", linestyle="--", alpha=0.5)
axes[1].set_ylabel("Median Demand ISF (mg/dL per U)")
axes[1].set_title("Per-Patient Median ISF by DynISF Formula")
axes[1].legend()

# Stats
for formula in ["sigmoid", "log", "autoisf"]:
    sub = trio_ev[trio_ev["formula"] == formula]
    if len(sub) > 0:
        results[f"dynisf_{formula}"] = {
            "n_events": len(sub),
            "n_patients": sub["patient_id"].nunique(),
            "median_isf": float(sub["demand_isf"].median()),
            "pct_positive": float((sub["demand_isf"] > 0).mean() * 100),
        }

plt.tight_layout()
plt.savefig(VIS / "fig5_dynisf_formula.png", dpi=150)
plt.close()
print("Panel 5: DynISF formula saved")

# ── Panel 6: ISF Stability Over Time ────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 6))

ev = events_180.copy()
ev["month"] = pd.to_datetime(ev["time"]).dt.to_period("M")

# 6a: Monthly median ISF by controller
for ctrl in ["loop", "trio", "openaps"]:
    sub = ev[ev["controller"] == ctrl]
    if len(sub) > 20:
        monthly = sub.groupby("month")["demand_isf"].agg(["median", "count"])
        monthly = monthly[monthly["count"] >= 5]
        if len(monthly) > 1:
            x = range(len(monthly))
            axes[0].plot(x, monthly["median"], "o-", label=ctrl, alpha=0.7)
            axes[0].fill_between(x, 
                                monthly["median"] - monthly["median"].std(),
                                monthly["median"] + monthly["median"].std(),
                                alpha=0.1)

axes[0].set_xlabel("Month")
axes[0].set_ylabel("Median Demand ISF (mg/dL per U)")
axes[0].set_title("Monthly ISF Trend (BG≥180)")
axes[0].legend()

# 6b: Rolling median per patient (top 5 by event count)
top_patients = ev.groupby("patient_id").size().nlargest(5).index
for pid in top_patients:
    sub = ev[ev["patient_id"] == pid].sort_values("time")
    if len(sub) >= 10:
        rolling = sub["demand_isf"].rolling(window=10, min_periods=5).median()
        axes[1].plot(range(len(rolling)), rolling, alpha=0.7,
                    label=f"{pid[:8]} ({ctrl_map.get(pid, '?')[0].upper()})")

axes[1].set_xlabel("Event index")
axes[1].set_ylabel("Rolling Median ISF (window=10)")
axes[1].set_title("ISF Stability (Top 5 Patients)")
axes[1].axhline(0, color="red", linestyle="--", alpha=0.3)
axes[1].legend(fontsize=7)

plt.tight_layout()
plt.savefig(VIS / "fig6_stability.png", dpi=150)
plt.close()
print("Panel 6: Stability saved")

# ── Panel 7: Summary Table ──────────────────────────────────────────
fig, ax = plt.subplots(figsize=(14, 10))
ax.axis("off")

# Build summary table
rows = []
for pid in sorted(results.get("by_patient", {}).keys()):
    d = results["by_patient"][pid]
    rows.append([
        pid[:12],
        d["controller"],
        d["n_events"],
        f"{d['median_isf']:.1f}",
        f"{d['iqr']:.1f}",
        f"{d['pct_positive']:.0f}%",
    ])

if rows:
    table = ax.table(
        cellText=rows,
        colLabels=["Patient", "Controller", "N Events", "Median ISF", "IQR", "% Positive"],
        loc="center",
        cellLoc="center",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(8)
    table.scale(1, 1.3)
    
    # Color by controller
    ctrl_colors = {"loop": "#cce5ff", "trio": "#ffe5cc", "openaps": "#ccffcc"}
    for i, row in enumerate(rows):
        color = ctrl_colors.get(row[1], "white")
        for j in range(len(row)):
            table[i + 1, j].set_facecolor(color)

ax.set_title("EXP-2680: Definitive Demand ISF Summary (BG≥180, 2h isolation)", fontsize=14, pad=20)

plt.tight_layout()
plt.savefig(VIS / "fig7_summary_table.png", dpi=150)
plt.close()
print("Panel 7: Summary table saved")

# ── Additional statistical tests ─────────────────────────────────────
if len(events_180) > 50:
    # Kruskal-Wallis across controllers
    groups = [events_180[events_180["controller"] == c]["demand_isf"].dropna()
              for c in ["loop", "trio", "openaps"]]
    groups = [g for g in groups if len(g) > 5]
    if len(groups) >= 2:
        kw_stat, kw_p = stats.kruskal(*groups)
        results["kruskal_wallis_controllers"] = {
            "statistic": float(kw_stat),
            "p_value": float(kw_p),
        }
        print(f"\nKruskal-Wallis (controllers): H={kw_stat:.1f}, p={kw_p:.4f}")
    
    # Dose-independence verification (should be |r| < 0.3)
    r_dose, p_dose = stats.spearmanr(events_180["dose"], events_180["demand_isf"])
    results["dose_independence"] = {
        "spearman_r": float(r_dose),
        "spearman_p": float(p_dose),
    }
    print(f"Dose-independence: r={r_dose:.3f}, p={p_dose:.4f} (expect |r|<0.3)")

# Save results
with open(EXP / "exp-2680_definitive_isf.json", "w") as f:
    json.dump(results, f, indent=2, default=str)

print(f"\n{'='*60}")
print(f"EXP-2680 COMPLETE")
print(f"Events: {len(events_all)} (all BG), {len(events_180)} (BG≥180)")
print(f"Results: {EXP / 'exp-2680_definitive_isf.json'}")
print(f"Figures: {VIS}/fig[1-7]_*.png")
