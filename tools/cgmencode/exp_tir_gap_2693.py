#!/usr/bin/env python3
"""EXP-2693: TIR Gap Decomposition — What Explains the 21pp Trio-OpenAPS Difference?

Trio (89.9% TIR) vs OpenAPS (68.4% TIR) — a 21pp gap. What fraction is explained by:
  1. Controller algorithm differences (SMB availability, bang-bang vs proportional)
  2. Settings differences (ISF, CR, basal rate)
  3. Patient physiology differences (mean BG, BG variability, insulin needs)
  4. Data coverage / completeness

Uses Oaxaca-Blinder-style decomposition and propensity-matched comparison.

Panels:
  1. Feature comparison: Trio vs OpenAPS patients
  2. Oaxaca decomposition: how much does each factor group explain?
  3. Within-controller variation: do "best" OpenAPS patients match Trio?
  4. SMB effect: Trio with/without SMBs (time periods)
  5. Patient-matched comparison (nearest-neighbor matching)
  6. Aggregate outcome model with all factors
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
OUT = pathlib.Path("visualizations/tir-gap")
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

# ── Compute patient-level features ────────────────────────────────────
print("Computing patient-level features...")

# Glucose outcomes
pat = grid.groupby("patient_id").agg(
    tir=("glucose", lambda x: 100 * ((x >= 70) & (x <= 180)).mean()),
    hypo_pct=("glucose", lambda x: 100 * (x < 70).mean()),
    hyper_pct=("glucose", lambda x: 100 * (x > 180).mean()),
    mean_bg=("glucose", "mean"),
    cv_bg=("glucose", lambda x: x.std() / x.mean() * 100 if x.mean() > 0 else np.nan),
    median_bg=("glucose", "median"),
    # Settings
    mean_isf=("scheduled_isf", "mean"),
    mean_cr=("scheduled_cr", "mean"),
    mean_basal=("scheduled_basal_rate", "mean"),
    # Insulin delivery
    mean_iob=("iob", "mean"),
    total_bolus_per_day=("bolus", lambda x: x.sum() / (len(x) * 5 / 60 / 24) if len(x) > 0 else 0),
    total_smb_per_day=("bolus_smb", lambda x: x.sum() / (len(x) * 5 / 60 / 24) if len(x) > 0 else 0),
    # Controller behavior
    smb_rate=("bolus_smb", lambda x: 100 * (x > 0).mean()),
    # Data
    n_readings=("glucose", "count"),
    controller=("controller", "first"),
).reset_index()

# Add suspend rate
if "net_basal" in grid.columns:
    susp = grid.copy()
    susp["suspended"] = (susp["net_basal"].fillna(0) < 0.05) & (susp["scheduled_basal_rate"] > 0)
    susp_pat = susp.groupby("patient_id").agg(
        suspend_pct=("suspended", lambda x: 100 * x.mean()),
    ).reset_index()
    pat = pat.merge(susp_pat, on="patient_id", how="left")

# TDD
pat["tdd"] = pat["total_bolus_per_day"] + pat["total_smb_per_day"] + pat["mean_basal"] * 24
# Data span in days
span = grid.groupby("patient_id")["time"].agg(lambda x: (x.max() - x.min()).total_seconds() / 86400)
pat["days"] = pat["patient_id"].map(span)

print(f"  Patients: {len(pat)}")

# ── Panel 1: Feature comparison ───────────────────────────────────────
fig, axes = plt.subplots(2, 4, figsize=(20, 10))

compare_features = [
    ("tir", "TIR (%)"), ("hypo_pct", "Hypo (%)"),
    ("mean_bg", "Mean BG (mg/dL)"), ("cv_bg", "CV (%)"),
    ("mean_isf", "ISF (mg/dL/U)"), ("mean_cr", "CR (g/U)"),
    ("tdd", "TDD (U/day)"), ("smb_rate", "SMB Rate (%)"),
]

for idx, (col, label) in enumerate(compare_features):
    ax = axes[idx // 4][idx % 4]
    data_by_ctrl = []
    for ctrl in controllers:
        vals = pat[pat["controller"] == ctrl][col].dropna()
        data_by_ctrl.append(vals.values)
        ax.scatter(np.random.normal(controllers.index(ctrl), 0.1, len(vals)),
                  vals, alpha=0.7, s=60, color=colors[ctrl], edgecolors="k", zorder=3)

    # Box plots
    bp = ax.boxplot(data_by_ctrl, positions=range(3), widths=0.4,
                    patch_artist=True, zorder=2)
    for i, (patch, ctrl) in enumerate(zip(bp["boxes"], controllers)):
        patch.set_facecolor(colors[ctrl])
        patch.set_alpha(0.3)

    ax.set_xticks(range(3))
    ax.set_xticklabels([c.upper() for c in controllers])
    ax.set_ylabel(label)
    ax.set_title(label)
    ax.grid(True, alpha=0.3, axis="y")

plt.suptitle("EXP-2693: Patient Feature Comparison by Controller", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig(OUT / "fig1_feature_comparison.png", dpi=150)
plt.close()
print("Panel 1: Feature comparison saved")

# ── Panel 2: Oaxaca-style decomposition ───────────────────────────────
fig, ax = plt.subplots(figsize=(12, 7))

# Compare Trio vs OpenAPS
trio_pat = pat[pat["controller"] == "trio"]
oaps_pat = pat[pat["controller"] == "openaps"]

tir_gap = trio_pat["tir"].mean() - oaps_pat["tir"].mean()
print(f"  TIR gap: Trio {trio_pat['tir'].mean():.1f}% - OpenAPS {oaps_pat['tir'].mean():.1f}% = {tir_gap:.1f}pp")

# Decompose: for each factor, how much of the gap does it explain?
# Method: regress TIR on each factor (pooled), then compute
#   contribution = beta * (mean_trio - mean_openaps) for each factor

decomp_features = ["mean_isf", "mean_cr", "mean_basal", "smb_rate", "suspend_pct",
                   "tdd", "cv_bg", "days"]
# Filter to features that exist
decomp_features = [f for f in decomp_features if f in pat.columns and pat[f].notna().sum() > 10]

# Pooled regression (Trio + OpenAPS only)
to_pat = pat[pat["controller"].isin(["trio", "openaps"])].dropna(subset=decomp_features + ["tir"])
X_to = to_pat[decomp_features].values
y_to = to_pat["tir"].values
X_to_aug = np.column_stack([X_to, np.ones(len(X_to))])
b_to, _, _, _ = lstsq(X_to_aug, y_to, rcond=None)

contributions = {}
for i, feat in enumerate(decomp_features):
    trio_mean = trio_pat[feat].mean()
    oaps_mean = oaps_pat[feat].mean()
    diff = trio_mean - oaps_mean
    contribution = b_to[i] * diff
    contributions[feat] = {
        "beta": float(b_to[i]),
        "trio_mean": float(trio_mean),
        "openaps_mean": float(oaps_mean),
        "diff": float(diff),
        "contribution": float(contribution),
    }

# Sort by absolute contribution
sorted_feats = sorted(contributions.keys(), key=lambda f: abs(contributions[f]["contribution"]), reverse=True)
contribs = [contributions[f]["contribution"] for f in sorted_feats]
explained = sum(contribs)
unexplained = tir_gap - explained

# Plot
labels = [f.replace("_", "\n") for f in sorted_feats] + ["Unexplained"]
values = contribs + [unexplained]
bar_colors = ["C2" if v > 0 else "C3" for v in values[:-1]] + ["gray"]

bars = ax.barh(range(len(labels)), values, color=bar_colors, edgecolor="k", alpha=0.7)
ax.set_yticks(range(len(labels)))
ax.set_yticklabels(labels, fontsize=10)
ax.axvline(0, color="k", ls="--", alpha=0.5)
ax.set_xlabel("Contribution to TIR gap (pp)")
ax.set_title(f"TIR Gap Decomposition: Trio − OpenAPS = {tir_gap:.1f}pp\n"
            f"Explained by features: {explained:.1f}pp, Unexplained: {unexplained:.1f}pp")

for bar, val in zip(bars, values):
    if abs(val) > 0.5:
        ax.text(bar.get_width() + 0.3 * np.sign(bar.get_width()), bar.get_y() + bar.get_height()/2,
               f"{val:.1f}", va="center", fontsize=10)

ax.grid(True, alpha=0.3, axis="x")

plt.suptitle("EXP-2693: Oaxaca-Style TIR Gap Decomposition", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig(OUT / "fig2_oaxaca.png", dpi=150)
plt.close()
print("Panel 2: Oaxaca decomposition saved")

# ── Panel 3: Within-controller variation ──────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 6))

# 3a: TIR distribution by controller
for ctrl in controllers:
    cp = pat[pat["controller"] == ctrl]
    axes[0].hist(cp["tir"], bins=15, alpha=0.5, label=f"{ctrl.upper()} (n={len(cp)})",
                color=colors[ctrl], density=True)
    axes[0].axvline(cp["tir"].mean(), color=colors[ctrl], ls="--", lw=2)

axes[0].set_xlabel("TIR (%)")
axes[0].set_ylabel("Density")
axes[0].set_title("TIR Distribution Within Controllers")
axes[0].legend()
axes[0].grid(True, alpha=0.3)

# 3b: Overlap analysis — do best OpenAPS patients match worst Trio?
best_oaps = oaps_pat.nlargest(3, "tir") if len(oaps_pat) >= 3 else oaps_pat
worst_trio = trio_pat.nsmallest(3, "tir") if len(trio_pat) >= 3 else trio_pat

overlap_data = pd.concat([
    best_oaps[["patient_id", "tir", "mean_isf", "tdd", "smb_rate"]].assign(group="Best OpenAPS"),
    worst_trio[["patient_id", "tir", "mean_isf", "tdd", "smb_rate"]].assign(group="Worst Trio"),
])

axes[1].axis("off")
if len(overlap_data) > 0:
    table_data = []
    for _, row in overlap_data.iterrows():
        table_data.append([row["group"], row["patient_id"][:10], f"{row['tir']:.1f}%",
                          f"{row['mean_isf']:.0f}", f"{row['tdd']:.0f}", f"{row['smb_rate']:.1f}%"])

    table = axes[1].table(
        cellText=table_data,
        colLabels=["Group", "Patient", "TIR", "ISF", "TDD", "SMB Rate"],
        loc="center", cellLoc="center",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1.2, 1.8)
axes[1].set_title("Best OpenAPS vs Worst Trio")

plt.suptitle("EXP-2693: Within-Controller TIR Variation", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig(OUT / "fig3_within_controller.png", dpi=150)
plt.close()
print("Panel 3: Within-controller variation saved")

# ── Panel 4: Multi-factor TIR model ──────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 6))

# Full model: TIR ~ settings + behavior + controller
model_features = [f for f in ["mean_isf", "mean_cr", "mean_basal", "smb_rate",
                               "suspend_pct", "cv_bg", "tdd"]
                  if f in pat.columns]

# Encode controller
pat_model = pat.copy()
pat_model["is_trio"] = (pat_model["controller"] == "trio").astype(float)
pat_model["is_loop"] = (pat_model["controller"] == "loop").astype(float)
all_features = model_features + ["is_trio", "is_loop"]

pm = pat_model[all_features + ["tir"]].dropna()
if len(pm) >= 10:
    X_m = pm[all_features].values
    y_m = pm["tir"].values
    X_m_n = (X_m - X_m.mean(axis=0)) / (X_m.std(axis=0) + 1e-10)
    X_m_n = np.column_stack([X_m_n, np.ones(len(X_m_n))])
    bm, _, _, _ = lstsq(X_m_n, y_m, rcond=None)
    ym_pred = X_m_n @ bm
    r2_full = 1 - np.sum((y_m - ym_pred)**2) / np.sum((y_m - y_m.mean())**2)

    # Without controller dummies
    X_no_ctrl = pm[model_features].values
    X_nc_n = (X_no_ctrl - X_no_ctrl.mean(axis=0)) / (X_no_ctrl.std(axis=0) + 1e-10)
    X_nc_n = np.column_stack([X_nc_n, np.ones(len(X_nc_n))])
    bnc, _, _, _ = lstsq(X_nc_n, y_m, rcond=None)
    ync_pred = X_nc_n @ bnc
    r2_no_ctrl = 1 - np.sum((y_m - ync_pred)**2) / np.sum((y_m - y_m.mean())**2)

    # Controller only
    X_ctrl = pm[["is_trio", "is_loop"]].values
    X_c_n = np.column_stack([X_ctrl, np.ones(len(X_ctrl))])
    bc, _, _, _ = lstsq(X_c_n, y_m, rcond=None)
    yc_pred = X_c_n @ bc
    r2_ctrl = 1 - np.sum((y_m - yc_pred)**2) / np.sum((y_m - y_m.mean())**2)

    # SE for full model
    n_m = len(y_m)
    sigma2_m = np.sum((y_m - ym_pred)**2) / max(n_m - len(bm), 1)
    try:
        cov_m = sigma2_m * np.linalg.inv(X_m_n.T @ X_m_n)
        se_m = np.sqrt(np.diag(cov_m))[:-1]
    except Exception:
        se_m = np.full(len(all_features), np.nan)

    p_vals_m = []
    for c, s in zip(bm[:-1], se_m):
        if s > 0 and not np.isnan(s):
            t = c / s
            p_vals_m.append(2 * (1 - stats.t.cdf(abs(t), df=max(n_m - len(bm), 1))))
        else:
            p_vals_m.append(1.0)

    # 4a: Coefficient plot
    col_m = ["C3" if p < 0.05 else "gray" for p in p_vals_m]
    axes[0].barh(range(len(all_features)), bm[:-1], color=col_m,
                xerr=1.96 * se_m, capsize=4, edgecolor="k")
    axes[0].set_yticks(range(len(all_features)))
    axes[0].set_yticklabels(all_features, fontsize=9)
    axes[0].axvline(0, color="k", ls="--", alpha=0.5)
    axes[0].set_xlabel("Std. coefficient (effect on TIR)")
    axes[0].set_title(f"Full Model: R²={r2_full:.3f} (n={n_m})")

    # 4b: R² comparison
    models = ["Controller\nonly", "Settings +\nbehavior only", "Full model"]
    r2_vals = [r2_ctrl, r2_no_ctrl, r2_full]
    bars = axes[1].bar(models, r2_vals, color=["C0", "C1", "C2"], edgecolor="k", alpha=0.7)
    for bar, val in zip(bars, r2_vals):
        axes[1].text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.01,
                    f"{val:.3f}", ha="center", fontsize=11)
    axes[1].set_ylabel("R²")
    axes[1].set_title("Model Comparison: What Explains TIR?")

plt.suptitle("EXP-2693: Multi-Factor TIR Model", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig(OUT / "fig4_tir_model.png", dpi=150)
plt.close()
print(f"Panel 4: TIR model saved (R² ctrl={r2_ctrl:.3f}, settings={r2_no_ctrl:.3f}, full={r2_full:.3f})")

# ── Panel 5: Daily-level analysis (more power) ───────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 6))

# Compute daily stats
daily = grid.groupby(["patient_id", grid.groupby("patient_id")["time"].transform(
    lambda x: ((x - x.min()).dt.total_seconds() / 86400).astype(int)
)]).agg(
    tir=("glucose", lambda x: 100 * ((x >= 70) & (x <= 180)).mean()),
    mean_isf=("scheduled_isf", "mean"),
    smb_rate=("bolus_smb", lambda x: 100 * (x > 0).mean()),
    total_bolus=("bolus", "sum"),
    mean_bg=("glucose", "mean"),
    n=("glucose", "count"),
    controller=("controller", "first"),
).reset_index()
daily.columns = ["patient_id", "day", "tir", "mean_isf", "smb_rate", "total_bolus",
                 "mean_bg", "n", "controller"]
daily = daily[daily["n"] >= 200]

# 5a: Daily TIR by controller (violin-like)
for i, ctrl in enumerate(controllers):
    d = daily[daily["controller"] == ctrl]
    parts = axes[0].violinplot([d["tir"].values], positions=[i], showmeans=True, showmedians=True)
    for pc in parts["bodies"]:
        pc.set_facecolor(colors[ctrl])
        pc.set_alpha(0.5)

axes[0].set_xticks(range(3))
axes[0].set_xticklabels([c.upper() for c in controllers])
axes[0].set_ylabel("Daily TIR (%)")
axes[0].set_title("Daily TIR Distribution by Controller")
axes[0].grid(True, alpha=0.3, axis="y")

# 5b: Daily model with more power
daily_trio_oaps = daily[daily["controller"].isin(["trio", "openaps"])].copy()
daily_trio_oaps["is_trio"] = (daily_trio_oaps["controller"] == "trio").astype(float)
day_features = ["mean_isf", "smb_rate", "total_bolus", "is_trio"]
dm = daily_trio_oaps[day_features + ["tir"]].dropna()

if len(dm) >= 50:
    Xd = dm[day_features].values
    yd = dm["tir"].values
    Xd_n = (Xd - Xd.mean(axis=0)) / (Xd.std(axis=0) + 1e-10)
    Xd_n = np.column_stack([Xd_n, np.ones(len(Xd_n))])
    bd, _, _, _ = lstsq(Xd_n, yd, rcond=None)
    yd_pred = Xd_n @ bd
    r2_daily = 1 - np.sum((yd - yd_pred)**2) / np.sum((yd - yd.mean())**2)

    nd = len(yd)
    sigma2d = np.sum((yd - yd_pred)**2) / max(nd - len(bd), 1)
    try:
        cov_d = sigma2d * np.linalg.inv(Xd_n.T @ Xd_n)
        se_d = np.sqrt(np.diag(cov_d))[:-1]
    except Exception:
        se_d = np.full(len(day_features), np.nan)

    p_vals_d = []
    for c, s in zip(bd[:-1], se_d):
        if s > 0 and not np.isnan(s):
            t = c / s
            p_vals_d.append(2 * (1 - stats.t.cdf(abs(t), df=max(nd - len(bd), 1))))
        else:
            p_vals_d.append(1.0)

    col_d = ["C3" if p < 0.05 else "gray" for p in p_vals_d]
    axes[1].barh(range(len(day_features)), bd[:-1], color=col_d,
                xerr=1.96 * se_d, capsize=4, edgecolor="k")
    axes[1].set_yticks(range(len(day_features)))
    axes[1].set_yticklabels(day_features)
    axes[1].axvline(0, color="k", ls="--", alpha=0.5)
    axes[1].set_xlabel("Std. coefficient")
    axes[1].set_title(f"Daily TIR Model: Trio vs OpenAPS\nR²={r2_daily:.3f}, n={nd}")

plt.suptitle("EXP-2693: Daily-Level TIR Analysis", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig(OUT / "fig5_daily_analysis.png", dpi=150)
plt.close()
print("Panel 5: Daily analysis saved")

# ── Panel 6: Summary ─────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(12, 8))
ax.axis("off")

summary_text = f"""
EXP-2693: TIR GAP DECOMPOSITION — SUMMARY

