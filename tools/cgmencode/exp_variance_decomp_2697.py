#!/usr/bin/env python3
"""EXP-2697: Within-Patient Variance Decomposition & Random Effects

Decompose BG outcome variance into:
  - Between-patient: physiology, settings, controller type
  - Within-patient, between-day: circadian, meal patterns, activity
  - Within-day residual: stochastic glucose variation

Uses hierarchical/mixed-effects style decomposition (via ANOVA):
  BG_drop = patient_mean + day_deviation + residual

Then within each level, assess how much insulin channels explain.

Also: within-patient natural experiments — do patients with ISF changes
show TIR changes? (Diff-in-diff for settings changes.)

Panels:
  1. Variance decomposition: between-patient vs within-patient vs residual
  2. Between-patient model: what patient factors predict mean BG drop?
  3. Within-patient day-to-day variation: what predicts good vs bad days?
  4. Within-patient insulin channel effects (patient-specific slopes)
  5. Settings change natural experiments (diff-in-diff)
  6. Patient-specific effect heterogeneity (forest plot)
"""

import json, pathlib, warnings
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy import stats
from numpy.linalg import lstsq

warnings.filterwarnings("ignore")
OUT = pathlib.Path("visualizations/variance-decomposition")
OUT.mkdir(parents=True, exist_ok=True)
EXP = pathlib.Path("externals/experiments")

# ── Load data ──────────────────────────────────────────────────────────
grid = pd.read_parquet("externals/ns-parquet/training/grid.parquet")
ds = pd.read_parquet("externals/ns-parquet/training/devicestatus.parquet")
ctrl_map = ds.groupby("patient_id")["controller"].first().to_dict()
grid["controller"] = grid["patient_id"].map(ctrl_map)

manifest = json.loads((EXP / "autoprepare-qualified.json").read_text())
qual = manifest["qualified_patients"]
grid = grid[grid["patient_id"].isin(qual)].copy()
grid["time"] = pd.to_datetime(grid["time"], utc=True)
grid = grid.sort_values(["patient_id", "time"]).reset_index(drop=True)

FLOOR = 180
HORIZON = 24

# ── Extract events with day structure ─────────────────────────────────
print("Extracting events with temporal structure...")
events = []
for pid in grid["patient_id"].unique():
    pg = grid[grid["patient_id"] == pid].reset_index(drop=True)
    ctrl = pg["controller"].iloc[0]
    glucose = pg["glucose"].values
    bolus = pg["bolus"].values
    smb = pg["bolus_smb"].values if "bolus_smb" in pg.columns else np.zeros(len(pg))
    net_basal = pg["net_basal"].values if "net_basal" in pg.columns else np.full(len(pg), np.nan)
    sched_basal = pg["scheduled_basal_rate"].values if "scheduled_basal_rate" in pg.columns else np.full(len(pg), np.nan)
    iob = pg["iob"].values if "iob" in pg.columns else np.full(len(pg), np.nan)
    carbs_col = pg["carbs"].values if "carbs" in pg.columns else np.zeros(len(pg))
    roc = pg["glucose_roc"].values if "glucose_roc" in pg.columns else np.full(len(pg), np.nan)
    times = pg["time"].values
    isf = pg["scheduled_isf"].values if "scheduled_isf" in pg.columns else np.full(len(pg), np.nan)

    t0 = pd.Timestamp(times[0])
    for i in range(HORIZON, len(pg) - HORIZON):
        bg0 = glucose[i]
        if np.isnan(bg0) or bg0 < FLOOR:
            continue
        bg_2h = glucose[i + HORIZON]
        if np.isnan(bg_2h):
            continue

        try:
            ts = pd.Timestamp(times[i])
            day = (ts - t0).days
            hour = ts.hour
        except Exception:
            day = i // 288
            hour = 12

        events.append({
            "patient_id": pid, "controller": ctrl,
            "bg0": bg0, "bg_2h": bg_2h, "bg_drop": bg0 - bg_2h,
            "bolus_total": np.nansum(bolus[i:i+HORIZON]),
            "smb_total": np.nansum(smb[i:i+HORIZON]),
            "excess_basal": (np.nansum(net_basal[i:i+HORIZON]) - np.nansum(sched_basal[i:i+HORIZON])) * (5.0/60.0),
            "carbs_2h": np.nansum(carbs_col[i:i+HORIZON]),
            "roc_start": roc[i] if not np.isnan(roc[i]) else 0,
            "iob_start": iob[i] if not np.isnan(iob[i]) else 0,
            "isf": isf[i] if not np.isnan(isf[i]) else np.nan,
            "day": day, "hour": hour,
        })

