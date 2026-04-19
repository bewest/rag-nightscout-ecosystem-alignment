#!/usr/bin/env python3
"""EXP-2691: Settings Mediation — How Settings Drive Controller Behavior → Outcomes

Settings (ISF, CR, basal rate) don't directly produce outcomes — they configure
how the controller responds. This experiment traces the causal pathway:

  Settings → Controller behavior → Glucose outcomes

Panels:
  1. Settings → controller behavior (SMB frequency, suspend rate, dosing intensity)
  2. Controller behavior → outcomes (TIR, hypo rate, mean BG)
  3. Full mediation path: settings → behavior → outcomes
  4. Within-patient settings changes: natural experiments
  5. Settings interaction with controller type
  6. Optimal settings frontier (TIR vs hypo by settings bin)
"""

import json, pathlib, warnings
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy import stats

warnings.filterwarnings("ignore")
OUT = pathlib.Path("visualizations/settings-mediation")
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

controllers = ["loop", "trio", "openaps"]
colors = {"loop": "C0", "trio": "C1", "openaps": "C2"}

# ── Compute daily stats per patient ────────────────────────────────────
print("Computing daily stats...")
grid["day"] = grid.groupby("patient_id")["time"].transform(
    lambda x: ((x - x.min()).dt.total_seconds() / 86400).astype(int)
)

# For each patient-day: settings, controller behavior, outcomes
daily = grid.groupby(["patient_id", "day"]).agg(
    # Settings
    mean_isf=("scheduled_isf", "mean"),
    mean_cr=("scheduled_cr", "mean"),
    mean_basal=("scheduled_basal_rate", "mean"),
    # Controller behavior
    smb_rate=("bolus_smb", lambda x: 100 * (x > 0).mean()),
    mean_smb_size=("bolus_smb", lambda x: x[x > 0].mean() if (x > 0).any() else 0),
    total_smb=("bolus_smb", "sum"),
    total_bolus=("bolus", "sum"),
    mean_iob=("iob", "mean"),
    # Outcomes
    tir=("glucose", lambda x: 100 * ((x >= 70) & (x <= 180)).mean()),
    hypo_pct=("glucose", lambda x: 100 * (x < 70).mean()),
    mean_bg=("glucose", "mean"),
    cv=("glucose", lambda x: x.std() / x.mean() * 100 if x.mean() > 0 else np.nan),
    n_readings=("glucose", "count"),
    controller=("controller", "first"),
).reset_index()

# Compute suspend rate
if "net_basal" in grid.columns:
    susp = grid.copy()
    susp["suspended"] = (susp["net_basal"].fillna(0) < 0.05) & (susp["scheduled_basal_rate"] > 0)
    # Excess basal per day
    susp["excess"] = susp["net_basal"].fillna(0) - susp["scheduled_basal_rate"].fillna(0)
    susp_daily = susp.groupby(["patient_id", "day"]).agg(
        suspend_pct=("suspended", lambda x: 100 * x.mean()),
        mean_excess=("excess", "mean"),
    ).reset_index()
    daily = daily.merge(susp_daily, on=["patient_id", "day"], how="left")

# Filter days with enough data
daily = daily[daily["n_readings"] >= 200].copy()  # at least ~16h of data
print(f"  Daily observations: {len(daily)} days from {daily['patient_id'].nunique()} patients")

# ── Panel 1: Settings → Controller Behavior ───────────────────────────
fig, axes = plt.subplots(2, 3, figsize=(18, 10))

# Settings predictors
settings = [("mean_isf", "ISF (mg/dL/U)"), ("mean_cr", "CR (g/U)"), ("mean_basal", "Basal (U/h)")]
# Behavior outcomes
behaviors = [("smb_rate", "SMB Rate (%)"), ("suspend_pct", "Suspend Rate (%)")]

