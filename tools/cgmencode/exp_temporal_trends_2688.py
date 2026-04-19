#!/usr/bin/env python3
"""EXP-2688: Within-Patient Temporal Trends

Do outcomes (TIR, hypo rate, mean BG) improve over time as patients use AID?
This tests whether settings tuning / learning has measurable effects on aggregate
outcomes, or if outcomes are stable from the start.

Panels:
  1. Weekly TIR trend per patient (small multiples)
  2. First-month vs last-month TIR comparison
  3. Settings drift over time (ISF, CR, basal rate)
  4. Controller aggressiveness over time (SMB rate, suspend %)
  5. Learning curve: days-on-AID vs TIR
"""

import json, pathlib, warnings
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy import stats

warnings.filterwarnings("ignore")
OUT = pathlib.Path("visualizations/temporal-trends")
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

# Ensure time is usable
grid["time"] = pd.to_datetime(grid["time"], utc=True)
grid = grid.sort_values(["patient_id", "time"]).reset_index(drop=True)

# ── Compute weekly stats per patient ──────────────────────────────────
print("Computing weekly stats...")
grid["week"] = grid.groupby("patient_id")["time"].transform(
    lambda x: ((x - x.min()).dt.total_seconds() / (7 * 86400)).astype(int)
)

weekly = grid.groupby(["patient_id", "week"]).agg(
    tir=("glucose", lambda x: 100 * ((x >= 70) & (x <= 180)).mean()),
    hypo_pct=("glucose", lambda x: 100 * (x < 70).mean()),
    mean_bg=("glucose", "mean"),
    median_bg=("glucose", "median"),
    mean_iob=("iob", "mean"),
    mean_isf=("scheduled_isf", "mean"),
    mean_cr=("scheduled_cr", "mean"),
    mean_basal=("scheduled_basal_rate", "mean"),
    n_readings=("glucose", "count"),
    controller=("controller", "first"),
).reset_index()

# Filter weeks with enough data (≥500 readings = ~1.7 days)
weekly = weekly[weekly["n_readings"] >= 500]

# Add SMB rate and suspend % where possible
smb_weekly = grid[grid["bolus_smb"].notna()].groupby(["patient_id", "week"]).agg(
    smb_rate=("bolus_smb", lambda x: 100 * (x > 0).mean()),
).reset_index()
weekly = weekly.merge(smb_weekly, on=["patient_id", "week"], how="left")

# Compute basal suspend rate
if "net_basal" in grid.columns and "scheduled_basal_rate" in grid.columns:
    susp = grid.copy()
    susp["suspended"] = (susp["net_basal"].fillna(0) < 0.05) & (susp["scheduled_basal_rate"] > 0)
    susp_weekly = susp.groupby(["patient_id", "week"]).agg(
        suspend_pct=("suspended", lambda x: 100 * x.mean()),
    ).reset_index()
    weekly = weekly.merge(susp_weekly, on=["patient_id", "week"], how="left")

# ── Panel 1: Small multiples — weekly TIR ─────────────────────────────
patients = sorted(weekly["patient_id"].unique())
n_patients = len(patients)
ncols = 5
nrows = (n_patients + ncols - 1) // ncols

fig, axes = plt.subplots(nrows, ncols, figsize=(20, 4 * nrows), squeeze=False)
colors = {"loop": "C0", "trio": "C1", "openaps": "C2"}

