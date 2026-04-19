#!/usr/bin/env python3
"""EXP-2681: BG Drop Direct Modeling (replaces ISF-centric approach)

KEY INSIGHT from EXP-2680: BG_drop ≈ constant (~70-80 mg/dL) regardless of dose.
ISF = drop/dose creates artificial 1/dose dependence. Model drop directly.

6-panel dashboard:
  1. BG drop vs dose (by controller) — the fundamental relationship
  2. BG drop vs starting BG — does higher BG predict larger drop?
  3. BG drop vs IOB at correction — does existing IOB affect drop?
  4. Multivariate model: drop = f(dose, BG0, IOB, controller)
  5. Per-patient BG drop distributions
  6. Practical implications: expected drop per dose bin
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

VIS = Path("visualizations/bg-drop-model")
VIS.mkdir(parents=True, exist_ok=True)
EXP = Path("externals/experiments")

# Load data
manifest = json.load(open(EXP / "autoprepare-qualified.json"))
grid = pd.read_parquet("externals/ns-parquet/training/grid.parquet")
ds = pd.read_parquet("externals/ns-parquet/training/devicestatus.parquet")
ctrl_map = ds.groupby("patient_id")["controller"].first().to_dict()
grid = grid[grid["patient_id"].isin(manifest["qualified_patients"])].copy()
grid["controller"] = grid["patient_id"].map(ctrl_map)


def extract_correction_events(df, bg_floor=180, isolation_hours=2, min_dose=0.1):
    """Extract correction events with full context."""
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
            
            t_iso = pd.Timestamp(t0) - pd.Timedelta(hours=isolation_hours)
            if hasattr(t_iso, "tz") and t_iso.tz is None:
                try:
                    t_iso = t_iso.tz_localize("UTC")
                except Exception:
                    pass
            
            prior = pdf[(pdf["time"] >= t_iso) & (pdf["time"] < t0) & (pdf["bolus"] > min_dose)]
            if len(prior) > 0:
                continue
            
            # Get BG at t+2h
            t2h = pd.Timestamp(t0) + pd.Timedelta(hours=2)
            if hasattr(t2h, "tz") and t2h.tz is None:
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
            
            bg_drop = bg0 - bg2h
            events.append({
                "patient_id": pid,
                "controller": ctrl_map.get(pid, "unknown"),
                "time": t0,
                "bg0": bg0,
                "bg2h": bg2h,
                "bg_drop": bg_drop,
                "dose": dose,
                "iob": row.get("iob", np.nan),
                "cob": row.get("cob", np.nan),
                "scheduled_isf": row.get("scheduled_isf", np.nan),
                "scheduled_basal": row.get("scheduled_basal_rate", np.nan),
                "hour": pd.Timestamp(t0).hour,
                "log_dose": np.log(dose) if dose > 0 else np.nan,
            })
    
    return pd.DataFrame(events)


print("Extracting correction events (BG≥180, 2h isolation)...")
ev = extract_correction_events(grid)
# Filter to positive drops only for modeling
ev_pos = ev[ev["bg_drop"] > 0].copy()
print(f"Total events: {len(ev)}, positive drops: {len(ev_pos)} ({100*len(ev_pos)/len(ev):.0f}%)")

results = {"n_total": len(ev), "n_positive": len(ev_pos)}

# ── Panel 1: BG Drop vs Dose ────────────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 6))

colors = {"loop": "C0", "trio": "C1", "openaps": "C2"}
for ctrl in ["loop", "trio", "openaps"]:
    sub = ev_pos[ev_pos["controller"] == ctrl]
    if len(sub) > 5:
        axes[0].scatter(sub["dose"], sub["bg_drop"], c=colors[ctrl],
                       alpha=0.3, s=20, label=f"{ctrl} (n={len(sub)})")

# Log fit
valid = ev_pos.dropna(subset=["log_dose"])
if len(valid) > 10:
    slope, intercept, r, p, se = stats.linregress(valid["log_dose"], valid["bg_drop"])
    x_fit = np.linspace(valid["dose"].min(), valid["dose"].max(), 100)
    y_fit = slope * np.log(x_fit) + intercept
    axes[0].plot(x_fit, y_fit, "k--", linewidth=2, 
                label=f"log fit: drop={slope:.0f}×ln(dose)+{intercept:.0f} (r={r:.3f})")
    results["log_model"] = {"slope": float(slope), "intercept": float(intercept),
                            "r": float(r), "p": float(p)}

axes[0].set_xlabel("Correction Dose (U)")
axes[0].set_ylabel("BG Drop at 2h (mg/dL)")
axes[0].set_title("BG Drop vs Dose (BG≥180)")
axes[0].legend(fontsize=8)
axes[0].set_xlim(0, 15)
axes[0].set_ylim(-20, 300)

# 1b: BG Drop vs log(dose) — linearized
for ctrl in ["loop", "trio", "openaps"]:
    sub = ev_pos[ev_pos["controller"] == ctrl]
    if len(sub) > 5:
        axes[1].scatter(sub["log_dose"], sub["bg_drop"], c=colors[ctrl],
                       alpha=0.3, s=20, label=ctrl)

if len(valid) > 10:
    x_fit = np.linspace(valid["log_dose"].min(), valid["log_dose"].max(), 100)
    y_fit = slope * x_fit + intercept
    axes[1].plot(x_fit, y_fit, "k--", linewidth=2)

axes[1].set_xlabel("ln(Dose)")
axes[1].set_ylabel("BG Drop at 2h (mg/dL)")
axes[1].set_title("Linearized: Drop vs ln(Dose)")
axes[1].legend(fontsize=8)

plt.tight_layout()
plt.savefig(VIS / "fig1_drop_vs_dose.png", dpi=150)
plt.close()
print("Panel 1: Drop vs dose saved")

# ── Panel 2: BG Drop vs Starting BG ─────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 6))

for ctrl in ["loop", "trio", "openaps"]:
    sub = ev_pos[ev_pos["controller"] == ctrl]
    if len(sub) > 5:
        axes[0].scatter(sub["bg0"], sub["bg_drop"], c=colors[ctrl],
                       alpha=0.3, s=20, label=ctrl)

r_bg, p_bg = stats.spearmanr(ev_pos["bg0"], ev_pos["bg_drop"])
axes[0].set_xlabel("Starting BG (mg/dL)")
axes[0].set_ylabel("BG Drop at 2h (mg/dL)")
axes[0].set_title(f"Drop vs Starting BG (r={r_bg:.3f}, p={p_bg:.4f})")
axes[0].legend()
results["bg0_vs_drop"] = {"r": float(r_bg), "p": float(p_bg)}

# 2b: Ending BG distribution
for ctrl in ["loop", "trio", "openaps"]:
    sub = ev_pos[ev_pos["controller"] == ctrl]
    if len(sub) > 5:
        axes[1].hist(sub["bg2h"], bins=40, alpha=0.5, label=ctrl, density=True)
axes[1].axvline(180, color="red", linestyle="--", label="180 mg/dL")
axes[1].axvline(70, color="orange", linestyle="--", label="70 mg/dL")
axes[1].set_xlabel("BG at 2h (mg/dL)")
axes[1].set_ylabel("Density")
axes[1].set_title("Post-Correction BG Distribution")
axes[1].legend()

plt.tight_layout()
plt.savefig(VIS / "fig2_drop_vs_bg.png", dpi=150)
plt.close()
print("Panel 2: Drop vs BG saved")

# ── Panel 3: BG Drop vs IOB ─────────────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 6))

ev_iob = ev_pos.dropna(subset=["iob"])
for ctrl in ["loop", "trio", "openaps"]:
    sub = ev_iob[ev_iob["controller"] == ctrl]
    if len(sub) > 5:
        axes[0].scatter(sub["iob"], sub["bg_drop"], c=colors[ctrl],
                       alpha=0.3, s=20, label=ctrl)

if len(ev_iob) > 10:
    r_iob, p_iob = stats.spearmanr(ev_iob["iob"], ev_iob["bg_drop"])
    axes[0].set_title(f"Drop vs IOB at Correction (r={r_iob:.3f}, p={p_iob:.4f})")
    results["iob_vs_drop"] = {"r": float(r_iob), "p": float(p_iob)}
else:
    axes[0].set_title("Drop vs IOB at Correction")

axes[0].set_xlabel("IOB at correction time (U)")
axes[0].set_ylabel("BG Drop at 2h (mg/dL)")
axes[0].legend()

# 3b: Drop vs dose + IOB (total insulin)
if len(ev_iob) > 10:
    total_insulin = ev_iob["dose"] + ev_iob["iob"].clip(lower=0)
    for ctrl in ["loop", "trio", "openaps"]:
        sub = ev_iob[ev_iob["controller"] == ctrl]
        if len(sub) > 5:
            ti = sub["dose"] + sub["iob"].clip(lower=0)
            axes[1].scatter(ti, sub["bg_drop"], c=colors[ctrl],
                           alpha=0.3, s=20, label=ctrl)
    r_total, p_total = stats.spearmanr(total_insulin, ev_iob["bg_drop"])
    axes[1].set_xlabel("Total Insulin (dose + IOB)")
    axes[1].set_ylabel("BG Drop at 2h (mg/dL)")
    axes[1].set_title(f"Drop vs Total Insulin (r={r_total:.3f}, p={p_total:.4f})")
    axes[1].legend()
    results["total_insulin_vs_drop"] = {"r": float(r_total), "p": float(p_total)}

plt.tight_layout()
plt.savefig(VIS / "fig3_drop_vs_iob.png", dpi=150)
plt.close()
print("Panel 3: Drop vs IOB saved")

# ── Panel 4: Multivariate Model ─────────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 6))

# Build a simple multivariate model
from numpy.linalg import lstsq

ev_model = ev_pos.dropna(subset=["iob", "log_dose"]).copy()
if len(ev_model) > 50:
    # Model 1: drop = a + b*log(dose) + c*bg0 + d*iob
    X = np.column_stack([
        np.ones(len(ev_model)),
        ev_model["log_dose"].values,
        ev_model["bg0"].values,
        ev_model["iob"].values,
    ])
    y = ev_model["bg_drop"].values
    
    coefs, residuals, rank, sv = lstsq(X, y, rcond=None)
    y_pred = X @ coefs
    r_multi = np.corrcoef(y, y_pred)[0, 1]
    r2 = r_multi ** 2
    
    results["multivariate_model"] = {
        "intercept": float(coefs[0]),
        "coef_log_dose": float(coefs[1]),
        "coef_bg0": float(coefs[2]),
        "coef_iob": float(coefs[3]),
        "r": float(r_multi),
        "r2": float(r2),
        "n": len(ev_model),
    }
    
    axes[0].scatter(y, y_pred, alpha=0.2, s=10)
    lim = max(y.max(), y_pred.max()) * 1.1
    axes[0].plot([0, lim], [0, lim], "k--", alpha=0.3)
    axes[0].set_xlabel("Actual BG Drop (mg/dL)")
    axes[0].set_ylabel("Predicted BG Drop (mg/dL)")
    axes[0].set_title(f"Multivariate: drop ~ log(dose) + BG0 + IOB\nR²={r2:.3f}, n={len(ev_model)}")
    
    # Model comparison: log(dose) only vs multivariate
    X_dose = np.column_stack([np.ones(len(ev_model)), ev_model["log_dose"].values])
    coefs_dose, _, _, _ = lstsq(X_dose, y, rcond=None)
    y_pred_dose = X_dose @ coefs_dose
    r2_dose = np.corrcoef(y, y_pred_dose)[0, 1] ** 2
    
    X_bg = np.column_stack([np.ones(len(ev_model)), ev_model["bg0"].values])
    coefs_bg, _, _, _ = lstsq(X_bg, y, rcond=None)
    y_pred_bg = X_bg @ coefs_bg
    r2_bg = np.corrcoef(y, y_pred_bg)[0, 1] ** 2
    
    X_iob = np.column_stack([np.ones(len(ev_model)), ev_model["iob"].values])
    coefs_iob, _, _, _ = lstsq(X_iob, y, rcond=None)
    y_pred_iob = X_iob @ coefs_iob
    r2_iob = np.corrcoef(y, y_pred_iob)[0, 1] ** 2
    
    models = ["log(dose)", "BG0", "IOB", "Full"]
    r2s = [r2_dose, r2_bg, r2_iob, r2]
    bars = axes[1].bar(models, r2s, color=["C0", "C1", "C2", "C3"], alpha=0.7)
    axes[1].set_ylabel("R²")
    axes[1].set_title("Model Comparison: Predictors of BG Drop")
    for bar, val in zip(bars, r2s):
        axes[1].text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.005,
                    f"{val:.3f}", ha="center", fontsize=10)
    
    results["model_comparison"] = {
        "r2_log_dose": float(r2_dose),
        "r2_bg0": float(r2_bg),
        "r2_iob": float(r2_iob),
        "r2_full": float(r2),
    }
    
    print(f"  R² model comparison: log(dose)={r2_dose:.3f}, BG0={r2_bg:.3f}, "
          f"IOB={r2_iob:.3f}, full={r2:.3f}")

plt.tight_layout()
plt.savefig(VIS / "fig4_multivariate.png", dpi=150)
plt.close()
print("Panel 4: Multivariate model saved")

# ── Panel 5: Per-Patient BG Drop Distributions ──────────────────────
fig, ax = plt.subplots(figsize=(16, 8))

patient_medians = ev_pos.groupby("patient_id")["bg_drop"].median().sort_values()
order = patient_medians.index.tolist()

data_for_box = []
labels = []
color_list = []

for pid in order:
    sub = ev_pos[ev_pos["patient_id"] == pid]
    ctrl = ctrl_map.get(pid, "unknown")
    data_for_box.append(sub["bg_drop"].values)
    short = pid[:8] if len(pid) > 8 else pid
    labels.append(f"{short}\n({ctrl[0].upper()}, n={len(sub)})")
    color_list.append(colors.get(ctrl, "gray"))
    
    results.setdefault("by_patient", {})[pid] = {
        "controller": ctrl,
        "n_events": len(sub),
        "median_drop": float(sub["bg_drop"].median()),
        "median_dose": float(sub["dose"].median()),
        "median_bg0": float(sub["bg0"].median()),
    }

bp = ax.boxplot(data_for_box, patch_artist=True, showfliers=False, widths=0.6)
for patch, c in zip(bp["boxes"], color_list):
    patch.set_facecolor(c)
    patch.set_alpha(0.6)

ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=7)
ax.set_ylabel("BG Drop at 2h (mg/dL)")
ax.set_title("Per-Patient BG Drop Distribution (BG≥180, positive drops only)")
ax.axhline(80, color="gray", linestyle="--", alpha=0.5, label="80 mg/dL reference")
ax.legend()

plt.tight_layout()
plt.savefig(VIS / "fig5_per_patient_drop.png", dpi=150)
plt.close()
print("Panel 5: Per-patient drops saved")

# ── Panel 6: Dose-Response Bins ──────────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 6))

# 6a: Binned dose-response
dose_bins = [0, 0.5, 1, 2, 3, 5, 8, 15]
ev_pos["dose_bin"] = pd.cut(ev_pos["dose"], bins=dose_bins)

bin_stats = ev_pos.groupby("dose_bin", observed=True).agg(
    median_drop=("bg_drop", "median"),
    iqr25=("bg_drop", lambda x: x.quantile(0.25)),
    iqr75=("bg_drop", lambda x: x.quantile(0.75)),
    n=("bg_drop", "count"),
    median_dose=("dose", "median"),
).dropna()

x = range(len(bin_stats))
axes[0].bar(x, bin_stats["median_drop"], yerr=[
    bin_stats["median_drop"] - bin_stats["iqr25"],
    bin_stats["iqr75"] - bin_stats["median_drop"]
], alpha=0.7, capsize=5, color="steelblue")
axes[0].set_xticks(x)
axes[0].set_xticklabels([f"{b}\n(n={n})" for b, n in 
                         zip(bin_stats.index.astype(str), bin_stats["n"])],
                       rotation=45, ha="right", fontsize=8)
axes[0].set_xlabel("Dose Bin (U)")
axes[0].set_ylabel("Median BG Drop (mg/dL)")
axes[0].set_title("Dose-Response: Median BG Drop per Dose Bin")

# 6b: By controller in dose bins
for ctrl in ["loop", "trio", "openaps"]:
    sub = ev_pos[ev_pos["controller"] == ctrl]
    if len(sub) > 10:
        ctrl_bins = sub.groupby("dose_bin", observed=True).agg(
            median_drop=("bg_drop", "median"),
            n=("bg_drop", "count"),
        ).dropna()
        valid = ctrl_bins[ctrl_bins["n"] >= 3]
        if len(valid) > 1:
            axes[1].plot(range(len(valid)), valid["median_drop"], "o-",
                        label=f"{ctrl}", color=colors[ctrl])

axes[1].set_xlabel("Dose Bin Index")
axes[1].set_ylabel("Median BG Drop (mg/dL)")
axes[1].set_title("Dose-Response by Controller")
axes[1].legend()

results["dose_bins"] = {str(k): {"median_drop": float(v["median_drop"]), "n": int(v["n"]),
                                  "median_dose": float(v["median_dose"])}
                        for k, v in bin_stats.iterrows()}

plt.tight_layout()
plt.savefig(VIS / "fig6_dose_response_bins.png", dpi=150)
plt.close()
print("Panel 6: Dose-response bins saved")

# ── Summary Stats ────────────────────────────────────────────────────
print(f"\n{'='*60}")
print(f"EXP-2681: BG Drop Direct Modeling — RESULTS")
print(f"{'='*60}")
print(f"Total events (BG≥180): {len(ev)}")
print(f"Positive drops: {len(ev_pos)} ({100*len(ev_pos)/len(ev):.0f}%)")
print(f"\nBG Drop Statistics (positive only):")
print(f"  Median: {ev_pos['bg_drop'].median():.0f} mg/dL")
print(f"  IQR: [{ev_pos['bg_drop'].quantile(0.25):.0f}, {ev_pos['bg_drop'].quantile(0.75):.0f}]")
print(f"  Mean dose: {ev_pos['dose'].mean():.1f} U")

for ctrl in ["loop", "trio", "openaps"]:
    sub = ev_pos[ev_pos["controller"] == ctrl]
    if len(sub) > 0:
        print(f"\n  {ctrl} (n={len(sub)}):")
        print(f"    Median drop: {sub['bg_drop'].median():.0f} mg/dL")
        print(f"    Median dose: {sub['dose'].median():.1f} U")
        print(f"    Median starting BG: {sub['bg0'].median():.0f} mg/dL")

if "model_comparison" in results:
    print(f"\nModel R² Comparison:")
    mc = results["model_comparison"]
    print(f"  log(dose) alone: {mc['r2_log_dose']:.3f}")
    print(f"  BG0 alone:       {mc['r2_bg0']:.3f}")
    print(f"  IOB alone:       {mc['r2_iob']:.3f}")
    print(f"  Full model:      {mc['r2_full']:.3f}")

# Save
with open(EXP / "exp-2681_bg_drop_model.json", "w") as f:
    json.dump(results, f, indent=2, default=str)

print(f"\nResults: {EXP / 'exp-2681_bg_drop_model.json'}")
print(f"Figures: {VIS}/fig[1-6]_*.png")
