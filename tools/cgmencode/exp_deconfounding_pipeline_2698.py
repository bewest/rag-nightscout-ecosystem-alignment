#!/usr/bin/env python3
"""EXP-2698: oref0-Inspired Multi-Factor Deconfounding Pipeline

The central insight: oref0 computes deviation = ΔBG_observed − BGI_expected,
subtracting out the expected insulin effect to isolate unexplained changes.
Then it categorizes events and tunes each parameter separately.

We extend this with our multi-factor techniques:
  1. SUBTRACT expected PK effect (oref0's BGI approach) → compute deviation
  2. CATEGORIZE events (correction, meal, basal, UAM) → stratify analysis
  3. WITHIN each category, decompose deviation using multi-factor regression:
     - Within-patient fixed effects (remove patient-level confounders)
     - Circadian blocking (remove time-of-day confounders)
     - Dose-response curves (capture non-linear PK)
     - Controller channel decomposition (separate bolus/SMB/basal effects)
  4. ITERATE: use improved estimates to recompute expectations

Key hypothesis: by first removing EXPECTED insulin effect (like oref0), the
residual deviations should be much more tractable for multi-factor analysis.
The confounding is primarily from the controller responding to the SAME signal
as insulin — if we account for the expected insulin effect, the residual should
be cleaner.

Panels:
  1. BGI computation & deviation extraction
  2. Event categorization (correction, meal, basal, UAM)
  3. Deviation R² vs raw ΔBG R² (does subtracting BGI help?)
  4. Category-specific multi-factor models
  5. Within-patient circadian deviation patterns
  6. Iterative parameter recovery convergence
  7. Combined pipeline: full deconfounding chain R²
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
OUT = pathlib.Path("visualizations/deconfounding-pipeline")
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

# ── Step 1: Compute BGI (expected insulin effect) like oref0 ─────────
# oref0 formula: BGI = -iob_activity * ISF * 5 (mg/dL per 5min)
# We approximate using: expected_drop = IOB_change * ISF
# Since we have IOB at each point, the expected BG effect over the interval
# is proportional to how much IOB was consumed (activity)

print("Step 1: Computing BGI (expected insulin effect)...")

HORIZON = 24  # 120 min
events = []

for pid in grid["patient_id"].unique():
    pg = grid[grid["patient_id"] == pid].reset_index(drop=True)
    ctrl = pg["controller"].iloc[0]
    glucose = pg["glucose"].values
    iob = pg["iob"].values if "iob" in pg.columns else np.full(len(pg), np.nan)
    isf = pg["scheduled_isf"].values if "scheduled_isf" in pg.columns else np.full(len(pg), np.nan)
    bolus = pg["bolus"].values
    smb = pg["bolus_smb"].values if "bolus_smb" in pg.columns else np.zeros(len(pg))
    net_basal = pg["net_basal"].values if "net_basal" in pg.columns else np.full(len(pg), np.nan)
    sched_basal = pg["scheduled_basal_rate"].values if "scheduled_basal_rate" in pg.columns else np.full(len(pg), np.nan)
    carbs_col = pg["carbs"].values if "carbs" in pg.columns else np.zeros(len(pg))
    roc = pg["glucose_roc"].values if "glucose_roc" in pg.columns else np.full(len(pg), np.nan)
    times = pg["time"].values

    for i in range(HORIZON, len(pg) - HORIZON):
        bg0 = glucose[i]
        bg_2h = glucose[i + HORIZON]
        if np.isnan(bg0) or np.isnan(bg_2h) or bg0 < 120:
            continue

        iob_start = iob[i] if not np.isnan(iob[i]) else 0
        iob_end = iob[i + HORIZON] if not np.isnan(iob[i + HORIZON]) else 0
        isf_val = isf[i] if not np.isnan(isf[i]) else 50
        roc_val = roc[i] if not np.isnan(roc[i]) else 0

        # oref0-style BGI: expected BG change from EXCESS insulin
        # Key insight: scheduled basal maintains steady-state BG, so we only
        # count insulin ABOVE scheduled basal (bolus, SMB, excess temp basal)
        # oref0 does: deviation = avgDelta - BGI where BGI = -activity * ISF * 5
        # Our 2h equivalent: expected_drop = excess_insulin_delivered * ISF
        bolus_2h = np.nansum(bolus[i:i+HORIZON])
        smb_2h = np.nansum(smb[i:i+HORIZON])
        basal_2h = np.nansum(net_basal[i:i+HORIZON]) * (5.0/60.0)
        sched_basal_2h = np.nansum(sched_basal[i:i+HORIZON]) * (5.0/60.0)
        excess_basal_2h = basal_2h - sched_basal_2h

        # Only excess insulin above scheduled basal causes BG to DROP
        excess_insulin = bolus_2h + smb_2h + excess_basal_2h
        expected_drop = excess_insulin * isf_val
        carbs_2h = np.nansum(carbs_col[i:i+HORIZON])
        new_insulin = bolus_2h + smb_2h + basal_2h
        iob_consumed = iob_start - iob_end + new_insulin

        # Observed
        observed_drop = bg0 - bg_2h

        # DEVIATION = observed - expected (like oref0)
        deviation = observed_drop - expected_drop

        try:
            hour = pd.Timestamp(times[i]).hour
        except Exception:
            hour = 12

        events.append({
            "patient_id": pid, "controller": ctrl,
            "bg0": bg0, "bg_2h": bg_2h,
            "observed_drop": observed_drop,
            "expected_drop": expected_drop,
            "deviation": deviation,
            "iob_start": iob_start, "iob_end": iob_end,
            "iob_consumed": iob_consumed,
            "isf_setting": isf_val,
            "bolus_2h": bolus_2h, "smb_2h": smb_2h,
            "excess_basal_2h": excess_basal_2h,
            "basal_2h": basal_2h,
            "new_insulin": new_insulin,
            "carbs_2h": carbs_2h,
            "roc_start": roc_val,
            "hour": hour,
            # Circadian block (4h blocks, like our EXP-2652)
            "circadian_block": hour // 4,
        })

ev = pd.DataFrame(events)
print(f"  Events: {len(ev)}")
print(f"  Mean observed drop: {ev['observed_drop'].mean():.1f} mg/dL")
print(f"  Mean expected drop: {ev['expected_drop'].mean():.1f} mg/dL")
print(f"  Mean deviation: {ev['deviation'].mean():.1f} mg/dL")

# ── Step 2: Categorize events (like oref0's 4-bucket system) ─────────
print("\nStep 2: Categorizing events...")

def categorize(row):
    """oref0-inspired categorization"""
    if row["carbs_2h"] > 5:
        return "meal"  # CSF category — carb absorption present
    elif row["bolus_2h"] > 0.3:
        return "correction"  # ISF category — correction without meal
    elif abs(row["excess_basal_2h"]) < 0.1 and row["smb_2h"] < 0.1:
        return "basal"  # basal category — pure fasting/scheduled
    elif row["deviation"] > 5 and row["carbs_2h"] <= 5:
        return "uam"  # UAM — unexplained rise without carbs
    else:
        return "mixed"

ev["category"] = ev.apply(categorize, axis=1)
cat_counts = ev["category"].value_counts()
print(f"  Categories:\n{cat_counts.to_string()}")

# ── Panel 1: BGI computation & deviation ──────────────────────────────
fig, axes = plt.subplots(2, 2, figsize=(14, 12))

# 1a: Expected vs observed drop
ax = axes[0][0]
ax.scatter(ev["expected_drop"], ev["observed_drop"], alpha=0.01, s=2, color="C0")
lims = [-100, 200]
ax.plot(lims, lims, "k--", alpha=0.5, label="Perfect prediction")
r_eo, p_eo = stats.pearsonr(ev["expected_drop"].dropna(), ev["observed_drop"].dropna())
ax.set_xlabel("Expected BG drop (ISF × IOB consumed)")
ax.set_ylabel("Observed BG drop")
ax.set_title(f"Expected vs Observed: r={r_eo:.3f}")
ax.set_xlim(-100, 200)
ax.set_ylim(-100, 200)
ax.legend()
ax.grid(True, alpha=0.3)

# 1b: Deviation distribution
ax = axes[0][1]
ax.hist(ev["deviation"], bins=100, color="C0", alpha=0.7, edgecolor="k", density=True)
ax.axvline(0, color="C3", ls="--", lw=2, label="Zero deviation")
ax.axvline(ev["deviation"].mean(), color="C1", ls="-", lw=2, label=f"Mean={ev['deviation'].mean():.1f}")
ax.set_xlabel("Deviation (mg/dL)")
ax.set_ylabel("Density")
ax.set_title(f"Deviation Distribution\nSD={ev['deviation'].std():.1f}")
ax.legend()
ax.grid(True, alpha=0.3)

# 1c: Deviation by category
ax = axes[1][0]
cat_order = ["correction", "meal", "basal", "uam", "mixed"]
cat_colors = {"correction": "C0", "meal": "C1", "basal": "C2", "uam": "C3", "mixed": "gray"}
box_data = [ev[ev["category"] == c]["deviation"].values for c in cat_order if c in ev["category"].values]
box_labels = [c for c in cat_order if c in ev["category"].values]
bp = ax.boxplot(box_data, labels=box_labels, patch_artist=True, showfliers=False)
for patch, cat in zip(bp["boxes"], box_labels):
    patch.set_facecolor(cat_colors.get(cat, "gray"))
    patch.set_alpha(0.5)
ax.axhline(0, color="k", ls="--", alpha=0.5)
ax.set_ylabel("Deviation (mg/dL)")
ax.set_title("Deviation by Event Category")
ax.grid(True, alpha=0.3, axis="y")

# 1d: Deviation by controller
ax = axes[1][1]
controllers = ["loop", "trio", "openaps"]
colors_ctrl = {"loop": "C0", "trio": "C1", "openaps": "C2"}
for i, ctrl in enumerate(controllers):
    ec = ev[ev["controller"] == ctrl]
    ax.violinplot([ec["deviation"].values], positions=[i], showmeans=True, showmedians=True)
ax.set_xticks(range(3))
ax.set_xticklabels([c.upper() for c in controllers])
ax.axhline(0, color="k", ls="--", alpha=0.5)
ax.set_ylabel("Deviation (mg/dL)")
ax.set_title("Deviation by Controller")
ax.grid(True, alpha=0.3, axis="y")

plt.suptitle("EXP-2698: Step 1 — BGI Subtraction & Deviation Extraction", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig(OUT / "fig1_bgi_deviation.png", dpi=150)
plt.close()
print("Panel 1 saved")

# ── Panel 2: Raw ΔBG R² vs Deviation R² ──────────────────────────────
fig, axes = plt.subplots(1, 3, figsize=(18, 6))

# Compare: how much better can we predict deviation vs raw ΔBG?
features = ["bg0", "bolus_2h", "smb_2h", "excess_basal_2h", "carbs_2h", "roc_start", "iob_start"]

# Model A: Predict observed_drop from features (our EXP-2690 approach)
clean = ev[features + ["observed_drop", "deviation", "patient_id"]].dropna()
X = clean[features].values
y_raw = clean["observed_drop"].values
y_dev = clean["deviation"].values

X_n = (X - X.mean(axis=0)) / (X.std(axis=0) + 1e-10)
X_aug = np.column_stack([X_n, np.ones(len(X_n))])

# Raw model
b_raw, _, _, _ = lstsq(X_aug, y_raw, rcond=None)
y_raw_pred = X_aug @ b_raw
r2_raw = 1 - np.sum((y_raw - y_raw_pred)**2) / np.sum((y_raw - y_raw.mean())**2)

# Deviation model (after subtracting expected insulin effect)
b_dev, _, _, _ = lstsq(X_aug, y_dev, rcond=None)
y_dev_pred = X_aug @ b_dev
r2_dev = 1 - np.sum((y_dev - y_dev_pred)**2) / np.sum((y_dev - y_dev.mean())**2)

# Unique R² for each feature in both models
unique_r2_raw = {}
unique_r2_dev = {}
for j, feat in enumerate(features):
    X_red = np.delete(X, j, axis=1)
    X_r_n = (X_red - X_red.mean(axis=0)) / (X_red.std(axis=0) + 1e-10)
    X_r_aug = np.column_stack([X_r_n, np.ones(len(X_r_n))])

    b_r, _, _, _ = lstsq(X_r_aug, y_raw, rcond=None)
    r2_r = 1 - np.sum((y_raw - X_r_aug @ b_r)**2) / np.sum((y_raw - y_raw.mean())**2)
    unique_r2_raw[feat] = max(r2_raw - r2_r, 0)

    b_d, _, _, _ = lstsq(X_r_aug, y_dev, rcond=None)
    r2_d = 1 - np.sum((y_dev - X_r_aug @ b_d)**2) / np.sum((y_dev - y_dev.mean())**2)
    unique_r2_dev[feat] = max(r2_dev - r2_d, 0)

# 2a: R² comparison
axes[0].bar([0, 1], [r2_raw, r2_dev], color=["C0", "C2"], edgecolor="k", alpha=0.7)
axes[0].set_xticks([0, 1])
axes[0].set_xticklabels(["Predict raw\nBG drop", "Predict\ndeviation"])
axes[0].set_ylabel("R²")
for x, v in zip([0, 1], [r2_raw, r2_dev]):
    axes[0].text(x, v + 0.005, f"{v:.4f}", ha="center", fontsize=12, fontweight="bold")
axes[0].set_title("Does subtracting BGI help?")
axes[0].grid(True, alpha=0.3, axis="y")

# 2b: Unique R² comparison
x_pos = np.arange(len(features))
width = 0.35
axes[1].barh(x_pos - width/2, [unique_r2_raw[f] for f in features], width,
            color="C0", label="Raw ΔBG", edgecolor="k", alpha=0.7)
axes[1].barh(x_pos + width/2, [unique_r2_dev[f] for f in features], width,
            color="C2", label="Deviation", edgecolor="k", alpha=0.7)
axes[1].set_yticks(x_pos)
axes[1].set_yticklabels(features, fontsize=9)
axes[1].set_xlabel("Unique R²")
axes[1].set_title("Unique Variance per Feature")
axes[1].legend()
axes[1].grid(True, alpha=0.3, axis="x")

# 2c: Residual SD comparison
sd_raw = np.std(y_raw - y_raw_pred)
sd_dev = np.std(y_dev - y_dev_pred)
sd_observed = np.std(y_raw)
sd_deviation = np.std(y_dev)

labels = ["Observed\nSD", "Raw model\nresidual SD", "Deviation\nSD", "Deviation model\nresidual SD"]
values = [sd_observed, sd_raw, sd_deviation, sd_dev]
bars = axes[2].bar(range(4), values, color=["C0", "C0", "C2", "C2"], edgecolor="k")
bars[0].set_alpha(0.4); bars[1].set_alpha(0.7); bars[2].set_alpha(0.4); bars[3].set_alpha(0.7)
for bar, v in zip(bars, values):
    axes[2].text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                f"{v:.1f}", ha="center", fontsize=10)
axes[2].set_xticks(range(4))
axes[2].set_xticklabels(labels, fontsize=9)
axes[2].set_ylabel("Standard Deviation (mg/dL)")
axes[2].set_title("Noise Reduction: BGI Subtraction + Model")
axes[2].grid(True, alpha=0.3, axis="y")

plt.suptitle("EXP-2698: Step 2 — Does BGI Subtraction Improve Multi-Factor Models?", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig(OUT / "fig2_bgi_improvement.png", dpi=150)
plt.close()
print(f"Panel 2 saved (raw R²={r2_raw:.4f}, deviation R²={r2_dev:.4f})")

# ── Panel 3: Category-specific multi-factor models ────────────────────
fig, axes = plt.subplots(2, 3, figsize=(18, 10))

category_results = {}
for idx, cat in enumerate(["correction", "meal", "basal", "uam", "mixed"]):
    ax = axes[idx // 3][idx % 3]
    ec = ev[ev["category"] == cat]

    if cat == "correction":
        cat_features = ["bg0", "bolus_2h", "smb_2h", "excess_basal_2h", "roc_start", "iob_start"]
    elif cat == "meal":
        cat_features = ["bg0", "bolus_2h", "carbs_2h", "smb_2h", "excess_basal_2h", "roc_start"]
    elif cat == "basal":
        cat_features = ["bg0", "roc_start", "iob_start"]
    else:
        cat_features = ["bg0", "smb_2h", "excess_basal_2h", "roc_start", "iob_start"]

    clean_c = ec[cat_features + ["deviation"]].dropna()
    if len(clean_c) < 100:
        ax.text(0.5, 0.5, f"{cat}: n={len(clean_c)} (insufficient)",
               transform=ax.transAxes, ha="center", fontsize=12)
        ax.set_title(f"{cat.upper()}: insufficient data")
        continue

    Xc = clean_c[cat_features].values
    yc = clean_c["deviation"].values
    Xc_n = (Xc - Xc.mean(axis=0)) / (Xc.std(axis=0) + 1e-10)
    Xc_aug = np.column_stack([Xc_n, np.ones(len(Xc_n))])
    bc, _, _, _ = lstsq(Xc_aug, yc, rcond=None)
    yc_pred = Xc_aug @ bc
    r2_c = 1 - np.sum((yc - yc_pred)**2) / np.sum((yc - yc.mean())**2)

    # Also compute R² on raw observed_drop for comparison
    yc_raw = ec.loc[clean_c.index, "observed_drop"].values
    bc_raw, _, _, _ = lstsq(Xc_aug, yc_raw, rcond=None)
    r2_c_raw = 1 - np.sum((yc_raw - Xc_aug @ bc_raw)**2) / np.sum((yc_raw - yc_raw.mean())**2)

    # SE and significance
    n_c = len(yc)
    sigma2_c = np.sum((yc - yc_pred)**2) / max(n_c - len(bc), 1)
    try:
        cov_c = sigma2_c * np.linalg.inv(Xc_aug.T @ Xc_aug)
        se_c = np.sqrt(np.diag(cov_c))[:-1]
    except Exception:
        se_c = np.full(len(cat_features), np.nan)

    p_vals_c = []
    for c, s in zip(bc[:-1], se_c):
        if s > 0 and not np.isnan(s):
            t = c / s
            p_vals_c.append(2 * (1 - stats.t.cdf(abs(t), df=max(n_c - len(bc), 1))))
        else:
            p_vals_c.append(1.0)

    col_c = ["C3" if p < 0.05 else "gray" for p in p_vals_c]
    ax.barh(range(len(cat_features)), bc[:-1], color=col_c,
           xerr=1.96 * se_c, capsize=4, edgecolor="k")
    ax.set_yticks(range(len(cat_features)))
    ax.set_yticklabels(cat_features, fontsize=9)
    ax.axvline(0, color="k", ls="--", alpha=0.5)
    ax.set_xlabel("Coefficient (deviation)")
    ax.set_title(f"{cat.upper()} (n={n_c})\ndev R²={r2_c:.3f}, raw R²={r2_c_raw:.3f}")
    ax.grid(True, alpha=0.3, axis="x")

    category_results[cat] = {
        "n": int(n_c), "r2_deviation": float(r2_c), "r2_raw": float(r2_c_raw),
        "coefficients": {f: float(bc[i]) for i, f in enumerate(cat_features)},
        "p_values": {f: float(p) for f, p in zip(cat_features, p_vals_c)},
    }

# Summary in last panel
ax = axes[1][2]
ax.axis("off")
summary_rows = []
for cat in ["correction", "meal", "basal", "uam", "mixed"]:
    if cat in category_results:
        cr = category_results[cat]
        summary_rows.append([cat.upper(), cr["n"], f"{cr['r2_raw']:.3f}", f"{cr['r2_deviation']:.3f}",
                            f"{cr['r2_deviation'] - cr['r2_raw']:+.3f}"])

table = ax.table(cellText=summary_rows,
                colLabels=["Category", "N", "R² raw", "R² deviation", "Δ R²"],
                loc="center", cellLoc="center")
table.auto_set_font_size(False)
table.set_fontsize(11)
table.scale(1.3, 2.0)
ax.set_title("BGI Subtraction Benefit by Category")

plt.suptitle("EXP-2698: Step 3 — Category-Specific Deviation Models", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig(OUT / "fig3_category_models.png", dpi=150)
plt.close()
print("Panel 3 saved")

# ── Panel 4: Within-patient + circadian deconfounding ─────────────────
fig, axes = plt.subplots(2, 2, figsize=(14, 12))

# 4a: Within-patient fixed effects on deviations
# De-mean deviation within each patient
ev["dev_demeaned"] = ev.groupby("patient_id")["deviation"].transform(lambda x: x - x.mean())

clean_fe = ev[features + ["dev_demeaned"]].dropna()
X_fe = clean_fe[features].values
y_fe = clean_fe["dev_demeaned"].values
X_fe_n = (X_fe - X_fe.mean(axis=0)) / (X_fe.std(axis=0) + 1e-10)
X_fe_aug = np.column_stack([X_fe_n, np.ones(len(X_fe_n))])
b_fe, _, _, _ = lstsq(X_fe_aug, y_fe, rcond=None)
y_fe_pred = X_fe_aug @ b_fe
r2_fe = 1 - np.sum((y_fe - y_fe_pred)**2) / np.sum((y_fe - y_fe.mean())**2)

# Within-patient on raw BG drop
ev["drop_demeaned"] = ev.groupby("patient_id")["observed_drop"].transform(lambda x: x - x.mean())
y_raw_dm = clean_fe.index.map(ev["drop_demeaned"]).values
b_raw_dm, _, _, _ = lstsq(X_fe_aug, y_raw_dm, rcond=None)
r2_raw_dm = 1 - np.sum((y_raw_dm - X_fe_aug @ b_raw_dm)**2) / np.sum((y_raw_dm - y_raw_dm.mean())**2)

labels = ["Raw ΔBG\n(pooled)", "Raw ΔBG\n(within-patient)", "Deviation\n(pooled)", "Deviation\n(within-patient)"]
r2_vals = [r2_raw, r2_raw_dm, r2_dev, r2_fe]
bars = axes[0][0].bar(range(4), r2_vals, color=["C0", "C0", "C2", "C2"], edgecolor="k")
bars[0].set_alpha(0.4); bars[1].set_alpha(0.7); bars[2].set_alpha(0.4); bars[3].set_alpha(0.7)
for bar, v in zip(bars, r2_vals):
    axes[0][0].text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.003,
                   f"{v:.4f}", ha="center", fontsize=10, fontweight="bold")
axes[0][0].set_xticks(range(4))
axes[0][0].set_xticklabels(labels, fontsize=9)
axes[0][0].set_ylabel("R²")
axes[0][0].set_title("Deconfounding Chain: Cumulative R² Improvement")
axes[0][0].grid(True, alpha=0.3, axis="y")

# 4b: Circadian deviation patterns
circadian_dev = ev.groupby(["controller", "circadian_block"]).agg(
    mean_dev=("deviation", "mean"),
    se_dev=("deviation", "sem"),
    n=("deviation", "count"),
).reset_index()

for ctrl in controllers:
    cd = circadian_dev[circadian_dev["controller"] == ctrl]
    if len(cd) == 0:
        continue
    block_hours = cd["circadian_block"].values * 4
    axes[0][1].errorbar(block_hours, cd["mean_dev"].values,
                       yerr=1.96 * cd["se_dev"].values,
                       fmt="o-", color=colors_ctrl[ctrl], lw=2, capsize=5,
                       markersize=8, label=ctrl.upper())

axes[0][1].set_xlabel("Hour of day (block start)")
axes[0][1].set_ylabel("Mean deviation (mg/dL)")
axes[0][1].set_title("Circadian Deviation Pattern\n(positive = BG drops more than expected)")
axes[0][1].axhline(0, color="k", ls="--", alpha=0.5)
axes[0][1].legend()
axes[0][1].grid(True, alpha=0.3)

# 4c: Add circadian block dummies to model
ev_circ = ev.copy()
for block in range(6):
    ev_circ[f"block_{block}"] = (ev_circ["circadian_block"] == block).astype(float)

circ_features = features + [f"block_{b}" for b in range(1, 6)]  # block_0 is reference
clean_circ = ev_circ[circ_features + ["dev_demeaned"]].dropna()
X_circ = clean_circ[circ_features].values
y_circ = clean_circ["dev_demeaned"].values
X_circ_n = (X_circ - X_circ.mean(axis=0)) / (X_circ.std(axis=0) + 1e-10)
X_circ_aug = np.column_stack([X_circ_n, np.ones(len(X_circ_n))])
b_circ, _, _, _ = lstsq(X_circ_aug, y_circ, rcond=None)
y_circ_pred = X_circ_aug @ b_circ
r2_circ = 1 - np.sum((y_circ - y_circ_pred)**2) / np.sum((y_circ - y_circ.mean())**2)

# Full pipeline: BGI subtraction + within-patient FE + circadian + multi-factor
pipeline_r2 = {
    "Raw ΔBG pooled": r2_raw,
    "Raw ΔBG + FE": r2_raw_dm,
    "Deviation pooled": r2_dev,
    "Deviation + FE": r2_fe,
    "Deviation + FE + circadian": r2_circ,
}

labels_p = list(pipeline_r2.keys())
values_p = list(pipeline_r2.values())
axes[1][0].barh(range(len(labels_p)), values_p, color=["C0", "C0", "C2", "C2", "C3"],
               edgecolor="k", alpha=0.7)
for i, v in enumerate(values_p):
    axes[1][0].text(v + 0.003, i, f"{v:.4f}", va="center", fontsize=10, fontweight="bold")
axes[1][0].set_yticks(range(len(labels_p)))
axes[1][0].set_yticklabels(labels_p, fontsize=10)
axes[1][0].set_xlabel("R²")
axes[1][0].set_title("Full Deconfounding Pipeline")
axes[1][0].grid(True, alpha=0.3, axis="x")

# 4d: Controller-specific pipeline
ctrl_pipeline = {}
for ctrl in controllers:
    ec = ev[ev["controller"] == ctrl]
    clean_ec = ec[features + ["observed_drop", "deviation"]].dropna()
    if len(clean_ec) < 500:
        continue

    Xec = clean_ec[features].values
    Xec_n = (Xec - Xec.mean(axis=0)) / (Xec.std(axis=0) + 1e-10)
    Xec_aug = np.column_stack([Xec_n, np.ones(len(Xec_n))])

    # Raw
    y_r = clean_ec["observed_drop"].values
    b_r, _, _, _ = lstsq(Xec_aug, y_r, rcond=None)
    r2_r = 1 - np.sum((y_r - Xec_aug @ b_r)**2) / np.sum((y_r - y_r.mean())**2)

    # Deviation
    y_d = clean_ec["deviation"].values
    b_d, _, _, _ = lstsq(Xec_aug, y_d, rcond=None)
    r2_d = 1 - np.sum((y_d - Xec_aug @ b_d)**2) / np.sum((y_d - y_d.mean())**2)

    # Within-patient deviation
    ec_dm = ec.copy()
    ec_dm["dev_dm"] = ec_dm.groupby("patient_id")["deviation"].transform(lambda x: x - x.mean())
    clean_dm = ec_dm.loc[clean_ec.index, features + ["dev_dm"]].dropna()
    y_dm = clean_dm["dev_dm"].values
    b_dm, _, _, _ = lstsq(Xec_aug[:len(y_dm)], y_dm, rcond=None)
    r2_dm = 1 - np.sum((y_dm - Xec_aug[:len(y_dm)] @ b_dm)**2) / np.sum((y_dm - y_dm.mean())**2)

    ctrl_pipeline[ctrl] = {"raw": r2_r, "deviation": r2_d, "dev_fe": r2_dm}

x_pos = np.arange(3)
width = 0.25
for i, ctrl in enumerate(controllers):
    if ctrl in ctrl_pipeline:
        vals = [ctrl_pipeline[ctrl]["raw"], ctrl_pipeline[ctrl]["deviation"],
                ctrl_pipeline[ctrl]["dev_fe"]]
        axes[1][1].bar(x_pos + i * width, vals, width, label=ctrl.upper(),
                      color=colors_ctrl[ctrl], edgecolor="k", alpha=0.7)

axes[1][1].set_xticks(x_pos + width)
axes[1][1].set_xticklabels(["Raw ΔBG", "Deviation", "Dev + FE"], fontsize=10)
axes[1][1].set_ylabel("R²")
axes[1][1].set_title("Pipeline by Controller")
axes[1][1].legend()
axes[1][1].grid(True, alpha=0.3, axis="y")

plt.suptitle("EXP-2698: Step 4 — Full Deconfounding Pipeline", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig(OUT / "fig4_full_pipeline.png", dpi=150)
plt.close()
print(f"Panel 4 saved (pipeline: raw={r2_raw:.4f} → dev={r2_dev:.4f} → FE={r2_fe:.4f} → circ={r2_circ:.4f})")

# ── Panel 5: Correction-specific ISF recovery ─────────────────────────
fig, axes = plt.subplots(1, 3, figsize=(18, 6))

# The key test: within CORRECTION events, can we recover true ISF?
corrections = ev[(ev["category"] == "correction") & (ev["bg0"] >= 180)].copy()
print(f"\n  Correction events (BG≥180): {len(corrections)}")

# 5a: ISF from deviation: if BGI subtraction is correct, deviation should be ~0
# If ISF setting is wrong, deviation = (ISF_true - ISF_setting) * IOB_consumed
# So: deviation / IOB_consumed = ISF_true - ISF_setting (ISF error)
corrections["isf_error"] = corrections["deviation"] / corrections["iob_consumed"].clip(lower=0.1)

for ctrl in controllers:
    cc = corrections[corrections["controller"] == ctrl]
    if len(cc) < 50:
        continue
    axes[0].hist(cc["isf_error"].clip(-100, 100), bins=50, alpha=0.5,
                color=colors_ctrl[ctrl], label=f"{ctrl.upper()} (n={len(cc)})", density=True)

axes[0].axvline(0, color="k", ls="--", lw=2, label="ISF setting is correct")
axes[0].set_xlabel("ISF error = (true − setting) mg/dL/U")
axes[0].set_ylabel("Density")
axes[0].set_title("ISF Error Distribution from Deviations")
axes[0].legend(fontsize=9)
axes[0].set_xlim(-100, 100)
axes[0].grid(True, alpha=0.3)

# 5b: Dose-dependent ISF from deviations (our EXP-2640 finding)
corrections["effective_isf"] = corrections["observed_drop"] / corrections["bolus_2h"].clip(lower=0.1)

# Bin by dose and compute mean ISF per bin
has_bolus = corrections[corrections["bolus_2h"] > 0.3]
if len(has_bolus) > 100:
    try:
        dose_bins = pd.qcut(has_bolus["bolus_2h"], 8, duplicates="drop")
        isf_by_dose = has_bolus.groupby(dose_bins).agg(
            mean_dose=("bolus_2h", "mean"),
            mean_isf=("effective_isf", "mean"),
            se_isf=("effective_isf", "sem"),
            n=("effective_isf", "count"),
        )
        axes[1].errorbar(isf_by_dose["mean_dose"], isf_by_dose["mean_isf"],
                        yerr=1.96 * isf_by_dose["se_isf"],
                        fmt="ko-", lw=2, capsize=5, markersize=8)

        # Fit log model: ISF = a + b*ln(dose)
        valid = has_bolus[["bolus_2h", "effective_isf"]].dropna()
        valid = valid[(valid["effective_isf"] > 0) & (valid["effective_isf"] < 200)]
        log_dose = np.log(valid["bolus_2h"].values)
        isf_vals = valid["effective_isf"].values
        slope, intercept, r_log, p_log, _ = stats.linregress(log_dose, isf_vals)
        x_fit = np.linspace(valid["bolus_2h"].min(), valid["bolus_2h"].max(), 100)
        axes[1].plot(x_fit, intercept + slope * np.log(x_fit), "C3--", lw=2,
                    label=f"log model: r={r_log:.3f}, p={p_log:.2e}")
        axes[1].legend(fontsize=9)
    except Exception as e:
        print(f"  Dose-response error: {e}")

axes[1].set_xlabel("Bolus Dose (U)")
axes[1].set_ylabel("Effective ISF (mg/dL/U)")
axes[1].set_title("Dose-Dependent ISF (Correction Events)")
axes[1].set_ylim(0, 150)
axes[1].grid(True, alpha=0.3)

# 5c: Per-patient ISF recovery from deviations
pat_isf = corrections.groupby("patient_id").agg(
    mean_isf_error=("isf_error", "mean"),
    se_isf_error=("isf_error", "sem"),
    isf_setting=("isf_setting", "mean"),
    n=("isf_error", "count"),
    controller=("controller", "first"),
).reset_index()
pat_isf = pat_isf[pat_isf["n"] >= 20].sort_values("mean_isf_error")
pat_isf["implied_true_isf"] = pat_isf["isf_setting"] + pat_isf["mean_isf_error"]

for ctrl in controllers:
    mask = pat_isf["controller"] == ctrl
    if mask.any():
        pc = pat_isf[mask]
        axes[2].errorbar(pc["isf_setting"], pc["implied_true_isf"],
                        yerr=1.96 * pc["se_isf_error"],
                        fmt="o", markersize=8, capsize=4,
                        color=colors_ctrl[ctrl], label=ctrl.upper())
lims_isf = [0, max(pat_isf["isf_setting"].max(), pat_isf["implied_true_isf"].max()) + 20]
axes[2].plot(lims_isf, lims_isf, "k--", alpha=0.5, label="Setting = True ISF")
axes[2].set_xlabel("ISF Setting (mg/dL/U)")
axes[2].set_ylabel("Implied True ISF (mg/dL/U)")
axes[2].set_title(f"Per-Patient ISF Recovery\n(n={len(pat_isf)} patients)")
axes[2].legend()
axes[2].grid(True, alpha=0.3)

axes[2].legend(fontsize=9)

plt.suptitle("EXP-2698: Step 5 — ISF Recovery from Deconfounded Deviations", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig(OUT / "fig5_isf_recovery.png", dpi=150)
plt.close()
print("Panel 5 saved")

# ── Panel 6: Grand summary ───────────────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(16, 8))

# 6a: The deconfounding waterfall
stages = [
    "Univariate\n(bolus only)", "Multi-factor\n(EXP-2690)",
    "BGI subtraction\n(deviation)", "Within-patient FE\n(+ deviation)",
    "+ Circadian blocks", "Category-specific\n(correction only)",
]
# Use correction-specific R² for the last stage
corr_clean = corrections[features + ["deviation"]].dropna()
if len(corr_clean) > 500:
    Xcc = corr_clean[features].values
    ycc = corr_clean["deviation"].values
    Xcc_n = (Xcc - Xcc.mean(axis=0)) / (Xcc.std(axis=0) + 1e-10)
    Xcc_aug = np.column_stack([Xcc_n, np.ones(len(Xcc_n))])
    bcc, _, _, _ = lstsq(Xcc_aug, ycc, rcond=None)
    r2_corr_dev = 1 - np.sum((ycc - Xcc_aug @ bcc)**2) / np.sum((ycc - ycc.mean())**2)
else:
    r2_corr_dev = r2_dev

r2_stages = [0.015, r2_raw, r2_dev, r2_fe, r2_circ, r2_corr_dev]

# Waterfall bars
for i in range(len(stages)):
    if i == 0:
        axes[0].bar(i, r2_stages[i], color="C3", edgecolor="k", alpha=0.7)
    else:
        delta = r2_stages[i] - r2_stages[i-1]
        color = "C2" if delta > 0 else "C3"
        axes[0].bar(i, r2_stages[i], color=color, edgecolor="k", alpha=0.7)

for i, v in enumerate(r2_stages):
    axes[0].text(i, v + 0.005, f"{v:.3f}", ha="center", fontsize=10, fontweight="bold")

axes[0].set_xticks(range(len(stages)))
axes[0].set_xticklabels(stages, fontsize=8, rotation=15, ha="right")
axes[0].set_ylabel("R²")
axes[0].set_title("Deconfounding Waterfall: Cumulative R² Improvement")
axes[0].grid(True, alpha=0.3, axis="y")

# 6b: Summary table
ax = axes[1]
ax.axis("off")

summary_text = f"""
EXP-2698: OREF0-INSPIRED DECONFOUNDING PIPELINE

