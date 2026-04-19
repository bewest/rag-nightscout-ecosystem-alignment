#!/usr/bin/env python3
"""EXP-2687: Null Model Benchmark — Regression to the Mean

Quantifies how much of the observed "correction effect" (BG drop after bolus)
is simply regression to the mean vs. actual treatment effect.

Key question: If we select BG≥180 time points WITHOUT a bolus, how much do
they drop over 2h? This establishes the null baseline.

Panels:
  1. BG drop: bolus events vs no-bolus events (matched BG₀)
  2. BG trajectory: bolus vs no-bolus over 0–2h
  3. Treatment effect = bolus_drop − null_drop as function of BG₀
  4. Dose-response after null subtraction
  5. Controller-stratified null model
  6. Patient equilibrium BG and regression strength
"""

import json, pathlib, warnings
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy import stats

warnings.filterwarnings("ignore")
OUT = pathlib.Path("visualizations/null-model")
OUT.mkdir(parents=True, exist_ok=True)
EXP = pathlib.Path("externals/experiments")

# ── Load data ──────────────────────────────────────────────────────────
grid = pd.read_parquet("externals/ns-parquet/training/grid.parquet")
ds = pd.read_parquet("externals/ns-parquet/training/devicestatus.parquet")
ctrl_map = ds.groupby("patient_id")["controller"].first().to_dict()
grid["controller"] = grid["patient_id"].map(ctrl_map)

manifest = json.loads((EXP / "autoprepare-qualified.json").read_text())
qual = manifest["qualified_patients"]
grid = grid[grid["patient_id"].isin(qual)]
grid = grid.sort_values(["patient_id", "time"]).reset_index(drop=True)

# ── Extract events ─────────────────────────────────────────────────────
# For each 5-min row with BG≥180, classify as bolus or no-bolus
# Then look ahead 24 rows (2h) for BG drop

FLOOR = 180
HORIZON = 24  # 2h in 5-min steps
MIN_ISOLATION = 6  # 30min no prior bolus for "no-bolus" events

def extract_events(df):
    """Extract bolus and no-bolus events with 2h forward BG."""
    events = []
    for pid in df["patient_id"].unique():
        pg = df[df["patient_id"] == pid].reset_index(drop=True)
        ctrl = pg["controller"].iloc[0] if "controller" in pg.columns else "unknown"
        glucose = pg["glucose"].values
        bolus = pg["bolus"].values if "bolus" in pg.columns else np.zeros(len(pg))
        
        # Patient equilibrium BG
        eq_bg = np.nanmedian(glucose)
        
        for i in range(MIN_ISOLATION, len(pg) - HORIZON):
            bg0 = glucose[i]
            if np.isnan(bg0) or bg0 < FLOOR:
                continue
            
            bg_2h = glucose[i + HORIZON]
            if np.isnan(bg_2h):
                continue
            
            # Trajectory
            traj = glucose[i:i + HORIZON + 1]
            if np.sum(np.isnan(traj)) > 6:  # skip if too many gaps
                continue
            
            has_bolus = bolus[i] > 0.5  # meaningful bolus at this time
            prior_bolus = np.nansum(bolus[max(0, i - MIN_ISOLATION):i])
            
            # For no-bolus: also require no bolus in the next 2h
            future_bolus = np.nansum(bolus[i:i + HORIZON])
            
            # Also check no carbs in 2h window for cleaner no-bolus events
            if "carbs" in pg.columns:
                carbs_window = pg["carbs"].values[i:i + HORIZON]
                carbs_2h = np.nansum(carbs_window)
            else:
                carbs_2h = 0
            
            if has_bolus and prior_bolus < 0.5:
                # Bolus event with clean prior
                events.append({
                    "patient_id": pid, "controller": ctrl,
                    "bg0": bg0, "bg_2h": bg_2h, "drop": bg0 - bg_2h,
                    "dose": bolus[i], "eq_bg": eq_bg,
                    "event_type": "bolus", "carbs_2h": carbs_2h,
                    "traj": traj.tolist(),
                })
            elif not has_bolus and future_bolus < 0.5 and prior_bolus < 0.5 and carbs_2h < 5:
                # No-bolus, no-carb event — pure regression to mean
                events.append({
                    "patient_id": pid, "controller": ctrl,
                    "bg0": bg0, "bg_2h": bg_2h, "drop": bg0 - bg_2h,
                    "dose": 0, "eq_bg": eq_bg,
                    "event_type": "no_bolus", "carbs_2h": carbs_2h,
                    "traj": traj.tolist(),
                })
    return pd.DataFrame(events)