for col_idx, (s_col, s_label) in enumerate(settings):
    for row_idx, (b_col, b_label) in enumerate(behaviors):
        ax = axes[row_idx][col_idx]
        for ctrl in controllers:
            d = daily[daily["controller"] == ctrl]
            valid = d[[s_col, b_col]].dropna()
            if len(valid) >= 20:
                ax.scatter(valid[s_col], valid[b_col], alpha=0.05, s=5, color=colors[ctrl])
                # Binned means
                bins = pd.qcut(valid[s_col], 5, duplicates="drop")
                binned = valid.groupby(bins)[b_col].mean()
                bin_centers = [interval.mid for interval in binned.index]
                ax.plot(bin_centers, binned.values, "o-", color=colors[ctrl], lw=2,
                       markersize=6, label=ctrl.upper())

        # Overall correlation
        valid_all = daily[[s_col, b_col]].dropna()
        if len(valid_all) >= 30:
            r, p = stats.pearsonr(valid_all[s_col], valid_all[b_col])
            ax.set_title(f"{s_label} → {b_label}\nr={r:.3f}, p={p:.2e}")
        else:
            ax.set_title(f"{s_label} → {b_label}")
        ax.set_xlabel(s_label)
        ax.set_ylabel(b_label)
        if col_idx == 0:
            ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)

plt.suptitle("EXP-2691: Settings → Controller Behavior", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig(OUT / "fig1_settings_to_behavior.png", dpi=150)
plt.close()
print("Panel 1: Settings → behavior saved")

# ── Panel 2: Controller Behavior → Outcomes ───────────────────────────
fig, axes = plt.subplots(2, 3, figsize=(18, 10))

behavior_cols = [("smb_rate", "SMB Rate (%)"), ("suspend_pct", "Suspend Rate (%)"),
                 ("total_bolus", "Total Bolus (U/day)")]
outcome_cols = [("tir", "TIR (%)"), ("hypo_pct", "Hypo (%)")]

for col_idx, (b_col, b_label) in enumerate(behavior_cols):
    for row_idx, (o_col, o_label) in enumerate(outcome_cols):
        ax = axes[row_idx][col_idx]
        for ctrl in controllers:
            d = daily[daily["controller"] == ctrl]
            valid = d[[b_col, o_col]].dropna()
            if len(valid) >= 20:
                ax.scatter(valid[b_col], valid[o_col], alpha=0.05, s=5, color=colors[ctrl])
                bins = pd.qcut(valid[b_col], 5, duplicates="drop")
                binned = valid.groupby(bins)[o_col].mean()
                bin_centers = [interval.mid for interval in binned.index]
                ax.plot(bin_centers, binned.values, "o-", color=colors[ctrl], lw=2,
                       markersize=6, label=ctrl.upper())

        valid_all = daily[[b_col, o_col]].dropna()
        if len(valid_all) >= 30:
            r, p = stats.pearsonr(valid_all[b_col], valid_all[o_col])
            ax.set_title(f"{b_label} → {o_label}\nr={r:.3f}, p={p:.2e}")
        ax.set_xlabel(b_label)
        ax.set_ylabel(o_label)
        if col_idx == 0:
            ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)

