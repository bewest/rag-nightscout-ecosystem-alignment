#!/usr/bin/env python3
"""EXP-2690: Multi-Channel Insulin Decomposition

Instead of analyzing bolus dose alone (confounded by controller co-intervention),
decompose the BG outcome into contributions from ALL insulin channels simultaneously.

The AID system delivers insulin through multiple channels:
  1. User bolus (correction or meal)
  2. Controller SMBs (micro-boluses)
  3. Net basal modulation (temp basals, suspend, increase)
  4. Prior insulin (IOB from earlier dosing)

Plus non-insulin factors:
  5. Starting BG (regression to mean)
  6. Glucose momentum (ROC)
  7. Carbohydrate absorption
  8. Time of day (circadian)

Multi-factor approach:
  - Panel 1: Correlation matrix of all predictors
  - Panel 2: Multiple regression: partial effects of each channel
  - Panel 3: Mixed-effects model (patient random intercept)
  - Panel 4: Variance decomposition: how much does each factor explain?
  - Panel 5: Controller-stratified partial effects
  - Panel 6: Interaction terms: do channels amplify/dampen each other?
  - Panel 7: Channel contribution over time (0-30, 30-60, 60-120 min)
"""

import json, pathlib, warnings
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy import stats

warnings.filterwarnings("ignore")
OUT = pathlib.Path("visualizations/multi-channel")
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
grid = grid.sort_values(["patient_id", "time"]).reset_index(drop=True)

FLOOR = 180
HORIZON = 24  # 2h in 5-min steps

# ── Extract multi-channel events ──────────────────────────────────────
print("Extracting multi-channel correction events (BG≥180)...")
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
    isf = pg["scheduled_isf"].values if "scheduled_isf" in pg.columns else np.full(len(pg), np.nan)
    cr = pg["scheduled_cr"].values if "scheduled_cr" in pg.columns else np.full(len(pg), np.nan)
    time_col = pg["time"].values

    eq_bg = np.nanmedian(glucose)

    for i in range(HORIZON, len(pg) - HORIZON):
        bg0 = glucose[i]
        if np.isnan(bg0) or bg0 < FLOOR:
            continue
        bg_2h = glucose[i + HORIZON]
        if np.isnan(bg_2h):
            continue

        # Check trajectory completeness
        traj = glucose[i:i + HORIZON + 1]
        if np.sum(np.isnan(traj)) > 6:
            continue

        # Multi-channel insulin over 2h window
        bolus_total = np.nansum(bolus[i:i + HORIZON])
        smb_total = np.nansum(smb[i:i + HORIZON])
        # Net basal integral (U over 2h) = sum of net_basal * (5/60) for each 5-min bin
        basal_integral = np.nansum(net_basal[i:i + HORIZON]) * (5.0 / 60.0)
        sched_integral = np.nansum(sched_basal[i:i + HORIZON]) * (5.0 / 60.0)
        # Excess basal = actual - scheduled (positive = controller adding, negative = suspending)
        excess_basal = basal_integral - sched_integral

        # Carbs
        carbs_2h = np.nansum(carbs_col[i:i + HORIZON])

        # IOB at start
        iob_start = iob[i]

        # Glucose ROC at start
        roc_start = roc[i]

        # Settings at event
        isf_at = isf[i]
        cr_at = cr[i]
        basal_at = sched_basal[i]

        # Time of day (hour, UTC)
        try:
            t = pd.Timestamp(time_col[i])
            if t.tzinfo is None:
                t = t.tz_localize("UTC")
            hour = t.hour + t.minute / 60.0
        except Exception:
            hour = np.nan

        # Intermediate BG points
        bg_30 = glucose[i + 6] if i + 6 < len(glucose) else np.nan
        bg_60 = glucose[i + 12] if i + 12 < len(glucose) else np.nan

        # Channel breakdown at sub-intervals
        bolus_0_60 = np.nansum(bolus[i:i + 12])
        smb_0_60 = np.nansum(smb[i:i + 12])
        bolus_60_120 = np.nansum(bolus[i + 12:i + HORIZON])
        smb_60_120 = np.nansum(smb[i + 12:i + HORIZON])

        events.append({
            "patient_id": pid, "controller": ctrl,
            "bg0": bg0, "bg_2h": bg_2h, "bg_drop": bg0 - bg_2h,
            "bg_30": bg_30, "bg_60": bg_60,
            "drop_0_60": bg0 - bg_60 if not np.isnan(bg_60) else np.nan,
            "drop_60_120": bg_60 - bg_2h if not np.isnan(bg_60) else np.nan,
            # Insulin channels
            "bolus_total": bolus_total,
            "smb_total": smb_total,
            "basal_integral": basal_integral,
            "excess_basal": excess_basal,
            "total_insulin": bolus_total + smb_total + basal_integral,
            "iob_start": iob_start,
            # Non-insulin
            "carbs_2h": carbs_2h,
            "roc_start": roc_start,
            "hour": hour,
            "eq_bg": eq_bg,
            "bg0_above_eq": bg0 - eq_bg,
            # Settings
            "isf": isf_at, "cr": cr_at, "basal_rate": basal_at,
            # Sub-intervals
            "bolus_0_60": bolus_0_60, "smb_0_60": smb_0_60,
            "bolus_60_120": bolus_60_120, "smb_60_120": smb_60_120,
        })