for i, pid in enumerate(patients):
    ax = axes[i // ncols][i % ncols]
    pw = weekly[weekly["patient_id"] == pid].sort_values("week")
    ctrl = pw["controller"].iloc[0]
    color = colors.get(ctrl, "gray")
    
    ax.plot(pw["week"], pw["tir"], "o-", color=color, markersize=3, lw=1)
    
    # Trend line
    if len(pw) >= 4:
        slope, intercept, r, p, _ = stats.linregress(pw["week"], pw["tir"])
        x_fit = np.array([pw["week"].min(), pw["week"].max()])
        ax.plot(x_fit, slope * x_fit + intercept, "--", color="red", lw=1.5)
        ax.set_title(f"{pid[:12]}\n{ctrl} slope={slope:.2f}/wk p={p:.2f}", fontsize=8)
    else:
        ax.set_title(f"{pid[:12]}\n{ctrl}", fontsize=8)
    
    ax.axhline(70, color="gray", ls=":", alpha=0.5)
    ax.set_ylim(30, 100)
    ax.tick_params(labelsize=7)

# Hide empty subplots
for i in range(n_patients, nrows * ncols):
    axes[i // ncols][i % ncols].set_visible(False)

fig.suptitle("EXP-2688: Weekly TIR Trends (dashed red = linear trend)", fontsize=14, fontweight="bold")
fig.text(0.5, 0.02, "Week", ha="center", fontsize=12)
fig.text(0.02, 0.5, "TIR (%)", va="center", rotation="vertical", fontsize=12)
plt.tight_layout(rect=[0.03, 0.03, 1, 0.96])
plt.savefig(OUT / "fig1_weekly_tir.png", dpi=150)
plt.close()
print("Panel 1: Weekly TIR saved")

# ── Panel 2: First month vs last month ────────────────────────────────
fig, axes = plt.subplots(1, 3, figsize=(16, 5))

first_last = []
for pid in patients:
    pw = weekly[weekly["patient_id"] == pid].sort_values("week")
    if len(pw) >= 8:  # need at least 8 weeks
        first_4 = pw.head(4)["tir"].mean()
        last_4 = pw.tail(4)["tir"].mean()
        ctrl = pw["controller"].iloc[0]
        first_last.append({"patient_id": pid, "first": first_4, "last": last_4,
                          "change": last_4 - first_4, "controller": ctrl})

fl = pd.DataFrame(first_last)

# 2a: Paired comparison
for ctrl in ["loop", "trio", "openaps"]:
    fc = fl[fl["controller"] == ctrl]
    axes[0].scatter(fc["first"], fc["last"], s=80, label=ctrl.upper(),
                   color=colors[ctrl], edgecolors="k", zorder=3)
lim = [40, 100]
axes[0].plot(lim, lim, "k--", alpha=0.5, label="No change")
axes[0].set_xlabel("First 4 weeks TIR (%)")
axes[0].set_ylabel("Last 4 weeks TIR (%)")
axes[0].set_title("First vs Last Month TIR")
axes[0].legend()
axes[0].grid(True, alpha=0.3)

# 2b: Change histogram
axes[1].hist(fl["change"], bins=15, color="C3", alpha=0.7, edgecolor="k")
axes[1].axvline(0, color="k", ls="--")
axes[1].axvline(fl["change"].median(), color="red", ls="--", lw=2, label=f"Median: {fl['change'].median():.1f}%")
axes[1].set_xlabel("TIR change (last − first, pp)")
axes[1].set_ylabel("Count")
axes[1].set_title("TIR Change Distribution")
axes[1].legend()

# 2c: Summary
n_improved = (fl["change"] > 2).sum()
n_declined = (fl["change"] < -2).sum()
n_stable = len(fl) - n_improved - n_declined
t_stat, p_val = stats.ttest_1samp(fl["change"], 0) if len(fl) > 2 else (0, 1)

summary_text = (
    f"Patients with ≥8 weeks: {len(fl)}\n\n"
    f"Improved (>2pp): {n_improved} ({100*n_improved/len(fl):.0f}%)\n"
    f"Stable (±2pp):   {n_stable} ({100*n_stable/len(fl):.0f}%)\n"
    f"Declined (<-2pp): {n_declined} ({100*n_declined/len(fl):.0f}%)\n\n"
    f"Mean change: {fl['change'].mean():.1f}pp\n"
    f"Median change: {fl['change'].median():.1f}pp\n"
    f"t-test vs 0: t={t_stat:.2f}, p={p_val:.3f}"
)
axes[2].text(0.1, 0.5, summary_text, transform=axes[2].transAxes, fontsize=12,
            verticalalignment="center", fontfamily="monospace")
axes[2].axis("off")
axes[2].set_title("Summary")

plt.suptitle("EXP-2688: First Month vs Last Month TIR", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig(OUT / "fig2_first_vs_last.png", dpi=150)
plt.close()
print("Panel 2: First vs last month saved")

# ── Panel 3: Settings drift over time ─────────────────────────────────
fig, axes = plt.subplots(1, 3, figsize=(16, 5))
settings = [("mean_isf", "ISF (mg/dL/U)"), ("mean_cr", "CR (g/U)"), ("mean_basal", "Basal (U/h)")]

for ax, (col, ylabel) in zip(axes, settings):
    for pid in patients[:15]:  # limit for readability
        pw = weekly[weekly["patient_id"] == pid].sort_values("week")
        if col in pw.columns:
            ctrl = pw["controller"].iloc[0]
            ax.plot(pw["week"], pw[col], alpha=0.5, color=colors.get(ctrl, "gray"), lw=1)
    ax.set_xlabel("Week")
    ax.set_ylabel(ylabel)
    ax.set_title(f"{ylabel} Over Time")
    ax.grid(True, alpha=0.3)

plt.suptitle("EXP-2688: Settings Drift Over Time (per patient)", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig(OUT / "fig3_settings_drift.png", dpi=150)
plt.close()
print("Panel 3: Settings drift saved")

# ── Panel 4: Controller aggressiveness over time ──────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 5))

for pid in patients[:15]:
    pw = weekly[weekly["patient_id"] == pid].sort_values("week")
    ctrl = pw["controller"].iloc[0]
    color = colors.get(ctrl, "gray")
    
    if "smb_rate" in pw.columns:
        axes[0].plot(pw["week"], pw["smb_rate"], alpha=0.4, color=color, lw=1)
    if "suspend_pct" in pw.columns:
        axes[1].plot(pw["week"], pw["suspend_pct"], alpha=0.4, color=color, lw=1)

axes[0].set_xlabel("Week")
axes[0].set_ylabel("SMB rate (%)")
axes[0].set_title("SMB Delivery Rate Over Time")
axes[0].grid(True, alpha=0.3)

axes[1].set_xlabel("Week")
axes[1].set_ylabel("Suspend rate (%)")
axes[1].set_title("Basal Suspend Rate Over Time")
axes[1].grid(True, alpha=0.3)

controllers = ["loop", "trio", "openaps"]

# Add legend
from matplotlib.lines import Line2D
legend_elements = [Line2D([0], [0], color=colors[c], lw=2, label=c.upper()) for c in controllers]
axes[0].legend(handles=legend_elements)

plt.suptitle("EXP-2688: Controller Aggressiveness Over Time", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig(OUT / "fig4_aggressiveness.png", dpi=150)
plt.close()
print("Panel 4: Aggressiveness saved")

# ── Panel 5: Days-on-AID vs TIR (learning curve) ─────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 5))

# Aggregate: for each patient, compute their data span and overall TIR
patient_span = grid.groupby("patient_id").agg(
    span_days=("time", lambda x: (x.max() - x.min()).total_seconds() / 86400),
    tir=("glucose", lambda x: 100 * ((x >= 70) & (x <= 180)).mean()),
    controller=("controller", "first"),
).reset_index()

for ctrl in controllers:
    ps = patient_span[patient_span["controller"] == ctrl]
    axes[0].scatter(ps["span_days"], ps["tir"], s=80, label=ctrl.upper(),
                   color=colors[ctrl], edgecolors="k", zorder=3)

axes[0].set_xlabel("Days of data")
axes[0].set_ylabel("Overall TIR (%)")
axes[0].set_title("Data Span vs TIR")
axes[0].legend()
axes[0].grid(True, alpha=0.3)

# Per-patient trend slopes
trend_data = []
for pid in patients:
    pw = weekly[weekly["patient_id"] == pid].sort_values("week")
    if len(pw) >= 4:
        slope, _, r, p, _ = stats.linregress(pw["week"], pw["tir"])
        ctrl = pw["controller"].iloc[0]
        trend_data.append({"patient_id": pid, "slope": slope, "r": r, "p": p, "controller": ctrl})

td = pd.DataFrame(trend_data)
for ctrl in controllers:
    tc = td[td["controller"] == ctrl]
    axes[1].scatter(tc.index, tc["slope"], s=80, label=ctrl.upper(),
                   color=colors[ctrl], edgecolors="k", zorder=3)

axes[1].axhline(0, color="k", ls="--", alpha=0.5)
axes[1].set_xlabel("Patient")
axes[1].set_ylabel("TIR slope (pp/week)")
axes[1].set_title(f"TIR Trend per Patient (n={len(td)})")
sig_improving = (td["slope"] > 0) & (td["p"] < 0.05)
sig_declining = (td["slope"] < 0) & (td["p"] < 0.05)
axes[1].text(0.02, 0.95, f"Sig. improving: {sig_improving.sum()}\nSig. declining: {sig_declining.sum()}\nNon-sig: {len(td)-sig_improving.sum()-sig_declining.sum()}",
            transform=axes[1].transAxes, fontsize=10, va="top")
axes[1].legend()

plt.suptitle("EXP-2688: Learning Curve — Do Outcomes Improve Over Time?", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig(OUT / "fig5_learning_curve.png", dpi=150)
plt.close()
print("Panel 5: Learning curve saved")

# ── Results ────────────────────────────────────────────────────────────
results = {
    "experiment": "EXP-2688",
    "title": "Within-Patient Temporal Trends",
    "n_patients": len(patients),
    "n_with_8_weeks": len(fl),
    "tir_change_mean": float(fl["change"].mean()),
    "tir_change_median": float(fl["change"].median()),
    "tir_change_ttest_p": float(p_val),
    "sig_improving": int(sig_improving.sum()),
    "sig_declining": int(sig_declining.sum()),
    "non_significant": int(len(td) - sig_improving.sum() - sig_declining.sum()),
    "median_slope_pp_week": float(td["slope"].median()),
}
(EXP / "exp-2688_temporal_trends.json").write_text(json.dumps(results, indent=2))

print(f"""
{'='*60}
EXP-2688: Within-Patient Temporal Trends — SUMMARY
{'='*60}

  Patients with ≥8 weeks data: {len(fl)}
  
  TIR CHANGE (first 4 weeks → last 4 weeks):
    Mean:   {fl['change'].mean():.1f} pp
    Median: {fl['change'].median():.1f} pp
    t-test: p={p_val:.3f}
    
  WEEKLY TIR TREND (linear regression per patient):
    Sig. improving (p<0.05): {sig_improving.sum()}
    Sig. declining (p<0.05): {sig_declining.sum()}
    Non-significant:         {len(td) - sig_improving.sum() - sig_declining.sum()}
    Median slope: {td['slope'].median():.3f} pp/week
""")