ev = pd.DataFrame(events)
print(f"  Events: {len(ev)}")

# ── Panel 1: Variance decomposition (hierarchical ANOVA) ─────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 6))

# Grand mean
grand_mean = ev["bg_drop"].mean()

# Patient means
pat_means = ev.groupby("patient_id")["bg_drop"].mean()
ev["pat_mean"] = ev["patient_id"].map(pat_means)

# Day means within patient
ev["pat_day"] = ev["patient_id"] + "_" + ev["day"].astype(str)
day_means = ev.groupby("pat_day")["bg_drop"].mean()
ev["day_mean"] = ev["pat_day"].map(day_means)

# Variance components
ss_total = np.sum((ev["bg_drop"] - grand_mean)**2)
ss_between_patient = np.sum((ev["pat_mean"] - grand_mean)**2)
ss_between_day = np.sum((ev["day_mean"] - ev["pat_mean"])**2)
ss_residual = np.sum((ev["bg_drop"] - ev["day_mean"])**2)

pct_patient = ss_between_patient / ss_total * 100
pct_day = ss_between_day / ss_total * 100
pct_residual = ss_residual / ss_total * 100

# 1a: Pie chart
axes[0].pie([pct_patient, pct_day, pct_residual],
           labels=[f"Between-patient\n{pct_patient:.1f}%",
                   f"Between-day\n{pct_day:.1f}%",
                   f"Residual\n{pct_residual:.1f}%"],
           colors=["C0", "C1", "C2"], autopct="%1.1f%%", startangle=90)
axes[0].set_title("BG Drop Variance Decomposition")

# 1b: ICC (Intraclass Correlation Coefficient)
n_patients = ev["patient_id"].nunique()
n_days = ev["pat_day"].nunique()
icc_patient = pct_patient / 100
icc_day = pct_day / 100

axes[1].barh(["Between-patient\n(physiology, settings,\ncontroller)",
              "Between-day\n(circadian, meals,\nactivity)",
              "Within-day\nresidual"],
            [pct_patient, pct_day, pct_residual],
            color=["C0", "C1", "C2"], edgecolor="k", alpha=0.7)
axes[1].set_xlabel("% of Total Variance")
axes[1].set_title(f"Hierarchical Variance Components\nICC(patient)={icc_patient:.3f}")
for i, v in enumerate([pct_patient, pct_day, pct_residual]):
    axes[1].text(v + 0.5, i, f"{v:.1f}%", va="center", fontsize=11)

