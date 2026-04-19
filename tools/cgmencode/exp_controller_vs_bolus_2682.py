#!/usr/bin/env python3
"""EXP-2682: Controller vs Bolus Insulin — Who Drives the Correction?

Follows from EXP-2681's finding that bolus dose explains only 1.5% of BG drop.

This experiment measures TOTAL insulin delivered over the 2h correction window
(bolus + controller temp basals + SMBs) to determine whether:
  a) Total insulin DOES predict BG drop (the controller compensates), or
  b) Even total insulin doesn't predict (BG drop is driven by something else)

5-panel dashboard:
  1. Total 2h insulin vs BG drop (vs bolus alone)
  2. Controller contribution: what fraction of 2h insulin is from the bolus?
  3. Controller behavior: does the controller increase or decrease dosing after bolus?
  4. BG trajectory: average BG trace 0-2h by dose quartile
  5. Net basal change: how does the controller adjust after a correction bolus?
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

VIS = Path("visualizations/controller-vs-bolus")
VIS.mkdir(parents=True, exist_ok=True)
EXP = Path("externals/experiments")

manifest = json.load(open(EXP / "autoprepare-qualified.json"))
grid = pd.read_parquet("externals/ns-parquet/training/grid.parquet")
ds = pd.read_parquet("externals/ns-parquet/training/devicestatus.parquet")
ctrl_map = ds.groupby("patient_id")["controller"].first().to_dict()
grid = grid[grid["patient_id"].isin(manifest["qualified_patients"])].copy()
grid["controller"] = grid["patient_id"].map(ctrl_map)


def extract_correction_windows(df, bg_floor=180, isolation_hours=2, min_dose=0.1):
    """Extract full 2h windows after corrections."""
    events = []
    for pid in df["patient_id"].unique():
        pdf = df[df["patient_id"] == pid].sort_values("time").reset_index(drop=True)
        bolus_idx = pdf.index[pdf["bolus"] > min_dose].tolist()
        
        for idx in bolus_idx:
            row = pdf.loc[idx]
            bg0 = row["glucose"]
            dose = row["bolus"]
            t0 = row["time"]
            
            if pd.isna(bg0) or bg0 < bg_floor:
                continue
            
            # 2h isolation
            t_iso = pd.Timestamp(t0) - pd.Timedelta(hours=isolation_hours)
            if hasattr(t_iso, "tz") and t_iso.tz is None:
                try:
                    t_iso = t_iso.tz_localize("UTC")
                except Exception:
                    pass
            
            prior = pdf[(pdf["time"] >= t_iso) & (pdf["time"] < t0) & (pdf["bolus"] > min_dose)]
            if len(prior) > 0:
                continue
            
            # Get the full 2h window
            t2h = pd.Timestamp(t0) + pd.Timedelta(hours=2)
            if hasattr(t2h, "tz") and t2h.tz is None:
                try:
                    t2h = t2h.tz_localize("UTC")
                except Exception:
                    pass
            
            window = pdf[(pdf["time"] >= t0) & (pdf["time"] <= t2h)]
            if len(window) < 5:
                continue
            
            # Get BG at 2h
            end_window = pdf[(pdf["time"] >= t2h - pd.Timedelta(minutes=10)) &
                            (pdf["time"] <= t2h + pd.Timedelta(minutes=10))]
            if len(end_window) == 0:
                continue
            closest = end_window.iloc[(end_window["time"] - t2h).abs().argsort().iloc[0]]
            bg2h = closest["glucose"]
            if pd.isna(bg2h):
                continue
            
            bg_drop = bg0 - bg2h
            
            # Total insulin in window (excluding the index bolus SMBs that happen AFTER)
            total_bolus_in_window = window["bolus"].sum()  # includes index bolus
            total_smb_in_window = window["bolus_smb"].sum() if "bolus_smb" in window.columns else 0
            
            # Net basal insulin over 2h
            if "actual_basal_rate" in window.columns:
                actual_basal_2h = window["actual_basal_rate"].mean() * 2  # U over 2h (rate * hours)
                scheduled_basal_2h = window["scheduled_basal_rate"].mean() * 2
                net_basal_excess = actual_basal_2h - scheduled_basal_2h
            else:
                actual_basal_2h = np.nan
                scheduled_basal_2h = np.nan
                net_basal_excess = np.nan
            
            total_insulin_2h = total_bolus_in_window + (actual_basal_2h if not pd.isna(actual_basal_2h) else 0)
            
            # IOB trajectory
            iob_start = row.get("iob", np.nan)
            iob_end = closest.get("iob", np.nan)
            
            # BG trajectory (for panel 4)
            bg_trace = []
            for mins in [0, 15, 30, 45, 60, 90, 120]:
                t_check = pd.Timestamp(t0) + pd.Timedelta(minutes=mins)
                if hasattr(t_check, "tz") and t_check.tz is None:
                    try:
                        t_check = t_check.tz_localize("UTC")
                    except Exception:
                        pass
                nearby = window[(window["time"] >= t_check - pd.Timedelta(minutes=5)) &
                               (window["time"] <= t_check + pd.Timedelta(minutes=5))]
                if len(nearby) > 0:
                    bg_trace.append(nearby["glucose"].iloc[0])
                else:
                    bg_trace.append(np.nan)
            
            events.append({
                "patient_id": pid,
                "controller": ctrl_map.get(pid, "unknown"),
                "time": t0,
                "bg0": bg0,
                "bg2h": bg2h,
                "bg_drop": bg_drop,
                "dose": dose,  # index bolus only
                "total_bolus_2h": total_bolus_in_window,  # all boluses including SMBs
                "total_smb_2h": total_smb_in_window,
                "actual_basal_2h": actual_basal_2h,
                "scheduled_basal_2h": scheduled_basal_2h,
                "net_basal_excess": net_basal_excess,
                "total_insulin_2h": total_insulin_2h,
                "iob_start": iob_start,
                "iob_end": iob_end,
                "bolus_fraction": dose / total_insulin_2h if total_insulin_2h > 0 else np.nan,
                "bg_trace": bg_trace,
            })
    
    return pd.DataFrame(events)


print("Extracting 2h correction windows (BG≥180)...")
ev = extract_correction_windows(grid)
ev_pos = ev[ev["bg_drop"] > 0].copy()
print(f"Total events: {len(ev)}, positive drops: {len(ev_pos)}")

results = {"n_total": len(ev), "n_positive": len(ev_pos)}

colors = {"loop": "C0", "trio": "C1", "openaps": "C2"}

# ── Panel 1: Total 2h Insulin vs BG Drop ─────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 6))

# 1a: Bolus dose vs BG drop
for ctrl in ["loop", "trio", "openaps"]:
    sub = ev_pos[ev_pos["controller"] == ctrl]
    if len(sub) > 5:
        axes[0].scatter(sub["dose"], sub["bg_drop"], c=colors[ctrl],
                       alpha=0.3, s=20, label=ctrl)

r_dose, p_dose = stats.spearmanr(ev_pos["dose"], ev_pos["bg_drop"])
axes[0].set_xlabel("Bolus Dose Only (U)")
axes[0].set_ylabel("BG Drop at 2h (mg/dL)")
axes[0].set_title(f"Bolus Dose vs Drop (r={r_dose:.3f})")
axes[0].legend()

# 1b: Total 2h insulin vs BG drop
valid = ev_pos.dropna(subset=["total_insulin_2h"])
valid = valid[valid["total_insulin_2h"] > 0]
for ctrl in ["loop", "trio", "openaps"]:
    sub = valid[valid["controller"] == ctrl]
    if len(sub) > 5:
        axes[1].scatter(sub["total_insulin_2h"], sub["bg_drop"], c=colors[ctrl],
                       alpha=0.3, s=20, label=ctrl)

if len(valid) > 10:
    r_total, p_total = stats.spearmanr(valid["total_insulin_2h"], valid["bg_drop"])
    axes[1].set_title(f"Total 2h Insulin vs Drop (r={r_total:.3f})")
    results["total_insulin_vs_drop"] = {"r": float(r_total), "p": float(p_total)}
else:
    axes[1].set_title("Total 2h Insulin vs Drop")

axes[1].set_xlabel("Total Insulin over 2h (U)")
axes[1].set_ylabel("BG Drop at 2h (mg/dL)")
axes[1].legend()

results["bolus_vs_drop"] = {"r": float(r_dose), "p": float(p_dose)}

plt.tight_layout()
plt.savefig(VIS / "fig1_insulin_vs_drop.png", dpi=150)
plt.close()
print(f"Panel 1: r(bolus,drop)={r_dose:.3f}, r(total,drop)={r_total:.3f}" if len(valid) > 10 else "Panel 1 saved")

# ── Panel 2: Bolus Fraction of Total 2h Insulin ─────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 6))

valid_frac = ev_pos.dropna(subset=["bolus_fraction"])
valid_frac = valid_frac[valid_frac["bolus_fraction"] > 0]
valid_frac = valid_frac[valid_frac["bolus_fraction"] <= 1]

# 2a: Distribution of bolus fraction
for ctrl in ["loop", "trio", "openaps"]:
    sub = valid_frac[valid_frac["controller"] == ctrl]
    if len(sub) > 5:
        axes[0].hist(sub["bolus_fraction"] * 100, bins=30, alpha=0.5,
                    label=f"{ctrl} (n={len(sub)}, median={sub['bolus_fraction'].median():.0%})",
                    density=True)

axes[0].set_xlabel("Bolus as % of Total 2h Insulin")
axes[0].set_ylabel("Density")
axes[0].set_title("What Fraction of 2h Insulin is the Bolus?")
axes[0].legend()

# 2b: Breakdown of 2h insulin components
components = []
for ctrl in ["loop", "trio", "openaps"]:
    sub = ev_pos[ev_pos["controller"] == ctrl]
    if len(sub) > 5:
        components.append({
            "controller": ctrl,
            "index_bolus": sub["dose"].median(),
            "additional_bolus": (sub["total_bolus_2h"] - sub["dose"]).median(),
            "basal": sub["actual_basal_2h"].median(),
        })

if components:
    comp_df = pd.DataFrame(components).set_index("controller")
    comp_df.plot(kind="bar", stacked=True, ax=axes[1], alpha=0.7)
    axes[1].set_ylabel("Median Insulin (U) over 2h")
    axes[1].set_title("2h Insulin Breakdown by Component")
    axes[1].legend(title="Component")
    
    results["insulin_breakdown"] = {c["controller"]: {
        "index_bolus": float(c["index_bolus"]),
        "additional_bolus": float(c["additional_bolus"]),
        "basal": float(c["basal"]) if not pd.isna(c["basal"]) else None,
    } for c in components}

plt.tight_layout()
plt.savefig(VIS / "fig2_bolus_fraction.png", dpi=150)
plt.close()
print("Panel 2: Bolus fraction saved")

# ── Panel 3: Controller Response After Bolus ────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 6))

# 3a: Net basal excess after correction (controller increasing or reducing?)
valid_basal = ev_pos.dropna(subset=["net_basal_excess"])
for ctrl in ["loop", "trio", "openaps"]:
    sub = valid_basal[valid_basal["controller"] == ctrl]
    if len(sub) > 5:
        axes[0].hist(sub["net_basal_excess"], bins=30, alpha=0.5,
                    label=f"{ctrl} (median={sub['net_basal_excess'].median():.2f}U)",
                    density=True)

axes[0].axvline(0, color="red", linestyle="--", alpha=0.5)
axes[0].set_xlabel("Net Basal Excess over 2h (U)")
axes[0].set_ylabel("Density")
axes[0].set_title("Controller Basal Adjustment After Correction")
axes[0].legend()

# 3b: SMBs delivered in 2h window
for ctrl in ["loop", "trio", "openaps"]:
    sub = ev_pos[ev_pos["controller"] == ctrl]
    if len(sub) > 5:
        axes[1].hist(sub["total_smb_2h"], bins=30, alpha=0.5,
                    label=f"{ctrl} (median={sub['total_smb_2h'].median():.1f}U)",
                    density=True)

axes[1].set_xlabel("Total SMBs in 2h Window (U)")
axes[1].set_ylabel("Density")
axes[1].set_title("SMB Delivery After Correction")
axes[1].legend()

plt.tight_layout()
plt.savefig(VIS / "fig3_controller_response.png", dpi=150)
plt.close()
print("Panel 3: Controller response saved")

# ── Panel 4: BG Trajectory by Dose Quartile ─────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 6))

timepoints = [0, 15, 30, 45, 60, 90, 120]

# 4a: All controllers, by dose quartile
ev_pos["dose_q"] = pd.qcut(ev_pos["dose"], q=4, labels=["Q1 (low)", "Q2", "Q3", "Q4 (high)"],
                            duplicates="drop")

for q_label in ev_pos["dose_q"].cat.categories:
    sub = ev_pos[ev_pos["dose_q"] == q_label]
    traces = np.array(sub["bg_trace"].tolist())
    if len(traces) > 5:
        # Normalize to starting BG
        bg_deltas = traces - traces[:, 0:1]
        median_trace = np.nanmedian(bg_deltas, axis=0)
        q25 = np.nanpercentile(bg_deltas, 25, axis=0)
        q75 = np.nanpercentile(bg_deltas, 75, axis=0)
        
        axes[0].plot(timepoints, median_trace, "o-", label=f"{q_label} (n={len(sub)})")
        axes[0].fill_between(timepoints, q25, q75, alpha=0.1)

axes[0].set_xlabel("Minutes after correction")
axes[0].set_ylabel("BG change from baseline (mg/dL)")
axes[0].set_title("BG Trajectory by Dose Quartile")
axes[0].axhline(0, color="gray", linestyle="--", alpha=0.3)
axes[0].legend()

# 4b: By controller
for ctrl in ["loop", "trio", "openaps"]:
    sub = ev_pos[ev_pos["controller"] == ctrl]
    traces = np.array(sub["bg_trace"].tolist())
    if len(traces) > 5:
        bg_deltas = traces - traces[:, 0:1]
        median_trace = np.nanmedian(bg_deltas, axis=0)
        axes[1].plot(timepoints, median_trace, "o-", label=f"{ctrl} (n={len(sub)})",
                    color=colors[ctrl])

axes[1].set_xlabel("Minutes after correction")
axes[1].set_ylabel("BG change from baseline (mg/dL)")
axes[1].set_title("BG Trajectory by Controller")
axes[1].axhline(0, color="gray", linestyle="--", alpha=0.3)
axes[1].legend()

plt.tight_layout()
plt.savefig(VIS / "fig4_bg_trajectory.png", dpi=150)
plt.close()
print("Panel 4: BG trajectory saved")

# ── Panel 5: R² Model Comparison (Extended) ─────────────────────────
fig, ax = plt.subplots(figsize=(10, 6))

from numpy.linalg import lstsq

ev_model = ev_pos.dropna(subset=["total_insulin_2h", "iob_start"]).copy()
ev_model = ev_model[ev_model["total_insulin_2h"] > 0]

if len(ev_model) > 50:
    y = ev_model["bg_drop"].values
    
    models = {}
    
    # Individual predictors
    for name, col in [("bolus_dose", "dose"), ("total_insulin_2h", "total_insulin_2h"),
                      ("BG0", "bg0"), ("IOB_start", "iob_start"),
                      ("net_basal_excess", "net_basal_excess")]:
        vals = ev_model[col].values
        valid_mask = ~np.isnan(vals)
        if valid_mask.sum() > 20:
            X = np.column_stack([np.ones(valid_mask.sum()), vals[valid_mask]])
            y_sub = y[valid_mask]
            coefs, _, _, _ = lstsq(X, y_sub, rcond=None)
            y_pred = X @ coefs
            r2 = max(0, np.corrcoef(y_sub, y_pred)[0, 1] ** 2)
            models[name] = r2
    
    # Full model
    cols = ["dose", "bg0", "iob_start", "total_insulin_2h"]
    X_full = np.column_stack([np.ones(len(ev_model))] + [ev_model[c].values for c in cols])
    coefs_full, _, _, _ = lstsq(X_full, y, rcond=None)
    y_pred_full = X_full @ coefs_full
    r2_full = max(0, np.corrcoef(y, y_pred_full)[0, 1] ** 2)
    models["full_model"] = r2_full
    
    bars = ax.bar(models.keys(), models.values(), color="steelblue", alpha=0.7)
    for bar, val in zip(bars, models.values()):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.003,
               f"{val:.3f}", ha="center", fontsize=9)
    
    ax.set_ylabel("R²")
    ax.set_title("Extended Model Comparison: What Predicts BG Drop?")
    ax.set_xticklabels(models.keys(), rotation=30, ha="right")
    
    results["extended_models"] = {k: float(v) for k, v in models.items()}
    
    print(f"\nR² Model Comparison:")
    for name, r2 in sorted(models.items(), key=lambda x: -x[1]):
        print(f"  {name}: {r2:.4f}")

plt.tight_layout()
plt.savefig(VIS / "fig5_extended_models.png", dpi=150)
plt.close()
print("Panel 5: Extended models saved")

# Summary
print(f"\n{'='*60}")
print(f"EXP-2682: Controller vs Bolus Insulin — RESULTS")
print(f"{'='*60}")
print(f"Events: {len(ev)} total, {len(ev_pos)} positive drops")

for ctrl in ["loop", "trio", "openaps"]:
    sub = ev_pos[ev_pos["controller"] == ctrl]
    if len(sub) > 0:
        frac = sub.dropna(subset=["bolus_fraction"])
        frac = frac[(frac["bolus_fraction"] > 0) & (frac["bolus_fraction"] <= 1)]
        print(f"\n{ctrl} (n={len(sub)}):")
        print(f"  Median bolus: {sub['dose'].median():.1f}U")
        print(f"  Median total 2h insulin: {sub['total_insulin_2h'].median():.1f}U")
        if len(frac) > 0:
            print(f"  Bolus as % of total: {frac['bolus_fraction'].median():.0%}")
        print(f"  Median BG drop: {sub['bg_drop'].median():.0f} mg/dL")

with open(EXP / "exp-2682_controller_vs_bolus.json", "w") as f:
    json.dump(results, f, indent=2, default=str)

print(f"\nResults: {EXP / 'exp-2682_controller_vs_bolus.json'}")