ev = pd.DataFrame(events)
print(f"  Total events: {len(ev)}")
for c in ["loop", "trio", "openaps"]:
    print(f"  {c}: {len(ev[ev['controller'] == c])}")

# ── Panel 1: Correlation matrix ───────────────────────────────────────
predictors = ["bg0", "bolus_total", "smb_total", "excess_basal", "iob_start",
              "carbs_2h", "roc_start", "bg0_above_eq", "total_insulin"]
target = "bg_drop"

fig, ax = plt.subplots(figsize=(12, 10))
cols = predictors + [target]
corr = ev[cols].corr()
im = ax.imshow(corr.values, cmap="RdBu_r", vmin=-1, vmax=1, aspect="auto")
ax.set_xticks(range(len(cols)))
ax.set_yticks(range(len(cols)))
ax.set_xticklabels(cols, rotation=45, ha="right", fontsize=9)
ax.set_yticklabels(cols, fontsize=9)
for i in range(len(cols)):
    for j in range(len(cols)):
        val = corr.values[i, j]
        ax.text(j, i, f"{val:.2f}", ha="center", va="center", fontsize=8,
               color="white" if abs(val) > 0.5 else "black")
plt.colorbar(im, ax=ax, label="Pearson r")
ax.set_title("EXP-2690: Correlation Matrix — All Channels + BG Drop", fontsize=13, fontweight="bold")
plt.tight_layout()
plt.savefig(OUT / "fig1_correlation_matrix.png", dpi=150)
plt.close()
print("Panel 1: Correlation matrix saved")

# ── Panel 2: Multiple regression — partial effects ───────────────────
from numpy.linalg import lstsq

fig, axes = plt.subplots(1, 2, figsize=(16, 6))

# Build design matrix with all channels
feature_names = ["bg0", "bolus_total", "smb_total", "excess_basal",
                 "iob_start", "carbs_2h", "roc_start"]
ev_clean = ev[feature_names + [target]].dropna()
X = ev_clean[feature_names].values
y = ev_clean[target].values

# Standardize for comparable coefficients
X_mean = X.mean(axis=0)
X_std = X.std(axis=0)
X_std[X_std == 0] = 1
X_norm = (X - X_mean) / X_std
X_norm = np.column_stack([X_norm, np.ones(len(X_norm))])  # intercept

beta, residuals, rank, sv = lstsq(X_norm, y, rcond=None)
y_pred = X_norm @ beta
ss_res = np.sum((y - y_pred) ** 2)
ss_tot = np.sum((y - y.mean()) ** 2)
r2 = 1 - ss_res / ss_tot

# Standardized coefficients (exclude intercept)
std_coefs = beta[:-1]
intercept = beta[-1]