print("Extracting events (BG≥180, 2h horizon)...")
ev = extract_events(grid)
bolus_ev = ev[ev["event_type"] == "bolus"]
null_ev = ev[ev["event_type"] == "no_bolus"]
print(f"  Bolus events: {len(bolus_ev)}")
print(f"  No-bolus events: {len(null_ev)}")

# ── Panel 1: BG drop comparison ───────────────────────────────────────
fig, axes = plt.subplots(1, 3, figsize=(15, 5))

# 1a: Histogram of drops
axes[0].hist(bolus_ev["drop"], bins=50, alpha=0.6, label=f"Bolus (n={len(bolus_ev)})", color="C0", density=True)
axes[0].hist(null_ev["drop"], bins=50, alpha=0.6, label=f"No-bolus (n={len(null_ev)})", color="C1", density=True)
axes[0].axvline(bolus_ev["drop"].median(), color="C0", ls="--", lw=2)
axes[0].axvline(null_ev["drop"].median(), color="C1", ls="--", lw=2)
axes[0].set_xlabel("BG drop (mg/dL)")
axes[0].set_ylabel("Density")
axes[0].set_title("2h BG Drop Distribution")
axes[0].legend()

# 1b: BG₀-matched comparison
bg_bins = np.arange(180, 350, 20)
bolus_means = []
null_means = []
bin_centers = []
for lo, hi in zip(bg_bins[:-1], bg_bins[1:]):
    b = bolus_ev[(bolus_ev["bg0"] >= lo) & (bolus_ev["bg0"] < hi)]
    n = null_ev[(null_ev["bg0"] >= lo) & (null_ev["bg0"] < hi)]
    if len(b) >= 10 and len(n) >= 10:
        bolus_means.append(b["drop"].mean())
        null_means.append(n["drop"].mean())
        bin_centers.append((lo + hi) / 2)

axes[1].plot(bin_centers, bolus_means, "o-", label="Bolus", color="C0", lw=2)
axes[1].plot(bin_centers, null_means, "s-", label="No-bolus (null)", color="C1", lw=2)
treatment_effect = [b - n for b, n in zip(bolus_means, null_means)]
axes[1].plot(bin_centers, treatment_effect, "^--", label="Treatment effect", color="C2", lw=2)
axes[1].set_xlabel("Starting BG (mg/dL)")
axes[1].set_ylabel("Mean 2h BG drop (mg/dL)")
axes[1].set_title("BG₀-Matched: Bolus vs Null")
axes[1].legend()
axes[1].grid(True, alpha=0.3)

# 1c: Summary stats
summary_data = {
    "Metric": ["Median drop", "Mean drop", "% positive drop", "Mean BG₀"],
    "Bolus": [
        f"{bolus_ev['drop'].median():.1f}",
        f"{bolus_ev['drop'].mean():.1f}",
        f"{100*(bolus_ev['drop']>0).mean():.1f}%",
        f"{bolus_ev['bg0'].mean():.0f}",
    ],
    "No-bolus": [
        f"{null_ev['drop'].median():.1f}",
        f"{null_ev['drop'].mean():.1f}",
        f"{100*(null_ev['drop']>0).mean():.1f}%",
        f"{null_ev['bg0'].mean():.0f}",
    ],
}
axes[2].axis("off")
table = axes[2].table(
    cellText=list(zip(summary_data["Metric"], summary_data["Bolus"], summary_data["No-bolus"])),
    colLabels=["Metric", "Bolus", "No-bolus"],
    loc="center", cellLoc="center",
)
table.auto_set_font_size(False)
table.set_fontsize(11)
table.scale(1.2, 1.8)
axes[2].set_title("Summary Statistics")