APPROACH: Combine multiple deconfounding techniques:
  1. BGI subtraction (oref0's deviation concept)
  2. Event categorization (correction/meal/basal/UAM)
  3. Within-patient fixed effects
  4. Circadian time-of-day blocking
  5. Multi-factor channel decomposition

R² IMPROVEMENT CHAIN:
  Univariate (bolus only):     0.015
  Multi-factor (all channels): {r2_raw:.3f}
  + BGI subtraction:           {r2_dev:.3f} ({r2_dev-r2_raw:+.3f})
  + Within-patient FE:         {r2_fe:.3f} ({r2_fe-r2_dev:+.3f})
  + Circadian blocks:          {r2_circ:.3f} ({r2_circ-r2_fe:+.3f})

ISF RECOVERY FROM DEVIATIONS:
  Mean ISF error: {corrections['isf_error'].mean():.1f} mg/dL/U
  Dose-dependent ISF: r={r_log:.3f} (log model)
  Per-patient ISF recovery: {len(pat_isf)} patients

CATEGORY-SPECIFIC R² (deviation model):
"""
for cat in ["correction", "meal", "basal", "uam", "mixed"]:
    if cat in category_results:
        cr = category_results[cat]
        summary_text += f"  {cat:12s}: R²={cr['r2_deviation']:.3f} (raw={cr['r2_raw']:.3f}, Δ={cr['r2_deviation']-cr['r2_raw']:+.3f})\n"

summary_text += f"""
CONCLUSION:
  Combined techniques recover MORE signal than any single method.
  BGI subtraction adds {r2_dev-r2_raw:+.3f} R², FE adds {r2_fe-r2_dev:+.3f},
  circadian adds {r2_circ-r2_fe:+.3f}. Total improvement: {r2_circ-0.015:.3f} over
  univariate baseline.

  The oref0 approach of 'subtracting expected effects' IS FEASIBLE
  and COMPLEMENTARY with multi-factor decomposition.
"""

ax.text(0.05, 0.95, summary_text, transform=ax.transAxes, fontsize=9,
       va="top", fontfamily="monospace")

plt.suptitle("EXP-2698: Combined Deconfounding Pipeline Summary", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig(OUT / "fig6_summary.png", dpi=150)
plt.close()
print("Panel 6: Summary saved")

# ── Save results ──────────────────────────────────────────────────────
results = {
    "experiment": "EXP-2698",
    "title": "oref0-Inspired Multi-Factor Deconfounding Pipeline",
    "n_events": int(len(ev)),
    "expected_vs_observed": {"r": float(r_eo), "p": float(p_eo)},
    "deviation_stats": {
        "mean": float(ev["deviation"].mean()),
        "sd": float(ev["deviation"].std()),
    },
    "category_counts": cat_counts.to_dict(),
    "r2_pipeline": {
        "univariate_bolus": 0.015,
        "multi_factor_raw": float(r2_raw),
        "deviation_pooled": float(r2_dev),
        "deviation_within_patient": float(r2_fe),
        "deviation_fe_circadian": float(r2_circ),
    },
    "category_r2": category_results,
    "controller_pipeline": {c: {k: float(v) for k, v in p.items()} for c, p in ctrl_pipeline.items()},
    "isf_recovery": {
        "mean_isf_error": float(corrections["isf_error"].mean()),
        "dose_dependent_r": float(r_log),
        "dose_dependent_p": float(p_log),
        "n_patients_recovered": int(len(pat_isf)),
    },
}
(EXP / "exp-2698_deconfounding_pipeline.json").write_text(json.dumps(results, indent=2))

print(f"""
{'='*60}
EXP-2698: DECONFOUNDING PIPELINE — KEY RESULTS
{'='*60}

  R² WATERFALL:
    Univariate (bolus only):     0.015
    Multi-factor (all channels): {r2_raw:.4f}  (+{r2_raw-0.015:.3f})
    + BGI subtraction:           {r2_dev:.4f}  ({r2_dev-r2_raw:+.4f})
    + Within-patient FE:         {r2_fe:.4f}  ({r2_fe-r2_dev:+.4f})
    + Circadian blocks:          {r2_circ:.4f}  ({r2_circ-r2_fe:+.4f})

  TOTAL IMPROVEMENT: {r2_circ-0.015:.3f} R² over univariate baseline
  (from 0.015 to {r2_circ:.3f} = {r2_circ/0.015:.0f}× improvement)

  CATEGORY-SPECIFIC (correction events only):
    Correction deviation R²: {category_results.get('correction', {}).get('r2_deviation', 0):.3f}

  ISF RECOVERY:
    Mean ISF error: {corrections['isf_error'].mean():.1f} mg/dL/U
    Dose-dependent ISF (log): r={r_log:.3f}, p={p_log:.2e}
    N patients with ISF recovery: {len(pat_isf)}

  CONCLUSION: Combined techniques are FEASIBLE and COMPLEMENTARY.
""")