plt.suptitle("EXP-2691: Controller Behavior → Outcomes", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig(OUT / "fig2_behavior_to_outcomes.png", dpi=150)
plt.close()
print("Panel 2: Behavior → outcomes saved")

# ── Panel 3: Mediation path analysis ──────────────────────────────────
fig, axes = plt.subplots(2, 2, figsize=(14, 10))

# 3a: Direct path: ISF → TIR (total effect)
for ctrl in controllers:
    d = daily[daily["controller"] == ctrl]
    valid = d[["mean_isf", "tir"]].dropna()
    if len(valid) >= 20:
        bins = pd.qcut(valid["mean_isf"], 5, duplicates="drop")
        binned = valid.groupby(bins)["tir"].mean()
        bin_centers = [interval.mid for interval in binned.index]
        axes[0][0].plot(bin_centers, binned.values, "o-", color=colors[ctrl], lw=2, label=ctrl.upper())

valid = daily[["mean_isf", "tir"]].dropna()
r_total, p_total = stats.pearsonr(valid["mean_isf"], valid["tir"]) if len(valid) >= 10 else (0, 1)
axes[0][0].set_xlabel("ISF (mg/dL/U)")
axes[0][0].set_ylabel("TIR (%)")
axes[0][0].set_title(f"Total effect: ISF → TIR\nr={r_total:.3f}, p={p_total:.2e}")
axes[0][0].legend()
axes[0][0].grid(True, alpha=0.3)

# 3b: ISF → SMB rate (a-path)
valid = daily[["mean_isf", "smb_rate"]].dropna()
r_a, p_a = stats.pearsonr(valid["mean_isf"], valid["smb_rate"]) if len(valid) >= 10 else (0, 1)
for ctrl in controllers:
    d = daily[daily["controller"] == ctrl]
    v = d[["mean_isf", "smb_rate"]].dropna()
    if len(v) >= 20:
        bins = pd.qcut(v["mean_isf"], 5, duplicates="drop")
        binned = v.groupby(bins)["smb_rate"].mean()
        bin_centers = [interval.mid for interval in binned.index]
        axes[0][1].plot(bin_centers, binned.values, "o-", color=colors[ctrl], lw=2, label=ctrl.upper())

axes[0][1].set_xlabel("ISF (mg/dL/U)")
axes[0][1].set_ylabel("SMB rate (%)")
axes[0][1].set_title(f"a-path: ISF → SMB rate\nr={r_a:.3f}, p={p_a:.2e}")
axes[0][1].legend()
axes[0][1].grid(True, alpha=0.3)

# 3c: SMB rate → TIR (b-path)
valid = daily[["smb_rate", "tir"]].dropna()
r_b, p_b = stats.pearsonr(valid["smb_rate"], valid["tir"]) if len(valid) >= 10 else (0, 1)
for ctrl in controllers:
    d = daily[daily["controller"] == ctrl]
    v = d[["smb_rate", "tir"]].dropna()
    if len(v) >= 20:
        bins = pd.qcut(v["smb_rate"], 5, duplicates="drop")
        binned = v.groupby(bins)["tir"].mean()
        bin_centers = [interval.mid for interval in binned.index]
        axes[1][0].plot(bin_centers, binned.values, "o-", color=colors[ctrl], lw=2, label=ctrl.upper())

axes[1][0].set_xlabel("SMB rate (%)")
axes[1][0].set_ylabel("TIR (%)")
axes[1][0].set_title(f"b-path: SMB rate → TIR\nr={r_b:.3f}, p={p_b:.2e}")
axes[1][0].legend()
axes[1][0].grid(True, alpha=0.3)

# 3d: Mediation summary
# Multiple regression: TIR ~ ISF + SMB_rate (to test for direct vs mediated effect)
valid = daily[["mean_isf", "smb_rate", "tir"]].dropna()
if len(valid) >= 30:
    from numpy.linalg import lstsq
    X = valid[["mean_isf", "smb_rate"]].values
    y = valid["tir"].values
    X_n = (X - X.mean(axis=0)) / (X.std(axis=0) + 1e-10)
    X_n = np.column_stack([X_n, np.ones(len(X_n))])
    b, _, _, _ = lstsq(X_n, y, rcond=None)
    y_pred = X_n @ b
    r2_med = 1 - np.sum((y - y_pred)**2) / np.sum((y - y.mean())**2)

    summary = (
        f"MEDIATION ANALYSIS: ISF → SMB rate → TIR\n\n"
        f"Total effect (ISF → TIR):\n"
        f"  r = {r_total:.3f}, p = {p_total:.2e}\n\n"
        f"a-path (ISF → SMB rate):\n"
        f"  r = {r_a:.3f}, p = {p_a:.2e}\n\n"
        f"b-path (SMB rate → TIR):\n"
        f"  r = {r_b:.3f}, p = {p_b:.2e}\n\n"
        f"Joint model (ISF + SMB → TIR):\n"
        f"  R² = {r2_med:.3f}\n"
        f"  β_ISF = {b[0]:.3f}\n"
        f"  β_SMB = {b[1]:.3f}\n\n"
        f"If mediation holds:\n"
        f"  β_ISF should shrink when SMB added\n"
        f"  β_SMB should remain significant"
    )
else:
    summary = "Insufficient data for mediation analysis"

axes[1][1].text(0.05, 0.95, summary, transform=axes[1][1].transAxes, fontsize=10,
               va="top", fontfamily="monospace")
axes[1][1].axis("off")
axes[1][1].set_title("Mediation Summary")

plt.suptitle("EXP-2691: Mediation Path — Settings → Behavior → Outcomes", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig(OUT / "fig3_mediation.png", dpi=150)
plt.close()
print("Panel 3: Mediation path saved")

# ── Panel 4: Within-patient settings changes (natural experiments) ────
fig, axes = plt.subplots(1, 3, figsize=(18, 5))

# For each patient, compute weekly ISF and TIR
weekly = grid.groupby(["patient_id", grid.groupby("patient_id")["time"].transform(
    lambda x: ((x - x.min()).dt.total_seconds() / (7*86400)).astype(int)
)]).agg(
    mean_isf=("scheduled_isf", "mean"),
    tir=("glucose", lambda x: 100 * ((x >= 70) & (x <= 180)).mean()),
    mean_cr=("scheduled_cr", "mean"),
    controller=("controller", "first"),
    n=("glucose", "count"),
).reset_index()
weekly.columns = ["patient_id", "week", "mean_isf", "tir", "mean_cr", "controller", "n"]
weekly = weekly[weekly["n"] >= 500]

# For each patient, compute ISF change and TIR change (week to week)
within_results = []
for pid in weekly["patient_id"].unique():
    pw = weekly[weekly["patient_id"] == pid].sort_values("week")
    if len(pw) >= 4:
        isf_change = pw["mean_isf"].diff()
        tir_change = pw["tir"].diff()
        cr_change = pw["mean_cr"].diff()
        valid = isf_change.notna() & tir_change.notna()
        if valid.sum() >= 3:
            r_isf, p_isf = stats.pearsonr(isf_change[valid], tir_change[valid])
            ctrl = pw["controller"].iloc[0]
            isf_range = pw["mean_isf"].max() - pw["mean_isf"].min()
            within_results.append({
                "patient_id": pid, "r_isf_tir": r_isf, "p_isf_tir": p_isf,
                "isf_range": isf_range, "n_weeks": int(valid.sum()),
                "controller": ctrl,
            })

wr = pd.DataFrame(within_results)

# 4a: Within-patient ISF change → TIR change correlations
for ctrl in controllers:
    wc = wr[wr["controller"] == ctrl]
    if len(wc) > 0:
        axes[0].scatter(wc.index, wc["r_isf_tir"], s=60, label=f"{ctrl.upper()} (n={len(wc)})",
                       color=colors[ctrl], edgecolors="k", zorder=3)
axes[0].axhline(0, color="k", ls="--", alpha=0.5)
axes[0].set_ylabel("r(ΔISF, ΔTIR) within patient")
axes[0].set_xlabel("Patient")
axes[0].set_title("Within-Patient: ISF Change ↔ TIR Change")
axes[0].legend()

# 4b: ISF variability (range) — do settings actually change?
for ctrl in controllers:
    wc = wr[wr["controller"] == ctrl]
    if len(wc) > 0:
        axes[1].scatter(wc["isf_range"], wc["r_isf_tir"], s=60, label=ctrl.upper(),
                       color=colors[ctrl], edgecolors="k", zorder=3)
axes[1].set_xlabel("ISF range within patient (mg/dL/U)")
axes[1].set_ylabel("r(ΔISF, ΔTIR)")
axes[1].set_title("Settings Variability vs Effect Strength")
axes[1].axhline(0, color="k", ls="--", alpha=0.5)
axes[1].legend()
axes[1].grid(True, alpha=0.3)

# 4c: Summary
sig_pos = ((wr["r_isf_tir"] > 0) & (wr["p_isf_tir"] < 0.05)).sum() if len(wr) > 0 else 0
sig_neg = ((wr["r_isf_tir"] < 0) & (wr["p_isf_tir"] < 0.05)).sum() if len(wr) > 0 else 0
mean_r = wr["r_isf_tir"].mean() if len(wr) > 0 else 0
mean_range = wr["isf_range"].mean() if len(wr) > 0 else 0

summary = (
    f"Within-Patient Natural Experiments\n\n"
    f"Patients analyzed: {len(wr)}\n"
    f"Mean ISF range: {mean_range:.1f} mg/dL/U\n"
    f"Mean r(ΔISF, ΔTIR): {mean_r:.3f}\n\n"
    f"Sig. positive (higher ISF → better TIR): {sig_pos}\n"
    f"Sig. negative (higher ISF → worse TIR): {sig_neg}\n"
    f"Non-significant: {len(wr) - sig_pos - sig_neg}\n\n"
    f"Note: positive r means that when ISF\n"
    f"increases, TIR also increases (less\n"
    f"aggressive dosing → better outcomes),\n"
    f"or the reverse."
)
axes[2].text(0.05, 0.95, summary, transform=axes[2].transAxes, fontsize=10,
            va="top", fontfamily="monospace")
axes[2].axis("off")

plt.suptitle("EXP-2691: Within-Patient Settings Changes", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig(OUT / "fig4_within_patient.png", dpi=150)
plt.close()
print("Panel 4: Within-patient saved")

# ── Panel 5: Settings × Controller interaction ───────────────────────
fig, axes = plt.subplots(1, 3, figsize=(18, 5))

for ax_idx, (s_col, s_label) in enumerate(settings):
    for ctrl in controllers:
        d = daily[daily["controller"] == ctrl]
        valid = d[[s_col, "tir"]].dropna()
        if len(valid) >= 30:
            bins = pd.qcut(valid[s_col], 5, duplicates="drop")
            binned = valid.groupby(bins).agg(tir_mean=("tir", "mean"), tir_se=("tir", "sem"))
            bin_centers = [interval.mid for interval in binned.index]
            axes[ax_idx].errorbar(bin_centers, binned["tir_mean"].values,
                                yerr=1.96 * binned["tir_se"].values,
                                fmt="o-", color=colors[ctrl], lw=2, capsize=4,
                                label=ctrl.upper())

    axes[ax_idx].set_xlabel(s_label)
    axes[ax_idx].set_ylabel("TIR (%)")
    axes[ax_idx].set_title(f"{s_label} → TIR by Controller")
    axes[ax_idx].legend()
    axes[ax_idx].grid(True, alpha=0.3)

plt.suptitle("EXP-2691: Settings × Controller Interaction", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig(OUT / "fig5_settings_controller_interaction.png", dpi=150)
plt.close()
print("Panel 5: Settings × controller interaction saved")

# ── Panel 6: Optimal settings frontier ────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 6))

# Patient-level: aggregate settings vs aggregate outcomes
patient_agg = daily.groupby("patient_id").agg(
    mean_isf=("mean_isf", "mean"),
    mean_cr=("mean_cr", "mean"),
    mean_basal=("mean_basal", "mean"),
    tir=("tir", "mean"),
    hypo=("hypo_pct", "mean"),
    smb_rate=("smb_rate", "mean"),
    controller=("controller", "first"),
    n_days=("tir", "count"),
).reset_index()

# 6a: TIR vs Hypo frontier, sized by ISF
for ctrl in controllers:
    pa = patient_agg[patient_agg["controller"] == ctrl]
    axes[0].scatter(pa["hypo"], pa["tir"], s=pa["mean_isf"] * 2, alpha=0.7,
                   label=ctrl.upper(), color=colors[ctrl], edgecolors="k")

axes[0].set_xlabel("Hypo rate (%)")
axes[0].set_ylabel("TIR (%)")
axes[0].set_title("Safety Frontier (bubble size = ISF)")
axes[0].axhline(70, color="gray", ls=":", alpha=0.5)
axes[0].axvline(4, color="gray", ls=":", alpha=0.5)
axes[0].legend()
axes[0].grid(True, alpha=0.3)

# 6b: Multi-factor regression: TIR ~ ISF + CR + basal + controller
from numpy.linalg import lstsq
pa = patient_agg.dropna(subset=["mean_isf", "mean_cr", "mean_basal", "tir"])
# Encode controller
pa["ctrl_loop"] = (pa["controller"] == "loop").astype(float)
pa["ctrl_trio"] = (pa["controller"] == "trio").astype(float)

feat_names = ["mean_isf", "mean_cr", "mean_basal", "ctrl_loop", "ctrl_trio"]
X_pa = pa[feat_names].values
y_pa = pa["tir"].values
X_pa_n = (X_pa - X_pa.mean(axis=0)) / (X_pa.std(axis=0) + 1e-10)
X_pa_n = np.column_stack([X_pa_n, np.ones(len(X_pa_n))])
b_pa, _, _, _ = lstsq(X_pa_n, y_pa, rcond=None)
y_pred_pa = X_pa_n @ b_pa
r2_pa = 1 - np.sum((y_pa - y_pred_pa)**2) / np.sum((y_pa - y_pa.mean())**2)

n_pa = len(y_pa)
sigma2_pa = np.sum((y_pa - y_pred_pa)**2) / max(n_pa - len(b_pa), 1)
try:
    cov_pa = sigma2_pa * np.linalg.inv(X_pa_n.T @ X_pa_n)
    se_pa = np.sqrt(np.diag(cov_pa))[:-1]
except Exception:
    se_pa = np.full(len(feat_names), np.nan)

p_vals_pa = []
for c, s in zip(b_pa[:-1], se_pa):
    if s > 0 and not np.isnan(s):
        t = c / s
        p_val = 2 * (1 - stats.t.cdf(abs(t), df=max(n_pa - len(b_pa), 1)))
    else:
        p_val = 1.0
    p_vals_pa.append(p_val)

col_pa = ["C3" if p < 0.05 else "gray" for p in p_vals_pa]
axes[1].barh(range(len(feat_names)), b_pa[:-1], color=col_pa,
            xerr=1.96 * se_pa, capsize=4, edgecolor="k")
axes[1].set_yticks(range(len(feat_names)))
axes[1].set_yticklabels(feat_names)
axes[1].axvline(0, color="k", ls="--", alpha=0.5)
axes[1].set_xlabel("Std. coefficient (effect on TIR)")
axes[1].set_title(f"Patient-Level: Settings + Controller → TIR\nR²={r2_pa:.3f}, n={n_pa}")

plt.suptitle("EXP-2691: Optimal Settings Frontier", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig(OUT / "fig6_frontier.png", dpi=150)
plt.close()
print("Panel 6: Frontier saved")

# ── Results ────────────────────────────────────────────────────────────
results = {
    "experiment": "EXP-2691",
    "title": "Settings Mediation Analysis",
    "n_patient_days": int(len(daily)),
    "n_patients": int(daily["patient_id"].nunique()),
    "mediation": {
        "total_effect_isf_tir": {"r": float(r_total), "p": float(p_total)},
        "a_path_isf_smb": {"r": float(r_a), "p": float(p_a)},
        "b_path_smb_tir": {"r": float(r_b), "p": float(p_b)},
    },
    "within_patient": {
        "n_patients_analyzed": int(len(wr)),
        "mean_r_isf_tir": float(mean_r),
        "mean_isf_range": float(mean_range),
        "sig_positive": int(sig_pos),
        "sig_negative": int(sig_neg),
    },
    "patient_level_model": {
        "r2": float(r2_pa),
        "n": int(n_pa),
        "coefficients": {f: float(c) for f, c in zip(feat_names, b_pa[:-1])},
        "p_values": {f: float(p) for f, p in zip(feat_names, p_vals_pa)},
    },
}
(EXP / "exp-2691_settings_mediation.json").write_text(json.dumps(results, indent=2))

print(f"""
{'='*60}
EXP-2691: Settings Mediation Analysis — SUMMARY
{'='*60}

  Patient-days: {len(daily)}, Patients: {daily['patient_id'].nunique()}

  MEDIATION PATH: ISF → SMB rate → TIR
    Total (ISF → TIR):   r={r_total:.3f}, p={p_total:.2e}
    a-path (ISF → SMB):  r={r_a:.3f}, p={p_a:.2e}
    b-path (SMB → TIR):  r={r_b:.3f}, p={p_b:.2e}

  WITHIN-PATIENT (natural experiments):
    Patients with ISF changes: {len(wr)}
    Mean r(ΔISF, ΔTIR): {mean_r:.3f}
    Mean ISF range: {mean_range:.1f}
    Sig. positive: {sig_pos}, Sig. negative: {sig_neg}

  PATIENT-LEVEL MODEL (settings + controller → TIR):
    R² = {r2_pa:.3f} (n={n_pa})""")

for f, c, p in zip(feat_names, b_pa[:-1], p_vals_pa):
    sig = "***" if p < 0.001 else "**" if p < 0.01 else "*" if p < 0.05 else ""
    print(f"    {f:15s}: β={c:+.3f}  p={p:.3f} {sig}")