plt.suptitle("EXP-2687: Null Model — Bolus vs No-Bolus BG Drop", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig(OUT / "fig1_null_vs_bolus.png", dpi=150)
plt.close()
print("Panel 1: Null vs bolus comparison saved")

# ── Panel 2: Mean trajectory ──────────────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 5))
t_min = np.arange(0, (HORIZON + 1) * 5, 5)

# 2a: Raw trajectories
for ev_type, label, color in [("bolus", "Bolus", "C0"), ("no_bolus", "No-bolus", "C1")]:
    subset = ev[ev["event_type"] == ev_type]
    trajs = np.array(subset["traj"].tolist())
    mean_traj = np.nanmean(trajs, axis=0)
    p25 = np.nanpercentile(trajs, 25, axis=0)
    p75 = np.nanpercentile(trajs, 75, axis=0)
    axes[0].plot(t_min, mean_traj, lw=2, label=f"{label} (n={len(subset)})", color=color)
    axes[0].fill_between(t_min, p25, p75, alpha=0.2, color=color)

axes[0].set_xlabel("Minutes after event")
axes[0].set_ylabel("BG (mg/dL)")
axes[0].set_title("Mean BG Trajectory (raw)")
axes[0].legend()
axes[0].grid(True, alpha=0.3)

# 2b: Normalized (delta from BG₀)
for ev_type, label, color in [("bolus", "Bolus", "C0"), ("no_bolus", "No-bolus", "C1")]:
    subset = ev[ev["event_type"] == ev_type]
    trajs = np.array(subset["traj"].tolist())
    bg0s = trajs[:, 0:1]
    delta_trajs = bg0s - trajs  # positive = BG falling
    mean_delta = np.nanmean(delta_trajs, axis=0)
    p25 = np.nanpercentile(delta_trajs, 25, axis=0)
    p75 = np.nanpercentile(delta_trajs, 75, axis=0)
    axes[1].plot(t_min, mean_delta, lw=2, label=f"{label}", color=color)
    axes[1].fill_between(t_min, p25, p75, alpha=0.2, color=color)

axes[1].set_xlabel("Minutes after event")
axes[1].set_ylabel("BG drop from start (mg/dL)")
axes[1].set_title("Mean BG Drop Trajectory (Δ from BG₀)")
axes[1].axhline(0, color="k", ls=":", alpha=0.5)
axes[1].legend()
axes[1].grid(True, alpha=0.3)

plt.suptitle("EXP-2687: BG Trajectory — Bolus vs No-Bolus Events", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig(OUT / "fig2_trajectory.png", dpi=150)
plt.close()
print("Panel 2: Trajectory comparison saved")

# ── Panel 3: Treatment effect by BG₀ ─────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 5))

# 3a: Treatment effect (bolus drop − null drop) by BG₀ bin
axes[0].bar(range(len(bin_centers)), treatment_effect, color="C2", alpha=0.7)
axes[0].set_xticks(range(len(bin_centers)))
axes[0].set_xticklabels([f"{int(c)}" for c in bin_centers])
axes[0].set_xlabel("Starting BG bin center (mg/dL)")
axes[0].set_ylabel("Treatment effect (mg/dL)")
axes[0].set_title("Treatment Effect = Bolus Drop − Null Drop")
axes[0].axhline(0, color="k", ls=":", alpha=0.5)
axes[0].grid(True, alpha=0.3)

# 3b: Null model as % of total drop
null_pct = [n / b * 100 if b > 0 else 0 for b, n in zip(bolus_means, null_means)]
axes[1].bar(range(len(bin_centers)), null_pct, color="C1", alpha=0.7)
axes[1].set_xticks(range(len(bin_centers)))
axes[1].set_xticklabels([f"{int(c)}" for c in bin_centers])
axes[1].set_xlabel("Starting BG bin center (mg/dL)")
axes[1].set_ylabel("Null model as % of bolus drop")
axes[1].set_title("Regression to Mean as % of Total Drop")
axes[1].axhline(100, color="r", ls="--", alpha=0.5, label="100% = no treatment effect")
axes[1].legend()
axes[1].grid(True, alpha=0.3)

plt.suptitle("EXP-2687: Treatment Effect After Null Subtraction", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig(OUT / "fig3_treatment_effect.png", dpi=150)
plt.close()
print("Panel 3: Treatment effect saved")

# ── Panel 4: Dose-response after null subtraction ─────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 5))

# Match each bolus event to the expected null drop for its BG₀
# Use a simple linear regression of null drops on BG₀
null_fit = np.polyfit(null_ev["bg0"], null_ev["drop"], 1)
bolus_ev = bolus_ev.copy()
bolus_ev["null_expected"] = np.polyval(null_fit, bolus_ev["bg0"])
bolus_ev["treatment_drop"] = bolus_ev["drop"] - bolus_ev["null_expected"]

# 4a: Raw dose vs drop
axes[0].scatter(bolus_ev["dose"], bolus_ev["drop"], alpha=0.1, s=5, color="C0")
axes[0].set_xlabel("Bolus dose (U)")
axes[0].set_ylabel("Raw BG drop (mg/dL)")
r_raw, p_raw = stats.pearsonr(bolus_ev["dose"].dropna(), bolus_ev["drop"].dropna())
axes[0].set_title(f"Raw: r={r_raw:.3f}, p={p_raw:.2e}")
axes[0].grid(True, alpha=0.3)

# 4b: Dose vs treatment effect (null-subtracted)
axes[1].scatter(bolus_ev["dose"], bolus_ev["treatment_drop"], alpha=0.1, s=5, color="C2")
axes[1].set_xlabel("Bolus dose (U)")
axes[1].set_ylabel("Treatment drop (null-subtracted, mg/dL)")
mask = bolus_ev["treatment_drop"].notna() & bolus_ev["dose"].notna()
r_tx, p_tx = stats.pearsonr(bolus_ev.loc[mask, "dose"], bolus_ev.loc[mask, "treatment_drop"])
axes[1].set_title(f"Null-subtracted: r={r_tx:.3f}, p={p_tx:.2e}")
axes[1].axhline(0, color="k", ls=":", alpha=0.5)
axes[1].grid(True, alpha=0.3)

plt.suptitle("EXP-2687: Dose-Response Before and After Null Subtraction", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig(OUT / "fig4_dose_response.png", dpi=150)
plt.close()
print("Panel 4: Dose-response saved")

# ── Panel 5: Controller-stratified null model ─────────────────────────
fig, axes = plt.subplots(1, 3, figsize=(16, 5))
controllers = ["loop", "trio", "openaps"]
colors = {"loop": "C0", "trio": "C1", "openaps": "C2"}

for ax, ctrl in zip(axes, controllers):
    b = bolus_ev[bolus_ev["controller"] == ctrl]
    n = null_ev[null_ev["controller"] == ctrl]
    
    ax.hist(b["drop"], bins=40, alpha=0.5, label=f"Bolus (n={len(b)})", color="C0", density=True)
    ax.hist(n["drop"], bins=40, alpha=0.5, label=f"No-bolus (n={len(n)})", color="C1", density=True)
    ax.axvline(b["drop"].median(), color="C0", ls="--", lw=2)
    ax.axvline(n["drop"].median(), color="C1", ls="--", lw=2)
    
    diff = b["drop"].median() - n["drop"].median()
    ax.set_title(f"{ctrl.upper()}\nBolus: {b['drop'].median():.0f}, Null: {n['drop'].median():.0f}, Δ={diff:.0f}")
    ax.set_xlabel("BG drop (mg/dL)")
    ax.legend(fontsize=8)

plt.suptitle("EXP-2687: Controller-Stratified Null Model", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig(OUT / "fig5_controller_null.png", dpi=150)
plt.close()
print("Panel 5: Controller null model saved")

# ── Panel 6: Patient equilibrium and regression ───────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 5))

# 6a: Patient equilibrium BG vs TIR
patient_stats = grid.groupby("patient_id").agg(
    eq_bg=("glucose", "median"),
    tir=("glucose", lambda x: 100 * ((x >= 70) & (x <= 180)).mean()),
    controller=("controller", "first"),
).reset_index()

for ctrl in controllers:
    ps = patient_stats[patient_stats["controller"] == ctrl]
    axes[0].scatter(ps["eq_bg"], ps["tir"], s=80, label=ctrl.upper(), color=colors[ctrl], edgecolors="k", zorder=3)
axes[0].set_xlabel("Median BG (mg/dL)")
axes[0].set_ylabel("TIR (%)")
axes[0].set_title("Patient Equilibrium BG vs TIR")
axes[0].legend()
axes[0].grid(True, alpha=0.3)

# 6b: Regression strength by patient
# For each patient's null events: r(BG₀, drop)
reg_data = []
for pid in null_ev["patient_id"].unique():
    pn = null_ev[null_ev["patient_id"] == pid]
    if len(pn) >= 20:
        r, p = stats.pearsonr(pn["bg0"], pn["drop"])
        ctrl = pn["controller"].iloc[0]
        reg_data.append({"patient_id": pid, "r": r, "p": p, "n": len(pn), "controller": ctrl})

reg_df = pd.DataFrame(reg_data)
for ctrl in controllers:
    rd = reg_df[reg_df["controller"] == ctrl]
    axes[1].scatter(rd["n"], rd["r"], s=80, label=ctrl.upper(), color=colors[ctrl], edgecolors="k", zorder=3)
axes[1].set_xlabel("N null events")
axes[1].set_ylabel("r(BG₀, drop) — regression strength")
axes[1].set_title("Regression to Mean Strength by Patient")
axes[1].axhline(0, color="k", ls=":", alpha=0.5)
axes[1].legend()
axes[1].grid(True, alpha=0.3)

plt.suptitle("EXP-2687: Patient Equilibrium & Regression to Mean", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig(OUT / "fig6_patient_equilibrium.png", dpi=150)
plt.close()
print("Panel 6: Patient equilibrium saved")

# ── Summary ────────────────────────────────────────────────────────────
overall_null_median = null_ev["drop"].median()
overall_bolus_median = bolus_ev["drop"].median()
treatment_median = overall_bolus_median - overall_null_median
null_pct_overall = overall_null_median / overall_bolus_median * 100 if overall_bolus_median > 0 else 0

results = {
    "experiment": "EXP-2687",
    "title": "Null Model Benchmark",
    "bolus_events": int(len(bolus_ev)),
    "null_events": int(len(null_ev)),
    "bolus_drop_median": float(overall_bolus_median),
    "bolus_drop_mean": float(bolus_ev["drop"].mean()),
    "null_drop_median": float(overall_null_median),
    "null_drop_mean": float(null_ev["drop"].mean()),
    "treatment_effect_median": float(treatment_median),
    "null_as_pct_of_bolus": float(null_pct_overall),
    "null_fit_slope": float(null_fit[0]),
    "null_fit_intercept": float(null_fit[1]),
    "dose_r_raw": float(r_raw),
    "dose_r_null_subtracted": float(r_tx),
    "by_controller": {},
}

for ctrl in controllers:
    b = bolus_ev[bolus_ev["controller"] == ctrl]
    n = null_ev[null_ev["controller"] == ctrl]
    results["by_controller"][ctrl] = {
        "bolus_n": int(len(b)),
        "null_n": int(len(n)),
        "bolus_drop_median": float(b["drop"].median()) if len(b) > 0 else None,
        "null_drop_median": float(n["drop"].median()) if len(n) > 0 else None,
        "treatment_effect": float(b["drop"].median() - n["drop"].median()) if len(b) > 0 and len(n) > 0 else None,
    }

(EXP / "exp-2687_null_model.json").write_text(json.dumps(results, indent=2))

print(f"""
{'='*60}
EXP-2687: Null Model Benchmark — SUMMARY
{'='*60}

  Bolus events: {len(bolus_ev)}
  No-bolus events: {len(null_ev)} (BG≥180, no bolus/carbs in 2h window)

  OVERALL:
    Bolus drop (median): {overall_bolus_median:.1f} mg/dL
    Null drop (median):  {overall_null_median:.1f} mg/dL
    Treatment effect:    {treatment_median:.1f} mg/dL
    Null as % of bolus:  {null_pct_overall:.1f}%

  DOSE-RESPONSE:
    Raw r(dose, drop):          {r_raw:.3f}
    Null-subtracted r(dose, Δ): {r_tx:.3f}

  BY CONTROLLER:""")

for ctrl in controllers:
    d = results["by_controller"][ctrl]
    tx = d["treatment_effect"] if d["treatment_effect"] is not None else 0
    print(f"    {ctrl.upper()}: bolus={d['bolus_drop_median']:.0f}, null={d['null_drop_median']:.0f}, Δ={tx:.0f} mg/dL (n_bolus={d['bolus_n']}, n_null={d['null_n']})")