# Standard errors via (X'X)^-1 * sigma^2
n, p = X_norm.shape
sigma2 = ss_res / (n - p)
try:
    cov_beta = sigma2 * np.linalg.inv(X_norm.T @ X_norm)
    se = np.sqrt(np.diag(cov_beta))[:-1]
    t_stats = std_coefs / se
    p_vals = 2 * (1 - stats.t.cdf(np.abs(t_stats), df=n - p))
except Exception:
    se = np.full(len(std_coefs), np.nan)
    p_vals = np.full(len(std_coefs), np.nan)

# 2a: Coefficient plot
colors_coef = ["C3" if p < 0.05 else "gray" for p in p_vals]
bars = axes[0].barh(range(len(feature_names)), std_coefs, color=colors_coef,
                    xerr=1.96 * se, capsize=4, edgecolor="k")
axes[0].set_yticks(range(len(feature_names)))
axes[0].set_yticklabels(feature_names)
axes[0].axvline(0, color="k", ls="--", alpha=0.5)
axes[0].set_xlabel("Standardized coefficient (effect on BG drop)")
axes[0].set_title(f"Multi-Channel Regression (R²={r2:.3f}, n={n})\nRed = p<0.05")

# 2b: Variance decomposition (sequential R² addition)
r2_sequential = []
for i in range(len(feature_names)):
    Xi = ev_clean[feature_names[:i + 1]].values
    Xi_n = (Xi - Xi.mean(axis=0)) / (Xi.std(axis=0) + 1e-10)
    Xi_n = np.column_stack([Xi_n, np.ones(len(Xi_n))])
    b, _, _, _ = lstsq(Xi_n, y, rcond=None)
    y_p = Xi_n @ b
    r2_i = 1 - np.sum((y - y_p) ** 2) / ss_tot
    r2_sequential.append(r2_i)

r2_marginal = [r2_sequential[0]] + [r2_sequential[i] - r2_sequential[i-1] for i in range(1, len(r2_sequential))]
axes[1].barh(range(len(feature_names)), r2_marginal, color="C0", edgecolor="k", alpha=0.7)
axes[1].set_yticks(range(len(feature_names)))
axes[1].set_yticklabels(feature_names)
axes[1].set_xlabel("Marginal R² contribution")
axes[1].set_title(f"Sequential Variance Decomposition\nTotal R²={r2:.3f}")

