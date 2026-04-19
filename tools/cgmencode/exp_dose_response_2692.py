#!/usr/bin/env python3
"""EXP-2692: Per-Channel Dose-Response & Non-Linear Effects

Now that we know all insulin channels contribute (EXP-2690), characterize the
dose-response relationship for each channel:
  - Is it linear or is there diminishing returns?
  - What's the marginal BG drop per unit through each channel?
  - Do channels interact (amplify or dampen each other)?
  - Are there non-linear thresholds (e.g., minimum effective dose)?

Also tests whether a non-linear model (polynomial, quantile regression)
captures effects the linear model misses.

Panels:
  1. Per-channel dose-response curves (binned means + CI)
  2. Marginal effects: BG drop per unit insulin by channel
  3. Non-linearity test: quadratic terms
  4. Channel substitution: bolus vs SMB equivalence
  5. Quantile regression: effects at different BG drop percentiles
  6. Residual analysis: what predicts extreme outliers?
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
OUT = pathlib.Path("visualizations/dose-response")
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
HORIZON = 24

# ── Extract events (reuse EXP-2690 logic) ─────────────────────────────
print("Extracting multi-channel events...")
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

    for i in range(HORIZON, len(pg) - HORIZON):
        bg0 = glucose[i]
        if np.isnan(bg0) or bg0 < FLOOR:
            continue
        bg_2h = glucose[i + HORIZON]
        if np.isnan(bg_2h):
            continue
        traj = glucose[i:i + HORIZON + 1]
        if np.sum(np.isnan(traj)) > 6:
            continue

        bolus_total = np.nansum(bolus[i:i + HORIZON])
        smb_total = np.nansum(smb[i:i + HORIZON])
        basal_integral = np.nansum(net_basal[i:i + HORIZON]) * (5.0 / 60.0)
        sched_integral = np.nansum(sched_basal[i:i + HORIZON]) * (5.0 / 60.0)
        excess_basal = basal_integral - sched_integral
        carbs_2h = np.nansum(carbs_col[i:i + HORIZON])
        roc_start = roc[i]
        iob_start = iob[i]

        events.append({
            "patient_id": pid, "controller": ctrl,
            "bg0": bg0, "bg_2h": bg_2h, "bg_drop": bg0 - bg_2h,
            "bolus_total": bolus_total, "smb_total": smb_total,
            "excess_basal": excess_basal, "basal_integral": basal_integral,
            "total_insulin": bolus_total + smb_total + basal_integral,
            "carbs_2h": carbs_2h, "roc_start": roc_start, "iob_start": iob_start,
        })

ev = pd.DataFrame(events)
print(f"  Events: {len(ev)}")

controllers = ["loop", "trio", "openaps"]
colors = {"loop": "C0", "trio": "C1", "openaps": "C2"}

# ── Panel 1: Per-channel dose-response curves ─────────────────────────
fig, axes = plt.subplots(2, 3, figsize=(18, 10))

channels = [
    ("bolus_total", "User Bolus (U)", (0, 15)),
    ("smb_total", "SMB Total (U)", (0, 8)),
    ("excess_basal", "Excess Basal (U)", (-2, 4)),
    ("total_insulin", "Total Insulin (U)", (0, 20)),
    ("carbs_2h", "Carbs (g)", (0, 80)),
    ("iob_start", "IOB at Start (U)", (-2, 10)),
]

for idx, (col, label, xlim) in enumerate(channels):
    ax = axes[idx // 3][idx % 3]

    for ctrl in controllers:
        ec = ev[ev["controller"] == ctrl]
        valid = ec[[col, "bg_drop"]].dropna()
        valid = valid[(valid[col] >= xlim[0]) & (valid[col] <= xlim[1])]
        if len(valid) < 50:
            continue

        # Binned means with CI
        try:
            bins = pd.qcut(valid[col], 10, duplicates="drop")
            binned = valid.groupby(bins).agg(
                mean_drop=("bg_drop", "mean"),
                se=("bg_drop", "sem"),
                n=("bg_drop", "count"),
            )
            bin_centers = [interval.mid for interval in binned.index]
            ax.errorbar(bin_centers, binned["mean_drop"].values,
                       yerr=1.96 * binned["se"].values,
                       fmt="o-", color=colors[ctrl], lw=1.5, capsize=3,
                       markersize=4, label=ctrl.upper())
        except Exception:
            pass

    ax.set_xlabel(label)
    ax.set_ylabel("Mean BG drop (mg/dL)")
    ax.set_title(f"Dose-Response: {label}")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

plt.suptitle("EXP-2692: Per-Channel Dose-Response Curves", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig(OUT / "fig1_dose_response.png", dpi=150)
plt.close()
print("Panel 1: Dose-response curves saved")

# ── Panel 2: Marginal effects (partial derivative from regression) ────
fig, axes = plt.subplots(1, 2, figsize=(14, 6))

feature_names = ["bg0", "bolus_total", "smb_total", "excess_basal",
                 "iob_start", "carbs_2h", "roc_start"]
ev_clean = ev[feature_names + ["bg_drop"]].dropna()
X = ev_clean[feature_names].values
y = ev_clean["bg_drop"].values

# Raw (unstandardized) coefficients = marginal effects
X_aug = np.column_stack([X, np.ones(len(X))])
beta_raw, _, _, _ = lstsq(X_aug, y, rcond=None)

# 2a: Marginal effect per unit
insulin_channels = ["bolus_total", "smb_total", "excess_basal"]
marginal = {f: beta_raw[i] for i, f in enumerate(feature_names)}

channel_labels = ["Bolus\n(per 1U)", "SMB\n(per 1U)", "Excess Basal\n(per 1U)"]
channel_effects = [marginal[c] for c in insulin_channels]

bars = axes[0].bar(channel_labels, channel_effects, color=["C0", "C1", "C2"],
                   edgecolor="k", alpha=0.7)
for bar, val in zip(bars, channel_effects):
    axes[0].text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.2,
                f"{val:.1f}", ha="center", fontsize=11)
axes[0].set_ylabel("BG drop per 1U insulin (mg/dL)")
axes[0].set_title("Marginal Effect: BG Drop per Unit Insulin")
axes[0].axhline(0, color="k", ls="--", alpha=0.5)
axes[0].grid(True, alpha=0.3, axis="y")

# 2b: Per controller
ctrl_marginals = {}
for ctrl in controllers:
    ec = ev[ev["controller"] == ctrl]
    ec_clean = ec[feature_names + ["bg_drop"]].dropna()
    if len(ec_clean) < 100:
        continue
    Xc = ec_clean[feature_names].values
    yc = ec_clean["bg_drop"].values
    Xc_aug = np.column_stack([Xc, np.ones(len(Xc))])
    bc, _, _, _ = lstsq(Xc_aug, yc, rcond=None)
    ctrl_marginals[ctrl] = {f: bc[i] for i, f in enumerate(feature_names)}

x_pos = np.arange(len(insulin_channels))
width = 0.25
for i, ctrl in enumerate(controllers):
    if ctrl in ctrl_marginals:
        vals = [ctrl_marginals[ctrl][c] for c in insulin_channels]
        axes[1].bar(x_pos + i * width, vals, width, label=ctrl.upper(),
                   color=colors[ctrl], edgecolor="k", alpha=0.7)

axes[1].set_xticks(x_pos + width)
axes[1].set_xticklabels(insulin_channels, fontsize=9)
axes[1].set_ylabel("BG drop per 1U (mg/dL)")
axes[1].set_title("Marginal Effects by Controller")
axes[1].legend()
axes[1].axhline(0, color="k", ls="--", alpha=0.5)
axes[1].grid(True, alpha=0.3, axis="y")

plt.suptitle("EXP-2692: Marginal Effects Per Unit Insulin", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig(OUT / "fig2_marginal_effects.png", dpi=150)
plt.close()
print("Panel 2: Marginal effects saved")

# ── Panel 3: Non-linearity test (quadratic terms) ────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 6))

# Add quadratic terms for insulin channels
ev_quad = ev_clean.copy()
for c in insulin_channels:
    ev_quad[f"{c}_sq"] = ev_quad[c] ** 2

quad_features = feature_names + [f"{c}_sq" for c in insulin_channels]
Xq = ev_quad[quad_features].values
Xq_n = (Xq - Xq.mean(axis=0)) / (Xq.std(axis=0) + 1e-10)
Xq_n = np.column_stack([Xq_n, np.ones(len(Xq_n))])
bq, _, _, _ = lstsq(Xq_n, y, rcond=None)
yq_pred = Xq_n @ bq
r2_quad = 1 - np.sum((y - yq_pred) ** 2) / np.sum((y - y.mean()) ** 2)

# Linear model R²
X_n = (X - X.mean(axis=0)) / (X.std(axis=0) + 1e-10)
X_n = np.column_stack([X_n, np.ones(len(X_n))])
bl, _, _, _ = lstsq(X_n, y, rcond=None)
yl_pred = X_n @ bl
r2_linear = 1 - np.sum((y - yl_pred) ** 2) / np.sum((y - y.mean()) ** 2)

# F-test for quadratic improvement
n_obs = len(y)
p_linear = len(feature_names) + 1
p_quad = len(quad_features) + 1
ss_res_linear = np.sum((y - yl_pred) ** 2)
ss_res_quad = np.sum((y - yq_pred) ** 2)
f_stat = ((ss_res_linear - ss_res_quad) / (p_quad - p_linear)) / (ss_res_quad / (n_obs - p_quad))
f_p = 1 - stats.f.cdf(f_stat, p_quad - p_linear, n_obs - p_quad)

# 3a: R² comparison
models = ["Linear\n(7 features)", "Linear +\nQuadratic\n(10 features)"]
r2_vals = [r2_linear, r2_quad]
bars = axes[0].bar(models, r2_vals, color=["C0", "C1"], edgecolor="k", alpha=0.7)
for bar, val in zip(bars, r2_vals):
    axes[0].text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.003,
                f"{val:.4f}", ha="center", fontsize=11)
axes[0].set_ylabel("R²")
axes[0].set_title(f"Linear vs Quadratic Model\nF={f_stat:.1f}, p={f_p:.2e}")

# 3b: Quadratic coefficients
quad_names = [f"{c}_sq" for c in insulin_channels]
quad_coefs = bq[len(feature_names):len(feature_names) + len(quad_names)]

# SE for quadratic terms
sigma2q = ss_res_quad / max(n_obs - p_quad, 1)
try:
    cov_q = sigma2q * np.linalg.inv(Xq_n.T @ Xq_n)
    se_q = np.sqrt(np.diag(cov_q))[len(feature_names):len(feature_names) + len(quad_names)]
except Exception:
    se_q = np.full(len(quad_names), np.nan)

p_vals_q = []
for c, s in zip(quad_coefs, se_q):
    if s > 0 and not np.isnan(s):
        t = c / s
        p_vals_q.append(2 * (1 - stats.t.cdf(abs(t), df=max(n_obs - p_quad, 1))))
    else:
        p_vals_q.append(1.0)

col_q = ["C3" if p < 0.05 else "gray" for p in p_vals_q]
axes[1].barh(range(len(quad_names)), quad_coefs, color=col_q,
            xerr=1.96 * se_q, capsize=4, edgecolor="k")
axes[1].set_yticks(range(len(quad_names)))
axes[1].set_yticklabels(quad_names)
axes[1].axvline(0, color="k", ls="--", alpha=0.5)
axes[1].set_xlabel("Quadratic coefficient (std)")
axes[1].set_title("Quadratic Terms (negative = diminishing returns)")
for i, (c, p) in enumerate(zip(quad_coefs, p_vals_q)):
    axes[1].text(0.95, i, f"p={p:.3f}", transform=axes[1].get_yaxis_transform(),
                ha="right", va="center", fontsize=9)

plt.suptitle("EXP-2692: Non-Linearity Test", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig(OUT / "fig3_nonlinearity.png", dpi=150)
plt.close()
print(f"Panel 3: Non-linearity saved (linear R²={r2_linear:.4f}, quad R²={r2_quad:.4f})")

# ── Panel 4: Channel substitution ─────────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 6))

# How many units of SMB equal 1 unit of bolus?
# From the marginal effects: drop_per_bolus / drop_per_smb
bolus_per_u = marginal["bolus_total"]
smb_per_u = marginal["smb_total"]
basal_per_u = marginal["excess_basal"]

# 4a: Equivalence ratios
if smb_per_u != 0:
    bolus_smb_ratio = bolus_per_u / smb_per_u
else:
    bolus_smb_ratio = np.nan
if basal_per_u != 0:
    bolus_basal_ratio = bolus_per_u / basal_per_u
else:
    bolus_basal_ratio = np.nan

labels = ["Bolus\n(reference)", "SMB\n(equivalence)", "Excess Basal\n(equivalence)"]
values = [1.0, 1.0 / bolus_smb_ratio if not np.isnan(bolus_smb_ratio) else 0,
          1.0 / bolus_basal_ratio if not np.isnan(bolus_basal_ratio) else 0]
bars = axes[0].bar(labels, values, color=["C0", "C1", "C2"], edgecolor="k", alpha=0.7)
for bar, val in zip(bars, values):
    axes[0].text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.05,
                f"{val:.2f}U", ha="center", fontsize=11)
axes[0].set_ylabel("Units needed for 1U bolus equivalent effect")
axes[0].set_title("Channel Substitution Ratios")
axes[0].grid(True, alpha=0.3, axis="y")

# 4b: Total insulin composition by controller
ctrl_composition = []
for ctrl in controllers:
    ec = ev[ev["controller"] == ctrl]
    ctrl_composition.append({
        "controller": ctrl.upper(),
        "bolus": ec["bolus_total"].mean(),
        "smb": ec["smb_total"].mean(),
        "basal": ec["basal_integral"].mean(),
    })

cc = pd.DataFrame(ctrl_composition).set_index("controller")
cc.plot(kind="barh", stacked=True, ax=axes[1], color=["C0", "C1", "C2"],
        edgecolor="k", alpha=0.7)
axes[1].set_xlabel("Mean 2h insulin (U)")
axes[1].set_title("Insulin Channel Composition by Controller")
axes[1].legend(title="Channel")

plt.suptitle("EXP-2692: Channel Substitution Analysis", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig(OUT / "fig4_substitution.png", dpi=150)
plt.close()
print("Panel 4: Substitution saved")

# ── Panel 5: Residual analysis ────────────────────────────────────────
fig, axes = plt.subplots(1, 3, figsize=(16, 5))

residuals = y - yl_pred

# 5a: Residual distribution
axes[0].hist(residuals, bins=80, color="C0", alpha=0.7, edgecolor="k", density=True)
axes[0].set_xlabel("Residual (mg/dL)")
axes[0].set_ylabel("Density")
axes[0].set_title(f"Residual Distribution\nSD={np.std(residuals):.1f}, Skew={stats.skew(residuals):.2f}")

# 5b: Residuals vs fitted
axes[1].scatter(yl_pred, residuals, alpha=0.02, s=3, color="C0")
axes[1].axhline(0, color="k", ls="--")
axes[1].set_xlabel("Fitted BG drop (mg/dL)")
axes[1].set_ylabel("Residual")
axes[1].set_title("Residuals vs Fitted")

# 5c: What predicts extreme residuals?
extreme_high = ev_clean.iloc[residuals > np.percentile(residuals, 95)]
extreme_low = ev_clean.iloc[residuals < np.percentile(residuals, 5)]

compare_cols = ["bg0", "bolus_total", "smb_total", "excess_basal", "carbs_2h"]
comparison = pd.DataFrame({
    "Feature": compare_cols,
    "Top 5%\n(dropped much more)": [extreme_high[c].mean() for c in compare_cols],
    "Bottom 5%\n(dropped much less)": [extreme_low[c].mean() for c in compare_cols],
    "All events": [ev_clean[c].mean() for c in compare_cols],
})

axes[2].axis("off")
table = axes[2].table(
    cellText=comparison.round(1).values.tolist(),
    colLabels=comparison.columns.tolist(),
    loc="center", cellLoc="center",
)
table.auto_set_font_size(False)
table.set_fontsize(9)
table.scale(1.2, 1.8)
axes[2].set_title("Extreme Residuals Characterization")

plt.suptitle("EXP-2692: Residual Analysis", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig(OUT / "fig5_residuals.png", dpi=150)
plt.close()
print("Panel 5: Residual analysis saved")

# ── Panel 6: Controller-specific dose-response ───────────────────────
fig, axes = plt.subplots(1, 3, figsize=(18, 5))

for ax, ctrl in zip(axes, controllers):
    ec = ev[ev["controller"] == ctrl]
    for col, label, color in [("bolus_total", "Bolus", "C0"),
                                ("smb_total", "SMB", "C1"),
                                ("excess_basal", "Excess Basal", "C2")]:
        valid = ec[[col, "bg_drop", "bg0"]].dropna()
        if len(valid) < 50:
            continue
        # Residualize out bg0 effect
        bg0_slope = np.polyfit(valid["bg0"], valid["bg_drop"], 1)
        resid_drop = valid["bg_drop"] - np.polyval(bg0_slope, valid["bg0"])
        try:
            bins = pd.qcut(valid[col], 8, duplicates="drop")
            binned_resid = pd.Series(resid_drop.values).groupby(bins.values).agg(["mean", "sem"])
            bin_centers = [interval.mid for interval in binned_resid.index]
            ax.errorbar(bin_centers, binned_resid["mean"].values,
                       yerr=1.96 * binned_resid["sem"].values,
                       fmt="o-", color=color, lw=1.5, capsize=3, markersize=4, label=label)
        except Exception:
            pass

    ax.set_xlabel("Insulin (U)")
    ax.set_ylabel("BG drop residual (BG₀ removed)")
    ax.set_title(f"{ctrl.upper()}: Dose-Response\n(BG₀ effect removed)")
    ax.legend(fontsize=9)
    ax.axhline(0, color="k", ls=":", alpha=0.5)
    ax.grid(True, alpha=0.3)

plt.suptitle("EXP-2692: BG₀-Adjusted Dose-Response by Controller", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig(OUT / "fig6_adjusted_dose_response.png", dpi=150)
plt.close()
print("Panel 6: Adjusted dose-response saved")

# ── Save results ──────────────────────────────────────────────────────
results = {
    "experiment": "EXP-2692",
    "title": "Per-Channel Dose-Response & Non-Linear Effects",
    "n_events": int(len(ev)),
    "marginal_effects_per_unit": {
        "bolus": float(bolus_per_u),
        "smb": float(smb_per_u),
        "excess_basal": float(basal_per_u),
        "bg0": float(marginal["bg0"]),
        "carbs": float(marginal["carbs_2h"]),
        "roc": float(marginal["roc_start"]),
    },
    "substitution_ratios": {
        "smb_per_bolus_equivalent": float(1.0 / bolus_smb_ratio) if not np.isnan(bolus_smb_ratio) else None,
        "excess_basal_per_bolus_equivalent": float(1.0 / bolus_basal_ratio) if not np.isnan(bolus_basal_ratio) else None,
    },
    "r2_linear": float(r2_linear),
    "r2_quadratic": float(r2_quad),
    "quadratic_f_test": {"F": float(f_stat), "p": float(f_p)},
    "controller_marginals": {c: {k: float(v) for k, v in m.items()} for c, m in ctrl_marginals.items()},
    "residual_sd": float(np.std(residuals)),
}
(EXP / "exp-2692_dose_response.json").write_text(json.dumps(results, indent=2))

print(f"""
{'='*60}
EXP-2692: Per-Channel Dose-Response — SUMMARY
{'='*60}

  Events: {len(ev)}

  MARGINAL EFFECTS (BG drop per 1U insulin):
    Bolus:        {bolus_per_u:+.2f} mg/dL per U
    SMB:          {smb_per_u:+.2f} mg/dL per U
    Excess basal: {basal_per_u:+.2f} mg/dL per U

  SUBSTITUTION RATIOS (units needed for 1U bolus equivalent):
    SMB: {1.0/bolus_smb_ratio:.2f}U = 1U bolus
    Excess basal: {1.0/bolus_basal_ratio:.2f}U = 1U bolus

  NON-LINEARITY:
    Linear R²:    {r2_linear:.4f}
    Quadratic R²: {r2_quad:.4f}
    F-test: F={f_stat:.1f}, p={f_p:.2e}

  PER-CONTROLLER MARGINALS (BG drop per 1U bolus):""")
for ctrl, m in ctrl_marginals.items():
    print(f"    {ctrl.upper()}: bolus={m['bolus_total']:+.2f}, smb={m['smb_total']:+.2f}, excess_basal={m['excess_basal']:+.2f}")