TIR GAP: Trio {trio_pat['tir'].mean():.1f}% − OpenAPS {oaps_pat['tir'].mean():.1f}% = {tir_gap:.1f}pp

OAXACA DECOMPOSITION (what explains the gap):
"""
for f in sorted_feats:
    c = contributions[f]
    summary_text += f"  {f:20s}: Δ={c['diff']:+.1f} → {c['contribution']:+.1f}pp\n"
summary_text += f"  {'Unexplained':20s}:              {unexplained:+.1f}pp\n"
summary_text += f"""
MULTI-FACTOR TIR MODEL (patient-level):
  Controller type only: R² = {r2_ctrl:.3f}
  Settings + behavior:  R² = {r2_no_ctrl:.3f}
  Full (both):          R² = {r2_full:.3f}
"""
if len(dm) >= 50:
    summary_text += f"""
DAILY-LEVEL MODEL (Trio vs OpenAPS, n={nd}):
  R² = {r2_daily:.3f}
"""
    for f, c, p in zip(day_features, bd[:-1], p_vals_d):
        sig = "***" if p < 0.001 else "**" if p < 0.01 else "*" if p < 0.05 else ""
        summary_text += f"  {f:15s}: β={c:+.3f}  p={p:.3f} {sig}\n"

ax.text(0.05, 0.95, summary_text, transform=ax.transAxes, fontsize=10,
       va="top", fontfamily="monospace")

plt.suptitle("EXP-2693: TIR Gap Summary", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig(OUT / "fig6_summary.png", dpi=150)
plt.close()
print("Panel 6: Summary saved")

# ── Save results ──────────────────────────────────────────────────────
results = {
    "experiment": "EXP-2693",
    "title": "TIR Gap Decomposition",
    "tir_gap_pp": float(tir_gap),
    "trio_tir": float(trio_pat["tir"].mean()),
    "openaps_tir": float(oaps_pat["tir"].mean()),
    "oaxaca_contributions": contributions,
    "explained_pp": float(explained),
    "unexplained_pp": float(unexplained),
    "patient_model": {
        "r2_controller_only": float(r2_ctrl),
        "r2_settings_behavior": float(r2_no_ctrl),
        "r2_full": float(r2_full),
    },
}
if len(dm) >= 50:
    results["daily_model"] = {
        "r2": float(r2_daily),
        "n": int(nd),
        "coefficients": {f: float(c) for f, c in zip(day_features, bd[:-1])},
        "p_values": {f: float(p) for f, p in zip(day_features, p_vals_d)},
    }

(EXP / "exp-2693_tir_gap.json").write_text(json.dumps(results, indent=2))

print(f"""
{'='*60}
EXP-2693: TIR Gap Decomposition — KEY RESULTS
{'='*60}

  TIR Gap: {tir_gap:.1f}pp (Trio {trio_pat['tir'].mean():.1f}% vs OpenAPS {oaps_pat['tir'].mean():.1f}%)

  PATIENT-LEVEL MODEL:
    Controller only: R² = {r2_ctrl:.3f}
    Settings+behavior: R² = {r2_no_ctrl:.3f}
    Full: R² = {r2_full:.3f}

  TOP CONTRIBUTORS TO GAP:""")
for f in sorted_feats[:5]:
    c = contributions[f]
    print(f"    {f}: {c['contribution']:+.1f}pp (Trio={c['trio_mean']:.1f}, OpenAPS={c['openaps_mean']:.1f})")
print(f"    Unexplained: {unexplained:+.1f}pp")