plt.suptitle("EXP-2690: Multi-Channel Partial Effects", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig(OUT / "fig2_partial_effects.png", dpi=150)
plt.close()
print(f"Panel 2: Partial effects saved (R²={r2:.3f})")

# ── Panel 3: Mixed effects (patient as grouping) ─────────────────────
# Approximate mixed-effects by adding patient dummies
fig, axes = plt.subplots(1, 2, figsize=(16, 6))

# Patient-demeaned regression (within-patient effects)
ev_dm = ev_clean.copy()
ev_dm["patient_id"] = ev[feature_names + [target]].dropna().index.map(lambda i: ev.loc[i, "patient_id"] if i in ev.index else None)
# Re-extract with patient_id
ev_full = ev[feature_names + [target, "patient_id"]].dropna()

# Demean within patient
for col in feature_names + [target]:
    ev_full[f"{col}_dm"] = ev_full.groupby("patient_id")[col].transform(lambda x: x - x.mean())

X_dm = ev_full[[f"{c}_dm" for c in feature_names]].values
y_dm = ev_full[f"{target}_dm"].values
X_dm_n = np.column_stack([X_dm, np.ones(len(X_dm))])

beta_dm, _, _, _ = lstsq(X_dm_n, y_dm, rcond=None)
y_pred_dm = X_dm_n @ beta_dm
r2_within = 1 - np.sum((y_dm - y_pred_dm) ** 2) / (np.sum((y_dm - y_dm.mean()) ** 2) + 1e-10)

# Standard errors for demeaned
n_dm, p_dm = X_dm_n.shape
sigma2_dm = np.sum((y_dm - y_pred_dm) ** 2) / max(n_dm - p_dm, 1)
try:
    cov_dm = sigma2_dm * np.linalg.inv(X_dm_n.T @ X_dm_n)
    se_dm = np.sqrt(np.diag(cov_dm))[:-1]
except Exception:
    se_dm = np.full(len(feature_names), np.nan)

std_dm = beta_dm[:-1]

# Between-patient: patient means
pat_means = ev_full.groupby("patient_id")[feature_names + [target]].mean()
if len(pat_means) >= 5:
    X_bp = pat_means[feature_names].values
    y_bp = pat_means[target].values
    X_bp_n = (X_bp - X_bp.mean(axis=0)) / (X_bp.std(axis=0) + 1e-10)
    X_bp_n = np.column_stack([X_bp_n, np.ones(len(X_bp_n))])
    beta_bp, _, _, _ = lstsq(X_bp_n, y_bp, rcond=None)
    y_pred_bp = X_bp_n @ beta_bp
    r2_between = 1 - np.sum((y_bp - y_pred_bp) ** 2) / (np.sum((y_bp - y_bp.mean()) ** 2) + 1e-10)
    std_bp = beta_bp[:-1]
else:
    r2_between = np.nan
    std_bp = np.full(len(feature_names), np.nan)

# Plot within vs between
x_pos = np.arange(len(feature_names))
width = 0.35
axes[0].barh(x_pos - width/2, std_dm, width, label=f"Within-patient (R²={r2_within:.3f})",
            color="C0", edgecolor="k", alpha=0.7, xerr=1.96*se_dm, capsize=3)
if not np.isnan(r2_between):
    axes[0].barh(x_pos + width/2, std_bp, width, label=f"Between-patient (R²={r2_between:.3f})",
                color="C1", edgecolor="k", alpha=0.7)
axes[0].set_yticks(x_pos)
axes[0].set_yticklabels(feature_names)
axes[0].axvline(0, color="k", ls="--", alpha=0.5)
axes[0].set_xlabel("Standardized coefficient")
axes[0].set_title("Within vs Between Patient Effects")
axes[0].legend(fontsize=9)

# 3b: Patient random intercepts
pat_intercepts = ev_full.groupby("patient_id")[target].mean().sort_values()
ctrl_colors = {"loop": "C0", "trio": "C1", "openaps": "C2"}
bar_colors = [ctrl_colors.get(ctrl_map.get(pid, ""), "gray") for pid in pat_intercepts.index]
axes[1].barh(range(len(pat_intercepts)), pat_intercepts.values, color=bar_colors, edgecolor="k", alpha=0.7)
axes[1].set_xlabel("Mean BG drop (mg/dL)")
axes[1].set_title("Patient Random Intercepts\n(mean BG drop per patient)")
axes[1].set_yticks(range(len(pat_intercepts)))
axes[1].set_yticklabels([p[:8] for p in pat_intercepts.index], fontsize=7)
from matplotlib.patches import Patch
legend_elements = [Patch(facecolor=c, label=l.upper()) for l, c in ctrl_colors.items()]
axes[1].legend(handles=legend_elements, fontsize=9)

plt.suptitle("EXP-2690: Within vs Between Patient Decomposition", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig(OUT / "fig3_mixed_effects.png", dpi=150)
plt.close()
print(f"Panel 3: Mixed effects saved (within R²={r2_within:.3f}, between R²={r2_between:.3f})")

# ── Panel 4: Unique variance per predictor (Type III) ─────────────────
fig, ax = plt.subplots(figsize=(10, 6))

# Type III: unique R² = full R² - R² without that predictor
unique_r2 = []
for i, fname in enumerate(feature_names):
    remaining = [f for j, f in enumerate(feature_names) if j != i]
    Xr = ev_clean[remaining].values
    Xr_n = (Xr - Xr.mean(axis=0)) / (Xr.std(axis=0) + 1e-10)
    Xr_n = np.column_stack([Xr_n, np.ones(len(Xr_n))])
    br, _, _, _ = lstsq(Xr_n, y, rcond=None)
    r2_without = 1 - np.sum((y - Xr_n @ br) ** 2) / ss_tot
    unique_r2.append(r2 - r2_without)

# Shared variance
total_unique = sum(unique_r2)
shared = r2 - total_unique
unexplained = 1 - r2

# Stacked bar: unique + shared + unexplained
colors_bar = plt.cm.Set2(np.linspace(0, 1, len(feature_names)))
bottom = 0
for i, (fname, ur) in enumerate(zip(feature_names, unique_r2)):
    ax.bar("Variance\nDecomposition", ur, bottom=bottom, color=colors_bar[i],
           label=f"{fname}: {ur:.4f}", edgecolor="k", linewidth=0.5)
    bottom += ur
ax.bar("Variance\nDecomposition", shared, bottom=bottom, color="lightgray",
       label=f"Shared: {shared:.4f}", edgecolor="k", linewidth=0.5)
bottom += shared
ax.bar("Variance\nDecomposition", unexplained, bottom=bottom, color="white",
       label=f"Unexplained: {unexplained:.4f}", edgecolor="k", linewidth=0.5)

ax.set_ylabel("Proportion of variance")
ax.set_title(f"Type III Unique Variance Decomposition (Total R²={r2:.3f})")
ax.legend(bbox_to_anchor=(1.02, 1), loc="upper left", fontsize=9)
ax.set_ylim(0, 1.05)

plt.tight_layout()
plt.savefig(OUT / "fig4_variance_decomposition.png", dpi=150)
plt.close()
print("Panel 4: Variance decomposition saved")

# ── Panel 5: Controller-stratified effects ────────────────────────────
fig, axes = plt.subplots(1, 3, figsize=(18, 6))
controllers = ["loop", "trio", "openaps"]

ctrl_results = {}
for ax, ctrl in zip(axes, controllers):
    ec = ev[ev["controller"] == ctrl]
    ec_clean = ec[feature_names + [target]].dropna()
    if len(ec_clean) < 50:
        ax.text(0.5, 0.5, f"{ctrl}: n={len(ec_clean)} (too few)", ha="center", transform=ax.transAxes)
        continue

    Xc = ec_clean[feature_names].values
    yc = ec_clean[target].values
    Xc_n = (Xc - Xc.mean(axis=0)) / (Xc.std(axis=0) + 1e-10)
    Xc_n = np.column_stack([Xc_n, np.ones(len(Xc_n))])
    bc, _, _, _ = lstsq(Xc_n, yc, rcond=None)
    yc_pred = Xc_n @ bc
    r2c = 1 - np.sum((yc - yc_pred) ** 2) / (np.sum((yc - yc.mean()) ** 2) + 1e-10)

    # SE
    nc = len(yc)
    sigma2c = np.sum((yc - yc_pred) ** 2) / max(nc - len(bc), 1)
    try:
        cov_c = sigma2c * np.linalg.inv(Xc_n.T @ Xc_n)
        se_c = np.sqrt(np.diag(cov_c))[:-1]
    except Exception:
        se_c = np.full(len(feature_names), np.nan)

    p_vals_c = []
    for coef, stderr in zip(bc[:-1], se_c):
        if stderr > 0 and not np.isnan(stderr):
            t_val = coef / stderr
            p_val = 2 * (1 - stats.t.cdf(abs(t_val), df=max(nc - len(bc), 1)))
        else:
            p_val = 1.0
        p_vals_c.append(p_val)

    colors_c = ["C3" if p < 0.05 else "gray" for p in p_vals_c]
    ax.barh(range(len(feature_names)), bc[:-1], color=colors_c,
            xerr=1.96 * se_c, capsize=3, edgecolor="k")
    ax.set_yticks(range(len(feature_names)))
    ax.set_yticklabels(feature_names, fontsize=9)
    ax.axvline(0, color="k", ls="--", alpha=0.5)
    ax.set_title(f"{ctrl.upper()} (n={nc}, R²={r2c:.3f})\nRed = p<0.05")
    ax.set_xlabel("Std. coefficient")

    ctrl_results[ctrl] = {
        "n": nc, "r2": float(r2c),
        "coefficients": {f: float(c) for f, c in zip(feature_names, bc[:-1])},
        "p_values": {f: float(p) for f, p in zip(feature_names, p_vals_c)},
    }

plt.suptitle("EXP-2690: Controller-Stratified Multi-Channel Effects", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig(OUT / "fig5_controller_stratified.png", dpi=150)
plt.close()
print("Panel 5: Controller-stratified effects saved")

# ── Panel 6: Interaction terms ────────────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 6))

# Test key interactions: bolus × smb, bolus × excess_basal
ev_int = ev_clean.copy()
ev_int["bolus_x_smb"] = ev_int["bolus_total"] * ev_int["smb_total"]
ev_int["bolus_x_basal"] = ev_int["bolus_total"] * ev_int["excess_basal"]
ev_int["smb_x_basal"] = ev_int["smb_total"] * ev_int["excess_basal"]

int_features = feature_names + ["bolus_x_smb", "bolus_x_basal", "smb_x_basal"]
Xi = ev_int[int_features].values
Xi_n = (Xi - Xi.mean(axis=0)) / (Xi.std(axis=0) + 1e-10)
Xi_n = np.column_stack([Xi_n, np.ones(len(Xi_n))])
bi, _, _, _ = lstsq(Xi_n, y, rcond=None)
yi_pred = Xi_n @ bi
r2_int = 1 - np.sum((y - yi_pred) ** 2) / ss_tot

# SE for interaction model
ni = len(y)
sigma2_i = np.sum((y - yi_pred) ** 2) / max(ni - len(bi), 1)
try:
    cov_i = sigma2_i * np.linalg.inv(Xi_n.T @ Xi_n)
    se_i = np.sqrt(np.diag(cov_i))[:-1]
except Exception:
    se_i = np.full(len(int_features), np.nan)

p_vals_i = []
for coef, stderr in zip(bi[:-1], se_i):
    if stderr > 0 and not np.isnan(stderr):
        t_val = coef / stderr
        p_val = 2 * (1 - stats.t.cdf(abs(t_val), df=max(ni - len(bi), 1)))
    else:
        p_val = 1.0
    p_vals_i.append(p_val)

colors_i = ["C3" if p < 0.05 else "gray" for p in p_vals_i]
axes[0].barh(range(len(int_features)), bi[:-1], color=colors_i,
            xerr=1.96 * se_i, capsize=3, edgecolor="k")
axes[0].set_yticks(range(len(int_features)))
axes[0].set_yticklabels(int_features, fontsize=9)
axes[0].axvline(0, color="k", ls="--", alpha=0.5)
axes[0].set_xlabel("Std. coefficient")
axes[0].set_title(f"With Interactions (R²={r2_int:.3f})\nΔR² from interactions: {r2_int - r2:.4f}")

# 6b: R² comparison
models = ["bg0 only", "All channels\n(additive)", "Channels +\ninteractions"]
r2_bg0 = 1 - np.sum((y - (np.polyval(np.polyfit(ev_clean["bg0"].values, y, 1), ev_clean["bg0"].values))) ** 2) / ss_tot
r2_vals = [r2_bg0, r2, r2_int]
bars = axes[1].bar(models, r2_vals, color=["C0", "C1", "C2"], edgecolor="k", alpha=0.7)
for bar, val in zip(bars, r2_vals):
    axes[1].text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.005,
                f"{val:.3f}", ha="center", fontsize=11)
axes[1].set_ylabel("R²")
axes[1].set_title("Model Comparison: Explained Variance")
axes[1].set_ylim(0, max(r2_vals) * 1.3)

plt.suptitle("EXP-2690: Channel Interactions", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig(OUT / "fig6_interactions.png", dpi=150)
plt.close()
print(f"Panel 6: Interactions saved (R² additive={r2:.3f}, with interactions={r2_int:.3f})")

# ── Panel 7: Time-resolved channel contributions ─────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 6))

# Compare first hour vs second hour
for ax_idx, (period, drop_col, bolus_col, smb_col) in enumerate([
    ("0-60 min", "drop_0_60", "bolus_0_60", "smb_0_60"),
    ("60-120 min", "drop_60_120", "bolus_60_120", "smb_60_120"),
]):
    ev_t = ev[[drop_col, bolus_col, smb_col, "bg0"]].dropna()
    if len(ev_t) < 50:
        continue

    Xt = ev_t[[bolus_col, smb_col, "bg0"]].values
    yt = ev_t[drop_col].values
    Xt_n = (Xt - Xt.mean(axis=0)) / (Xt.std(axis=0) + 1e-10)
    Xt_n = np.column_stack([Xt_n, np.ones(len(Xt_n))])
    bt, _, _, _ = lstsq(Xt_n, yt, rcond=None)
    yt_pred = Xt_n @ bt
    r2t = 1 - np.sum((yt - yt_pred) ** 2) / (np.sum((yt - yt.mean()) ** 2) + 1e-10)

    labels_t = [bolus_col, smb_col, "bg0"]
    axes[ax_idx].barh(range(3), bt[:-1], color=["C0", "C1", "C3"], edgecolor="k", alpha=0.7)
    axes[ax_idx].set_yticks(range(3))
    axes[ax_idx].set_yticklabels(labels_t)
    axes[ax_idx].axvline(0, color="k", ls="--", alpha=0.5)
    axes[ax_idx].set_xlabel("Std. coefficient")
    axes[ax_idx].set_title(f"{period} (R²={r2t:.3f})")

plt.suptitle("EXP-2690: Time-Resolved Channel Contributions", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig(OUT / "fig7_time_resolved.png", dpi=150)
plt.close()
print("Panel 7: Time-resolved saved")

# ── Save results ──────────────────────────────────────────────────────
results = {
    "experiment": "EXP-2690",
    "title": "Multi-Channel Insulin Decomposition",
    "n_events": int(len(ev)),
    "r2_bg0_only": float(r2_bg0),
    "r2_all_channels": float(r2),
    "r2_with_interactions": float(r2_int),
    "r2_within_patient": float(r2_within),
    "r2_between_patient": float(r2_between) if not np.isnan(r2_between) else None,
    "standardized_coefficients": {f: float(c) for f, c in zip(feature_names, std_coefs)},
    "p_values": {f: float(p) for f, p in zip(feature_names, p_vals)},
    "unique_r2": {f: float(u) for f, u in zip(feature_names, unique_r2)},
    "controller_stratified": ctrl_results,
}
(EXP / "exp-2690_multi_channel.json").write_text(json.dumps(results, indent=2))

print(f"""
{'='*60}
EXP-2690: Multi-Channel Insulin Decomposition — SUMMARY
{'='*60}

  Events: {len(ev)} (BG≥180, 2h horizon)

  MODEL COMPARISON:
    BG₀ only:            R² = {r2_bg0:.3f}
    All channels:        R² = {r2:.3f}
    Channels + interact: R² = {r2_int:.3f}
    Within-patient:      R² = {r2_within:.3f}

  STANDARDIZED PARTIAL EFFECTS (all-channel model):""")

for f, c, p in sorted(zip(feature_names, std_coefs, p_vals), key=lambda x: abs(x[1]), reverse=True):
    sig = "***" if p < 0.001 else "**" if p < 0.01 else "*" if p < 0.05 else ""
    print(f"    {f:20s}: β={c:+.3f}  p={p:.4f} {sig}")

print(f"""
  UNIQUE R² (Type III — variance uniquely explained by each):""")
for f, u in sorted(zip(feature_names, unique_r2), key=lambda x: x[1], reverse=True):
    print(f"    {f:20s}: {u:.4f}")

print(f"""
  CONTROLLER-STRATIFIED R²:""")
for ctrl, cr in ctrl_results.items():
    print(f"    {ctrl.upper():10s}: R²={cr['r2']:.3f} (n={cr['n']})")