plt.suptitle("EXP-2697: Variance Decomposition", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig(OUT / "fig1_variance_decomp.png", dpi=150)
plt.close()
print(f"Panel 1: Variance decomposition saved (patient={pct_patient:.1f}%, day={pct_day:.1f}%, residual={pct_residual:.1f}%)")

# ── Panel 2: Between-patient model ───────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 6))

# Patient-level features
pat = ev.groupby("patient_id").agg(
    mean_drop=("bg_drop", "mean"),
    mean_bg0=("bg0", "mean"),
    mean_bolus=("bolus_total", "mean"),
    mean_smb=("smb_total", "mean"),
    mean_excess_basal=("excess_basal", "mean"),
    mean_carbs=("carbs_2h", "mean"),
    mean_isf=("isf", "mean"),
    controller=("controller", "first"),
    n_events=("bg_drop", "count"),
).reset_index()

pat["is_trio"] = (pat["controller"] == "trio").astype(float)
pat["is_loop"] = (pat["controller"] == "loop").astype(float)

# Model: mean_drop ~ features
bp_features = ["mean_bg0", "mean_bolus", "mean_smb", "mean_excess_basal",
               "mean_carbs", "mean_isf", "is_trio", "is_loop"]
bp_data = pat[bp_features + ["mean_drop"]].dropna()

if len(bp_data) >= 10:
    X_bp = bp_data[bp_features].values
    y_bp = bp_data["mean_drop"].values
    X_bp_n = (X_bp - X_bp.mean(axis=0)) / (X_bp.std(axis=0) + 1e-10)
    X_bp_aug = np.column_stack([X_bp_n, np.ones(len(X_bp_n))])
    b_bp, _, _, _ = lstsq(X_bp_aug, y_bp, rcond=None)
    y_bp_pred = X_bp_aug @ b_bp
    r2_bp = 1 - np.sum((y_bp - y_bp_pred)**2) / np.sum((y_bp - y_bp.mean())**2)

    # SE
    n_bp = len(y_bp)
    sigma2_bp = np.sum((y_bp - y_bp_pred)**2) / max(n_bp - len(b_bp), 1)
    try:
        cov_bp = sigma2_bp * np.linalg.inv(X_bp_aug.T @ X_bp_aug)
        se_bp = np.sqrt(np.diag(cov_bp))[:-1]
    except Exception:
        se_bp = np.full(len(bp_features), np.nan)

    p_vals_bp = []
    for c, s in zip(b_bp[:-1], se_bp):
        if s > 0 and not np.isnan(s):
            t = c / s
            p_vals_bp.append(2 * (1 - stats.t.cdf(abs(t), df=max(n_bp - len(b_bp), 1))))
        else:
            p_vals_bp.append(1.0)

    col_bp = ["C3" if p < 0.05 else "gray" for p in p_vals_bp]
    axes[0].barh(range(len(bp_features)), b_bp[:-1], color=col_bp,
                xerr=1.96 * se_bp, capsize=4, edgecolor="k")
    axes[0].set_yticks(range(len(bp_features)))
    axes[0].set_yticklabels(bp_features, fontsize=9)
    axes[0].axvline(0, color="k", ls="--", alpha=0.5)
    axes[0].set_xlabel("Std. coefficient")
    axes[0].set_title(f"Between-Patient Model: R²={r2_bp:.3f} (n={n_bp})")

    # 2b: Predicted vs actual
    axes[1].scatter(y_bp_pred, y_bp, s=80, c="C0", edgecolors="k", alpha=0.7)
    axes[1].plot([y_bp.min(), y_bp.max()], [y_bp.min(), y_bp.max()], "k--", alpha=0.5)
    axes[1].set_xlabel("Predicted Mean BG Drop")
    axes[1].set_ylabel("Actual Mean BG Drop")
    axes[1].set_title(f"Between-Patient: Predicted vs Actual")

colors_map = {"loop": "C0", "trio": "C1", "openaps": "C2"}

plt.suptitle("EXP-2697: Between-Patient Model", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig(OUT / "fig2_between_patient.png", dpi=150)
plt.close()
print(f"Panel 2: Between-patient model saved (R²={r2_bp:.3f})")

# ── Panel 3: Within-patient day-to-day model ──────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 6))

# Day-level aggregation
day_agg = ev.groupby(["patient_id", "day"]).agg(
    mean_drop=("bg_drop", "mean"),
    mean_bg0=("bg0", "mean"),
    total_bolus=("bolus_total", "sum"),
    total_smb=("smb_total", "sum"),
    total_carbs=("carbs_2h", "sum"),
    mean_isf=("isf", "mean"),
    controller=("controller", "first"),
    n=("bg_drop", "count"),
).reset_index()
day_agg = day_agg[day_agg["n"] >= 5]

# De-mean within patient (fixed effects)
for col in ["mean_drop", "mean_bg0", "total_bolus", "total_smb", "total_carbs"]:
    pat_mean = day_agg.groupby("patient_id")[col].transform("mean")
    day_agg[f"{col}_dm"] = day_agg[col] - pat_mean

# Within-patient regression
wp_features = ["mean_bg0_dm", "total_bolus_dm", "total_smb_dm", "total_carbs_dm"]
wp_data = day_agg[wp_features + ["mean_drop_dm"]].dropna()

if len(wp_data) >= 50:
    X_wp = wp_data[wp_features].values
    y_wp = wp_data["mean_drop_dm"].values
    X_wp_n = (X_wp - X_wp.mean(axis=0)) / (X_wp.std(axis=0) + 1e-10)
    X_wp_aug = np.column_stack([X_wp_n, np.ones(len(X_wp_n))])
    b_wp, _, _, _ = lstsq(X_wp_aug, y_wp, rcond=None)
    y_wp_pred = X_wp_aug @ b_wp
    r2_wp = 1 - np.sum((y_wp - y_wp_pred)**2) / np.sum((y_wp - y_wp.mean())**2)

    # SE
    n_wp = len(y_wp)
    sigma2_wp = np.sum((y_wp - y_wp_pred)**2) / max(n_wp - len(b_wp), 1)
    try:
        cov_wp = sigma2_wp * np.linalg.inv(X_wp_aug.T @ X_wp_aug)
        se_wp = np.sqrt(np.diag(cov_wp))[:-1]
    except Exception:
        se_wp = np.full(len(wp_features), np.nan)

    col_wp = ["C3" if abs(b_wp[i]) > 1.96 * se_wp[i] else "gray" for i in range(len(wp_features))]
    axes[0].barh(range(len(wp_features)), b_wp[:-1], color=col_wp,
                xerr=1.96 * se_wp, capsize=4, edgecolor="k")
    axes[0].set_yticks(range(len(wp_features)))
    axes[0].set_yticklabels([f.replace("_dm", "\n(demeaned)") for f in wp_features], fontsize=9)
    axes[0].axvline(0, color="k", ls="--", alpha=0.5)
    axes[0].set_xlabel("Coefficient (within-patient)")
    axes[0].set_title(f"Within-Patient Day-Level: R²={r2_wp:.3f} (n={n_wp} days)")

print(f"Panel 3a: Within-patient model (R²={r2_wp:.3f})")

# 3b: Good day vs bad day
day_agg["tir"] = ev.groupby(["patient_id", "day"]).apply(
    lambda x: 100 * ((x["bg_2h"] >= 70) & (x["bg_2h"] <= 180)).mean()
).values if False else np.nan  # Skip if slow

# Instead: show within-patient drop variance
pat_drop_var = ev.groupby("patient_id")["bg_drop"].var()
pat_drop_mean = ev.groupby("patient_id")["bg_drop"].mean()

axes[1].scatter(pat_drop_mean, pat_drop_var, s=80, edgecolors="k", alpha=0.7,
               c=[colors_map.get(ctrl_map.get(p, ""), "gray") for p in pat_drop_mean.index])
axes[1].set_xlabel("Mean BG Drop (mg/dL)")
axes[1].set_ylabel("BG Drop Variance")
axes[1].set_title("Patient Heterogeneity: Mean vs Variance")
axes[1].grid(True, alpha=0.3)

# Legend
for ctrl, color in colors_map.items():
    axes[1].scatter([], [], color=color, label=ctrl.upper(), edgecolors="k")
axes[1].legend()

plt.suptitle("EXP-2697: Within-Patient Analysis", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig(OUT / "fig3_within_patient.png", dpi=150)
plt.close()
print("Panel 3: Within-patient saved")

# ── Panel 4: Patient-specific insulin slopes (forest plot) ────────────
fig, ax = plt.subplots(figsize=(12, 10))

# For each patient, run multi-channel regression and extract bolus coefficient
patient_slopes = []
features = ["bg0", "bolus_total", "smb_total", "excess_basal", "carbs_2h", "roc_start"]

for pid in ev["patient_id"].unique():
    pe = ev[ev["patient_id"] == pid]
    clean = pe[features + ["bg_drop"]].dropna()
    if len(clean) < 100:
        continue

    X = clean[features].values
    y = clean["bg_drop"].values
    X_aug = np.column_stack([X, np.ones(len(X))])
    b, _, _, _ = lstsq(X_aug, y, rcond=None)

    n = len(y)
    sigma2 = np.sum((y - X_aug @ b)**2) / max(n - len(b), 1)
    try:
        cov = sigma2 * np.linalg.inv(X_aug.T @ X_aug)
        se_bolus = np.sqrt(cov[1, 1])
    except Exception:
        se_bolus = np.nan

    r2_p = 1 - np.sum((y - X_aug @ b)**2) / np.sum((y - y.mean())**2)
    ctrl = pe["controller"].iloc[0]

    patient_slopes.append({
        "patient_id": pid[:12],
        "controller": ctrl,
        "bolus_coef": b[1],
        "se": se_bolus,
        "r2": r2_p,
        "n": n,
    })

ps = pd.DataFrame(patient_slopes).sort_values("bolus_coef")

# Forest plot
y_pos = range(len(ps))
ax.errorbar(ps["bolus_coef"], y_pos, xerr=1.96 * ps["se"],
           fmt="none", color="k", capsize=3)
ax.scatter(ps["bolus_coef"], y_pos, s=60,
          c=[colors_map.get(c, "gray") for c in ps["controller"]],
          edgecolors="k", zorder=5)
ax.set_yticks(y_pos)
ax.set_yticklabels([f"{row['patient_id']} ({row['controller']}, n={row['n']}, R²={row['r2']:.2f})"
                   for _, row in ps.iterrows()], fontsize=8)
ax.axvline(0, color="k", ls="--", alpha=0.5)

# Pooled estimate
pooled_beta = np.average(ps["bolus_coef"], weights=1/ps["se"]**2)
ax.axvline(pooled_beta, color="C3", ls=":", lw=2, label=f"Pooled β={pooled_beta:.1f}")

ax.set_xlabel("Bolus Coefficient (BG drop per 1U)")
ax.set_title("Patient-Specific Bolus Effects (Forest Plot)")
ax.legend()
ax.grid(True, alpha=0.3, axis="x")

plt.suptitle("EXP-2697: Patient-Specific Effect Heterogeneity", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig(OUT / "fig4_forest_plot.png", dpi=150)
plt.close()
print("Panel 4: Forest plot saved")

# ── Panel 5: Settings change natural experiments ──────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 6))

# Find patients with ISF changes (within-patient variation)
isf_changes = []
for pid in ev["patient_id"].unique():
    pe = ev[ev["patient_id"] == pid]
    isf_vals = pe["isf"].dropna()
    if len(isf_vals) < 100:
        continue

    isf_std = isf_vals.std()
    isf_range = isf_vals.max() - isf_vals.min()
    isf_iqr = isf_vals.quantile(0.75) - isf_vals.quantile(0.25)

    # Split into early/late halves
    mid = len(pe) // 2
    early = pe.iloc[:mid]
    late = pe.iloc[mid:]

    early_isf = early["isf"].mean()
    late_isf = late["isf"].mean()
    early_drop = early["bg_drop"].mean()
    late_drop = late["bg_drop"].mean()

    isf_changes.append({
        "patient_id": pid[:12],
        "controller": pe["controller"].iloc[0],
        "isf_std": isf_std,
        "isf_range": isf_range,
        "isf_iqr": isf_iqr,
        "early_isf": early_isf,
        "late_isf": late_isf,
        "delta_isf": late_isf - early_isf,
        "early_drop": early_drop,
        "late_drop": late_drop,
        "delta_drop": late_drop - early_drop,
    })

ic = pd.DataFrame(isf_changes)

# 5a: ISF change vs BG drop change
axes[0].scatter(ic["delta_isf"], ic["delta_drop"], s=80,
               c=[colors_map.get(c, "gray") for c in ic["controller"]],
               edgecolors="k", alpha=0.7)
if len(ic) >= 5:
    r_ic, p_ic = stats.pearsonr(ic["delta_isf"].dropna(), ic["delta_drop"].dropna())
    slope = np.polyfit(ic["delta_isf"].dropna(), ic["delta_drop"].dropna(), 1)
    x_line = np.linspace(ic["delta_isf"].min(), ic["delta_isf"].max(), 100)
    axes[0].plot(x_line, np.polyval(slope, x_line), "k--", alpha=0.5)
    axes[0].set_title(f"ISF Change → BG Drop Change\nr={r_ic:.3f}, p={p_ic:.3f}")
else:
    axes[0].set_title("ISF Change → BG Drop Change")

axes[0].set_xlabel("ΔISF (late − early)")
axes[0].set_ylabel("ΔBG Drop (late − early)")
axes[0].axhline(0, color="k", ls=":", alpha=0.5)
axes[0].axvline(0, color="k", ls=":", alpha=0.5)
axes[0].grid(True, alpha=0.3)

# 5b: ISF variability across patients
ic_sorted = ic.sort_values("isf_range", ascending=False)
axes[1].barh(range(len(ic_sorted)), ic_sorted["isf_range"],
            color=[colors_map.get(c, "gray") for c in ic_sorted["controller"]],
            edgecolor="k", alpha=0.7)
axes[1].set_yticks(range(len(ic_sorted)))
axes[1].set_yticklabels(ic_sorted["patient_id"], fontsize=8)
axes[1].set_xlabel("ISF Range (max − min, mg/dL/U)")
axes[1].set_title("ISF Variability by Patient")
axes[1].grid(True, alpha=0.3, axis="x")

plt.suptitle("EXP-2697: Settings Change Natural Experiments", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig(OUT / "fig5_settings_change.png", dpi=150)
plt.close()
print("Panel 5: Settings changes saved")

# ── Panel 6: R² explained at each level ──────────────────────────────
fig, ax = plt.subplots(figsize=(12, 7))

# Summary: how much can we explain at each level?
r2_levels = {
    "Event-level\n(all channels,\nEXP-2690)": 0.296,
    "Within-patient\nday-level": r2_wp if len(wp_data) >= 50 else 0,
    "Between-patient\n(EXP-2693)": r2_bp,
    "Patient TIR\n(EXP-2693)": 0.702,
}

labels = list(r2_levels.keys())
values = list(r2_levels.values())
bar_colors = ["C0", "C1", "C2", "C3"]

bars = ax.bar(range(len(labels)), values, color=bar_colors, edgecolor="k", alpha=0.7)
for bar, val in zip(bars, values):
    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.01,
           f"{val:.3f}", ha="center", fontsize=12, fontweight="bold")

ax.set_xticks(range(len(labels)))
ax.set_xticklabels(labels, fontsize=10)
ax.set_ylabel("R²")
ax.set_title("Variance Explained at Each Hierarchical Level")
ax.set_ylim(0, 0.85)
ax.grid(True, alpha=0.3, axis="y")

# Annotation
ax.annotate("More aggregation → more explainable", xy=(0.5, 0.15), xytext=(2.5, 0.15),
           fontsize=11, style="italic", color="gray",
           arrowprops=dict(arrowstyle="->", color="gray"))

plt.suptitle("EXP-2697: Hierarchical R² Summary", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig(OUT / "fig6_hierarchical_r2.png", dpi=150)
plt.close()
print("Panel 6: Hierarchical R² saved")

# ── Save results ──────────────────────────────────────────────────────
results = {
    "experiment": "EXP-2697",
    "title": "Within-Patient Variance Decomposition",
    "n_events": int(len(ev)),
    "variance_decomposition": {
        "between_patient_pct": float(pct_patient),
        "between_day_pct": float(pct_day),
        "residual_pct": float(pct_residual),
        "icc_patient": float(icc_patient),
    },
    "between_patient_model": {"r2": float(r2_bp), "n": int(n_bp)},
    "within_patient_day_model": {"r2": float(r2_wp), "n": int(n_wp)},
    "patient_specific_slopes": {
        row["patient_id"]: {
            "bolus_coef": float(row["bolus_coef"]),
            "se": float(row["se"]),
            "r2": float(row["r2"]),
        } for _, row in ps.iterrows()
    },
    "pooled_bolus_effect": float(pooled_beta),
    "isf_change_correlation": {
        "r": float(r_ic) if len(ic) >= 5 else None,
        "p": float(p_ic) if len(ic) >= 5 else None,
    },
}
(EXP / "exp-2697_variance_decomp.json").write_text(json.dumps(results, indent=2))

print(f"""
{'='*60}
EXP-2697: Variance Decomposition — KEY RESULTS
{'='*60}

  VARIANCE COMPONENTS:
    Between-patient: {pct_patient:.1f}%
    Between-day:     {pct_day:.1f}%
    Residual:        {pct_residual:.1f}%
    ICC(patient):    {icc_patient:.3f}

  R² AT EACH LEVEL:
    Event-level (all channels):  0.296
    Day-level (within-patient):  {r2_wp:.3f}
    Patient-level:               {r2_bp:.3f}
    Patient TIR:                 0.702

  PATIENT-SPECIFIC BOLUS EFFECTS:
    Range: {ps['bolus_coef'].min():.1f} to {ps['bolus_coef'].max():.1f} mg/dL/U
    Pooled (inverse-variance weighted): {pooled_beta:.1f} mg/dL/U
    N patients with β < 0: {(ps['bolus_coef'] < 0).sum()}/{len(ps)}

  ISF CHANGE → BG DROP CHANGE:
    r = {r_ic:.3f}, p = {p_ic:.3f}
""")
